+++
id = "P4-08"
title = "Dogfooding: shadow mode in our own agents and the shadow report"
labels = ["phase:4", "team:coordination", "type:infra", "gate:4"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P2-06", "P3-03"]
estimate_hours = 5
hardware = "laptop"
github_issue = 0
+++

## Context

Plan §7 "Dogfooding: from phase 4 the guard runs in shadow mode in our own agents. We are the first testers."
Phase 5 needs the review tooling already proven on ourselves.

## Scope

- Every core member installs the service + their agent's hook in shadow mode; `python -m warda report` aggregates
  logs; a weekly dogfood review section in `docs/team/MEETINGS.md`.
- Out of scope: external testers (phase 5).

## Deliverables

- `python -m warda report [--log PATH…] [--since ISO] --out DIR`: `report.md` with counts per action /
  destination class / channel / agent, p50/p95 latency, decisions per day, the 20 lowest-confidence non-allow
  decisions (ids + hashes only), and a "false alarm" section populated from `python -m warda mark <decision_id>
  --verdict correct|false_alarm|missed --note "…"` (appends to `~/.warda/feedback.jsonl`); `report.json` with the
  same numbers.
- `docs/testing/DOGFOOD.md`: install steps per agent (links), the weekly ritual (run `report`, mark ≥ 10
  decisions, paste summary into the meeting notes), the privacy rule (reports contain no payloads; sharing the
  raw log is opt-in and only with `store_payload = false`).
- Two weeks of dogfood summaries from ≥ 4 people pasted into `docs/gates/DOGFOOD-log.md` (numbers only).

## Definition of done

- [ ] ≥ 4 members ran shadow mode for ≥ 2 weeks; `DOGFOOD-log.md` has their weekly summaries
- [ ] `report` and `mark` work on merged logs from several machines (distinct `agent.session` ids)
- [ ] At least 10 marked decisions per person; the false-alarm rate and missed count are in the log

## Automated tests

- `warda/tests/test_report.py`: aggregation on a 30-line fixture (known counts/percentiles); merge of two logs;
  `mark` appends and `report` joins it; no `payload` field ever appears in `report.md` even when the log has one.

## Documentation

- `docs/testing/DOGFOOD.md`, `docs/service/CLI.md` (`report`, `mark`), `docs/team/MEETINGS.md` agenda item.

## Manual test (human, before the PR)

1. After a day of normal work with the hook in shadow mode, `python -m warda report --out /tmp/r`; open
   `report.md`: counts look plausible for your day; no payload text anywhere (`grep -c` for a word you committed →
   0).
2. `mark` one decision as `false_alarm`; rerun `report` → it appears in the false-alarm section.
