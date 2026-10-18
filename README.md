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

```bash
python3.12 -m venv pretrain/.venv && pretrain/.venv/bin/pip install -r pretrain/requirements.txt
mkdir -p pretrain/work/quality/models && curl -L -o pretrain/work/quality/models/lid.176.bin \
  https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin   # language ID used by quality/ (126 MB)
pretrain/.venv/bin/python -m pytest pretrain -q
pretrain/.venv/bin/python -m pretrain.harness.pii_gen --help
```

Generated data, model weights and run artefacts go to `pretrain/work/` (gitignored). Never commit real personal data,
work data or secrets: this repository is public.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
