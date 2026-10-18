+++
id = "P5-02"
title = "Tester onboarding, consent and privacy notice, feedback channel"
labels = ["phase:5", "team:gdpr", "type:docs", "gate:4"]
milestone = "Phase 5 — Shadow mode and gate 4 (weeks 16–20)"
depends_on = ["P5-01"]
estimate_hours = 4
hardware = "laptop"
github_issue = 46
+++

## Context

Testers run the guard on real work. The log holds decision metadata and payload hashes, not payloads, but it still
records what channels and destinations they use and when. The GDPR person must sign off on what we collect, what
testers share back, and how it is deleted.

## Scope

- Onboarding doc, consent text, data inventory, feedback form, deletion procedure.
- Out of scope: tooling (P5-01, P5-03).

## Deliverables

- Before onboarding begins, commit `docs/gates/GATE4-PROTOCOL.md` with the P5-04 numeric thresholds, sample
  selection seed/procedure, review coverage requirements, reporting schema and freeze date. Randomly select
  non-allow decisions for review; report separately any extra user-selected complaints. Specify an allow-decision
  review sample for missed leaks without claiming recall from unsolicited reports. No post-hoc threshold changes.
- Privacy inventory matches the P4-08 allowlisted aggregate schema; no payload hashes or free-text notes in
  shared reports. Document local vs shared retention, and delete both copies after the agreed retention period.

- `docs/testing/ONBOARDING.md`: who testers are (3–5, named by handle in `docs/team/OWNERS.md`), what they
  install, what shadow mode means (nothing is blocked), what they send weekly (the `report.md` from `python -m
  warda report`, never the raw log), how to mark false alarms/misses, how to stop and uninstall.
- `docs/testing/PRIVACY.md`: data inventory table `Field | Example | Why | Retention`, statement that payloads
  are not stored (`store_payload = false` enforced by the shadow lock), that reports contain allowlisted aggregates and
  pseudonymous tester IDs, retention (deleted 30 days after gate 4), the deletion command, and the contact for the
  GDPR person;
  consent paragraph testers acknowledge by replying in the tester channel (recorded in `OWNERS.md`).
- `docs/testing/FEEDBACK.md`: the weekly form (5 questions: false alarms seen, misses noticed, latency felt,
  anything confusing, one example you'd want handled better — described without real data) and where to post it.

## Definition of done

- [ ] GDPR person approved `PRIVACY.md` (PR review)
- [ ] All testers acknowledged consent before installing (recorded)
- [ ] `python -m warda report` output contains only fields listed in the inventory (test below)

## Automated tests

- `warda/tests/test_report.py`: the set of keys in `report.json` is a subset of the inventory table parsed from
  `docs/testing/PRIVACY.md` (keeps docs and code in sync).

## Documentation

- The three files; `README.md` "Try it" links onboarding.

## Manual test (human, before the PR)

1. A tester reads `ONBOARDING.md` and installs without asking a question; any question they ask becomes a doc fix
   before the PR.
2. Run the deletion command from `PRIVACY.md` on your own install → `~/.warda/decisions.jsonl` and
   `feedback.jsonl` gone.
