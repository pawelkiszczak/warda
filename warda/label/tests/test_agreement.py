import pytest

from warda.label.agreement import cohen_kappa, disagreements, krippendorff_alpha, report


def test_kappa_of_identical_sequences_is_one():
    assert cohen_kappa(["allow", "block", "redact"], ["allow", "block", "redact"]) == 1.0
    assert cohen_kappa(["allow", "allow"], ["allow", "allow"]) == 1.0


def test_kappa_matches_the_textbook_two_by_two_table():
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no: observed 0.7, expected 0.5 -> kappa 0.4.
    a = ["yes"] * 25 + ["no"] * 25
    b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_kappa_rejects_unpaired_input():
    with pytest.raises(ValueError):
        cohen_kappa(["allow"], [])


def test_alpha_ignores_a_missing_cell():
    # Pairable values: a x3, b x3 (n=6); one a-b unit gives observed 2, expected (36 - 18) / 5 = 3.6 -> 1 - 2/3.6.
    rows: list[list[str | None]] = [["a", "a"], ["a", "b"], ["b", "b"], ["b", None]]
    assert krippendorff_alpha(rows) == pytest.approx(4 / 9)


def test_alpha_needs_a_pairable_item():
    with pytest.raises(ValueError):
        krippendorff_alpha([["a", None], [None, None]])


def label(verdict, category=None, action=None, reason=""):
    return {"verdict": verdict, "category": category, "action": action, "reason": reason}


def test_disagreements_list_only_mismatching_outcomes_with_every_reason():
    by_labeller = {
        "alice": {
            "same": label("confirm", "direct_pii", "block", "PESEL in payload"),
            "fix-equals-confirm": label("confirm", "credential", "block"),
            "action": label("confirm", "direct_pii", "block", "policy says block"),
            "rejected": label("confirm", "none", "allow", "clean"),
            "only-alice": label("reject", reason="broken item"),
        },
        "bob": {
            "same": label("fix", "direct_pii", "block", "agree"),
            "fix-equals-confirm": label("fix", "credential", "block"),
            "action": label("fix", "direct_pii", "redact", "a rewrite is possible"),
            "rejected": label("reject", reason="payload is not realistic"),
        },
    }
    found = disagreements(by_labeller)
    assert [d["item_id"] for d in found] == ["action", "rejected"]
    assert found[0]["labels"]["alice"]["reason"] == "policy says block"
    assert found[0]["labels"]["bob"] == label("fix", "direct_pii", "redact", "a rewrite is possible")


def test_report_kappa_skips_labels_without_the_field():
    rows = [
        {"item_id": "1", "labeller": "a", **label("confirm", "none", "allow")},
        {"item_id": "1", "labeller": "b", **label("confirm", "none", "allow")},
        {"item_id": "2", "labeller": "a", **label("fix", "direct_pii", "block")},
        {"item_id": "2", "labeller": "b", **label("fix", "direct_pii", "redact")},
        {"item_id": "3", "labeller": "a", **label("confirm", "none", "allow")},
        {"item_id": "3", "labeller": "b", **label("unsure")},
    ]
    result = report(rows)
    pair = result["kappa"]["a vs b"]
    assert (pair["n"], pair["n_action"]) == (3, 2)
    assert pair["kappa_category"] == 1.0
    assert pair["kappa_action"] == pytest.approx(cohen_kappa(["allow", "block"], ["allow", "redact"]))
    assert [d["item_id"] for d in result["disagreements"]] == ["2", "3"]
