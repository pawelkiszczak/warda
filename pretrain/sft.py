"""Turn a pretrained warda-scratch MoE into a typed-decision model, calibrate it and evaluate it.

Input format is Warda's own (`prompt.py`): chat with a fixed system prompt, state, question and lettered
options, assistant prefilled with `{"answer": "`; one forward pass per option order. Two readouts:
- `--readout letter`: softmax over the option-letter logits at the answer slot. The 37M-active scratch model
  did not learn it (train loss stayed at uniform for 2 epochs: no letter-to-option binding at this scale).
- `--readout pointer` (default): a small bilinear head scores each option's last-token state against the answer-slot
  state, so the model reads option content instead of binding letters.
Training loss is cross-entropy over the options, with option order shuffled per item per epoch and families mixed
within batches. Routers are frozen during fine-tuning (balance biases fixed) so narrow data cannot collapse routing.

Evaluation uses both option orders (canonical + reversed) averaged; one temperature per question
type fitted by NLL on `cal`; confidence thresholds for 1% / 5% target error fixed on `cal`, then applied once to `test`.

    pretrain/.venv/bin/python pretrain/sft.py --base s126m-1b --name s126m-1b-sft
    pretrain/.venv/bin/python pretrain/sft.py --base s126m-1b --name s126m-1b-sft --eval-only

Writes `pretrain/work/runs/<name>/`: `model.safetensors`, `config.json`, `calibration.json`, `eval.json`, `sft.jsonl`.
"""

import argparse
import bisect
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import mlx.core as mx
import mlx.optimizers as optim
import numpy as np
from mlx import nn
from mlx.utils import tree_flatten, tree_unflatten
from model import Config, Model
from prompt import LETTERS, letter_ids, render
from train import cast_params
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent

SFT = ROOT / "work" / "sft"
TOKENIZER = "speakleash/Bielik-1.5B-v3.0-Instruct"
PAD = 2


def load_jsonl(path):
    # split on "\n" only: str.splitlines() also breaks on U+2028/U+0085 inside JSON strings written with ensure_ascii=False
    return [json.loads(line) for line in Path(path).read_text().split("\n") if line.strip()]


class Pointer(nn.Module):
    """Option-pointer readout: bilinear score between the answer-slot state and the last-token state of each option.

    Same prompt and single forward pass as the letter readout, but it scores option *content* directly instead of
    asking the model to bind letters to options, which the 37M-active scratch model did not learn (loss stayed at
    uniform for 2 epochs with the letter readout)."""

    def __init__(self, d, r=256):
        super().__init__()
        self.q = nn.Linear(d, r, bias=False)
        self.k = nn.Linear(d, r, bias=False)
        self.r = r

    def __call__(self, h_ans, h_opts):
        return (self.k(h_opts) @ self.q(h_ans)[:, :, None])[..., 0] / math.sqrt(self.r)


def load_model(run):
    """Model, config, balance biases and the pointer head (None when the run has no pointer weights)."""
    checkpoint = run / "model.safetensors"
    if not checkpoint.exists():
        raise FileNotFoundError(
            f"missing trained checkpoint {checkpoint}: train first "
            f"(or point --base/--name at a run directory that contains model.safetensors)"
        )
    cfg = Config(**json.loads((run / "config.json").read_text())["model"])
    model = Model(cfg)
    w = mx.load(str(checkpoint))
    biases = [w.pop(f"blocks.{i}.moe.balance_bias") for i in range(cfg.layers)]
    head = {k[len("pointer.") :]: w.pop(k) for k in [k for k in w if k.startswith("pointer.")]}
    model.update(tree_unflatten(list(w.items())))
    model.set_balance_biases(biases)
    pointer = None
    if head:
        pointer = Pointer(cfg.d, head["q.weight"].shape[0])
        pointer.update(tree_unflatten(list(head.items())))
    return model, cfg, biases, pointer


class Encoder:
    """Prompt tokens for one item in one option order, plus the token index of the last token of each option line.
    Also holds the single-token ids of letters A..J at the answer slot (letter readout)."""

    def __init__(self, tok):
        self.tok = tok
        probe = render(tok, "x", "y", list("abcdefghij"), lang="pl")
        self.letters = letter_ids(tok, probe, len(LETTERS))
        if self.letters is None:
            raise RuntimeError("option letters must be single tokens at the answer position")
        self.cache = {}

    def __call__(self, item, order, cache=True):
        """(token ids as np.int32, last-token index of every option line). With `cache=False` the encoding is not
        stored: per-epoch shuffled training orders are never revisited, so caching them would grow the cache by
        ~len(train) entries per epoch with no reuse."""
        key = (item["id"], tuple(order))
        if cache and key in self.cache:
            return self.cache[key]
        state = item["state"] if isinstance(item["state"], str) else json.dumps(item["state"], ensure_ascii=False)
        options = [item["options"][i] for i in order]
        # the prompt module has Polish and English templates; every other language is shown with the English one
        lang = "pl" if item.get("language") == "pl" else "en"
        prompt = render(self.tok, state, item["question"], options, lang=lang)
        enc = self.tok(prompt, add_special_tokens=False, return_offsets_mapping=True)
        lines = [f"{LETTERS[k]}. {o}" for k, o in enumerate(options)]
        pos = prompt.rfind("\n".join(lines))
        if pos < 0:
            raise ValueError(f"options block not found verbatim in the rendered prompt of {item['id']}")
        starts = [s for s, _ in enc.offset_mapping]
        ends = []
        for line in lines:
            pos += len(line)
            ends.append(bisect.bisect_left(starts, pos) - 1)  # last token starting before the line end
            pos += 1
        encoded = (np.asarray(enc.input_ids, dtype=np.int32), np.asarray(ends, dtype=np.int32))
        if cache:
            self.cache[key] = encoded
        return encoded


def batches(rows, max_tokens, rng=None, bucket=2048):
    """rows: list of (ids, k, gold, meta). Batches under a padded-token budget.

    Without `rng`: globally length-sorted (inference). With `rng` (training): shuffle, then length-sort only within
    random buckets of `bucket` rows, so every batch mixes families. Globally sorted training batches are near
    single-family (length tracks family) and the resulting gradient whipsaw collapsed the model onto one letter.
    """
    if rng is None:
        groups = [sorted(rows, key=lambda r: len(r[0]))]
    else:
        rows = rows[:]
        rng.shuffle(rows)
        groups = [sorted(rows[i : i + bucket], key=lambda r: len(r[0])) for i in range(0, len(rows), bucket)]
    out = []
    for group in groups:
        cur = []
        for r in group:
            if cur and (len(cur) + 1) * len(r[0]) > max_tokens:
                out.append(cur)
                cur = []
            cur.append(r)
        if cur:
            out.append(cur)
    return out


def collate(batch):
    """rows (ids, ends, k, gold, meta, target) -> (x, last, ends (B, 10), mask (B, 10)), target (B, 10)."""
    L = max(len(r[0]) for r in batch)
    x = np.full((len(batch), L), PAD, dtype=np.int32)
    ends = np.zeros((len(batch), len(LETTERS)), dtype=np.int32)
    target = np.zeros((len(batch), len(LETTERS)), dtype=np.float32)
    for i, r in enumerate(batch):
        x[i, : len(r[0])] = r[0]
        ends[i, : len(r[1])] = r[1]
        target[i, : len(r[5])] = r[5]
    last = np.array([len(r[0]) - 1 for r in batch], dtype=np.int32)
    mask = np.array([[0.0 if j < r[2] else -1e9 for j in range(len(LETTERS))] for r in batch], dtype=np.float32)
    return (mx.array(x), mx.array(last), mx.array(ends), mx.array(mask)), mx.array(target)


def option_logits(model, pointer, letters, batch):
    """(B, 10) masked logits over options: letter readout (pointer None) or option-pointer readout."""
    x, last, ends, mask = batch
    rows = mx.arange(x.shape[0])
    if pointer is None:
        logits, _, _ = model(x)
        z = logits[rows, last].astype(mx.float32)[:, letters]
    else:
        h, _, _ = model.hidden(x)
        h = h.astype(mx.float32)
        z = pointer(h[rows, last], h[rows[:, None], ends])
    return z + mask


def order_rows(enc, items, orders, cache=True):
    """One row per (item, option order). The target is the item's soft distribution (`target`, e.g. annotator vote
    shares) or one-hot on `gold`, permuted into display order."""
    rows = []
    for it in items:
        k = len(it["options"])
        target = it.get("target") or [1.0 if j == it["gold"] else 0.0 for j in range(k)]
        for o in orders(it):
            ids, ends = enc(it, o, cache=cache)
            rows.append(
                (
                    ids,
                    ends,
                    len(o),
                    o.index(it["gold"]) if it["gold"] is not None else 0,
                    (it["id"], tuple(o)),
                    [target[i] for i in o],
                )
            )
    return rows


def predict(model, pointer, enc, items, max_tokens):
    """Per item id: [canonical-order logits from the original order, from the reversed order (mapped back)]."""
    rows = order_rows(
        enc, items, lambda it: [list(range(len(it["options"]))), list(reversed(range(len(it["options"]))))]
    )
    out = {}
    for b in batches(rows, max_tokens):
        inputs, _ = collate(b)
        z = np.array(option_logits(model, pointer, enc.letters, inputs))
        for r, zr in zip(b, z, strict=False):
            iid, order = r[4]
            k = len(order)
            canon = np.empty(k, dtype=np.float64)
            canon[list(order)] = zr[:k]
            out.setdefault(iid, []).append(canon)
    return out


def probs_at(zs, T):
    ps = [np.exp((z - z.max()) / T) for z in zs]
    ps = [p / p.sum() for p in ps]
    return sum(ps) / len(ps), ps


def fit_temperature(items, logits):
    grid = np.exp(np.linspace(math.log(0.05), math.log(20.0), 301))
    best = min(
        grid,
        key=lambda T: -np.mean([math.log(max(probs_at(logits[it["id"]], T)[0][it["gold"]], 1e-12)) for it in items]),
    )
    return float(best)


MIN_TEMP_ITEMS = 100


def temp_key(it):
    return f"{it['type']}/{'pl' if it.get('language') == 'pl' else 'other'}"


def fit_temperatures(items, logits):
    """One temperature per question type and per (type, language group: pl / other). Groups with fewer than
    MIN_TEMP_ITEMS calibration items fall back to the type temperature. A single per-type temperature fitted on Polish
    calibration data left English sets at ECE 0.03-0.10."""
    temps = {}
    for t in sorted({it["type"] for it in items}):
        of_type = [it for it in items if it["type"] == t]
        temps[t] = fit_temperature(of_type, logits)
        for group in ("pl", "other"):
            sub = [it for it in of_type if temp_key(it) == f"{t}/{group}"]
            if len(sub) >= MIN_TEMP_ITEMS:
                temps[f"{t}/{group}"] = fit_temperature(sub, logits)
    return temps


def temp_for(temps, it):
    return temps.get(temp_key(it), temps.get(it["type"], 1.0))


def threshold_for(conf, correct, target):
    """Lowest confidence threshold whose accepted set has error <= target (equal confidences accepted together)."""
    order = np.argsort(-conf)
    best = None
    errs = 0
    for n, i in enumerate(order, 1):
        errs += 0 if correct[i] else 1
        if n < len(order) and conf[order[n]] == conf[i]:
            continue
        if errs / n <= target:
            best = float(conf[i])
    return best if best is not None else 1.01


MIN_THRESHOLD_ITEMS = 200


def fit_thresholds(items, logits, temps, targets=(0.01, 0.05)):
    """{target error: {group: threshold}} with groups = (type, language group) as for temperatures, plus "all" as
    the fallback for groups with fewer than MIN_THRESHOLD_ITEMS calibration items. One global threshold fitted on mixed
    calibration data accepted 12.4% errors on the Polish test at a 1% target."""
    probs = [probs_at(logits[it["id"]], temp_for(temps, it))[0] for it in items]
    conf = np.array([p.max() for p in probs])
    ok = np.array([int(np.argmax(p)) == it["gold"] for p, it in zip(probs, items, strict=False)])
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[temp_key(it)].append(i)
    out = {}
    for t in targets:
        out[str(t)] = {"all": threshold_for(conf, ok, t)}
        for g, idx in sorted(groups.items()):
            if len(idx) >= MIN_THRESHOLD_ITEMS:
                out[str(t)][g] = threshold_for(conf[idx], ok[idx], t)
    return out


def metrics(items, logits, temps, thresholds=None):
    rec = defaultdict(list)
    for it in items:
        p, ps = probs_at(logits[it["id"]], temp_for(temps, it))
        g = it["gold"]
        rec["correct"].append(int(np.argmax(p)) == g)
        rec["nll"].append(-math.log(max(p[g], 1e-12)))
        rec["brier"].append(float(((p - np.eye(len(p))[g]) ** 2).sum()))
        rec["conf"].append(float(p.max()))
        rec["flip"].append(int(np.argmax(ps[0])) != int(np.argmax(ps[1])))
        rec["chance"].append(1 / len(p))
    conf, correct = np.array(rec["conf"]), np.array(rec["correct"])
    keys = [temp_key(it) for it in items]
    bins = np.minimum((conf * 15).astype(int), 14)
    ece = sum(
        abs(correct[bins == b].mean() - conf[bins == b].mean()) * (bins == b).mean()
        for b in range(15)
        if (bins == b).any()
    )
    out = {
        "n": len(items),
        "accuracy": float(correct.mean()),
        "chance": float(np.mean(rec["chance"])),
        "nll": float(np.mean(rec["nll"])),
        "brier": float(np.mean(rec["brier"])),
        "ece": float(ece),
        "flip_rate": float(np.mean(rec["flip"])),
    }
    for tgt, by_group in (thresholds or {}).items():
        acc = conf >= np.array([by_group.get(k, by_group["all"]) for k in keys])
        out[f"coverage@{tgt}"] = float(acc.mean())
        out[f"error@{tgt}"] = float(1 - correct[acc].mean()) if acc.any() else None
    return out


def grouped(items, logits, temps, key):
    groups = defaultdict(list)
    for it in items:
        groups[it.get(key, "?")].append(it)
    return {g: metrics(v, logits, temps) for g, v in sorted(groups.items())}


def parity(model, pointer, enc, items):
    """Max |Δp| of the option distribution between a mixed batch and batch size 1 (MoE determinism gate)."""
    rows = order_rows(enc, items, lambda it: [list(range(len(it["options"])))])
    inputs, _ = collate(rows)
    batched = mx.softmax(option_logits(model, pointer, enc.letters, inputs), axis=-1)
    worst = 0.0
    for i, r in enumerate(rows):
        single = mx.softmax(option_logits(model, pointer, enc.letters, collate([r])[0]), axis=-1)
        worst = max(worst, float(mx.abs(single[0] - batched[i]).max()))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="run under pretrain/work/runs to start from (pretraining or SFT run)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--wd", type=float, default=0.1)
    ap.add_argument("--max-tokens", type=int, default=16384, help="padded tokens per batch")
    ap.add_argument("--max-train", type=int, default=0, help="subsample train items (0 = all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--data", type=Path, default=SFT, help="directory with {train,dev,cal,test}.jsonl")
    ap.add_argument(
        "--readout",
        choices=["pointer", "letter"],
        default="pointer",
        help="pointer: option-pointer head (default); letter: option-letter logits",
    )
    ap.add_argument(
        "--extra-eval",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="additional held-out JSONL scored once with the calibrated model (repeatable)",
    )
    a = ap.parse_args()
    random.seed(a.seed)
    # Batches have varying shapes; without a cap MLX keeps every freed buffer size cached and the process grows until
    # macOS kills it (observed: 78 GB compressed memory during a dry run).
    mx.set_cache_limit(4 << 30)

    base, run = ROOT / "work" / "runs" / a.base, ROOT / "work" / "runs" / a.name
    run.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    enc = Encoder(tok)
    split = {s: load_jsonl(a.data / f"{s}.jsonl") for s in ("train", "dev", "cal", "test")}
    if a.max_train:
        split["train"] = random.sample(split["train"], min(a.max_train, len(split["train"])))
    print({s: len(v) for s, v in split.items()}, flush=True)

    if not a.eval_only:
        model, cfg, biases, base_pointer = load_model(base)
        pointer = (base_pointer or Pointer(cfg.d)) if a.readout == "pointer" else None
        flat = tree_flatten(model.trainable_parameters())
        router = {k: v for k, v in flat if ".router." in f".{k}."}
        params = {"model": tree_unflatten([(k, v) for k, v in flat if ".router." not in f".{k}."])}
        if pointer is not None:
            params["pointer"] = pointer.trainable_parameters()

        def loss_fn(p, inputs, target):
            """Cross-entropy against the (soft) target distribution over the shown options."""
            model.update(cast_params(p["model"], mx.bfloat16))
            if pointer is not None:
                pointer.update(p["pointer"])
            z = option_logits(model, pointer, enc.letters, inputs)
            return -(target * (z - mx.logsumexp(z, axis=-1, keepdims=True))).sum(-1).mean()

        grad = mx.value_and_grad(loss_fn)
        decay = optim.AdamW(learning_rate=a.lr, betas=[0.9, 0.95], weight_decay=a.wd)
        no_decay = optim.AdamW(learning_rate=a.lr, betas=[0.9, 0.95], weight_decay=0.0)
        opt = optim.MultiOptimizer([decay, no_decay], [lambda path, w: w.ndim >= 2])
        n_train = len(split["train"])
        steps_per_epoch = None
        total = None
        step, best = 0, (float("inf"), -1)
        log = (run / "sft.jsonl").open("w")
        for epoch in range(a.epochs):
            rows = order_rows(
                enc,
                split["train"],
                lambda it: [random.sample(range(len(it["options"])), len(it["options"]))],
                cache=False,
            )
            bs = batches(rows, a.max_tokens, rng=random)
            random.shuffle(bs)
            if total is None:
                steps_per_epoch = len(bs)
                total = steps_per_epoch * a.epochs
            t0, seen, recent = time.perf_counter(), 0, []
            for b in bs:
                lr = (
                    a.lr * (step + 1) / a.warmup
                    if step < a.warmup
                    else a.lr
                    * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (step - a.warmup) / max(1, total - a.warmup))))
                )
                for o in opt.optimizers:
                    o.learning_rate = lr
                inputs, target = collate(b)
                loss, g = grad(params, inputs, target)
                g, _ = optim.clip_grad_norm(g, 1.0)
                params = opt.apply_gradients(g, params)
                mx.eval(params, opt.state, loss)
                step += 1
                seen += len(b)
                recent.append(float(loss))
                if step % 50 == 0:
                    mean = sum(recent) / len(recent)
                    recent = []
                    print(
                        f"epoch {epoch} step {step}/{total} loss(avg50) {mean:.4f} lr {lr:.2e} "
                        f"{seen / (time.perf_counter() - t0):.0f} items/s",
                        flush=True,
                    )
                    log.write(json.dumps({"epoch": epoch, "step": step, "loss": mean, "lr": lr}) + "\n")
            model.update(cast_params(params["model"], mx.float32))
            model.update(tree_unflatten(list(router.items())))
            if pointer is not None:
                pointer.update(params["pointer"])
            dev_logits = predict(model, pointer, enc, split["dev"], a.max_tokens)
            dev = metrics(split["dev"], dev_logits, {})
            # Select on dev NLL after per-type temperature (fitted on dev): calibration is applied post hoc anyway, so
            # raw NLL would penalise later, sharper epochs that are more accurate.
            dev_temps = fit_temperatures(split["dev"], dev_logits)
            dev["nll_tempered"] = metrics(split["dev"], dev_logits, dev_temps)["nll"]
            print(f"epoch {epoch} dev {json.dumps(dev)}", flush=True)
            log.write(json.dumps({"epoch": epoch, "dev": dev}) + "\n")
            log.flush()
            if dev["nll_tempered"] < best[0]:
                best = (dev["nll_tempered"], epoch)
                w = dict(tree_flatten(model.trainable_parameters()))
                w.update({f"blocks.{i}.moe.balance_bias": b for i, b in enumerate(biases)})
                if pointer is not None:
                    w.update({f"pointer.{k}": v for k, v in tree_flatten(pointer.trainable_parameters())})
                mx.save_safetensors(str(run / "model.safetensors"), w)
        log.close()
        (run / "config.json").write_text(
            json.dumps(
                {
                    "model": cfg.to_dict(),
                    "sft": vars(a),
                    "base": a.base,
                    "best_epoch": best[1],
                    "items_train": n_train,
                    "steps_per_epoch": steps_per_epoch,
                },
                indent=2,
                default=str,
            )
        )

    model, cfg, _, pointer = load_model(run)
    cal_logits = predict(model, pointer, enc, split["cal"], a.max_tokens)
    temps = fit_temperatures(split["cal"], cal_logits)
    thresholds = fit_thresholds(split["cal"], cal_logits, temps)
    (run / "calibration.json").write_text(json.dumps({"temperatures": temps, "thresholds": thresholds}, indent=2))

    test_logits = predict(model, pointer, enc, split["test"], a.max_tokens)
    extra = {}
    for spec in a.extra_eval:
        name, path = spec.split("=", 1)
        items = load_jsonl(path)
        logits = predict(model, pointer, enc, items, a.max_tokens)
        extra[name] = {
            "all": metrics(items, logits, temps, thresholds),
            "by_type": grouped(items, logits, temps, "type"),
            "by_language": grouped(items, logits, temps, "language"),
        }
    report = {
        "temperatures": temps,
        "thresholds": thresholds,
        "test_uncalibrated": metrics(split["test"], test_logits, {}),
        "test": metrics(split["test"], test_logits, temps, thresholds),
        "test_by_family": grouped(split["test"], test_logits, temps, "family"),
        "test_by_type": grouped(split["test"], test_logits, temps, "type"),
        "test_by_language": grouped(split["test"], test_logits, temps, "language"),
        "router_parity_max_abs_dp": parity(model, pointer, enc, split["test"][:64]),
        "extra": extra,
    }
    (run / "eval.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {k: report[k] for k in ("temperatures", "thresholds", "test", "test_by_type", "router_parity_max_abs_dp")},
            indent=2,
        ),
        flush=True,
    )
    for name, r in extra.items():
        print(name, json.dumps(r["all"]), flush=True)


if __name__ == "__main__":
    main()
