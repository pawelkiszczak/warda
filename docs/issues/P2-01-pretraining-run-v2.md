+++
id = "P2-01"
title = "Pretraining run v2 on the extended corpus at the chosen size"
labels = ["phase:2", "team:model", "type:experiment"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P1-04", "P1-05", "P0-07", "P1-06"]
estimate_hours = 8
hardware = "strong"
github_issue = 22
+++

## Context

Plan phase 2: "training from scratch". The 1B-token run of the 126M MoE (`pretrain/README.md`) is the reference;
P1-04 extends the corpus, P1-05/ADR-0001 fix the size, ADR-0005 fixes where it runs. This is a multi-day job on
one machine; the issue is about reproducibility and the record, not the hours.

## Scope

- One full run (≥ 1B tokens; 2B if the machine allows within 7 days) with the chosen config; checkpoints; MLflow
  record; a run report.
- Out of scope: decision fine-tuning (P3-01).

## Deliverables

- `pretrain/work/runs/<name>/` with `config.json`, `metrics.jsonl`, final checkpoint, `ckpt/` for resume; run
  launched through `scripts/queue.sh` on the shared machine (or rented Apple-silicon Mac per ADR-0005).
- `docs/model/PRETRAIN-v2.md`: config, corpus manifest hash, tokens/s, wall time, loss curve summary (step →
  val loss per source from `val_<source>.bin`), router balance stats (from `metrics.jsonl`), comparison row with
  the 1B reference, checkpoint path and SHA-256.
- `train.py --resume` verified once mid-run (kill and resume; loss continues without a jump).

## Definition of done

- [ ] Final val loss on Polish sources ≤ the 1B reference at equal tokens (else the report explains)
- [ ] `PRETRAIN-v2.md` complete; MLflow run visible with `track.py`
- [ ] Checkpoint loads in `sft.py --base <name> --eval-only` without error

## Automated tests

- None new (long-running). `pretrain/tests/test_configs.py` from P1-05 covers config loading.

## Documentation

- `docs/model/PRETRAIN-v2.md`; `pretrain/README.md` "Model and pretraining" links it and updates the results table.

## Manual test (human, before the PR)

1. `uv run python pretrain/track.py <name>` → MLflow shows the run with the full curve.
2. Greedy sample from the final checkpoint on a Polish and an English prompt (existing sampling path in
   `train.py` eval) → fluent text, paste 5 lines of each.
