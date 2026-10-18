+++
id = "P5-04"
title = "Gate 4 record, publication decision and release checklist"
labels = ["phase:5", "team:coordination", "type:decision", "gate:4"]
milestone = "Phase 5 — Shadow mode and gate 4 (weeks 16–20)"
depends_on = ["P5-03", "P0-07"]
estimate_hours = 4
hardware = "laptop"
github_issue = 48
+++

## Context

Plan §3 gate 4: "works in practice: rare false alarms, fast, real catches" and phase 5 ends with the publication
decision. ADR-0002 deferred the licence/release form (open model? dataset only?) to this point.

## Scope

- `docs/gates/GATE4.md`, ADR-0002 finalised, release checklist; if PASS, the first tagged release.
- Out of scope: marketing, packaging beyond the tester installer.

## Deliverables

- `docs/gates/GATE4.md`: criteria frozen before external tester observation in P5-02 (false-alarm rate ≤ 5 % of
  reviewed non-allow decisions, at least 100 reviewed non-allow decisions overall with a prespecified random
  review sample and coverage per tester; p95 histogram-bin upper bound within ADR-0005; ≥ 3 real catches
  confirmed by testers as "would have leaked"). Insufficient evidence is INCONCLUSIVE, not PASS; numbers from
  `week-4.md`; PASS/FAIL/INCONCLUSIVE; approvers (coordinator, tools owner, GDPR person, one
  tester).
- ADR-0002 updated to `accepted` with the decision on: code (stays Apache-2.0), dataset (`data/` publication:
  yes/no, licence), weights (publish/hold, licence), model card requirements, and what the public README claims
  (FINDINGS: "risk reduction plus audit, never a guarantee").
- `docs/testing/RELEASE.md` checklist executed for `v0.1.0`: tag, model bundle asset with SHA-256, installer
  points at the tag, `README.md` status line changed from "research and data stage" to the release status,
  `FINDINGS.md` updated with gate outcomes, tester data deleted per `PRIVACY.md` retention.

## Definition of done

- [ ] GATE4.md merged with approvers and date; ADR-0002 accepted
- [ ] If PASS: `v0.1.0` tag exists, release has the model asset, installer from a clean machine installs that
      tag; if FAIL or INCONCLUSIVE: the stop/continue decision and next-phase outline are in GATE4.md
- [ ] Tester logs deleted; confirmation from each tester recorded

## Automated tests

- Gate calculator rejects undefined rates, inadequate review counts, latency overflow and mixed unfrozen
  versions; it uses the precommitted protocol, not thresholds selected from the observed results.

- `scripts/tests/test_release_checklist.py`: every checklist item in `RELEASE.md` is a `- [x]` after release
  (parsed; test is skipped unless `WARDA_RELEASE=1`).

## Documentation

- `docs/gates/GATE4.md`, `docs/decisions/ADR-0002-*.md`, `README.md` status, `FINDINGS.md`.

## Manual test (human, before the PR)

1. Second person recomputes the false-alarm rate from `week-4.md` inputs.
2. On a clean machine, the installer with the tag installs the released model (SHA matches the release page).
