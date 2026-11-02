+++
id = "P1-08"
title = "Realistic data policies with the GDPR person"
labels = ["phase:1", "team:gdpr", "type:data", "gate:3"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-07", "P0-06", "P0-09"]
estimate_hours = 5
hardware = "laptop"
github_issue = 18
+++

## Context

Training policies are three synthetic tables rendered to text (`pii_gen.POLICIES`, `policy_text`). The guard must
read a *company's* policy as plain text. The handwritten set (P1-10, P3-04) and shadow testers (phase 5) need
realistic policy texts that differ in wording and structure from the training tables, written with the GDPR
person.

## Scope

- Five fictional but realistic policies (PL and EN each): software house with client data separation, bank
  (banking secrecy), public-sector unit, open-source foundation, startup with US cloud processors.
- Out of scope: legal advice; the policy-file format for the service (P2-03).

## Deliverables

- `data/policies/<slug>.{pl,en}.md`: 150–400 words each, written as a company would (sections, exceptions, named
  processor categories), with a machine-readable header block (TOML front matter) `id`, `language`,
  `summary_table`: a `category → destination class → action` table equivalent to `pii_gen.POLICIES` entries so
  gold actions can be computed for items under these policies, plus `exceptions = [...]` free text that the table
  can't express (kept for the model to read; items relying on an exception get `label_method = "manual"`).
- `docs/research/POLICIES.md`: how each policy maps to RODO/GDPR articles, what the summary table cannot express,
  review notes from the GDPR person (GitHub handle).
- `warda/bench/policies.py`: `load_policy(path) -> Policy(id, language, text, table, exceptions)` (shared schema type)
  and `gold_action(policy,
  category, dest)` reusing `warda.schema.DEST_CLASS`.

## Definition of done

- [ ] 10 policy files (5 × 2 languages) with front matter parsing; the GDPR person's review recorded
- [ ] Each policy's table differs from all three training tables in at least one cell
- [ ] `gold_action` agrees with the written text for every cell (checked by the GDPR person on a printed table)

## Automated tests

- `warda/bench/tests/test_policies.py`: all files parse; tables have every category × class cell with an action
  in `ACTIONS`; no policy table equals a `pii_gen.POLICIES` table; PL and EN variants of a policy have identical
  tables.

## Documentation

- `docs/research/POLICIES.md`; `docs/labelling/GUIDELINES.md` section 8 links the policies as the texts used by the
  handwritten set.

## Manual test (human, before the PR)

1. Give one policy (text only, no table) to a developer; ask "may I paste a customer's PESEL into Claude?" → their
   answer equals `gold_action(policy, "direct_pii", "llm_provider")`.
2. Repeat for `public_repo` with `confidential_business` on the bank policy → `block`.
