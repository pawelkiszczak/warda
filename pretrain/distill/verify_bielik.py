#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from common import ROOT, WORK, log, read_jsonl, write_jsonl


class PromptTokenizer:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def apply_chat_template(self, *args, **kwargs):
        return self.tokenizer.apply_chat_template(*args, **kwargs)

    def encode(self, text, add_special_tokens=True):
        return self.tokenizer.encode(text, add_special_tokens=add_special_tokens)

    def __call__(self, text, add_special_tokens=True):
        return SimpleNamespace(input_ids=self.encode(text, add_special_tokens))


def score_order(model, mx, prompt_module, tok, item, options):
    prompt = prompt_module.render(tok, item["state"], item["question"], options, lang="pl")
    ids = prompt_module.letter_ids(tok, prompt, len(options))
    if ids is None:
        raise ValueError(f"Verifier cannot tokenize answer letters for {item['id']}")
    encoded = tok.encode(prompt, add_special_tokens=False)
    logits = model(mx.array([encoded]))
    if hasattr(logits, "logits"):
        logits = logits.logits
    mx.eval(logits)
    values = np.asarray(logits[0, -1, ids], dtype=np.float64)
    values -= values.max()
    probs = np.exp(values)
    return probs / probs.sum()


def verify(model, mx, prompt_module, tok, item):
    opts = item["options"]
    first = score_order(model, mx, prompt_module, tok, item, opts)
    reverse_opts = list(reversed(opts))
    reverse = score_order(model, mx, prompt_module, tok, item, reverse_opts)[::-1]
    probs = (first + reverse) / 2
    probs /= probs.sum()
    return {
        **item,
        "verifier_target": probs.tolist(),
        "verifier_gold": int(probs.argmax()),
        "verifier": "Bielik-11B-v2.3-Instruct",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=WORK / "teacher_eval_teacher.jsonl")
    parser.add_argument("--output", type=Path, default=WORK / "teacher_eval_verified.jsonl")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default="speakleash/Bielik-11B-v2.3-Instruct")
    args = parser.parse_args()
    import sys

    import mlx.core as mx
    from mlx_lm import load

    sys.path.insert(0, str(ROOT))
    from pretrain import prompt as prompt_module

    start = time.perf_counter()
    model, mlx_tokenizer = load(args.model)
    tok = PromptTokenizer(mlx_tokenizer)
    done = {row["id"] for row in read_jsonl(args.output)}
    items = [row for row in read_jsonl(args.input) if row["id"] not in done]
    if args.limit:
        items = items[: args.limit]
    rows, agrees = [], 0
    for i, item in enumerate(items, 1):
        row = verify(model, mx, prompt_module, tok, item)
        agrees += row["verifier_gold"] == item["gold"]
        rows.append(row)
        if i % 10 == 0:
            write_jsonl(args.output, rows, append=True)
            rows.clear()
            log(f"verified {i}/{len(items)} new eval items")
    if rows:
        write_jsonl(args.output, rows, append=True)
    elapsed = time.perf_counter() - start
    log(
        f"verified {len(items)} items at {len(items) / max(elapsed, 1e-9):.2f} items/s; teacher agreement={agrees}/{len(items)} ({agrees / max(len(items), 1):.3f}); output={args.output}"
    )


if __name__ == "__main__":
    main()
