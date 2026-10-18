+++
id = "P0-05"
title = "Verification round 1: 100 synthetic items double-labelled, gate 1 record"
labels = ["phase:0", "team:labelling", "type:data", "gate:1"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-03", "P0-04", "P0-07"]
estimate_hours = 5
hardware = "laptop"
github_issue = 8
+++

## Context

Gate 1: manual verification confirms ≥ 95 % of labels. The build has 23,912 items from 2,296 cases; verifiers were
two LLMs. This round measures how often humans agree with the generated gold on a stratified sample and records
the gate decision.

## Scope

- Sample 100 items from `pretrain/work/harness_pii/items/{dev,cal}.jsonl` stratified by `category` (≥ 12 per
  category, remainder proportional) and `language` (60/40 pl/en), `question_id == "action"` only, seed 0, via a
  script `warda/label/sample.py` (`--items … --n 100 --by category,language --seed 0 --out FILE`).
- Two labellers, independent, using P0-03 and P0-04; adjudication of disagreements per ADR-0004.
- Out of scope: fixing the generator (file follow-up issues under P1-03).

## Deliverables

- `warda/label/sample.py` as above (deterministic; writes the sample JSONL plus `sample_manifest.json` with
  counts per stratum).
- `data/verification/round1/sample.jsonl` (100 items, fictional content, < 500 KB), `labels_alice.jsonl`,
  `labels_bob.jsonl`, `adjudicated.jsonl` (final category/action per item with `adjudicator` and `reason`).
- `docs/gates/GATE1.md`: method, counts, confirm rate (items where adjudicated == generated gold), kappa (category,
  action), table of error types (e.g. "verifier missed quasi-identifier", "safe twin still identifying"), decision
  `PASS` / `FAIL` with date and signatures (GitHub handles), and the list of follow-up issues.

## Definition of done

- [ ] 100/100 items have two labels and an adjudicated verdict
- [ ] `docs/gates/GATE1.md` states the confirm rate and the PASS/FAIL decision; if < 95 %, lists the generator
      fixes as new issues under P1-03 and the re-run plan
- [ ] Sampling is reproducible: re-running `sample.py` with the manifest's seed yields identical ids

## Automated tests

- `warda/label/tests/test_sample.py`: stratified counts match the manifest; same seed → same ids; `--n` larger
  than available in a stratum degrades gracefully (takes all, warns).
- `warda/label/tests/test_verification_data.py`: every id in the three label files exists in `sample.jsonl`;
  `adjudicated.jsonl` has exactly 100 rows with `category` in schema and `action` consistent with
  `pii_gen.action_for(policy, category, destination)`.

## Documentation

- `docs/gates/GATE1.md` (new); `docs/labelling/GUIDELINES.md` "Known hard cases" appendix extended with the round's
  disagreements.

## Manual test (human, before the PR)

1. Open `docs/gates/GATE1.md`; recompute confirm rate by hand from `adjudicated.jsonl` vs `sample.jsonl` gold for
   10 random items → matches the table.
2. Pick 3 disagreements; the reasons recorded make the final verdict understandable without asking the labellers.
3. `grep -c '"language": "pl"' data/verification/round1/sample.jsonl` → 60.
