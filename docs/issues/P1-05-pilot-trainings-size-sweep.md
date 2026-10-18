+++
id = "P1-05"
title = "Pilot trainings: model-size sweep and a CPU-runnable mini config"
labels = ["phase:1", "team:model", "type:experiment"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P1-04", "P0-06", "P1-03", "P0-07"]
estimate_hours = 8
hardware = "strong"
github_issue = 15
+++

## Context

ADR-0001 chooses the model size by a sweep. `pretrain/train.py` trains the `model.Config` MoE (8 layers, d=512,
32 experts top-4); `pretrain/sft.py` fine-tunes and evaluates; `track.py` mirrors runs into local MLflow. No sweep
configs exist, and no config runs on CPU for tests.

## Scope

- Three sizes (`xs` ≈ 30M, `s` = current 126M, `m` ≈ 250M total params; expert count/width scaled, 8 layers
  kept), short runs (≤ 100M tokens each) followed by SFT on `pretrain/work/harness_pii/items/` and the bench.
- A `tiny` config (2 layers, d=64, 4 experts) for tests and CPU smoke.
- Out of scope: the full pretraining (P2-01).

## Deliverables

- `pretrain/configs/{tiny,xs,s,m}.json` loaded by `train.py --config PATH` (fields mirror `model.Config`);
  `--config` defaults to `s.json` to preserve current behaviour.
- `train.py --tokens 1e5 --config pretrain/configs/tiny.json --name smoke` finishes on CPU-only MLX in < 2 min.
- `sft.py --data pretrain/work/harness_pii/items --extra-eval dev_ood=pretrain/work/harness_pii/items/dev_ood.jsonl`
  used for each size; results into `docs/model/SWEEP-1.md`: table `size | params | active | tokens | SFT dev
  acc | dev_ood acc | ECE | coverage@1% | ms/decision (MLX, M-series)`; MLflow run names listed.
- Bench integration: `warda/bench/deciders/sft_run.py` registering `sft:<run-name>` that loads
  `pretrain/work/runs/<run>/` and uses `pretrain/sft.py`'s `predict` + `calibration.json` (imports MLX; registered
  lazily so `warda.bench.run --help` works without MLX).

## Definition of done

- [ ] Three sizes trained and scored; `SWEEP-1.md` filled; ADR-0001's rule applied → a chosen size recorded in
      the ADR as "interim"
- [ ] `tiny` smoke documented and used by the new tests
- [ ] `warda.bench.run --decider sft:<run> --set …/dev.jsonl --limit 200` works and reports ECE/coverage

## Automated tests

- `pretrain/tests/test_configs.py` (gated by `WARDA_SLOW`): `tiny` config builds a model, one train step runs,
  loss is finite; `Config` round-trips through JSON for all four files.
- `warda/bench/tests/test_sft_decider.py` (`WARDA_SLOW`): decider on 3 items from `data/harness_pii/sample-v2.jsonl`
  returns actions in `ACTIONS` and confidences in [0, 1]; without `WARDA_SLOW`, importing the registry does not
  import MLX (assert `"mlx" not in sys.modules` after `import warda.bench.deciders`).

## Documentation

- `docs/model/SWEEP-1.md`; `pretrain/README.md` "Model and pretraining" gains `--config` and the configs dir.

## Manual test (human, before the PR)

1. Run the `tiny` smoke on a laptop; `uv run python pretrain/track.py smoke` then open MLflow
   (`uv run mlflow ui --backend-store-uri sqlite:///pretrain/work/mlflow.db`) → the run shows a loss curve.
2. On the strong machine, for the chosen size, time 20 decisions with the bench decider and paste ms/decision.
