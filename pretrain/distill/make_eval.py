#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import ROOT, WORK, log, read_jsonl, write_jsonl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=WORK / "teacher_eval_verified.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "pretrain" / "work" / "sft_jev" / "ext" / "pl_real.jsonl")
    parser.add_argument("--limit", type=int, help="maximum accepted items (normally omitted)")
    parser.add_argument(
        "--teacher-only",
        action="store_true",
        help="no verifier: keep items where the teacher alone is >=0.7 confident (larger, cheaper set)",
    )
    args = parser.parse_args()
    all_rows = list(read_jsonl(args.input))
    eligible = []
    input_families: Counter[str] = Counter()
    input_sources: Counter[str] = Counter()
    agreements = 0
    for row in all_rows:
        input_families[row["family"]] += 1
        input_sources[row["source"]] += 1
        t = row.get("target", [])
        teacher_gold = max(range(len(t)), key=t.__getitem__) if t else None
        if args.teacher_only:
            if not t or max(t) < 0.7:
                continue
            eligible.append({**row, "gold": teacher_gold, "split": "eval"})
            continue
        v = row.get("verifier_target", [])
        if not t or not v or len(t) != len(v):
            continue
        verifier_gold = max(range(len(v)), key=v.__getitem__)
        if teacher_gold == verifier_gold:
            agreements += 1
        if teacher_gold != verifier_gold or max(t) < 0.7:
            continue
        eligible.append({**row, "gold": teacher_gold, "split": "eval"})
    by_family = defaultdict(list)
    for row in eligible:
        by_family[row["family"]].append(row)
    families = sorted(by_family)
    # Find the largest result size whose per-family quota is at most 10%.
    requested = min(len(eligible), args.limit) if args.limit is not None else len(eligible)
    target, cap = 0, 0
    for size in range(requested, 9, -1):
        quota = size // 10
        if sum(min(len(by_family[family]), quota) for family in families) >= size:
            target, cap = size, quota
            break
    selected: list[dict[str, Any]] = []
    selected_by_family: Counter[str] = Counter()
    while len(selected) < target:
        progressed = False
        for family in families:
            if len(selected) >= target:
                break
            if by_family[family] and selected_by_family[family] < cap:
                selected.append(by_family[family].pop(0))
                selected_by_family[family] += 1
                progressed = True
        if not progressed:
            break
    if selected and max(Counter(r["family"] for r in selected).values()) > len(selected) * 0.1:
        raise ValueError("selected evaluation data exceeds the per-family 10% quota")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output, selected)
    family_counts = Counter(r["family"] for r in selected)
    source_counts = Counter(r["source"] for r in selected)
    total = len(all_rows)
    family_yield = {key: f"{family_counts[key]}/{value}" for key, value in sorted(input_families.items())}
    source_yield = {key: f"{source_counts[key]}/{value}" for key, value in sorted(input_sources.items())}
    agreement = (
        "n/a (teacher only)" if args.teacher_only else f"{agreements}/{total} ({agreements / max(total, 1):.3f})"
    )
    log(
        f"eval: retained {len(selected)}/{total}; teacher/verifier agreement={agreement}; selected/input family yield={family_yield}; selected/input source yield={source_yield}; selected families={dict(family_counts)}; selected sources={dict(source_counts)}; output={args.output}"
    )


if __name__ == "__main__":
    main()
