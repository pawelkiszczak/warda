+++
id = "P4-05"
title = "Remaining agents: Qwen Code, Gemini CLI, Orca (per survey)"
labels = ["phase:4", "team:tools", "type:feature"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P1-09", "P2-05", "P3-03"]
estimate_hours = 8
hardware = "laptop"
github_issue = 40
+++

## Context

Plan §7: the mechanism for Qwen Code, Gemini CLI and Orca is checked in phase 1 (P1-09). This issue implements
whatever HOOKS.md concluded for each (`hook` / `extension` / `plugin` / `unsupported`). Orca runs many agents in
worktrees: if it has no gate of its own, the integration is "ensure each worker agent's hook is installed in the
worktree" via the install helpers' `--scope project`.

## Scope

- One hook module per supported agent (`warda/hooks/qwen_code.py`, `warda/hooks/gemini_cli.py`,
  `warda/hooks/orca.py` or a doc-only section for unsupported ones), under the integration contract.

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

- Per supported agent: hook, install/uninstall, doctor row, `docs/integrations/<AGENT>.md`.
- Per unsupported agent: `docs/integrations/<AGENT>.md` stating the evidence and the workaround (e.g. git-level
  `pre-commit`/`pre-push` hook from P4-08 as the fallback gate).
- `warda/hooks/git.py`: a plain git `pre-commit` + `pre-push` hook (`install --repo PATH`) that sends the commit
  message / pushed commit messages to the service — the agent-agnostic fallback used by unsupported agents and
  by Orca worktrees; `agent.name = "git"`.

## Definition of done

- [ ] Each of the three agents has either a passing three-step scenario or a documented unsupported verdict with
      the git fallback verified in it
- [ ] Git hook: committing a message with a fictional PESEL in enforce mode is rejected with the reason; shadow
      mode logs only

## Automated tests

- `warda/hooks/tests/test_git_hook.py`: runs the hook script with a temp repo (`git init`, commit) and a fake
  service; exit codes; message reading from `.git/COMMIT_EDITMSG`; `pre-push` reads commit list from stdin.
- Per supported agent: `warda/hooks/tests/test_<agent>.py` as in P4-01.

## Documentation

- `docs/integrations/{QWEN_CODE,GEMINI_CLI,ORCA,GIT}.md`.

## Manual test (human, before the PR)

1. For each supported agent: three-step scenario.
2. Orca: launch two workers in two worktrees with `--scope project` hooks installed; both workers' commits appear
   in `warda log` with distinct sessions.
