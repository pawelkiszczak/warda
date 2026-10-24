# Apple Silicon acceleration

## Policy and implementation status

Use the Apple Silicon GPU wherever supported execution improves measured end-to-end throughput or latency without
changing correctness. Maximise useful work on the Mac, not GPU utilisation as an isolated metric: CPU SIMD,
columnar scans, GPU kernels and overlapped loading are complementary. Do not move a stage to the GPU merely to
claim acceleration, or disable a faster GPU path simply because a CPU implementation already exists.

This is an implementation requirement for the task catalogue, not a claim that accelerated preprocessing has
already shipped. The current trainer uses MLX on Apple Silicon. Current corpus processing uses CPU/native-library
work and multiprocessing; Polars, ArrowMetal and gpudb are not production dependencies. P1-12 must implement and
validate the preprocessing benchmark and optional accelerated path before P1-04's extended corpus rebuild.

| Workload | Required baseline and acceleration investigation | Owner task |
| --- | --- | --- |
| Read/decompress/parse | Bounded Arrow/Parquet scans, projection and metadata pushdown before Python rows; profile JSON/zstd separately | P1-12, P1-04 |
| Text cleanup/filter/dedup | Python reference, native CPU Polars/Arrow, explicit Metal string kernels and hybrid placement | P1-12 |
| MinHash/tokenization | Bounded batch updates, compact interprocess results, tokenizer batching/thread budgets; optional Metal only with exact parity | P1-12 |
| Synthetic generation/verification | Apple GPU model-server path, measured concurrency/batching and accepted cases per second; explicit CPU profile | P1-02 |
| Pretraining and SFT | MLX GPU, completed-step timing, batch/compilation/precision experiments and overlapped bounded loading | P1-05, P2-01, P3-01 |
| Model serving | Warm MLX GPU inference, cold load and p50/p95 at actual request sizes; compare explicit CPU path | P3-03, P4-06 |

The task files are specifications: commands, flags and modules named there are not available until implemented.
Keep heavy optional imports lazy and isolate experimental dependencies from the locked runtime until adoption.

## Backend placement and compatibility

- **MLX:** the Apple GPU numerical/model path. Materialise lazy results before stopping timers; supported
  operations and dtypes must be checked on the installed version. GPU `float64` is not supported by current MLX.
- **Polars and PyArrow:** CPU baselines in this plan. Polars' official `engine="gpu"` uses NVIDIA RAPIDS, not Metal.
- **ArrowMetal:** an optional, third-party Metal candidate, not an upstream Polars backend. Its direct string APIs
  and Polars translator have different coverage. Require actual route evidence; automatic fallback is CPU, not
  a GPU measurement. Pin and test the engine/Polars pair; ArrowMetal 0.5.0 is alpha.
- **gpudb:** an optional third-party DuckDB community extension for expensive SQL stages, not the default text
  cleanup choice. Its SQL wrapper, explicit functions, data residency and NULL/overflow semantics differ. Pilot
  only a profiled SQL bottleneck with exact reference checks and backend reporting.
- **MinHash:** `datasketch` batch updates are a CPU optimisation here. Its optional CuPy/CUDA mode is not a Metal
  switch. Never change shingle bytes, permutation/hash scheme or document-order LSH decisions for a speed claim.
- **Model endpoints:** an OpenAI-compatible HTTP API does not identify the execution device. Record the local
  server/runtime, model, quantisation and offload/backend configuration; label placement unknown if unverified.
- **Unified memory:** CPU and GPU share capacity and bandwidth. Mapping, conversion, allocation, synchronisation
  and host output still cost time. Leave headroom for model weights, activations, OS and concurrent jobs.

NVIDIA generation endpoints may be used if separately configured. The current MLX trainer cannot train on CUDA;
NVIDIA/cloud training requires a separately estimated port and parity checks. Rent a supported Apple Silicon Mac
for MLX when local capacity is insufficient. Core ML/Neural Engine and GGUF conversion are not implicit fallbacks
for this custom MoE; they need separate compatibility work and approval.

## Benchmark and adoption contract

1. Profile the existing read-to-output pipeline first: decompression, parse, cleanup, features, exact/near dedup,
   tokenizer, interprocess communication and storage. Report documents/s, input MB/s and output tokens/s where
   meaningful; separate model tokens/s from corpus tokenisation throughput.
2. Use seeded, fictional Polish/English fixtures at small and large sizes, including Unicode, malformed/empty
   values, duplicates and skew. Keep a CPU reference and real-data runs local; never commit private samples.
3. Compare native multithreaded CPU with optional Metal and hybrid paths. Time completed outputs and include
   read/convert/map/compute/write costs in the end-to-end result. Also expose resident-kernel measurements, but
   never call them whole-pipeline speedups. Separate Python-list materialisation from native-array output.
4. Record hardware/OS, versions, backend and fallback reasons, dtype, thread/process counts, batch size,
   memory/swap observations, power/background-load conditions, first-call costs and at least five warm samples.
   Randomise implementation order and preserve raw timings plus median/spread plots. Do not claim hardware-counter
   verification when evidence consists of runtime routing and source-path inspection alone.
5. Validate exact kept IDs/order, text, metadata, split assignment, shingle signatures and tokenizer IDs/framing.
   Compare float model outputs with a declared tolerance; preserve calibration and quality gates. Unsupported
   Unicode or operation semantics require an explicit CPU path, not a silent approximation.
6. Bound prefetching and native/worker thread pools; measure useful overlap instead of oversubscribing CPU/GPU
   bandwidth. Concurrent preprocessing must not starve model training or create swap. Ordered dedup and seeded
   sampling must remain deterministic even when data loading is asynchronous.
7. Adopt every supported stage that gives a repeatable end-to-end benefit at its intended batch size without
   quality, latency or memory regression. Leave slower/unsupported stages on CPU and document why. An accelerated
   mode must not be accepted as GPU-backed if every requested stage silently falls back.
8. Keep a reproducible CPU smoke on supported laptops, plus an optional Apple GPU parity/performance smoke.
   Missing accelerators are reported as unavailable, not as a successful GPU run. No universal speedup threshold
   is inferred from the exploratory results below; choose per-workload acceptance criteria before selection.

P1-12 must produce runnable scripts, raw JSON/CSV and plots under `pretrain/work/bench/`, and update this document
with source-committed reproduction commands, selected stage placement and an adoption/no-go record. Production
flags/configuration are part of that task, not introduced by this documentation update.

## Exploratory local observations: 20 October 2026

These are measured synthetic microbenchmarks on an M4 Max, 128 GiB unified memory, macOS 27.0.1, native Python
3.12.13, Polars 2.0.0, PyArrow 25.0.1 and ArrowMetal 0.5.0. They are not measurements of Warda's full corpus
pipeline. Local scripts/results are not yet integrated into the repository; P1-12 must make them reproducible
here before treating them as an acceptance baseline. Background load and thermal state were not controlled.

At five million synthetic Polish/English documents, median of five warm runs, native Arrow output and pre-mapped
GPU input, compared with the fastest measured CPU implementation (Polars streaming in these cases):

| Operation | CPU ms | Explicit Metal GPU ms | CPU/GPU ratio |
| --- | ---: | ---: | ---: |
| Lowercase | 83.41 | 24.04 | 3.47x |
| Literal substring filter | 25.72 | 6.65 | 3.87x |
| Trim, lowercase, character-length filter, ordered exact dedup | 158.48 | 45.01 | 3.52x |

The import-inclusive GPU variants measured 17.21, 8.92 and 35.85 ms respectively. Their sometimes lower timings
reflect run variability, not negative import cost; preserve both modes and their spreads. At 100,000 documents,
the CPU won all three operations. Exact ordered outputs matched for the supported fixture characters; this is
not proof of arbitrary-Unicode equivalence. GPU placement was checked via device/API and source paths, not a
hardware-counter trace.

The original regex-normalisation, word-count filtering and ordered-dedup pipeline at one million documents took
84.20 ms with Polars CPU, 525.73 ms through ArrowMetal's automatic engine (the report said **nothing ran on
Metal**) and 631.31 ms for an explicit CPU-regex/GPU hybrid. The simpler GPU pipeline above omits internal
whitespace collapsing and word-count filtering; it cannot silently replace the original semantics. This is why
P1-12 must preserve the complete contract and select stage placement from end-to-end measurements.

A separate CPU-only MinHash microbenchmark over 32 documents with 1,024 pre-encoded shingles each took 125.07 ms
with scalar updates and 14.06 ms with batches of 1,024; signatures matched exactly. It excludes shingle
construction and LSH decisions. Neither this ratio nor the GPU ratios may be multiplied into a predicted corpus
speedup.

## References

- [MLX data types](https://ml-explore.github.io/mlx/build/html/python/data_types.html).
- [Polars official GPU support](https://docs.pola.rs/user-guide/gpu-support/).
- [ArrowMetal 0.5.0 Polars integration](https://github.com/singhpratech/ArrowMetal/blob/v0.5.0/docs/POLARS.md).
- [ArrowMetal package metadata](https://pypi.org/project/arrowmetal/0.5.0/).
- [DuckDB gpudb community extension](https://duckdb.org/community_extensions/extensions/gpudb.html).
- [gpudb surface-specific limitations](https://github.com/singhpratech/duckdbgpumetaldbram/blob/main/KNOWN_ISSUES.md).
- [datasketch API and CUDA-specific GPU mode](https://ekzhu.com/datasketch/documentation.html).
