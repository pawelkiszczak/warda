"""Pretrain the warda-scratch MoE from scratch on the token bins written by `pretrain/data/` (MLX, Apple Silicon).

Mixed precision: fp32 master weights and AdamW state; the forward/backward runs in bf16 except the routers (fp32).
Schedule: warmup -> stable -> linear decay to 0 (WSD). Data: `train.bin` cut into non-overlapping (seq+1)-token chunks,
visited in a seeded random order (one epoch = every chunk once). MoE balancing: Switch-style balance loss
(`--aux-coef`) plus DeepSeek-V3 selection bias moved by `--balance-rate` towards uniform load after every step.
The logged/validated `loss` is the LM cross-entropy only.

Writes `pretrain/work/runs/<name>/`: `metrics.jsonl`, `ckpt/` (latest, resumable), `model.safetensors` + `config.json`.

    uv run python pretrain/train.py --name s126m-1b --tokens 1e9
    uv run python pretrain/train.py --name s126m-1b --tokens 1e9 --resume
"""

import argparse
import json
import time
from pathlib import Path

import mlx.core as mx
import mlx.optimizers as optim
import numpy as np
from mlx import nn
from mlx.utils import tree_flatten, tree_map, tree_map_with_path, tree_unflatten
from model import Config, Model, param_counts

ROOT = Path(__file__).resolve().parent
TOKENS = ROOT / "work" / "tokens"
SAMPLE_PROMPTS = ["Polska jest krajem położonym w", "Zgodnie z art. 10 kodeksu pracy", "The capital of France is"]


def cast_params(params, dtype):
    """Compute copy of the masters: routers stay fp32 (routing must not depend on batch rounding)."""
    return tree_map_with_path(lambda p, a: a if ".router." in f".{p}." else a.astype(dtype), params)


def lr_at(step, total, peak, warmup, decay_frac):
    if step < warmup:
        return peak * (step + 1) / warmup
    decay_start = int(total * (1 - decay_frac))
    if step < decay_start:
        return peak
    return peak * max(0.0, (total - step) / max(1, total - decay_start))


class Chunks:
    """Non-overlapping (seq+1)-token windows of a uint16 token stream in seeded random order."""

    def __init__(self, path, seq, seed):
        self.data = np.memmap(path, dtype=np.uint16, mode="r")
        self.seq = seq
        self.n = len(self.data) // (seq + 1)
        self.seed = seed

    def order(self, epoch):
        return np.random.default_rng(self.seed + epoch).permutation(self.n)

    def batch(self, idx):
        rows = np.stack([self.data[i * (self.seq + 1) : (i + 1) * (self.seq + 1)] for i in idx]).astype(np.int32)
        return mx.array(rows[:, :-1]), mx.array(rows[:, 1:])


def make_loss(model, dtype, aux_coef):
    """(total loss, (routed-token counts, LM cross-entropy)); total = CE + aux_coef * balance loss."""

    def loss_fn(params, biases, x, y):
        model.update(cast_params(params, dtype))
        model.set_balance_biases(biases)
        logits, loads, aux = model(x)
        ce = nn.losses.cross_entropy(logits.astype(mx.float32), y, reduction="mean")
        return ce + aux_coef * aux, (loads, ce)

    return loss_fn


def greedy(model, tok, prompt, n=24):
    ids = tok(prompt, add_special_tokens=False).input_ids
    ids = [1, *ids]
    for _ in range(n):
        logits, _, _ = model(mx.array([ids]))
        nxt = int(mx.argmax(logits[0, -1]))
        if nxt == 2:
            break
        ids.append(nxt)
    return tok.decode(ids[1:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--tokens", type=float, default=1e9, help="training token budget")
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--micro", type=int, default=16, help="sequences per micro-batch")
    ap.add_argument("--accum", type=int, default=8, help="micro-batches per optimizer step")
    ap.add_argument("--lr", type=float, default=1.2e-3)
    ap.add_argument("--warmup", type=int, default=150)
    ap.add_argument("--decay-frac", type=float, default=0.2)
    ap.add_argument("--wd", type=float, default=0.1)
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--balance-rate", type=float, default=1e-3)
    ap.add_argument("--aux-coef", type=float, default=1e-2, help="Switch-style balance loss weight (OLMoE: 0.01)")
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument("--eval-seqs", type=int, default=32, help="sequences per validation source")
    ap.add_argument("--ckpt-every", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--data", type=Path, default=TOKENS, help="directory with train.bin and val_<source>.bin")
    a = ap.parse_args()

    run = ROOT / "work" / "runs" / a.name
    (run / "ckpt").mkdir(parents=True, exist_ok=True)
    cfg = Config()
    model = Model(cfg)
    model.init_weights(a.seed)
    counts = param_counts(model)
    tok_per_step = a.micro * a.accum * a.seq
    total_steps = int(a.tokens // tok_per_step)

    decay = optim.AdamW(learning_rate=a.lr, betas=[0.9, 0.95], eps=1e-8, weight_decay=a.wd)
    no_decay = optim.AdamW(learning_rate=a.lr, betas=[0.9, 0.95], eps=1e-8, weight_decay=0.0)
    opt = optim.MultiOptimizer([decay, no_decay], [lambda path, w: w.ndim >= 2])

    params = model.trainable_parameters()
    biases = [mx.zeros((cfg.n_experts,)) for _ in range(cfg.layers)]
    step = 0
    if a.resume and (run / "ckpt" / "state.json").exists():
        st = json.loads((run / "ckpt" / "state.json").read_text())
        params = tree_unflatten(list(mx.load(str(run / "ckpt" / "params.safetensors")).items()))
        b = mx.load(str(run / "ckpt" / "biases.safetensors"))
        biases = [b[str(i)] for i in range(cfg.layers)]
        opt.init(params)
        opt.state = tree_unflatten(list(mx.load(str(run / "ckpt" / "opt.safetensors")).items()))
        step = st["step"]
        print(f"resumed at step {step}", flush=True)
    (run / "config.json").write_text(
        json.dumps({"model": cfg.to_dict(), "train": vars(a), "params": counts}, indent=2, default=str)
    )

    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("speakleash/Bielik-1.5B-v3.0-Instruct")
    train = Chunks(a.data / "train.bin", a.seq, a.seed)
    val_sources = {p.stem[4:]: Chunks(p, a.seq, 0) for p in sorted(a.data.glob("val_*.bin"))}
    print(
        f"params {counts} | train chunks {train.n:,} ({train.n * (a.seq + 1) / 1e9:.2f}B tok) | "
        f"{total_steps} steps x {tok_per_step:,} tok | val sources {list(val_sources)}",
        flush=True,
    )

    loss_and_grad = mx.value_and_grad(make_loss(model, mx.bfloat16, a.aux_coef))
    micro = mx.compile(loss_and_grad)
    loss_only = mx.compile(make_loss(model, mx.bfloat16, a.aux_coef))

    def evaluate():
        out = {}
        for name, ch in val_sources.items():
            losses = []
            for i in range(0, min(a.eval_seqs, ch.n), a.micro):
                x, y = ch.batch(range(i, min(i + a.micro, a.eval_seqs, ch.n)))
                _, (_, ce) = loss_only(params, biases, x, y)
                losses.append(float(ce))
            out[name] = sum(losses) / len(losses)
        out["mean"] = sum(out.values()) / len(out)
        return out

    def checkpoint():
        mx.save_safetensors(str(run / "ckpt" / "params.safetensors"), dict(tree_flatten(params)))
        mx.save_safetensors(str(run / "ckpt" / "biases.safetensors"), {str(i): b for i, b in enumerate(biases)})
        mx.save_safetensors(str(run / "ckpt" / "opt.safetensors"), dict(tree_flatten(opt.state)))
        (run / "ckpt" / "state.json").write_text(json.dumps({"step": step}))

    log = open(run / "metrics.jsonl", "a")
    per_epoch = train.n // (a.micro * a.accum)
    if per_epoch == 0:
        raise SystemExit(
            f"training data too small: {train.n} chunks give no full optimizer step at "
            f"micro={a.micro} x accum={a.accum}; lower --micro/--accum or add data"
        )
    t_last, tok_since = time.perf_counter(), 0
    while step < total_steps:
        lr = lr_at(step, total_steps, a.lr, a.warmup, a.decay_frac)
        for o in opt.optimizers:
            o.learning_rate = lr
        epoch, pos = divmod(step, per_epoch)
        order = train.order(epoch)
        grads_acc, loads_acc, loss_acc = None, None, 0.0
        for m in range(a.accum):
            s = (pos * a.accum + m) * a.micro
            x, y = train.batch(order[s : s + a.micro])
            (_, (loads, loss)), grads = micro(params, biases, x, y)
            grads_acc = grads if grads_acc is None else tree_map(mx.add, grads_acc, grads)
            loads_acc = loads if loads_acc is None else loads_acc + loads
            loss_acc = loss_acc + loss
            mx.eval(grads_acc, loads_acc, loss_acc)  # bound memory: one micro-batch graph at a time
        if grads_acc is None or loads_acc is None:
            raise RuntimeError("gradient accumulation produced no micro-batches")
        grads_acc = tree_map(lambda g: g / a.accum, grads_acc)
        grads_acc, gnorm = optim.clip_grad_norm(grads_acc, a.clip)
        params = opt.apply_gradients(grads_acc, params)
        mean_load = loads_acc.mean(axis=1, keepdims=True)
        new_b = mx.stack(biases) + a.balance_rate * mx.sign(mean_load - loads_acc)
        biases = [new_b[i] for i in range(cfg.layers)]
        imbalance = (loads_acc.max(axis=1) / mean_load[:, 0]).max()
        mx.eval(params, opt.state, biases, loss_acc, gnorm, imbalance)
        step += 1
        tok_since += tok_per_step
        rec = {
            "step": step,
            "loss": float(loss_acc) / a.accum,
            "lr": lr,
            "gnorm": float(gnorm),
            "max_load_ratio": float(imbalance),
            "tokens": step * tok_per_step,
        }
        if step % 10 == 0 or step == 1:
            dt = time.perf_counter() - t_last
            rec["tok_s"] = tok_since / dt
            eta_h = (total_steps - step) * tok_per_step / rec["tok_s"] / 3600
            print(
                f"step {step}/{total_steps} loss {rec['loss']:.4f} lr {lr:.2e} gnorm {rec['gnorm']:.2f} "
                f"maxload {rec['max_load_ratio']:.2f} {rec['tok_s']:,.0f} tok/s eta {eta_h:.1f} h",
                flush=True,
            )
            t_last, tok_since = time.perf_counter(), 0
        if step % a.eval_every == 0 or step == total_steps:
            rec["val"] = evaluate()
            model.update(cast_params(params, mx.float32))
            model.set_balance_biases(biases)
            rec["samples"] = [greedy(model, tok, p) for p in SAMPLE_PROMPTS]
            print(f"  val {json.dumps(rec['val'])}\n  " + "\n  ".join(rec["samples"]), flush=True)
        log.write(json.dumps(rec) + "\n")
        log.flush()
        if step % a.ckpt_every == 0 or step == total_steps:
            checkpoint()

    final = cast_params(params, mx.float32)
    weights = dict(tree_flatten(final))
    weights.update({f"blocks.{i}.moe.balance_bias": b for i, b in enumerate(biases)})
    mx.save_safetensors(str(run / "model.safetensors"), weights)
    print(f"done: {run / 'model.safetensors'}", flush=True)


if __name__ == "__main__":
    main()
