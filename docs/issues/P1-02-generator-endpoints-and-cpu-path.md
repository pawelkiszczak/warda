+++
id = "P1-02"
title = "Generator: configurable endpoints, CPU small-model path, smoke profile"
labels = ["phase:1", "team:data-decision", "type:infra"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01"]
estimate_hours = 5
hardware = "laptop"
github_issue = 12
+++

## Context

Plan §6 "weaker hardware": data generation at small scale with quantised 3–8B models on CPU (llama.cpp / Ollama)
must be a first-class path, and every script needs a small-sample flag. `pii_gen.py` hardcodes two LM Studio /
omlx endpoints and model names (`endpoints()` at l.1128–1132) and the verifier model.

## Scope

- CLI/env configuration of generation and verification endpoints; a documented Ollama/llama.cpp profile; a
  `--limit 5` smoke that finishes on CPU.
- Out of scope: new case kinds (P1-03).

## Deliverables

- `pii_gen.py`: replace the hardcoded pool with `--endpoints FILE` (TOML, default
  `pretrain/harness/endpoints.toml`, committed, containing the current two generators + verifier) with schema
  `[[generator]] name, base_url, model, thinking_off (bool), concurrency, api_key_env (optional)` and
  `[verifier] …`; `--profile cpu` selects `pretrain/harness/endpoints.cpu.toml` (one Ollama entry
  `http://127.0.0.1:11434/v1`, model `qwen2.5:7b-instruct-q4_K_M`, concurrency 1; verifier = same endpoint).
- `--limit N` already exists; add `--dry-run` that renders prompts for N cases to stdout without calling any
  endpoint (for prompt review on any laptop).
- `build --limit N` to build items from the first N accepted cases (for CPU tests of downstream tools).
- Preserve/configure an Apple GPU model-server profile alongside the CPU profile: verify the server's actual
  backend/offload, model and quantisation rather than inferring GPU use from its HTTP API. Measure bounded
  concurrency/batching by accepted cases per second, verification throughput, retries and memory headroom;
  choose the fastest stable settings without changing blind verification or data-quality rules. Document
  unavailable/CPU-only endpoints honestly under `docs/performance/APPLE_SILICON.md`; no CUDA requirement.
- Endpoint errors: retry 3× with backoff, then mark the case `status: "endpoint_error"` and continue (resumable
  behaviour preserved).

## Definition of done

- [ ] `uv run python -m pretrain.harness.pii_gen generate --profile cpu --limit 5` completes on a laptop with
      Ollama running and appends 5 raw cases
- [ ] `generate --dry-run --limit 3` prints 3 prompts with no network
- [ ] A supported Apple GPU endpoint profile has backend/offload evidence and measured accepted-case throughput
      with bounded concurrency and memory; unavailable hardware is recorded, not silently claimed as GPU
- [ ] Default run is byte-for-byte the previous behaviour (same endpoints/models) — compare one `--dry-run` prompt
      before/after

## Automated tests

- `pretrain/harness/tests/test_endpoints.py`: TOML parsing and validation (missing `base_url` → `ValueError`);
  `--profile cpu` resolves the cpu file; `--dry-run` writes prompts to a buffer and never calls the HTTP client
  (monkeypatch `requests.post` to raise).

## Documentation

- `pretrain/README.md` "Harness decider": endpoints file, `--profile cpu`, `--dry-run`, Ollama setup lines
  (`ollama pull qwen2.5:7b-instruct-q4_K_M`). `AGENTS.md` "Hardware": "generator runs on CPU with `--profile cpu
  --limit`".

## Manual test (human, before the PR)

1. On an 8–16 GB laptop with Ollama: run the DoD command; measure wall time; record it in the PR (expected: minutes,
   not hours, for 5 cases).
2. Kill Ollama mid-run → log shows `endpoint_error` for the case and the process exits cleanly; rerun resumes
   without duplicating accepted cases (`wc -l raw_cases.jsonl` grows by the retried case only).
