"""Serve a decision model that ships only a Python API as `POST /v1/systemone`, so `run_brama --decider systemone`
reads every System-1 model the same way. Run it in the model's own environment (each card pins its own torch and
transformers); it needs only the standard library besides the model's code.

    python -m warda.bench.systemone_shim --backend automodel --model vllm-sr/d3-flash --revision <sha> --port 8001

Backends, as each model card documents its API:

- `automodel`: `AutoModel.from_pretrained(..., trust_remote_code=True).system_one(state=..., questions=...)`
  (vLLM Semantic Router Decision 3.0: d3-flash, d3-mini, d3-nano, d3-lite).
- `pplx`: `pplx_decider.Decider.from_pretrained(checkpoint).decide(request)` (perplexity-ai/pplx-decider-*).
- `clef`: `joint_schema_model.systemone(model, processor, request)` (Cloudflare/clef-*).
- `jev`: `jev_omni.JevOmni(...).predict(state=..., question=..., options=[...])` (akhilaaa3/Jev-Omni), assembled as its
  `load_jev_omni` does but with the backbone in 8 bits (bitsandbytes LLM.int8), since its bf16 weights need 24 GB.
  `choice` questions only; the options are the criteria texts in the order given.
- `decider`: `decider.infer.Decider(path, gguf_file=...).system_one(state, questions)` (Mapika/decider-*, decider-ai);
  `--gguf` names a local Q8_0 file converted with llama.cpp, its folder holding the tokenizer and `decider_config.json`.
- `nimble`: `NimbleEngine(adapter=...)(state, questions)` from the code in the
  bespokelabs/bespoke-nimble-9b-v3-decision-index dataset (Bespoke-Nimble-9B-v3, a LoRA on Qwen3.5-9B). The engine's
  two `decision_index.engines` names are stubbed, since only its call is used. The code is pinned to
  `NIMBLE_CODE_REVISION`.
- `spx`: `decision.decide(case, backend, labels)` from the SurdAI/SPX-CD-Omni repo (a LoRA on Gemma 4 12B), with its
  `TransformersBackend` built on an 8-bit base (`--base`), since the bf16 base needs 24 GB. `choice` questions only.

The model code is downloaded from the pinned revision and runs in this process: pin `--revision` to the commit that
was reviewed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

Handler = Callable[[dict[str, Any]], dict[str, Any]]


def load(
    backend: str, model_id: str, revision: str | None, device: str, gguf: str | None = None, base: str | None = None
) -> Handler:
    import torch
    from huggingface_hub import snapshot_download

    if backend == "automodel":
        from transformers import AutoModel

        model: Any = AutoModel.from_pretrained(
            model_id, revision=revision, trust_remote_code=True, dtype=torch.bfloat16
        )
        model = model.to(device).eval()
        return lambda req: model.system_one(state=req["state"], questions=req["questions"])
    if backend == "decider":
        from decider.infer import Decider

        decider_model = Decider(gguf) if gguf else Decider(model_id, device=device)
        return lambda req: decider_model.system_one(req["state"], req["questions"])
    path = snapshot_download(model_id, revision=revision)
    if backend == "pplx":
        sys.path.insert(0, f"{path}/source/src")
        from pplx_decider import Decider

        decider = Decider.from_pretrained(path, device=device)
        return lambda req: decider.decide({"state": req["state"], "questions": req["questions"]})
    if backend == "clef":
        sys.path.insert(0, path)
        from joint_schema_model import load_release_model, systemone

        model, processor = load_release_model(path, device=device)
        return lambda req: systemone(model, processor, req)
    if backend == "jev":
        return _jev(path, device)
    if backend == "nimble":
        return _nimble(path)
    if backend == "spx":
        return _spx(path, base or "google/gemma-4-12B-it", device)
    raise SystemExit(f"unknown backend {backend!r}")


def _jev(path: str, device: str) -> Handler:
    from pathlib import Path

    import torch
    import transformers
    from transformers import AutoConfig, AutoProcessor, BitsAndBytesConfig

    sys.path.insert(0, path)
    import jev_omni

    arch = AutoConfig.from_pretrained(path).architectures[0]
    quant = BitsAndBytesConfig(load_in_8bit=True)
    model = getattr(transformers, arch).from_pretrained(
        path, dtype=torch.bfloat16, device_map=device, quantization_config=quant
    )
    decision = json.loads((Path(path) / "decision_config.json").read_text())
    head = jev_omni._Head256(decision["hidden_size"]).to(device).eval()
    head.load_state_dict(torch.load(Path(path) / "head.pt", map_location=device, weights_only=True))
    _, decoder = jev_omni._find_backbone(model.eval())
    clf = jev_omni.JevOmni(model, head, AutoProcessor.from_pretrained(path), decoder, device)

    def handle(req: dict[str, Any]) -> dict[str, Any]:
        answers = {}
        for key, q in req["questions"].items():
            if q.get("type") != "choice":
                raise ValueError("the jev backend serves choice questions only")
            keys, texts = list(q["criteria"]), list(q["criteria"].values())
            out = clf.predict(state=req["state"], question=q.get("instructions", ""), options=texts)
            probs = dict(zip(keys, (out["probabilities"][t] for t in texts), strict=True))
            answers[key] = {"type": "choice", "choice": max(probs, key=probs.__getitem__), "probabilities": probs}
        return {"answers": answers}

    return handle


NIMBLE_CODE = "bespokelabs/bespoke-nimble-9b-v3-decision-index"
NIMBLE_CODE_REVISION = "654b124d3508a7da0d849405744bde80c4bb1a1b"


def _nimble(adapter: str) -> Handler:
    import tempfile
    import types

    from huggingface_hub import snapshot_download

    engines = types.ModuleType("decision_index.engines")

    class Engine:
        def __init__(self, **options: Any) -> None:
            self.options = options

    class Unsupported(Exception):  # noqa: N818 -- the name the engine imports.
        pass

    engines.Engine, engines.Unsupported = Engine, Unsupported  # type: ignore[attr-defined]
    sys.modules["decision_index"] = types.ModuleType("decision_index")
    sys.modules["decision_index.engines"] = engines
    # Real files, not cache symlinks: the engine hashes its prompt sources next to `__file__.resolve()`.
    code = snapshot_download(
        NIMBLE_CODE,
        repo_type="dataset",
        revision=NIMBLE_CODE_REVISION,
        allow_patterns=["code/**"],
        local_dir=tempfile.mkdtemp(prefix="nimble-code-"),
    )
    sys.path.insert(0, f"{code}/code")
    from nimble.evaluation.decision_index_engine import NimbleEngine

    engine = NimbleEngine(adapter=adapter)
    return lambda req: engine(req["state"], req["questions"])[0]


def _spx(path: str, base: str, device: str) -> Handler:
    from pathlib import Path

    import torch
    from peft import PeftModel
    from transformers import AutoModelForMultimodalLM, AutoProcessor, BitsAndBytesConfig

    sys.path.insert(0, path)
    import decision
    import infer

    backend = infer.TransformersBackend.__new__(infer.TransformersBackend)
    backend.torch, backend.max_context = torch, 16384
    backend.processor = AutoProcessor.from_pretrained(base)
    quant = BitsAndBytesConfig(load_in_8bit=True)
    model = AutoModelForMultimodalLM.from_pretrained(
        base, dtype=torch.bfloat16, device_map=device, quantization_config=quant
    )
    backend.model = PeftModel.from_pretrained(model, path).eval()
    labels = json.loads((Path(path) / "label_tokens.json").read_text())
    decision.validate_labels(backend.processor, labels)

    def handle(req: dict[str, Any]) -> dict[str, Any]:
        answers = {}
        for key, q in req["questions"].items():
            if q.get("type") != "choice":
                raise ValueError("the spx backend serves choice questions only")
            case = {"id": key, "state": req["state"], "question": q["instructions"], "options": q["criteria"]}
            out = decision.decide(case, backend, labels)
            answers[key] = {"type": "choice", "choice": out["choice"], "probabilities": out["probabilities"]}
        return {"answers": answers}

    return handle


def serve(handle: Handler, model_id: str, port: int) -> None:
    import torch

    class Server(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._send(200, {"data": [{"id": model_id}]} if self.path == "/v1/models" else {"status": "ok"})

        def do_POST(self) -> None:
            if self.path != "/v1/systemone":
                return self._send(404, {"error": "not found"})
            req = json.loads(self.rfile.read(int(self.headers["content-length"])))
            with torch.inference_mode():
                self._send(200, handle(req))

        def log_message(self, *args: Any) -> None:
            pass

    print(f"systemone_shim: {model_id} ready on port {port}", flush=True)  # noqa: T201 -- the ready line the caller waits for.
    HTTPServer(("127.0.0.1", port), Server).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--backend", required=True, choices=["automodel", "pplx", "clef", "jev", "decider", "nimble", "spx"]
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--gguf", help="local GGUF file (decider backend)")
    parser.add_argument("--base", help="base model for an adapter (spx backend; default google/gemma-4-12B-it)")
    args = parser.parse_args()
    handle = load(args.backend, args.model, args.revision, args.device, args.gguf, args.base)
    serve(handle, args.model, args.port)


if __name__ == "__main__":
    main()
