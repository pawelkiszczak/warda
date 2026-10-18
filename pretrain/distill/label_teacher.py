#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from common import WORK, log, read_jsonl, write_jsonl


def server_question(item):
    opts = item["options"]
    typ = item["type"]
    if typ == "noul":
        return {"type": typ, "instructions": item["question"], "criteria": {"true": opts[0], "false": opts[1]}}
    if typ == "score":
        return {"type": typ, "instructions": item["question"], "criteria": opts}
    return {"type": typ, "instructions": item["question"], "criteria": {f"o{i}": opt for i, opt in enumerate(opts)}, "option_keys": "hide"}


def label_group(items, url, timeout, teacher):
    questions, key_map = {}, {}
    for idx, item in enumerate(items):
        key = f"q{idx}"
        questions[key] = server_question(item)
        key_map[key] = item
    response = requests.post(url, json={"state": items[0]["state"], "questions": questions}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    output = []
    for key, item in key_map.items():
        answer = data["answers"][key]
        if item["type"] == "noul":
            p = float(answer["noul"])
            probs = [p, 1.0 - p]
        else:
            raw = answer["probabilities"]
            keys = list(range(len(item["options"]))) if item["type"] == "score" else [f"o{i}" for i in range(len(item["options"]))]
            probs = [float(raw[str(k)] if item["type"] == "score" else raw[k]) for k in keys]
        total = sum(probs)
        if total <= 0 or not all(0 <= p <= 1 for p in probs):
            raise ValueError(f"Invalid teacher probabilities for {item['id']}: {probs}")
        probs = [p / total for p in probs]
        output.append({**item, "target": probs, "gold": max(range(len(probs)), key=probs.__getitem__), "teacher": teacher})
    return output, data.get("usage", {}).get("questions", len(items))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["train", "eval"], required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8077/v1/systemone")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--teacher", default="basal-1.0-4.5B", help="name of the model basal-serve is running (recorded per row)")
    args = parser.parse_args()
    source = args.input or WORK / f"pool_{args.split}.jsonl"
    dest = args.output or WORK / ("teacher_train.jsonl" if args.split == "train" else "teacher_eval_teacher.jsonl")
    done = {row["id"] for row in read_jsonl(dest)}
    groups = defaultdict(list)
    for row in read_jsonl(source):
        if row["id"] not in done:
            groups[row["case_id"]].append(row)
    batch = list(groups.values())
    if args.limit:
        selected, n = [], 0
        for group in batch:
            if n >= args.limit: break
            selected.append(group[:args.limit - n]); n += len(selected[-1])
        batch = selected
    start, completed, decisions = time.perf_counter(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(label_group, group, args.url, args.timeout, args.teacher) for group in batch]
        for future in as_completed(futures):
            rows, n = future.result()
            write_jsonl(dest, rows, append=True)
            completed += len(rows); decisions += n
            if completed % 50 == 0:
                log(f"{args.split}: {completed} new items, {decisions / max(time.perf_counter()-start, 1e-9):.2f} decisions/s")
    rate = decisions / max(time.perf_counter() - start, 1e-9)
    log(f"{args.split}: labelled {completed} items ({decisions} decisions) at {rate:.2f} decisions/s; output={dest}; resumed={len(done)}")
    for row in list(read_jsonl(dest))[-min(5, completed):]:
        log(json.dumps({"id": row["id"], "question": row["question"], "options": row["options"], "target": row["target"], "gold": row["gold"]}, ensure_ascii=False))

if __name__ == "__main__": main()
