# Task catalogue

One file per task, mirrored to GitHub issues by `scripts/issues_sync.py`. The file is the source of truth: edit it
and run the sync; do not edit issue bodies on GitHub. Sync also reconciles colours/descriptions of existing
catalogue labels, so corrected hardware guidance is not limited to newly created labels.

- `P<phase>-<nn>-<slug>.md` — TOML front matter (`id`, `title`, `labels`, `milestone`, `depends_on`,
  `estimate_hours`, `hardware`, `github_issue`) and seven fixed sections: Context, Scope, Deliverables, Definition of
  done, Automated tests, Documentation, Manual test (human, before the PR).
- Phases and gates follow `pretrain/HARNESS_DECIDER_PLAN.md`; a gate issue closes only when its criteria are met and
  the gate record under `docs/gates/` is merged.
- Labels: `phase:N`, one `team:*`, one `type:*`, optional `gate:N`. The `hardware:*` label is added by the sync
  from the `hardware` field — do not write it in `labels`.
- Compute levels (`hardware` field / label): `laptop` = ordinary 8–16 GB laptop, no discrete GPU or shared
  machine required; optional Apple GPU acceleration is encouraged where supported and measured faster.
  `strong` = Mac ≥ 64 GB or NVIDIA ≥ 24 GB for supported generation; MLX training needs a sufficiently
  provisioned Apple Silicon Mac, typically 96–128 GB, local or rented, through `scripts/queue.sh`.
  `cloud` = approved remote compute; renting an NVIDIA GPU does not make the MLX trainer portable. CUDA
  training needs a separate approved port. Preserve portable CPU tooling smokes and Mac-only MLX smokes as
  applicable; do not label unavailable backends as a successful run. Filter `hardware:laptop` for tasks needing
  no shared machine.
- [Apple Silicon acceleration](../performance/APPLE_SILICON.md) is the shared contract: prefer useful MLX/Metal
  speedups with verified backend placement, exact preprocessing parity and end-to-end evidence. P1-12 owns
  preprocessing, P1-04 adopts it, and the generation/training/serving tasks own their corresponding GPU paths.
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
