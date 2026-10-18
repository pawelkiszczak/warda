#!/usr/bin/env python3
"""Convert public Jev-style typed decisions to Warda's typed-decision JSONL contract."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pretrain.prompt import render

OUT = ROOT / "pretrain/work/sft_jev"
TOKENIZER_ID = "speakleash/Bielik-1.5B-v3.0-Instruct"
SEED = 211
TASKSOURCE = "tasksource/tasksource-jev-typed-decisions"
OPENJEV = "ZefanCai/Open-Jev-v1.1"
SYSTEM_ONE = "kaivoss/system-one-270m-data"
SARGEDEV = "SargeDev/jev-distill-corpus-v3"
FIELDS = (
    "id",
    "state",
    "question",
    "options",
    "gold",
    "target",
    "type",
    "family",
    "template_id",
    "case_id",
    "language",
    "split",
    "label_method",
    "source",
    "license",
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value).strip()
    )


def language(state: str, source: str = "") -> str:
    parts = re.split(r"[/_.-]", source.lower())
    codes = {
        "pl": "pl",
        "pol": "pl",
        "en": "en",
        "eng": "en",
        "zh": "zh",
        "zho": "zh",
        "chi": "zh",
        "ru": "ru",
        "rus": "ru",
        "ar": "ar",
        "ara": "ar",
        "arq": "ar",
        "ary": "ar",
        "de": "de",
        "deu": "de",
        "ger": "de",
        "fr": "fr",
        "fra": "fr",
        "fre": "fr",
        "es": "es",
        "spa": "es",
        "it": "it",
        "ita": "it",
        "pt": "pt",
        "por": "pt",
        "nl": "nl",
        "nld": "nl",
        "dut": "nl",
        "sv": "sv",
        "swe": "sv",
        "fi": "fi",
        "fin": "fi",
        "ja": "ja",
        "jpn": "ja",
        "ko": "ko",
        "kor": "ko",
        "vi": "vi",
        "vie": "vi",
        "yor": "yo",
        "da": "da",
        "el": "el",
        "gr": "el",
        "et": "et",
        "ht": "ht",
        "my": "my",
        "hi": "hi",
        "id": "id",
        "kn": "kn",
        "ml": "ml",
        "ta": "ta",
        "bn": "bn",
        "pa": "pa",
        "ur": "ur",
        "th": "th",
        "ms": "ms",
        "sw": "sw",
        "cs": "cs",
        "ro": "ro",
        "hu": "hu",
        "he": "he",
        "ace": "ace",
        "bbc": "bbc",
    }
    if parts and parts[-1] in codes:
        return codes[parts[-1]]
    if "multilingual" in parts:
        for part in reversed(parts):
            if part in codes:
                return codes[part]
    if re.search(r"[ąćęłńśźżĄĆĘŁŃŚŹŻ]", state):
        return "pl"
    if re.search(r"[\u4e00-\u9fff]", state):
        return "zh"
    if re.search(r"[\u0400-\u04ff]", state):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", state):
        return "ar"
    tokens = set(re.findall(r"\w+", state.casefold()))
    polish_clues = {
        "się",
        "jest",
        "są",
        "być",
        "który",
        "która",
        "które",
        "oraz",
        "może",
        "czy",
        "jaki",
        "jaka",
        "jakie",
        "należy",
        "został",
        "została",
        "odpowiedź",
    }
    if len(tokens & polish_clues) >= 2:
        return "pl"
    return "en"


def redistributable(use: str, license_name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", license_name.lower()))
    forbidden = {"nc", "nd", "unknown", "unspecified", "none", "unlicensed", "noassertion"}
    return (
        use.lower() == "commercial"
        and not tokens.intersection(forbidden)
        and not ("no" in tokens and "redistribution" in tokens)
    )


def row_id(source: str, upstream_id: str) -> str:
    return digest(source + "\0" + upstream_id)[:24]


def item(
    source_name,
    upstream_id,
    state,
    question,
    options,
    target,
    kind,
    case,
    lang,
    split,
    label_method,
    upstream_source,
    lic,
    template=None,
):
    state, question = text(state), text(question)
    opts = [text(x) for x in options]
    values = [float(x) for x in target]
    if kind == "noul":
        # Target order follows each source's own convention: Tasksource ships [P(yes)]; Open-Jev and kaivoss ship
        # [P(no), P(yes)]. kaivoss verified 2026-10-18 against kaivoss/system-one-270m-data train.jsonl: all 8,341
        # noul rows list option A as "no" and B as "yes", the card defines `target` as a distribution over the
        # prompt's own options, and the `label` field agrees on 8,329 rows (the other 12 are exact 0.5/0.5 ties),
        # so element 1 is P(yes).
        p_yes = values[1] if len(values) == 2 else values[0]
        opts = ["tak", "nie"] if lang == "pl" else ["yes", "no"]
        values = [p_yes, 1.0 - p_yes]
    if len(values) != len(opts) or not values or any(not math.isfinite(x) or x < 0 for x in values):
        return None
    total = sum(values)
    if total <= 0:
        return None
    values = [x / total for x in values]
    gold = max(range(len(values)), key=values.__getitem__)
    if kind == "score":
        try:
            order = sorted(range(len(opts)), key=lambda i: float(opts[i]))
            opts = [opts[i] for i in order]
            values = [values[i] for i in order]
            gold = max(range(len(values)), key=values.__getitem__)
        except ValueError:
            pass
    family = source_name + "/" + str(upstream_source)
    return {
        "id": row_id(source_name, str(upstream_id)),
        "state": state,
        "question": question,
        "options": opts,
        "gold": gold,
        "target": values,
        "type": kind,
        "family": family,
        "template_id": str(template or source_name),
        "case_id": str(case or upstream_id),
        "language": lang,
        "split": split,
        "label_method": label_method,
        "source": str(upstream_source),
        "license": str(lic),
    }


def validate(rows: list[dict[str, Any]], tokenizer: Any) -> tuple[list[dict[str, Any]], Counter[str]]:
    seen_ids: set[str] = set()
    valid: list[dict[str, Any]] = []
    drops: Counter[str] = Counter()

    for row in rows:
        if set(row) != set(FIELDS):
            raise ValueError(f"schema keys differ for {row.get('id')}")
        opts, target = row["options"], row["target"]
        if not isinstance(row["state"], str) or not isinstance(row["question"], str):
            raise ValueError(f"non-string state or question: {row.get('id')}")
        if not row["state"].strip() or not row["question"].strip():
            drops["empty_text"] += 1
            continue
        string_fields = (
            "id",
            "family",
            "template_id",
            "case_id",
            "language",
            "split",
            "label_method",
            "source",
            "license",
        )
        if any(not isinstance(row[k], str) or not row[k].strip() for k in string_fields):
            raise ValueError(f"invalid metadata string field: {row.get('id')}")
        if not re.fullmatch(r"[a-z]{2,3}", row["language"]):
            raise ValueError(f"invalid ISO language code: {row['id']}")
        if (
            not isinstance(opts, list)
            or not 2 <= len(opts) <= 10
            or any(not isinstance(x, str) or not x.strip() for x in opts)
            or len(set(opts)) != len(opts)
        ):
            drops["invalid_options"] += 1
            continue
        if (
            not isinstance(target, list)
            or len(target) != len(opts)
            or any(not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in target)
            or abs(sum(target) - 1) > 1e-6
        ):
            drops["invalid_target"] += 1
            continue
        if (
            type(row["gold"]) is not int
            or not 0 <= row["gold"] < len(opts)
            or row["gold"] != max(range(len(target)), key=target.__getitem__)
        ):
            raise ValueError(f"gold does not match target: {row['id']}")
        if row["type"] == "noul" and (
            len(opts) != 2 or opts != (["tak", "nie"] if row["language"] == "pl" else ["yes", "no"])
        ):
            raise ValueError(f"invalid noul options: {row['id']}")
        if row["type"] not in ("choice", "noul", "score"):
            drops["unsupported_type"] += 1
            continue
        if row["split"] not in ("train", "dev", "cal", "test"):
            raise ValueError(f"invalid split: {row['id']}")
        if row["label_method"] not in ("public", "synthetic", "distilled"):
            raise ValueError(f"invalid label method: {row['id']}")
        if row["id"] in seen_ids:
            raise ValueError(f"duplicate id: {row['id']}")
        seen_ids.add(row["id"])
        prompt = render(tokenizer, row["state"], row["question"], opts, lang="pl" if row["language"] == "pl" else "en")
        if len(tokenizer(prompt, add_special_tokens=False).input_ids) > 1536:
            drops["over_1536_tokens"] += 1
            continue
        valid.append(row)
    return valid, drops


def rows_from_parquet(repo: str, filenames: list[str]) -> Iterator[dict[str, Any]]:
    for filename in filenames:
        path = hf_hub_download(repo, filename, repo_type="dataset")
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=4096):
            yield from batch.to_pylist()


def subset_files(repo: str, prefix: str):
    return sorted(
        f for f in HfApi().list_repo_files(repo, repo_type="dataset") if f.startswith(prefix) and f.endswith(".parquet")
    )


def read_jsonl(repo, filename):
    path = hf_hub_download(repo, filename, repo_type="dataset")
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def stratified(rows, limit, seed=SEED):
    if len(rows) <= limit:
        return list(rows)
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row["family"], row["type"], len(row["options"]), row["language"])].append(row)
    rng = random.Random(seed)
    chosen = []
    for bucket in buckets.values():
        rng.shuffle(bucket)
    total = len(rows)
    allocations = {k: min(len(v), int(limit * len(v) / total)) for k, v in buckets.items()}
    remainder = limit - sum(allocations.values())
    for k in sorted(buckets, key=lambda k: (-(limit * len(buckets[k]) / total - allocations[k]), str(k))):
        n = min(remainder, len(buckets[k]) - allocations[k])
        allocations[k] += n
        remainder -= n
        if not remainder:
            break
    for k, bucket in buckets.items():
        chosen.extend(bucket[: allocations[k]])
    rng.shuffle(chosen)
    return chosen


def threegram_filter(rows: list[dict[str, Any]], protected_states: list[str]) -> tuple[list[dict[str, Any]], int]:
    # 13-word shingles; short states are exact-deduped only.
    blocked: set[tuple[str, ...]] = set()
    exact = {state.strip().casefold() for state in protected_states}
    for state in protected_states:
        words = re.findall(r"\w+", state.lower())
        blocked.update(tuple(words[i : i + 13]) for i in range(max(0, len(words) - 12)))
    kept, removed = [], 0
    for row in rows:
        words = re.findall(r"\w+", row["state"].lower())
        shingles = (tuple(words[i : i + 13]) for i in range(max(0, len(words) - 12)))
        if row["state"].strip().casefold() in exact or any(shingle in blocked for shingle in shingles):
            removed += 1
        else:
            kept.append(row)
    return kept, removed


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    stage_raw: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    ext_raw: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    manifest: dict[str, Any] = {
        "seed": SEED,
        "tokenizer": TOKENIZER_ID,
        "sources": {},
        "decisions": {},
        "mixture": {},
        "filters": {},
        "license_exclusions": {"by_use": {}, "by_license": {}, "by_source": {}},
        "sargedev": {
            "decision": "excluded",
            "reason": "The card explicitly says yuri_v3 labels were distilled from Jev 1.13 (TypeSafe) via OpenRouter; yuri_v1 is 32B-teacher distilled and openjev_v2 is CC0, but admitting the mixed corpus would retain TypeSafe API-derived rows, contrary to the admission rule.",
            "repo": SARGEDEV,
            "card_split_rows": {
                "train": 655806,
                "validation": 14111,
                "calibration": 13766,
                "test": 14261,
                "ood": 13058,
                "test_set_30k": 29955,
            },
        },
    }
    polish_test_rows = [
        json.loads(line)
        for line in (ROOT / "pretrain/work/sft/test.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    protected = [row["state"] for row in polish_test_rows]
    # Ground truth Polish evaluation text is protected against 13-gram overlap.
    # Tasksource default mix: only sources explicitly marked commercial are redistributed here.
    task_files = {
        split: subset_files(TASKSOURCE, f"data/{name}-")
        for split, name in (("train", "train"), ("dev", "validation"), ("test", "test"))
    }
    task_train: list[dict[str, Any]] = []
    task_eval: list[dict[str, Any]] = []
    raw_counts: Counter[str] = Counter()
    licenses: Counter[str] = Counter()
    for split, files in task_files.items():
        for source_row in rows_from_parquet(TASKSOURCE, files):
            raw_counts[split] += 1
            use, lic = (
                str(source_row.get("license_use", "unspecified")).lower(),
                str(source_row.get("license", "unknown")),
            )
            licenses[use] += 1
            if not redistributable(use, lic):
                exclusions = manifest["license_exclusions"]
                exclusions["by_use"][use] = exclusions["by_use"].get(use, 0) + 1
                exclusions["by_license"][lic] = exclusions["by_license"].get(lic, 0) + 1
                source = str(source_row.get("source", "unknown"))
                exclusions["by_source"][source] = exclusions["by_source"].get(source, 0) + 1
                continue
            opts = source_row.get("options") or []
            kind = str(source_row.get("kind", "choice"))
            tar = source_row.get("target") or []
            if kind == "noul" and len(tar) != 1:
                continue
            if kind != "noul" and len(opts) != len(tar):
                continue
            state = text(source_row.get("state"))
            lang = language(state + " " + text(source_row.get("question")), source_row.get("source", ""))
            splitname = {"train": "train", "dev": "dev", "test": "test"}[split]
            converted = item(
                "tasksource",
                source_row.get("id"),
                state,
                source_row.get("question"),
                opts,
                tar,
                kind,
                source_row.get("group_id"),
                lang,
                splitname,
                "synthetic" if str(source_row.get("source", "")).startswith("procedural") else "public",
                source_row.get("source"),
                lic,
                source_row.get("variant"),
            )
            if converted:
                (task_train if split == "train" else task_eval).append(converted)
    manifest["sources"]["tasksource"] = {
        "raw_rows": dict(raw_counts),
        "license_use_rows": dict(licenses),
        "candidate_rows": len(task_train) + len(task_eval),
    }
    # Cap each source family at 5% of target mixture. Take a deterministic stratified shuffle.
    groups = defaultdict(list)
    for row in task_train:
        groups[row["source"]].append(row)
    for group in groups.values():
        rng.shuffle(group)
    cap = 11_000
    task_capped = []
    for name in sorted(groups):
        task_capped.extend(groups[name][:cap])
    raw_source_counts = Counter(row["source"] for row in task_train)
    # Cap aggregate tasksource pool to the requested 200-250k band while preserving source balance.
    polish_rows = [r for r in task_capped if r["language"] == "pl"]
    other_rows = [r for r in task_capped if r["language"] != "pl"]
    task_train = polish_rows + stratified(other_rows, max(0, 250_000 - len(polish_rows)))
    capped_source_counts = Counter(row["source"] for row in task_capped)
    selected_source_counts = Counter(row["source"] for row in task_train)
    manifest["sources"]["tasksource"]["per_source"] = {
        source: {
            "eligible_train": count,
            "after_11k_source_cap": capped_source_counts[source],
            "selected_train": selected_source_counts[source],
        }
        for source, count in sorted(raw_source_counts.items())
    }
    task_eval = [r for r in task_eval if r["split"] == "dev"]
    stage_raw["tasksource/train"] = task_train

    # Open-Jev v1.1 explicitly describes its redistributable projection and source-dependent CC0/CC-BY licenses.
    for upstream, outsplit in (
        ("train", "train"),
        ("validation", "dev"),
        ("calibration", "cal"),
        ("test", "test"),
        ("ood", "test"),
    ):
        files = subset_files(OPENJEV, f"data/community-hard-mix-v2-redistributable/{upstream}-")
        converted_rows = []
        for source_row in rows_from_parquet(OPENJEV, files):
            state = json.loads(source_row["state_json"])
            tar = source_row["target"]
            kind = source_row["kind"]
            # Dataset uses CC0 for generated records and CC-BY-4.0 for WANLI; source attribution is retained.
            source = source_row["source"]
            lic = (
                "CC-BY-4.0 (WANLI)"
                if "wanli" in source.lower()
                else "CC0-1.0 (Open-Jev generated); source-dependent projection"
            )
            method = "public" if "wanli" in source.lower() else "synthetic"
            converted = item(
                "openjev",
                source_row["id"],
                state,
                source_row["question"],
                source_row["options"],
                tar,
                kind,
                source_row["group_id"],
                language(text(state) + " " + source_row["question"], source),
                outsplit,
                method,
                source,
                lic,
                upstream,
            )
            if converted:
                converted_rows.append(converted)
        if outsplit == "train":
            stage_raw["openjev/train"].extend(converted_rows)
        elif outsplit in ("dev", "cal"):
            stage_raw[f"openjev/{outsplit}"].extend(converted_rows)
        else:
            ext_raw["openjev_test" if upstream == "test" else "openjev_ood"].extend(converted_rows)
        manifest["sources"].setdefault("openjev", {})[upstream] = {
            "raw_rows": len(converted_rows),
            "by_source": dict(Counter(r["source"] for r in converted_rows)),
            "license": "source-dependent CC0-1.0 / CC-BY-4.0; redistributable projection",
        }

    # System-One prompts contain an explicitly marked state/question/options block; split on state_id.
    system_rows = list(read_jsonl(SYSTEM_ONE, "train.jsonl"))
    state_split = {}
    rng.shuffle(system_rows)
    state_ids = sorted({r["state_id"] for r in system_rows})
    rng.shuffle(state_ids)
    n_test, n_dev, n_cal = int(len(state_ids) * 0.10), int(len(state_ids) * 0.05), int(len(state_ids) * 0.05)
    for i, sid in enumerate(state_ids):
        state_split[sid] = (
            "kaivoss_test"
            if i < n_test
            else "dev"
            if i < n_test + n_dev
            else "cal"
            if i < n_test + n_dev + n_cal
            else "train"
        )
    for index, r in enumerate(system_rows):
        prompt = r["prompt"]
        state_match = re.search(r"<state>\s*(.*?)\s*</state>", prompt, re.S)
        q_match = re.search(r"Question:\s*(.*?)\s*Options:\s*\n(.*)", prompt, re.S)
        option_lines = re.findall(r"(?m)^\s*[A-J]\.\s*(.+?)\s*$", prompt)
        if state_match and q_match:
            state, question = state_match.group(1).strip(), q_match.group(1).strip()
            options = re.findall(r"(?m)^\s*[A-J]\.\s*(.+?)\s*$", q_match.group(2))
        else:
            question_match = re.search(r"(?m)^Question:\s*(.+)$", prompt)
            state = prompt.strip()
            question = (
                question_match.group(1).strip() if question_match else "Choose the best answer from the listed options."
            )
            options = option_lines
        kind = r["qtype"]
        opts = ["yes", "no"] if kind == "noul" else options
        tar = r["target"]
        if kind == "noul" and len(tar) != 2:
            continue
        output_split = "test" if state_split[r["state_id"]] == "kaivoss_test" else state_split[r["state_id"]]
        converted = item(
            "kaivoss",
            str(index),
            state,
            question,
            opts,
            tar,
            kind,
            r["state_id"],
            "en",
            output_split,
            "synthetic",
            r["domain"],
            "Apache-2.0",
            r["qtype"],
        )
        if converted:
            if state_split[r["state_id"]] == "kaivoss_test":
                ext_raw["kaivoss_test"].append(converted)
            else:
                stage_raw[f"kaivoss/{state_split[r['state_id']]}"].append(converted)
    manifest["sources"]["kaivoss"] = {
        "raw_rows": len(system_rows),
        "state_count": len(state_ids),
        "state_split": dict(Counter(state_split.values())),
        "reconstruction": "Parsed <state>, Question and lettered Options blocks from prompt; fallback retains whole prompt as state.",
    }

    # Validate lengths first, then globally deduplicate states and enforce split priority/evaluation separation.
    for source_split, rows in list(stage_raw.items()):
        converted, dropped = validate(rows, tokenizer)
        manifest["filters"][source_split] = {"before": len(rows), "dropped": dict(dropped), "after": len(converted)}
        stage_raw[source_split] = converted
    train_rows = stage_raw["tasksource/train"] + stage_raw["openjev/train"] + stage_raw["kaivoss/train"]
    dev_rows = stage_raw["openjev/dev"] + stage_raw["kaivoss/dev"] + task_eval
    cal_rows = stage_raw["openjev/cal"] + stage_raw["kaivoss/cal"]
    # Sample own validation/calibration data to ~3k, then resolve cross-source exact state collisions.
    dev_before, cal_before = len(dev_rows), len(cal_rows)
    dev_rows = stratified(dev_rows, 3000)
    cal_rows = stratified(cal_rows, 3000)
    dev_rows, dev_drops = validate(dev_rows, tokenizer)
    cal_rows, cal_drops = validate(cal_rows, tokenizer)
    manifest["filters"]["dev_selection"] = {"before": dev_before, "after": len(dev_rows), "dropped": dict(dev_drops)}
    manifest["filters"]["cal_selection"] = {"before": cal_before, "after": len(cal_rows), "dropped": dict(cal_drops)}
    for name in list(ext_raw):
        ext_raw[name], removed = threegram_filter(ext_raw[name], protected)
        manifest["filters"][name + "_13gram"] = {"removed": removed}
    train_rows, ngram_removed = threegram_filter(train_rows, protected)
    manifest["filters"]["train_13gram"] = {"removed": ngram_removed}
    final_groups = [
        ("test", list(ext_raw["openjev_test"]) + list(ext_raw["openjev_ood"]) + list(ext_raw["kaivoss_test"])),
        ("cal", cal_rows),
        ("dev", dev_rows),
        ("train", train_rows),
    ]
    seen_states = {
        digest(r["state"].strip().casefold()): (("test", "polish_test"), "polish_test") for r in polish_test_rows
    }
    seen_cases = {r["case_id"]: ("test", "polish_test") for r in polish_test_rows}
    final: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    dedup_drops: Counter[str] = Counter()
    accepted: set[str] = set()
    for split, rows in final_groups:
        rng.shuffle(rows)
        for r in rows:
            state_key = digest(r["state"].strip().casefold())
            case_key = r["case_id"]
            dataset = r["family"].split("/", 1)[0]
            # Keep sibling questions together; exact states from another dataset never re-enter.
            partition = (split, r["template_id"] if split == "test" else "")
            if state_key in seen_states and seen_states[state_key] != (partition, dataset):
                dedup_drops["exact_state"] += 1
                continue
            if case_key in seen_cases and seen_cases[case_key] != partition:
                dedup_drops["cross_split_case"] += 1
                continue
            seen_states[state_key] = (partition, dataset)
            seen_cases[case_key] = partition
            if r["id"] in accepted:
                dedup_drops["duplicate_id"] += 1
                continue
            accepted.add(r["id"])
            final[split].append(r)
    manifest["filters"]["cross_dataset_dedup"] = dict(dedup_drops)
    accepted_ids = {r["id"] for r in final["test"]}
    # Preserve source split identity after resolving all test-family overlaps.
    for key in ("openjev_test", "openjev_ood", "kaivoss_test"):
        ext_raw[key] = stratified([r for r in ext_raw[key] if r["id"] in accepted_ids], 3000)
    # Populate tasksource test separately from upstream held-out split, without mixing it into Polish test.
    task_test = []
    for source_row in rows_from_parquet(TASKSOURCE, task_files["test"]):
        if not redistributable(str(source_row.get("license_use", "")), str(source_row.get("license", "unknown"))):
            continue
        opts, tar, kind = (
            source_row.get("options") or [],
            source_row.get("target") or [],
            source_row.get("kind", "choice"),
        )
        if kind == "noul" and len(tar) != 1:
            continue
        if kind != "noul" and len(tar) != len(opts):
            continue
        state = text(source_row.get("state"))
        source = source_row.get("source", "")
        converted = item(
            "tasksource",
            source_row.get("id"),
            state,
            source_row.get("question"),
            opts,
            tar,
            kind,
            source_row.get("group_id"),
            language(state + " " + text(source_row.get("question")), source),
            "test",
            "synthetic" if str(source).startswith("procedural") else "public",
            source,
            source_row.get("license", "unknown"),
            source_row.get("variant"),
        )
        if converted:
            task_test.append(converted)
    task_test, drop = validate(task_test, tokenizer)
    task_test, removed = threegram_filter(task_test, protected)
    ext_raw["tasksource_test"] = stratified(task_test, 3000)
    manifest["filters"]["tasksource_test"] = {"dropped": dict(drop), "13gram_removed": removed}
    existing_states = {digest(r["state"].strip().casefold()) for split in ("train", "dev", "cal") for r in final[split]}
    existing_cases = {r["case_id"] for split in ("train", "dev", "cal") for r in final[split]}
    for key, rows in list(ext_raw.items()):
        ext_raw[key] = [
            r
            for r in rows
            if digest(r["state"].strip().casefold()) not in existing_states and r["case_id"] not in existing_cases
        ]
    task_test = [
        r
        for r in task_test
        if digest(r["state"].strip().casefold()) not in existing_states and r["case_id"] not in existing_cases
    ]
    ext_raw["tasksource_test"] = stratified(task_test, 3000)
    external_rows = [r for name, rows in ext_raw.items() if name != "tasksource_test" for r in rows]
    external_states = {digest(r["state"].strip().casefold()) for r in external_rows}
    external_cases = {r["case_id"] for r in external_rows}
    task_test = [
        r
        for r in task_test
        if digest(r["state"].strip().casefold()) not in existing_states
        and r["case_id"] not in existing_cases
        and digest(r["state"].strip().casefold()) not in external_states
        and r["case_id"] not in external_cases
    ]
    ext_raw["tasksource_test"] = stratified(task_test, 3000)
    for name, source_rows in list(ext_raw.items()):
        before = len(source_rows)
        validated_rows, dropped = validate(source_rows, tokenizer)
        ext_raw[name] = stratified(validated_rows, 3000)
        manifest["filters"][name + "_final_validation_and_cap"] = {
            "before": before,
            "dropped": dict(dropped),
            "after_validation": len(validated_rows),
            "after_cap": len(ext_raw[name]),
        }

    # Stage mixture source training rows; fixed-count stratified probe sample retains stage proportions.
    train_rows = final["train"]
    # keep approximately requested 300-400k; tasksource cap plus complete Open-Jev and System-One.
    if len(train_rows) > 400_000:
        train_rows = stratified(train_rows, 400_000)
    final["train"] = train_rows
    final["dev"], _ = validate(final["dev"], tokenizer)
    final["cal"], _ = validate(final["cal"], tokenizer)
    # Preserve the Polish examples and add the distribution required by this output schema.
    test_path = ROOT / "pretrain/work/sft/test.jsonl"
    output_files = {}
    test_rows = []
    for line in test_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["target"] = [1.0 if i == row["gold"] else 0.0 for i in range(len(row["options"]))]
        if row["label_method"] == "code":
            row["label_method"] = "synthetic"
        test_rows.append(row)
    test_rows, test_drops = validate(test_rows, tokenizer)
    if test_drops:
        raise ValueError(f"Polish test did not validate: {dict(test_drops)}")
    for split in ("train", "dev", "cal"):
        rows = final[split]
        path = OUT / "stage1" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        output_files[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    probe = stratified(final["train"], 100_000)
    for split, rows in (("train", probe), ("dev", final["dev"]), ("cal", final["cal"])):
        path = OUT / "probe" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        output_files[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for dirname in ("stage1", "probe"):
        dest = OUT / dirname / "test.jsonl"
        dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in test_rows), encoding="utf-8")
        output_files[str(dest.relative_to(ROOT))] = hashlib.sha256(dest.read_bytes()).hexdigest()
    for name, rows in ext_raw.items():
        path = OUT / "ext" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        output_files[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()

    all_rows = [r for split in ("train", "dev", "cal") for r in final[split]]
    for split in ("train", "dev", "cal"):
        manifest["decisions"][split] = {
            "rows": len(final[split]),
            "types": dict(Counter(r["type"] for r in final[split])),
            "languages": dict(Counter(r["language"] for r in final[split])),
            "datasets": dict(Counter(r["family"].split("/", 1)[0] for r in final[split])),
        }
    manifest["polish_test"] = {
        "rows": len(test_rows),
        "types": dict(Counter(r["type"] for r in test_rows)),
        "languages": dict(Counter(r["language"] for r in test_rows)),
    }
    train_datasets = Counter(r["family"].split("/", 1)[0] for r in final["train"])
    train_families = Counter(r["family"] for r in final["train"])
    manifest["mixture"] = {
        "train_rows": len(final["train"]),
        "dataset_counts": dict(train_datasets),
        "dataset_shares": {k: v / len(final["train"]) for k, v in train_datasets.items()},
        "family_counts": dict(train_families),
        "family_shares": {k: v / len(final["train"]) for k, v in train_families.items()},
        "probe_rows": len(probe),
        "probe_preserves_proportions_by_stratification": True,
    }
    manifest["histograms"] = {
        "language": dict(Counter(r["language"] for r in all_rows)),
        "type": dict(Counter(r["type"] for r in all_rows)),
        "option_count": dict(Counter(str(len(r["options"])) for r in all_rows)),
        "gold_position": dict(Counter(str(r["gold"]) for r in all_rows)),
    }
    manifest["source_counts_by_split"] = {
        split: dict(Counter(r["source"] for r in rows))
        for split, rows in final.items()
        if split in ("train", "dev", "cal")
    }
    manifest["external"] = {
        name: {
            "rows": len(rows),
            "source_counts": dict(Counter(r["source"] for r in rows)),
            "types": dict(Counter(r["type"] for r in rows)),
            "languages": dict(Counter(r["language"] for r in rows)),
        }
        for name, rows in ext_raw.items()
    }
    manifest["external"]["option_count"] = {
        name: dict(Counter(str(len(r["options"])) for r in rows)) for name, rows in ext_raw.items()
    }
    manifest["external"]["gold_position"] = {
        name: dict(Counter(str(r["gold"]) for r in rows)) for name, rows in ext_raw.items()
    }
    manifest["sha256"] = output_files
    mp = OUT / "manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "stage": manifest["decisions"],
                "external": {k: len(v) for k, v in ext_raw.items()},
                "manifest": str(mp),
                "sargedev": manifest["sargedev"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
