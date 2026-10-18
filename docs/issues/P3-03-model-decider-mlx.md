+++
id = "P3-03"
title = "Model decider backend (MLX) in the service"
labels = ["phase:3", "team:tools", "type:feature", "gate:3"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P3-01", "P3-02", "P2-04"]
estimate_hours = 8
hardware = "laptop"
github_issue = 30
+++

## Context

The service runs the tier-1 decider only. `cand-v1` exists as `work/runs/<name>` loadable by `pretrain/sft.py`
(`predict`, `calibration.json`). ADR-0003: macOS/MLX first. The model answers the typed questions on the state
(action, category, flow); the service needs a `ModelDecider` with warm loading, the prompt rendering from
`prompt.py`, and both-order averaging as in `sft.py`.

## Scope

- `warda/service/model_mlx.py`; model packaging; `serve --decider mlx:<path>`; latency measurement.
- Out of scope: portable backend (P4-06).

## Deliverables

- `warda/service/model_mlx.py`: `class MlxDecider(Decider)` loading `model.safetensors`, `config.json`,
  `calibration.json`, `pointer.safetensors`, tokenizer (paths from a `model_dir`); `decide(request: DecisionInput)`
  renders the state
  (policy text, channel, destination, payload, task) with `pretrain/prompt.py` templates by language, asks
  `category` (7 options) and `action` (4 options), averages original/reversed orders, applies temperature by
  (type, language group), returns `Decision` with `confidence = max prob of action`; category also returned.
  Loads once in a background thread at startup; `/healthz` reports `decider.ready`; requests before ready → 503.
- Packaging: `scripts/export_model.py --run <name> --out models/cand-v1/` copying the files above plus
  `MODEL_CARD.md` (size, training data version, eval numbers, SHA-256s); `models/` is gitignored; the card is
  copied to `docs/model/CARD-cand-v1.md`.
- Config: `[decider] kind = "mlx"; model_dir = "~/.warda/models/cand-v1"`; `kind = "tier1"` keeps phase-2
  behaviour.
- Pipeline order in `Service.decide`: tier-1 credential → block; else deterministic PII policy requirement + model
  category/action →
  combine under P2-04 precedence → bands → response;
  `tier1` hits still populate `tier1[]` and drive `redacted_payload`; when the model says `redact` but tier-1 found
  nothing, `redacted_payload` is `None` and the reason says "model: redact, no deterministic spans — ask the
  agent to rewrite" (deny-and-continue semantics: hooks treat it as deny with that reason).

## Definition of done

- [ ] `serve` with `kind = "mlx"` answers the P2-04 DoD payloads plus a tier-2 mosaic payload ("jedyna księgowa w
      biurze w Opolu, wczoraj złożyła wypowiedzenie") to `public_repo` with `block` or `ask_user`
- [ ] Raw model outputs equal `warda.bench.run --decider sft:cand-v1` for 100 frozen test items
      (same action and |Δconfidence| < 1e-3); full service outputs are compared against the full pipeline,
      including deterministic precedence, bands and session state
- [ ] p95 end-to-end latency for ≤ 1k-token states ≤ the ADR-0005 budget on the dev Mac (report p50/p95 and RAM)

## Automated tests

- Valid PESEL under a redact policy + fake model allow cannot allow; policy-permitted internal PII remains
  permitted. Model block plus deterministic redact stays block. Credential block cannot escalate to ask.
  Unsafe/missing redaction spans cannot result in an executable rewrite.

- `warda/service/tests/test_model_mlx.py` (`WARDA_SLOW`): load `tiny`-based export fixture (built in-test from
  the `tiny` config, random weights) → `decide` returns valid actions, both orders averaged (monkeypatch
  `predict` to record calls = 2 per question); 503 before ready.
- `warda/service/tests/test_pipeline_order.py` (no MLX, fake decider): credential bypass; model redact without
  spans → reason text and `redacted_payload is None`.

## Documentation

- `docs/service/MODEL.md`: export, install under `~/.warda/models`, config, memory/latency table;
  `docs/model/CARD-cand-v1.md`.

## Manual test (human, before the PR)

1. Export `cand-v1`, start `serve`, wait for `healthz.ready`; run the four DoD payloads via `python -m warda
   decide`; paste actions/confidences.
2. `python -m warda log --stats` after 50 decisions → p95 within budget; Activity Monitor RAM for the process
   noted.
