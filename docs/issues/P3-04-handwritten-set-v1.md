+++
id = "P3-04"
title = "Handwritten set v1: 300 items, double-labelled, adjudicated"
labels = ["phase:3", "team:labelling", "type:data", "gate:3"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P1-10", "P3-01"]
estimate_hours = 8
hardware = "laptop"
github_issue = 31
+++

## Context

Gate 3 is measured on ~300 realistic hand-written items (plan §4, §5 phase 3). P1-10 fixed the schema, guide and
tooling and delivered 50 development items. This issue is the independent authoring and labelling campaign for 300
final items with the same quality
bar. Estimate is 8 h of coordination; authoring hours are spread across 3–5 labellers (≈ 10 items/h each).

## Scope

- 300 new held-out items (v0 remains development-only; none of its items/twins are reused) (≥ 40 % must be tier 2/3,
  every leaking item with a twin), two labels each, adjudication, kappa
  report, freeze as `v1`.
- Out of scope: new channels/policies.

## Deliverables

- Freeze v1 IDs, policy versions, paired-case groups and file hashes before candidate evaluation. No v0
  payloads, twins or paraphrases in v1; authors/bench owner record the overlap review. Protected spans or
  accepted safe rewrites are adjudicated for redact cases so P0-06 can verify actual disclosure prevention.
  Cases without a provably safe rewrite require deny/ask to count as caught.

- `data/handwritten/v1.jsonl` (300 items; split into `v1-a.jsonl`, `v1-b.jsonl` if > 500 KB — loader accepts a
  glob), `data/handwritten/v1-agreement.json` from `warda/label/export.py`.
- Authoring sprint plan in `docs/data/HANDWRITTEN.md` "v1 campaign": per-author quotas by channel/tier/language,
  weekly checkpoints, the rule that an author never labels their own items.
- `docs/bench/PROTOCOL.md`: `handwritten v1` becomes the gate-3 set; `v0` retired.

## Definition of done

- [ ] 300 valid, adjudicated items; kappa on action ≥ 0.7 and on category ≥ 0.7; mix constraints hold
- [ ] `warda.bench.run` on v1 with `tier1`, `presidio`, `always_allow`, `sft:cand-v1` → table in the PR
- [ ] No author labelled their own items (test below)

## Automated tests

- `warda/bench/tests/test_handwritten.py` extended to v1 (glob) and the self-labelling rule (`author` not in
  `labels[*].labeller`).

## Documentation

- `docs/data/HANDWRITTEN.md` campaign section; `docs/bench/PROTOCOL.md`; `docs/data/DATASET-CARD.md` gains a
  "Handwritten set" section.

## Manual test (human, before the PR)

1. Sample 15 items at random; for each, say in one line why the gold action follows from the policy; any you
   cannot explain → reopen adjudication before the PR.
2. Search v1 for real company/product names from the authors' workplaces (each author greps their own list) →
   zero hits, confirmed in the PR by each author.
