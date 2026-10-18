"""Build fine-tuning mixtures from the Polish decision data, the Jev-style stage-1 data and the distilled Polish data.

- `work/sft_jev/stage2/`: Polish train + replayed stage-1 rows making up `--replay` (default 30%) of the mixture.
  dev/cal/test are the Polish splits.
- `work/sft_jev/joint/`: all stage-1 train rows + Polish train ×`--polish-copies` (default 3).
- `work/sft_jev/joint-v2/` (only when `work/distill/teacher_train.jsonl` exists): stage-1 rows + Polish train
  ×`--v2-polish-copies` (default 5) + teacher-distilled Polish real-text items ×`--distill-copies` (default 2), with
  the distilled yes/no majority class subsampled to ≤60% (the converted-data class-balance rule).
- `work/sft_jev/joint-v3/` (when `work/distill/teacher_round2.jsonl` also exists): joint-v2 recipe over both teacher
  rounds, Open-Jev + kaivoss rows doubled, and 4% of distilled passages held out into dev/cal.
- `work/sft_jev/joint-v4/`: joint-v3 with Polish train ×`--v4-polish-copies` (default 8) and the distilled yes/no
  majority capped at `--v4-noul-share` (default 55%), to recover the synthetic Polish families v3 diluted.

joint and joint-v2 use dev/cal = Polish + stage-1 (Jev-style) dev/cal, so epoch selection and per-language
temperatures see both languages; test is always the Polish test.

    uv run python pretrain/sft/mix_stages.py
"""

import argparse
import json
import random
import shutil
from pathlib import Path

WORK = Path(__file__).resolve().parents[1] / "work"


def read(path):
    return [line for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copies(lines, n):
    """n copies with unique ids (ids stay distinct across the mixture and in any downstream eval)."""
    if n == 1:
        return list(lines)
    return [
        json.dumps({**json.loads(line), "id": f"{json.loads(line)['id']}#copy{c}"}, ensure_ascii=False)
        for c in range(n)
        for line in lines
    ]


def balance_noul(lines, rng, max_share=0.6):
    """Class-balance rule for converted data: no yes/no class above 60%. Teacher labels on real text are ~88% "nie"
    (most passages contain no ads, personal data, …), so the majority class is subsampled; other types are kept."""
    rows = [json.loads(line) for line in lines]
    noul = [r for r in rows if r["type"] == "noul"]
    by_gold = {g: [r for r in noul if r["gold"] == g] for g in (0, 1)}
    minority = min(by_gold.values(), key=len)
    majority = max(by_gold.values(), key=len)
    keep_major = min(len(majority), int(len(minority) * max_share / (1 - max_share)))
    kept = {id(r) for r in minority + rng.sample(majority, keep_major)}
    return [line for line, r in zip(lines, rows, strict=False) if r["type"] != "noul" or id(r) in kept]


def held_bucket(line):
    """Deterministic passage-level hold-out: 2% of passages → dev, 2% → cal (same passage never in two splits)."""
    b = int(json.loads(line)["case_id"][:8], 16) % 100
    return "dev" if b < 2 else "cal" if b < 4 else None


def joint_v3(stage1, polish, distilled, both, polish_copies, distill_copies, noul_share, rng):
    """v2 recipe on both teacher rounds, with 4% of distilled passages held out as real-text dev/cal rows (so
    temperatures and thresholds see the real-text distribution) and Open-Jev + kaivoss rows doubled (v2 lost 5 points
    on kaivoss)."""
    train = [line for line in distilled if held_bucket(line) is None]
    held = {s: both[s] + [line for line in distilled if held_bucket(line) == s] for s in ("dev", "cal")}
    boost = [
        json.dumps({**json.loads(line), "id": json.loads(line)["id"] + "#boost"}, ensure_ascii=False)
        for line in stage1
        if json.loads(line)["family"].split("/")[0] in ("openjev", "kaivoss")
    ]
    rows = stage1 + boost + copies(polish, polish_copies) + copies(balance_noul(train, rng, noul_share), distill_copies)
    return rows, held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", type=float, default=0.3, help="share of stage-1 rows in the stage-2 mixture")
    ap.add_argument("--polish-copies", type=int, default=3)
    ap.add_argument("--v2-polish-copies", type=int, default=5)
    ap.add_argument("--distill-copies", type=int, default=2)
    ap.add_argument("--v4-polish-copies", type=int, default=8)
    ap.add_argument("--v4-noul-share", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    polish = read(WORK / "sft" / "train.jsonl")
    stage1 = read(WORK / "sft_jev" / "stage1" / "train.jsonl")
    both = {
        s: read(WORK / "sft" / f"{s}.jsonl") + read(WORK / "sft_jev" / "stage1" / f"{s}.jsonl") for s in ("dev", "cal")
    }
    polish_only = {s: read(WORK / "sft" / f"{s}.jsonl") for s in ("dev", "cal")}
    n_replay = round(len(polish) * a.replay / (1 - a.replay))
    mixes = {
        "stage2": (polish + rng.sample(stage1, n_replay), polish_only),
        "joint": (stage1 + copies(polish, a.polish_copies), both),
    }
    distilled = WORK / "distill" / "teacher_train.jsonl"
    if distilled.exists():
        distill = balance_noul(read(distilled), rng)
        mixes["joint-v2"] = (stage1 + copies(polish, a.v2_polish_copies) + copies(distill, a.distill_copies), both)
    round2 = WORK / "distill" / "teacher_round2.jsonl"
    if distilled.exists() and round2.exists():
        mixes["joint-v3"] = joint_v3(
            stage1, polish, read(distilled) + read(round2), both, a.v2_polish_copies, a.distill_copies, 0.6, rng
        )
        # own RNG so adding v4 leaves the earlier mixtures' sampling and shuffles unchanged
        mixes["joint-v4"] = joint_v3(
            stage1,
            polish,
            read(distilled) + read(round2),
            both,
            a.v4_polish_copies,
            a.distill_copies,
            a.v4_noul_share,
            random.Random(a.seed + 4),
        )
    for name, (rows, held) in mixes.items():
        rng.shuffle(rows)
        out = WORK / "sft_jev" / name
        write(out / "train.jsonl", rows)
        for split, lines in held.items():
            write(out / f"{split}.jsonl", lines)
        shutil.copyfile(WORK / "sft" / "test.jsonl", out / "test.jsonl")
        print(name, len(rows), "train rows,", {s: len(v) for s, v in held.items()})


if __name__ == "__main__":
    main()
