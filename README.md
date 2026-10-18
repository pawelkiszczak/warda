# warda

A small, local decision model that guards what coding agents send out. Before an agent commits, comments, searches or
calls an external API, Warda reads the company's data policy, the destination and the content, and decides:
**allow / redact / ask the user / block**, with a calibrated confidence. It is built from scratch; the decision is
typed — a choice from a closed set of options — rather than free-form text generation.

Status: research and data stage. No trained Warda model yet.

## Contents

- `pretrain/HARNESS_DECIDER_PLAN.md`: team plan (Polish): goals, gates, teams and sign-up table, schedule, tools.
- `FINDINGS.md`: results and decisions so far, with links to the detailed documents.
- `pretrain/harness/`: synthetic PII / disclosure dataset generator (`pii_gen.py`) and its tests.
- `pretrain/`: scratch-model experiments: data pipeline (`data/`), MoE model and pretraining (`model.py`, `train.py`),
  decision fine-tuning (`sft.py`, `sft/`), distillation (`distill/`), text-quality labelling tool (`quality/`).
  Details and results: `pretrain/README.md`.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`). Dependencies are declared in `pyproject.toml` and
locked in `uv.lock`; uv fetches Python 3.12 itself if it is missing.

```bash
uv sync --locked              # creates .venv with the locked runtime + dev dependencies
mkdir -p pretrain/work/quality/models && curl -L -o pretrain/work/quality/models/lid.176.bin \
  https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin   # language ID used by quality/ (126 MB)
uv run pytest -q
uv run python -m pretrain.harness.pii_gen --help
```

Run every script through `uv run` (it uses `.venv` and keeps it in sync with the lock). To change dependencies, edit
`pyproject.toml` or use `uv add` / `uv remove`, and commit the updated `uv.lock`.

Generated data, model weights and run artefacts go to `pretrain/work/` (gitignored). Never commit real personal data,
work data or secrets: this repository is public.

## Development checks

After the quick start (`pre-commit` is in the dev dependencies), install the CodeQL CLI and the Git hooks:

```bash
brew install --cask codeql
uv run pre-commit install
```

Formatting, lint, typing, secret, spelling, lockfile and documentation checks run on every commit; pytest and CodeQL
run before every push. Hook tools (ShellCheck, gitleaks, Biome, ...) are installed by pre-commit itself; the pytest
hook runs through `uv run`, so no virtual environment has to be activated. The push hooks call `uv` and `codeql`
from your `PATH`: GUI Git clients that don't load your shell profile may not find `/opt/homebrew/bin`, so push from a
terminal or add that directory to the client's environment.

```bash
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
```

To skip only the CodeQL check in an emergency, use `SKIP=codeql git push`. To upload retained SARIF results manually,
run `CODEQL_SARIF_DIR=/tmp/codeql-sarif scripts/codeql-scan.sh`, then for each result file:

```bash
codeql github upload-results --sarif=/tmp/codeql-sarif/python.sarif --repository=OWNER/REPO \
  --ref=refs/heads/BRANCH --commit=COMMIT_SHA
```

CodeQL runs the standard code-scanning suites for Python, JavaScript and GitHub Actions on the staged tree, and fails on
any result. Those suites treat only network input as untrusted. CodeQL has no model for plain Starlette route
handlers, so `codeql/python-models/` marks their request data (`query_params`, `path_params`, `headers`, `cookies`,
`url`, `json()`, `body()`, `form()`) as remote input, which brings the labelling app into scope.

Rule deviations: Biome keeps its recommended rules with no exceptions. Markdownlint disables MD060 (compact table
pipes are used throughout) and exempts tables and fenced code from the 120-character MD013 limit. Ruff and codespell
exceptions are listed with reasons in `pyproject.toml`.

`.pre-commit-config.yaml` pins every external hook revision. `.gitleaks.toml` and `detect-private-key` exclude only
the synthetic credential generator at `pretrain/harness/pii_gen.py`.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
