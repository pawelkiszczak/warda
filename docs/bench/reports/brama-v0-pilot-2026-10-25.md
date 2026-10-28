# Brama v0 pilot report (2026-10-25)

Brama v0 (examples split) on the open **System-1 decision models** that fit 16 GB as GGUF Q8_0 or FP8, with
**basal** (Remek Kinas) as the primary family, next to Fastino's open GLiNER2.5-Decide classifiers, two Bielik v3.0
instruct models as general-LLM reference rows, the V-04 floors and the tier-1 rule. **This is a pilot on 108
agent-drafted items with unreviewed gold**: it checks that the benchmark runs and separates deciders, and it is not
evidence for model selection or gate 3.

This report replaces the first version of the same date, which read "the newest Basal up to 8B" as Bielik and ran
only Bielik-PL-Minitron-7B and GLiNER2.5-Decide. Those rows are kept, rerun on the current dataset hash.

## Headline

- **Decision models clear the tier-1 rule by a wide margin; general LLMs and GLiNER do not.** 14 of 21 System-1
  models beat tier-1 on acceptable accuracy with a paired interval above zero (basal-omni-pico's touches zero);
  Bielik 7B and 11B do not, and every GLiNER2.5-Decide row is below the `always_allow` floor.
- **The top is basal-omni-1.1-max** (12 B, Q8_0): Catch@UIR5 100.0 % [98.0, 100.0], acceptable accuracy 89.8 %
  [84.3, 94.7], 71.4 % of contrast groups fully right, no hard-invariant violation. **Winnow-12B, basal-omni-1.0-max
  and Bespoke-Nimble-9B-v3 are not distinguishable from it at this n** (accuracy −1.9 to −2.8 pt, paired intervals
  include 0). basal-2.0-max, torchcast-decision-12b and basal-omni-1.0-mini are distinguishably below it on accuracy.
- **Up to 8 B**, as the original request asked: the largest basal in that range, **basal-omni-1.0-mini** (7.9 B),
  scores 78.2 % catch and 79.6 % accuracy; **h2o-lightning-4b** (4.7 B) has the best accuracy at that size (86.1 %),
  but stops fewer protected items at the 5 % budget (69.1 %). basal-2.0-4.5B, built on Bielik-4.5B, reaches 65.5 % /
  71.3 %.
- **The basal fine-tune is what moves its base.** basal-2.0-max is Bielik-11B-v3 trained for decisions: +25.0 pt
  accuracy [16.8, 32.7] and +29.1 pt catch [5.9, 75.0] over Bielik-PL-11B-v3.0-Instruct read the LLM way. The 11B
  Bielik is no better than the 7B one (54.6 % vs 57.4 %), and neither ever asks the user.
- **Not saturated.** The best model gets 71.4 % of contrast groups fully right; no decider solves more than 50 % of
  the T2 (quasi-identifier) groups or 66.7 % of the T5, T6 and T7 groups.

| decider | params | run as | Catch@UIR5 | acceptable acc | groups | hard | ECE |
|---|---|---|---|---|---|---|---|
| basal-omni-1.1-max | 12.0 B | Q8_0 (converted) | 100.0 | 89.8 | 71.4 | 0 | 0.066 |
| basal-omni-1.0-max | 12.0 B | Q8_0 | 98.2 | 88.0 | 68.6 | 0 | 0.079 |
| torchcast-decision-12b | 12.0 B | FP8 weights | 98.2 | 80.6 | 51.4 | 0 | 0.090 |
| Winnow-12B | 12 B | Q8_0 | 96.4 | 88.0 | 62.9 | 1 | 0.037 |
| basal-2.0-max | 11.2 B | Q8_0 | 92.7 | 79.6 | 48.6 | 0 | 0.067 |
| d3-flash | 8.4 B | bf16 | 92.7 | 83.3 | 54.3 | 0 | 0.123 |
| SPX-CD-Omni | 12 B | LLM.int8 | 90.9 | 62.0 | 22.9 | 0 | 0.184 |
| decider-12b | 12.0 B | Q8_0 (converted) | 90.9 | 75.0 | 42.9 | 0 | 0.134 |
| basal-omni-1.0-mini | 7.9 B | bf16 | 78.2 | 79.6 | 54.3 | 1 | 0.136 |
| d3-mini | 4.5 B | bf16 | 78.2 | 72.2 | 37.1 | 1 | 0.095 |
| Bespoke-Nimble-9B-v3 | 9 B | bf16 | 74.5 | 87.0 | 62.9 | 0 | 0.083 |
| pplx-decider-flash-v1.2 | 4.5 B | bf16 | 74.5 | 77.8 | 48.6 | 2 | 0.114 |
| h2o-lightning-4b | 4.7 B | bf16 | 69.1 | 86.1 | 60.0 | 0 | 0.065 |
| basal-2.0-4.5B | 4.8 B | bf16 | 65.5 | 71.3 | 40.0 | 0 | 0.131 |
| Jev-Omni | 12.0 B | LLM.int8 | 56.4 | 74.1 | 45.7 | 0 | 0.114 |
| d3-nano | 2.2 B | bf16 | 45.5 | 64.8 | 37.1 | 0 | 0.184 |
| hopper | 4 B | bf16 | 43.6 | 60.2 | 28.6 | 0 | 0.104 |
| basal-omni-pico | 0.75 B | bf16 | 30.9 | 70.4 | 40.0 | 0 | 0.130 |
| clef-flash | 9.4 B | bf16 | 25.5 | 65.7 | 28.6 | 4 | 0.142 |
| d3-lite | 0.85 B | bf16 | 23.6 | 32.4 | 0.0 | 1 | 0.213 |
| basal-2.0-mini | 1.6 B | bf16 | 16.4 | 40.7 | 5.7 | 1 | 0.219 |
| Bielik-PL-11B-v3.0-Instruct | 11.2 B | LLM.int8 | 63.6 | 54.6 | 14.3 | 2 | 0.352 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | 7.5 B | bf16 | 20.0 | 57.4 | 11.4 | 4 | 0.299 |
| GLiNER2.5-multi-Decide-nopolicy (best GLiNER row) | 0.29 B | fp32 | 7.3 | 34.3 | 0.0 | 6 | 0.104 |
| tier1 | — | rule | 0.0 | 61.1 | 17.1 | 6 | 0.398 |
| always_allow | — | floor | 0.0 | 49.1 | 0.0 | 11 | 0.509 |

Full list with sources, licences and revisions: [`../brama-v0-models.md`](../brama-v0-models.md).

## What was run

- **System-1 decision models** (21): every open-weight model that answers typed questions with a probability per
  option and fits 16 GB as GGUF Q8_0 or FP8, from Tacit, Werdykt, JevBench, the Decision Index and the Polish PIRB
  decision board. Families: basal (7), vLLM Semantic Router d3 (4), Perplexity pplx-decider, Cloudflare clef,
  decider-ai, Jev-Omni, Winnow, H2O lightning, torchcast, HopitAI hopper, Bespoke Nimble, SurdAI SPX. Larger models
  (GLiDE v1.2, basal-omni-1.0-ultra, d3, Quyet-1.0-Large, Span-02) and API-only models are listed as not admitted in
  the model list.
- **Fastino**: GLiNER2.5-multi-Decide, GLiNER2.5-Decide, GLiNER2.5-Decide-1B, each with and without the policy text.
  Fastino's decision model GLiDE v1.2 (26 B) does not fit 16 GB.
- **Reference LLMs**: Bielik-PL-Minitron-7B-v3.0-Instruct (bf16) and Bielik-PL-11B-v3.0-Instruct (LLM.int8), the
  base of basal-2.0-max, read by the letter-logit prompt.
- **Floors and rules**: `always_allow`, `always_redact`, `always_ask_user`, `always_block`, `tier1` (credential hit
  → `block`, other id hit → `redact`, none → `allow`).

Setup:

- Dataset: `data/brama/examples-v0.jsonl` + ids sidecar + both policies, `dataset_sha256` `98e4883a…`, decider-input
  hash `states_sha256` `cf566607…`; both are identical in every run's `.meta.json`.
- Hardware: WSL2 on Linux x86_64, one NVIDIA RTX 3090 24 GB (sm86: no FP8 tensor cores).
- **How System-1 models were asked:** one `choice` question over the four actions with the same state, question
  and option texts as the LLM prompt (`brama.QUESTION`, `brama.OPTION_TEXT`, in the item's language), through
  `POST /v1/systemone` (`run_brama --decider systemone`). Models that ship only a Python API are served on that
  endpoint by `warda.bench.systemone_shim`, which calls the API their card documents. Canonical and reversed option
  order are averaged (R-13); the model's own probabilities are renormalised over the four actions. No prompt or
  label tuning for any model.
- **Precision:** bf16 where the model fits the card; otherwise the author's GGUF Q8_0, a Q8_0 converted here with
  llama.cpp, LLM.int8 or FP8 weights (Marlin W8A16). The "run as" column says which; the model list says why.
  Servers: basal-serve 2.4.1, vLLM 0.30.0 (h2o, torchcast), llama.cpp via llama-cpp-python 0.3.36 (decider-12b and
  the basal Q8_0 ports), winnow-inference, hopper-serve 1.1.1; each model in its own environment as its card pins
  it (torch 2.8–2.14, transformers 5.10–5.20).
- LLM readout (Bielik): `pretrain/prompt.py` chat template with the `{"answer": "` prefill, softmax over the four
  option letters. GLiNER readout: one single-label task over the four actions (`run_brama.GLINER_LABELS`). Both as
  in the first version.
- Statistics: cluster bootstrap over the 43 contrast groups, 10,000 resamples; differences paired on the same items.
- Reproduce: `uv run python -m warda.bench.run_brama report` (point estimates exact; intervals within bootstrap
  noise). Per-item probabilities are in `docs/bench/results/brama-v0/*.jsonl`, all scores in `scores.json`; each
  `.meta.json` records revision, server command, hardware and run time.

## Results

Columns: Catch@UIR5 = share of non-allow items stopped at the threshold where ≤ 5 % of gold-allow items are
stopped (M-01; `redact` and `ask_user` count as stopped, R-17); acceptable acc = prediction in `acceptable`; groups
= share of multi-row contrast groups with every row acceptable (M-02); UIR / miss = unnecessary-intervention and
missed-disclosure rates at argmax; hard = M-08 violations; order flips = items whose argmax changes with option
order; ms = median latency per item (both orders). Rows: System-1 models by Catch@UIR5, then the reference LLMs,
GLiNER, tier-1 and the floors.

| decider | Catch@UIR5 [95% CI] | acceptable acc [95% CI] | macro-F1 | groups | UIR | miss | hard | ECE | Brier | order flips | ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| basal-omni-1.1-max | 100.0 [98.0, 100.0] | 89.8 [84.3, 94.7] | 86.3 | 71.4 | 13.2 | 0.0 | 0 | 0.066 | 0.162 | 4.6 | 1081 |
| basal-omni-1.0-max | 98.2 [68.0, 100.0] | 88.0 [81.0, 93.9] | 84.1 | 68.6 | 17.0 | 0.0 | 0 | 0.079 | 0.198 | 3.7 | 1075 |
| torchcast-decision-12b | 98.2 [55.6, 100.0] | 80.6 [72.2, 88.1] | 65.1 | 51.4 | 18.9 | 0.0 | 0 | 0.090 | 0.307 | 7.4 | 200 |
| Winnow-12B | 96.4 [88.0, 100.0] | 88.0 [82.7, 93.1] | 85.7 | 62.9 | 15.1 | 1.8 | 1 | 0.037 | 0.182 | 6.5 | 589 |
| basal-2.0-max | 92.7 [73.2, 98.2] | 79.6 [72.4, 86.7] | 73.7 | 48.6 | 20.8 | 3.6 | 0 | 0.067 | 0.283 | 11.1 | 982 |
| d3-flash | 92.7 [50.9, 100.0] | 83.3 [77.1, 89.4] | 76.0 | 54.3 | 18.9 | 0.0 | 0 | 0.123 | 0.269 | 7.4 | 916 |
| SPX-CD-Omni | 90.9 [70.9, 98.3] | 62.0 [53.0, 70.9] | 55.2 | 22.9 | 52.8 | 0.0 | 0 | 0.184 | 0.543 | 12.0 | 2053 |
| decider-12b | 90.9 [29.5, 100.0] | 75.0 [66.4, 83.3] | 61.0 | 42.9 | 24.5 | 0.0 | 0 | 0.134 | 0.409 | 13.9 | 8852 |
| basal-omni-1.0-mini | 78.2 [60.0, 98.3] | 79.6 [70.6, 87.6] | 74.4 | 54.3 | 26.4 | 1.8 | 1 | 0.136 | 0.336 | 3.7 | 508 |
| d3-mini | 78.2 [32.8, 93.1] | 72.2 [63.6, 80.2] | 59.5 | 37.1 | 35.8 | 1.8 | 1 | 0.095 | 0.434 | 2.8 | 563 |
| Bespoke-Nimble-9B-v3 | 74.5 [58.2, 100.0] | 87.0 [81.7, 92.5] | 87.4 | 62.9 | 22.6 | 0.0 | 0 | 0.083 | 0.217 | 5.6 | 1157 |
| pplx-decider-flash-v1.2 | 74.5 [50.8, 92.3] | 77.8 [68.6, 85.8] | 63.6 | 48.6 | 20.8 | 7.3 | 2 | 0.114 | 0.350 | 2.8 | 1622 |
| h2o-lightning-4b | 69.1 [35.8, 100.0] | 86.1 [80.0, 91.9] | 84.7 | 60.0 | 20.8 | 0.0 | 0 | 0.065 | 0.236 | 2.8 | 468 |
| basal-2.0-4.5B | 65.5 [52.4, 93.2] | 71.3 [62.3, 80.0] | 59.3 | 40.0 | 30.2 | 7.3 | 0 | 0.131 | 0.450 | 4.6 | 602 |
| Jev-Omni | 56.4 [43.9, 94.5] | 74.1 [64.9, 83.0] | 58.3 | 45.7 | 34.0 | 0.0 | 0 | 0.114 | 0.393 | 13.0 | 1568 |
| d3-nano | 45.5 [19.7, 77.4] | 64.8 [54.2, 75.5] | 45.0 | 37.1 | 20.8 | 12.7 | 0 | 0.184 | 0.581 | 6.5 | 615 |
| hopper | 43.6 [22.6, 80.9] | 60.2 [49.6, 70.4] | 46.9 | 28.6 | 24.5 | 5.5 | 0 | 0.104 | 0.523 | 20.4 | 551 |
| basal-omni-pico | 30.9 [13.6, 70.0] | 70.4 [60.5, 79.8] | 58.8 | 40.0 | 26.4 | 9.1 | 0 | 0.130 | 0.469 | 4.6 | 704 |
| clef-flash | 25.5 [6.0, 68.0] | 65.7 [55.7, 75.5] | 49.4 | 28.6 | 17.0 | 21.8 | 4 | 0.142 | 0.515 | 0.0 | 1429 |
| d3-lite | 23.6 [8.7, 37.1] | 32.4 [22.9, 41.9] | 25.5 | 0.0 | 69.8 | 10.9 | 1 | 0.213 | 0.769 | 18.5 | 160 |
| basal-2.0-mini | 16.4 [5.7, 43.9] | 40.7 [32.8, 48.7] | 28.8 | 5.7 | 66.0 | 16.4 | 1 | 0.219 | 0.750 | 19.4 | 209 |
| Bielik-PL-11B-v3.0-Instruct | 63.6 [17.5, 76.3] | 54.6 [45.2, 64.1] | 33.9 | 14.3 | 34.0 | 18.2 | 2 | 0.352 | 0.802 | 10.2 | 1854 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | 20.0 [7.4, 47.7] | 57.4 [48.8, 65.9] | 34.0 | 11.4 | 26.4 | 27.3 | 4 | 0.299 | 0.722 | 14.8 | 845 |
| GLiNER2.5-multi-Decide | 3.6 [0.0, 22.6] | 9.3 [4.0, 15.3] | 6.7 | 0.0 | 100.0 | 1.8 | 1 | 0.439 | 0.982 | 0.0 | 232 |
| GLiNER2.5-multi-Decide-nopolicy | 7.3 [0.0, 19.7] | 34.3 [26.4, 42.7] | 24.0 | 0.0 | 50.9 | 41.8 | 6 | 0.104 | 0.766 | 0.0 | 60 |
| GLiNER2.5-Decide | 5.5 [0.0, 22.0] | 29.6 [22.0, 37.5] | 16.5 | 0.0 | 50.9 | 50.9 | 6 | 0.103 | 0.795 | 0.0 | 667 |
| GLiNER2.5-Decide-nopolicy | 1.8 [0.0, 10.0] | 18.5 [10.9, 26.6] | 14.1 | 0.0 | 96.2 | 3.6 | 2 | 0.280 | 0.871 | 0.0 | 116 |
| GLiNER2.5-Decide-1B | 3.6 [0.0, 15.7] | 12.0 [5.8, 19.2] | 8.3 | 0.0 | 100.0 | 0.0 | 0 | 0.464 | 1.098 | 0.0 | 732 |
| GLiNER2.5-Decide-1B-nopolicy | 3.6 [0.0, 9.5] | 10.2 [4.3, 17.3] | 4.6 | 0.0 | 100.0 | 0.0 | 0 | 0.608 | 1.259 | 0.0 | 95 |
| tier1 | 0.0 [0.0, 39.0] | 61.1 [53.6, 69.0] | 39.5 | 17.1 | 15.1 | 47.3 | 6 | 0.398 | 0.796 | 0.0 | 0 |
| always_allow | 0.0 [0.0, 0.0] | 49.1 [43.7, 55.1] | 16.5 | 0.0 | 0.0 | 100.0 | 11 | 0.509 | 1.019 | 0.0 | 0 |
| always_redact | 0.0 [0.0, 0.0] | 22.2 [13.6, 31.0] | 7.5 | 0.0 | 100.0 | 0.0 | 0 | 0.824 | 1.648 | 0.0 | 0 |
| always_ask_user | 0.0 [0.0, 0.0] | 10.2 [4.3, 17.3] | 4.6 | 0.0 | 100.0 | 0.0 | 0 | 0.898 | 1.796 | 0.0 | 0 |
| always_block | 0.0 [0.0, 0.0] | 28.7 [20.0, 37.1] | 9.4 | 0.0 | 100.0 | 0.0 | 0 | 0.769 | 1.537 | 0.0 | 0 |

With 53 gold-allow items the 5 % budget allows at most two stopped allow items, so Catch@UIR5 turns on a couple of
items near the threshold and its intervals are wide (decider-12b [29.5, 100]); acceptable accuracy is the steadier
number at this n. Constant and one-hot deciders have no confidence to threshold, so their Catch@UIR5 is 0 by
construction; the tier-1 interval [0, 39] comes from resamples in which its 15 % UIR falls under 5 %.

Per track (acceptable accuracy / group consistency; T8 has only single-row groups, so no group score):

| decider | T1 acc / groups | T2 acc / groups | T3 acc / groups | T4 acc / groups | T5 acc / groups | T6 acc / groups | T7 acc / groups | T8 acc / groups | T9 acc / groups |
|---|---|---|---|---|---|---|---|---|---|
| basal-omni-1.1-max | 91.7 / 80.0 | 75.0 / 25.0 | 100.0 / 100.0 | 100.0 / 100.0 | 93.3 / 66.7 | 81.2 / 50.0 | 71.4 / 33.3 | 87.5 / n/a | 100.0 / 100.0 |
| basal-omni-1.0-max | 91.7 / 80.0 | 66.7 / 25.0 | 100.0 / 100.0 | 100.0 / 100.0 | 86.7 / 33.3 | 81.2 / 66.7 | 71.4 / 33.3 | 100.0 / n/a | 94.4 / 83.3 |
| torchcast-decision-12b | 83.3 / 60.0 | 83.3 / 50.0 | 90.0 / 75.0 | 100.0 / 100.0 | 60.0 / 33.3 | 75.0 / 33.3 | 71.4 / 33.3 | 100.0 / n/a | 77.8 / 33.3 |
| Winnow-12B | 83.3 / 60.0 | 75.0 / 25.0 | 90.0 / 75.0 | 100.0 / 100.0 | 86.7 / 33.3 | 87.5 / 66.7 | 85.7 / 66.7 | 100.0 / n/a | 88.9 / 66.7 |
| basal-2.0-max | 83.3 / 60.0 | 66.7 / 0.0 | 80.0 / 50.0 | 90.0 / 75.0 | 66.7 / 33.3 | 75.0 / 33.3 | 71.4 / 66.7 | 100.0 / n/a | 88.9 / 66.7 |
| d3-flash | 75.0 / 40.0 | 83.3 / 50.0 | 90.0 / 75.0 | 100.0 / 100.0 | 73.3 / 0.0 | 68.8 / 16.7 | 71.4 / 66.7 | 100.0 / n/a | 94.4 / 83.3 |
| SPX-CD-Omni | 83.3 / 60.0 | 33.3 / 0.0 | 60.0 / 0.0 | 80.0 / 50.0 | 53.3 / 0.0 | 50.0 / 0.0 | 57.1 / 33.3 | 75.0 / n/a | 72.2 / 33.3 |
| decider-12b | 83.3 / 60.0 | 66.7 / 25.0 | 70.0 / 50.0 | 90.0 / 75.0 | 66.7 / 33.3 | 68.8 / 16.7 | 57.1 / 33.3 | 100.0 / n/a | 77.8 / 50.0 |
| basal-omni-1.0-mini | 75.0 / 40.0 | 75.0 / 25.0 | 90.0 / 75.0 | 100.0 / 100.0 | 73.3 / 33.3 | 81.2 / 50.0 | 42.9 / 33.3 | 75.0 / n/a | 88.9 / 66.7 |
| d3-mini | 66.7 / 20.0 | 83.3 / 50.0 | 90.0 / 75.0 | 100.0 / 100.0 | 53.3 / 0.0 | 62.5 / 0.0 | 42.9 / 33.3 | 75.0 / n/a | 77.8 / 33.3 |
| Bespoke-Nimble-9B-v3 | 91.7 / 80.0 | 75.0 / 25.0 | 80.0 / 50.0 | 100.0 / 100.0 | 73.3 / 0.0 | 87.5 / 66.7 | 85.7 / 66.7 | 100.0 / n/a | 94.4 / 83.3 |
| pplx-decider-flash-v1.2 | 75.0 / 40.0 | 83.3 / 50.0 | 80.0 / 50.0 | 100.0 / 100.0 | 60.0 / 33.3 | 68.8 / 16.7 | 57.1 / 33.3 | 87.5 / n/a | 88.9 / 66.7 |
| h2o-lightning-4b | 91.7 / 80.0 | 83.3 / 50.0 | 80.0 / 50.0 | 90.0 / 75.0 | 80.0 / 33.3 | 68.8 / 16.7 | 85.7 / 66.7 | 100.0 / n/a | 100.0 / 100.0 |
| basal-2.0-4.5B | 83.3 / 60.0 | 58.3 / 0.0 | 90.0 / 75.0 | 80.0 / 50.0 | 53.3 / 0.0 | 50.0 / 16.7 | 57.1 / 33.3 | 87.5 / n/a | 88.9 / 66.7 |
| Jev-Omni | 75.0 / 40.0 | 50.0 / 0.0 | 90.0 / 75.0 | 100.0 / 100.0 | 60.0 / 33.3 | 56.2 / 16.7 | 71.4 / 33.3 | 100.0 / n/a | 83.3 / 66.7 |
| d3-nano | 66.7 / 40.0 | 75.0 / 25.0 | 80.0 / 75.0 | 90.0 / 75.0 | 40.0 / 0.0 | 37.5 / 16.7 | 28.6 / 33.3 | 100.0 / n/a | 77.8 / 33.3 |
| hopper | 83.3 / 60.0 | 50.0 / 0.0 | 40.0 / 25.0 | 70.0 / 25.0 | 46.7 / 0.0 | 50.0 / 16.7 | 28.6 / 33.3 | 75.0 / n/a | 83.3 / 50.0 |
| basal-omni-pico | 75.0 / 40.0 | 41.7 / 0.0 | 100.0 / 100.0 | 70.0 / 25.0 | 53.3 / 0.0 | 56.2 / 33.3 | 57.1 / 33.3 | 100.0 / n/a | 88.9 / 66.7 |
| clef-flash | 83.3 / 60.0 | 33.3 / 0.0 | 50.0 / 0.0 | 60.0 / 0.0 | 53.3 / 33.3 | 68.8 / 33.3 | 57.1 / 33.3 | 100.0 / n/a | 83.3 / 50.0 |
| d3-lite | 25.0 / 0.0 | 25.0 / 0.0 | 20.0 / 0.0 | 50.0 / 0.0 | 33.3 / 0.0 | 37.5 / 0.0 | 14.3 / 0.0 | 25.0 / n/a | 44.4 / 0.0 |
| basal-2.0-mini | 25.0 / 0.0 | 50.0 / 0.0 | 70.0 / 50.0 | 60.0 / 0.0 | 26.7 / 0.0 | 25.0 / 0.0 | 14.3 / 0.0 | 37.5 / n/a | 55.6 / 0.0 |
| Bielik-PL-11B-v3.0-Instruct | 75.0 / 40.0 | 25.0 / 0.0 | 50.0 / 0.0 | 60.0 / 0.0 | 26.7 / 0.0 | 43.8 / 0.0 | 57.1 / 0.0 | 100.0 / n/a | 72.2 / 50.0 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | 75.0 / 40.0 | 50.0 / 0.0 | 50.0 / 0.0 | 50.0 / 0.0 | 26.7 / 0.0 | 56.2 / 0.0 | 42.9 / 0.0 | 100.0 / n/a | 72.2 / 33.3 |
| GLiNER2.5-multi-Decide | 8.3 / 0.0 | 16.7 / 0.0 | 20.0 / 0.0 | 20.0 / 0.0 | 0.0 / 0.0 | 12.5 / 0.0 | 14.3 / 0.0 | 0.0 / n/a | 0.0 / 0.0 |
| GLiNER2.5-multi-Decide-nopolicy | 41.7 / 0.0 | 33.3 / 0.0 | 30.0 / 0.0 | 40.0 / 0.0 | 20.0 / 0.0 | 37.5 / 0.0 | 42.9 / 0.0 | 62.5 / n/a | 22.2 / 0.0 |
| GLiNER2.5-Decide | 25.0 / 0.0 | 25.0 / 0.0 | 30.0 / 0.0 | 10.0 / 0.0 | 40.0 / 0.0 | 18.8 / 0.0 | 42.9 / 0.0 | 37.5 / n/a | 38.9 / 0.0 |
| GLiNER2.5-Decide-nopolicy | 25.0 / 0.0 | 8.3 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 33.3 / 0.0 | 25.0 / 0.0 | 28.6 / 0.0 | 25.0 / n/a | 16.7 / 0.0 |
| GLiNER2.5-Decide-1B | 16.7 / 0.0 | 8.3 / 0.0 | 0.0 / 0.0 | 10.0 / 0.0 | 20.0 / 0.0 | 25.0 / 0.0 | 14.3 / 0.0 | 0.0 / n/a | 5.6 / 0.0 |
| GLiNER2.5-Decide-1B-nopolicy | 8.3 / 0.0 | 8.3 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 20.0 / 0.0 | 25.0 / 0.0 | 14.3 / 0.0 | 0.0 / n/a | 5.6 / 0.0 |
| tier1 | 83.3 / 60.0 | 50.0 / 0.0 | 50.0 / 0.0 | 50.0 / 0.0 | 33.3 / 0.0 | 50.0 / 0.0 | 71.4 / 33.3 | 100.0 / n/a | 77.8 / 33.3 |
| always_allow | 50.0 / 0.0 | 50.0 / 0.0 | 50.0 / 0.0 | 50.0 / 0.0 | 40.0 / 0.0 | 43.8 / 0.0 | 42.9 / 0.0 | 100.0 / n/a | 38.9 / 0.0 |
| always_redact | 41.7 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 20.0 / 0.0 | 18.8 / 0.0 | 42.9 / 0.0 | 0.0 / n/a | 55.6 / 0.0 |
| always_ask_user | 8.3 / 0.0 | 8.3 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 20.0 / 0.0 | 25.0 / 0.0 | 14.3 / 0.0 | 0.0 / n/a | 5.6 / 0.0 |
| always_block | 16.7 / 0.0 | 41.7 / 0.0 | 50.0 / 0.0 | 50.0 / 0.0 | 26.7 / 0.0 | 18.8 / 0.0 | 14.3 / 0.0 | 0.0 / n/a | 33.3 / 0.0 |

Pair scores (both members of a twin pair acceptable) and the predicted action mix (gold: allow 49.1 / redact 22.2 /
ask_user 10.2 / block 23.1, counting the gold action):

| decider | safe_pair | flow_sensitivity | fact_sensitivity | policy_sensitivity | surface_pair | adv_pair | predicted allow / redact / ask_user / block |
|---|---|---|---|---|---|---|---|
| basal-omni-1.1-max | 74.1 | 91.3 | 100.0 | 50.0 | 100.0 | 100.0 | 42.6 / 25.0 / 7.4 / 25.0 |
| basal-omni-1.0-max | 70.4 | 69.6 | 100.0 | 100.0 | 100.0 | 100.0 | 40.7 / 23.1 / 9.3 / 26.9 |
| torchcast-decision-12b | 66.7 | 47.8 | 85.7 | 0.0 | 100.0 | 66.7 | 39.8 / 25.9 / 0.9 / 33.3 |
| Winnow-12B | 77.8 | 73.9 | 85.7 | 100.0 | 100.0 | 66.7 | 42.6 / 19.4 / 9.3 / 28.7 |
| basal-2.0-max | 63.0 | 34.8 | 71.4 | 50.0 | 100.0 | 66.7 | 40.7 / 19.4 / 5.6 / 34.3 |
| d3-flash | 66.7 | 52.2 | 42.9 | 100.0 | 100.0 | 100.0 | 39.8 / 22.2 / 4.6 / 33.3 |
| SPX-CD-Omni | 44.4 | 21.7 | 42.9 | 0.0 | 100.0 | 66.7 | 23.1 / 39.8 / 3.7 / 33.3 |
| decider-12b | 48.1 | 56.5 | 57.1 | 0.0 | 100.0 | 66.7 | 37.0 / 36.1 / 1.9 / 25.0 |
| basal-omni-1.0-mini | 59.3 | 65.2 | 85.7 | 50.0 | 100.0 | 100.0 | 37.0 / 25.0 / 7.4 / 30.6 |
| d3-mini | 48.1 | 56.5 | 42.9 | 0.0 | 100.0 | 66.7 | 32.4 / 33.3 / 0.9 / 33.3 |
| Bespoke-Nimble-9B-v3 | 77.8 | 43.5 | 71.4 | 100.0 | 100.0 | 100.0 | 38.0 / 20.4 / 11.1 / 30.6 |
| pplx-decider-flash-v1.2 | 51.9 | 69.6 | 71.4 | 0.0 | 100.0 | 100.0 | 42.6 / 32.4 / 0.9 / 24.1 |
| h2o-lightning-4b | 70.4 | 69.6 | 42.9 | 100.0 | 100.0 | 100.0 | 38.9 / 23.1 / 8.3 / 29.6 |
| basal-2.0-4.5B | 63.0 | 26.1 | 28.6 | 0.0 | 100.0 | 100.0 | 38.0 / 34.3 / 0.9 / 26.9 |
| Jev-Omni | 63.0 | 43.5 | 57.1 | 0.0 | 100.0 | 66.7 | 32.4 / 31.5 / 2.8 / 33.3 |
| d3-nano | 55.6 | 30.4 | 14.3 | 0.0 | 100.0 | 66.7 | 45.4 / 16.7 / 1.9 / 36.1 |
| hopper | 44.4 | 26.1 | 28.6 | 0.0 | 100.0 | 66.7 | 39.8 / 46.3 / 0.9 / 13.0 |
| basal-omni-pico | 59.3 | 30.4 | 42.9 | 0.0 | 100.0 | 66.7 | 40.7 / 33.3 / 2.8 / 23.1 |
| clef-flash | 40.7 | 30.4 | 57.1 | 0.0 | 100.0 | 33.3 | 51.9 / 38.0 / 2.8 / 7.4 |
| d3-lite | 0.0 | 26.1 | 0.0 | 0.0 | 66.7 | 33.3 | 20.4 / 33.3 / 13.0 / 33.3 |
| basal-2.0-mini | 14.8 | 4.3 | 14.3 | 0.0 | 66.7 | 33.3 | 25.0 / 12.0 / 3.7 / 59.3 |
| Bielik-PL-11B-v3.0-Instruct | 37.0 | 4.3 | 0.0 | 0.0 | 66.7 | 33.3 | 41.7 / 54.6 / 0.0 / 3.7 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | 29.6 | 8.7 | 0.0 | 0.0 | 66.7 | 33.3 | 50.0 / 46.3 / 0.0 / 3.7 |
| GLiNER2.5-multi-Decide | 0.0 | 4.3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.9 / 0.0 / 63.0 / 36.1 |
| GLiNER2.5-multi-Decide-nopolicy | 0.0 | 0.0 | 14.3 | 0.0 | 0.0 | 0.0 | 45.4 / 38.9 / 14.8 / 0.9 |
| GLiNER2.5-Decide | 0.0 | 13.0 | 0.0 | 0.0 | 33.3 | 33.3 | 50.0 / 35.2 / 13.9 / 0.9 |
| GLiNER2.5-Decide-nopolicy | 0.0 | 0.0 | 0.0 | 0.0 | 33.3 | 0.0 | 3.7 / 14.8 / 79.6 / 1.9 |
| GLiNER2.5-Decide-1B | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 / 0.0 / 97.2 / 2.8 |
| GLiNER2.5-Decide-1B-nopolicy | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 / 0.0 / 100.0 / 0.0 |
| tier1 | 40.7 | 8.7 | 0.0 | 0.0 | 0.0 | 100.0 | 65.7 / 31.5 / 0.0 / 2.8 |
| always_allow | 0.0 | 13.0 | 0.0 | 0.0 | 0.0 | 33.3 | 100.0 / 0.0 / 0.0 / 0.0 |
| always_redact | 0.0 | 4.3 | 0.0 | 0.0 | 100.0 | 66.7 | 0.0 / 100.0 / 0.0 / 0.0 |
| always_ask_user | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 / 0.0 / 100.0 / 0.0 |
| always_block | 0.0 | 8.7 | 14.3 | 0.0 | 66.7 | 33.3 | 0.0 / 0.0 / 0.0 / 100.0 |

Paired differences against tier-1 and the hard-invariant violations by item id (R-19):

| decider | Δ acceptable acc vs tier1 [95% CI] | Δ Catch@UIR5 vs tier1 [95% CI] | hard-invariant violations (ids) |
|---|---|---|---|
| basal-omni-1.1-max | [20.2, 36.8] | [61.0, 100.0] | none |
| basal-omni-1.0-max | [18.3, 35.1] | [58.2, 100.0] | none |
| torchcast-decision-12b | [10.3, 28.5] | [51.6, 100.0] | none |
| Winnow-12B | [18.0, 35.1] | [57.7, 100.0] | brama-ex-0099 |
| basal-2.0-max | [10.8, 26.2] | [48.8, 98.2] | none |
| d3-flash | [13.9, 29.9] | [50.0, 100.0] | none |
| SPX-CD-Omni | [-7.9, 9.7] | [48.3, 98.3] | none |
| decider-12b | [4.8, 22.8] | [28.8, 100.0] | none |
| basal-omni-1.0-mini | [7.2, 28.7] | [41.4, 98.3] | brama-ex-0033 |
| d3-mini | [1.8, 20.0] | [29.8, 93.0] | brama-ex-0031 |
| Bespoke-Nimble-9B-v3 | [18.1, 33.6] | [53.3, 100.0] | none |
| pplx-decider-flash-v1.2 | [7.6, 25.2] | [34.8, 92.2] | brama-ex-0031, brama-ex-0033 |
| h2o-lightning-4b | [17.2, 33.1] | [35.6, 100.0] | none |
| basal-2.0-4.5B | [2.7, 18.1] | [41.4, 93.1] | none |
| Jev-Omni | [4.0, 22.0] | [27.3, 94.5] | none |
| d3-nano | [-7.0, 14.1] | [17.9, 75.4] | none |
| hopper | [-10.4, 8.0] | [14.6, 80.4] | none |
| basal-omni-pico | [0.0, 18.6] | [9.4, 69.1] | none |
| clef-flash | [-3.9, 13.5] | [4.8, 67.3] | brama-ex-0025, brama-ex-0031, brama-ex-0033, brama-ex-0099 |
| d3-lite | [-41.1, -16.8] | [-15.2, 37.0] | brama-ex-0099 |
| basal-2.0-mini | [-30.8, -10.9] | [-20.0, 43.9] | brama-ex-0099 |
| Bielik-PL-11B-v3.0-Instruct | [-13.1, 0.0] | [15.6, 75.9] | brama-ex-0031, brama-ex-0099 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | [-9.5, 1.7] | [-4.0, 46.2] | brama-ex-0028, brama-ex-0030, brama-ex-0031, brama-ex-0099 |
| GLiNER2.5-multi-Decide | [-61.6, -42.5] | [-30.6, 22.6] | brama-ex-0094 |
| GLiNER2.5-multi-Decide-nopolicy | [-36.3, -17.6] | [-32.1, 19.7] | brama-ex-0004, brama-ex-0028, brama-ex-0033, brama-ex-0094, brama-ex-0106, brama-ex-0107 |
| GLiNER2.5-Decide | [-41.6, -21.9] | [-30.6, 21.8] | brama-ex-0006, brama-ex-0031, brama-ex-0033, brama-ex-0094, brama-ex-0106, brama-ex-0107 |
| GLiNER2.5-Decide-nopolicy | [-55.0, -29.8] | [-37.0, 9.8] | brama-ex-0094, brama-ex-0099 |
| GLiNER2.5-Decide-1B | [-60.7, -36.6] | [-31.0, 15.7] | none |
| GLiNER2.5-Decide-1B-nopolicy | [-62.6, -38.2] | [-35.1, 9.4] | none |
| tier1 |  |  | brama-ex-0025, brama-ex-0028, brama-ex-0030, brama-ex-0031, brama-ex-0033, brama-ex-0107 |
| always_allow | [-19.6, -5.0] | [-39.0, 0.0] | brama-ex-0004, brama-ex-0006, brama-ex-0025, brama-ex-0028, brama-ex-0030, brama-ex-0031, brama-ex-0033, brama-ex-0094, brama-ex-0099, brama-ex-0106, brama-ex-0107 |
| always_redact | [-47.9, -30.8] | [-39.0, 0.0] | none |
| always_ask_user | [-62.6, -38.2] | [-39.0, 0.0] | none |
| always_block | [-44.3, -21.0] | [-39.0, 0.0] | none |

Paired differences against the leader, basal-omni-1.1-max (point difference [95 % CI], pt):

| decider | Δ acceptable acc | Δ Catch@UIR5 |
|---|---|---|
| Winnow-12B | −1.9 [−8.0, 4.5] | −3.6 [−11.9, 0.0] |
| basal-omni-1.0-max | −1.9 [−6.4, 2.7] | −1.8 [−30.4, 0.0] |
| Bespoke-Nimble-9B-v3 | −2.8 [−9.5, 4.3] | −25.5 [−41.7, 0.0] |
| h2o-lightning-4b | −3.7 [−10.9, 3.6] | −30.9 [−63.9, 0.0] |
| d3-flash | −6.5 [−12.8, 0.0] | −7.3 [−49.1, 0.0] |
| torchcast-decision-12b | −9.3 [−17.4, −1.1] | −1.8 [−44.2, 0.0] |
| basal-2.0-max | −10.2 [−17.3, −2.9] | −7.3 [−26.6, −1.7] |
| basal-omni-1.0-mini | −10.2 [−17.9, −2.9] | −21.8 [−40.0, −1.7] |

Acceptable accuracy by item language (62 Polish, 46 English items; differences under ~15 pt are noise here):

| decider | PL | EN |
|---|---|---|
| basal-omni-1.1-max | 90.3 | 88.1 |
| basal-omni-1.0-max | 90.3 | 85.7 |
| torchcast-decision-12b | 82.3 | 81.0 |
| Winnow-12B | 88.7 | 88.1 |
| basal-2.0-max | 79.0 | 81.0 |
| d3-flash | 82.3 | 83.3 |
| SPX-CD-Omni | 69.4 | 54.8 |
| decider-12b | 82.3 | 69.0 |
| basal-omni-1.0-mini | 80.6 | 78.6 |
| d3-mini | 72.6 | 71.4 |
| Bespoke-Nimble-9B-v3 | 85.5 | 88.1 |
| pplx-decider-flash-v1.2 | 79.0 | 76.2 |
| h2o-lightning-4b | 82.3 | 90.5 |
| basal-2.0-4.5B | 74.2 | 66.7 |
| Jev-Omni | 75.8 | 73.8 |
| d3-nano | 64.5 | 64.3 |
| hopper | 58.1 | 61.9 |
| basal-omni-pico | 71.0 | 69.0 |
| clef-flash | 67.7 | 61.9 |
| d3-lite | 30.6 | 33.3 |
| basal-2.0-mini | 37.1 | 45.2 |
| Bielik-PL-11B-v3.0-Instruct | 58.1 | 50.0 |
| Bielik-PL-Minitron-7B-v3.0-Instruct | 59.7 | 52.4 |
| GLiNER2.5-multi-Decide | 1.6 | 21.4 |
| GLiNER2.5-multi-Decide-nopolicy | 29.0 | 40.5 |
| GLiNER2.5-Decide | 35.5 | 21.4 |
| GLiNER2.5-Decide-nopolicy | 11.3 | 28.6 |
| GLiNER2.5-Decide-1B | 3.2 | 23.8 |
| GLiNER2.5-Decide-1B-nopolicy | 3.2 | 19.0 |
| tier1 | 62.9 | 57.1 |
| always_allow | 51.6 | 45.2 |

## Reading the results

- **The decision models read the policy and the destination, not only the payload.** The general LLMs and tier-1
  score 0–9 % on flow sensitivity (does the answer change when only the destination changes) and 0 % on policy
  sensitivity; basal-omni-1.1-max scores 91.3 % and 50 %, Winnow-12B 73.9 % and 100 %. That is the part of the
  construct the tier-1 rule cannot cover, and the main reason the decision models pull ahead on T2–T7.
- **Policy reading is still thin.** Only five models (Nimble, Winnow, basal-omni-1.0-max, d3-flash, h2o) get both
  policy-twin pairs right, and T6 group consistency tops out at 66.7 %. There are only two policy pairs in v0, so
  this is a pointer for the dev split, not a result.
- **`ask_user` splits the field.** Of the 11 gold-`ask_user` items, Bespoke-Nimble gets 10, Winnow and h2o 8, the
  two basal-omni max models 7, d3-flash and basal-2.0-max 5, torchcast 1 and both Bielik models 0. The usual miss is
  `redact`, which Brama counts as a catch under R-17 but wrong under M-04.
- **Size helps within a family, not across them.** basal's 0.75–1.6 B models stop 16–31 % at the budget, 4.8 B
  66 %, 7.9 B 78 % and 11–12 B 93–100 %; d3 goes 24 → 46 → 78 → 93 % from 0.85 B to 8.4 B. Across families,
  h2o-lightning-4b out-scores five 11–12 B models on accuracy.
- **Calibration is usable for most decision models.** ECE is ≤ 0.14 for 16 of 21 (Winnow 0.037 best); Bielik is
  overconfident (0.30–0.35), and GLiNER's low ECE comes from low confidence.
- **Order sensitivity varies.** hopper (20.4 %), basal-2.0-mini (19.4 %) and d3-lite (18.5 %) change their argmax
  with option order most often; R-13 averaging matters for them. The top four flip on 4–7 % of items.
- **Hard invariants:** three of the top four have none; Winnow-12B lets one planted "the policy says this is fine"
  instruction through (brama-ex-0099, T9 `adv_twin`), the same item that catches basal-2.0-mini, d3-lite, clef and
  both Bielik models. With brama-ex-0031 (special category, T3) it is the item most deciders get hard-wrong.
- **Fastino's GLiNER2.5-Decide rows are unchanged from the first version**: on this task, zero-shot, they collapse
  onto `ask_user` or `block` with the full state (which exceeds their 512-position encoder) and stay below
  `always_allow` without it. Fastino's larger decision model, GLiDE v1.2 (26 B), is too large for this round.
- **Latency is not comparable across rows**: servers, precision and batching differ (torchcast on vLLM 200 ms,
  decider-12b on its llama.cpp engine 8.9 s, hopper on its slow reference kernels).

## Validity notes

- V-04 holds: every constant decider scores 0 group consistency. Tier-1 scores 17.1 %, from T1 (60 %), T7 and T9
  (33 % each), which breaks the letter of V-04 ("M-02 ≤ 0.05 for tier-1 regex"); the P0-11 review should either
  exempt T1 or scope V-04 to T2–T6.
- M-02 is computed over multi-row groups only (the eight single-row T8 groups would let `always_allow` score
  18.6 %).
- Every run in this report shares one dataset hash and one decider-input hash. The first version's runs were on an
  earlier dataset hash (`659768b9…`, same decider inputs) and are all rerun; the reruns reproduce the
  first version's GLiNER and Bielik-7B numbers exactly.
- Each model was asked through the interface its card documents, with the same question and option texts. A model
  whose own prompt conventions differ (for example a fixed question key, as torchcast's `decision`) was given its
  key, never different text.
- The items were written for this pilot and none was public before these runs, so no model was trained on them;
  but they were drafted by an LLM agent, and decision models trained on LLM-written synthetic data may share their
  style.

## Limitations

- n = 108, 55 non-allow and 53 gold-allow items: ±11 pt on catch and ±6 pt on UIR at best (`BRAMA.md` power table).
  The top four are not separable; only differences of ~10 pt or more in accuracy are.
- Gold is the author's draft (an agent; `adjudication = "pending"`), never labelled by two people or signed off by
  the GDPR person (R-08–R-10). Items were written by an agent, not by people outside the training team (R-06).
- Two synthetic policies; no ood policy, no destination names never seen.
- **Precision differs between rows**: bf16, Q8_0 (the author's or converted here), LLM.int8 and FP8 weights. The
  effect of the port was not measured on Brama; basal-omni-1.1-max and decider-12b had no author GGUF, and
  basal-omni-1.1-max then uses the bf16 calibration on its Q8_0 port.
- Every model ran with its default settings: no prompt, label or threshold tuning. Published scores in the model
  list are the authors' or boards' and were not reproduced here.
- No rewrite verifier (R-17): `redact` and `ask_user` count as prevention, so `redact`-heavy deciders look better on
  M-01 than they would be enforced.
- **Licences:** torchcast-decision-12b and Bespoke-Nimble-9B-v3 are CC-BY-NC-4.0 and hopper is for research and
  demo use only; they are comparison rows and cannot ship in Warda.

## Next steps

- P0-11 review: accept or change M-02 scope, V-04 for T1, the D-B3 acceptable sets (11 items), and the GDPR sign-off
  on T3/T6 gold.
- P1-13: human-written pool and dev/official v0.5, so that the top models become distinguishable, with more policy
  twins and more `ask_user` gold.
- On dev: the leading basal model in bf16 next to its Q8_0 port, to size the quantisation effect; and a GLiDE v1.2 run
  on a larger card, as Fastino's decision-model row.
