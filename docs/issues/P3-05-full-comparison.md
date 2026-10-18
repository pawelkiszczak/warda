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
`leak_recall_public ≥ 0.80` at `unnecessary_intervention_rate ≤ 0.05` on handwritten v1.

## Scope

- Adapters for the remaining tools; the comparison report; the gate-3 numbers for `cand-v1` with bands.
- Out of scope: tuning the model.

## Deliverables

- `warda/bench/deciders/hf_classifier.py`: generic adapter for Hugging Face sequence classifiers run with
  `transformers` on CPU (already a dependency): `hf:<model-id>:<label-map.json>` mapping labels to categories;
  used for Bielik-Guard and Prompt Guard 2 with the maps committed under `warda/bench/maps/`; `--limit` and a
  cache dir under `pretrain/work/hf/`; marked `WARDA_SLOW`.
- `warda/bench/deciders/service.py`: `service:isolated` decider starting an isolated local service for each set policy
  using the
  shared Policy loader. Requests use the existing API; no request-controlled policy override is added to the
  production service. Disposable logs and reset session state make the *deployed* tier-1 + model + bands
  pipeline reproducible. Group by policy and restore item order in reports.
- `docs/bench/COMPARISON.md`: one table per set (`test`, `test_ood`, `handwritten v1`) with all deciders ×
  (accuracy, macro-F1, leak_recall_public, false_block_rate, unnecessary_intervention_rate, ECE, coverage@1%,
  ms/item), slices by tier and
  language for the handwritten set, 3 qualitative examples per tool of a miss, and the gate-3 line in bold.

## Definition of done

- [ ] Every tool marked "in benchmark" in `LANDSCAPE.md` has a row or an explicit "could not run: reason"
- [ ] `service:isolated` decider numbers equal the in-process full pipeline (tier-1 + model + bands) numbers (same
  items) — proves the deployment path
- [ ] `COMPARISON.md` states gate-3 PASS/FAIL for `cand-v1` with bands

## Automated tests

- `warda/bench/tests/test_hf_classifier.py` (`WARDA_SLOW`, small public model): label map applied; unknown label
  → `None` category.
- `warda/bench/tests/test_service_decider.py`: against a `TestClient`-backed service with a fake decider, the
  adapter forwards channel/destination/task/provenance, selects an isolated service configured with the
  item policy, and maps the response. Two policies giving opposite actions on one payload are evaluated correctly.
  Session counters reset between independent items; explicit multi-call fixtures preserve their session.

## Documentation

- `docs/bench/COMPARISON.md`; `docs/bench/PROTOCOL.md` lists the new deciders.

## Manual test (human, before the PR)

1. Run the handwritten v1 comparison end-to-end on a laptop (`--limit 0`); total wall time recorded.
2. Open the 5 worst `cand-v1` false blocks: are they arguably correct under the policy? Record the judgement;
   suspected label errors are adjudicated blind to candidate identity. Preserve the frozen original result,
   version any corrections and rerun every comparator. Do not tune the candidate against corrected gate items;
   after tuning, use a fresh held-out gate set.
