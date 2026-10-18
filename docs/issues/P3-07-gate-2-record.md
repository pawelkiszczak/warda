+++
id = "P3-07"
title = "Gate 2 record: the model learns"
labels = ["phase:3", "team:coordination", "type:decision", "gate:2"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P3-01", "P1-11"]
estimate_hours = 2
hardware = "laptop"
github_issue = 34
+++

## Context

Plan §3 gate 2: the model beats simple solutions ("always allow", pattern matching) and copes with an unseen
policy. The evidence is `docs/model/SFT-candidate.md` and `docs/bench/BASELINES.md`; the gate needs a dated
decision with named approvers and a stop/continue outcome.

## Scope

- `docs/gates/GATE2.md` only.

## Deliverables

- `docs/gates/GATE2.md`: criteria quoted from `PROTOCOL.md`; the numbers with links to the exact report files and
  run names; PASS/FAIL per criterion; overall decision; if FAIL, the chosen remedy (more data: P1-03 follow-up /
  larger size: ADR-0001 / stop) and the re-check date; approvers (coordinator + model owner + benchmarks owner).

## Definition of done

- [ ] File merged with three approvers' handles and a date
- [ ] Every number in the file is reproducible from a linked `report.json` / `eval.json`

## Automated tests

- None (docs).

## Documentation

- `FINDINGS.md` top table gains a "Gates" row linking `docs/gates/`.

## Manual test (human, before the PR)

1. A second person recomputes one criterion from the linked `report.json` with `jq` → same number.
