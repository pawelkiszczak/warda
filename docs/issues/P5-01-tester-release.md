+++
id = "P5-01"
title = "Tester release: one-command install, privacy-safe defaults, `doctor`"
labels = ["phase:5", "team:tools", "type:feature", "gate:4"]
milestone = "Phase 5 — Shadow mode and gate 4 (weeks 16–20)"
depends_on = ["P4-06", "P4-08", "P4-09"]
estimate_hours = 8
hardware = "laptop"
github_issue = 45
+++

## Context

Plan phase 5: 2–4 weeks with 3–5 external testers, decisions logged only, nothing blocked. Testers run on their
own machines with real work; the install must be one command, shadow mode must be impossible to leave by
accident, and the log must never contain their payloads.

## Scope

- `scripts/install.sh` (macOS/Linux) + `scripts/install.ps1` (Windows), a pinned release tag, model download,
  `doctor` completeness, shadow lock.
- Out of scope: auto-update; packaging on PyPI (decide at gate 4).

## Deliverables

- `scripts/install.sh`: installs `uv` if missing, clones/updates the repo at the release tag into
  `~/.warda/src`, `uv sync --locked` (`--group cpu` on non-Mac), downloads the model bundle from the release
  asset URL (SHA-256 verified; the asset is produced by `scripts/export_model.py` + `tar`), runs `python -m warda
  init --tester` (sets `mode = "shadow"`, `store_payload = false`, `[tester] id = "<random 8 hex>"`), installs
  the hook for the agents found on the machine (`--agents claude-code,codex,…` to choose), starts the service as
  a user service (launchd plist / systemd user unit / Windows scheduled task) and runs `doctor`.
- Shadow lock: with `[tester]` present, `serve --mode enforce` and `mode = "enforce"` are refused with the message
  "tester installs run in shadow mode; remove [tester] to enable enforce" — the tester phase only observes.
- `doctor` extended: service autostart installed, model SHA matches the release, hooks installed per agent, log
  size, last decision timestamp, version vs latest tag.
- `docs/testing/INSTALL.md`: the one command per OS, what gets installed where, how to uninstall completely
  (`scripts/uninstall.sh` removes service, hooks, `~/.warda` after confirmation, keeps nothing).

## Definition of done

- [ ] A fresh macOS user account and a fresh Linux VM go from nothing to `doctor` all-✔ with one command in
      < 10 min on a normal connection
- [ ] `serve --mode enforce` refused on a tester install
- [ ] `uninstall.sh` leaves no files, hooks or services (verified by `doctor` reporting "not installed" and
      `ls ~/.warda` failing)

## Automated tests

- `warda/tests/test_cli.py`: `init --tester` output; shadow lock refusal; `doctor` new rows.
- `scripts/tests/test_install_sh.py`: ShellCheck passes (pre-commit); `bash -n`; a `--dry-run` mode of the
  installer prints the planned steps without executing (tested).

## Documentation

- `docs/testing/INSTALL.md`; `README.md` "Try it" section; release notes template `docs/testing/RELEASE.md`.

## Manual test (human, before the PR)

1. On a colleague's Mac (not yours) run the one command; time it; paste `doctor` output.
2. Edit `warda.toml` to `mode = "enforce"` → `serve` refuses; `doctor` flags it.
3. Run `uninstall.sh`; reboot; confirm the service did not come back and the agent has no hook entry.
