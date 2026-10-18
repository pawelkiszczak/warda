#!/usr/bin/env python3
"""Reservoir-sample raw Polish and English controls into work/quality/items.jsonl.
Run: pretrain/.venv/bin/python pretrain/quality/sample.py [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import zlib
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
from pretrain.data import build_tokens

OUT = ROOT / "work" / "quality"
LIMIT = 5_000
FEATURE_NAMES = [
    "words",
    "chars",
    "lines",
    "paragraphs",
    "sentences",
    "stopword_ratio",
    "diacritics_per_char",
    "diacritics_per_word",
    "short_line_ratio",
    "duplicate_line_ratio",
    "punctuation_per_word",
    "uppercase_per_char",
    "punctuation_per_sentence",
    "words_per_sentence",
    "words_per_paragraph",
    "hapax_ratio",
    "repeated_trigram_ratio",
    "oov_ratio",
    "alphabetic_or_space_per_char",
    "blank_line_ratio",
    "single_char_word_ratio",
    "lowercase_per_char",
    "colon_per_sentence",
    "comma_per_sentence",
    "type_token_ratio",
    "digits_per_char",
    "markup_per_char",
    "longest_line_ratio",
    "mean_line_length",
    "std_line_length",
    "polish_function_word_ratio",
    "asterisk_per_char",
    "hash_per_char",
    "underscore_per_char",
    "hyphen_per_char",
    "semicolon_per_sentence",
    "long_word_ratio",
    "short_word_ratio",
    "unique_line_ratio",
    "question_per_sentence",
    "exclamation_per_sentence",
    "uppercase_per_alpha",
    "alphabetic_or_space_ratio",
]


def read_zstd(path: Path):
    import io

    import zstandard

    with (
        path.open("rb") as compressed,
        io.TextIOWrapper(
            zstandard.ZstdDecompressor().stream_reader(compressed), encoding="utf-8", errors="replace"
        ) as stream,
    ):
        for line in stream:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    yield row
            except json.JSONDecodeError:
                continue


def capped_text(text: str) -> tuple[str, bool, int]:
    original = len(text)
    if original <= LIMIT:
        return text, False, original
    prefix = text[:LIMIT]
    end = prefix.rfind("\n\n")
    if end < 200:
        matches = list(re.finditer(r"[.!?](?:[\"'»)]*)?(?=\s|$)", prefix))
        end = matches[-1].end() if matches else LIMIT
        if end < 200:
            end = LIMIT
    return prefix[:end].rstrip(), True, original


def signals(text: str) -> tuple[bool, bool, float, float]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    dup = sum(n for n in Counter(lines).values() if n > 1) / max(1, len(lines))
    ratio = len(zlib.compress(text.encode("utf-8"), 6)) / max(1, len(text.encode("utf-8")))
    repetitive = dup > 0.08 or ratio < 0.18 or ratio > 0.95
    alpha = [c for c in text if c.isalpha()]
    foreign = sum(c in "ąćęłńóśźż" for c in text.lower()) / max(1, len(alpha)) < 0.008 or any(
        ord(c) > 0x024F for c in alpha
    )
    return repetitive, foreign, dup, ratio


def reservoir_add(bucket: list, row: dict, seen: Counter, capacity: int, rng: random.Random):
    seen[row["_bucket"]] += 1
    n = seen[row["_bucket"]]
    if len(bucket) < capacity:
        bucket.append(row)
    else:
        j = rng.randrange(n)
        if j < capacity:
            bucket[j] = row


def reserve_hard_cases(rows: list[dict], repeat_slots: int, mixed_slots: int, rng: random.Random) -> list[dict]:
    chosen = []
    chosen_ids = set()
    repetitive = [row for row in rows if row["_heuristic"]]
    mixed = [row for row in rows if row["_foreign"]]
    rng.shuffle(repetitive)
    rng.shuffle(mixed)
    for row in repetitive[:repeat_slots]:
        chosen.append(row)
        chosen_ids.add(row["id"])
    mixed_selected = sum(row["_foreign"] for row in chosen)
    for row in mixed:
        if mixed_selected >= mixed_slots:
            break
        if row["id"] not in chosen_ids:
            chosen.append(row)
            chosen_ids.add(row["id"])
            mixed_selected += 1
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    started = datetime.now(UTC)
    rng = random.Random(args.seed)
    source_root = ROOT / "work" / "raw"
    input_paths = (
        sorted((source_root / "speakleash").glob("*.jsonl.zst"))
        + sorted((source_root / "hf" / "fineweb-2").glob("*.parquet"))
        + sorted((source_root / "hf" / "fineweb-edu").glob("*.parquet"))
    )
    if not input_paths:
        raise SystemExit(f"No raw input files under {source_root}")
    # Keep independent bounded reservoirs for each sampling stratum.
    buckets: dict[str, list[dict]] = defaultdict(list)
    seen: Counter = Counter()
    cap = 1_000

    def add(row: dict, key: str):
        row["_bucket"] = key
        reservoir_add(buckets[key], row, seen, cap, rng)

    for path in input_paths:
        print(f"Scanning {path}", flush=True)
        if path.suffix == ".zst":
            source = path.name.removesuffix(".jsonl.zst")
            manifest_path = path.with_suffix("").with_suffix(".manifest")
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            license_name = str(manifest.get("license", "unknown"))
            for index, raw in enumerate(read_zstd(path)):
                text = raw.get("text")
                if not isinstance(text, str) or len(text) < 200:
                    continue
                meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
                label = str(meta.get("quality", "UNKNOWN")).upper()
                if label not in {"HIGH", "MEDIUM", "LOW"}:
                    label = "UNKNOWN"
                repetitive, mixed, dup, ratio = signals(text)
                strata = {"sl_quality": label}
                if repetitive:
                    strata["hard_case_repetitive"] = "true"
                if mixed:
                    strata["hard_case_mixed_script"] = "true"

                text, truncated, orig_chars = capped_text(text)
                add(
                    {
                        "id": f"sl:{source}:{index}",
                        "origin": "speakleash",
                        "source": source,
                        "url": raw.get("url") or meta.get("url"),
                        "license": license_name,
                        "text": text,
                        "truncated": truncated,
                        "orig_chars": orig_chars,
                        "strata": strata,
                        "source_meta": meta,
                        "_heuristic": repetitive,
                        "_foreign": mixed,
                        "_dup": dup,
                        "_ratio": ratio,
                    },
                    f"sl:{source}:{label}:{'rep' if repetitive else 'normal'}:{'foreign' if mixed else 'local'}",
                )
        else:
            import pyarrow.parquet as pq

            origin = "fineweb-edu" if "fineweb-edu" in str(path) else "fineweb-2"
            source = origin
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=4096):
                cols = batch.to_pydict()
                for j, text in enumerate(cols.get("text", [])):
                    if not isinstance(text, str) or len(text) < 200:
                        continue
                    raw_meta = {k: vals[j] for k, vals in cols.items() if k != "text"}
                    repetitive, mixed, dup, ratio = signals(text)
                    strata = {}
                    if origin == "fineweb-2":
                        score = raw_meta.get("language_score")
                        band = (
                            "lt_0.9"
                            if score is not None and score < 0.9
                            else "0.9_0.98"
                            if score is not None and score <= 0.98
                            else "gt_0.98"
                        )
                        cluster = "singleton" if raw_meta.get("minhash_cluster_size") == 1 else "clustered"
                        strata.update(language_score=band, minhash_cluster_size=cluster)
                        key = f"fw2:{band}:{cluster}:{'rep' if repetitive else 'normal'}:{'foreign' if mixed else 'local'}"
                    else:
                        strata["control"] = "wrong_language"
                        key = f"fwe:{'rep' if repetitive else 'normal'}:{'foreign' if mixed else 'local'}"
                    if repetitive:
                        strata["hard_case_repetitive"] = "true"
                    if mixed:
                        strata["hard_case_mixed_script"] = "true"
                    capped, truncated, orig_chars = capped_text(text)
                    rowid = raw_meta.get("id") or f"{path.stem}:{seen['rows']}"
                    seen["rows"] += 1
                    add(
                        {
                            "id": f"{origin}:{rowid}",
                            "origin": origin,
                            "source": source,
                            "url": raw_meta.get("url"),
                            "license": "unknown",
                            "text": capped,
                            "truncated": truncated,
                            "orig_chars": orig_chars,
                            "strata": strata,
                            "source_meta": raw_meta,
                            "_heuristic": repetitive,
                            "_foreign": mixed,
                            "_dup": dup,
                            "_ratio": ratio,
                        },
                        key,
                    )

    # Reserve a small hard-case slice, then sample only non-hard rows until the target is reached.
    selected: list[dict] = []
    targets = {"speakleash": 600, "fineweb-2": 330, "fineweb-edu": 50}
    source_names = sorted({x["source"] for values in buckets.values() for x in values})
    sl_sources = [x for x in source_names if x not in {"fineweb-2", "fineweb-edu"}]
    for source in sl_sources:
        source_rows = [r for k, values in buckets.items() if k.startswith(f"sl:{source}:") for r in values]
        quota = min(60, max(1, round(targets["speakleash"] / max(1, len(sl_sources)))))
        rng.shuffle(source_rows)
        chosen = reserve_hard_cases(source_rows, round(quota * 0.10), round(quota * 0.05), rng)
        chosen_ids = {r["id"] for r in chosen}
        special = [r for r in source_rows if r["_heuristic"] or r["_foreign"]]
        normal = [r for r in source_rows if not (r["_heuristic"] or r["_foreign"])]
        label_slots = quota - len(chosen)
        for label in ("HIGH", "MEDIUM", "LOW"):
            part = [r for r in normal if r["strata"].get("sl_quality") == label and r["id"] not in chosen_ids]
            rng.shuffle(part)
            label_quota = round(label_slots * {"HIGH": 0.4, "MEDIUM": 0.3, "LOW": 0.3}[label])
            for row in part[:label_quota]:
                chosen.append(row)
                chosen_ids.add(row["id"])
        for group in (normal, special):
            for row in group:
                if len(chosen) >= quota:
                    break
                if row["id"] not in chosen_ids:
                    chosen.append(row)
                    chosen_ids.add(row["id"])
        selected.extend(chosen[:quota])
    for origin in ("fineweb-2", "fineweb-edu"):
        rows = [
            r
            for k, values in buckets.items()
            if k.startswith("fw2:" if origin == "fineweb-2" else "fwe:")
            for r in values
        ]
        quota = targets[origin]
        chosen = reserve_hard_cases(rows, round(quota * 0.10), round(quota * 0.05), rng)
        chosen_ids = {r["id"] for r in chosen}
        special = [r for r in rows if r["_heuristic"] or r["_foreign"]]
        remaining = [r for r in rows if r["id"] not in chosen_ids and not (r["_heuristic"] or r["_foreign"])]
        # Round-robin across FineWeb strata ensures score/cluster coverage.
        grouped = defaultdict(list)
        for r in remaining:
            grouped[tuple(sorted(r["strata"].items()))].append(r)
        for group in grouped.values():
            rng.shuffle(group)
        keys = list(grouped)
        rng.shuffle(keys)
        while len(chosen) < quota and any(grouped.values()):
            for stratum_key in keys:
                if grouped[stratum_key] and len(chosen) < quota:
                    chosen.append(grouped[stratum_key].pop())
        if len(chosen) < quota:
            fallback = [r for r in special if r["id"] not in chosen_ids]
            chosen.extend(fallback[: quota - len(chosen)])
        selected.extend(chosen)

    # The target is approximate when a source/stratum has insufficient eligible documents.
    vocab = set()
    for r in selected:
        vocab.update(re.findall(r"[^\W\d_]{3,}", r["text"].lower(), re.UNICODE))
    if not vocab:
        raise RuntimeError("No eligible documents found in raw files")
    output = []
    clean_reasons: Counter[str] = Counter()
    for row in selected:
        raw_text = row["text"]
        clean = build_tokens.clean(raw_text)
        reason = None
        if clean is None:
            if raw_text.count("\ufffd") / max(1, len(raw_text)) > 0.001:
                reason = "replacement_character_ratio"
            elif (
                len(raw_text.splitlines()) > 4
                and sum(n for n in Counter(x for x in raw_text.splitlines() if x.strip()).values() if n > 1)
                / max(1, len(raw_text.splitlines()))
                > 0.35
            ):
                reason = "duplicate_line_ratio"
            elif (
                len(re.findall(r"\w+", raw_text.lower())) > 80
                and len(
                    set(
                        zip(
                            re.findall(r"\w+", raw_text.lower()),
                            re.findall(r"\w+", raw_text.lower())[1:],
                            re.findall(r"\w+", raw_text.lower())[2:],
                            strict=False,
                        )
                    )
                )
                < 8
            ):
                reason = "repeated_trigrams"
            else:
                reason = "content_length"
        cheap = dict(zip(FEATURE_NAMES, map(float, build_tokens.features(raw_text, vocab)), strict=False))
        clean_reason = "ok" if clean is not None else (reason or "content_length")
        clean_reasons[clean_reason] += 1
        for key in ("_heuristic", "_foreign", "_dup", "_ratio", "_bucket"):
            row.pop(key, None)
        row.update(pipeline={"clean_ok": clean is not None, "clean_reason": clean_reason}, features={"cheap": cheap})
        output.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    items = OUT / "items.jsonl"
    tmp = items.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        for row in output:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(items)
    for derived in (OUT / "stylometrix.jsonl", OUT / "features.parquet"):
        derived.unlink(missing_ok=True)
    file_hashes = {str(p.relative_to(ROOT)): build_tokens.file_sha256(p) for p in input_paths}
    counts = {
        "origin": dict(Counter(r["origin"] for r in output)),
        "source": dict(Counter(r["source"] for r in output)),
        "strata": dict(Counter(f"{r['origin']}:{k}={v}" for r in output for k, v in r["strata"].items())),
    }
    manifest = {
        "seed": args.seed,
        "created_at": started.isoformat(),
        "inputs": file_hashes,
        "counts": counts,
        "clean_ok": sum(r["pipeline"]["clean_ok"] for r in output),
        "total": len(output),
    }
    (OUT / "sample_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({"sampled": len(output), "counts": counts, "clean": dict(clean_reasons)}, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
