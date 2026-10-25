"""Local web app for confirming, fixing or rejecting proposed gold labels on decision items.

Run: python -m warda.label.app --items PATH --db PATH --labeller NAME [--port 8766] [--order seed|file] [--limit N]

Reads any decision-item JSONL: `pii_gen` items (`state`, `question`, `options`, `gold`, `category`, `action`) or
handwritten rows (`payload`, `task`, `channel`, `destination`, `policy_id`, `gold_category`, `gold_action`).
Labels go to an append-only SQLite table; the latest row per (item, labeller) wins.
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
from warda.schema import ACTIONS, CATEGORIES

APP_VERSION = "1"
SEED = 211
STATIC = Path(__file__).parent / "static"
# Fixed paths: the URL only selects an entry, so request data never becomes part of a filesystem path.
STATIC_FILES = {"app.js": (STATIC / "app.js", "text/javascript"), "style.css": (STATIC / "style.css", "text/css")}
VERDICTS = ("confirm", "fix", "reject", "unsure")
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
 id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, labeller TEXT NOT NULL,
 verdict TEXT NOT NULL CHECK(verdict IN ('confirm','fix','reject','unsure')),
 category TEXT, action TEXT, reason TEXT NOT NULL DEFAULT '',
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


def proposed(item: dict[str, Any]) -> dict[str, str | None]:
    """The gold under review: adjudicated `gold_*` fields first, then the generator's `category`/`action`."""
    category = item.get("gold_category") or item.get("category")
    action = item.get("gold_action") or item.get("action")
    return {
        "category": category if category in CATEGORIES else None,
        "action": action if action in ACTIONS else None,
    }


def view(item: dict[str, Any]) -> dict[str, Any]:
    """Split an item into the policy block and the rest of what the decider sees."""
    if item.get("state"):
        # pii_gen renders the policy first and separates it from the call context with one blank line.
        policy, _, body = str(item["state"]).partition("\n\n")
        if not body:
            policy, body = "", policy
    else:
        policy = f"Policy: {item.get('policy_id') or item.get('policy') or '(none)'}"
        lines = [f"{key.capitalize()}: {item[key]}" for key in ("channel", "destination", "task") if item.get(key)]
        body = "\n".join([*lines, "Content:", '"""', str(item.get("payload", "")), '"""'])
    options = item.get("options")
    return {
        "id": str(item["id"]),
        "policy": policy,
        "body": body,
        "question": item.get("question"),
        "options": options if isinstance(options, list) else [],
        "gold": item.get("gold") if isinstance(item.get("gold"), int) else None,
        "proposed": proposed(item),
        "meta": {key: item[key] for key in ("language", "split", "question_id", "template_id", "tier") if key in item},
    }


def create_app(
    items_path: Path, db_path: Path, labeller: str, order: str = "seed", limit: int | None = None
) -> Starlette:
    items = read_items(Path(items_path))
    ordered = item_order(items, order)[:limit]
    all_items = {str(item["id"]): item for item in items}
    by_id = {item_id: all_items[item_id] for item_id in ordered}
    positions = {item_id: i for i, item_id in enumerate(ordered)}
    db = connect(Path(db_path))

    def latest_rows() -> list[dict[str, Any]]:
        return [dict(row) for row in db.execute(LATEST_SQL) if row["item_id"] in by_id]

    def who(request: Request) -> str:
        return request.query_params.get("labeller") or labeller

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
        done = {row["item_id"] for row in mine}
        return JSONResponse(
            {
                "labeller": name,
                "total": len(ordered),
                "done": len(done),
                "last": mine[-1]["item_id"] if mine else None,
                "items": [{"id": item_id, "done": item_id in done} for item_id in ordered],
                "categories": list(CATEGORIES),
                "actions": list(ACTIONS),
            }
        )

    async def api_item(request: Request) -> Response:
        item_id = request.path_params["item_id"]
        if item_id not in by_id:
            return JSONResponse({"error": "unknown item"}, status_code=404)
        name = who(request)
        mine = [row for row in latest_rows() if row["item_id"] == item_id and row["labeller"] == name]
        return JSONResponse(
            {**view(by_id[item_id]), "position": positions[item_id], "label": mine[0] if mine else None}
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
            if item_id not in by_id:
                raise ValueError(f"unknown item {item_id!r}")
            if verdict not in VERDICTS:
                raise ValueError(f"verdict must be one of: {', '.join(VERDICTS)}")
            if not isinstance(name, str) or not isinstance(reason, str):
                raise ValueError("labeller and reason must be strings")
            if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 0:
                raise ValueError("seconds must be a non-negative integer")
            category: str | None = None
            action: str | None = None
            if verdict == "fix":
                category, action = payload.get("category"), payload.get("action")
                if category not in CATEGORIES:
                    raise ValueError(f"fix needs a category from: {', '.join(CATEGORIES)}")
                if action not in ACTIONS:
                    raise ValueError(f"fix needs an action from: {', '.join(ACTIONS)}")
            elif verdict == "confirm":
                gold = proposed(by_id[item_id])
                category, action = gold["category"], gold["action"]
                if category is None or action is None:
                    raise ValueError("this item has no proposed category and action to confirm; use fix")
        except (ValueError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        with db:
            cur = db.execute(
                "INSERT INTO labels(item_id,labeller,verdict,category,action,reason,seconds,created_at,app_version) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    name,
                    verdict,
                    category,
                    action,
                    reason,
                    seconds,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    APP_VERSION,
                ),
            )
        return JSONResponse({"id": cur.lastrowid, "item_id": item_id, "category": category, "action": action})

    async def api_stats(request: Request) -> Response:
        rows = latest_rows()
        verdicts: dict[str, Counter[str]] = {}
        for row in rows:
            verdicts.setdefault(row["labeller"], Counter())[row["verdict"]] += 1
        return JSONResponse({"total": len(ordered), "verdicts": verdicts, **report(rows)})

    async def api_export(request: Request) -> Response:
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
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--order", choices=("seed", "file"), default="seed")
    parser.add_argument("--limit", type=int, help="label only the first N items in the chosen order")
    args = parser.parse_args()
    import uvicorn  # only the server needs it; tests and export do not

    uvicorn.run(
        create_app(args.items, args.db, args.labeller, args.order, args.limit), host="127.0.0.1", port=args.port
    )


if __name__ == "__main__":
    main()
