#!/usr/bin/env python3
"""Compute isolated GPL StyloMetrix features from items.jsonl.
Run in .venv-stylometrix: python pretrain/quality/stylometrix_worker.py [--workers 6].
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "quality"
_MODEL: Any | None = None


def initialize():
    global _MODEL
    from stylo_metrix import StyloMetrix

    _MODEL = StyloMetrix("pl")


def compute(batch):
    ids, texts = zip(*batch, strict=False)
    if _MODEL is None:
        raise RuntimeError("StyloMetrix worker was not initialized")
    result = _MODEL.transform(list(texts))
    if hasattr(result, "to_dict"):
        result = result.to_dict(orient="records")
    elif hasattr(result, "to_dicts"):
        result = result.to_dicts()
    elif isinstance(result, dict):
        if result and all(isinstance(v, (list, tuple)) for v in result.values()):
            result = [dict(zip(result, values, strict=False)) for values in zip(*result.values(), strict=False)]
        else:
            result = [result]
    rows = []
    for item_id, metrics in zip(ids, result, strict=False):
        clean = {}
        for key, raw_value in metrics.items():
            try:
                metric_value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(metric_value):
                clean[str(key)] = metric_value
        rows.append({"id": item_id, "metrics": clean})
    return rows


def batches(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--items", type=Path, default=WORK / "items.jsonl")
    parser.add_argument("--output", type=Path, default=WORK / "stylometrix.jsonl")
    args = parser.parse_args()
    if args.workers < 1 or args.batch_size < 1:
        parser.error("workers and batch-size must be positive")
    if not args.items.is_file():
        parser.error(f"items file not found: {args.items}")
    done = set()
    if args.output.exists():
        existing = args.output.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing = existing.rsplit("\n", 1)[0] + "\n" if "\n" in existing else ""
            args.output.write_text(existing, encoding="utf-8")
        for line in existing.split("\n"):
            if line.strip():
                done.add(json.loads(line)["id"])
    rows = []
    with args.items.open(encoding="utf-8") as stream:
        for line in stream.read().split("\n"):
            if not line.strip():
                continue
            item = json.loads(line)
            if item["id"] not in done:
                rows.append((item["id"], item["text"]))
    print(f"StyloMetrix: {len(done)} already complete; {len(rows)} remaining; {args.workers} workers", flush=True)
    if not rows:
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    started = time.monotonic()
    processed = 0
    with args.output.open("a", encoding="utf-8") as output, ctx.Pool(args.workers, initializer=initialize) as pool:
        for index, result in enumerate(pool.imap_unordered(compute, batches(rows, args.batch_size)), 1):
            for row in result:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                done.add(row["id"])
                processed += 1
            output.flush()
            if index % 10 == 0 or processed == len(rows):
                print(
                    f"StyloMetrix: {processed} / {len(rows)} complete ({processed / max(time.monotonic() - started, 1e-6):.2f} docs/s wall)",
                    flush=True,
                )


if __name__ == "__main__":
    main()
