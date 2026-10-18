+++
id = "P2-05"
title = "First integration: Claude Code `PreToolUse` hook"
labels = ["phase:2", "team:tools", "type:feature"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P1-09", "P2-04"]
estimate_hours = 8
hardware = "laptop"
github_issue = 26
+++

## Context

Plan phase 2: "skeleton of the local service and the first integration". FINDINGS §2: Claude Code `PreToolUse`
can deny or rewrite tool input (`updatedInput`), hooks fail open on timeout unless configured otherwise, managed
settings can make hooks mandatory. P1-09 captured the exact event JSON.

## Scope

- `warda/hooks/claude_code.py`: stdin → service → stdout decision; install/uninstall helper; docs.
- Out of scope: `PostToolUse` inbound redaction (P4-07), other agents (phase 4).

## Deliverables

- Enforce mode: `redact` with null/unsafe replacement, unsupported rewrite capability, malformed service
  response or uninspectable outbound payload denies execution with a reason. Never execute the original payload
  as a fallback. Shadow mode leaves the call unchanged and records the limitation. Read failure mode from
  validated local config; invalid config fails closed. Preserve unrelated hooks during install/uninstall.

- `warda/hooks/claude_code.py`: reads the `PreToolUse` JSON from stdin; `classify_tool(tool_name, tool_input)`
  (P2-03) → if `None`, exit 0 with no output (not outbound); else build the `/v1/decide` request (`agent.name =
  "claude-code"`, `session` from the event's session id, `task` from the event's last user message if present in
  the payload — else null) and call `client.decide`. Output mapping (field names per `docs/integrations/HOOKS.md`,
  verified in P1-09): `allow` → exit 0 no output; `redact` → JSON with `updatedInput` replacing the payload field
  (commit `-m` args / PR body / comment body / request body) by `redacted_payload` and a `permissionDecisionReason`
  saying what was masked; `ask_user` → `permissionDecision: "ask"` with the reason; `block` → `permissionDecision:
  "deny"` with the reason (deny-and-continue: the agent sees the reason and can rewrite). In shadow mode
  (`enforced: false`) always exit 0 silently after logging. Service unreachable: shadow → exit 0; enforce → deny
  with reason "warda service unreachable" (fail closed).
- Install helper `python -m warda.hooks.claude_code install [--scope user|project]` that merges a `PreToolUse`
  matcher for `Bash|WebSearch|WebFetch|mcp__.*` into `~/.claude/settings.json` or `.claude/settings.json`
  (idempotent; backs up the file to `settings.json.bak-<ts>`), command `uv run --project <repo> python -m
  warda.hooks.claude_code`, timeout 5 s; `uninstall` removes exactly what it added.
- Hook latency budget: < 300 ms end-to-end on the tier-1 path (process start + HTTP).

## Definition of done

- [ ] With the service in `enforce` mode, asking Claude Code to commit a message containing a fictional PESEL to a
      `public_repo`-mapped remote results in a commit whose message contains `[PESEL]` instead of the number
- [ ] A `ghp_…` token in a commit message is denied and Claude Code reports the reason
- [ ] In `shadow` mode the same actions pass unchanged and appear in `decisions.jsonl`
- [ ] `install` twice leaves one hook entry; `uninstall` restores the original file byte-for-byte when nothing
      else changed

## Automated tests

- Null redacted payload, malformed service response, uninspectable outbound action and missing/invalid config;
  enforce denies, shadow records supported limitations without changing the call. Test platform rewrite fallback.

- `warda/hooks/tests/test_claude_code.py`: feed each fixture event from `warda/guard/tests/fixtures/tool_calls/`
  with a fake service (monkeypatch `client.decide`) returning each action → assert exact stdout JSON / empty
  output / exit code; unreachable service in both modes; non-JSON stdin → deny in enforce, diagnostic and pass-through
  in shadow; `install`/`uninstall`
  idempotence on a temp settings file with pre-existing unrelated hooks preserved.

## Documentation

- `docs/integrations/CLAUDE_CODE.md`: install, verify, uninstall, what is intercepted, limitations (PostToolUse
  not yet; transcripts still contain the original text — FINDINGS caveat), troubleshooting (service down, timeout).
- `README.md` "Run the guard" links it.

## Manual test (human, before the PR)

1. In a scratch repo with a remote mapped to `public_repo`, service in `enforce`: ask Claude Code "commit with
   message 'fix: klient Jan Nowak PESEL 44051401458 zgłosił błąd'" → `git log -1` shows `[PESEL]` and the hook
   reason was shown in the session.
2. Ask it to add a comment with a fake `ghp_` token to an issue via `gh` → denied; the agent rewrites without the
   token on its own or asks you.
3. Switch to `shadow`; repeat 1 → commit unchanged; `decisions.jsonl` has the `redact` line with `enforced: false`.
4. Time 10 `git status` calls through the agent with and without the hook; difference < 300 ms each.
