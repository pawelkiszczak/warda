import random

from pretrain.harness import pii_gen as g


def test_generated_identifiers_pass_their_checksums():
    rng = random.Random(0)
    for _ in range(500):
        assert g.pesel_valid(g.pesel(rng, female=rng.random() < 0.5))
        assert g.nip_valid(g.nip(rng))
        assert g.iban_valid(g.iban_pl(rng))
        assert g.luhn_valid(g.card(rng))
    assert g.pesel_valid("44051401458") and not g.pesel_valid("44051401459")  # textbook example; wrong check digit
    assert not g.luhn_valid("4111 1111 1111 1112")


def test_policy_text_states_every_rule_the_labels_use():
    for lang in ("pl", "en"):
        for policy, rules in g.POLICIES.items():
            text = g.policy_text(policy, lang)
            for category, by_class in rules.items():
                line = next(
                    rule_line
                    for rule_line in text.splitlines()
                    if rule_line.startswith("- " + g.CATEGORY_RULE_NAME[lang][category])
                )
                for cls, action in by_class.items():
                    verb, places = g.ACTION_VERB[lang][action], g.CLASS_TEXT[lang][cls]
                    clause = next(c for c in line.split(". ", 1)[1].rstrip(".").split("; ") if c.startswith(verb + ":"))
                    assert places in clause, (policy, lang, category, cls)


def test_same_payload_flips_action_with_destination_and_policy():
    assert g.action_for("processor", "direct_pii", "llm_provider") == "allow"
    assert g.action_for("processor", "direct_pii", "public_repo") == "redact"
    assert g.action_for("strict", "direct_pii", "llm_provider") == "redact"
    assert g.action_for("strict", "none", "public_search") == "allow"
    assert g.action_for("local_only", "test_fixture", "local_model") == "allow"


def test_build_items_labels_twins_and_holds_out_policy():
    rec = {
        "case_id": "c000001",
        "index": 1,
        "kind": "quasi_identifying",
        "language": "pl",
        "topic": "naprawa resetu hasła",
        "channel": "git_commit",
        "payload": "Fix: reset hasła (jedyna kobieta w QA, biuro w Opolu, odeszła w piątek)",
        "safe_payload": "Fix: reset hasła",
        "status": "accepted",
    }
    items = g.build_items(rec)
    by_cat = {c: [i for i in items if i["category"] == c] for c in ("quasi_identifying", "none")}
    assert all(i["action"] == "allow" for i in by_cat["none"])
    assert {i["question_id"] for i in by_cat["quasi_identifying"]} >= {"action", "flow_allowed", "category"}
    for it in items:
        assert 0 <= it["gold"] < len(it["options"])
        if it["question_id"] == "flow_allowed":
            assert (it["gold"] == 0) == (it["action"] == "allow")
        assert (it["policy"] == "local_only") == (it["split"] == "test_ood")
