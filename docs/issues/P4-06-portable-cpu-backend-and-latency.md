+++
id = "P4-06"
title = "Portable CPU backend and latency benchmark on ordinary laptops"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P3-03", "P0-07", "P3-07", "P3-08"]
estimate_hours = 8
hardware = "laptop"
github_issue = 41
+++

## Context

Plan §5 phase 4 "speed on ordinary laptops", §6 "speed tests on weak laptops are needed", ADR-0003 Linux/Windows
via a portable backend. `model.py` is a custom MoE (sigmoid fp32 router, shared expert, pointer head) — llama.cpp
has no converter for it, so GGUF is not a drop-in. The model is small (≤ 250M params); a NumPy/PyTorch forward
pass of `model.py` is the boring, reliable path.

## Scope

- `warda/service/model_torch.py` (PyTorch CPU, fp32/bf16) implementing the same forward as `model.py` and the
  pointer readout, loading the same safetensors; parity test against MLX; `warda bench-latency`; a latency table
  across machines.
- Out of scope: Core ML, ONNX (revisit if torch CPU misses the budget).

## Deliverables

- `pyproject.toml`: optional group `cpu = ["torch>=2.x"]` (CPU wheels; documented `uv sync --group cpu`); Reuse P0-01
  platform markers/lazy imports; verify Linux/Windows installs without MLX.
  This backend provides inference only, not a portable training implementation.
- `warda/service/model_torch.py`: `TorchDecider(Decider)` with identical outputs to `MlxDecider` (|Δp| < 1e-4
  on 100 items); config `kind = "torch"`.
- `python -m warda bench-latency [--n 50] [--decider mlx|torch|tier1] [--state-tokens 1000]`: p50/p95 ms,
  RSS MB, machine description (CPU, RAM, OS) → appends a row to `docs/service/LATENCY.md` when `--record`.
- On Apple Silicon compare explicit MLX CPU and GPU paths on the same checkpoint/state sample, including
  cold load and warm p50/p95; record actual device, fallbacks, dtype, versions, concurrency, tokenisation time
  and memory/swap. Use the faster correct path within the interactive latency/memory budget; do not claim
  whole-request speedups from a resident kernel. PyTorch CPU remains the portable baseline, not a CUDA port.
  Follow `docs/performance/APPLE_SILICON.md` and carry results back into P3-03 serving defaults.
- `docs/service/LATENCY.md`: table from ≥ 4 machines including one 8 GB Apple silicon, one 16 GB x86 laptop
  (Linux or Windows WSL), one Windows native; budget from ADR-0005; recommendation per platform.

## Definition of done

- [ ] Before this phase-4 work starts, Gate 2 and Gate 3 records state PASS for the candidate version;
      closing a gate issue with FAIL does not authorise progression. A failed gate requires a new approved PASS.

- [ ] Parity test passes; `torch` backend serves the P3-03 DoD payloads on a Linux machine
- [ ] `LATENCY.md` compares actual MLX CPU/GPU placement on the same Apple Silicon sample and reports
      full-request p50/p95, cold load, memory and fallback reasons rather than only GPU kernel time
- [ ] `LATENCY.md` has ≥ 4 rows; at least one 8 GB machine meets the ADR-0005 budget, or ADR-0005 is amended
      with the measured numbers and the reason
- [ ] `uv sync --locked` succeeds on Linux (no MLX) and `pytest -q` passes there (MLX tests skipped by platform)

## Automated tests

- `warda/service/tests/test_model_torch.py` (`pytest.importorskip("torch")`): `tiny` random weights saved from
  MLX (fixture generated on macOS and committed as a tiny safetensors < 16 MB (the 32k × 64 embedding alone is about 4
  MB in fp16) under `warda/service/tests/fixtures/`)
  → torch forward matches the stored MLX reference logits within 1e-4; decide path.
- `warda/tests/test_platform_deps.py`: on Linux, `import warda.service.app` does not import `mlx`.

## Documentation

- `docs/service/LATENCY.md`, `docs/service/MODEL.md` (torch backend, install per platform), `README.md`
  platform note.

## Manual test (human, before the PR)

1. On a non-Mac laptop: `uv sync --group cpu`, `python -m warda serve` with `kind = "torch"`, run the four DoD
   payloads → same actions as on the Mac.
2. `python -m warda bench-latency --record` on your machine; the new row appears in `LATENCY.md`.
