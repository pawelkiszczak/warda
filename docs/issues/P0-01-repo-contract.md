+++
id = "P0-01"
title = "Repo contract: AGENTS.md, `warda/` package skeleton, shared schema, test wiring"
labels = ["phase:0", "team:tools", "type:infra"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = []
estimate_hours = 5
hardware = "laptop"
github_issue = 4
+++

## Context

Section 7 of `pretrain/HARNESS_DECIDER_PLAN.md` requires a repo contract that every coding agent and human reads
first: how to run tests, repo layout, data formats, prohibitions. Product code (guard, service, hooks, bench,
labelling) will live in a new top-level `warda/` package while `pretrain/` stays research. Constants that both sides
need (actions, categories, destinations, channels) currently live only in `pretrain/harness/pii_gen.py`.

## Scope

- `AGENTS.md` at repo root and `CLAUDE.md` as a relative symlink to it.
- `warda/` package skeleton with `warda/schema.py` holding the shared literals, imported by `pii_gen.py`.
- pytest / mypy / ruff / pre-commit wired to `warda/`.
- `WARDA_SLOW` env gate for tests needing MLX, fastText models or network.
- Out of scope: any guard logic, service, or hook code.

## Deliverables

- Make non-ML tooling installable on supported Linux/Windows laptops now: platform-mark MLX/mlx-lm, lazy-load
  MLX-only modules, and skip MLX tests by capability. Run a non-ML smoke on Linux and Windows. This does not
  promise portable training; document MLX training as Apple-silicon-only until a training port is separately scoped.

- Shared `Policy` dataclass in `warda/schema.py`: `id`, `language`, `text`, `table` (category → destination
  class → action), `exceptions` (list of text clauses). Shared `DecisionInput`: `payload`, `channel`,
  `destination`, `policy: Policy`, `language`, `task: str | None`, `provenance: list[str]`. No gold fields.
  Runtime boundaries validate these fields; TypedDict annotations alone are not validation.

- `AGENTS.md` sections, in order: "Run" (`uv sync --locked`, `uv run pytest -q`, `uv run pre-commit run
  --all-files`, `WARDA_SLOW=1 uv run pytest -q` for slow tests); "Layout" (`warda/` product code with one line per
  subpackage: `guard`, `service`, `hooks`, `bench`, `label`, `schema.py`, `cli.py`; `pretrain/` research; `data/`
  committed synthetic sets; `docs/` plans, ADRs, gates, issues; `pretrain/work/` gitignored artefacts); "Data
  formats" (decision item JSONL fields: `id`, `state`, `question`, `options`, `gold`, `type`, `family`,
  `template_id`, `case_id`, `language`, `split`, `label_method`, `source`, `license`, plus harness fields
  `question_id`, `category`, `policy`, `destination`, `action`; link to `warda/schema.py`); "Rules" (no real
  personal data, no work data, no secrets in prompts or code; one task = one branch/worktree named
  `<issue-id>-<slug>`; small PRs; tests pass before merge; agent proposes, human decides on gold labels);
  "Hardware" (every script has a CPU small-sample flag; strong hardware optional).
- `CLAUDE.md` → symlink `AGENTS.md` (pre-commit `check-symlinks` must pass).
- `warda/__init__.py` (docstring only), `warda/schema.py` with: `ACTIONS = ("allow", "redact", "ask_user",
  "block")`, `CATEGORIES`, `DEST_CLASSES = ("internal", "client", "llm", "saas", "public")`, `DEST_CLASS: dict[str,
  str]` (the 12 destination ids from `pii_gen.DEST_CLASS`), `CHANNELS: tuple[str, ...]` (the 10 outbound channel
  ids), `INBOUND_CHANNELS` (3 ids), `LANGUAGES = ("pl", "en")`, and `class Decision(TypedDict)`: `action: str`,
  `confidence: float`, `reason: str`, `redacted_payload: str | None`, `category: str | None`. `pii_gen.py` imports
  `ACTIONS`, `CATEGORIES`,
  `DEST_CLASS` and `DEST_CLASSES` (replacing its `CLASSES`; `_rule` and `CLASS_TEXT` keep working on the same
  five strings) from `warda.schema` and deletes its own copies
  (`grep -n "^ACTIONS\|^CLASSES\|^DEST_CLASS\|^CATEGORIES" pretrain/harness/pii_gen.py` returns nothing after).
- Empty packages with `__init__.py`: `warda/guard`, `warda/service`, `warda/hooks`, `warda/bench`, `warda/label`,
  `warda/tests`.
- `pyproject.toml`: `testpaths = ["pretrain", "scripts", "warda"]`; mypy `files` adds `"warda"`; ruff
  per-file-ignores add `"warda/tests/**/*.py" = ["S101"]`. `.pre-commit-config.yaml` mypy `files:
  ^(pretrain|scripts|warda)/`. `.github/workflows/tests.yml` unchanged (it runs `pytest -q` which picks up the new
  testpaths).
- `warda/tests/conftest.py` with `slow = pytest.mark.skipif(os.environ.get("WARDA_SLOW") != "1", reason="set
  WARDA_SLOW=1")` exported for reuse.

## Definition of done

- [ ] `uv run pytest -q` passes and collects tests from `warda/`
- [ ] `uv run pre-commit run --all-files` passes (mypy covers `warda/`)
- [ ] `pretrain/harness/tests/test_pii_gen.py` passes unchanged against the moved constants
- [ ] `AGENTS.md` contains all five sections; `CLAUDE.md` resolves to it
- [ ] `README.md` "Contents" lists `warda/`, `data/`, `docs/` and links `AGENTS.md`

## Automated tests

- `warda/tests/test_schema.py`: `ACTIONS` order equals `pii_gen.ACTION_TEXT["en"]` positions; every
  `DEST_CLASS` value is in `DEST_CLASSES`; every `pii_gen.CHANNELS` key is in `CHANNELS`; `Decision` keys exact.
- `warda/tests/test_slow_marker.py`: a test marked `slow` is skipped without `WARDA_SLOW` (assert via
  `pytest.mark` introspection in a `pytester` run: `pytester.runpytest()` reports `skipped=1`).

## Documentation

- `AGENTS.md` (new) as specified; `README.md` "Contents" and "Quick start" mention `AGENTS.md` and `WARDA_SLOW`.
- `pretrain/README.md` "Harness decider" section: one sentence that shared literals now live in `warda/schema.py`.

## Manual test (human, before the PR)

1. Fresh clone, `uv sync --locked`, `uv run pytest -q` → all green, output lists `warda/tests` files.
2. `cat CLAUDE.md` prints `AGENTS.md`'s content (symlink works on macOS and Linux).
3. Open Claude Code in the repo and ask "how do I run the slow tests?" → it answers `WARDA_SLOW=1 uv run pytest -q`
   from `AGENTS.md` without you pasting anything.
4. `uv run python -m pretrain.harness.pii_gen --help` still prints the generate/build usage.
