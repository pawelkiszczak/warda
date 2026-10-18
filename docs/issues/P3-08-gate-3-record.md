+++
id = "P3-08"
title = "Gate 3 record: works on real-looking text"
labels = ["phase:3", "team:coordination", "type:decision", "gate:3"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P3-05", "P3-04"]
estimate_hours = 2
hardware = "laptop"
github_issue = 35
+++

## Context

Plan §3 gate 3: on the manual set, ≥ 80 % of leaks to public destinations caught at ≤ 5 % unnecessary blocks.
Evidence: `docs/bench/COMPARISON.md`.

## Scope

- `docs/gates/GATE3.md` only.

## Deliverables

- `docs/gates/GATE3.md`: same structure as GATE2; the `service:isolated` decider row is the one judged (deployed path);
  slices by tier and language reported even though the gate is global; if FAIL, remedy chosen among: refit
  bands (P3-02), more handwritten data in the failing slice (P3-04 follow-up), model change (P3-01 follow-up),
  stop.

## Definition of done

- [ ] Merged with approvers (coordinator, benchmarks owner, GDPR person) and date
- [ ] Numbers reproducible from the linked `report.json`

## Automated tests

- None (docs).

## Documentation

- Linked from `FINDINGS.md` "Gates" row.

## Manual test (human, before the PR)

1. Second person recomputes `leak_recall_public` and `unnecessary_intervention_rate` from the linked report with `jq`.
