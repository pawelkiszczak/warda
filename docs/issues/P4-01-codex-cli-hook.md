+++
id = "P4-01"
title = "Codex CLI hook"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P3-03", "P3-07", "P3-08"]
estimate_hours = 5
hardware = "laptop"
github_issue = 36
+++

## Context

FINDINGS §2: Codex has the same five core hook events as Claude Code. `docs/integrations/HOOKS.md` (P1-09) holds
the verified config path, event names, stdin/stdout JSON and fail-open behaviour for Codex CLI. The Claude Code
hook (P2-05) is the reference implementation.

## Scope

- `warda/hooks/codex.py`, install/uninstall into Codex's hooks config, doctor row, docs.
- Out of scope: Codex cloud/web; post-execution output rewriting.

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

- `warda/hooks/codex.py` implementing the pre-tool event per HOOKS.md: parse stdin, `classify_tool`, call the
  service, emit the Codex decision JSON (deny / rewritten input / ask) or nothing; `agent.name = "codex"`.
- `install --scope user|project` merging into the Codex hooks file named in HOOKS.md (backup, idempotent);
  `uninstall`.
- `warda doctor` row `codex hook`.

## Definition of done

- [ ] Before this phase-4 work starts, Gate 2 and Gate 3 records state PASS for the candidate version;
      closing a gate issue with FAIL does not authorise progression. A failed gate requires a new approved PASS.

- [ ] The three-step manual scenario passes in Codex CLI (redact, deny, shadow)
- [ ] Hook adds < 300 ms per intercepted call; non-outbound tools are not sent to the service
- [ ] Install twice → one entry; uninstall → original file

## Automated tests

- Null redacted payload, malformed service response, uninspectable outbound action and missing/invalid config;
  enforce denies, shadow records supported limitations without changing the call. Test platform rewrite fallback.

- `warda/hooks/tests/test_codex.py`: fixtures `warda/hooks/tests/fixtures/codex/*.json` from P1-09; mapping for
  each action; unreachable service shadow/enforce; install/uninstall on a temp config with unrelated entries.

## Documentation

- `docs/integrations/CODEX.md`.

## Manual test (human, before the PR)

1. Enforce mode: Codex commits a message with a fictional PESEL to a public-mapped remote → `[PESEL]` in `git log`.
2. Codex posts an issue comment containing a fake `xoxb-` token → denied, reason visible in the session.
3. Shadow mode: step 1 passes unchanged; `warda log --last 1` shows `redact`, `enforced: false`.
