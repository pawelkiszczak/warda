+++
id = "P1-11"
title = "Baselines on synthetic and handwritten sets: Presidio, ggshield, tier-1 regex"
labels = ["phase:1", "team:benchmarks", "type:experiment", "gate:2"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-06", "P1-01", "P1-07", "P1-10"]
estimate_hours = 8
hardware = "laptop"
github_issue = 21
+++

## Context

Gate 2 requires beating simple solutions; gate 3 compares to existing tools. `warda/bench` (P0-06) scores any
`Decider`; P1-07 says how each tool runs locally. This issue adds adapters for Presidio and ggshield and publishes
the first baseline table.

## Scope

- `warda/bench/deciders/presidio.py`, `warda/bench/deciders/ggshield.py`; a `docs/bench/BASELINES.md` report on
  `dev.jsonl`, `dev_ood.jsonl` and `data/handwritten/v0.jsonl`.
- Out of scope: Bielik-Guard / Prompt Guard (P3-05, they need GPU or HF downloads).

## Deliverables

- Presidio adapter: optional dependency group `bench-presidio = ["presidio-analyzer", "presidio-anonymizer",
  "spacy"]` in `pyproject.toml` (`uv sync --group bench-presidio`), plus a documented `python -m spacy download
  pl_core_news_md` / `en_core_web_lg`; the decider maps entity hits to `direct_pii` (PERSON, EMAIL, PHONE, IBAN,
  CREDIT_CARD, PL_PESEL via a custom recognizer using `warda.guard.checksums`) and otherwise `None`; action via
  the supplied shared `Policy` table like `tier1`, including conservative handling of exceptions; `confidence` = max
  Presidio score.
- ggshield adapter: shells out to `ggshield secret scan path` on a temp file (free account API key via
  `GITGUARDIAN_API_KEY` env; skipped with a clear message when absent); any secret → `credential` → `block`.
- Registry names `presidio`, `ggshield`; both lazy-import (no MLX, optional deps only when selected).
- `docs/bench/BASELINES.md`: table per set with `always_allow`, `always_block`, `tier1`, `presidio`, `ggshield`,
  `policy_oracle`; a paragraph on what each misses (by category slice), and the gate-2 bar: "a model must beat
  `tier1` and `always_allow` on accuracy on final `test` and `test_ood` (scored after candidate freeze in P3-01)".

## Definition of done

- [ ] Table filled for the three sets; `tier1` ≥ `presidio` on `credential` recall; `presidio` ≥ `tier1` on
      `direct_pii` recall for names (expected; if not, note why)
- [ ] `warda.bench.run --decider presidio` without the group installed prints an actionable message and exits 2
- [ ] Both adapters run with `--limit 100` in < 2 min on a laptop

## Automated tests

- Both adapters accept realistic policies without synthetic title lookup; unsupported cases and external API
  use are explicit in reports. ggshield receives fictional benchmark data only, never tester payloads.

- `warda/bench/tests/test_presidio_decider.py` (`pytest.importorskip("presidio_analyzer")`): PESEL recognizer
  fires on a valid PESEL and not on an invalid one; mapping to category.
- `warda/bench/tests/test_ggshield_decider.py`: with `GITGUARDIAN_API_KEY` unset the decider raises
  `SkipDecider` and the runner records `skipped` in `report.json` instead of failing.

## Documentation

- `docs/bench/BASELINES.md`; `docs/bench/PROTOCOL.md` lists the two deciders and their setup.

## Manual test (human, before the PR)

1. Install the group, download spaCy models, run the three sets with `--limit 300` → `report.md` rows for all
   deciders; paste the handwritten-set table into the PR.
2. Inspect 5 `presidio` false negatives on `quasi_identifying` items → confirm they contain no explicit
   identifier (expected behaviour of a pattern tool; this is the gap the model must fill).
