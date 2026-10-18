+++
id = "P2-02"
title = "Decision data round 2 build, verification sample and dataset card"
labels = ["phase:2", "team:data-decision", "type:data", "gate:1"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P1-03", "P0-05"]
estimate_hours = 5
hardware = "laptop"
github_issue = 23
+++

## Context

After P1-03 the raw cases include new kinds; gate 1's bar (≥ 95 % confirmed) must hold on the new material too,
and the dataset needs a card so the team and later the public know what is in it.

## Scope

- Final `build` of round 2; a 100-item verification sample on the *new* kinds only; dataset card.
- Out of scope: training.

## Deliverables

- `pretrain/work/harness_pii/items/` rebuilt; `manifest.json` with per-kind/per-policy/per-split counts, a
  `version: "v2"` field and the git commit of `pii_gen.py`.
- `data/verification/round2/` (sample, two label files, adjudicated) produced exactly as in P0-05 but with
  `--by kind,language --only-new-kinds` (sampler flag added: restrict to kinds/channels listed in
  `docs/data/GAPS-round2.md`).
- `docs/data/DATASET-CARD.md`: purpose, generation pipeline (models, verifiers, acceptance rules), schema (link
  `AGENTS.md`), counts table (v1 and v2), splits and OOD policy, known noise (from `pretrain/README.md` "Checks
  after the build"), verification rounds with confirm rates, licence (ADR-0002), "fictional only" statement,
  intended/unintended use.
- `docs/gates/GATE1.md` appended with "Round 2" results.

## Definition of done

- [ ] Confirm rate on the round-2 sample ≥ 95 % (else a P1-03 follow-up issue and the build is not promoted —
      `manifest.json` keeps `version: "v1"`)
- [ ] Dataset card complete; counts match `manifest.json`
- [ ] `data/harness_pii/sample-v2.jsonl` refreshed from the promoted build

## Automated tests

- `warda/label/tests/test_sample.py`: `--only-new-kinds` filter.
- `pretrain/harness/tests/test_manifest.py`: manifest counts equal recounts over the committed sample (sample
  carries a `manifest_slice` note) — pins that the card's numbers come from the manifest, not by hand.

## Documentation

- `docs/data/DATASET-CARD.md`; `pretrain/README.md` run table v2; `docs/gates/GATE1.md`.

## Manual test (human, before the PR)

1. Pick 10 items from `sample-v2.jsonl`; verify by eye that category/action match the guidelines.
2. Read the dataset card as an outsider: you can say what the data is for, how big, and what it must not be used
   for, without opening code.
