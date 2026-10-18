+++
id = "P0-06"
title = "Shared evaluation protocol and `warda/bench` harness with trivial baselines"
labels = ["phase:0", "team:benchmarks", "type:feature", "gate:2"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-01"]
estimate_hours = 8
hardware = "laptop"
github_issue = 9
+++

## Context

Plan §8: "one shared way of evaluating". Gates 2 and 3 are stated in those terms (beats "always allow" and pattern
matching; ≥ 80 % leak recall to public destinations at ≤ 5 % unnecessary blocks). `pretrain/sft.py` already
computes accuracy/NLL/Brier/ECE/coverage on its own test split, but there is no evaluator that takes *any* decider
(regex, Presidio, a model, a hook) and scores it on *any* set with the gate metrics.

## Scope

- `warda/bench/` with a `Decider` protocol, set loader, metrics, runner CLI, markdown report, and two trivial
  deciders.
- Out of scope: Presidio/ggshield adapters (P1-11), the model decider (P3-03).

## Deliverables

- Keep the model action metric separate from effective enforcement: redaction with no safe spans is a catch
  only when the evaluated hook/service explicitly denies it. Model-only reports cannot invent that fallback.
  `PolicyOracle` is selected by the runner outside the production registry; production deciders receive no labels.

- `warda/bench/policies.py`: load synthetic policies into the shared `Policy` and evaluate their tables.
  P1-08 extends this loader to realistic policy files. Missing policy/category mappings are explicit errors.
- Freeze gate metrics and a final evaluation manifest before candidate selection. Use `dev`/`dev_ood` for
  selection, `cal` for fitting, and `test`/`test_ood` plus handwritten v1 only for final evaluation. Report
  denominators, unsupported cases and paired-case grouping; a zero denominator is undefined, never a PASS.

- `warda/bench/protocol.py`: `class Decider(Protocol): name: str; def decide(self, request: DecisionInput) -> Decision`
  (`DecisionInput`, `Policy`, and `Decision` from `warda.schema`).
- `warda/bench/sets.py`: `load_set(path) -> list[Item]` accepting the `pii_gen` item JSONL (uses rows with
  `question_id == "action"`, derives `payload` by parsing the state block the way `build_items` wrote it —
  implement `split_state(state) -> dict(policy, channel, destination, payload)` from the labelled sections) and
  the handwritten schema (P1-10) which already has the fields. Field `gold_action` always present.
- `warda/bench/metrics.py`: `confusion(actions_true, actions_pred)`; `leak_recall_public` = fraction of items with
  `gold != allow` and `DEST_CLASS[dest] == "public"` whose enforced outcome prevents disclosure (deny/ask with no
  execution, or a verified safe rewrite);
  a `redact` label alone is not a catch. Safe rewrites must remove all annotated protected content and satisfy
  the item policy; absent rewrite evidence is not a catch. Record the evaluated enforcement outcome separately
  from the model action. `false_block_rate` = fraction
  of items with `gold == allow` predicted `block` or `ask_user`; `over_redaction` = gold allow → redact;
  `unnecessary_intervention_rate` = fraction of gold-allow items
  receiving any non-allow action (including redact); accuracy;
  macro-F1 over the four actions; `ece` (15-bin) and `coverage_at_error(target=0.01)` when `confidence` present
  (same definitions as `pretrain/sft.py` `metrics` — reimplement in pure Python, do not import MLX); per-slice
  breakdown by `language`, `category`, `DEST_CLASS`, `policy`.
- `warda/bench/deciders/trivial.py`: `AlwaysAllow`, `AlwaysBlock`, `AlwaysRedact` (no rewrite: negative control).
  `PolicyOracle` is a separate evaluation-only function taking the labelled item and applying its policy table;
  it is not a production `Decider` and never exposes gold fields to other deciders. Exception-dependent manual
  items are reported unsupported by the table oracle, with coverage stated; never silently dropped from model scores.
- `warda/bench/run.py`: CLI `python -m warda.bench.run --set PATH [--set PATH…] --decider NAME [--decider …]
  --out DIR [--limit N]` → `DIR/report.json` (`{set, decider, n, metrics, slices, items: [{id, gold, pred,
  confidence, category, destination, destination_class, policy_id, language, tier, enforced_outcome,
  rewrite_verified}]}` per pair) and `DIR/report.md` with one table per set: decider × (accuracy, macro-F1,
  leak_recall_public, false_block_rate, unnecessary_intervention_rate, ece, coverage@1%). Decider registry `DECIDERS:
  dict[str, Callable[[],
  Decider]]` in `warda/bench/deciders/__init__.py`.
- `docs/bench/PROTOCOL.md`: metric definitions with formulas, which sets exist, gate thresholds mapped to metric
  names (gate 2: `accuracy` > `AlwaysAllow` and > the tier-1 regex decider on `test` and `test_ood`; gate 3:
  `leak_recall_public ≥ 0.80` and `unnecessary_intervention_rate ≤ 0.05` on the handwritten set), reporting rules
  (always
  report `n`, seed, set version/commit).

## Definition of done

- [ ] `python -m warda.bench.run --set pretrain/work/harness_pii/items/test.jsonl --decider always_allow --decider
      always_block --decider policy_oracle --out /tmp/b` produces both reports; `policy_oracle` accuracy is 1.0
- [ ] `--limit 50` runs in < 5 s on CPU with no MLX import
- [ ] `docs/bench/PROTOCOL.md` is the single definition referenced by gate records

## Automated tests

- Always-redact with no safe rewrite fails the leak gate; always-redact with valid rewrites still fails the
  unnecessary-intervention gate. Partial redaction, absent spans and unknown enforcement outcomes are not catches.
- Gold category reaches only the oracle; per-item report fields support destination-wise calibration.

- `warda/bench/tests/test_metrics.py`: hand-built 8-item set with known confusion → exact
  `leak_recall_public`, `false_block_rate`, macro-F1; ECE of a perfectly calibrated toy is 0; coverage at 1 %
  returns 0 when every confident item is wrong.
- `warda/bench/tests/test_sets.py`: `split_state` round-trips a state built by `pii_gen.build_items` for one
  synthetic record (the record from `test_pii_gen.py::test_build_items_labels_twins_and_holds_out_policy`).
- `warda/bench/tests/test_run.py`: runner on a 6-item temp set with `always_allow` writes `report.json` whose
  `items` length is 6 and `report.md` has a table row per decider.

## Documentation

- `docs/bench/PROTOCOL.md` (new); `README.md` "Contents" `warda/bench` line; `AGENTS.md` "Run" gains the bench
  command.

## Manual test (human, before the PR)

1. Run the DoD command; open `/tmp/b/report.md`: `always_allow` has `leak_recall_public = 0.0`, `always_block` has
   `false_block_rate = 1.0`, `policy_oracle` 1.0 accuracy.
2. Pick 3 rows from `report.json["items"]`, open the matching ids in `test.jsonl`, confirm `gold` matches the
   `action` field there.
3. Run with `--limit 20` on `test_ood.jsonl` → works (the OOD policy text parses).
