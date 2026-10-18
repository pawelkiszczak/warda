+++
id = "P1-04"
title = "General corpus extension: code sources, licence audit, dedup report"
labels = ["phase:1", "team:data-general", "type:data"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01", "P1-06"]
estimate_hours = 8
hardware = "strong"
github_issue = 14
+++

## Context

Plan §6 "general data": SpeakLeash, FineWeb-2, HPLT (PL), FineWeb-Edu (EN) and code under training-permitting
licences; fastText language ID; `datasketch` dedup. `pretrain/data/build_tokens.py` already downloads SpeakLeash
and HF shards, filters, classifies, dedups and tokenises into `pretrain/work/tokens/`. Code is not in the mix and
licences are not recorded per source.

## Scope

- Add a code source and an HPLT PL source to `build_tokens.py`; produce a licence table and a dedup/quality report.
- Out of scope: training (P1-05, P2-01).

## Deliverables

- `build_tokens.py`: new source entries for (1) a permissively licensed code dataset on Hugging Face (the Stack
  v2 "permissive" subset or `bigcode/the-stack-smol` for the small path — the licence filter must keep only
  `MIT|Apache-2.0|BSD-2/3|ISC|Unlicense|CC0`), limited to `py|ts|js|go|sql|md|yaml|json|sh` extensions; (2) HPLT
  v2 Polish cleaned shards. Each source gets a `license` string in `manifest.json`. `--sources` flag to pick a
  subset; `--limit-docs N` for a CPU smoke.
- `docs/data/CORPUS.md`: table `Source | Language | Docs | Tokens | Licence | Filter | Notes` for every source in
  the manifest; dedup statistics (near-duplicate rate per source from `datasketch` MinHash as already used in the
  pipeline), language-ID confusion (pl/en/other), share of documents removed per filter stage.
- `pretrain/work/tokens/` rebuilt with the extended mix; token counts in `manifest.json`.

## Definition of done

- [ ] `uv run python pretrain/data/build_tokens.py --sources code,hplt_pl --limit-docs 200` runs on a laptop
      (CPU) in < 10 min and writes a manifest with `license` per source
- [ ] `docs/data/CORPUS.md` lists every source with a licence that allows training and redistribution of the
      *model* (recorded reasoning per source)
- [ ] Code share of the final token mix is stated and ≤ 15 % (default; ADR-0005 can change it)

## Automated tests

- `pretrain/data/tests/test_build_tokens.py`: licence filter keeps/rejects the listed SPDX ids; extension filter;
  `--limit-docs` honoured on an in-memory fake shard (no network: monkeypatch the download function); manifest
  contains `license` for each source.

## Documentation

- `docs/data/CORPUS.md` (new); `pretrain/README.md` "Pretraining data" gains the new sources and the `--sources` /
  `--limit-docs` flags.

## Manual test (human, before the PR)

1. Run the DoD smoke; open 5 random decoded code documents from the output (use the existing decode path in
   `pretrain/distill/build_pool.py`) → all have a permissive licence recorded and no obvious secrets (grep `-----BEGIN`
   and `AKIA` over the smoke output: zero hits, else add to the filter).
2. Read `CORPUS.md` as the GDPR person would: each source has a reason it may be used.
