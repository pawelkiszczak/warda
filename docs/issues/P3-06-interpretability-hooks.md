+++
id = "P3-06"
title = "Interpretability hooks for the MLX model: logit lens and token attribution"
labels = ["phase:3", "team:model", "type:feature"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P3-01"]
estimate_hours = 5
hardware = "laptop"
github_issue = 33
+++

## Context

Plan §6 "model internals (for future pruning)": live view of which layers/heads/experts drive a decision; MLX has
no nnsight/TransformerLens, so "own hooks on layers (a dozen lines)". `model.py` exposes hidden states and the
router; `sft.py` has the pointer readout.

## Scope

- `pretrain/interp/` with per-layer readout, expert-usage stats and input attribution; a CLI that prints a report
  for one item; no UI.
- Out of scope: pruning itself.

## Deliverables

- `pretrain/interp/lens.py`: `layer_readouts(model, item) -> list[dict]` applying the pointer head to every
  layer's residual (logit-lens analogue) → per-layer action probabilities; `expert_usage(model, item) ->
  dict[layer, Counter[expert]]`; `attribution(model, item, method="erasure") -> list[(token, Δp)]` by masking
  each payload token (or span of 4) and measuring the change in the chosen action's probability.
- CLI `python pretrain/interp/lens.py --run <name> --item-id ID --items PATH` printing the three tables; `--out
  JSON`.
- `docs/model/INTERP.md`: what each view means, 3 worked examples from `cand-v1` (one per tier), observed
  expert concentration, and the layers where the decision "appears" (first layer whose readout matches the
  final action for ≥ 80 % of 200 dev items).

## Definition of done

- [ ] CLI runs on `tiny` on CPU and on `cand-v1` on the dev Mac
- [ ] `INTERP.md` has the three examples and the layer statistic
- [ ] For the mosaic example, the attribution top-3 spans are the identifying details (sanity check of the method)

## Automated tests

- `pretrain/interp/tests/test_lens.py` (`WARDA_SLOW`, `tiny` random model): readouts length = layers; probabilities
  sum to 1; erasure attribution of a token outside the payload is 0 (only payload tokens are masked).

## Documentation

- `docs/model/INTERP.md`; `pretrain/README.md` gains an "Interpretability" paragraph.

## Manual test (human, before the PR)

1. Run the CLI on one `direct_pii` item: the PESEL tokens have the largest Δp.
2. Run on the OOD policy item: readout flips to the final action at the layer the doc claims (±1).
