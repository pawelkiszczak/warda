+++
id = "P1-09"
title = "Hook mechanism survey for all target agents"
labels = ["phase:1", "team:tools", "type:docs"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01"]
estimate_hours = 5
hardware = "laptop"
github_issue = 19
+++

## Context

Plan §7: Claude Code, Codex and Cursor have hooks; omp and OpenCode have extensions; Qwen Code, Gemini CLI and Orca
are to be checked in phase 1. FINDINGS §2 lists Claude Code events (`PreToolUse` with deny / `updatedInput`,
`PostToolUse` with `updatedToolOutput`, `UserPromptSubmit`, managed settings `allowManagedHooksOnly`, fail-open on
timeout unless `onFailure: "block"`). Phase 2 and 4 integrations need one verified table before coding.

## Scope

- `docs/integrations/HOOKS.md`: per agent, verified against the agent's documentation and by running a trivial
  hook on a laptop.
- Out of scope: writing the real hooks.

## Deliverables

- Capture only in a disposable repo/session using authored fictional fixtures; do not install on normal work
  sessions. Truncation is a size limit, not sanitisation. Drop authentication headers, environment values and
  unrelated event fields; remove capture hook and delete local capture after fixture review.

- Per agent (Claude Code, Codex CLI, Cursor, omp, OpenCode, Qwen Code, Gemini CLI, Orca): config file path and
  format; event names that fire before an outbound action (tool call, shell command, MCP call, web search); exact
  stdin/stdout JSON for a `PreToolUse`-equivalent, with the fields to deny, to rewrite input, to ask the user;
  post-execution event and whether output can be rewritten; timeout and fail-open/closed behaviour; whether an
  organisation can enforce the hook; how the tool name/arguments of `git commit`, `git push`, `gh pr create`,
  `gh issue comment`, `curl`, web search and MCP tools appear in the payload (one captured sample each, with any
  real paths replaced by placeholders); version tested.
- A "capture" script `warda/hooks/capture.py` that, installed as a hook, requires explicit `--synthetic-fixtures`
  opt-in and appends allowlisted event metadata plus fictional
  fixture payloads to `~/.warda/capture.jsonl` (0700 directory, 0600 file), strings capped at 200 chars — used to
  produce the samples and reused by
  integration issues as a debugging aid.
- Comparison table and a "Mechanism per agent for phase 4" row (`hook` / `extension` / `plugin` / `unsupported:
  reason`).

## Definition of done

- [ ] All eight agents have a filled section; unsupported ones state the evidence
- [ ] At least one captured sample per supported agent for `git push` and one for an HTTP/web action
- [ ] `capture.py` never writes more than 200 chars of any string field

## Automated tests

- Capture refuses absent synthetic opt-in; nested credential/environment fields are omitted, permissions are
  private, and cleanup removes only the capture hook it installed.

- `warda/hooks/tests/test_capture.py`: truncation of nested string fields; append semantics; writes nothing if
  stdin is not JSON (exit 0, so the agent is never blocked by the capture hook).

## Documentation

- `docs/integrations/HOOKS.md` (new); `README.md` "Contents" adds `docs/integrations/`.

## Manual test (human, before the PR)

1. Install `capture.py` in your own agent per the doc; run `git status` through the agent → a line appears in
   `~/.warda/capture.jsonl`; no string longer than 200 chars (`jq` check in the doc).
2. Make the hook time out deliberately (add `sleep 60`) → observe and record whether the agent proceeded
   (fail-open) or stopped; the doc's row must match what you saw.
