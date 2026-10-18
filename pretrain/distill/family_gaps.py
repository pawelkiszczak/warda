"""Measure where a fine-tuned student lags the teacher, per distillation question family, and write sampling weights.

Scores teacher-labelled items the student never trained on (e.g. a fresh probe pool) with the student run's calibrated
predictor, compares with the teacher distribution (argmax agreement and KL(teacher‖student)), and writes
`work/distill/family_weights.json` with weight = clip(KL / mean KL, 0.5, 3) per family, for
`build_pool.py --family-weights`.

    uv run python pretrain/distill/family_gaps.py --run jev-joint-v2 --items pretrain/work/distill/teacher_probe2.jsonl
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sft  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "distill" / "family_weights.json")
    a = ap.parse_args()
    run = ROOT / "work" / "runs" / a.run
    model, _, _, pointer = sft.load_model(run)
    temps = json.loads((run / "calibration.json").read_text())["temperatures"]
    enc = sft.Encoder(AutoTokenizer.from_pretrained(sft.TOKENIZER))
    items = sft.load_jsonl(a.items)
    logits = sft.predict(model, pointer, enc, items, 16384)
    stats: defaultdict[str, dict[str, int | float]] = defaultdict(lambda: {"n": 0, "agree": 0, "kl": 0.0})
    for it in items:
        p, _ = sft.probs_at(logits[it["id"]], sft.temp_for(temps, it))
        t = it["target"]
        s = stats[it["family"]]
        s["n"] += 1
        s["agree"] += int(max(range(len(t)), key=t.__getitem__) == int(p.argmax()))
        s["kl"] += sum(ti * math.log(max(ti, 1e-9) / max(float(pi), 1e-9)) for ti, pi in zip(t, p, strict=False))
    mean_kl = sum(s["kl"] for s in stats.values()) / sum(s["n"] for s in stats.values())
    report = {f: {"n": s["n"], "agreement": s["agree"] / s["n"], "kl": s["kl"] / s["n"]} for f, s in stats.items()}
    weights = {f: round(min(3.0, max(0.5, r["kl"] / mean_kl)), 2) for f, r in report.items()}
    a.out.write_text(json.dumps(weights, indent=2, ensure_ascii=False))
    for f, r in sorted(report.items(), key=lambda x: -x[1]["kl"]):
        print(f"{f:28s} n={r['n']:4d} agree={r['agreement']:.2f} KL={r['kl']:.3f} weight={weights[f]}")
    print(f"mean KL {mean_kl:.3f}; weights -> {a.out}")


if __name__ == "__main__":
    main()
