#!/usr/bin/env python3
"""Merge StyloMetrix, scratch-model LM NLL, and optional textstats into quality artifacts.
Run: uv run python pretrain/quality/enrich.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(REPO))
WORK = ROOT / "work" / "quality"
RUN = ROOT / "work" / "runs" / "s126m-1b"
TOKENIZER_NAME = "speakleash/Bielik-1.5B-v3.0-Instruct"


def read_jsonl(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream.read().split("\n") if line.strip()]


def lm_features(items: list[dict], batch_size: int) -> dict[str, dict]:
    from importlib import import_module

    import mlx.core as mx
    from mlx import nn
    from transformers import AutoTokenizer

    load_model = import_module("pretrain.sft").load_model

    model, _, _, _ = load_model(RUN)
    model.set_dtype(mx.float32)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME, use_fast=True)
    sequences = []
    for item in items:
        encoded = tokenizer.encode(item["text"], add_special_tokens=False)
        ids = ([1, *encoded, 2])[:1024]
        if len(ids) > 1:
            sequences.append((item["id"], ids))
    # Equal-length batches avoid padding and make fp32 results independent of batch composition.
    by_length = defaultdict(list)
    for row in sequences:
        by_length[len(row[1])].append(row)
    result = {}
    processed = 0
    for _, rows in sorted(by_length.items()):
        for start in range(0, len(rows), batch_size):
            group = rows[start : start + batch_size]
            token_ids = mx.array([ids for _, ids in group], dtype=mx.int32)
            logits, _, _ = model(token_ids)
            log_probs = nn.log_softmax(logits[:, :-1, :].astype(mx.float32), axis=-1)
            targets = token_ids[:, 1:]
            rows_nll = -mx.take_along_axis(log_probs, targets[:, :, None], axis=-1)[:, :, 0]
            mx.eval(rows_nll)
            values = np.asarray(rows_nll, dtype=np.float32)
            for (item_id, _), nll in zip(group, values, strict=False):
                result[item_id] = {
                    "nll_mean": float(np.mean(nll, dtype=np.float64)),
                    "nll_p50": float(np.percentile(nll, 50)),
                    "nll_p90": float(np.percentile(nll, 90)),
                    "nll_std": float(np.std(nll, dtype=np.float64)),
                    "tokens": len(nll),
                }
                processed += 1
            if processed % 100 < len(group) or processed == len(sequences):
                print(f"LM: {processed}/{len(sequences)} documents", flush=True)
    return result


def write_atomic(path: Path, contents: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(contents, encoding="utf-8")
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--skip-lm", action="store_true", help="reuse existing LM features and do not load the model")
    args = parser.parse_args()
    started = time.monotonic()
    items_path = WORK / "items.jsonl"
    if not items_path.exists():
        parser.error(f"missing sampled items: {items_path}")
    items = read_jsonl(items_path)
    if not items:
        parser.error("items.jsonl is empty")
    from pretrain.quality.sample import capped_text

    for item in items:
        if len(item["text"]) > 5_000:
            item["text"], _, _ = capped_text(item["text"])
    stylometrix = {row["id"]: row.get("metrics", {}) for row in read_jsonl(WORK / "stylometrix.jsonl")}
    for item in items:
        metrics = stylometrix.get(item["id"])
        if metrics:
            item.setdefault("features", {})["stylometrix"] = metrics

    missing: list[str] = []
    textstats: Any | None
    try:
        from pretrain.quality import textstats
    except ModuleNotFoundError as exc:
        if exc.name not in {"pretrain.quality.textstats", "textstats"}:
            raise
        textstats = None
    if textstats is None:
        missing = ["loop", "multilingual", "highlights"]
        print(
            "textstats.py is not present; skipping loop, multilingual, and highlights groups (rerun enrich.py after it lands).",
            flush=True,
        )
    else:
        for i, item in enumerate(items, 1):
            groups = item.setdefault("features", {})
            groups["loop"] = textstats.loop_metrics(item["text"])
            groups["multilingual"] = textstats.multilingual_metrics(item["text"])
            item["highlights"] = textstats.highlight_spans(item["text"])
            if i % 100 == 0:
                print(f"textstats: {i}/{len(items)}", flush=True)

    lm = {item["id"]: item.get("features", {}).get("lm") for item in items if item.get("features", {}).get("lm")}
    if not args.skip_lm:
        lm.update(lm_features([item for item in items if item["id"] not in lm], args.batch_size))
    for item in items:
        if item["id"] in lm:
            item.setdefault("features", {})["lm"] = lm[item["id"]]

    write_atomic(items_path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items))
    import pyarrow as pa
    import pyarrow.parquet as pq

    records = []
    for item in items:
        row = {
            "id": item["id"],
            "origin": item["origin"],
            "source": item["source"],
            "strata": json.dumps(item.get("strata", {}), ensure_ascii=False),
            "pipeline": json.dumps(item.get("pipeline", {}), ensure_ascii=False),
        }
        for group, values in item.get("features", {}).items():
            if isinstance(values, dict):
                for name, value in values.items():
                    row[f"{group}.{name}"] = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        records.append(row)
    table = pa.Table.from_pylist(records)
    parquet = WORK / "features.parquet"
    tmp = parquet.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, parquet)
    print(
        json.dumps(
            {
                "items": len(items),
                "stylo": sum(bool(x.get("features", {}).get("stylometrix")) for x in items),
                "lm": sum(bool(x.get("features", {}).get("lm")) for x in items),
                "textstats_missing": missing,
                "parquet_rows": table.num_rows,
                "elapsed_seconds": round(time.monotonic() - started, 2),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
