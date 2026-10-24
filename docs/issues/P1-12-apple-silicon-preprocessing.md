+++
id = "P1-12"
title = "Apple Silicon preprocessing: CPU/Metal benchmarks and measured stage acceleration"
labels = ["phase:1", "team:data-general", "type:feature"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01", "P1-06"]
estimate_hours = 12
hardware = "strong"
github_issue = 52
+++

## Context

The current corpus pipeline cleans, filters, deduplicates and tokenises on CPU/native libraries with a process
pool. Apple GPU acceleration exists for selected string operations, but automatic engines may fall back and an
explicit CPU/GPU hybrid may lose to native CPU. `docs/performance/APPLE_SILICON.md` records exploratory local
results and the correctness/measurement contract. The goal is to use as much useful Apple Silicon acceleration
as possible without changing the corpus or slowing the complete pipeline.

## Scope

- Profile `pretrain/data/build_tokens.py`; build reproducible text-processing CPU/Metal comparisons; implement
  optional, measured stage placement plus CPU batching/columnar improvements. Feed the result into P1-04.
- Measure parsing/decompression, regex/Unicode cleanup, metadata filtering, exact/near dedup, features,
  tokenisation, interprocess communication and output writes, not only dense-array kernels.
- Out of scope: CUDA trainer port, arbitrary-Unicode approximations, changing quality/licence criteria, full
  corpus rebuild (P1-04), model training (P1-05/P2-01), forcing every stage onto GPU.

## Deliverables

- A repository-owned benchmark entry point with seeded fictional Polish/English fixtures and small/large runs
  (include at least 100k and 1M documents where memory permits); raw JSON/CSV plus timing and speedup plots in
  `pretrain/work/bench/`. Separate native-output and Python-materialised-output tests, resident kernels and
  read-to-output pipelines. Record at least five randomised-order warm samples, first-call time and spread.
- CPU references and candidate paths: Python, bounded Arrow/Parquet projection/filter pushdown, native CPU
  Polars/Arrow, explicit ArrowMetal Metal kernels and hybrid placement. Evaluate gpudb only for a measured SQL
  bottleneck. Keep heavy experimental dependencies optional, lazy and version-pinned; no requirement for CUDA.
- A backend capability/route report per stage: requested backend, actual CPU/Metal placement, unsupported
  operation/Unicode/dtype, fallback reason and version. Direct Metal APIs and automatic Polars translation are
  distinct capabilities. GPU-required mode fails clearly when a requested GPU stage cannot execute; automatic
  mode may use an explicitly reported CPU path. A CPU fallback is never counted as GPU evidence.
- Bounded `MinHash.update_batch` with identical signatures, compact tokenizer-worker results and batching where
  profiling supports them; test thread/process budgets and deterministic ordered prefetch. Treat datasketch's
  CuPy/CUDA option as unavailable on Metal, not an acceleration flag for Macs.
- Preserve NFC/regex semantics, null/malformed handling, cleaning/stat counters, document IDs/order, metadata,
  exact/near-duplicate decisions, seeded split assignment and APT4 token IDs with one BOS/EOS and
  `add_special_tokens=False`. Keep stateful LSH decisions ordered; do not replace semantic steps with a simpler
  pipeline just because its GPU benchmark wins.
- Adopt each supported stage with repeatable end-to-end benefit at intended batch sizes; keep CPU for stages
  that are faster or unsupported. Record measured crossover/batch rules, bounded memory/prefetch settings,
  useful overlap with training and the remaining bottleneck. CPU execution must remain explicitly selectable.
- Update `docs/performance/APPLE_SILICON.md` with runnable `uv run` commands, package versions, per-stage
  placement, documents/s, MB/s, tokenisation throughput, memory/swap observations and adoption/no-go decisions.
  Reproduce the exploratory observations before citing them as repository benchmarks; no private corpus data in git.

## Definition of done

- [ ] A laptop CPU smoke and optional Apple GPU smoke run through the documented entry point; missing GPU support
      is reported unavailable, not a successful accelerated run
- [ ] Every adopted GPU stage has actual Metal-route evidence and a completed-output parity test; automatic CPU
      fallbacks and unsupported stages are visible in the report
- [ ] Frozen-sample read-to-output comparison preserves outputs/order and reports both wins and regressions;
      performance criteria were fixed before candidate selection, with no swap or unbounded-memory requirement
- [ ] The selected configuration uses every evaluated, supported CPU/GPU stage that improves end-to-end time;
      rejected placements have measurements or explicit compatibility reasons
- [ ] P1-04 can reuse the selected path without changing dataset semantics; scripts, raw results, plots and
      reproduction commands exist rather than only a written recommendation

## Automated tests

- New benchmark/processing tests cover deterministic fixtures, malformed/empty/duplicate records, Polish casing,
  whitespace, preserved IDs/order/stats, source metadata, split selection, shingle signatures and token framing.
- CPU-only imports never require ArrowMetal/MLX; fake capability reports cover auto fallback and GPU-required
  errors. Optional Apple tests check actual kernel completion and parity, not only a GPU device name.
- Raw-result schema rejects missing actual-backend fields and mismatched output checks; plots calculate speedup
  against the fastest equivalent measured CPU baseline, not an unrelated single-threaded operation.

## Documentation

- `docs/performance/APPLE_SILICON.md`; `pretrain/README.md` preprocessing commands and measured placement;
  `AGENTS.md` commands/optional dependency rules; P1-04 corpus report includes preprocessing provenance.

## Manual test (human, before the PR)

1. Run the CPU smoke on a supported laptop and the large comparison on an Apple Silicon Mac on AC power; inspect
   raw samples, min/max plots, completed outputs, memory/swap and actual backend reports.
2. Run unsupported regex/Unicode cases and verify explicit CPU fallback or a GPU-required error; demonstrate at
   least one supported Metal string kernel without pretending the entire pipeline ran on GPU.
3. Repeat the frozen-sample end-to-end run, including ingestion and writes. Confirm that all retained IDs,
   token-bin hashes and corpus counters match the reference; document any nondeterministic timing spread.
