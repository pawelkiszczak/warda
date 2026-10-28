"""Run the Brama v0 pilot: one decider over the example set, then score every saved run.

    uv run python -m warda.bench.run_brama run --decider always_allow
    uv run --with torch python -m warda.bench.run_brama run --decider hf --model speakleash/Bielik-PL-Minitron-7B-v3.0-Instruct
    uv run --with "gliner2[local]" python -m warda.bench.run_brama run --decider gliner2 --model fastino/GLiNER2.5-multi-Decide
    uv run python -m warda.bench.run_brama run --decider systemone --endpoint http://127.0.0.1:8000 --model Remek/basal-2.0-4.5B
    uv run python -m warda.bench.run_brama report

Every decider returns a distribution over the four actions. Model deciders are read in the canonical and the reversed
option order and the two distributions are averaged (R-13). Runs are written as one JSONL per decider (only ids and
probabilities, no item text) next to a `.meta.json` with the model revision, dataset hash and hardware.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import time
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pretrain.prompt import letter_ids, render
from warda.bench import brama
from warda.schema import ACTIONS

RUNS = brama.ROOT / "docs/bench/results/brama-v0"
Probs = dict[str, float]
Decider = Callable[[brama.Case], tuple[Probs, Probs]]  # canonical-order and reversed-order distributions


def _onehot(action: str) -> Probs:
    return {a: float(a == action) for a in ACTIONS}


def constant(action: str) -> Decider:
    return lambda case: (_onehot(action), _onehot(action))


SAFE_HIT_SUFFIXES = (":documented_dummy", ":reserved_domain", ":invalid_checksum")
CREDENTIAL_HITS = ("api_key", "password", "private_key")


def tier1(case: brama.Case) -> tuple[Probs, Probs]:
    """The deterministic tier-1 rule alone: a credential hit blocks, any other identifier hit redacts, nothing allows."""
    hits = [h for h in case.facts.get("tier1_hits", []) if not h.endswith(SAFE_HIT_SUFFIXES)]
    action = "block" if any(h in CREDENTIAL_HITS for h in hits) else "redact" if hits else "allow"
    return _onehot(action), _onehot(action)


def hf_decider(model_id: str, device: str | None, load_8bit: bool = False) -> tuple[Decider, dict[str, Any]]:
    """A causal LM read through Warda's letter prompt (`pretrain/prompt.py`). `load_8bit` loads the weights as
    bitsandbytes LLM.int8 (for 11B+ models on a 24 GB card)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = device or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(model_id)
    if load_8bit:
        from transformers import BitsAndBytesConfig

        quant = BitsAndBytesConfig(load_in_8bit=True)
        model: Any = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=torch.bfloat16, quantization_config=quant, device_map={"": device}
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.bfloat16)
        model = model.to(device)
    model = model.eval()

    def read(case: brama.Case, order: Sequence[str]) -> Probs:
        lang = case.input.language
        options = [brama.OPTION_TEXT[lang][a] for a in order]
        prompt = render(tok, brama.render_state(case), brama.QUESTION[lang], options, lang)
        ids = letter_ids(tok, prompt, len(order))
        if ids is None:
            raise SystemExit(f"{model_id}: option letters are not single tokens at the answer slot")
        enc = tok(prompt, add_special_tokens=False, return_tensors="pt").to(device)
        with torch.inference_mode():
            logits = model(**enc).logits[0, -1].float()
        p = torch.softmax(logits[ids], dim=-1).tolist()
        return dict(zip(order, p, strict=True))

    def decide(case: brama.Case) -> tuple[Probs, Probs]:
        return read(case, ACTIONS), read(case, ACTIONS[::-1])

    dtype = "int8 (bitsandbytes)" if load_8bit else "bfloat16"
    return decide, {"device": device, "dtype": dtype, "revision": _hf_revision(model_id)}


GLINER_LABELS = {
    "allow": "allow: the policy permits sending this content to this destination unchanged",
    "redact": "redact: remove the protected personal data from the content, then send the rest",
    "ask_user": "ask_user: the policy does not settle this case or a needed fact is unknown, so ask the user",
    "block": "block: the policy forbids sending this content to this destination",
}


def gliner_decider(model_id: str, device: str | None, with_policy: bool) -> tuple[Decider, dict[str, Any]]:
    """A GLiNER2 classifier: one single-label task over the four actions. With `with_policy` it reads the same state
    text as the LLM (~1,000 subword tokens, past the 512 positions its mDeBERTa encoder was trained on); without, a
    short state where the policy is named but not included."""
    from gliner2.classification import ClassificationSchema, Classifier

    clf = Classifier.from_pretrained(model_id)
    if device:  # `from_pretrained(device=...)` leaves the weights on the CPU in gliner2 2.1, so move them explicitly
        clf = clf.to(device=device)
    schemas = {
        order: ClassificationSchema().single("decision", {a: GLINER_LABELS[a] for a in order})
        for order in (ACTIONS, ACTIONS[::-1])
    }

    def decide(case: brama.Case) -> tuple[Probs, Probs]:
        text = brama.render_state(case, with_policy=with_policy)
        out = []
        for order in (ACTIONS, ACTIONS[::-1]):
            p = dict(clf.classify(text, schemas[order]).probabilities("decision"))
            total = sum(p.values()) or 1.0
            out.append({a: p[a] / total for a in ACTIONS})
        return out[0], out[1]

    return decide, {
        "device": str(clf.scorer.device) if hasattr(clf.scorer, "device") else device,
        "revision": _hf_revision(model_id),
        "input": "state" if with_policy else "state_without_policy",
    }


def _post(url: str, body: dict[str, Any], timeout: float = 600.0) -> dict[str, Any]:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json"})  # noqa: S310 -- local decision server named on the command line.
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- local decision server named on the command line.
        return json.loads(resp.read())


def systemone_decider(
    endpoint: str, model_id: str | None, key: str = "action", request_model: str | None = None
) -> tuple[Decider, dict[str, Any]]:
    """A System-1 decision model behind `POST /v1/systemone` (basal-serve, vLLM Semantic Router, decider-ai,
    `warda.bench.systemone_shim`): one `choice` question over the four actions with the same state, question and
    option texts as the LLM prompt, asked once per option order. The model's own probabilities are used as returned.
    `key` names the question (some servers accept one fixed name, e.g. torchcast's `decision`); `request_model` is
    the request's `model` field when the server knows the model by its own name (Winnow: `Winnow-12B`), not
    `model_id`."""
    url = endpoint.rstrip("/") + "/v1/systemone"

    def ask(case: brama.Case, order: Sequence[str]) -> Probs:
        lang = case.input.language
        question: dict[str, Any] = {"type": "choice", "instructions": brama.QUESTION[lang]}
        question["criteria"] = {a: brama.OPTION_TEXT[lang][a] for a in order}
        body: dict[str, Any] = {"state": brama.render_state(case), "questions": {key: question}}
        if request_model or model_id:
            body["model"] = request_model or model_id
        p = _post(url, body)["answers"][key]["probabilities"]
        total = sum(p[a] for a in ACTIONS) or 1.0
        return {a: p[a] / total for a in ACTIONS}

    def decide(case: brama.Case) -> tuple[Probs, Probs]:
        return ask(case, ACTIONS), ask(case, ACTIONS[::-1])

    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/v1/models", timeout=30) as resp:  # noqa: S310 -- as above.
            served: Any = json.loads(resp.read())
    except Exception:  # not every server lists its models
        served = None
    meta = {"endpoint": url, "served": served, "revision": _hf_revision(model_id) if model_id else None}
    meta |= {"question_key": key} if key != "action" else {}
    return decide, meta | ({"request_model": request_model} if request_model else {})


def _hf_revision(model_id: str) -> str | None:
    try:
        from huggingface_hub import model_info

        return model_info(model_id).sha
    except Exception:  # offline or gated: the run still records the model id
        return None


def _hardware() -> str:
    gpu = ""
    try:
        import torch

        if torch.cuda.is_available():
            gpu = f", {torch.cuda.get_device_name(0)}"
    except ImportError:  # e.g. a systemone run, where the model runs in its server: name the local GPU, if any
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],  # noqa: S607 -- nvidia-smi from PATH.
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            names = out.stdout.split("\n")[0].strip()
            gpu = f", {names}" if names else ""
        except (OSError, subprocess.SubprocessError):
            pass
    return f"{platform.system()} {platform.machine()}{gpu}"


def run(args: argparse.Namespace) -> None:
    items = brama.load_items(args.items)
    policies = brama.load_policies(args.policies)
    ids = brama.load_ids(args.ids, items)
    if args.limit:
        items = items[: args.limit]
    meta: dict[str, Any] = {}
    if args.decider == "hf":
        decide, meta = hf_decider(args.model, args.device, args.load_8bit)
    elif args.decider == "gliner2":
        decide, meta = gliner_decider(args.model, args.device, not args.no_policy_text)
    elif args.decider == "systemone":
        decide, meta = systemone_decider(args.endpoint, args.model, args.question_key, args.request_model)
    elif args.decider == "tier1":
        decide = tier1
    else:
        decide = constant(args.decider.removeprefix("always_"))
    name = args.name or (args.model.split("/")[-1] if args.model else args.decider)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.perf_counter()
    for k, item in enumerate(items, 1):
        case = brama.decider_view(item, policies, ids)
        t0 = time.perf_counter()
        canonical, reversed_ = decide(case)
        ms = (time.perf_counter() - t0) * 1000
        mean = {a: (canonical[a] + reversed_[a]) / 2 for a in ACTIONS}
        rows.append(
            {"id": item["id"], "probs": mean, "canonical": canonical, "reversed": reversed_, "ms": round(ms, 1)}
        )
        if k % 10 == 0 or k == len(items):
            print(f"{name}: {k}/{len(items)}", flush=True)
    path = args.out / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    meta |= {
        "name": name,
        "decider": args.decider,
        "model": args.model,
        "items": len(rows),
        "dataset_sha256": brama.dataset_sha256(args.items, args.ids, *sorted(args.policies.glob("*.md"))),
        "states_sha256": brama.states_sha256(items, policies, ids),
        "hardware": _hardware(),
        "seconds": round(time.perf_counter() - started, 1),
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
    } | dict(kv.split("=", 1) for kv in args.meta)
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)


def _fmt(x: float | None, pct: bool = True) -> str:
    if x is None or math.isnan(x):
        return "n/a"
    return f"{100 * x:.1f}" if pct else f"{x:.3f}"


def _acc(items: Sequence[dict], probs: Sequence[Probs]) -> float:
    return brama.score(items, probs)["acceptable_acc"]


def _catch(items: Sequence[dict], probs: Sequence[Probs]) -> float:
    return brama.catch_at_uir(items, probs)[0]


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(row) + " |")
    print()


def report(args: argparse.Namespace) -> None:
    """Score every run in `--out` and print the pilot tables (Markdown) plus a `scores.json` next to the runs."""
    items = brama.load_items(args.items)
    states = brama.states_sha256(items, brama.load_policies(args.policies), brama.load_ids(args.ids, items))
    by_id = {it["id"]: it for it in items}
    results, runs = {}, {}
    for path in sorted(args.out.glob("*.jsonl")):
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        if meta.get("states_sha256") != states:
            print(f"warning: {path.stem} was run on different decider inputs (states hash mismatch)", flush=True)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        sub = [by_id[r["id"]] for r in rows]
        probs = [r["probs"] for r in rows]
        s = brama.score(sub, probs)
        s["catch_ci"] = brama.bootstrap(sub, probs, _catch, args.resamples)
        s["acc_ci"] = brama.bootstrap(sub, probs, _acc, args.resamples)
        flips = [brama.argmax(r["canonical"]) != brama.argmax(r["reversed"]) for r in rows]
        s["order_flip_rate"] = sum(flips) / len(flips)
        s["ms_median"] = sorted(r["ms"] for r in rows)[len(rows) // 2]
        results[path.stem], runs[path.stem] = s, (sub, probs)
    if args.baseline in runs:
        base_items, base_probs = runs[args.baseline]
        for name, (sub, probs) in runs.items():
            if name != args.baseline and sub == base_items:
                diff_acc = brama.bootstrap(sub, probs, _acc, args.resamples, other=base_probs)
                diff_catch = brama.bootstrap(sub, probs, _catch, args.resamples, other=base_probs)
                results[name]["vs_baseline"] = {"baseline": args.baseline, "acc_ci": diff_acc, "catch_ci": diff_catch}
    (args.out / "scores.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    _table(
        [
            "decider",
            "Catch@UIR5 [95% CI]",
            "acceptable acc [95% CI]",
            "macro-F1",
            "groups",
            "UIR",
            "miss",
            "hard",
            "ECE",
            "Brier",
            "order flips",
            "ms",
        ],
        [
            [
                name,
                f"{_fmt(s['catch_at_uir5'])} [{_fmt(s['catch_ci'][0])}, {_fmt(s['catch_ci'][1])}]",
                f"{_fmt(s['acceptable_acc'])} [{_fmt(s['acc_ci'][0])}, {_fmt(s['acc_ci'][1])}]",
                _fmt(s["macro_f1"]),
                _fmt(s["group_consistency"]),
                _fmt(s["uir_at_argmax"]),
                _fmt(s["miss_at_argmax"]),
                str(s["hard_violations"]),
                _fmt(s["ece"], False),
                _fmt(s["brier"], False),
                _fmt(s["order_flip_rate"]),
                f"{s['ms_median']:.0f}",
            ]
            for name, s in results.items()
        ],
    )
    tracks = [t for t in brama.TRACKS if any(t in s["per_track"] for s in results.values())]
    _table(
        ["decider", *[f"{t} acc / groups" for t in tracks]],
        [
            [name] + [f"{_fmt(s['per_track'][t]['acceptable'])} / {_fmt(s['per_track'][t]['groups'])}" for t in tracks]
            for name, s in results.items()
        ],
    )
    roles = ["safe_pair", "flow_sensitivity", "fact_sensitivity", "policy_sensitivity", "surface_pair", "adv_pair"]
    _table(
        ["decider", *roles, "predicted allow / redact / ask_user / block"],
        [
            [name, *[_fmt(s[r]) for r in roles], " / ".join(_fmt(s["pred_share"][a]) for a in ACTIONS)]
            for name, s in results.items()
        ],
    )
    _table(
        [
            "decider",
            f"Δ acceptable acc vs {args.baseline} [95% CI]",
            f"Δ Catch@UIR5 vs {args.baseline} [95% CI]",
            "hard-invariant violations (ids)",
        ],
        [
            [
                name,
                "[{}, {}]".format(*map(_fmt, s["vs_baseline"]["acc_ci"])) if "vs_baseline" in s else "",
                "[{}, {}]".format(*map(_fmt, s["vs_baseline"]["catch_ci"])) if "vs_baseline" in s else "",
                ", ".join(s["hard_ids"]) or "none",
            ]
            for name, s in results.items()
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("run", "report"):
        p = sub.add_parser(cmd)
        p.add_argument("--items", type=Path, default=brama.EXAMPLES)
        p.add_argument("--ids", type=Path, default=brama.IDS)
        p.add_argument("--policies", type=Path, default=brama.POLICIES)
        p.add_argument("--out", type=Path, default=RUNS)
        if cmd == "run":
            p.add_argument(
                "--decider",
                required=True,
                choices=[
                    "always_allow",
                    "always_redact",
                    "always_ask_user",
                    "always_block",
                    "tier1",
                    "hf",
                    "gliner2",
                    "systemone",
                ],
            )
            p.add_argument("--model", help="Hugging Face id for --decider hf / gliner2 / systemone")
            p.add_argument("--endpoint", help="base URL of a System One server for --decider systemone")
            p.add_argument("--question-key", default="action", help="systemone: the question's name in the request")
            p.add_argument("--request-model", help="systemone: the request's `model` field (default: --model)")
            p.add_argument("--meta", action="append", default=[], help="extra KEY=VALUE recorded in the run's meta")
            p.add_argument("--name", help="run name (default: model basename or decider)")
            p.add_argument("--device", help="torch device (default: cuda, then mps, then cpu)")
            p.add_argument("--limit", type=int, default=0, help="first N items only (smoke runs)")
            p.add_argument("--load-8bit", action="store_true", help="hf: load the weights in 8 bits (bitsandbytes)")
            p.add_argument("--no-policy-text", action="store_true", help="gliner2: leave the policy text out")
        else:
            p.add_argument("--resamples", type=int, default=10_000)
            p.add_argument("--baseline", default="tier1", help="run that paired differences are taken against")
    args = parser.parse_args()
    if args.command == "run" and args.decider in ("hf", "gliner2") and not args.model:
        parser.error("--model is required for hf and gliner2")
    if args.command == "run" and args.decider == "systemone" and not args.endpoint:
        parser.error("--endpoint is required for systemone")
    run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    main()
