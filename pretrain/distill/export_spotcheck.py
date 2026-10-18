"""Export a stratified sample of the realistic Polish eval set for human review.

Writes `work/distill/spotcheck_pl_real.md` (readable) and `spotcheck_pl_real.csv` (one row per item with empty
`reviewer_ok` / `reviewer_answer` / `note` columns to fill in). Items are spread across question families.

    pretrain/.venv/bin/python pretrain/distill/export_spotcheck.py --n 100
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

WORK = Path(__file__).resolve().parents[1] / "work"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = [
        json.loads(line)
        for line in (WORK / "sft_jev" / "ext" / "pl_real.jsonl").read_text().split("\n")
        if line.strip()
    ]
    by_family = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)
    rng = random.Random(a.seed)
    for v in by_family.values():
        rng.shuffle(v)
    sample: list[dict[str, Any]] = []
    i = 0
    while len(sample) < min(a.n, len(rows)):  # round-robin over families
        for v in by_family.values():
            if i < len(v) and len(sample) < a.n:
                sample.append(v[i])
        i += 1
    md = [
        "# Spot-check: realistic Polish eval (pl_real)",
        "",
        (
            "Label = answer the teacher and Bielik-11B agreed on (teacher confidence ≥ 0.7). Mark each item OK or "
            "give the correct option in the CSV."
        ),
        "",
    ]
    with (WORK / "distill" / "spotcheck_pl_real.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "n",
                "id",
                "family",
                "question",
                "options",
                "label",
                "teacher_conf",
                "reviewer_ok",
                "reviewer_answer",
                "note",
            ]
        )
        for n, r in enumerate(sample, 1):
            opts = " | ".join(f"{chr(65 + k)}. {o}" for k, o in enumerate(r["options"]))
            label = f"{chr(65 + r['gold'])}. {r['options'][r['gold']]}"
            conf = max(r["target"])
            w.writerow([n, r["id"], r["family"], r["question"], opts, label, f"{conf:.2f}", "", "", ""])
            md += [
                f"## {n}. {r['family']}  (`{r['id']}`)",
                "",
                "> " + r["state"].replace("\n", "\n> "),
                "",
                f"**Pytanie:** {r['question']}",
                "",
            ]
            md += [
                f"- {chr(65 + k)}. {o}" + ("  ← **label**" if k == r["gold"] else "")
                for k, o in enumerate(r["options"])
            ]
            md += ["", f"teacher confidence {conf:.2f}", ""]
    (WORK / "distill" / "spotcheck_pl_real.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(sample)} items from {len(by_family)} families -> {WORK / 'distill' / 'spotcheck_pl_real.md'} (+ .csv)")


if __name__ == "__main__":
    main()
