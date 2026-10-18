import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from starlette.testclient import TestClient

from pretrain.quality import export_labels
from pretrain.quality.app import create_app
from pretrain.quality.export_labels import export


def fixture_items(path: Path):
    rows = [
        {
            "id": "a",
            "origin": "speakleash",
            "source": "sl",
            "text": "good text",
            "truncated": False,
            "source_meta": {"quality": "HIGH"},
            "features": {
                "cheap": {"score": 3.0},
                "loop": {"loop_score": 0.1},
                "multilingual": {
                    "multilingual_score": 0.2,
                    "top_lang": "pl",
                    "pl_share": 0.9,
                    "lang_shares": {"pl": 0.9},
                },
                "lm": {"nll_mean": 2.0},
            },
        },
        {
            "id": "b",
            "origin": "fineweb-2",
            "source": "fineweb-2",
            "text": "bad text",
            "truncated": True,
            "source_meta": {"language_score": 0.8},
            "features": {"cheap": {"score": 1.0}, "loop": {"loop_score": 0.9}},
        },
        {
            "id": "c",
            "origin": "fineweb-edu",
            "source": "fineweb-edu",
            "text": "middle text",
            "features": {"cheap": {"score": 2.0}},
        },
    ]
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return rows


def test_label_stats_and_export_roundtrip(tmp_path):
    items = tmp_path / "items.jsonl"
    fixture_items(items)
    db = tmp_path / "labels.sqlite"
    app = create_app(items, db, "tester")
    with TestClient(app) as client:
        assert client.get("/api/items?limit=3").status_code == 200
        assert client.get("/api/item/b").json()["features"]["loop"]["loop_score"] == 0.9
        assert (
            client.post(
                "/api/label",
                json={"item_id": "a", "quality": "HIGH", "flags": ["looped"], "confidence": 3, "seconds": 4},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/label", json={"item_id": "b", "quality": "LOW", "confidence": 2, "seconds": 6}
            ).status_code
            == 200
        )
        assert client.post("/api/label", json={"item_id": "c", "quality": "MEDIUM", "seconds": 2}).status_code == 200
        assert client.post("/api/label", json={"item_id": "c", "quality": "LOW", "seconds": 3}).status_code == 200
        stats = client.get("/api/stats").json()
        assert stats["labelled"] == 3 and stats["by_origin"] == {"speakleash": 1, "fineweb-2": 1, "fineweb-edu": 1}
        cheap = next(m for m in stats["metrics"] if m["name"] == "cheap.score")
        assert cheap["high_auroc"] == 1.0 and cheap["low_auroc"] == 0.0
        selected = client.get("/api/stats?metric=cheap.score").json()
        assert "cheap.score" in selected["metric_names"]
        assert selected["histogram_metric"]["name"] == "cheap.score"
        assert len(selected["histogram_metric"]["values"]) == 3
        assert len(client.get("/api/export").text.splitlines()) == 3
    assert create_app(items, db, "second-labeller").state.order == app.state.order
    out = tmp_path / "export"
    latest, audit = export(items, db, out)
    assert (latest, audit) == (3, 4)
    exported = [json.loads(x) for x in (out / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert next(x for x in exported if x["item_id"] == "c")["quality"] == "LOW"
    assert any(x["feature.cheap.score"] == 3.0 for x in exported)
    assert any(x["feature.multilingual.lang_shares.pl"] == 0.9 for x in exported)
    assert len((out / "labels_audit.jsonl").read_text(encoding="utf-8").splitlines()) == 4


def test_absent_groups_and_bad_label_are_tolerated(tmp_path):
    items = tmp_path / "items.jsonl"
    fixture_items(items)
    with TestClient(create_app(items, tmp_path / "labels.sqlite")) as client:
        item = client.get("/api/item/c").json()
        assert item["text"] == "middle text" and "stylometrix" not in item.get("features", {})
        stats = client.get("/api/stats").json()
        assert stats["labelled"] == 0 and stats["metrics"] == []
        assert client.post("/api/label", json={"item_id": "missing", "quality": "HIGH"}).status_code == 400
        assert client.get("/dashboard").status_code == 200
        assert client.get("/").status_code == 200


def test_viz_endpoint_serves_every_item_with_requested_metrics_and_latest_labels(tmp_path):
    items = tmp_path / "items.jsonl"
    fixture_items(items)
    with TestClient(create_app(items, tmp_path / "labels.sqlite", "tester")) as client:
        client.post("/api/label", json={"item_id": "b", "quality": "MEDIUM", "flags": ["looped"]})
        client.post("/api/label", json={"item_id": "b", "quality": "LOW", "flags": ["looped", "garbled_ocr"]})
        viz = client.get("/api/viz?metric=cheap.score&metric=loop.loop_score").json()
        assert {i["id"] for i in viz["items"]} == {"a", "b", "c"}
        assert "cheap.score" in viz["metrics"] and viz["metrics"].count("loop.loop_score") == 1
        b = next(i for i in viz["items"] if i["id"] == "b")
        assert b["m"]["loop.loop_score"] == 0.9 and b["m"]["cheap.score"] == 1.0 and b["m"]["lm.nll_mean"] is None
        assert sorted(i["pos"] for i in viz["items"]) == [0, 1, 2]
        assert viz["labels"] == [
            {
                "item_id": "b",
                "labeller": "tester",
                "quality": "LOW",
                "flags": ["garbled_ocr", "looped"],
                "confidence": viz["labels"][0]["confidence"],
                "seconds": viz["labels"][0]["seconds"],
                "created_at": viz["labels"][0]["created_at"],
            }
        ]
        assert client.get("/static/dashboard.css").status_code == 200


def test_tied_percentiles_use_midrank_and_suppress_median_mass(tmp_path):
    path = tmp_path / "items.jsonl"
    rows = [
        {
            "id": f"tie-{n}",
            "origin": "speakleash",
            "source": "fixture",
            "text": "sample",
            "features": {"cheap": {"zero_heavy": 0.0 if n < 19 else 1.0}},
        }
        for n in range(20)
    ]
    path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
    with TestClient(create_app(path, tmp_path / "labels.sqlite")) as client:
        tied = client.get("/api/item/tie-0").json()["metric_percentiles"]["cheap.zero_heavy"]
        high = client.get("/api/item/tie-19").json()["metric_percentiles"]["cheap.zero_heavy"]
        assert tied["percentile"] == 47.5 and tied["extreme"] is False
        assert high["percentile"] == 97.5 and high["extreme"] is True


def test_optional_parquet_join(tmp_path, monkeypatch):
    items = tmp_path / "items.jsonl"
    fixture_items(items)
    db = tmp_path / "labels.sqlite"
    create_app(items, db)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(export_labels, "WORK", work)
    pq.write_table(pa.table({"id": ["a", "b"], "text": ["A", "B"]}), work / "dataset.parquet")
    pq.write_table(pa.table({"id": ["a"], "extra_feature": [0.75]}), work / "features.parquet")
    out = tmp_path / "export"
    export(items, db, out)
    joined = pq.read_table(out / "dataset.parquet")
    assert joined.column("extra_feature").to_pylist() == [0.75, None]
