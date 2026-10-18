#!/usr/bin/env python3
"""Export latest labels, full audit history, and optional parquet joins.

Run: python -m pretrain.quality.export_labels [--items PATH] [--db PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "pretrain" / "work" / "quality"


def flatten(item):
    row = {k: v for k, v in item.items() if k != "features"}

    def flatten_values(prefix, values):
        for key, value in values.items():
            name = f"{prefix}.{key}"
            if isinstance(value, dict):
                flatten_values(name, value)
            else:
                row[name] = value

    for group, values in (item.get("features") or {}).items():
        if isinstance(values, dict):
            flatten_values(group, values)
    return row


def export(items_path: Path, db_path: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    items = {}
    with items_path.open(encoding="utf-8") as f:
        for line in f.read().split("\n"):
            if line.strip():
                item = json.loads(line)
                items[item["id"]] = item
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        audit = [dict(r) for r in db.execute("SELECT * FROM labels ORDER BY id")]
        latest = [
            dict(r)
            for r in db.execute(
                "SELECT l.* FROM labels l JOIN (SELECT item_id,labeller,MAX(id) id FROM labels GROUP BY item_id,labeller) x ON l.id=x.id ORDER BY l.id"
            )
        ]
    with (out / "labels_audit.jsonl").open("w", encoding="utf-8") as f:
        for row in audit:
            row["flags"] = json.loads(row["flags"] or "[]")
            row["item"] = items.get(row["item_id"])
            row["features"] = flatten(row["item"] or {})
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "labels.jsonl").open("w", encoding="utf-8") as f:
        for row in latest:
            row["flags"] = json.loads(row["flags"] or "[]")
            item = items.get(row["item_id"], {})
            row["item"] = item
            row.update({f"feature.{k}": v for k, v in flatten(item).items() if k not in item})
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    dataset, features = WORK / "dataset.parquet", WORK / "features.parquet"
    if dataset.exists():
        table = pq.read_table(dataset)
        if features.exists():
            feature_table = pq.read_table(features)
            key = "id" if "id" in table.column_names else "item_id"
            feature_key = key if key in feature_table.column_names else "item_id"
            table = table.join(feature_table, keys=key, right_keys=feature_key, join_type="left outer")
        pq.write_table(table, out / "dataset.parquet")
    return len(latest), len(audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=WORK / "items.jsonl")
    parser.add_argument("--db", type=Path, default=WORK / "labels.sqlite")
    parser.add_argument("--out", type=Path, default=WORK / "export")
    args = parser.parse_args()
    latest, audit = export(args.items, args.db, args.out)
    print(f"Exported {latest} latest labels and {audit} audit rows to {args.out}")


if __name__ == "__main__":
    main()
