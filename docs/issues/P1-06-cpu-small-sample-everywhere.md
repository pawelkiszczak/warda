+++
id = "P1-06"
title = "CPU smoke paths with explicit platform limits; shared-machine job queue"
labels = ["phase:1", "team:tools", "type:infra"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01"]
estimate_hours = 5
hardware = "laptop"
github_issue = 16
+++

## Context

Plan §6 rule: "every script can run on CPU with a small-sample flag"; and the shared strong machine needs a queue
instead of first-come. Flags are inconsistent today: `pii_gen` has `--limit`, `build_pool.py` has `--limit`,
`train.py`/`sft.py` have `--tokens`/`--max-train`, `quality/sample.py` and `enrich.py` have none.

## Scope

- Audit every `__main__` script under `pretrain/` and `warda/`; add `--limit N` where missing with the semantics
  "process at most N input records/documents"; document a one-line smoke per script.
- A minimal job queue for the shared machine using `tmux` + a lock directory (no new dependency).
- Out of scope: changing algorithms.

## Deliverables

- SMOKE.md separates portable CPU tools, MLX-on-Mac-only training, and external-model tasks. A skipped
  unsupported platform is not reported as executed/passed. Do not implement a new training backend in this task.
  Queue and model-generation requirements remain explicit per command.

- `docs/dev/SMOKE.md`: table `Script | Smoke command (CPU, < 2 min) | Needs (Ollama / MLX / fastText model)`; every
  script listed; `scripts/smoke_all.sh` runs the subset that needs nothing external and exits non-zero on any
  failure.
- `--limit` added to `quality/sample.py`, `quality/enrich.py`, `quality/stylometrix_worker.py`,
  `sft/generate.py`, `sft/convert_jev.py`, `sft/mix_stages.py` (where a per-input limit makes sense; otherwise the
  table says "n/a: generator is parameterised by count already").
- `scripts/queue.sh`: `queue.sh add "<command>"`, `queue.sh run` (runs jobs from `~/.warda-queue/*.job` one at a
  time inside a `tmux` session `warda-queue`, logs to `~/.warda-queue/logs/`), `queue.sh ls`. Documented in
  `docs/team/HARDWARE.md` "Shared machine queue".

## Definition of done

- [ ] `scripts/smoke_all.sh` passes on a laptop without Ollama/MLX-GPU/fastText model present (skips are printed,
      not failures)
- [ ] Every script in `SMOKE.md` has a smoke line that was executed at least once (record output lines in the PR)
- [ ] `queue.sh` runs two queued jobs sequentially on one machine

## Automated tests

- `scripts/tests/test_smoke_table.py`: every `__main__`-bearing `.py` under `pretrain/` and `warda/` appears in
  `docs/dev/SMOKE.md` (parse the table), so new scripts can't be added without a smoke line.
- ShellCheck on the two shell scripts via pre-commit.

## Documentation

- `docs/dev/SMOKE.md`; `AGENTS.md` "Run" links it; `docs/team/HARDWARE.md` queue section.

## Manual test (human, before the PR)

1. On a laptop, `scripts/smoke_all.sh` → final line `smoke: N passed, M skipped, 0 failed`.
2. `scripts/queue.sh add "sleep 5 && echo one"`, `add "echo two"`, `run` → log shows `one` then `two`, never
   interleaved; `tmux attach -t warda-queue` shows the runner.
