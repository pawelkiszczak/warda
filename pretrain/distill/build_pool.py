#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Set
from pathlib import Path
from typing import Any

import numpy as np
from common import (
    BANK,
    LICENSES,
    ROOT,
    WORK,
    applicable,
    doc_hash,
    is_polish,
    load_prompt_tokenizer,
    log,
    make_question,
    write_jsonl,
)
from tokenizers import Tokenizer

sys.path.insert(0, str(ROOT))
from pretrain.prompt import render

TOKENS = ROOT / "pretrain" / "work" / "tokens"
TOKENIZER = ROOT / "pretrain" / "work" / "cache" / "apt4-tokenizer.json"


def decode_bin(path: Path, tokenizer: Tokenizer, source: str):
    ids = np.memmap(path, dtype=np.uint16, mode="r")
    current: list[int] = []
    chunk_size = 8_000_000
    for offset in range(0, len(ids), chunk_size):
        chunk = ids[offset : offset + chunk_size]
        special = np.flatnonzero((chunk == 1) | (chunk == 2))
        start = 0
        for position in special:
            token = int(chunk[position])
            if token == 1:
                current = []
            else:
                current.extend(map(int, chunk[start:position]))
                text = tokenizer.decode(current, skip_special_tokens=True).strip()
                current = []
                if len(text) >= 400:
                    yield source, text
            start = int(position) + 1
        current.extend(map(int, chunk[start:]))
    if current:
        text = tokenizer.decode(current, skip_special_tokens=True).strip()
        if len(text) >= 400:
            yield source, text


def boundaries(text: str):
    # Divide long source documents only at paragraph/sentence boundaries.
    chunks = re.split(r"(?<=[.!?…])\s+|\n{1,}", text)
    acc = ""
    for raw_sentence in chunks:
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        if acc and len(acc) + len(sentence) + 1 > 1500:
            if len(acc) >= 400:
                yield acc
            acc = ""
        if len(sentence) > 1500:
            for start in range(0, len(sentence), 1200):
                part = sentence[start : start + 1200]
                if len(part) >= 400:
                    if acc and len(acc) >= 400:
                        yield acc
                    acc = part
            continue
        acc = f"{acc} {sentence}".strip()
    if len(acc) >= 400:
        yield acc


def passage_rows(split: str, limit: int | None, tokenizer: Tokenizer):
    if split == "train":
        paths = [TOKENS / "train.bin"]
        source_names = ["pretrain_train_mixed"]
    else:
        paths = sorted(TOKENS.glob("val_*.bin"))
        source_names = [p.name.removeprefix("val_").removesuffix(".bin") for p in paths]
    seen, count = set(), 0
    for path, source in zip(paths, source_names, strict=False):
        if source == "fineweb-edu":
            continue
        for _, doc in decode_bin(path, tokenizer, source):
            if not is_polish(doc):
                continue
            digest = doc_hash(doc)
            if digest in seen:
                continue
            seen.add(digest)
            for passage in boundaries(doc):
                if not is_polish(passage):
                    continue
                yield source, digest, passage
                count += 1
                if limit and count >= limit:
                    return


def choose_families(families, digest, weights):
    """2-4 question families per passage. Unweighted: a deterministic rotation; weighted (round 2): a deterministic
    weighted draw without replacement, so families where the student lags the teacher get more items."""
    count = min(2 + (int(digest[8:10], 16) % 3), len(families))
    if not weights:
        offset = int(digest[:8], 16) % len(families)
        return [families[(offset + i) % len(families)] for i in range(count)]
    rng, pool, chosen = random.Random(int(digest[:16], 16)), list(families), []
    for _ in range(count):
        pick = rng.choices(pool, weights=[weights.get(f, 1.0) for f in pool])[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def build_items(
    split: str,
    target: int,
    limit: int | None,
    tokenizer: Tokenizer,
    prompt_tok: Any,
    exclude: Set[str] = frozenset(),
    weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    pool: list[dict[str, Any]] = []
    fam_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    doc_seen: set[str] = set()
    for source, digest, passage in passage_rows(split, None, tokenizer):
        if digest in doc_seen or digest in exclude:
            continue
        doc_seen.add(digest)
        families = [name for name, *_ in BANK if applicable(name, source, passage)]
        chosen = choose_families(families, digest, weights)
        if split == "eval" and source_counts[source] + len(chosen) > target * 0.2:
            continue
        for j, family in enumerate(chosen):
            if len(pool) >= target:
                return pool, fam_counts, source_counts
            variant = int(digest[10:12], 16) % 3
            question, typ, options = make_question(family, variant, passage)
            item_id = f"{split}-{digest[:16]}-{j}"
            rendered = render(prompt_tok, passage, question, options, lang="pl")
            prompt_length = len(prompt_tok.encode(rendered, add_special_tokens=False))
            if prompt_length > 1536:
                continue
            pool.append(
                {
                    "id": item_id,
                    "state": passage,
                    "question": question,
                    "options": options,
                    "type": typ,
                    "family": f"distill/{family}",
                    "template_id": f"{family}/{variant}",
                    "case_id": digest,
                    "language": "pl",
                    "split": split,
                    "label_method": "distilled",
                    "source": source,
                    "license": LICENSES.get(source, "unknown"),
                }
            )
            fam_counts[family] += 1
            source_counts[source] += 1
    return pool, fam_counts, source_counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="maximum items in each pool")
    parser.add_argument("--train-items", type=int, default=60000)
    parser.add_argument("--eval-items", type=int, default=2500)
    parser.add_argument("--splits", default="train,eval", help="comma-separated subset of train,eval")
    parser.add_argument(
        "--exclude",
        type=Path,
        nargs="*",
        default=[],
        help="JSONL files whose case_ids (passage documents) must not be reused",
    )
    parser.add_argument("--family-weights", type=Path, help="JSON {family: weight} for the weighted family draw")
    parser.add_argument("--output-prefix", default="pool", help="writes <prefix>_<split>.jsonl under work/distill")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if not TOKENIZER.exists():
        raise FileNotFoundError(f"APT4 tokenizer not found: {TOKENIZER}")
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    prompt_tok = load_prompt_tokenizer()
    exclude: set[str] = set()
    for path in args.exclude:
        with path.open(encoding="utf-8") as f:
            exclude.update(json.loads(line)["case_id"] for line in f if line.strip())
    weights = json.loads(args.family_weights.read_text()) if args.family_weights else None
    val_hashes: set[str] = set()
    # Ensure train passages are not drawn from held-out validation documents.
    for path in sorted(TOKENS.glob("val_*.bin")):
        val_hashes.update(doc_hash(text) for _, text in decode_bin(path, tokenizer, path.stem))
    targets = {"train": args.limit or args.train_items, "eval": args.limit or args.eval_items}
    for split in args.splits.split(","):
        rows, families, sources = build_items(
            split,
            targets[split],
            args.limit,
            tokenizer,
            prompt_tok,
            exclude,
            weights and {k.removeprefix("distill/"): v for k, v in weights.items()},
        )
        if split == "train":
            rows = [row for row in rows if row["case_id"] not in val_hashes]
        dest = WORK / f"{args.output_prefix}_{split}.jsonl"
        write_jsonl(dest, rows)
        types = Counter(row["type"] for row in rows)
        lengths: Counter[int] = Counter()
        for row in rows:
            rendered = render(prompt_tok, row["state"], row["question"], row["options"], lang="pl")
            length = len(prompt_tok.encode(rendered, add_special_tokens=False))
            lengths[min(1536, length // 128 * 128)] += 1
        log(
            f"{split}: {len(rows):,} items -> {dest}; excluded docs={len(exclude):,}; weights={'yes' if weights else 'no'}; sources={dict(sources)}; families={dict(families)}; types={dict(types)}; prompt_length_bins={dict(sorted(lengths.items()))}"
        )


if __name__ == "__main__":
    main()
