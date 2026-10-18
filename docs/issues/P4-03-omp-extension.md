+++
id = "P4-03"
title = "omp extension"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-05", "P3-03", "P3-07", "P3-08"]
estimate_hours = 5
hardware = "laptop"
github_issue = 38
+++

## Context

Plan §7: omp has extensions rather than hooks. `docs/integrations/HOOKS.md` records omp's extension API: how an
extension observes tool calls before execution, whether it can veto/rewrite, and its packaging/installation.

## Scope

- extension under `warda/hooks/omp/` (language per HOOKS.md) calling the Warda service;
  Python helper `warda/hooks/omp.py` for install/uninstall/doctor; docs.
- Out of scope: omp features beyond the pre-tool gate.

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

- Extension that intercepts outbound tool calls (same tool-shape list as `classify_tool`: git commit/push, gh,
  curl/http, web search, MCP, publish), posts to `/v1/decide` with `agent.name = "omp"`, and applies the decision
  with omp's veto/rewrite API; shadow mode logs only.
- `python -m warda.hooks.omp install|uninstall` placing/removing the extension where HOOKS.md says; doctor row.

## Definition of done

- [ ] Before this phase-4 work starts, Gate 2 and Gate 3 records state PASS for the candidate version;
      closing a gate issue with FAIL does not authorise progression. A failed gate requires a new approved PASS.

- [ ] Three-step scenario passes in omp
- [ ] Extension load adds no measurable startup delay (< 100 ms, measured with omp's timing output or a
      stopwatch over 5 starts)
- [ ] Install/uninstall idempotent

## Automated tests

- Null redacted payload, malformed service response, uninspectable outbound action and missing/invalid config;
  enforce denies, shadow records supported limitations without changing the call. Test platform rewrite fallback.

- `warda/hooks/tests/test_omp.py`: the Python helper's install/uninstall; if the extension is JS/TS, a Bun/Node
  test file next to it (Biome-checked, pre-commit `biome-check` `files` pattern extended to
  `^warda/hooks/omp/.*\.(js|ts)$`) covering the action mapping with a mocked fetch.

## Documentation

- `docs/integrations/OMP.md`.

## Manual test (human, before the PR)

1. Enforce mode: omp commits a message with a fictional PESEL to a public-mapped remote → `[PESEL]` in
   `git log`.
2. omp posts an issue comment containing a fake `xoxb-` token → denied, reason visible in the session.
3. Shadow mode: step 1 passes unchanged; `warda log --last 1` shows `redact`, `enforced: false`.
