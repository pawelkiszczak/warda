#!/usr/bin/env python3
"""Offline local quality-labeling web app.

Run: python -m pretrain.quality.app --items pretrain/work/quality/items.jsonl --labeller NAME
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, cast
from urllib.parse import unquote

import numpy as np
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WORK = ROOT / "pretrain" / "work" / "quality"
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
 id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, labeller TEXT NOT NULL,
 quality TEXT NOT NULL CHECK(quality IN ('HIGH','MEDIUM','LOW','SKIP')),
 flags TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '',
 confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 3),
 seconds REAL NOT NULL, created_at TEXT NOT NULL, app_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS labels_latest ON labels(item_id, labeller, id);
CREATE TABLE IF NOT EXISTS item_order (position INTEGER PRIMARY KEY, item_id TEXT UNIQUE NOT NULL);
"""
QUALITY = {"HIGH", "MEDIUM", "LOW", "SKIP"}
FLAG_VOCAB = [
    "looped",
    "multilingual",
    "wrong_language",
    "boilerplate",
    "spam_ads",
    "machine_generated",
    "garbled_ocr",
    "truncated_fragment",
    "personal_data",
    "offensive",
    "code_or_markup",
    "list_or_table",
]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(DB_SCHEMA)
    return db


def read_items(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f.read().split("\n") if line.strip()]


def stratified_order(items: list[dict[str, Any]], seed: int = 211) -> list[str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for item in items:
        groups[str(item.get("origin", "unknown"))].append(str(item["id"]))
    rng = random.Random(seed)
    for rows in groups.values():
        rng.shuffle(rows)
    order = []
    while groups:
        for origin in list(groups):
            order.append(groups[origin].pop())
            if not groups[origin]:
                del groups[origin]
    return order


def numeric_features(item: dict[str, Any]) -> dict[str, float]:
    out = {}
    for group, values in (item.get("features") or {}).items():
        if isinstance(values, dict):
            for name, value in values.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    out[f"{group}.{name}"] = float(value)
                elif isinstance(value, dict):
                    for child, number in value.items():
                        if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number):
                            out[f"{group}.{name}.{child}"] = float(number)
    return out


def create_app(items_path: str | Path, db_path: str | Path, labeller: str = "local") -> Starlette:
    items_path, db_path = Path(items_path), Path(db_path)
    items = read_items(items_path)
    by_id = {str(i["id"]): i for i in items}
    db = connect(db_path)
    existing = {r[0] for r in db.execute("SELECT item_id FROM item_order")}
    if len(existing) != len(items) or existing != set(by_id):
        db.execute("DELETE FROM item_order")
        db.executemany("INSERT INTO item_order(position,item_id) VALUES(?,?)", enumerate(stratified_order(items)))
        db.commit()
    ordered = [r[0] for r in db.execute("SELECT item_id FROM item_order ORDER BY position")]
    positions = {item_id: i for i, item_id in enumerate(ordered)}
    # Percentiles are computed over the fixed sample, not only labeled documents.
    metric_values: dict[str, list[float]] = defaultdict(list)
    for item in items:
        for name, value in numeric_features(item).items():
            metric_values[name].append(value)
    percentile_values = {name: sorted(values) for name, values in metric_values.items()}
    try:
        from importlib import import_module

        METRIC_DOCS = import_module("pretrain.quality.textstats").METRIC_DOCS
    except ImportError:
        METRIC_DOCS = {}

    def item_data(item_id: str) -> dict[str, Any] | None:
        item = by_id.get(item_id)
        if item is None:
            return None
        out = dict(item)
        out["metric_percentiles"] = {}
        for name, value in numeric_features(item).items():
            vals = percentile_values[name]
            less = sum(v < value for v in vals)
            equal = sum(v == value for v in vals)
            pct = 100 * (less + equal / 2) / len(vals)
            median = vals[len(vals) // 2]
            out["metric_percentiles"][name] = {
                "percentile": pct,
                "extreme": value != median and (pct >= 95 or pct <= 5),
                "description": METRIC_DOCS.get(name.split(".", 1)[-1], ""),
            }
        return out

    def latest_rows(conn: sqlite3.Connection | None = None):
        conn = conn or db
        return conn.execute(
            "SELECT l.* FROM labels l JOIN (SELECT item_id,labeller,MAX(id) id FROM labels GROUP BY item_id,labeller) x ON l.id=x.id"
        ).fetchall()

    async def index(request: Request):
        return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))

    async def dashboard_page(request: Request):
        return HTMLResponse((Path(__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8"))

    async def check_page(request: Request):
        return HTMLResponse((Path(__file__).parent / "static" / "check.html").read_text(encoding="utf-8"))

    async def static_file(request: Request):
        name = request.path_params["name"]
        if name not in {"app.js", "style.css", "dashboard.js", "dashboard.css", "check.js"}:
            return JSONResponse({"error": "not found"}, status_code=404)
        path = Path(__file__).parent / "static" / name
        return HTMLResponse(
            path.read_text(encoding="utf-8"), media_type="text/javascript" if name.endswith(".js") else "text/css"
        )

    async def api_items(request: Request):
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
            limit = min(100, max(1, int(request.query_params.get("limit", 20))))
        except ValueError:
            return JSONResponse({"error": "offset and limit must be integers"}, status_code=400)
        labelled_ids = {r["item_id"] for r in latest_rows() if r["labeller"] == labeller}
        return JSONResponse(
            {
                "total": len(ordered),
                "items": [
                    {**cast(dict[str, Any], item_data(item_id)), "labelled": item_id in labelled_ids}
                    for item_id in ordered[offset : offset + limit]
                ],
            }
        )

    async def api_item(request: Request):
        item_id = unquote(request.path_params["item_id"])
        item = item_data(item_id)
        if item is None:
            return JSONResponse({"error": "unknown item"}, status_code=404)
        item["position"] = positions[item_id]
        item["total"] = len(ordered)
        item["latest_label"] = [dict(r) for r in latest_rows() if r["item_id"] == item_id and r["labeller"] == labeller]
        return JSONResponse(item)

    async def save_label(request: Request):
        try:
            payload = await request.json()
            item_id, quality = str(payload["item_id"]), payload["quality"]
            flags = payload.get("flags", [])
            confidence = int(payload.get("confidence", 2))
            seconds = float(payload.get("seconds", 0))
            if (
                item_id not in by_id
                or quality not in QUALITY
                or not isinstance(flags, list)
                or any(x not in FLAG_VOCAB for x in flags)
                or confidence not in (1, 2, 3)
                or not math.isfinite(seconds)
                or seconds < 0
            ):
                raise ValueError("invalid label fields")
            note = str(payload.get("note", ""))
            with db:
                cur = db.execute(
                    "INSERT INTO labels(item_id,labeller,quality,flags,note,confidence,seconds,created_at,app_version) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        item_id,
                        labeller,
                        quality,
                        json.dumps(sorted(set(flags))),
                        note,
                        confidence,
                        seconds,
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "1",
                    ),
                )
            return JSONResponse({"id": cur.lastrowid, "item_id": item_id, "quality": quality})
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    def stats_data(selected_metric: str | None = None):
        labels = latest_rows()
        totals = Counter(r["quality"] for r in labels)
        origins: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        flag_counts: Counter[str] = Counter()
        labelled_item_ids = {r["item_id"] for r in labels}
        for item_id in labelled_item_ids:
            item = by_id[item_id]
            origins[item.get("origin", "unknown")] += 1
            sources[item.get("source", "unknown")] += 1
        for row in labels:
            flag_counts.update(json.loads(row["flags"] or "[]"))
        sample_origins = Counter(i.get("origin", "unknown") for i in items)
        sample_sources = Counter(i.get("source", "unknown") for i in items)
        by_labeller = Counter(r["labeller"] for r in labels)
        times = [r["seconds"] for r in labels]
        pair_labels: dict[str, dict[str, str]] = defaultdict(dict)
        for row in labels:
            pair_labels[row["item_id"]][row["labeller"]] = row["quality"]
        kappas = {}
        labellers = sorted(by_labeller)
        for a_i, a in enumerate(labellers):
            for b in labellers[a_i + 1 :]:
                pairs = [(v[a], v[b]) for v in pair_labels.values() if a in v and b in v]
                if not pairs:
                    continue
                observed = sum(x == y for x, y in pairs) / len(pairs)
                categories = set(QUALITY)
                pa = {c: sum(x == c for x, _ in pairs) / len(pairs) for c in categories}
                pb = {c: sum(y == c for _, y in pairs) / len(pairs) for c in categories}
                expected = sum(pa[c] * pb[c] for c in categories)
                kappas[f"{a} vs {b}"] = {
                    "n": len(pairs),
                    "kappa": (observed - expected) / (1 - expected) if expected < 1 else 1.0,
                }
        confusion: Counter[str] = Counter()
        for row in labels:
            q = (by_id[row["item_id"]].get("source_meta") or {}).get("quality")
            if q:
                confusion[f"{q}|{row['quality']}"] += 1
        metric_rows = []
        numeric = defaultdict(list)
        for row in labels:
            if row["quality"] not in ("HIGH", "MEDIUM", "LOW"):
                continue
            for name, val in numeric_features(by_id[row["item_id"]]).items():
                numeric[name].append((val, row["quality"]))

        def auc(rows, positive):
            pos = sorted(v for v, q in rows if q == positive)
            neg = sorted(v for v, q in rows if q != positive)
            if not pos or not neg:
                return None
            # Mann–Whitney with average ranks handles ties.
            allv = sorted([(v, True) for v in pos] + [(v, False) for v in neg], key=lambda x: x[0])
            rank_sum = 0.0
            i = 0
            while i < len(allv):
                j = i + 1
                while j < len(allv) and allv[j][0] == allv[i][0]:
                    j += 1
                rank = (i + 1 + j) / 2
                rank_sum += rank * sum(flag for _, flag in allv[i:j])
                i = j
            return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

        for name, rows in numeric.items():
            means = {
                q: mean([v for v, label in rows if label == q])
                for q in ("HIGH", "MEDIUM", "LOW")
                if any(label == q for _, label in rows)
            }
            metric_rows.append(
                {
                    "name": name,
                    "n": len(rows),
                    "high_auroc": auc(rows, "HIGH"),
                    "low_auroc": auc(rows, "LOW"),
                    "means": means,
                    "values": [{"value": v, "label": q} for v, q in rows],
                }
            )
        metric_rows.sort(key=lambda r: max((r["high_auroc"] or 0, r["low_auroc"] or 0)), reverse=True)
        samples = {}
        for name, vals in metric_values.items():
            a = np.asarray(vals, dtype=float)
            samples[name] = {
                "mean": float(a.mean()),
                "p5": float(np.percentile(a, 5)),
                "p50": float(np.percentile(a, 50)),
                "p95": float(np.percentile(a, 95)),
            }
        metric_names = sorted(metric_values)
        selected = selected_metric if selected_metric in metric_values else (metric_names[0] if metric_names else None)
        histogram = next(
            ({"name": row["name"], "values": row["values"]} for row in metric_rows if row["name"] == selected), None
        )
        metric_summary = [{key: value for key, value in row.items() if key != "values"} for row in metric_rows[:25]]
        return {
            "total": len(items),
            "labelled": len(labelled_item_ids),
            "by_origin": dict(origins),
            "by_source": dict(sources),
            "total_by_origin": dict(sample_origins),
            "total_by_source": dict(sample_sources),
            "labels": dict(totals),
            "flags": dict(flag_counts),
            "mean_seconds": mean(times) if times else 0,
            "per_labeller": dict(by_labeller),
            "kappa": kappas,
            "speakleash_confusion": dict(confusion),
            "metrics": metric_summary,
            "metric_names": metric_names,
            "histogram_metric": histogram,
            "sample_metrics": samples,
        }

    async def api_stats(request: Request):
        return JSONResponse(stats_data(request.query_params.get("metric")))

    VIZ_METRICS = [
        "loop.loop_score",
        "multilingual.multilingual_score",
        "multilingual.pl_share",
        "lm.nll_mean",
        "loop.zlib_compression_ratio",
        "loop.duplicate_line_char_fraction",
        "multilingual.script_mix",
        "cheap.oov_ratio",
        "cheap.stopword_ratio",
        "cheap.words",
        "stylometrix.L_ERROR",
        "stylometrix.L_TTR_IA",
    ]

    async def api_viz(request: Request):
        """Compact per-item data for the dashboard charts: automated fields for every item (key metrics plus any
        `metric=` query parameters, repeatable) and every latest label row. Charts are drawn client-side."""
        extra = [m for m in request.query_params.getlist("metric") if m]
        names = VIZ_METRICS + [m for m in dict.fromkeys(extra) if m not in VIZ_METRICS]
        rows = []
        for item_id in ordered:
            item = by_id[item_id]
            nums = numeric_features(item)
            pipeline = item.get("pipeline") or {}
            rows.append(
                {
                    "id": item_id,
                    "pos": positions[item_id],
                    "origin": item.get("origin", "unknown"),
                    "source": item.get("source", "unknown"),
                    "sl_quality": (item.get("source_meta") or {}).get("quality"),
                    "clean_ok": pipeline.get("clean_ok"),
                    "clean_reason": pipeline.get("clean_reason"),
                    "top_lang": ((item.get("features") or {}).get("multilingual") or {}).get("top_lang", "unknown"),
                    "m": {name: nums.get(name) for name in names},
                }
            )
        labels = [
            {
                "item_id": r["item_id"],
                "labeller": r["labeller"],
                "quality": r["quality"],
                "flags": json.loads(r["flags"] or "[]"),
                "confidence": r["confidence"],
                "seconds": r["seconds"],
                "created_at": r["created_at"],
            }
            for r in latest_rows()
        ]
        return JSONResponse(
            {"metrics": names, "items": rows, "labels": labels, "flag_vocab": FLAG_VOCAB, "labeller": labeller}
        )

    async def api_check(request: Request):
        try:
            text = (await request.json()).get("text", "")
        except (ValueError, AttributeError):
            return JSONResponse({"error": "expected JSON text"}, status_code=400)
        try:
            from importlib import import_module

            textstats = import_module("pretrain.quality.textstats")
        except ImportError:
            return JSONResponse({"available": False, "message": "textstats is not installed yet"})
        if not isinstance(text, str):
            return JSONResponse({"error": "text must be a string"}, status_code=400)
        return JSONResponse(
            {
                "available": True,
                "loop": textstats.loop_metrics(text),
                "multilingual": textstats.multilingual_metrics(text),
                "highlights": textstats.highlight_spans(text),
            }
        )

    async def api_export(request: Request):
        rows = latest_rows()

        def stream():
            for row in rows:
                result = dict(row)
                result["flags"] = json.loads(result["flags"] or "[]")
                result["item"] = by_id[row["item_id"]]
                yield json.dumps(result, ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/dashboard", dashboard_page),
            Route("/check", check_page),
            Route("/static/{name}", static_file),
            Route("/api/items", api_items),
            Route("/api/item/{item_id:path}", api_item),
            Route("/api/label", save_label, methods=["POST"]),
            Route("/api/stats", api_stats),
            Route("/api/viz", api_viz),
            Route("/api/check", api_check, methods=["POST"]),
            Route("/api/export", api_export),
        ]
    )
    app.state.items = by_id
    app.state.order = ordered
    app.state.db_path = db_path
    app.state.labeller = labeller
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=WORK / "items.jsonl")
    parser.add_argument("--db", type=Path, default=WORK / "labels.sqlite")
    parser.add_argument("--labeller", default="local")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(create_app(args.items, args.db, args.labeller), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
