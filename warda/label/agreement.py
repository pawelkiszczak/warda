"""Inter-labeller agreement for decision labels: Cohen's kappa, Krippendorff's alpha, disagreement list.

Pure Python, so the labelling app and the export CLI need no numeric dependencies.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

FIELDS = ("category", "action")
REASON_FIELDS = ("verdict", "category", "action", "reason")


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa for two labellers' paired labels. Two constant, identical sequences count as full agreement."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two non-empty sequences of equal length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[label] * count_b[label] for label in count_a) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def krippendorff_alpha(rows: Sequence[Sequence[str | None]]) -> float:
    """Nominal Krippendorff's alpha. One row per item, one cell per labeller; `None` marks a missing label.

    Items with fewer than two labels are not pairable and are ignored. No variation at all counts as 1.0.
    """
    coincidences: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        values = [value for value in row if value is not None]
        if len(values) < 2:
            continue
        weight = 1 / (len(values) - 1)
        for i, x in enumerate(values):
            for j, y in enumerate(values):
                if i != j:
                    coincidences[x, y] += weight
    totals: dict[str, float] = defaultdict(float)
    for (x, _), weight in coincidences.items():
        totals[x] += weight
    n = sum(totals.values())
    if n == 0:
        raise ValueError("alpha needs at least one item with two labels")
    observed = sum(weight for (x, y), weight in coincidences.items() if x != y)
    expected = (n * n - sum(count * count for count in totals.values())) / (n - 1)
    return 1.0 if expected == 0 else 1 - observed / expected


def outcome(label: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    """What a label means for agreement: `confirm` and `fix` with the same category and action agree."""
    if label["verdict"] in ("reject", "unsure"):
        return label["verdict"], None, None
    return "label", label["category"], label["action"]


def disagreements(labels_by_labeller: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Items labelled by two or more labellers whose outcomes differ, with every labeller's verdict and reason."""
    names = sorted(labels_by_labeller)
    item_ids = sorted({item_id for labels in labels_by_labeller.values() for item_id in labels})
    out = []
    for item_id in item_ids:
        rows = {name: labels_by_labeller[name][item_id] for name in names if item_id in labels_by_labeller[name]}
        if len(rows) >= 2 and len({outcome(row) for row in rows.values()}) > 1:
            labels = {name: {key: row[key] for key in REASON_FIELDS} for name, row in rows.items()}
            out.append({"item_id": item_id, "labels": labels})
    return out


def report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Agreement over the latest label per (item, labeller): pairwise kappa per field, alpha per field, disagreements.

    Kappa and alpha use only labels that carry the field (`confirm` and `fix`); `reject`/`unsure` are missing values.
    """
    by_labeller: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_labeller[row["labeller"]][row["item_id"]] = row
    names = sorted(by_labeller)
    item_ids = sorted({item_id for labels in by_labeller.values() for item_id in labels})
    kappa = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            common = sorted(by_labeller[a].keys() & by_labeller[b].keys())
            pair: dict[str, Any] = {"n": len(common)}
            for field in FIELDS:
                ids = [
                    x for x in common if by_labeller[a][x][field] is not None and by_labeller[b][x][field] is not None
                ]
                pair[f"n_{field}"] = len(ids)
                pair[f"kappa_{field}"] = (
                    cohen_kappa([by_labeller[a][x][field] for x in ids], [by_labeller[b][x][field] for x in ids])
                    if ids
                    else None
                )
            kappa[f"{a} vs {b}"] = pair
    alpha: dict[str, float | None] = {}
    for field in FIELDS:
        cells = [[by_labeller[name][x][field] if x in by_labeller[name] else None for name in names] for x in item_ids]
        try:
            alpha[field] = krippendorff_alpha(cells)
        except ValueError:
            alpha[field] = None
    return {
        "labellers": {name: len(by_labeller[name]) for name in names},
        "n": len(item_ids),
        "kappa": kappa,
        "alpha": alpha,
        "disagreements": disagreements(by_labeller),
    }
