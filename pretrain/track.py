"""Mirror a run's local logs into a local MLflow store. Works on finished runs and, with --follow, on runs still training.

Store: `pretrain/work/mlflow.db` (SQLite) + `pretrain/work/mlflow-artifacts/`, experiment `warda-scratch`. No account or
network needed. View with:

    pretrain/.venv/bin/mlflow ui --backend-store-uri sqlite:///pretrain/work/mlflow.db --port 5000

Reads `pretrain/work/runs/<name>/`: `config.json` (params), `metrics.jsonl` (pretraining: loss, lr, grad norm, expert
load, throughput, per-source validation loss; greedy samples become text artifacts), `sft.jsonl` (fine-tuning loss and
per-epoch dev metrics) and `eval.json` (final metrics + the file as an artifact). Progress is kept in `<run>/mlflow.json`,
so rerunning resumes the same MLflow run without duplicating steps. The trainers stay tracker-free.

    pretrain/.venv/bin/python pretrain/track.py s126m-1b              # backfill once
    pretrain/.venv/bin/python pretrain/track.py jev-joint-v2 --follow  # mirror a live run until it finishes
    pretrain/.venv/bin/python pretrain/track.py --all                 # backfill every run directory
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
import mlflow
from mlflow.entities import Metric, Param
from mlflow.tracking import MlflowClient

WORK = Path(__file__).resolve().parent / "work"
RUNS = WORK / "runs"
URI = f"sqlite:///{WORK / 'mlflow.db'}"
EXPERIMENT = "warda-scratch"


def key(k):
    """MLflow keys allow [A-Za-z0-9_-./ ]; map everything else (ł, @, …) to '_'."""
    return re.sub(r"[^A-Za-z0-9_\-./ ]", "_", k)


def flatten(prefix, d):
    out = {}
    for k, v in d.items():
        name = f"{prefix}/{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(name, v))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key(name)] = float(v)
    return out


def flat_params(d, prefix=""):
    out = {}
    for k, v in d.items():
        name = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flat_params(v, name))
        else:
            out[key(name)] = str(v)[:500]
    return out


def new_lines(path, done):
    if not path.exists():
        return []
    lines = [line for line in path.read_text().split("\n") if line.strip()]
    return [json.loads(line) for line in lines[done:]]


def records(fname, rec, last_step):
    """(step, metrics dict, samples text or None) for one log record."""
    if fname == "metrics.jsonl":
        d = {
            f"train/{k}": float(rec[k])
            for k in ("loss", "lr", "gnorm", "max_load_ratio", "tok_s", "tokens")
            if k in rec
        }
        d.update(flatten("val", rec.get("val", {})))
        samples = "\n\n".join(rec["samples"]) if "samples" in rec else None
        return rec["step"], d, samples
    if "dev" in rec:
        return last_step, {**flatten("dev", rec["dev"]), "sft/epoch": float(rec["epoch"])}, None
    return (
        rec["step"],
        {"sft/loss": float(rec["loss"]), "sft/lr": float(rec["lr"]), "sft/epoch": float(rec["epoch"])},
        None,
    )


def sync(name, follow, poll):
    run_dir = RUNS / name
    state_path = run_dir / "mlflow.json"
    state: dict[str, Any] = (
        json.loads(state_path.read_text())
        if state_path.exists()
        else {
            "run_id": None,
            "lines": {"metrics.jsonl": 0, "sft.jsonl": 0},
            "eval_logged": False,
            "step": 0,
            "params": False,
        }
    )
    client = MlflowClient()
    exp = client.get_experiment_by_name(EXPERIMENT) or client.get_experiment(
        client.create_experiment(EXPERIMENT, artifact_location=(WORK / "mlflow-artifacts").as_uri())
    )
    if state["run_id"] is None:
        job = "sft" if (run_dir / "sft.jsonl").exists() else "pretrain"
        state["run_id"] = client.create_run(exp.experiment_id, run_name=name, tags={"job_type": job}).info.run_id
    rid = state["run_id"]
    while True:
        if not state["params"] and (run_dir / "config.json").exists():
            params = flat_params(json.loads((run_dir / "config.json").read_text()))
            items = [Param(k, v) for k, v in params.items()]
            for i in range(0, len(items), 100):
                client.log_batch(rid, params=items[i : i + 100])
            state["params"] = True
        for fname in ("metrics.jsonl", "sft.jsonl"):
            recs = new_lines(run_dir / fname, state["lines"][fname])
            batch, now = [], int(time.time() * 1000)
            for rec in recs:
                step, d, samples = records(fname, rec, state["step"])
                state["step"] = max(state["step"], step)
                batch += [Metric(k, v, now, state["step"]) for k, v in d.items()]
                if samples:
                    client.log_text(rid, samples, f"samples/step_{state['step']:06d}.txt")
            for i in range(0, len(batch), 1000):
                client.log_batch(rid, metrics=batch[i : i + 1000])
            state["lines"][fname] += len(recs)
        if (run_dir / "eval.json").exists() and not state["eval_logged"]:
            ev = json.loads((run_dir / "eval.json").read_text())
            now = int(time.time() * 1000)
            batch = [Metric(k, v, now, state["step"]) for k, v in flatten("eval", ev).items()]
            for i in range(0, len(batch), 1000):
                client.log_batch(rid, metrics=batch[i : i + 1000])
            client.log_artifact(rid, str(run_dir / "eval.json"))
            if (run_dir / "calibration.json").exists():
                client.log_artifact(rid, str(run_dir / "calibration.json"))
            state["eval_logged"] = True
        state_path.write_text(json.dumps(state))
        finished = state["eval_logged"] or (
            (run_dir / "metrics.jsonl").exists() and (run_dir / "model.safetensors").exists()
        )
        if not follow or finished:
            break
        time.sleep(poll)
    client.set_terminated(rid, "FINISHED" if finished else "RUNNING")
    print(f"{name}: run {rid}, step {state['step']}, eval {'yes' if state['eval_logged'] else 'no'}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="run directory name under pretrain/work/runs")
    ap.add_argument("--all", action="store_true", help="sync every run directory that has training logs")
    ap.add_argument("--follow", action="store_true", help="keep mirroring until the run finishes")
    ap.add_argument("--poll", type=float, default=30.0)
    a = ap.parse_args()
    mlflow.set_tracking_uri(URI)
    os.environ["MLFLOW_TRACKING_URI"] = URI
    names = (
        sorted(p.name for p in RUNS.iterdir() if (p / "metrics.jsonl").exists() or (p / "sft.jsonl").exists())
        if a.all
        else [a.name]
    )
    for name in names:
        sync(name, a.follow, a.poll)


if __name__ == "__main__":
    main()
