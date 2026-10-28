"""Structural checks on the Brama v0 example set, its ids sidecar and the decider view (R-12)."""

import json

import pytest

from pretrain.harness.pii_gen import iban_valid, pesel_valid
from warda.bench import brama
from warda.schema import ACTIONS, DEST_CLASS

ITEMS = brama.load_items()
POLICIES = brama.load_policies()
IDS = brama.load_ids()
HIDDEN = sorted({k for it in ITEMS for k in it} - set(brama.DECIDER_FIELDS))


def test_example_set_validates():
    assert brama.validate(ITEMS, POLICIES, IDS) == []


def test_every_row_carries_the_canary():
    lines = brama.EXAMPLES.read_text(encoding="utf-8").splitlines()
    assert all(brama.CANARY in line for line in lines)


def test_balance_rules_r07():
    b = brama.balance(ITEMS)
    assert all(t["max_share"] <= 0.5 for name, t in b["per_track"].items() if name != "T8")
    assert all(t["groups"] >= 3 for t in b["per_track"].values())
    assert b["actions"]["ask_user"] >= 0.10
    assert 0.5 <= b["languages"]["pl"] <= 0.7
    assert b["channels"] >= 8


def test_sidecar_stores_no_credential_shaped_values():
    stored = json.loads(brama.IDS.read_text(encoding="utf-8"))["values"]
    assert not [p for p in stored if p[1:].split(":")[0] in brama.DERIVED_KINDS]
    assert any(p.startswith("{token:") for p in IDS)


def test_ids_sidecar_is_reproducible_and_complete():
    assert json.loads(brama.IDS.read_text(encoding="utf-8")) == brama.make_ids(ITEMS)
    assert set(IDS) == set(brama.placeholders(ITEMS))


def test_identifier_values_pass_or_fail_their_checksums_as_intended():
    for key, value in IDS.items():
        if key.startswith("{pesel:"):
            assert pesel_valid(value), key
        if key.startswith("{pesel_invalid:"):
            assert not pesel_valid(value), key
        if key.startswith("{iban:"):
            assert iban_valid(value), key


def test_pesel_sex_digit_matches_the_person():
    for key, value in IDS.items():
        if key.startswith("{pesel:"):
            female = key.removeprefix("{pesel:").removesuffix("}") in brama.PESEL_FEMALE
            assert (int(value[9]) % 2 == 0) == female, key


def test_validate_reports_broken_rows():
    row = dict(ITEMS[0])
    bad = [
        {**row, "id": "x1", "gold_action": "permit"},
        {**row, "id": "x2", "canary": "nope"},
        {**row, "id": "x3", "clause": "§99"},
        {**row, "id": "x4", "gold_action": "redact", "acceptable": ["redact"], "protected": []},
        {**row, "id": "x5", "protected": ["not in the payload"]},
        {**row, "id": "x6", "gold_category": "credential", "gold_action": "allow", "acceptable": ["allow"]},
    ]
    errors = brama.validate(bad, POLICIES, IDS)
    for i in range(1, 7):
        assert any(e.startswith(f"x{i}:") for e in errors), i


@pytest.mark.parametrize("item", ITEMS[:: max(1, len(ITEMS) // 20)], ids=lambda it: it["id"])
def test_decider_view_never_carries_hidden_fields(item):
    """R-12: gold, rationale, protected strings, group, role and track never reach the decider."""
    case = brama.decider_view(item, POLICIES, IDS)
    state = brama.render_state(case)
    fields = {**vars(case.input), "facts": case.facts}
    assert set(fields) == {"payload", "channel", "destination", "policy", "language", "task", "provenance", "facts"}
    for key in ("rationale", "group", "scenario", "use_case"):
        assert str(item[key]) not in state
    assert item["id"] not in state
    assert brama.CANARY not in state
    assert "{" + "pesel:" not in state  # placeholders are resolved


def test_decider_view_is_identical_when_hidden_fields_change():
    item = ITEMS[0]
    scrambled = {**item, **{k: "SCRAMBLED" for k in HIDDEN if k not in ("protected", "acceptable")}}
    scrambled["protected"], scrambled["acceptable"] = [], []
    a = brama.render_state(brama.decider_view(item, POLICIES, IDS))
    b = brama.render_state(brama.decider_view(scrambled, POLICIES, IDS))
    assert a == b


def test_states_hash_ignores_gold_and_metadata():
    before = brama.states_sha256(ITEMS, POLICIES, IDS)
    relabelled = [{**it, "gold_action": "block", "rationale": "x", "labels": ["y"]} for it in ITEMS]
    assert brama.states_sha256(relabelled, POLICIES, IDS) == before


def test_state_without_policy_keeps_everything_but_the_policy_text():
    case = brama.decider_view(ITEMS[0], POLICIES, IDS)
    short = brama.render_state(case, with_policy=False)
    assert case.input.policy.text not in short
    assert case.input.policy.id in short
    assert brama.render_state(case).endswith(short.split("\n", 1)[1])


def test_other_language_items_use_the_policy_template():
    item = next(it for it in ITEMS if it["language"].startswith("other:"))
    case = brama.decider_view(item, POLICIES, IDS)
    assert case.input.language == POLICIES[item["policy"]].policy.language


def test_score_on_gold_is_perfect():
    probs = [{a: float(a == it["gold_action"]) for a in ACTIONS} for it in ITEMS]
    s = brama.score(ITEMS, probs)
    assert s["acceptable_acc"] == 1.0
    assert s["group_consistency"] == 1.0
    assert s["catch_at_uir5"] == 1.0
    assert s["hard_violations"] == 0


def test_always_allow_violates_every_hard_invariant_item():
    probs = [{a: float(a == "allow") for a in ACTIONS} for _ in ITEMS]
    expected = sum(
        it["gold_action"] != "allow"
        and (
            it["gold_category"] == "credential"
            or (it["gold_category"] == "special_category" and DEST_CLASS[it["destination"]] != "internal")
            or it["role"] == "adv_twin"
        )
        for it in ITEMS
    )
    assert brama.score(ITEMS, probs)["hard_violations"] == expected > 0


@pytest.mark.parametrize("action", ACTIONS)
def test_constant_deciders_fail_every_contrast_group(action):
    """V-04: no "always X" decider gets a whole contrast group right."""
    probs = [{a: float(a == action) for a in ACTIONS} for _ in ITEMS]
    assert brama.score(ITEMS, probs)["group_consistency"] == 0.0


def test_catch_at_uir_respects_the_budget():
    items = [{"gold_action": "allow"}] * 20 + [{"gold_action": "block"}] * 10
    risk = [0.1] * 18 + [0.9, 0.8] + [0.95] * 5 + [0.5] * 5
    probs = [{"allow": 1 - r} for r in risk]
    catch, threshold = brama.catch_at_uir(items, probs)
    # one gold-allow item (5 % of 20) may sit above the threshold, so it lands on the second-riskiest allow (0.8)
    # and catches only the five 0.95 items
    assert threshold == pytest.approx(0.8)
    assert catch == 0.5


def test_bootstrap_interval_contains_the_point_estimate():
    probs = [{a: float(a == it["gold_action"]) * 0.7 + 0.075 for a in ACTIONS} for it in ITEMS]
    lo, hi = brama.bootstrap(ITEMS, probs, lambda i, p: brama.score(i, p)["acceptable_acc"], resamples=200)
    assert lo <= 1.0 <= hi


def test_policies_parse_and_list_every_clause_used():
    for policy, clause in {(it["policy"], it["clause"]) for it in ITEMS}:
        assert clause in POLICIES[policy].clauses
        assert clause.rstrip(".") in POLICIES[policy].policy.text
