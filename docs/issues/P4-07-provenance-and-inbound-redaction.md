+++
id = "P4-07"
title = "Provenance tracker and inbound tier-1 redaction (`PostToolUse`)"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P1-01", "P3-07", "P3-08"]
estimate_hours = 8
hardware = "laptop"
github_issue = 42
+++

## Context

FINDINGS §2 "Design settled": deterministic provenance (taint) tracking — mark tool results from policy-restricted
sources, fingerprint with hashed n-grams, check every outbound payload for overlap ("exact data match"); and
`PostToolUse` can replace tool output before the model sees it (tier-1 redaction of inbound SQL/file/log output).
Both strengthen the per-call guard against mosaic leaks spread over calls. This design comes from FINDINGS, not
from the team plan; it is scoped here because the hooks and service exist by phase 4.

## Scope

- `warda/guard/provenance.py`, `POST /v1/observe` endpoint, `PostToolUse` handling in the Claude Code hook (other
  agents follow in their own issues when their post-event supports rewriting), config for restricted sources.
- Out of scope: cross-session persistence beyond 24 h; images/base64 (FINDINGS risk, documented).

## Deliverables

- Also fingerprint exact normalised non-empty lines and extracted key/value values for short restricted
  records that contain fewer than five words (e.g. `DB_HOST=db.internal.example`). Match whole values/lines,
  not arbitrary substrings; document collision/false-positive limits and keep only hashes in the ledger.
- Restricted-source overlap to a non-internal destination imposes `ask_user` for every backend, including MLX
  and torch; model/bands cannot weaken it to allow. Credential blocks retain highest precedence. Bound the
  ledger globally as well as per session; expiry/eviction must be observable as coverage limitations.

- Config `[provenance] restricted_paths = ["**/.env", "**/secrets/**", "db/prod/**"]`, `restricted_tools =
  ["mcp__prod_db__*"]`, `ttl_hours = 24`.
- `warda/guard/provenance.py`: `fingerprint(text) -> set[int]` (hashed word 5-grams, lowercase, 64-bit),
  `Ledger` keyed by session with `add(source_id, text)` and `overlap(payload) -> list[(source_id, matched_ngrams,
  ratio)]`, in-memory with TTL; `ratio ≥ 0.2` or `matched ≥ 3` counts as "draws on restricted source".
- `POST /v1/observe` `{agent, tool, tool_input, tool_output}` → if the tool/path matches restricted rules:
  ledger add; run tier-1 `detect` on `tool_output`; respond `{redacted_output: str|null, restricted: bool,
  tier1_kinds: [...]}` (`redacted_output` only when `mode = enforce` and hits exist).
- `/v1/decide` request gains optional `provenance_check: true` (default true from hooks): the response adds
  `provenance: [{source_id, ratio}]` and the state passed to the model gains a line "Draws on restricted source:
  <source_id>" (the FINDINGS "provenance summary" field); for the tier-1-only decider, any overlap to a non-internal
  destination yields `ask_user` with reason `restricted_source_overlap`.
- Claude Code hook: `PostToolUse` matcher for `Read|Bash|mcp__.*` calling `/v1/observe` and emitting
  `updatedToolOutput` with the redacted text when returned (field name per HOOKS.md).

## Definition of done

- [ ] Before this phase-4 work starts, Gate 2 and Gate 3 records state PASS for the candidate version;
      closing a gate issue with FAIL does not authorise progression. A failed gate requires a new approved PASS.

- [ ] Reading a fictional `.env` through the agent then committing a line from it to `public_repo` → decision
      carries `provenance` with that source and the action is non-allow
- [ ] A `psql`-style output with three fictional PESELs read via Bash shows `[PESEL]` in the agent's view in
      enforce mode; unchanged in shadow mode (log line present)
- [ ] Ledger memory bounded: 10k observations of 4 kB each stay < 200 MB (test below)

## Automated tests

- A one-token `.env` assignment and its copied hostname match; unrelated short words do not. Fake model allow
  with restricted overlap still asks; credentials still block. Cross-session isolation and global memory cap.

- `warda/guard/tests/test_provenance.py`: fingerprint determinism; overlap thresholds; TTL expiry; memory bound
  (count n-grams, not bytes, with a cap per session and LRU eviction).
- `warda/service/tests/test_observe.py`: restricted path matching; redaction only in enforce; decide-with-overlap
  → `ask_user` for the tier-1 decider.
- `warda/hooks/tests/test_claude_code.py`: `PostToolUse` fixture → `updatedToolOutput` emitted only when the
  service returned a redaction.

## Documentation

- `docs/guard/PROVENANCE.md` (design from FINDINGS, limits: transcripts on disk keep originals; side effects
  already happened before PostToolUse); `docs/service/API.md` `/v1/observe`; `docs/service/CONFIG.md`
  `[provenance]`; `docs/integrations/CLAUDE_CODE.md` PostToolUse section.

## Manual test (human, before the PR)

1. In a scratch repo create `.env` with fictional keys; ask Claude Code to read it and then "add the DB host to
   the README and commit" with a public-mapped remote → blocked/asked with `restricted_source_overlap`.
2. Ask it to run a script printing three fictional PESELs → the agent's visible output shows `[PESEL]`.
