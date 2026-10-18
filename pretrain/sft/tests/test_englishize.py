"""Behavior tests for the English rendering of amount and urgency (severity) rows.

For every template, the numbers written into the English state must be exactly the numbers the gold
label was computed from: re-deriving the answer from the English text alone must reproduce `gold`.
"""

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pretrain/sft.py shadows this package
import generate as g


def english_rows(generator, template, base=7, split="train"):
    """All rows of one template, English-ified like rows_for_split does (English base cases get englishize()).

    `base` is the generator's idx // 8; idx = 8*base + template keeps idx % 8 == template. For amounts,
    even bases additionally produce a gold-flipping twin row; for urgency, base 7/8/16 select the
    deterministic low/medium/high English value tuples.
    """
    rng = random.Random(1000 + 8 * base + template)
    rows = generator(rng, split, 8 * base + template, "en")
    for row in rows:
        g.englishize(row)
    return rows


AMOUNT_PARSERS = {
    0: r"The net price is ([\d.]+) PLN\. VAT rate: (\d+)%\.",
    6: r"The net price is ([\d.]+) PLN\. VAT rate: (\d+)%\.",
    1: r"The gross price is ([\d.]+) PLN\. VAT rate: (\d+)%\.",
    3: r"The gross price is ([\d.]+) PLN\. VAT rate: (\d+)%\.",
    2: r"The net list price is ([\d.]+) PLN, discount is (\d+)%, and VAT rate is (\d+)%\.",
    4: r"The net list price is ([\d.]+) PLN, discount is (\d+)%, and VAT rate is (\d+)%\.",
    5: r"The gross total is ([\d.]+) PLN, payable in (\d+) equal installments\.",
    7: r"The gross price is ([\d.]+) PLN, discount is (\d+)%\.",
}


def amount_from_english(template, state):
    """Recompute the correct amount using only numbers stated in the English sentence (mirrors amount_result)."""
    match = re.search(AMOUNT_PARSERS[template], state)
    assert match is not None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", match.group(0))]
    if template in (0, 6):
        net, vat = numbers
        return round(net * (1 + vat / 100), 2) if template == 0 else round(net * vat / 100, 2)
    if template in (1, 3):
        gross, vat = numbers
        return round(gross / (1 + vat / 100), 2)
    if template in (2, 4):
        net, discount, vat = numbers
        return round(round(net * (100 - discount) / 100, 2) * (1 + vat / 100), 2)
    if template == 5:
        gross, parts = numbers
        return round(gross / parts, 2)
    gross, discount = numbers
    return round(gross * (100 - discount) / 100, 2)


@pytest.mark.parametrize("base", [7, 8])  # 7: plain rows; 8: adds a gold-flipping twin row
@pytest.mark.parametrize("template", range(8))
def test_english_amount_states_reproduce_gold(template, base):
    for row in english_rows(g.make_amount, template, base):
        assert "_en" not in row
        expected = amount_from_english(template, row["state"])
        assert row["options"][row["gold"]] == f"{expected:.2f} PLN", row["state"]


@pytest.mark.parametrize("base", [7, 8, 16])  # deterministic low / medium / high value tuples
@pytest.mark.parametrize("template", range(8))
def test_english_urgency_states_reproduce_gold(template, base):
    for row in english_rows(g.make_severity, template, base):
        assert "_en" not in row
        users, hours, deadline = map(
            int,
            re.findall(
                r"(\d+) users are affected; the outage has lasted (\d+) hours; "
                r"the critical deadline is in (\d+) hours",
                row["state"],
            )[0],
        )
        score = 3 if users >= 1000 or deadline <= 1 else 2 if users >= 50 or hours >= 3 or deadline <= 4 else 1
        assert row["gold"] == score - 1, row["state"]
        assert row["options"] == ["low", "medium", "high"]


def test_englishize_raises_when_generator_facts_missing():
    row = {
        "id": "x",
        "state": "Czas awarii: 8 godz.",
        "question": "Jaki poziom pilności wynika z reguły?",
        "options": ["niski", "średni", "wysoki"],
        "gold": 2,
        "type": "score",
        "family": "urgency",
        "template_id": "urgency-3",
        "language": "pl",
    }
    with pytest.raises(ValueError, match="generator facts"):
        g.englishize(row)
