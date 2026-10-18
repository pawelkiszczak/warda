"""Compare basal-1.0 (served by `basal-serve`) with basal-scratch runs on the same evaluation items.

Each set is subsampled (seeded) to at most `--per-set` items so every model sees exactly the same items. basal is
queried through its `/v1/systemone` API (both option orders and its own calibration, as served). basal-scratch runs
use `sft.py`'s predictor with their `calibration.json`. Reports accuracy, NLL of the gold option, ECE and decisions/s
per model and set into `work/compare_basal.json`.

    # terminal 1: .venv-basal/bin/basal-serve --model Remek/basal-1.0-1.5B --mode mlx --port 8078
    pretrain/.venv/bin/python pretrain/compare_basal.py --basal basal-1.0-1.5B=http://127.0.0.1:8078/v1/systemone
    pretrain/.venv/bin/python pretrain/compare_basal.py --runs jev-joint-v3 jev-joint-v4
"""
import argparse
import json
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from transformers import AutoTokenizer

import sft

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "distill"))
from label_teacher import server_question  # noqa: E402

SETS = {
    "pl_test": ROOT / "work" / "sft" / "test.jsonl",
    "basal_examples": None,
    "pl_real": ROOT / "work" / "sft_jev" / "ext" / "pl_real.jsonl",
    "pl_real_t45": ROOT / "work" / "sft_jev" / "ext" / "pl_real_t45.jsonl",
    "openjev_test": ROOT / "work" / "sft_jev" / "ext" / "openjev_test.jsonl",
    "openjev_ood": ROOT / "work" / "sft_jev" / "ext" / "openjev_ood.jsonl",
    "tasksource_test": ROOT / "work" / "sft_jev" / "ext" / "tasksource_test.jsonl",
    "kaivoss_test": ROOT / "work" / "sft_jev" / "ext" / "kaivoss_test.jsonl",
}
OUT = ROOT / "work" / "compare_basal.json"


def load_sets(per_set, seed):
    sets = {}
    for name, path in SETS.items():
        items = sft.examples() if path is None else sft.load_jsonl(path)
        rng = random.Random(seed)
        sets[name] = items if len(items) <= per_set else rng.sample(items, per_set)
    return sets


def summarize(items, probs, seconds):
    correct, nll, conf = [], [], []
    for it in items:
        p = probs[it["id"]]
        correct.append(int(np.argmax(p)) == it["gold"])
        nll.append(-math.log(max(p[it["gold"]], 1e-12)))
        conf.append(float(np.max(p)))
    correct, conf = np.array(correct), np.array(conf)
    bins = np.minimum((conf * 15).astype(int), 14)
    ece = sum(abs(correct[bins == b].mean() - conf[bins == b].mean()) * (bins == b).mean()
              for b in range(15) if (bins == b).any())
    return {"n": len(items), "accuracy": float(correct.mean()), "nll": float(np.mean(nll)), "ece": float(ece),
            "decisions_per_s": len(items) / max(seconds, 1e-9)}


def basal_probs(item, url):
    state = item["state"] if isinstance(item["state"], str) else json.dumps(item["state"], ensure_ascii=False)
    q = server_question(item)
    r = requests.post(url, json={"state": state, "questions": {"q": q}}, timeout=600)
    r.raise_for_status()
    ans = r.json()["answers"]["q"]
    k = len(item["options"])
    if item["type"] == "noul":
        p = [float(ans["noul"]), 1 - float(ans["noul"])]
    elif item["type"] == "score":
        p = [float(ans["probabilities"][str(i)]) for i in range(k)]
    else:
        p = [float(ans["probabilities"][f"o{i}"]) for i in range(k)]
    p = np.array(p) / sum(p)
    return item["id"], p


def run_basal(name, url, sets, workers):
    out = {}
    for set_name, items in sets.items():
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            probs = dict(ex.map(lambda it: basal_probs(it, url), items))
        out[set_name] = summarize(items, probs, time.perf_counter() - t0)
        print(name, set_name, json.dumps(out[set_name]), flush=True)
    return out


def run_scratch(run, sets, enc):
    model, _, _, pointer = sft.load_model(ROOT / "work" / "runs" / run)
    temps = json.loads((ROOT / "work" / "runs" / run / "calibration.json").read_text())["temperatures"]
    out = {}
    for set_name, items in sets.items():
        t0 = time.perf_counter()
        logits = sft.predict(model, pointer, enc, items, 16384)
        probs = {it["id"]: sft.probs_at(logits[it["id"]], sft.temp_for(temps, it))[0] for it in items}
        out[set_name] = summarize(items, probs, time.perf_counter() - t0)
        print(run, set_name, json.dumps(out[set_name]), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basal", nargs="*", default=[], metavar="NAME=URL")
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--per-set", type=int, default=800)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    sets = load_sets(a.per_set, a.seed)
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for spec in a.basal:
        name, url = spec.split("=", 1)
        results[name] = run_basal(name, url, sets, a.workers)
        OUT.write_text(json.dumps(results, indent=2))
    if a.runs:
        enc = sft.Encoder(AutoTokenizer.from_pretrained(sft.TOKENIZER))
        for run in a.runs:
            results[run] = run_scratch(run, sets, enc)
            OUT.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
