import json

import pytest
from starlette.testclient import TestClient

from warda.label.agreement import cohen_kappa
from warda.label.app import create_app
from warda.label.export import export

POLICY = "Example policy:\n- Direct personal data. Block: public."
STATE = POLICY + '\n\nChannel: git commit\nDestination: public GitHub repository\nContent:\n"""\n{payload}\n"""'


def pii_item(item_id, category, action):
    return {
        "id": item_id,
        "state": STATE.format(payload=f"fixture {item_id}"),
        "question": "What should the data guard decide before this content is passed on?",
        "options": ["allow unchanged", "redact the protected data", "ask the user", "block"],
        "gold": ["allow", "redact", "ask_user", "block"].index(action),
        "language": "en",
        "question_id": "action",
        "category": category,
        "action": action,
    }


@pytest.fixture
def items_path(tmp_path):
    rows = [
        pii_item("a", "direct_pii", "block"),
        pii_item("b", "none", "allow"),
        pii_item("c", "credential", "block"),
        {"id": "hw-000001", "language": "pl", "channel": "pr_body", "destination": "github_public",
         "policy_id": "ex-softhouse", "task": "fix pagination", "payload": "Jan Testowy, tel. 600 000 000"},
    ]  # fmt: skip
    path = tmp_path / "items.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def post(client, item_id, verdict, labeller=None, **extra):
    body = {"item_id": item_id, "verdict": verdict, "reason": f"{verdict} {item_id}", "seconds": 3, **extra}
    if labeller:
        body["labeller"] = labeller
    return client.post("/api/label", json=body)


def test_label_round_trip_and_latest_wins(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice", order="file")) as client:
        listing = client.get("/api/items").json()
        assert [i["id"] for i in listing["items"]] == ["a", "b", "c", "hw-000001"]
        assert listing["last"] is None
        item = client.get("/api/item/a").json()
        assert item["policy"] == POLICY
        assert item["body"].startswith("Channel: git commit")
        assert item["proposed"] == {"category": "direct_pii", "action": "block"}
        assert item["gold"] == 3

        assert post(client, "a", "confirm").status_code == 200
        assert client.get("/api/item/a").json()["label"]["action"] == "block"  # confirm stores the proposed gold
        assert post(client, "a", "fix", category="direct_pii", action="redact").status_code == 200
        label = client.get("/api/item/a").json()["label"]
        assert (label["verdict"], label["action"], label["reason"]) == ("fix", "redact", "fix a")

        listing = client.get("/api/items").json()
        assert (listing["done"], listing["last"]) == (1, "a")
        assert len(client.get("/api/export").text.splitlines()) == 1


def test_handwritten_item_has_policy_block_and_must_be_fixed(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        item = client.get("/api/item/hw-000001").json()
        assert item["policy"] == "Policy: ex-softhouse"
        assert "Jan Testowy" in item["body"] and item["proposed"] == {"category": None, "action": None}
        assert post(client, "hw-000001", "confirm").status_code == 400
        assert post(client, "hw-000001", "fix", category="direct_pii", action="block").status_code == 200


@pytest.mark.parametrize(
    "extra",
    [
        {"category": "home_address", "action": "block"},
        {"category": "direct_pii", "action": "delete"},
        {"category": None, "action": "block"},
    ],
)
def test_fix_outside_the_schema_is_rejected(items_path, tmp_path, extra):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        response = post(client, "a", "fix", **extra)
        assert response.status_code == 400 and "fix needs" in response.json()["error"]
        assert client.get("/api/item/a").json()["label"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"item_id": "missing", "verdict": "confirm", "seconds": 1},
        {"item_id": "a", "verdict": "maybe", "seconds": 1},
        {"item_id": "a", "verdict": "confirm", "seconds": -1},
        {"item_id": "a", "verdict": "confirm", "seconds": 1.5},
        ["not", "an", "object"],
    ],
)
def test_malformed_labels_are_rejected(items_path, tmp_path, body):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        assert client.post("/api/label", json=body).status_code == 400


def test_stats_kappa_matches_agreement_module(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "shared.sqlite", "alice")) as client:
        for item_id in ("a", "b", "c"):
            post(client, item_id, "confirm", labeller="alice")
        post(client, "a", "confirm", labeller="bob")
        post(client, "b", "fix", labeller="bob", category="direct_pii", action="block")
        post(client, "c", "fix", labeller="bob", category="credential", action="redact")
        stats = client.get("/api/stats").json()
    pair = stats["kappa"]["alice vs bob"]
    assert pair["kappa_action"] == pytest.approx(cohen_kappa(["block", "allow", "block"], ["block", "block", "redact"]))
    assert pair["kappa_category"] == pytest.approx(
        cohen_kappa(["direct_pii", "none", "credential"], ["direct_pii", "direct_pii", "credential"])
    )
    assert stats["verdicts"] == {"alice": {"confirm": 3}, "bob": {"confirm": 1, "fix": 2}}
    assert [d["item_id"] for d in stats["disagreements"]] == ["b", "c"]


def test_limit_gives_every_labeller_the_same_items(items_path, tmp_path):
    first = create_app(items_path, tmp_path / "a.sqlite", "alice", limit=2).state.order
    assert first == create_app(items_path, tmp_path / "b.sqlite", "bob", limit=2).state.order
    assert len(first) == 2


def test_export_merges_two_labellers_databases(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        post(client, "a", "confirm")
        post(client, "b", "confirm")
        post(client, "b", "reject")  # relabel: only the latest counts
    with TestClient(create_app(items_path, tmp_path / "b.sqlite", "bob")) as client:
        post(client, "a", "confirm")
        post(client, "b", "confirm")
    out = tmp_path / "agree"
    agreement = export([tmp_path / "a.sqlite", tmp_path / "b.sqlite"], out)
    assert sorted(p.name for p in out.iterdir()) == ["agreement.json", "labels.jsonl", "labels_audit.jsonl"]
    assert len((out / "labels_audit.jsonl").read_text(encoding="utf-8").splitlines()) == 5
    latest = [json.loads(line) for line in (out / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(latest) == 4
    assert json.loads((out / "agreement.json").read_text(encoding="utf-8")) == agreement
    assert agreement["labellers"] == {"alice": 2, "bob": 2}
    [disagreement] = agreement["disagreements"]
    assert disagreement["item_id"] == "b"
    assert disagreement["labels"]["alice"]["reason"] == "reject b"
    assert agreement["kappa"]["alice vs bob"]["kappa_action"] == 1.0  # "b" has no alice action, only "a" pairs


def test_static_route_serves_only_the_ui_files(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/static/app.py").status_code == 404
        assert client.get("/static/..%2Fapp.py").status_code == 404
