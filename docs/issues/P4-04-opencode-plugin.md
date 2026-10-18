+++
id = "P4-04"
title = "OpenCode plugin"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P3-03"]
estimate_hours = 5
hardware = "laptop"
github_issue = 39
+++

## Context

Plan §7: OpenCode has extensions; HOOKS.md records its plugin API (tool-execute-before style event, veto/rewrite
capability, plugin install path).

## Scope

- plugin under `warda/hooks/opencode/` (language per HOOKS.md), helper
  `warda/hooks/opencode.py`, docs.

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

- Plugin intercepting outbound tools and applying decisions; `agent.name = "opencode"`.
- Install/uninstall helper; doctor row.

## Definition of done

- [ ] Three-step scenario passes in OpenCode
- [ ] Non-outbound tools bypass the service; install/uninstall idempotent

## Automated tests

- `warda/hooks/tests/test_opencode.py` and, if JS/TS, a plugin unit test with mocked fetch (Biome pattern
  extended as in P4-03).

## Documentation

- `docs/integrations/OPENCODE.md`.

## Manual test (human, before the PR)

1. Enforce mode: OpenCode commits a message with a fictional PESEL to a public-mapped remote → `[PESEL]` in
   `git log`.
2. OpenCode posts an issue comment containing a fake `xoxb-` token → denied, reason visible in the session.
3. Shadow mode: step 1 passes unchanged; `warda log --last 1` shows `redact`, `enforced: false`.
