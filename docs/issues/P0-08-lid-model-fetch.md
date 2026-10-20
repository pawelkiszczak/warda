+++
id = "P0-08"
title = "fastText LID model: one checksummed fetch command and a `requires_lid` test gate"
labels = ["phase:0", "team:tools", "type:infra"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-01"]
estimate_hours = 3
hardware = "laptop"
github_issue = 53
+++

## Context

`pretrain/quality/textstats.py` (and `pii_gen.py` language verification through it) needs fastText's `lid.176`
language-ID model, which is not in git. Today three hand-written `curl` commands fetch it and already disagree:
`README.md` and `AGENTS.md` download `lid.176.bin`, `.github/workflows/tests.yml` downloads `lid.176.ftz` (the
compressed model `pretrain/QUALITY_CLASSIFIER.md` says mislabels short Polish text). Nothing checks integrity, and a
fresh clone that skips the step gets 10 opaque `LidUnavailableError` failures in `test_textstats.py`. The model is
CC BY-SA 3.0 and the `.ftz` is over the 500 KB pre-commit limit, so committing it is not an option.

## Scope

- One fetch command with pinned SHA-256 checksums, used by README, `AGENTS.md` and CI.
- A `requires_lid` collection gate: skipped with the fetch command as the reason when the model is missing, but
  never skipped under CI (`CI` set), so CI cannot silently lose these tests.
- Out of scope: auto-downloading from library code or tests; changing which model `textstats` prefers.

## Deliverables

- `pretrain/quality/fetch_lid.py`: `uv run python -m pretrain.quality.fetch_lid [--variant bin|ftz]` (default
  `bin`). Streams from `dl.fbaipublicfiles.com` with retries into a temp file in `MODEL_DIR`, verifies the pinned
  SHA-256, then `os.replace`s into place; a mismatch or transfer error leaves no partial file. An existing file with
  the right checksum is kept without a request; a wrong one is replaced.
- `textstats.lid_model_path()` returns the model `textstats` would load (`.bin` preferred, else `.ftz`) or `None`;
  `_load_lid` uses it. `LidUnavailableError` names the fetch command.
- Root `conftest.py`: `requires_lid` marker skipped when `lid_model_path()` is `None` and `CI` is unset/false.
  Registered in `pyproject.toml`; applied to the `test_textstats.py` tests that call the real model.
- CI `Download fastText LID model` step runs `fetch_lid --variant ftz`.
- `fetch_lid.py` per-file ignore for `T201` (CLI status) with a reason comment.

## Definition of done

- [ ] Fresh clone without the model: `uv run pytest -q` passes with the LID tests skipped, reason names the command
- [ ] Same with `CI=true`: the LID tests run and fail with `LidUnavailableError` (not skipped)
- [ ] After `fetch_lid`: `uv run pytest -q` passes with nothing skipped for LID; same after `--variant ftz` only
- [ ] No `curl … lid.176` left in README, `AGENTS.md` or `tests.yml`
- [ ] `uv run pre-commit run --all-files` passes

## Automated tests

- `pretrain/quality/tests/test_fetch_lid.py` (fake HTTP session, tiny pinned payload): verified download lands
  atomically with no `.part` left; checksum mismatch raises and leaves no file; a valid existing file is kept with no
  request; a corrupt existing file is replaced.
- `warda/tests/test_slow_marker.py`: in a `pytester` run over the real root `conftest.py`, a `requires_lid` test is
  skipped when the model is missing, runs when `CI=true`, and runs when a model file is present.

## Documentation

- `README.md` quick start and `AGENTS.md` (Run, Important Files, Runtime/Tooling, Testing & QA): the fetch command
  and the skip-locally / fail-in-CI rule.
- `textstats.py` module docstring: the fetch command.

## Manual test (human, before the PR)

1. Fresh clone, `uv sync --locked`, `uv run pytest -q` → green, `-rs` shows LID tests skipped with the command.
2. `CI=true uv run pytest -q pretrain/quality` → LID tests fail with `LidUnavailableError`.
3. `uv run python -m pretrain.quality.fetch_lid` → downloads and verifies; rerun → "already present", no download.
4. `uv run pytest -q` → green, no LID skips.
