+++
id = "P4-02"
title = "Cursor hook"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P3-03", "P3-07", "P3-08"]
estimate_hours = 5
hardware = "laptop"
github_issue = 37
+++

## Context

Plan §7 lists Cursor among agents with hooks; `docs/integrations/HOOKS.md` records Cursor's hook config location,
the pre-shell/pre-MCP events, the JSON contract and whether input can be rewritten (if Cursor cannot rewrite,
`redact` degrades to deny with a reason that includes the redacted text so the agent can retry — stated in the
doc as a limitation).

## Scope

- `warda/hooks/cursor.py`, install/uninstall, doctor row, docs.
- Out of scope: Cursor's cloud agents.

Integration contract (shared by P4-01 … P4-05):

- Hook/extension script lives in `warda/hooks/<agent>.py` (or `warda/hooks/<agent>/` for non-Python plugins with
  the Python side in `warda/hooks/<agent>.py`), uses `classify_tool` + `payload_of` (P2-03) and
  `warda.service.client.decide`; the mapping `allow → no-op`, `redact → rewrite input`, `ask_user → ask`,
  `block → deny with reason` is the same as P2-05, with the agent's own field names from `docs/integrations/HOOKS.md`.
- Shadow mode: log only, never alter behaviour. Enforce: fail closed when the service is unreachable.
- `python -m warda.hooks.<agent> install|uninstall [--scope …]` idempotent with backup.
- `warda doctor` (P2-06) gains a row for the agent (installed / not installed / stale command path).
- Tests: fixtures from the P1-09 captures; every action mapping; unreachable service in both modes; install
  idempotence.
- Docs: `docs/integrations/<AGENT>.md` with install/verify/uninstall/limitations.
- Manual test: the three-step scenario of P2-05 (PESEL redact, token deny, shadow pass-through) run in that agent.

## Deliverables

- Enforce mode: `redact` with null/unsafe replacement, unsupported rewrite capability, malformed service
  response or uninspectable outbound payload denies execution with a reason. Never execute the original payload
  as a fallback. Shadow mode leaves the call unchanged and records the limitation. Read failure mode from
  validated local config; invalid config fails closed. Preserve unrelated hooks during install/uninstall.

- `warda/hooks/cursor.py` per HOOKS.md; `agent.name = "cursor"`; `redact` handling per the capability recorded in
  HOOKS.md (rewrite if supported; otherwise deny with the suggested rewrite in the reason).
- Install/uninstall for Cursor's hooks file; doctor row `cursor hook`.

## Definition of done

- [ ] Before this phase-4 work starts, Gate 2 and Gate 3 records state PASS for the candidate version;
      closing a gate issue with FAIL does not authorise progression. A failed gate requires a new approved PASS.

- [ ] Three-step scenario passes (with the documented degradation for redact if applicable)
- [ ] Non-outbound tool calls not sent to the service; latency < 300 ms
- [ ] Install idempotent, uninstall restores

## Automated tests

- Null redacted payload, malformed service response, uninspectable outbound action and missing/invalid config;
  enforce denies, shadow records supported limitations without changing the call. Test platform rewrite fallback.

- `warda/hooks/tests/test_cursor.py`: same shape as P4-01 with Cursor fixtures; the redact degradation path.

## Documentation

- `docs/integrations/CURSOR.md`.

## Manual test (human, before the PR)

1. Enforce mode: Cursor commits a message with a fictional PESEL to a public-mapped remote → `[PESEL]` in
   `git log`.
2. Cursor posts an issue comment containing a fake `xoxb-` token → denied, reason visible in the session.
   Paste the agent's visible reaction to the deny into the PR.
3. Shadow mode: step 1 passes unchanged; `warda log --last 1` shows `redact`, `enforced: false`.
