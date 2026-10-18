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
decisions written into the repo. The sign-up table lives in `pretrain/HARNESS_DECIDER_PLAN.md` §4. The project board
(<https://github.com/users/pawelkiszczak/projects/2>) with its fields and views is created and filled by
`scripts/issues_sync.py`, and the workflow is in `CONTRIBUTING.md`; what remains are the board settings the API
cannot change and the team docs.

## Scope

- Board settings available only in the web UI: enable the built-in workflows "Item closed" → Status `Done` and
  "Pull request merged" → Status `Done`; on the "Board" view show the Team and Hardware fields on cards.
- `docs/team/OWNERS.md`, `docs/team/HARDWARE.md`, `docs/team/MEETINGS.md`.
- Out of scope: choosing owners (done at the first meeting), Discord setup.

## Deliverables

- Assign a GitHub assignee before moving an issue to In progress; team labels are not ownership. Record hands-on
  effort separately from compute time, authoring/labelling person-hours and observation weeks. The catalogue
  totals 271 estimated hours, including 122 tools hours; these are not the full project delivery duration.
  Re-estimate affected tasks after contract corrections and record capacity by named owner; do not invent owners.

- `docs/team/OWNERS.md`: table `Team | Owner | Deputy | Contact` for the 8 teams + GDPR person + trainer deputy; a
  line "Disputes on gold labels are settled per ADR-0004".
- `docs/team/HARDWARE.md`: table `Nick | Machine | RAM | GPU | Can run: generation / training / labelling only |
  Remote access (yes/no)`; a section "Shared machine queue" that states the rule from plan §6: jobs go through a
  queue, not first-come (tool chosen in P1-06).
- `docs/team/MEETINGS.md`: cadence (weekly, 30 min), standing agenda (gate status, blocked issues, decisions to
  record), and the rule that every decision becomes an ADR (`docs/decisions/`) or a line in the relevant gate
  record.
- `CONTRIBUTING.md` "Project board" section checked against the live board; fix whichever is wrong.

## Definition of done

- [ ] Ready means prerequisites satisfied and scope reviewed, not merely dependency issues closed: gate
      dependencies need a recorded PASS. No unassigned issue is moved to In progress.

- [ ] Both built-in workflows enabled; closing a test issue moves its card to `Done`
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
