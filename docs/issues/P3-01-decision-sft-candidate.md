+++
id = "P3-01"
title = "Decision fine-tuning on harness data (+ Jev-style joint mix) → candidate model"
labels = ["phase:3", "team:model", "type:experiment", "gate:2"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P2-01", "P2-02", "P0-06"]
estimate_hours = 8
hardware = "strong"
github_issue = 28
+++

## Context

`pretrain/README.md` shows that joint training (Polish + Jev-style public sets) beat staged training and that the
pointer readout learns at this scale. The candidate for gates 2–3 is the P2-01 base fine-tuned on
`harness_pii` v2 items jointly with the existing `work/sft_jev/joint` mixture, selected on dev NLL after
per-type temperature (the current `sft.py` rule).

## Scope

- Mixture builder, three SFT runs (harness-only, joint, joint with harness ×3 upweight), bench scoring.
- Out of scope: calibration bands (P3-02), serving (P3-03).

## Deliverables

- `pretrain/sft/mix_harness.py`: builds `work/sft_harness/{harness_only,joint,joint_x3}/{train,dev,cal,test}.jsonl`
  from `work/harness_pii/items/` and `work/sft_jev/joint/`; `--harness-copies`, `--seed`, `--limit`; `stats.json`
  with counts per family/type/language.
- Three `sft.py` runs with `--extra-eval test_ood=…/test_ood.jsonl --extra-eval handwritten=data/handwritten/v0.jsonl`
  (handwritten converted to item format by `warda/bench/sets.py to_items()` — add this function: renders the
  state with the P1-08 policy text, question "action", 4 options in the item's language).
- `docs/model/SFT-candidate.md`: table `run | test acc | test_ood acc | handwritten acc | ECE | coverage@1% |
  flip rate | by category | by language | by destination class`; comparison to `BASELINES.md` numbers
  (`always_allow`, `tier1`); the chosen candidate named `cand-v1` with its `work/runs/<name>` path and SHA-256.

## Definition of done

- [ ] Gate-2 bar from `docs/bench/PROTOCOL.md` met by the chosen run: accuracy > `tier1` and > `always_allow` on
      `test` and `test_ood`; `test_ood` accuracy within 5 points of `test` (reads the policy, not memorises)
- [ ] `warda.bench.run --decider sft:cand-v1` on `test.jsonl` reproduces `eval.json` accuracy within 0.5 pt
- [ ] `SFT-candidate.md` complete; MLflow runs tracked

## Automated tests

- `pretrain/sft/tests/test_mix_harness.py`: mixture counts follow `--harness-copies`; no test/cal leakage into
  train (by `case_id`); `--limit` produces a 50-row smoke on CPU from `data/harness_pii/sample-v2.jsonl`.
- `warda/bench/tests/test_sets.py`: `to_items` renders a handwritten row into a state whose policy block equals
  the policy file text and whose options are the four `ACTION_TEXT[lang]` strings.

## Documentation

- `docs/model/SFT-candidate.md`; `pretrain/README.md` "Decision fine-tuning" gains the harness mixture.

## Manual test (human, before the PR)

1. Run the `--limit` smoke mixture and `sft.py --epochs 1 --max-train 50` with the `tiny` base on a laptop → finishes,
   writes `eval.json`.
2. Open 10 `cand-v1` errors on `test_ood` from `eval.json`-adjacent predictions (export with `--dump-preds`, add
   the flag if missing) → classify by hand: policy misread vs category miss; paste the tally.
