+++
id = "P2-06"
title = "`warda` CLI: `init`, `serve`, `decide`, `doctor`, `log`"
labels = ["phase:2", "team:tools", "type:feature"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P2-04"]
estimate_hours = 5
hardware = "laptop"
github_issue = 27
+++

## Context

Testers and teammates need one entry point instead of `python -m` paths. The repo is not an installable package
(`[tool.uv] package = false`); the CLI is therefore `uv run warda …` via a `[project.scripts]` entry only if
packaging is enabled — decision: keep `package = false` and expose `python -m warda` (`warda/__main__.py`), with a
documented shell alias `alias warda='uv run --project <repo> python -m warda'`.

## Scope

- `warda/cli.py` (argparse subcommands) and `warda/__main__.py`.
- Out of scope: packaging/pipx (revisit in P5-01).

## Deliverables

- `init [--dir ~/.warda] [--policy PATH]`: writes `warda.toml` from the `CONFIG.md` example (mode `shadow`),
  copies the chosen policy file (default: `data/policies/software-house.pl.md`), prints next steps; refuses to
  overwrite without `--force`.
- `serve [--port 8787] [--mode shadow|enforce]`: runs the service (uvicorn) with the config; `--mode` overrides
  the file for this process.
- `decide --channel git_commit --destination public_repo --payload "…" | --payload-file PATH` (or `--target
  git:github.com/x/y`): calls the running service, prints the JSON response; exit code 0 allow, 10 redact, 20
  ask_user, 30 block, 2 service unreachable — so shell scripts can branch.
- `doctor`: checks config parses, policy loads, service reachable (`/healthz`), hook installed for each agent
  (phase 4 extends), log file permissions `0600`, prints a table with ✔/✘ and a fix hint per row; exit 1 on any ✘.
- `log [--last N] [--since ISO] [--action block]`: tabulates `decisions.jsonl`; `log --stats` prints counts per
  action/destination class and p50/p95 latency.

## Definition of done

- [ ] `python -m warda init && python -m warda serve &` then `python -m warda decide …` with a PESEL payload
      exits 10 and prints `redact`
- [ ] `doctor` on a fresh machine without config prints one ✘ with the `init` hint and exits 1
- [ ] `log --stats` matches `jq` counts over the file

## Automated tests

- `warda/tests/test_cli.py`: `init` writes/refuses/forces; `decide` exit codes for each action with a fake
  client; `doctor` rows and exit code with each check failing in turn; `log --stats` on a 6-line fixture.

## Documentation

- `docs/service/CLI.md`; `README.md` "Run the guard" uses the CLI; `AGENTS.md` "Run".

## Manual test (human, before the PR)

1. Fresh `~/.warda` (move the old one aside): `init`, `serve`, `decide` with a clean payload → exit 0; with a
   PESEL to `public_repo` → exit 10; stop the service → `decide` exit 2.
2. `doctor` while the service is stopped → the "service" row is ✘ with "run: python -m warda serve".
