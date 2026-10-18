+++
id = "P2-03"
title = "Policy configuration file and destination resolver"
labels = ["phase:2", "team:tools", "type:feature"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P0-01", "P1-08"]
estimate_hours = 5
hardware = "laptop"
github_issue = 24
+++

## Context

The service reads the company policy as plain text and must know which destination class an outbound action
targets (`internal|client|llm|saas|public`). Agents only give us a tool name and arguments (a git remote URL, an
HTTP host, an MCP server name, "web search"). A local config file maps those to destination ids and holds the
policy text and mode.

## Scope

- `warda/config.py` (TOML, `tomllib`), `warda/guard/destinations.py`; default config path `~/.warda/warda.toml`
  overridable by `WARDA_CONFIG`.
- Out of scope: the HTTP service (P2-04).

## Deliverables

- Config schema (`docs/service/CONFIG.md`), exact keys:

  ```toml
  mode = "shadow"            # shadow | enforce
  language = "pl"            # policy language used in the state
  [policy]
  file = "policy.md"         # P1-08-style file with front matter, relative to the config dir
  [destinations]             # pattern -> destination id; first match wins; patterns are glob on the resolved target
  "git:github.com/acme-corp/*"   = "internal_repo"
  "git:github.com/*"             = "public_repo"
  "git:gitlab.client.example/*"  = "client_repo"
  "http:api.openai.com"          = "llm_provider"
  "http:*.slack.com"             = "internal_chat"
  "http:*"                       = "saas"
  "search:*"                     = "public_search"
  "mcp:*"                        = "saas"
  "publish:*"                    = "public_package"
  "local:*"                      = "local_model"
  [log]
  path = "~/.warda/decisions.jsonl"
  store_payload = false      # never true in shadow deployments with real data
  ```

- `warda/config.py`: `@dataclass Config(mode, language, policy: Policy, destinations: list[tuple[str, str]],
  log_path: Path, store_payload: bool)`; `load_config(path: Path | None = None) -> Config`; validation errors name
  the key; unknown destination ids rejected against `warda.schema.DEST_CLASS`; missing file → `ConfigError` with
  the `warda init` hint (P2-06).
- `warda/guard/destinations.py`: `Target = tuple[str, str]` (`scheme`, `value`) and `resolve(target: Target,
  rules) -> str` (destination id) using `fnmatch` on `f"{scheme}:{value}"`; `classify_tool(tool_name: str,
  tool_input: dict) -> tuple[str, Target] | None` returning `(channel, target)` for: shell commands containing
  `git push`/`git commit` (channel `git_commit`, target `git:<remote host/path>` resolved via `git remote get-url`
  in `cwd` when available, else `git:unknown`), `gh pr create|edit` → `pr_description`, `gh issue comment|create`
  → `issue_comment`, `curl`/`http`/`wget` with a URL → `http_post`, agent-native web search tools →
  `web_search`, MCP tools (`mcp__<server>__<tool>`) → `mcp_tool_call` + `mcp:<server>`, `npm publish`/`uv
  publish`/`cargo publish` → `docs` + `publish:<registry>`. Returns `None` for anything else (not outbound).
  Payload extraction `payload_of(channel, tool_input) -> str` (commit message `-m` args / heredoc, PR body, comment
  body, request `-d` body, query string).

## Definition of done

- [ ] `load_config` parses the example in `CONFIG.md`; a typo in a destination id gives `ConfigError: destinations:
      "public_rep" is not a destination id`
- [ ] `classify_tool` recognises the 9 tool shapes captured in `docs/integrations/HOOKS.md` (P1-09 samples) and
      returns `None` for `ls`, `pytest`, file edits
- [ ] Unknown git remote resolves to `git:unknown` → rule `"git:*"` if present, else destination `public_repo`
      (fail-safe: unknown is treated as public)

## Automated tests

- `warda/tests/test_config.py`: round-trip of the example; each validation error; env override.
- `warda/guard/tests/test_destinations.py`: parametrised over the HOOKS.md samples (copied into
  `warda/guard/tests/fixtures/tool_calls/*.json`); first-match-wins; `git:unknown` fail-safe; payload extraction
  for `git commit -m "a" -m "b"` and heredoc forms; `curl -d @file` returns the file content when the file exists
  in `cwd`, else the literal.

## Documentation

- `docs/service/CONFIG.md` (new) with the full example and a table of destination ids and their class.

## Manual test (human, before the PR)

1. Write `~/.warda/warda.toml` for your own machine (your org's GitHub as internal); `uv run python -m
   warda.config` prints the parsed config and resolves `git:github.com/<your-org>/x` → `internal_repo` and
   `git:github.com/someone/else` → `public_repo`.
2. Break the TOML (remove a quote) → error message names the line.
