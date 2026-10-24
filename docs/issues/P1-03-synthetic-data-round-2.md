+++
id = "P1-03"
title = "Synthetic decision data round 2: gap-driven case kinds"
labels = ["phase:1", "team:data-decision", "type:data", "gate:2"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-05", "P1-02", "P1-07", "P1-06", "P0-10"]
estimate_hours = 8
hardware = "strong"
github_issue = 13
+++

## Context

Plan §5 phase 1–2: a second round of decision data aimed at gaps found by labelling (P0-05) and by the research
review (P1-07). Known gaps from `pretrain/README.md`: combined-detail payloads rejected because verifiers call
personnel events confidential; Polish names not declined after prepositions; only 10 outbound channels; policies
are three fixed tables.

## Scope

- New case kinds and policy variants in `pii_gen.py` driven by a written gap list; a new build with manifest.
- Out of scope: hand-written data (P1-10).

## Deliverables

- Add a development-only OOD policy and `dev_ood` items from dev case IDs; keep final `local_only` policy and
  test case IDs untouched for `test_ood`. Document allowed paired reuse within dev/dev_ood and test/test_ood;
  no case/payload crosses train, development, calibration and final-test partitions.

- `docs/data/GAPS-round2.md`: table `Gap | Evidence (gate-1 error type / review finding) | Change | Target count`.
  Must include at minimum: (a) mosaic payloads spread over two sentences; (b) client-codename + deal facts;
  (c) policies with an explicit exception clause ("client X data may go to provider Y") — a 5th policy
  `exception` used in train, not OOD; (d) payloads in Polish with correctly declined names (use a declension table
  in code for the 50 most common first names/surnames in the pools); (e) two new channels: `mcp_tool_call` and
  `package_publish`.
- `pii_gen.py` changes implementing the table; `KIND_WEIGHTS` updated; `POLICIES["exception"]` with its table
  and `policy_text` rendering the exception clause; `TRAIN_POLICIES` includes it.
- Generation run (strong machine, ≥ 1,000 new accepted cases) and `build` → `pretrain/work/harness_pii/manifest.json`
  updated; summary table added to `pretrain/README.md` (same columns as the 2026-10-14 table).
- `data/harness_pii/sample-v2.jsonl`: 200 items (fictional) committed for tests and demos, < 500 KB.

## Definition of done

- [ ] Gate 1 failure remediation may proceed, but no failed dataset is promoted for downstream training.

- [ ] Every gap in the table has a kind/channel/policy in code and ≥ its target count accepted
- [ ] `test_pii_gen.py` extended and green; existing cases regenerate identically for unchanged kinds (seeded)
- [ ] New build keeps split integrity: no `case_id` or payload text shared across train and dev/cal/test
      (reuse the check described in `pretrain/README.md` "Checks after the build" as a test)

## Automated tests

- dev_ood uses development case IDs and its own held-out policy, never local_only; no train/development/cal/final
  partition overlap. Final paired test/test_ood reuse is deliberate and recorded in the manifest.

- `pretrain/harness/tests/test_pii_gen.py`: `policy_text("exception", lang)` contains the exception clause and
  `action_for("exception", …)` follows it; declension helper returns `z Zbigniewem Kowalskim` for the nominative
  pair; new channels present in `CHANNELS` and `warda.schema.CHANNELS`; `build_items` for a two-sentence mosaic
  record labels `quasi_identifying`.
- `pretrain/harness/tests/test_split_integrity.py` on `data/harness_pii/sample-v2.jsonl`: no shared `case_id`/text
  across splits, every `gold` index valid, every `action` equals `action_for(...)`.

## Documentation

- `docs/data/GAPS-round2.md`; `pretrain/README.md` run table; `docs/labelling/GUIDELINES.md` gains examples for
  the new kinds.

## Manual test (human, before the PR)

1. `generate --dry-run --limit 10` → at least one prompt per new kind/channel appears (grep for `mcp_tool_call`,
   `package_publish`, exception clause text).
2. Read 10 random accepted Polish payloads from the new run: names after prepositions are declined.
3. Run P0-05's sampler on the new build with `--n 30` and label 30 items yourself using the guidelines; record the
   confirm rate in the PR (expected ≥ 90 %; below that, file the gap and do not close).
