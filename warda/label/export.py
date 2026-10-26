"""Merge one or more labelling databases into latest labels, the full audit trail and an agreement report.

Run: python -m warda.label.export --db a.sqlite [--db b.sqlite ...] --out DIR [--items PATH]

Writes `labels.jsonl` (latest label per item and labeller), `labels_audit.jsonl` (every row, tagged with its
source `db`) and `agreement.json` (pairwise kappa on category and action, alpha, n, disagreements). With `--items`,
`agreement.json` also reports kappa per `track` and per `language` (Brama R-10 / V-08: kappa >= 0.7 per track).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from warda.label.agreement import report
from warda.label.app import LATEST_SQL, read_items

GROUP_FIELDS = ("track", "language")


def _rows(db: sqlite3.Connection, sql: str, path: Path) -> list[dict[str, Any]]:
    rows = [dict(row) for row in db.execute(sql)]
    for row in rows:
        row["protected"] = json.loads(row.get("protected") or "[]")
        row["db"] = str(path)
    return rows


def load(db_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Audit rows, latest rows and conflicts.

    Latest is decided inside each database by row id, as the app does, never by wall-clock time. If the same
    (item, labeller) appears in several databases, the database given later on the command line wins and the
    clash is reported as a conflict.
    """
    audit: list[dict[str, Any]] = []
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts = []
    for path in db_paths:
        if not path.is_file():
            raise SystemExit(f"no labelling database at {path}")
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            audit += _rows(db, "SELECT * FROM labels ORDER BY id", path)
            for row in _rows(db, LATEST_SQL, path):
                key = (row["item_id"], row["labeller"])
                if key in latest:
                    conflicts.append({"item_id": key[0], "labeller": key[1], "dbs": [latest[key]["db"], row["db"]]})
                latest[key] = row
    return audit, list(latest.values()), conflicts


def export(db_paths: list[Path], out: Path, items_path: Path | None = None) -> dict[str, Any]:
    audit, latest, conflicts = load(db_paths)
    agreement = report(latest)
    agreement["conflicts"] = conflicts
    if items_path is not None:
        items = {str(item["id"]): item for item in read_items(items_path)}
        for field in GROUP_FIELDS:
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in latest:
                value = items.get(row["item_id"], {}).get(field)
                if value is not None:
                    groups.setdefault(str(value), []).append(row)
            agreement[f"by_{field}"] = {value: report(rows)["kappa"] for value, rows in sorted(groups.items())}
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
    parser.add_argument("--items", type=Path, help="the labelled JSONL, for kappa per track and language")
    args = parser.parse_args()
    agreement = export(args.db, args.out, args.items)
    print(
        f"{agreement['n']} items, labellers {agreement['labellers']}, {len(agreement['disagreements'])} disagreements,"
        f" {len(agreement['conflicts'])} conflicts; wrote {args.out}/labels.jsonl, labels_audit.jsonl, agreement.json",
        flush=True,
    )
    for pair, values in agreement["kappa"].items():
        print(f"{pair}: kappa category {values['kappa_category']}, action {values['kappa_action']}", flush=True)
    print(f"alpha: {agreement['alpha']}", flush=True)


if __name__ == "__main__":
    main()
