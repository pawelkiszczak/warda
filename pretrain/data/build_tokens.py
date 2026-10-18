#!/usr/bin/env python3
"""Curate local pretrain/work/raw corpora into APT4 uint16 token bins.

Run `python pretrain/data/build_tokens.py --download` to fetch bounded, resumable
SpeakLeash prefixes and Hugging Face parquet shards, then curate and tokenize.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import requests
import zstandard
from datasketch import MinHash, MinHashLSH
from requests.adapters import HTTPAdapter
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from tokenizers import Tokenizer
from urllib3.util.retry import Retry
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
RAW = WORK / "raw"
OUT = WORK / "tokens"
BASE = "https://d6t0.c15.e2-2.dev/speakleash-ds-pub/datasets_text"
SL = [
    "plwiki",
    "wolne_lektury_corpus",
    "1000_novels_corpus_CLARIN-PL",
    "biblioteka_nauki_pl_corpus",
    "europeana_eu_pl_corpus",
    "saos",
    "eurlex_corpus",
    "ISAP_corpus",
    "PPC_corpus",
    "CBOSA_corpus",
    "open_subtitles_corpus",
    "shopping_1_general_corpus",
    "forum_gazeta_pl_corpus",
    "forum_muratordom_pl_corpus",
    "web_artykuły_inne_1",
    "web_artykuły_inne_2",
]
TARGET = 1_050_000_000
VAL_TARGET = 5_000_000
# Bielik v3 corpus cutoff (7B/11B used 0.90). Volume is quota-limited: 0.90 gave 821.9M train tokens, 0.50 gave 822.4M.
QUALITY_THRESHOLD = 0.5
STOP = {
    "a",
    "aby",
    "ach",
    "albo",
    "ale",
    "aż",
    "bardziej",
    "bardzo",
    "bez",
    "bo",
    "być",
    "była",
    "były",
    "będzie",
    "celu",
    "ci",
    "co",
    "czy",
    "dla",
    "do",
    "dziś",
    "gdzie",
    "go",
    "i",
    "ich",
    "ile",
    "im",
    "inny",
    "ja",
    "jak",
    "jako",
    "je",
    "jeden",
    "jego",
    "jej",
    "jeśli",
    "już",
    "ją",
    "kiedy",
    "który",
    "która",
    "które",
    "kto",
    "ku",
    "lub",
    "ma",
    "mam",
    "mi",
    "mnie",
    "może",
    "na",
    "nad",
    "nam",
    "nas",
    "nie",
    "nich",
    "nic",
    "niż",
    "no",
    "o",
    "od",
    "on",
    "ona",
    "one",
    "oni",
    "ono",
    "oraz",
    "pa",
    "pani",
    "po",
    "pod",
    "podczas",
    "pomiędzy",
    "przez",
    "przy",
    "roku",
    "się",
    "są",
    "ta",
    "tak",
    "tam",
    "te",
    "tego",
    "tej",
    "ten",
    "to",
    "tu",
    "twój",
    "twoja",
    "w",
    "we",
    "więc",
    "wszystek",
    "wy",
    "z",
    "za",
    "ze",
    "że",
}

HTTP = requests.Session()
HTTP.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=5,
            connect=5,
            read=5,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
        )
    ),
)


def request(method: str, url: str, **kwargs):
    kwargs.setdefault("timeout", (20, 120))
    return HTTP.request(method, url, **kwargs)


def progress(message: str) -> None:
    print(message, flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "data_pipeline.log").open("a", encoding="utf-8") as log:
        log.write(message + "\n")


def get(url: str, path: Path, end: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "warda-pretraining/1.0"}
    offset = path.stat().st_size if path.exists() else 0
    expected_size = 0
    if end is None:
        remote = request("HEAD", url, headers=headers, allow_redirects=True, timeout=(20, 60))
        remote.raise_for_status()
        expected_size = int(remote.headers.get("Content-Length", 0))
        if expected_size and offset == expected_size:
            return
        if expected_size and offset > expected_size:
            path.unlink()
            offset = 0
    if offset:
        headers["Range"] = f"bytes={offset}-{end - 1 if end else ''}"
    elif end is not None:
        headers["Range"] = f"bytes=0-{end - 1}"
    with request("GET", url, headers=headers, stream=True) as r:
        r.raise_for_status()
        if (offset or end is not None) and r.status_code != 206:
            raise RuntimeError(f"server ignored byte range for {url}")
        mode = "ab" if offset else "wb"
        with path.open(mode) as f:
            for block in r.iter_content(1024 * 1024):
                if block:
                    f.write(block)
    if end is None and expected_size and path.stat().st_size != expected_size:
        raise RuntimeError(f"incomplete download for {url}: {path.stat().st_size}/{expected_size} bytes")


def hf_files(repo: str, config: str) -> list[str]:
    api_config = config.replace("/", "-")
    url = f"https://huggingface.co/api/datasets/{repo}/parquet/{api_config}"
    response = request("GET", url)
    response.raise_for_status()
    data = response.json()
    files = [f for f in data.get("train", []) if f.endswith(".parquet")]
    if not files:
        raise RuntimeError(f"No training parquet files returned for {repo}/{config}")
    return files


def download_one(item: tuple[str, Path, int | None]) -> str:
    url, path, size = item
    get(url, path, size)
    return f"{path.name}: {path.stat().st_size:,} bytes"


def download() -> None:
    jobs: list[tuple[str, Path, int | None]] = []
    # Range prefixes are bounded to 550 MiB per set; total compressed download stays below 10 GiB.
    for name in SL:
        manifest_url = f"{BASE}/{name}.manifest"
        manifest = request("GET", manifest_url, timeout=(20, 40)).json()
        (RAW / "speakleash" / f"{name}.manifest").parent.mkdir(parents=True, exist_ok=True)
        (RAW / "speakleash" / f"{name}.manifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        jobs.append(
            (
                f"{BASE}/{name}.jsonl.zst",
                RAW / "speakleash" / f"{name}.jsonl.zst",
                min(550 * 1024 * 1024, int(manifest.get("file_size", 0)) or 550 * 1024 * 1024),
            )
        )
    for repo, config, count in [
        ("HuggingFaceFW/fineweb-2", "pol_Latn", 2),
        ("HuggingFaceFW/fineweb-edu", "sample-10BT", 1),
    ]:
        jobs.extend(
            (file, RAW / "hf" / repo.split("/")[-1] / Path(file).name, None) for file in hf_files(repo, config)[:count]
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(download_one, jobs):
            print(result, flush=True)


def clean(text: str) -> str | None:
    text = unicodedata.normalize("NFC", text.encode("utf-8", "replace").decode("utf-8"))
    if text.count("\ufffd") / max(1, len(text)) > 0.001:
        return None
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " [EMAIL] ", text)
    text = re.sub(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", " [PHONE] ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " [URL] ", text, flags=re.I)
    lines = text.splitlines()
    line_counts = Counter(line for line in lines if line.strip())
    duplicate_line_ratio = sum(count for count in line_counts.values() if count > 1) / max(1, len(lines))
    if len(lines) > 4 and duplicate_line_ratio > 0.35:
        return None
    words = re.findall(r"\w+", text.lower())
    content_length = len(re.sub(r"[\W_]+", "", text, flags=re.UNICODE))
    if content_length < 200 or (len(words) > 80 and len(set(zip(words, words[1:], words[2:], strict=False))) < 8):
        return None
    return text.strip()


def features(text: str, wordlist: set[str]) -> list[float]:
    words = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)
    lines = text.splitlines() or [text]
    sentences = re.split(r"[.!?]+", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    counts = Counter(words)
    chars = max(1, len(text))
    punct = sum(not c.isalnum() and not c.isspace() for c in text)
    dia = sum(c in "ąćęłńóśźż" for c in text.lower())
    lengths = [len(x) for x in lines]
    repeats = sum(count > 1 for count in Counter(x.strip() for x in lines if x.strip()).values())
    ngram = Counter(zip(words, words[1:], words[2:], strict=False))
    return [
        len(words),
        len(text),
        len(lines),
        len(paragraphs),
        len(sentences),
        sum(w in STOP for w in words) / max(1, len(words)),
        dia / chars,
        dia / max(1, len(words)),
        sum(n < 20 for n in lengths) / len(lengths),
        repeats / max(1, len(lines)),
        punct / max(1, len(words)),
        sum(c.isupper() for c in text) / chars,
        punct / max(1, len(sentences)),
        len(words) / max(1, len(sentences)),
        sum(len(p.split()) for p in paragraphs) / max(1, len(paragraphs)),
        sum(v == 1 for v in counts.values()) / max(1, len(words)),
        max(ngram.values(), default=0) / max(1, len(words)),
        sum(w not in wordlist for w in words) / max(1, len(words)),
        sum(c.isalpha() for c in text) / chars,
        text.count("\n\n") / max(1, len(lines)),
        sum(len(w) == 1 for w in words) / max(1, len(words)),
        sum(c.islower() for c in text) / chars,
        text.count(":") / max(1, len(sentences)),
        text.count(",") / max(1, len(sentences)),
        len(set(words)) / max(1, len(words)),
        sum(c.isdigit() for c in text) / chars,
        sum(c in "<>|{}[]" for c in text) / chars,
        max(lengths) / max(1, len(text)),
        np.mean(lengths),
        np.std(lengths),
        sum(1 for w in words if w in {"jest", "są", "oraz", "który", "która"}) / max(1, len(words)),
        text.count("*") / chars,
        text.count("#") / chars,
        text.count("_") / chars,
        text.count("-") / chars,
        text.count(";") / max(1, len(sentences)),
        sum(len(w) >= 7 for w in words) / max(1, len(words)),
        sum(len(w) <= 3 for w in words) / max(1, len(words)),
        len(set(lines)) / max(1, len(lines)),
        text.count("?") / max(1, len(sentences)),
        text.count("!") / max(1, len(sentences)),
        sum(c.isupper() for c in text) / max(1, sum(c.isalpha() for c in text)),
        sum(c.isalpha() or c.isspace() for c in text) / chars,
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def zstd_lines(reader, truncated: bool):
    try:
        yield from reader
    except zstandard.ZstdError:
        if not truncated:
            raise


def record(row: object) -> tuple[str, dict]:
    if isinstance(row, dict):
        text = row.get("text") or row.get("content") or row.get("document") or ""
        meta = row.get("meta") or row.get("metadata") or row
    elif isinstance(row, str):
        text, meta = row, {}
    else:
        text, meta = "", {}
    return str(text), meta if isinstance(meta, dict) else {}


def json_records(stream):
    decoder = json.JSONDecoder()
    utf8 = __import__("codecs").getincrementaldecoder("utf-8")()
    buffer = ""
    eof = False
    while True:
        if buffer.startswith("\\n"):
            buffer = buffer[2:]
            continue
        if buffer.startswith("\n"):
            buffer = buffer[1:]
            continue
        if buffer:
            try:
                record, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                pass
            else:
                yield record
                buffer = buffer[end:]
                continue
        if eof:
            if buffer.strip():
                raise ValueError("invalid or truncated cached JSON records")
            return
        chunk = stream.read(1024 * 1024)
        eof = not chunk
        buffer += utf8.decode(chunk, final=eof)


def load_docs(stats: Counter):
    cache_root = WORK / "cache" / "speakleash"
    cache_root.mkdir(parents=True, exist_ok=True)
    for path in sorted((RAW / "speakleash").glob("*.jsonl.zst")):
        source = path.name.removesuffix(".jsonl.zst")
        manifest = json.loads(path.with_suffix("").with_suffix(".manifest").read_text())
        cache = cache_root / f"{source}.{path.stat().st_size}.jsonl.zst"
        cache_stats = cache.with_suffix(".stats.json")
        progress(f"Stage: streaming raw/cache source {source}")
        if cache.exists() and cache_stats.exists():
            source_stats = json.loads(cache_stats.read_text())
            cache_format = source_stats.pop("_cache_format", 0)
            stats.update(source_stats)
            if cache_format == 2:
                with cache.open("rb") as cached:
                    reader = __import__("io").BufferedReader(zstandard.ZstdDecompressor().stream_reader(cached))
                    for line in reader:
                        yield json.loads(line)
            else:
                repaired = cache.with_suffix(".repair")
                with cache.open("rb") as cached, repaired.open("wb") as target:
                    reader = __import__("io").BufferedReader(zstandard.ZstdDecompressor().stream_reader(cached))
                    with zstandard.ZstdCompressor().stream_writer(target, closefd=False) as cached_out:
                        for doc in json_records(reader):
                            cached_out.write(json.dumps(doc, ensure_ascii=False).encode("utf-8") + b"\n")
                            yield doc
                os.replace(repaired, cache)
                cache_stats.write_text(json.dumps({**source_stats, "_cache_format": 2}))
                progress(f"{source}: repaired legacy cache separators")
            progress(f"{source}: streamed cached docs")
            continue
        source_stats = Counter()
        partial = cache.with_suffix(".partial")
        with (
            partial.open("wb") as target,
            zstandard.ZstdCompressor().stream_writer(target, closefd=False) as cached_out,
            path.open("rb") as compressed,
        ):
            dctx = __import__("io").BufferedReader(zstandard.ZstdDecompressor().stream_reader(compressed))
            truncated = path.stat().st_size < int(manifest.get("file_size", path.stat().st_size))
            for line in zstd_lines(dctx, truncated):
                source_stats["raw"] += 1
                try:
                    raw, meta = record(json.loads(line))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    source_stats["bad_json"] += 1
                    continue
                text = clean(raw)
                if not text:
                    source_stats["clean_drop"] += 1
                    continue
                label = str(meta.get("quality", "")).upper()
                if label in ("HIGH", "MEDIUM", "LOW"):
                    doc = {
                        "text": text,
                        "source": source,
                        "license": manifest.get("license", "unknown"),
                        "label": label,
                        "language": "pl",
                        "quality": label,
                    }
                    cached_out.write(json.dumps(doc, ensure_ascii=False).encode("utf-8") + b"\n")
                    yield doc
                source_stats["clean"] += 1
        os.replace(partial, cache)
        cache_stats.write_text(json.dumps({**dict(source_stats), "_cache_format": 2}))
        progress(f"{source}: cleaned {source_stats['clean']:,} docs")
        stats.update(source_stats)


def shingles(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower(), re.UNICODE)
    return {" ".join(words[i : i + 13]) for i in range(max(0, len(words) - 12))}


def minhash_for_text(text: str):
    words = re.findall(r"\w+", text.lower())
    if len(words) < 13:
        return None
    result = MinHash(num_perm=128)
    for i in range(len(words) - 12):
        result.update(" ".join(words[i : i + 13]).encode())
    return result


_WORKER_WORDLIST: set[str] = set()
_WORKER_TOKENIZER: Tokenizer | None = None


def initialize_worker(wordlist: set[str], tokenizer_path: str) -> None:
    global _WORKER_WORDLIST, _WORKER_TOKENIZER
    _WORKER_WORDLIST = wordlist
    _WORKER_TOKENIZER = Tokenizer.from_file(tokenizer_path)


def feature_worker(text: str) -> list[float]:
    return features(text, _WORKER_WORDLIST)


def tokenize_worker(text: str) -> list[int]:
    if _WORKER_TOKENIZER is None:
        raise RuntimeError("tokenizer worker has not been initialized")
    return [1, *_WORKER_TOKENIZER.encode(text, add_special_tokens=False).ids, 2]


def decontamination_shingles(pq) -> set[str]:
    refs: set[str] = set()
    for repo in ("klej-polemo2-in", "klej-allegro-reviews", "klej-cbd", "klej-dyk"):
        response = request("GET", f"https://huggingface.co/api/datasets/allegro/{repo}/parquet")
        response.raise_for_status()
        data = response.json()
        files = [file for config in data.values() for file in config.get("test", [])]
        if not files:
            raise RuntimeError(f"Missing test split for allegro/{repo}")
        for index, file in enumerate(files):
            cache = RAW / "decontam" / repo / f"{index}.parquet"
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                with request("GET", file, stream=True) as download:
                    download.raise_for_status()
                    with cache.open("wb") as out:
                        for block in download.iter_content(1024 * 1024):
                            if block:
                                out.write(block)
            for batch in pq.ParquetFile(cache).iter_batches(batch_size=1024):
                for row in batch.to_pylist():
                    for value in row.values():
                        if isinstance(value, str):
                            refs.update(shingles(value))
    progress(f"Decontamination reference 13-grams: {len(refs):,}")
    return refs


def build() -> None:
    import pyarrow.parquet as pq

    progress("Stage: gathering decontamination references")
    reference_grams = decontamination_shingles(pq)
    progress("Stage: loading APT4 tokenizer")
    tokenizer_path = WORK / "cache" / "apt4-tokenizer.json"
    tokenizer_path.parent.mkdir(parents=True, exist_ok=True)
    if (ROOT / "tokenizer.json").exists():
        tokenizer = Tokenizer.from_file(str(ROOT / "tokenizer.json"))
    else:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            "speakleash/Bielik-1.5B-v3.0-Instruct", use_fast=True
        ).backend_tokenizer
    tokenizer.save(str(tokenizer_path))

    # Reservoir-sample bounded classifier data and build the Polish OOV vocabulary.
    progress("Stage: streaming SpeakLeash caches for stratified classifier sample")
    stats: Counter[str] = Counter()
    sample: dict[str, list[dict[str, Any]]] = {label: [] for label in ("HIGH", "MEDIUM", "LOW")}
    seen_labels: Counter[str] = Counter()
    rng = random.Random(42)
    vocab: set[str] = set()
    for doc in load_docs(stats):
        label = doc["label"]
        seen_labels[label] += 1
        group = sample[label]
        if len(group) < 50_000:
            group.append(doc)
        else:
            slot = rng.randrange(seen_labels[label])
            if slot < len(group):
                group[slot] = doc
        if doc["source"] == "plwiki" and len(vocab) < 300_000:
            vocab.update(re.findall(r"[^\W\d_]{3,}", doc["text"].lower(), re.UNICODE))
    sample_docs = [doc for label in sample for doc in sample[label]]
    if not sample_docs or any(not sample[label] for label in sample):
        raise RuntimeError(f"Quality classifier requires all labels; found {seen_labels}")

    xgb_labels = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=12, initializer=initialize_worker, initargs=(vocab, str(tokenizer_path))
    ) as pool:
        features_sample = list(pool.map(feature_worker, (doc["text"] for doc in sample_docs), chunksize=128))
        X = np.asarray(features_sample, dtype=np.float32)
        y = np.asarray([xgb_labels[doc["label"]] for doc in sample_docs], dtype=np.int32)
        train_ix, test_ix = train_test_split(np.arange(len(y)), test_size=0.1, random_state=42, stratify=y)
        model = XGBClassifier(
            n_estimators=250,
            max_depth=8,
            learning_rate=0.08,
            subsample=0.75,
            colsample_bytree=0.8,
            reg_alpha=0.2,
            reg_lambda=0.5,
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=12,
        )
        progress(f"Stage: fitting XGBoost on {len(train_ix):,} stratified documents")
        model.fit(X[train_ix], y[train_ix])
        prediction = model.predict(X[test_ix])
        metrics = {
            "accuracy": float(accuracy_score(y[test_ix], prediction)),
            "macro_f1": float(f1_score(y[test_ix], prediction, average="macro")),
            "high_f1": float(
                f1_score(y[test_ix], prediction, labels=[xgb_labels["HIGH"]], average="macro", zero_division=0)
            ),
        }
        progress(f"Stage: classifier metrics {json.dumps(metrics)}")
        high_index = list(model.classes_).index(xgb_labels["HIGH"])

        db_path = WORK / "cache" / "tokens.sqlite"
        db = sqlite3.connect(db_path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("DROP TABLE IF EXISTS tokens")
        db.execute("DROP TABLE IF EXISTS selected")
        db.execute(
            "CREATE TABLE tokens (id INTEGER PRIMARY KEY, source TEXT, license TEXT, token_count INTEGER, shuffle_key INTEGER, ids BLOB)"
        )
        db.execute("CREATE INDEX tokens_source_shuffle ON tokens(source, shuffle_key)")
        db.execute("CREATE TABLE selected (token_id INTEGER PRIMARY KEY, split TEXT)")
        db.commit()

        lsh = MinHashLSH(threshold=0.8, num_perm=128)
        seen_hashes: set[bytes] = set()
        shuffle_rng = random.Random(42)
        insert_rows = []
        processed = 0

        def store_candidates(docs: list[dict]) -> None:
            nonlocal processed
            candidates = []
            for doc in docs:
                if reference_grams.intersection(shingles(doc["text"])):
                    stats["decontaminated"] += 1
                    continue
                digest = hashlib.sha256(doc["text"].encode("utf-8")).digest()
                if digest in seen_hashes:
                    stats["exact_duplicate"] += 1
                    continue
                seen_hashes.add(digest)
                candidates.append(doc)
            if not candidates:
                return
            fingerprints = pool.map(minhash_for_text, (doc["text"] for doc in candidates), chunksize=32)
            keep = []
            for doc, fingerprint in zip(candidates, fingerprints, strict=False):
                if fingerprint is not None:
                    if lsh.query(fingerprint):
                        stats["near_duplicate"] += 1
                        continue
                    lsh.insert(str(processed), fingerprint)
                keep.append(doc)
                processed += 1
            token_lists = pool.map(tokenize_worker, (doc["text"] for doc in keep), chunksize=32)
            for doc, ids in zip(keep, token_lists, strict=False):
                insert_rows.append(
                    (
                        doc["source"],
                        doc["license"],
                        len(ids),
                        shuffle_rng.getrandbits(63),
                        np.asarray(ids, dtype="<u2").tobytes(),
                    )
                )
            stats["dedup_kept"] += len(keep)
            if len(insert_rows) >= 2048:
                db.executemany(
                    "INSERT INTO tokens(source,license,token_count,shuffle_key,ids) VALUES(?,?,?,?,?)", insert_rows
                )
                db.commit()
                insert_rows.clear()
            if processed and processed % 50_000 < len(keep):
                progress(f"Stage: deduplicated and tokenized {processed:,} documents")

        progress("Stage: streaming SpeakLeash quality scoring")
        batch: list[dict] = []
        current_source = ""

        def score_speakleash(rows: list[dict]) -> None:
            if not rows:
                return
            matrix = np.asarray(
                list(pool.map(feature_worker, (doc["text"] for doc in rows), chunksize=64)), dtype=np.float32
            )
            probabilities = model.predict_proba(matrix)[:, high_index]
            candidates = []
            for doc, probability in zip(rows, probabilities, strict=False):
                stats["speakleash_scored"] += 1
                if doc["quality"] == "HIGH" or probability > QUALITY_THRESHOLD:
                    doc["p_high"] = float(probability)
                    candidates.append(doc)
                else:
                    stats["classifier_drop"] += 1
            stats["speakleash_quality_kept"] += len(candidates)
            store_candidates(candidates)

        for doc in load_docs(Counter()):
            if doc["source"] != current_source:
                if current_source:
                    score_speakleash(batch)
                    progress(f"Stage: finished quality scoring source {current_source}")
                    batch.clear()
                current_source = doc["source"]
                progress(f"Stage: quality scoring source {current_source}")
            batch.append(doc)
            if len(batch) == 512:
                score_speakleash(batch)
                batch.clear()
        score_speakleash(batch)
        if current_source:
            progress(f"Stage: finished quality scoring source {current_source}")

        progress("Stage: streaming FineWeb parquet shards")
        hf_paths = sorted(
            Path(root) / filename
            for root, _, names in os.walk(RAW / "hf")
            for filename in names
            if filename.endswith(".parquet")
        )
        for path in hf_paths:
            language = "en" if "fineweb-edu" in str(path) else "pl"
            source = "fineweb-edu" if language == "en" else "fineweb-2"
            progress(f"Stage: reading {source}/{path.name}")
            for batch_index, arrow_batch in enumerate(pq.ParquetFile(path).iter_batches(batch_size=512)):
                candidates: list[dict[str, Any]] = []
                polish: list[dict[str, Any]] = []
                for row in arrow_batch.to_pylist():
                    text = clean(str(row.get("text", "")))
                    if not text:
                        stats["clean_drop"] += 1
                    elif language == "en":
                        if int(row.get("int_score", 0) or 0) >= 3:
                            candidates.append(
                                {
                                    "text": text,
                                    "source": source,
                                    "license": "ODC-By-1.0",
                                    "language": "en",
                                    "quality": "public",
                                }
                            )
                        else:
                            stats["source_quality_drop"] += 1
                    elif float(row.get("language_score", 0) or 0) >= 0.98:
                        polish.append(
                            {
                                "text": text,
                                "source": source,
                                "license": "ODC-By-1.0",
                                "language": "pl",
                                "quality": "public",
                            }
                        )
                    else:
                        stats["source_quality_drop"] += 1
                if polish:
                    matrix = np.asarray(
                        list(pool.map(feature_worker, (doc["text"] for doc in polish), chunksize=64)), dtype=np.float32
                    )
                    probabilities = model.predict_proba(matrix)[:, high_index]
                    for doc, probability in zip(polish, probabilities, strict=False):
                        if probability > QUALITY_THRESHOLD:
                            doc["p_high"] = float(probability)
                            candidates.append(doc)
                        else:
                            stats["classifier_drop"] += 1
                stats[f"{source}_eligible"] += len(candidates)
                for offset in range(0, len(candidates), 512):
                    store_candidates(candidates[offset : offset + 512])
                if batch_index % 100 == 0:
                    progress(f"Stage: {source}/{path.name} row batch {batch_index:,}")
            progress(f"Stage: finished {source}/{path.name}")

        if insert_rows:
            db.executemany(
                "INSERT INTO tokens(source,license,token_count,shuffle_key,ids) VALUES(?,?,?,?,?)", insert_rows
            )
            db.commit()
        source_totals = dict(db.execute("SELECT source, SUM(token_count) FROM tokens GROUP BY source"))
        speak_sources = [source for source in source_totals if source not in {"fineweb-2", "fineweb-edu"}]
        desired = {"fineweb-2": 0.35, "fineweb-edu": 0.15}
        targets = {source: int(TARGET * share) for source, share in desired.items()}
        remaining = TARGET - sum(targets.values())
        for source in speak_sources:
            targets[source] = min(remaining // max(1, len(speak_sources)), int(TARGET * 0.12))
        targets = {source: min(target, int(source_totals.get(source, 0))) for source, target in targets.items()}
        progress(f"Stage: selecting whole-document mix from tokenized store {source_totals}")
        selected_counts: Counter[str] = Counter()
        total_target = sum(targets.values())
        for source, target_count in targets.items():
            available = int(source_totals.get(source, 0))
            bounded_target = min(target_count, available)
            val_target = VAL_TARGET * bounded_target / max(1, total_target)
            chosen = val_count = 0
            cursor = db.execute("SELECT id, token_count FROM tokens WHERE source=? ORDER BY shuffle_key, id", (source,))
            for token_id, token_count in cursor:
                if chosen >= bounded_target:
                    break
                split = "val" if val_count < val_target else "train"
                db.execute("INSERT INTO selected(token_id,split) VALUES(?,?)", (token_id, split))
                chosen += token_count
                selected_counts[source] += token_count
                if split == "val":
                    val_count += token_count
            db.commit()

        OUT.mkdir(parents=True, exist_ok=True)
        for old_bin in OUT.glob("*.bin"):
            old_bin.unlink()
        token_counts: Counter[str] = Counter()
        source_split_counts: Counter[tuple[str, str]] = Counter()
        for split in ("train", "val"):
            with (OUT / f"{split}.bin").open("wb") as output:
                query = db.execute(
                    "SELECT tokens.source, tokens.token_count, tokens.ids FROM selected JOIN tokens ON selected.token_id=tokens.id WHERE selected.split=? ORDER BY tokens.shuffle_key, tokens.id",
                    (split,),
                )
                while rows := query.fetchmany(2048):
                    for source, count, payload in rows:
                        output.write(payload)
                        token_counts[split] += count
                        source_split_counts[(split, source)] += count
        for source in speak_sources + [s for s in ("fineweb-2", "fineweb-edu") if s in source_totals]:
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", source)
            with (OUT / f"val_{safe}.bin").open("wb") as output:
                query = db.execute(
                    "SELECT tokens.ids FROM selected JOIN tokens ON selected.token_id=tokens.id WHERE selected.split='val' AND tokens.source=? ORDER BY tokens.shuffle_key, tokens.id",
                    (source,),
                )
                while rows := query.fetchmany(2048):
                    for (payload,) in rows:
                        output.write(payload)
        window_rng = random.Random(42)
        start = window_rng.randrange(max(1, token_counts["train"] - 2048))
        with (OUT / "train.bin").open("rb") as stream:
            stream.seek(start * 2)
            window = np.frombuffer(stream.read(4096), dtype="<u2").tolist()
        progress("Random decoded 2048-token window: " + tokenizer.decode(window))
        sources = dict(db.execute("SELECT source, MIN(license) FROM tokens GROUP BY source"))
        manifest = {
            "tokenizer": "speakleash/Bielik-1.5B-v3.0-Instruct",
            "total_tokens": dict(token_counts),
            "per_source_tokens": {
                split: {source: count for (which, source), count in source_split_counts.items() if which == split}
                for split in ("train", "val")
            },
            "per_source_selected_tokens": dict(selected_counts),
            "filter_stats": dict(stats),
            "classifier": metrics,
            "quality_threshold": QUALITY_THRESHOLD,
            "sources": sources,
            "sha256": {path.name: file_sha256(path) for path in OUT.glob("*.bin")},
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        progress(f"Stage: completed token bins {json.dumps(manifest, ensure_ascii=False)}")
        db.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--download", action="store_true")
    p.add_argument("--download-only", action="store_true")
    args = p.parse_args()
    if args.download:
        download()
    if not args.download_only:
        build()


if __name__ == "__main__":
    main()
