+++
id = "P1-10"
title = "Handwritten realistic set v0: schema, authoring guide, first 50 items"
labels = ["phase:1", "team:labelling", "type:data", "gate:3"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-03", "P0-04", "P1-08", "P1-01", "P0-06", "P0-09"]
estimate_hours = 8
hardware = "laptop"
github_issue = 20
+++

## Context

Gate 3 is measured on "a manual set" of ~300 realistic examples, each judged by two people (plan §4). Synthetic
items are template-shaped; this set is written by humans to look like real commits, PR bodies, issue comments,
chat, search queries and prompts — with fictional people/companies — under the realistic policies from P1-08.

## Scope

- Schema, authoring guide, authoring helper, and the first 50 items double-labelled.
- Out of scope: reaching 300 (P3-04).

## Deliverables

- Mark v0 as development-only. Add `case_id`/`twin_of`, protected-span annotations or adjudicated accepted safe
  rewrites for redact cases. Human labels establish whether the rewritten payload is safe under that policy;
  merely removing one identifier is insufficient for mosaic cases.

- Schema (`docs/data/HANDWRITTEN.md`, validated by `warda/bench/sets.py`): JSONL rows `id` (`hw-000001`),
  `language`, `channel` (from `warda.schema.CHANNELS`), `destination` (12 ids), `policy_id` (P1-08 ids),
  `payload`, `task` (one-line what the agent was doing), `gold_category`, `gold_action`, `tier` (1|2|3),
  `author`, `labels` (list of `{labeller, category, action, reason}`), `adjudication` (`{by, category, action,
  reason}` or null), `notes`. `gold_*` is the adjudicated value; items without adjudication are excluded by the
  loader unless `--include-unadjudicated`.
- `docs/data/HANDWRITTEN.md` authoring guide: target mix (channels ≥ 8 of 10 used; tiers ≈ 20/50/30 %; actions
  not more than 50 % any single value; PL/EN 60/40); realism rules (write the whole commit/PR/comment, include
  noise: ticket ids, code, emoji); mosaic recipes; the twin rule (every leaking item gets a safe twin with the
  same `task`, `channel`, `destination`, `policy_id` and `gold_action = allow`); fictional-only rule with a name
  pool file `data/handwritten/names.txt` (invented) to draw from.
- `warda/label/author.py`: CLI that prompts for the fields, validates against the schema, assigns the next id,
  appends to `data/handwritten/v0.jsonl`; `--twin ID` pre-fills from an existing item.
- `data/handwritten/v0.jsonl`: 50 items (25 leaking + 25 twins) by ≥ 3 authors, each with two labels (via the
  P0-04 app, `--items data/handwritten/v0.jsonl`) and adjudication; kappa reported in the PR.

## Definition of done

- [ ] 50 items valid against the schema, all adjudicated, kappa on action ≥ 0.7 (ADR-0005 floor)
- [ ] Mix constraints in the guide hold (checked by the test below)
- [ ] `warda.bench.run --set data/handwritten/v0.jsonl --decider tier1 --decider always_allow` works and the
      report is pasted in the PR (tier1 is expected to miss most tier-2/3 items — that is the point of the set)

## Automated tests

- `warda/bench/tests/test_handwritten.py`: schema validation on the real file; every leaking item has a twin
  (same `task`+`channel`+`destination`+`policy_id`, `gold_action == "allow"`); mix constraints (channels ≥ 8,
  no action > 50 %, language ratio within ±10 pts); every `gold_action` consistent with `gold_action(policy,
  gold_category, destination)` unless `notes` starts with `exception:`.
- `warda/label/tests/test_author.py`: id assignment, validation errors on bad channel, `--twin` prefill.

## Documentation

- `docs/data/HANDWRITTEN.md`; `docs/bench/PROTOCOL.md` lists the set with version `v0`.

## Manual test (human, before the PR)

1. Author one new item with `author.py`, then its twin with `--twin` → both appended, ids consecutive, twin has
   `gold_action = allow`.
2. Open 5 random items: a colleague not on the team says they look like real commits/comments.
3. Search `v0.jsonl` for your own employer's name, product names and any real colleague's name → zero hits.
