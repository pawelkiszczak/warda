+++
id = "P0-02"
title = "Kick-off logistics: task board, owners, hardware inventory, meeting cadence"
labels = ["phase:0", "team:coordination", "type:docs"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = []
estimate_hours = 3
hardware = "laptop"
github_issue = 5
+++

## Context

Plan §4 asks for one owner per team, a sign-up table, a hardware inventory and a weekly 30-minute meeting with
decisions written into the repo. The sign-up table lives in `pretrain/HARNESS_DECIDER_PLAN.md` §4; everything else
has no home yet.

## Scope

- GitHub Projects board linked to this repo, columns `Backlog`, `Ready`, `In progress`, `Review`, `Done`, with the
  `phase:*` and `team:*` labels as board fields.
- `docs/team/OWNERS.md`, `docs/team/HARDWARE.md`, `docs/team/MEETINGS.md`.
- Out of scope: choosing owners (done at the first meeting), Discord setup.

## Deliverables

- `docs/team/OWNERS.md`: table `Team | Owner | Deputy | Contact` for the 8 teams + GDPR person + trainer deputy; a
  line "Disputes on gold labels are settled per ADR-0004".
- `docs/team/HARDWARE.md`: table `Nick | Machine | RAM | GPU | Can run: generation / training / labelling only |
  Remote access (yes/no)`; a section "Shared machine queue" that states the rule from plan §6: jobs go through a
  queue, not first-come (tool chosen in P1-06).
- `docs/team/MEETINGS.md`: cadence (weekly, 30 min), standing agenda (gate status, blocked issues, decisions to
  record), and the rule that every decision becomes an ADR (`docs/decisions/`) or a line in the relevant gate
  record.
- Board URL recorded in `docs/issues/README.md` under a "Board" heading.

## Definition of done

- [ ] Board exists, all open issues appear on it with phase and team fields populated
- [ ] The three team docs exist with headers filled; owner cells may be empty until the first meeting
- [ ] `docs/issues/README.md` links the board

## Automated tests

- None (documentation only). `uv run pre-commit run --all-files` must pass (markdownlint).

## Documentation

- The three new files; `README.md` "Contents" gains a `docs/team/` line.

## Manual test (human, before the PR)

1. Open the board; filter by `team:labelling` → only labelling issues show.
2. Drag one issue to `In progress` → the issue's project field updates on the issue page.
3. Read `HARDWARE.md` as a newcomer with an 8 GB laptop: the "Can run" column tells you which roles you can take
   without asking.
