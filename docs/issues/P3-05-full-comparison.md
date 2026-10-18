+++
id = "P3-05"
title = "Full comparison with existing tools on the gate-3 set"
labels = ["phase:3", "team:benchmarks", "type:experiment", "gate:3"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P1-11", "P3-03", "P3-04", "P1-07"]
estimate_hours = 8
hardware = "laptop"
github_issue = 32
+++

## Context

Plan phase 3: "full comparison with existing solutions". P1-11 covered Presidio/ggshield; P1-07 marked
Bielik-Guard, Llama Prompt Guard 2 and a Jev-style decision model as "in benchmark". Gate 3 reads
`leak_recall_public ≥ 0.80` at `false_block_rate ≤ 0.05` on handwritten v1.

## Scope

- Adapters for the remaining tools; the comparison report; the gate-3 numbers for `cand-v1` with bands.
- Out of scope: tuning the model.

## Deliverables

- `warda/bench/deciders/hf_classifier.py`: generic adapter for Hugging Face sequence classifiers run with
  `transformers` on CPU (already a dependency): `hf:<model-id>:<label-map.json>` mapping labels to categories;
  used for Bielik-Guard and Prompt Guard 2 with the maps committed under `warda/bench/maps/`; `--limit` and a
  cache dir under `pretrain/work/hf/`; marked `WARDA_SLOW`.
- `warda/bench/deciders/service.py`: `service:<url>` decider calling a running Warda service (so the *deployed*
  pipeline — tier-1 + model + bands — is what gets scored, not just the model).
- `docs/bench/COMPARISON.md`: one table per set (`test`, `test_ood`, `handwritten v1`) with all deciders ×
  (accuracy, macro-F1, leak_recall_public, false_block_rate, ECE, coverage@1%, ms/item), slices by tier and
  language for the handwritten set, 3 qualitative examples per tool of a miss, and the gate-3 line in bold.

## Definition of done

- [ ] Every tool marked "in benchmark" in `LANDSCAPE.md` has a row or an explicit "could not run: reason"
- [ ] `service:` decider numbers equal `sft:cand-v1`+bands numbers (same items) — proves the deployment path
- [ ] `COMPARISON.md` states gate-3 PASS/FAIL for `cand-v1` with bands

## Automated tests

- `warda/bench/tests/test_hf_classifier.py` (`WARDA_SLOW`, small public model): label map applied; unknown label
  → `None` category.
- `warda/bench/tests/test_service_decider.py`: against a `TestClient`-backed service with a fake decider, the
  adapter forwards channel/destination/policy and maps the response.

## Documentation

- `docs/bench/COMPARISON.md`; `docs/bench/PROTOCOL.md` lists the new deciders.

## Manual test (human, before the PR)

1. Run the handwritten v1 comparison end-to-end on a laptop (`--limit 0`); total wall time recorded.
2. Open the 5 worst `cand-v1` false blocks: are they arguably correct under the policy? Record the judgement;
   if ≥ 3 are labelling errors, reopen those items in P3-04 before computing the gate.
