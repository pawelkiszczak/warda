"""Local web app for labelling decision items: review a proposed gold, or label blind.

Run: python -m warda.label.app --items PATH --db PATH --labeller NAME [--blind] [--policies DIR] [--ids FILE]
     [--port 8766] [--order seed|file] [--limit N]

Reads `pii_gen` items, Brama rows and handwritten rows (see `warda/label/items.py`). Review mode shows the proposed
gold and asks to confirm, fix, reject or mark unsure; blind mode (Brama R-08) hides the gold and every field that
hints at it, and the labeller decides from the decider's view. Labels go to an append-only SQLite table; the latest
row per (item, labeller) wins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from warda.label.agreement import report
from warda.label.items import (
    allowed_clauses,
    labelled_text,
    load_ids,
    load_policies,
    proposed,
    resolve,
    unresolve,
    view,
)
from warda.schema import ACTIONS, CATEGORIES

APP_VERSION = "1"
SEED = 211
STATIC = Path(__file__).parent / "static"
# Fixed paths: the URL only selects an entry, so request data never becomes part of a filesystem path.
STATIC_FILES = {"app.js": (STATIC / "app.js", "text/javascript"), "style.css": (STATIC / "style.css", "text/css")}
REVIEW_VERDICTS = ("confirm", "fix", "reject", "unsure")
BLIND_VERDICTS = ("label", "reject", "unsure")
MAX_SPANS, MAX_SPAN_CHARS = 50, 500
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
 id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, labeller TEXT NOT NULL,
 verdict TEXT NOT NULL CHECK(verdict IN ('confirm','fix','label','reject','unsure')),
 category TEXT, action TEXT, clause TEXT, protected TEXT NOT NULL DEFAULT '[]', reason TEXT NOT NULL DEFAULT '',
 seconds INTEGER NOT NULL, created_at TEXT NOT NULL, app_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS labels_latest ON labels(item_id, labeller, id);
"""
LATEST_SQL = (
    "SELECT l.* FROM labels l JOIN (SELECT item_id,labeller,MAX(id) id FROM labels GROUP BY item_id,labeller) x "
    "ON l.id=x.id ORDER BY l.id"
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(DB_SCHEMA)
    return db


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    out["protected"] = json.loads(out["protected"] or "[]")
    return out


def read_items(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    duplicates = [item_id for item_id, n in Counter(str(i["id"]) for i in items).items() if n > 1]
    if duplicates:
        raise SystemExit(f"{path}: duplicate item ids: {', '.join(duplicates[:5])}")
    return items


def item_order(items: list[dict[str, Any]], order: str) -> list[str]:
    """`file` keeps the file order; `seed` is a fixed hash order, the same for every labeller and laptop."""
    ids = [str(item["id"]) for item in items]
    if order == "file":
        return ids
    return sorted(ids, key=lambda item_id: hashlib.sha256(f"{SEED}:{item_id}".encode()).hexdigest())


def create_app(
    items_path: Path,
    db_path: Path,
    labeller: str,
    order: str = "seed",
    limit: int | None = None,
    *,
    blind: bool = False,
    policies_dir: Path | None = None,
    ids_path: Path | None = None,
) -> Starlette:
    """Policies default to a `policies/` directory next to the items, ids to `<items stem>.ids.json` (Brama layout)."""
    items_path = Path(items_path)
    items = read_items(items_path)
    policies = load_policies(policies_dir or items_path.parent / "policies")
    ids = load_ids(ids_path or items_path.with_suffix(".ids.json"))
    ordered = item_order(items, order)[:limit]
    all_items = {str(item["id"]): item for item in items}
    by_id = {item_id: all_items[item_id] for item_id in ordered}
    positions = {item_id: i for i, item_id in enumerate(ordered)}
    verdicts = BLIND_VERDICTS if blind else REVIEW_VERDICTS
    db = connect(Path(db_path))

    def latest_rows() -> list[dict[str, Any]]:
        return [row_dict(row) for row in db.execute(LATEST_SQL) if row["item_id"] in by_id]

    def who(request: Request) -> str:
        return request.query_params.get("labeller") or labeller

    def spans(item: dict[str, Any], value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > MAX_SPANS:
            raise ValueError(f"protected must be a list of at most {MAX_SPANS} strings")
        text = labelled_text(item, ids)
        out = []
        for span in value:
            if not isinstance(span, str) or not span.strip() or len(span) > MAX_SPAN_CHARS:
                raise ValueError(f"each protected span must be a non-empty string of at most {MAX_SPAN_CHARS} chars")
            if span not in text:
                raise ValueError(f"protected span {span[:40]!r} does not occur in the payload")
            out.append(unresolve(span, ids))
        return sorted(set(out), key=out.index)

    async def index(request: Request) -> Response:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    async def static_file(request: Request) -> Response:
        entry = STATIC_FILES.get(request.path_params["name"])
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(entry[0], media_type=entry[1])

    async def api_items(request: Request) -> Response:
        name = who(request)
        mine = [row for row in latest_rows() if row["labeller"] == name]
        done = {row["item_id"]: row["verdict"] for row in mine}
        return JSONResponse(
            {
                "labeller": name,
                "blind": blind,
                "total": len(ordered),
                "done": len(done),
                "last": mine[-1]["item_id"] if mine else None,
                "items": [{"id": item_id, "verdict": done.get(item_id)} for item_id in ordered],
                "categories": list(CATEGORIES),
                "actions": list(ACTIONS),
                "verdicts": list(verdicts),
            }
        )

    async def api_item(request: Request) -> Response:
        item_id = request.path_params["item_id"]
        if item_id not in by_id:
            return JSONResponse({"error": "unknown item"}, status_code=404)
        name = who(request)
        mine = [row for row in latest_rows() if row["item_id"] == item_id and row["labeller"] == name]
        label = mine[0] if mine else None
        if label:
            # stored spans keep placeholders; the UI marks them in the resolved payload and sends them back resolved
            label["protected"] = [resolve(span, ids) for span in label["protected"]]
        return JSONResponse(
            {
                **view(by_id[item_id], policies, ids, all_items, blind),
                "position": positions[item_id],
                "label": label,
            }
        )

    async def save_label(request: Request) -> Response:
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("expected a JSON object")
            item_id = payload.get("item_id")
            verdict = payload.get("verdict")
            name = payload.get("labeller") or labeller
            reason = payload.get("reason", "")
            seconds = payload.get("seconds", 0)
            if not isinstance(item_id, str) or item_id not in by_id:
                raise ValueError(f"unknown item {item_id!r}")
            if verdict not in verdicts:
                raise ValueError(f"verdict must be one of: {', '.join(verdicts)}")
            if not isinstance(name, str) or not isinstance(reason, str):
                raise ValueError("labeller and reason must be strings")
            if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 0:
                raise ValueError("seconds must be a non-negative integer")
            item = by_id[item_id]
            category: str | None = None
            action: str | None = None
            clause: str | None = None
            protected: list[str] = []
            if verdict in ("fix", "label"):
                category, action = payload.get("category"), payload.get("action")
                if category not in CATEGORIES:
                    raise ValueError(f"{verdict} needs a category from: {', '.join(CATEGORIES)}")
                if action not in ACTIONS:
                    raise ValueError(f"{verdict} needs an action from: {', '.join(ACTIONS)}")
                clause = payload.get("clause")
                if clause is not None and clause not in allowed_clauses(item, policies):
                    raise ValueError(f"clause {clause!r} is not declared by this item's policy")
                protected = spans(item, payload.get("protected"))
            elif verdict == "confirm":
                gold = proposed(item, {})  # unresolved: stored spans keep their placeholders
                category, action, clause, protected = (
                    gold["category"],
                    gold["action"],
                    gold["clause"],
                    gold["protected"],
                )
                if category is None or action is None:
                    raise ValueError("this item has no proposed category and action to confirm; use fix")
        except (ValueError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        with db:
            cur = db.execute(
                "INSERT INTO labels(item_id,labeller,verdict,category,action,clause,protected,reason,seconds,"
                "created_at,app_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    name,
                    verdict,
                    category,
                    action,
                    clause,
                    json.dumps(protected, ensure_ascii=False),
                    reason,
                    seconds,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    APP_VERSION,
                ),
            )
            row = db.execute("SELECT * FROM labels WHERE id=?", (cur.lastrowid,)).fetchone()
        return JSONResponse(row_dict(row))

    def hidden_when_blind() -> Response | None:
        if blind:
            # R-08: labellers stay blind to each other; merge databases with warda.label.export instead.
            return JSONResponse({"error": "hidden while labelling blind; use warda.label.export"}, status_code=403)
        return None

    async def api_stats(request: Request) -> Response:
        if (hidden := hidden_when_blind()) is not None:
            return hidden
        rows = latest_rows()
        counts: dict[str, Counter[str]] = {}
        for row in rows:
            counts.setdefault(row["labeller"], Counter())[row["verdict"]] += 1
        return JSONResponse({"total": len(ordered), "verdicts": counts, **report(rows)})

    async def api_export(request: Request) -> Response:
        if (hidden := hidden_when_blind()) is not None:
            return hidden
        rows = latest_rows()
        return StreamingResponse(
            (json.dumps(row, ensure_ascii=False) + "\n" for row in rows), media_type="application/x-ndjson"
        )

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/static/{name}", static_file),
            Route("/api/items", api_items),
            Route("/api/item/{item_id:path}", api_item),
            Route("/api/label", save_label, methods=["POST"]),
            Route("/api/stats", api_stats),
            Route("/api/export", api_export),
        ]
    )
    app.state.order = ordered
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, required=True, help="decision-item JSONL")
    parser.add_argument("--db", type=Path, required=True, help="SQLite file for this labeller's labels")
    parser.add_argument("--labeller", required=True)
    parser.add_argument("--blind", action="store_true", help="hide the proposed gold (Brama R-08 independent labels)")
    parser.add_argument("--policies", type=Path, help="policy Markdown directory (default: policies/ next to items)")
    parser.add_argument("--ids", type=Path, help="identifier sidecar (default: <items stem>.ids.json)")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--order", choices=("seed", "file"), default="seed")
    parser.add_argument("--limit", type=int, help="label only the first N items in the chosen order")
    args = parser.parse_args()
    import uvicorn  # only the server needs it; tests and export do not

    app = create_app(
        args.items,
        args.db,
        args.labeller,
        args.order,
        args.limit,
        blind=args.blind,
        policies_dir=args.policies,
        ids_path=args.ids,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
