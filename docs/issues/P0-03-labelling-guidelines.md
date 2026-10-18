+++
id = "P0-03"
title = "Labelling guidelines v1 with worked examples per category and tier"
labels = ["phase:0", "team:labelling", "type:docs", "gate:1"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = []
estimate_hours = 5
hardware = "laptop"
github_issue = 6
+++

## Context

Gate 1 ("≥ 95 % of labels confirmed by manual verification") needs people to judge synthetic items against a shared
rulebook. The label space already exists in code (`warda/schema.py` after P0-01; today `pii_gen.ACTIONS`,
`CATEGORIES`, `POLICIES`): action `allow|redact|ask_user|block`, category `none|direct_pii|quasi_identifying|
special_category|credential|confidential_business|test_fixture`, destination classes `internal|client|llm|saas|
public`, and the gold action is a pure function `action_for(policy, category, dest)`. Humans therefore verify two
things: the **category** of the payload and that the **policy text** really implies the action.

## Scope

- `docs/labelling/GUIDELINES.md` in English with Polish terms in parentheses where the data uses them.
- Out of scope: the labelling app (P0-04), the handwritten set (P1-10).

## Deliverables

- `docs/labelling/GUIDELINES.md` with sections:
  1. "What you label": the item fields you see (`state`, `question`, `options`, proposed `gold`), what to confirm
     (category; action follows from the policy table), the four verdicts: `confirm`, `fix` (with the corrected
     category/action), `reject` (unusable text, wrong language, stray placeholder like `[[NAME]]`), `unsure`.
  2. "Categories" — one subsection per category with the definition, 3 positive and 3 negative examples (PL + EN),
     and the tier it belongs to (tier 1 explicit identifiers/secrets; tier 2 combinations; tier 3 flow). Examples
     are fictional and at least 2 per category come from `pretrain/work/harness_pii/items/dev.jsonl` (quote `id`).
  3. "Quasi-identifiers" — the mosaic rule: a payload singles out a person when the combination plausibly narrows
     to one individual in the stated context (role + location + event; date of birth + town). Table of 10 example
     combinations with verdicts.
  4. "Special-category data" — list from GDPR art. 9 (health, religion, union membership, sexual orientation,
     criminal record, biometrics, ethnicity, political opinions) with 2 examples each.
  5. "Credentials" — always `block` under every policy; formats to recognise (API keys, private keys, Slack/GitHub
     tokens, passwords in URLs).
  6. "Confidential business" — what counts (contracts, incidents, pricing, infrastructure, personnel events) and
     the known verifier bias: personnel events are not labelled confidential in quasi-identifier payloads.
  7. "Test fixtures vs real records" — fixture provenance (`tests/fixtures/…`, obviously fake values) allows.
  8. "Destination and policy" — how to read the policy block in `state` and map to the action; worked example
     where the same payload is `allow` (processor policy, LLM provider with DPA) and `redact` (strict policy).
  9. "Disagreements" — label independently; never discuss before both labels are in; adjudication by the role in
     ADR-0004; record every disagreement with a one-line reason.
  10. "Time budget" — target 60–90 s per item; mark `unsure` rather than exceed 3 minutes.

## Definition of done

- [ ] All ten sections present; every category has ≥ 3 positive and ≥ 3 negative fictional examples
- [ ] Two labellers who did not write the doc label the same 20 dev items using only the doc and reach Cohen's
      kappa ≥ 0.7 on category (computed with `warda/label/agreement.py` from P0-04, or by hand if P0-04 is not
      merged yet: paste the two label columns into the sheet formula documented in section 9)
- [ ] Disagreements from that trial are listed in a "Known hard cases" appendix

## Automated tests

- None (documentation). markdownlint via pre-commit.

## Documentation

- This file; `README.md` "Contents" adds `docs/labelling/`.

## Manual test (human, before the PR)

1. Give the doc to a person outside the labelling team with 5 items from `dev.jsonl` (ids listed in the PR).
2. They label without asking questions; compare with gold: ≥ 4/5 category matches, and for any miss the doc has a
   section they say "should have covered it" → add the example to that section before the PR.
3. Confirm every example in the doc is fictional (search names in the doc against `pii_gen.py` name pools or
   state "invented by author").
