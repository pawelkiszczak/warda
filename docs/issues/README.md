# Task catalogue

One file per task, mirrored to GitHub issues by `scripts/issues_sync.py`. The file is the source of truth: edit it
and run the sync; do not edit issue bodies on GitHub.

- `P<phase>-<nn>-<slug>.md` — TOML front matter (`id`, `title`, `labels`, `milestone`, `depends_on`,
  `estimate_hours`, `hardware`, `github_issue`) and seven fixed sections: Context, Scope, Deliverables, Definition of
  done, Automated tests, Documentation, Manual test (human, before the PR).
- Phases and gates follow `pretrain/HARNESS_DECIDER_PLAN.md`; a gate issue closes only when its criteria are met and
  the gate record under `docs/gates/` is merged.
- Labels: `phase:N`, one `team:*`, one `type:*`, optional `gate:N`. The `hardware:*` label is added by the sync
  from the `hardware` field — do not write it in `labels`.
- Compute levels (`hardware` field / label): `laptop` = any 8–16 GB laptop, CPU only, no shared machine;
  `strong` = Mac ≥ 64 GB or NVIDIA ≥ 24 GB for generation, Mac 96–128 GB or rented GPU for training, run through
  `scripts/queue.sh`; `cloud` = rented or free cloud GPU, budget approved first. Every task, including `strong`
  and `cloud` ones, has a CPU `--limit` smoke path that is part of its definition of done. Filter the board by
  `hardware:laptop` to find work that needs no special machine.
- Every task is 2–5 h unless marked otherwise.

```bash
uv run python scripts/issues_sync.py lint                 # validates the catalogue (also runs in pytest)
uv run python scripts/issues_sync.py sync --dry-run       # shows what would change on GitHub
uv run python scripts/issues_sync.py sync                 # creates/updates labels, milestones, issues, project cards
```

## Board

[Warda project](https://github.com/users/pawelkiszczak/projects/2), created and filled by `sync`: one card per issue,
fields Status (`Backlog`, `Ready`, `In progress`, `Review`, `Done`), Phase, Team, Hardware, Estimate; views
"All tasks", "Board", "Ready on a laptop", "Needs strong compute". `sync` sets every field except Status from the
file and puts new cards in `Backlog`; every Status move after that is made by people. When a card may go to `Ready`
and how to run `sync`: `CONTRIBUTING.md`.
