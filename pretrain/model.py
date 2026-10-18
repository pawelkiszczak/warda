"""warda-scratch MoE decoder for MLX.

GQA attention with QK-norm and RoPE; every block's FFN is a fine-grained mixture of experts: sigmoid router computed in
fp32 (measured: with bf16 routing a prompt's answer depends on the batch composition around it), top-k routed experts
with renormalised gates and one always-on shared expert. Balancing has two parts: DeepSeek-V3 aux-loss-free selection
bias (nudged by the trainer after each step towards uniform load) and a Switch-style balance loss (OLMoE uses 0.01),
because the bias alone is too slow for a few-thousand-step run (routing collapsed onto 4 of 32 experts without it).
Embeddings are tied.

`Model(tokens)` returns `(logits, loads, balance_loss)`; `loads` is a (layers, n_experts) array of routed-token counts
that the trainer uses to update the selection bias.
"""

import math
from dataclasses import asdict, dataclass

import mlx.core as mx
from mlx import nn
from mlx.utils import tree_flatten, tree_map_with_path
from mlx_lm.models.switch_layers import SwitchGLU


@dataclass
class Config:
    vocab: int = 32000
    d: int = 512
    layers: int = 8
    heads: int = 8
    kv_heads: int = 2
    n_experts: int = 32
    expert_ff: int = 256
    top_k: int = 4
    shared_ff: int = 256
    rope_base: float = 10000.0
    norm_eps: float = 1e-5

    def to_dict(self):
        return asdict(self)


class Attention(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.h, self.kv, self.hd = c.heads, c.kv_heads, c.d // c.heads
        self.q_proj = nn.Linear(c.d, c.heads * self.hd, bias=False)
        self.k_proj = nn.Linear(c.d, c.kv_heads * self.hd, bias=False)
        self.v_proj = nn.Linear(c.d, c.kv_heads * self.hd, bias=False)
        self.o_proj = nn.Linear(c.heads * self.hd, c.d, bias=False)
        self.q_norm = nn.RMSNorm(self.hd, eps=c.norm_eps)
        self.k_norm = nn.RMSNorm(self.hd, eps=c.norm_eps)
        self.rope = nn.RoPE(self.hd, base=c.rope_base)

    def __call__(self, x, mask):
        B, L, _ = x.shape
        q = self.q_norm(self.q_proj(x).reshape(B, L, self.h, self.hd)).transpose(0, 2, 1, 3)
        k = self.k_norm(self.k_proj(x).reshape(B, L, self.kv, self.hd)).transpose(0, 2, 1, 3)
        v = self.v_proj(x).reshape(B, L, self.kv, self.hd).transpose(0, 2, 1, 3)
        q, k = self.rope(q), self.rope(k)
        o = mx.fast.scaled_dot_product_attention(q, k, v, scale=self.hd**-0.5, mask=mask)
        return self.o_proj(o.transpose(0, 2, 1, 3).reshape(B, L, -1))


class MoE(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.k, self.n = c.top_k, c.n_experts
        self.router = nn.Linear(c.d, c.n_experts, bias=False)
        self.experts = SwitchGLU(c.d, c.expert_ff, c.n_experts)
        self.shared_gate = nn.Linear(c.d, c.shared_ff, bias=False)
        self.shared_up = nn.Linear(c.d, c.shared_ff, bias=False)
        self.shared_down = nn.Linear(c.shared_ff, c.d, bias=False)
        self.balance_bias = mx.zeros((c.n_experts,))  # frozen; updated by the trainer, selection only

    def __call__(self, x):
        scores = mx.sigmoid(x.astype(mx.float32) @ self.router.weight.astype(mx.float32).T)
        sel = scores + mx.stop_gradient(self.balance_bias.astype(mx.float32))
        idx = mx.stop_gradient(mx.argpartition(-sel, kth=self.k - 1, axis=-1)[..., : self.k])
        g = mx.take_along_axis(scores, idx, axis=-1)
        g = (g / g.sum(-1, keepdims=True)).astype(x.dtype)
        y = (self.experts(x, idx) * g[..., None]).sum(-2)
        y = y + self.shared_down(nn.silu(self.shared_gate(x)) * self.shared_up(x))
        load = mx.zeros((self.n,), mx.float32).at[idx.reshape(-1)].add(1.0)
        # Switch-style balance loss n * sum_i f_i * P_i (f: routed share, no grad; P: mean normalised affinity)
        affinity = (scores / scores.sum(-1, keepdims=True)).reshape(-1, self.n).mean(0)
        aux = self.n * (mx.stop_gradient(load / load.sum()) * affinity).sum()
        return y, load, aux


class Block(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.attn_norm = nn.RMSNorm(c.d, eps=c.norm_eps)
        self.attn = Attention(c)
        self.ffn_norm = nn.RMSNorm(c.d, eps=c.norm_eps)
        self.moe = MoE(c)

    def __call__(self, x, mask):
        x = x + self.attn(self.attn_norm(x), mask)
        y, load, aux = self.moe(self.ffn_norm(x))
        return x + y, load, aux


class Model(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.config = c
        self.embed = nn.Embedding(c.vocab, c.d)
        self.blocks = [Block(c) for _ in range(c.layers)]
        self.norm = nn.RMSNorm(c.d, eps=c.norm_eps)
        self.freeze(keys=["balance_bias"], strict=False)

    def hidden(self, tokens, mask="causal"):
        """Final normed hidden states (B, L, d), routed-token counts (layers, n_experts), mean balance loss."""
        x = self.embed(tokens)
        loads, auxes = [], []
        for b in self.blocks:
            x, load, aux = b(x, mask)
            loads.append(load)
            auxes.append(aux)
        return self.norm(x), mx.stack(loads), mx.stack(auxes).mean()

    def __call__(self, tokens, mask="causal"):
        """Returns (logits, per-layer routed-token counts (layers, n_experts), mean balance loss)."""
        h, loads, aux = self.hidden(tokens, mask)
        return self.embed.as_linear(h), loads, aux

    def init_weights(self, seed=0):
        """GPT-2 style: N(0, 0.02); residual output projections scaled by 1/sqrt(2*layers)."""
        mx.random.seed(seed)
        resid = 0.02 / math.sqrt(2 * self.config.layers)

        def init(path, p):
            if p.ndim < 2:
                return p
            std = resid if path.endswith(("o_proj.weight", "down_proj.weight", "shared_down.weight")) else 0.02
            return mx.random.normal(p.shape) * std

        self.update(tree_map_with_path(init, self.trainable_parameters()))

    def balance_biases(self):
        return [b.moe.balance_bias for b in self.blocks]

    def set_balance_biases(self, biases):
        for b, v in zip(self.blocks, biases, strict=False):
            b.moe.balance_bias = v


def param_counts(model: Model):
    total = sum(v.size for _, v in tree_flatten(model.trainable_parameters()))
    c = model.config
    routed = c.layers * c.n_experts * 3 * c.d * c.expert_ff
    active = total - routed + c.layers * c.top_k * 3 * c.d * c.expert_ff
    return {"total": total, "active": active, "active_non_embedding": active - c.vocab * c.d}
