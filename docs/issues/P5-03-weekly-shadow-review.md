+++
id = "P5-03"
title = "Weekly shadow review: aggregation across testers and triage workflow"
labels = ["phase:5", "team:benchmarks", "type:feature", "gate:4"]
milestone = "Phase 5 — Shadow mode and gate 4 (weeks 16–20)"
depends_on = ["P4-08", "P5-02"]
estimate_hours = 5
hardware = "laptop"
github_issue = 47
+++

## Context

Plan phase 5: weekly review for 2–4 weeks. Testers send `report.md`/`report.json` per week; the team needs one
aggregate view, a triage of false alarms and misses into issues, and the numbers gate 4 will cite (rare false
alarms, fast, real catches).

## Scope

- `python -m warda review` aggregating many `report.json` files; triage doc; four weekly records.
- Out of scope: changing model/bands during the test window (freeze; record only).

## Deliverables

- Reject duplicate/overlapping tester reporting periods and incompatible schema versions; separate model
  versions and policy/config changes rather than silently pooling them. Carry reviewed/unreviewed counts and
  confirmed catches into week-4. Zero reviewed non-allow decisions means undefined rate, not zero errors.

- `python -m warda review --reports DIR --week N --out docs/gates/shadow/week-N.md`: per tester (by `[tester]
  id`) and overall: decisions, non-allow rate, false-alarm rate (false_alarm / reviewed non-allow), review coverage,
  misses
  reported, p95 latency bin interval from merged histograms, agents used; trend vs previous weeks; the 10 most common
  `reason` codes.
- `docs/testing/TRIAGE.md`: how a false alarm or miss becomes an issue (label `type:data` for data gaps,
  `type:feature` for pipeline bugs), with the template; the freeze rule for the window.
- `docs/gates/shadow/week-{1..4}.md` filled from real tester reports.

## Definition of done

- [ ] Four weekly files produced by the command from tester reports (no hand edits except the "Notes" section)
- [ ] Every false alarm/miss reported in the window has an issue or a "won't fix" note in the week file
- [ ] The numbers gate 4 needs (false-alarm rate, p95, real catches count) are in `week-4.md`

## Automated tests

- `warda/tests/test_review.py`: aggregation over three fixture reports; trend computation; missing week handled;
  no payload-like field leaks into the output.

## Documentation

- `docs/testing/TRIAGE.md`; `docs/service/CLI.md` (`review`).

## Manual test (human, before the PR)

1. Run `review` on the week-1 reports; cross-check one tester's non-allow count against their `report.md`.
2. File one triage issue from a real false alarm using the template; link it from the week file.
