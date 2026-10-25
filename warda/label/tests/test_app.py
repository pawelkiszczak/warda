import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from warda.label.agreement import cohen_kappa
from warda.label.app import create_app
from warda.label.export import export

POLICY = "Example policy:\n- Direct personal data. Block: public."
STATE = POLICY + '\n\nChannel: git commit\nDestination: public GitHub repository\nContent:\n"""\n{payload}\n"""'
POLICY_FILE = """+++
id = "ex-test"
name = "Example Ltd (fictional)"
clauses = ["§1", "§2"]
+++

**§1 Scope.** Everything the assistant sends.

**§2 Personal data.** Never to public places: redact it.
"""


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


BRAMA_BASE = {
    "id": "br-1", "group": "g-1", "role": "base", "track": "T1", "language": "pl", "policy": "ex-test",
    "channel": "git_commit", "destination": "public_repo", "task": "fix signup", "provenance": "none",
    "facts": {"tier1_hits": ["pesel"]}, "payload": "fix: PESEL {pesel:wk} (Wanda Testowa)",
    "gold_action": "redact", "acceptable": ["redact", "block"], "gold_category": "direct_pii", "tier": 1,
    "clause": "§2", "protected": ["{pesel:wk}", "Wanda Testowa"], "rationale": "§2: no personal data in public.",
}  # fmt: skip
BRAMA_TWIN = {
    **BRAMA_BASE, "id": "br-2", "role": "safe_twin", "twin_of": "br-1", "facts": {"tier1_hits": []},
    "payload": "fix: PESEL validation", "gold_action": "allow", "acceptable": ["allow"], "gold_category": "none",
    "protected": [], "rationale": "No person.",
}  # fmt: skip


@pytest.fixture
def items_path(tmp_path):
    rows = [
        pii_item("a", "direct_pii", "block"),
        pii_item("b", "none", "allow"),
        pii_item("c", "credential", "block"),
        {"id": "hw-000001", "language": "pl", "channel": "pr_description", "destination": "public_repo",
         "policy_id": "ex-missing", "task": "fix pagination", "payload": "Jan Testowy, tel. 600 000 000"},
        BRAMA_BASE,
        BRAMA_TWIN,
    ]  # fmt: skip
    path = tmp_path / "items.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (tmp_path / "items.ids.json").write_text(json.dumps({"values": {"{pesel:wk}": "00000000001"}}), encoding="utf-8")
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "ex-test.md").write_text(POLICY_FILE, encoding="utf-8")
    return path


def post(client, item_id, verdict, labeller=None, **extra):
    body = {"item_id": item_id, "verdict": verdict, "reason": f"{verdict} {item_id}", "seconds": 3, **extra}
    if labeller:
        body["labeller"] = labeller
    return client.post("/api/label", json=body)


def test_label_round_trip_and_latest_wins(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice", order="file")) as client:
        listing = client.get("/api/items").json()
        assert [i["id"] for i in listing["items"]][:3] == ["a", "b", "c"]
        assert listing["last"] is None and listing["verdicts"] == ["confirm", "fix", "reject", "unsure"]
        item = client.get("/api/item/a").json()
        assert item["policy"]["text"] == POLICY
        assert item["body"].startswith("Channel: git commit")
        assert (item["proposed"]["category"], item["proposed"]["action"], item["gold"]) == ("direct_pii", "block", 3)

        assert post(client, "a", "confirm").status_code == 200
        assert client.get("/api/item/a").json()["label"]["action"] == "block"  # confirm stores the proposed gold
        assert post(client, "a", "fix", category="direct_pii", action="redact").status_code == 200
        label = client.get("/api/item/a").json()["label"]
        assert (label["verdict"], label["action"], label["reason"]) == ("fix", "redact", "fix a")

        listing = client.get("/api/items").json()
        assert (listing["done"], listing["last"]) == (1, "a")
        assert listing["items"][0]["verdict"] == "fix"
        assert len(client.get("/api/export").text.splitlines()) == 1


def test_brama_item_shows_policy_text_resolved_payload_and_twin(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        item = client.get("/api/item/br-2").json()
        base = client.get("/api/item/br-1").json()
    assert item["policy"]["name"] == "Example Ltd (fictional)" and "**§2 Personal data.**" in item["policy"]["text"]
    assert item["clauses"] == ["§1", "§2", "silence"]
    assert {"key": "destination_class", "value": "public"} in item["context"]
    assert item["twin"]["id"] == "br-1" and item["twin"]["payload"] == "fix: PESEL 00000000001 (Wanda Testowa)"
    assert base["payload"][1] == {"text": "00000000001", "placeholder": "{pesel:wk}", "kind": "pesel"}
    assert base["proposed"]["protected"] == ["00000000001", "Wanda Testowa"]
    assert base["proposed"]["acceptable"] == ["redact", "block"] and base["proposed"]["clause"] == "§2"


def test_protected_spans_round_trip_through_placeholders(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        response = post(
            client, "br-1", "fix", category="direct_pii", action="block", clause="§2", protected=["00000000001"]
        )
        assert response.status_code == 200 and response.json()["protected"] == ["{pesel:wk}"]  # stored like the gold
        assert client.get("/api/item/br-1").json()["label"]["protected"] == ["00000000001"]  # shown resolved
        assert post(client, "br-1", "confirm").json()["protected"] == ["{pesel:wk}", "Wanda Testowa"]


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        ({"clause": "§9"}, "not declared"),
        ({"protected": ["Jan Kowalski"]}, "does not occur"),
        ({"protected": "Wanda Testowa"}, "must be a list"),
        ({"protected": ["  "]}, "non-empty"),
    ],
)
def test_clause_and_spans_must_match_the_item(items_path, tmp_path, extra, error):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        response = post(client, "br-1", "fix", category="direct_pii", action="redact", **extra)
    assert response.status_code == 400 and error in response.json()["error"]


def test_handwritten_item_without_policy_file_or_gold_must_be_fixed(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        item = client.get("/api/item/hw-000001").json()
        assert item["policy"] == {"id": "ex-missing", "name": None, "text": "", "found": False}
        assert item["clauses"] == [] and item["proposed"]["action"] is None
        assert post(client, "hw-000001", "confirm").status_code == 400
        assert post(client, "hw-000001", "fix", category="direct_pii", action="block", clause="§1").status_code == 400
        assert post(client, "hw-000001", "fix", category="direct_pii", action="block").status_code == 200


def test_blind_mode_hides_gold_and_accepts_only_fresh_labels(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice", blind=True)) as client:
        assert client.get("/api/items").json()["verdicts"] == ["label", "reject", "unsure"]
        item = client.get("/api/item/br-2").json()
        assert item["proposed"] is None and item["twin"] is None and item["meta"] == {"language": "pl"}
        assert client.get("/api/item/a").json()["gold"] is None
        assert post(client, "br-2", "confirm").status_code == 400
        assert post(client, "br-2", "fix", category="none", action="allow").status_code == 400
        assert post(client, "br-2", "label", category="none", action="allow").status_code == 200
        assert client.get("/api/stats").status_code == 403
        assert client.get("/api/export").status_code == 403


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
        {"item_id": ["a"], "verdict": "confirm", "seconds": 1},
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
    with TestClient(create_app(items_path, tmp_path / "b.sqlite", "bob", blind=True)) as client:
        post(client, "a", "label", category="direct_pii", action="block")
        post(client, "b", "label", category="none", action="allow")
    out = tmp_path / "agree"
    agreement = export([tmp_path / "a.sqlite", tmp_path / "b.sqlite"], out, items_path)
    assert sorted(p.name for p in out.iterdir()) == ["agreement.json", "labels.jsonl", "labels_audit.jsonl"]
    assert len((out / "labels_audit.jsonl").read_text(encoding="utf-8").splitlines()) == 5
    latest = [json.loads(line) for line in (out / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(latest) == 4 and all(isinstance(row["protected"], list) for row in latest)
    assert json.loads((out / "agreement.json").read_text(encoding="utf-8")) == agreement
    assert agreement["labellers"] == {"alice": 2, "bob": 2} and agreement["conflicts"] == []
    [disagreement] = agreement["disagreements"]  # a blind label equal to a confirm agrees; reject vs label does not
    assert disagreement["item_id"] == "b" and disagreement["labels"]["alice"]["reason"] == "reject b"
    assert agreement["by_language"]["en"]["alice vs bob"]["kappa_action"] == 1.0


def test_export_latest_follows_row_order_not_clocks(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        post(client, "a", "confirm")
        post(client, "a", "reject")
    with sqlite3.connect(tmp_path / "a.sqlite") as db:  # the laptop clock went back between the two saves
        db.execute("UPDATE labels SET created_at = '2030-01-01T00:00:00Z' WHERE verdict = 'confirm'")
    with TestClient(create_app(items_path, tmp_path / "b.sqlite", "alice")) as client:
        post(client, "a", "unsure")
    agreement = export([tmp_path / "a.sqlite"], tmp_path / "one")
    assert agreement["conflicts"] == []
    latest = json.loads((tmp_path / "one" / "labels.jsonl").read_text(encoding="utf-8"))
    assert latest["verdict"] == "reject"
    agreement = export([tmp_path / "a.sqlite", tmp_path / "b.sqlite"], tmp_path / "two")
    [conflict] = agreement["conflicts"]  # same labeller in two databases: the later --db wins, and it is reported
    assert (conflict["item_id"], conflict["labeller"]) == ("a", "alice")
    latest = json.loads((tmp_path / "two" / "labels.jsonl").read_text(encoding="utf-8"))
    assert latest["verdict"] == "unsure"


def test_static_route_serves_only_the_ui_files(items_path, tmp_path):
    with TestClient(create_app(items_path, tmp_path / "a.sqlite", "alice")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/static/app.py").status_code == 404
        assert client.get("/static/..%2Fapp.py").status_code == 404
