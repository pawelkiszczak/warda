+++
id = "P1-13"
title = "Brama v0.5: human-written pool, dev and official draw, first official run"
labels = ["phase:1", "team:benchmarks", "type:data", "gate:3"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-11", "P0-12", "P0-04", "P1-08"]
estimate_hours = 40
hardware = "strong"
github_issue = 0
+++

## Context

P0-12 ran the Brama v0 examples (108 agent-drafted items, unreviewed gold) and showed the runner, validator and
metrics work end to end. At that size nothing is distinguishable (±11 pt on catch, ±6 pt on UIR), and the gold has
no independent labels. P0-11's staged plan is a v0.5 with ~600 official items before the full v1. This task follows
P0-11's construction pipeline steps 2–9.

## Scope

- In: blueprints, human authoring (T5 as a grid), twins review, two blind labels per item, adjudication,
  privacy and validity checks V-01–V-05/V-07, the seeded stratified draw, a private official split, the first
  official run on local deciders.
- Out: v1 sizes (1,200 official), ood split, external submission path (D-B2), rewrite verifier unless P0-06 has one.

## Deliverables

- Blueprint table (one row per planned group) under `docs/bench/`.
- Public `data/brama/dev-v0.5.jsonl` (~300) with ids sidecar; private official v0.5 (~600) and reserve (~150), with
  hashes and per-track statistics published.
- `CARD.md` updated for v0.5 with a new canary GUID.
- A report under `docs/bench/reports/` with floors, tier-1, B2/B3 comparators and the pilot models from P0-12.

## Definition of done

- [ ] Every official item written by a person outside the training team (R-06); no LLM-drafted official items
- [ ] κ ≥ 0.7 per track (R-10); contested items listed
- [ ] V-01 policy-blind and V-02 destination-blind baselines within their limits on T5/T6
- [ ] V-04 floors: M-02 ≤ 0.05 for constant deciders; the tier-1 floor is reported per track (P0-12 found it
      0.17 over multi-row groups, driven by T1/T7/T9)
- [ ] V-07: 0 exact 13-gram overlaps against `pii_gen` raw cases and SFT splits
- [ ] Official run on local deciders only (R-16), with the R-19 report fields

## Automated tests

- `warda/bench/tests/`: the P0-12 validator and leakage tests run over the dev split; a test that the draw is
  reproducible from its seed and stratified per track × language × destination class.

## Documentation

- `docs/bench/BRAMA.md` (splits and sizes, power table for the realised n), `data/brama/CARD.md`, the report;
  `AGENTS.md` if file names or formats change.

## Manual test (human, before the PR)

1. Two people outside the team label 50 dev items from the decider view only (V-06); report their accuracy and M-02.
2. Classify 30 errors of the best local comparator as decider error, item error or contested (V-09); item errors
   < 10 %.
3. Confirm the official files are not in the public repository and their hashes match the report.
