"""Merge one or more labelling databases into latest labels, the full audit trail and an agreement report.

Run: python -m warda.label.export --db a.sqlite [--db b.sqlite ...] --out DIR

Writes `labels.jsonl` (latest label per item and labeller), `labels_audit.jsonl` (every row, tagged with its
source `db`) and `agreement.json` (pairwise kappa on category and action, alpha, n, disagreements).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from warda.label.agreement import report


def load(db_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """All rows from every database, and the latest per (item, labeller) across them (by `created_at`, then row)."""
    audit: list[dict[str, Any]] = []
    for path in db_paths:
        if not path.is_file():
            raise SystemExit(f"no labelling database at {path}")
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            audit += [{**dict(row), "db": str(path)} for row in db.execute("SELECT * FROM labels ORDER BY id")]
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in audit:
        key = (row["item_id"], row["labeller"])
        if key not in latest or row["created_at"] >= latest[key]["created_at"]:
            latest[key] = row
    return audit, list(latest.values())


def export(db_paths: list[Path], out: Path) -> dict[str, Any]:
    audit, latest = load(db_paths)
    agreement = report(latest)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("labels.jsonl", latest), ("labels_audit.jsonl", audit)):
        with (out / name).open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (out / "agreement.json").write_text(json.dumps(agreement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return agreement


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, action="append", required=True, help="labelling SQLite file; repeatable")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    agreement = export(args.db, args.out)
    print(
        f"{agreement['n']} items, labellers {agreement['labellers']}, {len(agreement['disagreements'])} disagreements;"
        f" wrote {args.out}/labels.jsonl, labels_audit.jsonl, agreement.json",
        flush=True,
    )
    for pair, values in agreement["kappa"].items():
        print(f"{pair}: kappa category {values['kappa_category']}, action {values['kappa_action']}", flush=True)
    print(f"alpha: {agreement['alpha']}", flush=True)


if __name__ == "__main__":
    main()
