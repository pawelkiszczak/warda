# warda-scratch: a GPT-2-sized MoE decision model trained from scratch on a Mac

End-to-end experiment: curate Polish (+English) pretraining data from SpeakLeash and Hugging Face following the Bielik
reports, pretrain a 126M-parameter MoE (37M active) for 1B tokens with MLX on an M4 Max, fine-tune it into a
typed-decision model, calibrate it and evaluate it. Environment: Python **3.12** (required: pyarrow publishes no wheels
past 3.13), managed by uv from the repository root: `uv sync --locked` installs the dependencies declared in
`pyproject.toml` at the versions locked and tested together in `uv.lock`, and every command below runs through
`uv run`. Data and runs live in `pretrain/work/` (gitignored).

## Pretraining data

`data/build_tokens.py` downloads resumable SpeakLeash JSONL.zst prefixes in parallel with HTTP Range and the selected Hugging
Face parquet train shards, then filters, classifies, deduplicates, and tokenizes with APT4. Cleaned SpeakLeash docs are
cached per source; curation and tokenization are streamed in bounded batches through a 12-worker process pool into a
SQLite spool to avoid retaining the corpus in RAM. Run progress is persisted at `work/data_pipeline.log`; token-bin
hashes and source licenses are written to `work/tokens/manifest.json`.

Curation uses NFC normalization, replacement-character ratio ≤0.001, email/phone/URL anonymization, ≥200 alphanumeric
characters, and loop/duplicate-line rejection. Documents sharing any normalized word 13-gram with KLEJ test data are
removed. SpeakLeash HIGH passes directly; other Polish docs require P(HIGH)>0.50 (the permitted relaxation from >0.90;
it did not materially increase selected volume). The XGBoost classifier uses Bielik v3 hyperparameters (250 estimators,
depth 8, learning rate .08, subsample .75, colsample .8, alpha .2, lambda .5); evaluation: accuracy 0.8133, macro-F1
0.8136, HIGH-F1 0.7845. Exact SHA-256 and 128-permutation MinHash word 13-gram LSH at Jaccard .8 are used. Per-source
train/val selection is seeded-random (42) within caps, not ranked by P(HIGH); val is held out by document.

Data source licenses as reported by the source manifests:

| Source | Manifest license |
| --- | --- |
| `fineweb-2` (Polish), `fineweb-edu` (English) | ODC-By-1.0 |
| `plwiki` | CC-BY-SA 3.0 |
| `wolne_lektury_corpus` | CC BY-SA 4.0 or Free Art License |
| `1000_novels_corpus_CLARIN-PL` | CC BY 4.0 |
| `biblioteka_nauki_pl_corpus` | TBC |
| `europeana_eu_pl_corpus` | Public Domain, Creative Commons |
| `saos` | Not specified (blank in manifest) |
| `eurlex_corpus` | Public domain |
| `ISAP_corpus` | `https://isap.sejm.gov.pl/` (manifest value) |
| `PPC_corpus` | Public Domain |
| `CBOSA_corpus` | conditional licence |
| `open_subtitles_corpus` | Public Domain; CC BY-SA 3.0; Free Art License 1.3 |
| `shopping_1_general_corpus` | conditional license |
| `forum_gazeta_pl_corpus`, `forum_muratordom_pl_corpus` | conditional license |
| `web_artykuły_inne_1`, `web_artykuły_inne_2` | conditional license |

One clean run downloaded 19,993,996,594 unique bytes (~18.6 GiB); repairing a corrupted FineWeb-2 shard brought total
transfer to about 24.84 GB plus small manifests/benchmark files. The full pipeline log is `work/data_pipeline.log`.

Observed stage yields:

| Stage | Documents |
| --- | ---: |
| SpeakLeash raw | 3,003,775 |
| Invalid JSON | 13 |
| SpeakLeash cleaned | 2,644,563 |
| Cleaning drops | 415,157 |
| SpeakLeash quality-scored | 2,644,563 |
| SpeakLeash admitted (HIGH or P(HIGH)>0.50) | 1,400,947 |
| FineWeb-2 language/quality eligible | 2,932,005 |
| FineWeb-Edu eligible | 725,720 |
| Decontaminated | 543 |
| Exact duplicates | 6,192 |
| MinHash near-duplicates | 360,362 |
| Unique deduplicated/tokenized candidates | 4,691,575 |

Final token mix (whole-document counts from the manifest; the 1.05B allocation is unmet because SpeakLeash source
quotas/data availability cap the total):

| Source group | Planned tokens | Selected tokens | Share of selected |
| --- | ---: | ---: | ---: |
| FineWeb-2 Polish | 367,500,000 (35%) | 367,500,780 | 44.4% |
| FineWeb-Edu English | 157,500,000 (15%) | 157,501,803 | 19.0% |
| SpeakLeash | 525,000,000 (50%) | 302,436,277 | 36.6% |
| Total train + val | 1,050,000,000 | 827,438,860 | 100% |

The P(HIGH)>0.90 run produced 821,854,843 train / 5,144,940 val tokens. The P(HIGH)>0.50 run produced 822,407,035 train
/ 5,031,825 val tokens, only 552,192 more combined tokens; neither reaches the ≥1B train target. Rebuilding with the
strict threshold would take well over the 60-minute limit (the relaxed full run took 16,185 seconds), so the current
bins retain the P(HIGH)>0.50 setting. They are usable for training 1B total tokens (~1.22 epochs), but are not a
1B-token unique corpus.

The bins built by this run framed every document as `<s><s> … </s>`: the tokenizer added its own `<s>` on top of the
explicit framing. The doubled `<s>` was removed in place afterwards (train 822,407,035 → 821,488,299 tokens; new hashes
under `bos_dedup_fix` in the manifest) and `tokenize_worker` now encodes with `add_special_tokens=False`, so a rebuild
produces `<s> … </s>` directly.

Per-source train/val bins, mixed bins, and SHA-256 hashes are in `work/tokens/manifest.json`. Reproduce with:

```bash
uv run python pretrain/data/build_tokens.py --download --download-only
uv run python pretrain/data/build_tokens.py
```

## Decision data

`sft/generate.py` builds the four typed-decision JSONL splits in `work/sft/`. Run from the repository root with:

```bash
uv run python pretrain/sft/generate.py
```

Generation is seeded and rerunnable. It produces five code-labeled Polish-first families (deadlines, VAT/discounts/instalments,
threshold rules, ticket routing, urgency scores), plus sufficiency pairs in every split and gold-flipping deadline,
amount, and threshold counterfactuals whose paired rows share `case_id` and split. Each family has eight narrative
templates: templates 0–4 train, 5 dev, 6 calibration, 7 test. Entity pools are disjoint by split. Polish states use
named entities in labelled fields and natural-language dates; ISO dates are used only in the held-out template.
English is sampled on every eighth base case (10.8% of retained rows overall). English amount and urgency states are
rebuilt from the generator's exact values rather than re-parsed from the Polish text, so the stated numbers always
match the gold label (`sft/tests/test_englishize.py` locks this in; a value that cannot be determined raises instead
of defaulting). Instruction injections measured 15.9% of code-labeled rows.

Deadline arithmetic shifts weekend and Polish public-holiday endpoints (including Easter Monday and Corpus Christi)
to the next business day. Amount labels use decimal rounding, nonzero discounts, and same-width plausible options;
threshold comparisons cover inclusive and strict boundaries, routing labels are assigned by construction, and urgency
scores follow the explicit thresholds in each state. Option arrays remain canonical (score levels low-to-high; noul
options `tak, nie` / `yes, no`); downstream training performs option randomization.

Public conversions use only `allegro/klej-polemo2-in` (choice sentiment, CC-BY-SA-4.0),
`allegro/klej-allegro-reviews` (score 1–5, license untagged), `allegro/klej-cbd` (noul, license untagged), and
`allegro/klej-dyk` (noul, CC-BY-SA-3.0). Train/dev/cal rows are selected only from each source's train CSV; test
rows come only from its test CSV. Public noul labels are sampled evenly, and each dataset is capped at 12% of the
final training split. No NC datasets are included; “none-tagged” is retained verbatim as a provenance warning, not
a license grant.

The latest generation produced **32,677 / 3,442 / 3,615 / 4,974** train/dev/cal/test rows. Family counts in that
order: deadlines 8,521/1,135/1,136/1,419; sufficiency 3,946/536/536/668; amounts 4,500/400/400/1,000; thresholds
3,298/249/400/629; routing 2,336/341/351/399; urgency 2,650/382/393/459; Polemo 2,500/100/100/100; reviews
2,420/99/99/100; CBD 1,379/100/100/100; DYK 1,127/100/100/100. Per-type counts: choice 14,857/1,576/1,587/2,418;
noul 12,750/1,385/1,536/1,997; score 5,070/481/492/559. Code-computed train share: 77.3%. Bielik render/letter
validation passed for retained rows; 2,173 exact duplicate task-state examples and 27 unpairable sufficiency rows
were removed. The script asserts paired sufficiency labels, train/test template separation, case/split locality, and
all record invariants. When a deciding fact is removed for a sufficiency negative, `tidy_removed` repairs the leftover
separators (`; ;`, `: .`, …) so the removal leaves no surface trace the model could key on.

Audits saved to `work/sft/stats.json`: gold-position histogram 0–4 = 13,518 / 16,529 / 9,112 / 4,555 / 994
(canonical order; training shuffles options); gold-flipping twin pairs = 4,557 train and 1,062 test; complete
sufficiency pairs = 1,973 train, 268 dev, 268 cal, and 334 test. Strict longest-option correctness is reported per
family with ties excluded: routing 23.9% (four options), sufficiency 50.0%, thresholds 50.3%, urgency 32.4%
(three levels), and deadlines 50.2% on eligible rows; amounts and public families have no unique-longest eligible
rows. Output files are `train.jsonl`, `dev.jsonl`, `cal.jsonl`, and `test.jsonl`.

## Model and pretraining

`model.py`: 8 layers, d=512, GQA 8 heads / 2 KV heads with QK-norm and RoPE, tied 32k APT4 embeddings. Every FFN is a
MoE: 32 routed experts (SwiGLU, width 256), top-4, plus one shared expert (width 256); sigmoid router computed in fp32.
125.6M parameters in total, 37.5M active per token (21.1M excluding embeddings).

`train.py`: fp32 master weights + AdamW (β 0.9/0.95, wd 0.1 on matrices, clip 1.0); bf16 forward/backward except the
routers; 16×2048-token micro-batches × 8 accumulation = 262,144 tokens per step; WSD schedule (150 warmup steps, flat,
linear decay to 0 over the last 20%). Balancing: Switch-style balance loss (0.01) plus DeepSeek-V3 selection bias
(step 0.01). With the bias alone at the DeepSeek rate (0.001) routing collapsed onto 4 of 32 experts within a
114-step run (max/mean expert load ≈ 7–8 of a possible 8); with both it stays at ≈1.25.

```bash
uv run python pretrain/train.py --name s126m-1b --tokens 1e9 --lr 6e-4 --warmup 150 --decay-frac 0.2 \
  --balance-rate 1e-2 --aux-coef 1e-2 --eval-every 200 --ckpt-every 200      # add --resume to continue
```

Peak LR came from a 30M-token sweep at the same batch (6e-4 / 1.2e-3 / 2.4e-3 → mean val loss 6.28 / 6.47 / 6.51).
The 1B-token run (3,814 steps, ≈1.22 epochs over 821.5M unique tokens) took 15.0 h on the M4 Max (median 18.5k tok/s).
Mean per-source validation loss went 5.23 (step 200) → 2.96 (end); FineWeb-2 PL 3.30, plwiki 2.78, FineWeb-Edu EN 2.44.

## Decision fine-tuning and evaluation

`sft.py` fine-tunes the pretrained model on `work/sft/`, fits per-type temperatures and 1%/5% error thresholds on `cal`,
and scores `test` once. It renders prompts with `prompt.py` and averages the original and reversed option order.
Routers stay frozen.

Prompt format (`prompt.py`): Warda's own template — a fixed system prompt, then one user turn holding the state, the
question and `A.`–`J.` lettered options, with the assistant reply prefilled to `{"answer": "` so the decision is the
next token. Polish and English templates exist; every other language renders with the English one. The template matches
no external model's format, no released weights depend on it, and old local checkpoints trained with earlier
experimental templates are not compatible with it.

```bash
uv run python pretrain/sft.py --base s126m-1b --name s126m-1b-sft --epochs 6
```

Readout: the letter readout (`--readout letter`) did not train at this scale. Train loss stayed at the
uniform level (≈1.2) for two epochs and dev predictions were one fixed letter (flip rate ≈1.0), so the model never bound
letters to options. The default `--readout pointer` scores each option's last-token hidden state against the
answer-slot state with a small bilinear head (same prompt, one forward pass per order) and learns immediately.

Results (`work/runs/*/eval.json`; checkpoint chosen by dev NLL; test is template-disjoint and the public sets use their
own test splits):

| pretraining before SFT | test acc (chance 0.348) | NLL | ECE (calibrated) | flip rate | coverage @1% target (observed error) |
|---|---:|---:|---:|---:|---:|
| none (random init) | 0.452 | 1.334 | 0.148 | 0.20 | 10.5% (22.5%) |
| 262M tokens (step 1000) | 0.537 | 0.905 | 0.060 | 0.17 | 20.1% (1.7%) |
| **1B tokens (final)** | **0.567** | **0.852** | **0.042** | 0.24 | **23.8% (0.5%)** |

Final model by family (test accuracy / chance): routing 0.995/0.25, urgency 0.950/0.33, sufficiency 0.844/0.50,
PolEmo 0.760/0.25, CBD 0.670/0.50, DYK 0.620/0.50, Allegro reviews 0.510/0.20, deadlines 0.417/0.31,
thresholds 0.498/0.50, amounts 0.264/0.25. By type: score 0.871, noul 0.669, choice 0.414. Polish 0.582, English 0.460.
Temperatures: choice 0.82, noul 1.58, score 1.08. Batched-vs-single parity (fp32 routers): max |Δp| 2.7e-7.

Reading the results: pretraining helps at every level measured (accuracy, calibration, and whether thresholds hold on
test). The model learns the rule-in-state and text-classification families. It does not learn date arithmetic,
VAT/discount amounts or numeric threshold comparison, which stay at chance. Routing and urgency are near-perfect partly
because their generators reuse a small set of messages and rules, so treat those two numbers as template fit rather
than skill. The dev-NLL selection picked epoch 3 of 6 on raw dev NLL; dev accuracy kept rising to 0.609 at epoch 5
while uncalibrated NLL worsened. `sft.py` now selects on dev NLL after a per-type temperature fitted on dev.

Further `sft.py` options: items may carry a soft `target` distribution (e.g. annotator vote shares), which is used as
the training target instead of one-hot `gold`; `--base` may also be a fine-tuned run, so stages chain and the pointer
head carries over; `--extra-eval NAME=PATH` (repeatable) scores additional held-out sets with the calibrated model into
`eval.json["extra"]`.

## Tracking

Tracking is local MLflow; no account or network is needed. `track.py <run> [--follow]` (or `--all`) mirrors a run
directory's `config.json` (params), `metrics.jsonl` / `sft.jsonl` (curves, greedy samples as text artifacts) and
`eval.json` / `calibration.json` (final metrics + artifacts) into `work/mlflow.db`, experiment `warda-scratch`. It
resumes using `<run>/mlflow.json`. Browse and compare runs with:

```bash
uv run mlflow ui --backend-store-uri sqlite:///pretrain/work/mlflow.db --port 5000   # http://127.0.0.1:5000
```

## Jev-style decision data

`sft/convert_jev.py` converts redistributable public typed-decision sources into `work/sft_jev/`. Run from the
repository root with:

```bash
uv run python pretrain/sft/convert_jev.py
```

The script reads Hugging Face Parquet/JSONL directly, validates every converted prompt with the Bielik tokenizer,
and writes full-mixture and 100k stratified-probe train/dev/cal splits plus the existing Polish test examples. The
test examples are re-encoded to the shared schema with one-hot targets; code-labeled rows become `synthetic`.
External evaluation sets are capped at 3,000 rows. `manifest.json` records row/filter/license decisions, mixture and label
histograms, and SHA-256 hashes. Tasksource uses only rows explicitly marked commercial; Open-Jev v1.1 is its
source-dependent redistributable CC0/CC-BY projection; System-One is Apache-2.0. SargeDev is excluded because its
card identifies yuri_v3 as distilled from TypeSafe Jev 1.13 via OpenRouter, so the mixed corpus cannot be shown to
avoid Jev API-derived rows. System-One prompts are parsed into `<state>`, Question and lettered options; any
unparseable prompt is retained whole as state with a generic selection question. The resulting counts, per-source
caps, language/type shares, exclusions and SargeDev provenance decision are recorded in the generated manifest.

Tasksource has no row-level language field; the converter uses source-language tags, script markers and Polish lexical
cues, defaulting to English when no signal is available. Language shares are therefore an inference, not upstream
annotations.

Generated counts: stage-1 train/dev/cal = **368,080 / 2,916 / 3,000**; train source counts are Tasksource 214,143,
Open-Jev 136,017 and System-One 17,920. Dev source counts are 509 / 2,378 / 29 and calibration counts are 0 /
2,898 / 102 in the same order. Train type counts (choice/noul/score) are 274,047 / 64,951 / 29,082; dev
1,705 / 1,015 / 196; cal 1,436 / 1,291 / 273. The 100k probe is stratified by source family, type, option count
and language. Tasksource's largest retained training family is 4,618 rows (1.25% of train); Open-Jev's largest
WANLI family has 82,045 rows (22.3%) and is retained under the explicit full-train inclusion rule. External counts
are Open-Jev test 2,228,
Open-Jev OOD 1,985, System-One test 1,361 and Tasksource test 3,000 (all below the 3,000 cap).

Tasksource's upstream default config has 1,028,298 train, 15,000 validation and 15,122 test rows. Of the combined
1,058,420 rows, 625,554 have `license_use=commercial`; 119,986 non-commercial and 312,880 unspecified rows were
excluded. Per-license and per-source exclusion counts, all row-level filters, language shares and file hashes are
in the manifest. SargeDev v3's 740,957 rows remain excluded because its card says yuri_v3 labels were distilled
from TypeSafe Jev 1.13 through OpenRouter.

## Fine-tuning with Jev-style data

`sft/mix_stages.py` builds `work/sft_jev/stage2/` (Polish train + 30% replayed stage-1 rows; 46,681 rows) and
`work/sft_jev/joint/` (stage-1 train + Polish train ×3; 466,111 rows). All runs start from `s126m-1b`, use the pointer
readout and LR 3e-4, and are scored on the Polish test plus four external sets
(`--extra-eval .../ext/{openjev_test,openjev_ood,kaivoss_test,tasksource_test}.jsonl`). Accuracy, chance in brackets:

| run | data | Polish test (0.348) | Open-Jev test (0.373) | Open-Jev OOD (0.393) | tasksource (0.369) | kaivoss (0.348) |
|---|---|---:|---:|---:|---:|---:|
| `s126m-1b-sft` | Polish only, 6 ep | **0.567** | 0.243 | 0.223 | 0.368 | 0.393 |
| `jev-probe` | 100k stage-1 rows, 1 ep | 0.313 | 0.567 | 0.609 | 0.414 | 0.395 |
| `jev-stage1` | 368k stage-1 rows, 1 ep | 0.396 | 0.627 | 0.654 | 0.432 | 0.442 |
| `jev-stage2` | stage 1 → Polish + 30% replay, 3 ep (epoch 1 selected) | 0.485 | 0.595 | 0.644 | 0.426 | 0.427 |
| `jev-joint` | stage-1 rows + Polish ×3, 1 ep | 0.544 | **0.628** | **0.659** | **0.443** | **0.444** |

Wall time on the M4 Max: stage 1 2.0 h, stage 2 0.4 h, joint 2.4 h (58–80 items/s). One joint run beats
stage 1 → stage 2 on every scored set. In stage 2, Polish dev accuracy fell after its first epoch
(0.515 → 0.499), which suggests the continued 3e-4 learning rate overwrote stage 1. Joint keeps Polish within 2.3
points of the Polish-only model (routing 1.00, urgency 0.96, PolEmo 0.76) and covers 10.5% of Polish test decisions at
0.6% observed error. Per-type temperatures fitted on the Polish calibration set are ≈2 (the model is overconfident);
applied to the English sets they leave ECE 0.03–0.10.

## Distillation data

`distill/build_pool.py` decodes `work/tokens/train.bin` (mixed training documents) and source-attributed held-out
documents from `work/tokens/val_<source>.bin`; the English FineWeb-Edu validation bin is excluded. Training bins have no
per-document source tags, so rows use `pretrain_train_mixed` with mixed-license provenance rather than an inferred source.
A Polish-language heuristic (at least two Polish diacritics or three Polish function words) filters both documents
and candidate passages.
Each passage is a contiguous 400–1,500 character sentence/paragraph slice, identified by a normalized-text SHA-256;
validation document hashes are excluded from training. Questions come from 26 Polish families, each with three
paraphrases and content/source applicability rules; prompts are checked with `prompt.py`'s `render` and limited to 1,536
tokens. The defaults produce 60,000 train and 2,500 eval items. Pool generation is CPU-only; `--limit N` makes each
pool at most N rows.

The pools are unlabelled question rows over real Polish passages; any labelling process (teacher model or human) that
writes a `target` probability vector per row can consume them. The teacher-labelling client used for the historical
runs below spoke an external serving API and has been removed with that dependency. What remains is the generic
tooling around labelled pools:

```bash
uv run python pretrain/distill/build_pool.py        # build unlabelled pools from the token bins
uv run python pretrain/distill/verify_bielik.py     # independent Bielik-11B scoring of labelled eval rows
uv run python pretrain/distill/make_eval.py         # keep teacher/verifier argmax agreements
```

`verify_bielik.py` renders each item with `prompt.py` and averages letter-readout probabilities across both option
orders. `make_eval.py` keeps rows where the teacher and verifier argmaxes agree and the teacher's maximum probability
is at least 0.7, with a per-family cap of 10% (`--teacher-only` skips the verifier). `family_gaps.py` scores a labelled
pool with a fine-tuned run and writes per-family sampling weights for a weighted `build_pool.py --family-weights` round;
`export_spotcheck.py` writes a stratified 100-item human-review sample. Progress and measured rates are logged under
`work/distill/*.log`; all generated data stays under gitignored `work/`.

## Distillation round 1 (24 h plan, P0–P2)

- **P0 – calibration:** `sft.py` fits temperatures per question type and per language group (pl / other), using
  Polish + Jev-style calibration rows (`joint` / `joint-v2` dirs). On the existing `jev-joint` model, English-set ECE
  dropped from 0.078 / 0.098 / 0.065 to 0.031 / 0.043 / 0.042 (Open-Jev test / OOD / kaivoss) with unchanged accuracy.
- **P1 – data:** 45,075 Polish real-text items were labelled by the external teacher's small variant (5.7 decisions/s).
  The large variant ran at only 1.6 decisions/s on these longer prompts, which would have taken 10 h for 60k items.
  The realistic eval set `ext/pl_real.jsonl` has 792 items: 1,900 held-out candidates labelled by the large variant,
  kept only where Bielik-11B agreed (70.7%) and the teacher was ≥0.7 confident. That filter keeps easy families (ads,
  money, instructions) and drops formality and quality questions entirely. 78% of its yes/no gold labels are "nie".
- **P2 – `jev-joint-v2`:** stage-1 rows + Polish ×5 + distilled ×2 (yes/no majority capped at 60%; 63,604
  distilled rows); 595k rows, 1 epoch, 2.5 h.

| run | Polish test | pl_real (n=792) | Open-Jev test | Open-Jev OOD | tasksource | kaivoss |
|---|---:|---:|---:|---:|---:|---:|
| `jev-joint` | 0.543 | 0.408 | 0.628 | 0.659 | 0.443 | 0.444 |
| `jev-joint-v2` | **0.570** | **0.734** | 0.632 | 0.648 | 0.450 | 0.394 |

On pl_real, accuracy by type is choice 0.599, yes/no 0.804 (always answering "nie" scores 0.781) and score 0.952;
ECE is 0.190. The 1% confidence threshold, fitted on Polish + Jev calibration rows, does not hold on the Polish test
(9.7% coverage at 12.4% observed error). pl_real labels come from the same model that labelled the training data,
so part of the gain measures imitation of the teacher.

## Distillation round 2 (P3a)

- **Calibration:** 4% of distilled passages (by `case_id`) are held out into dev/cal, so temperatures and thresholds
  see real Polish text. Confidence thresholds are now fitted per (type, language group) with a global fallback
  (`fit_thresholds` in `sft.py`; groups need ≥200 calibration items).
- **Weighted second round:** `distill/family_gaps.py` scored `jev-joint-v2` against the teacher labels on 2,000 fresh
  labelled items. It set family weights from KL(teacher‖student), from topic 2.8 and genre 2.3 down to 0.5
  for yes/no families the student already matched. `build_pool.py --family-weights --exclude` then drew 78,000 new
  items from passages unused in round 1. These were labelled by the small teacher variant (5.6 decisions/s, 3.9 h).
- **`jev-joint-v3`:** stage-1 rows + Open-Jev/kaivoss ×2 + Polish ×5 + both distilled rounds ×2 (yes/no majority
  ≤60%); 877k rows, 1 epoch, 3.8 h.
- `distill/export_spotcheck.py` writes 100 stratified pl_real items to `work/distill/spotcheck_pl_real.{md,csv}` for
  human review.

| run | Polish test | pl_real (n=792) | Open-Jev test | Open-Jev OOD | tasksource | kaivoss |
|---|---:|---:|---:|---:|---:|---:|
| `jev-joint` | 0.543 | 0.408 | 0.628 | 0.659 | 0.443 | 0.444 |
| `jev-joint-v2` | **0.570** | 0.734 | **0.632** | 0.648 | **0.450** | 0.394 |
| `jev-joint-v3` | 0.542 | **0.768** | 0.631 | 0.649 | 0.449 | **0.487** |

Confidence thresholds (target error → coverage at observed error):

| run | Polish test @1% | Polish test @5% | pl_real @5% |
|---|---:|---:|---:|
| `jev-joint-v2` (round-1 calibration) | 9.7% at 12.4% | 27.8% at 9.9% | 9.5% at 5.3% |
| `jev-joint-v3` (real-text cal, per-group thresholds) | 9.5% at **1.3%** | 17.2% at **3.5%** | 14.0% at **2.7%** |

`jev-joint-v3` on pl_real: choice 0.599 → 0.732, yes/no 0.804 → 0.777, score 0.952 → 0.929; ECE 0.086 (v2: 0.190).
On the Polish test it lost the v2 gains on synthetic rule families (thresholds 0.666 → 0.590, deadlines 0.411 →
0.366), because the Polish synthetic rows are a smaller share of the larger mixture. CBD rose 0.69 → 0.75 and PolEmo
0.75 → 0.78. Re-scoring v2 with the v3 calibration split is not a clean comparison, because v2 trained on part of
those held-out round-1 passages.

## Joint v4 and a larger teacher-labelled eval

- **`ext/pl_real_t45.jsonl`:** 1,606 items. 3,000 new candidates come from held-out documents not used by
  `pl_real`, labelled by the large teacher variant alone (`make_eval.py --teacher-only`, confidence ≥0.7, ≤10% per
  family). 87.5% of its yes/no gold labels are "nie", so its yes/no part barely separates models; choice items
  (n=537) do.
- **`jev-joint-v4`:** the v3 mixture with Polish synthetic ×8 (instead of ×5) and the distilled yes/no majority capped
  at 55%; 973k rows, 1 epoch, 4.0 h. v2 and v3 were re-scored on the new set with the v3 calibration split.

| run | Polish test (±0.014) | pl_real (n=792) | pl_real_t45 (n=1,606, ±0.017) | t45 choice (n=537) | Open-Jev test | Open-Jev OOD | tasksource | kaivoss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `jev-joint-v2` | **0.570** | 0.734 | 0.852 | 0.771 | 0.632 | 0.648 | 0.450 | 0.394 |
| `jev-joint-v3` | 0.542 | 0.768 | 0.860 | 0.808 | 0.631 | 0.649 | 0.449 | **0.487** |
| `jev-joint-v4` | 0.548 | **0.789** | **0.866** | **0.821** | **0.635** | **0.665** | **0.452** | 0.414 |

| run | Polish test @1% | Polish test @5% | pl_real_t45 @5% |
|---|---:|---:|---:|
| `jev-joint-v2` | 23.5% at 5.9% | 33.7% at 13.2% | 46.9% at 5.8% |
| `jev-joint-v3` | 9.5% at **1.3%** | 17.2% at **3.5%** | 20.7% at **3.0%** |
| `jev-joint-v4` | 15.3% at 4.6% | 29.8% at 10.8% | 31.7% at **3.5%** |

Polish ×8 did not bring back the synthetic rule families. v4's Polish test is 0.548 against v2's 0.570; thresholds
fell to 0.552 and deadlines are 0.385. On real Polish text v4 is the best model (pl_real +2.1 over v3, t45 choice
+5.0 over v2), but its thresholds hold only on real text. On the template-shifted synthetic test (the held-out
template writes ISO dates) they accept 4.6% / 10.8% errors at 1% / 5% targets. kaivoss swings between 0.39 and 0.49
across runs, so differences there are not meaningful.

## Text-quality labelling tool (`quality/`)

A data-intake quality check in progress. It samples documents, computes every metric a future classifier may use,
and lets a person label HIGH / MEDIUM / LOW while seeing those metrics. Design: `QUALITY_CLASSIFIER.md`.

| Step | Command | Time | Resumable |
|---|---|---:|---|
| Sample ~1,000 raw documents (SpeakLeash, FineWeb-2 PL, FineWeb-Edu EN controls; stratified by SpeakLeash label and FineWeb `language_score` / `minhash_cluster_size`; 10% repetitive and 5% mixed-language quotas) | `uv run python pretrain/quality/sample.py` | ~56 min | no (output written at the end; seed 42) |
| StyloMetrix env (GPL-3.0, separate process) | `pretrain/quality/setup_stylometrix.sh` | ~5 min, 475 MB model download | — |
| 172 StyloMetrix metrics | `pretrain/.venv-stylometrix/bin/python pretrain/quality/stylometrix_worker.py` | ~2–3 min (6 processes) | yes (skips done ids; delete `stylometrix.jsonl` after a re-sample) |
| Merge: loop + multilingual metrics and highlights (`quality/textstats.py`), LM perplexity (`s126m-1b`), StyloMetrix → `items.jsonl` + `features.parquet` | `uv run python pretrain/quality/enrich.py` | ~2 min | reruns in full, atomic write |
| Labelling app | `uv run python -m pretrain.quality.app --items pretrain/work/quality/items.jsonl --labeller <name> --port 8765` | — | labels saved per click |
| Export | `uv run python -m pretrain.quality.export_labels` → `work/quality/export/{labels,labels_audit}.jsonl`, `dataset.parquet` | seconds | — |

**App views:**

- **`/` (labelling):**
  - The document with repeated text (orange) and non-Polish segments (blue) highlighted.
  - Per-document metrics with sample percentiles: loop, multilingual, cheap features, LM perplexity, StyloMetrix.
  - A source-metadata box.
  - Keys: `1/2/3` HIGH/MEDIUM/LOW, `0` SKIP, letter keys toggle flags (looped, multilingual, wrong_language, …),
    `c` confidence, `n` note, `Enter` save + next, `←/→`, `u` next unlabelled.
- **`/dashboard`:** two tabs (or both), offline inline-SVG charts fed by `/api/viz` + `/api/stats`, refreshed every 15 s.
  - *Automated metrics* (whole sample, no labels): summary tiles; loop × multilingual scatter coloured by origin;
    composition by source with SpeakLeash's own label; dominant language; current cleaning pass / reject reasons;
    12 key-metric histograms stacked by origin; Spearman correlation matrix; any metric by SpeakLeash label.
  - *Human labels*: progress per source (stacked by your label), time left at your median pace; label and flag
    counts; your label × SpeakLeash and × cleaning heatmaps; the scatter coloured by your label; AUROC of each
    detector against its matching flag; top-20 metric AUROC (HIGH-vs-rest / LOW-vs-rest); any metric by your label;
    labelling pace; Cohen's kappa once two labellers overlap.
  - Click any scatter dot to open that document in the labeller (`/?pos=N`).
- **`/check`:** paste any text to see its loop / multilingual metrics (preview of the intake checker).

**Loop / multilingual metrics (`textstats.py`, 14 tests):**

- **Repetition:** Gopher repetition fractions, top 2–4-gram and duplicate 5–10-gram character fractions, zlib ratio,
  longest repeated substring, repeated-line/sentence runs → `loop_score`.
- **Language:** fastText `lid.176.bin` per line (long lines per sentence; units with <20 letters or confidence <0.5
  use Polish cues or inherit the dominant language), character-weighted language shares, `pl_share`, `switch_rate`,
  Unicode script mix, Polish diacritic / stopword ratios → `multilingual_score`. Fetch the model with
  `uv run python -m pretrain.quality.fetch_lid` (SHA-256 pinned); tests that need it are marked `requires_lid`.

Status (2026-10-10): `work/quality/items.jsonl` holds the final sample of 988 documents. Origins: 608 SpeakLeash
(HIGH 232 / MEDIUM 175 / LOW 201), 330 FineWeb-2 (by `language_score` band and cluster size), 50 FineWeb-Edu English
controls. Hard-case strata: 109 repetitive, 56 mixed-script. 98.3% pass the current cleaning. Every item has all
feature groups, except one document where StyloMetrix itself fails ("173 columns passed, data had 172"); it is stored
with empty `stylometrix`. The duplicate-n-gram fractions count each character once; overlapping occurrences used to be
summed and capped at 1.0.

## Harness decider: restricted-data / PII dataset (`harness/pii_gen.py`)

Synthetic typed-decision data for a local data guard in coding harnesses (idea and evidence: `FINDINGS.md`,
data-guard / permission-gate evidence). The guard reads a data policy, a channel, a destination and the content, then decides
what to do with it. All people, companies and values are fictional.

The shared literals behind these labels — actions, categories, destination classes and their mapping, channels —
live in `warda/schema.py`; `pii_gen.py` imports them from there.

```bash
uv run python -m pretrain.harness.pii_gen generate --hours 7.5 --workers 16   # resumable
uv run python -m pretrain.harness.pii_gen build                               # items + manifest
uv run pytest pretrain/harness/tests -q
```

- **How labels are made.** Code samples each case and fixes its ground truth: the kind of restricted data (direct PII,
  details that combine to identify a person, special-category data, credentials, confidential business facts,
  records read by a tool), the channel (commit, PR, issue, chat, HTTP body, web search, LLM prompt, code comment,
  monitoring event, package docs; or SQL / file / log output entering the model) and the facts. Identifiers are
  generated in code and are format-valid (PESEL, NIP, IBAN mod-97, Luhn cards), then substituted into `[[NAME]]`-style
  placeholders the model writes.
- **Generation.** Qwen3.6-35B-A3B (LM Studio on port 1235 and omlx on port 8000, thinking off) writes the payload
  and a *safe twin* for the same task without the restricted information. For tool-output records, the twin is the
  same content with fixture provenance (`tests/fixtures/…`) instead of a production source, sometimes with
  obviously fake values.
- **Verification.** Two blind verifiers judge each text: Qwen3.8-27B and a separate Qwen3.6 pass, both at
  temperature 0. They answer direct identifier / singles out a person / special category / credential /
  confidential.
  - The flags that define the label must be reproduced by both, or the case is dropped.
  - Any other flag drops the case only when both raise it (Qwen3.8 alone over-flags "confidential").
  - Wrong language (fastText) or missing or stray placeholders are rejected as well.
- **Items.** `build` renders each payload and twin under two of three data policies (strict, contracted
  processors, open source). The policy text is generated from the same table that computes the gold action, so
  state and label can't disagree. Each state gets a destination drawn from the channel (internal, client, LLM
  provider with a DPA, external SaaS, public). Questions:
  - action (allow / redact / ask the user / block);
  - may this be sent unchanged (yes/no);
  - the most serious category (7 options);
  - one verified property (yes/no).

  The same payload therefore changes action with policy and destination.
- **Splits.** By case, so twins stay together: 80/5/5/10 for train/dev/cal/test. `test_ood` holds test cases
  re-rendered under a fourth policy (data must not leave the company) that no other split uses. It measures
  whether the guard reads the policy rather than memorising it.
- **Smoke runs.** With the first verifier rule (every flag strict), 8/36 cases were accepted, nearly all failing on
  the twin. After the rule change and stricter safe-twin instructions, 19/36. Quasi-identifier payloads were then
  rejected because both verifiers call personnel events (raises, probation, notice) confidential, so that flag is
  neither checked nor used as a label for them.

Run 2026-10-14 (7.5 h, 16 workers, ~440 cases/h, 0 endpoint errors): **3,332 cases, 2,296 accepted (69%) →
23,912 items** in `work/harness_pii/items/` (72 MB). Manifest: `work/harness_pii/manifest.json`.

| | |
|---|---|
| accepted by kind | direct PII 398/631 · combining details 505/711 · special category 212/442 · credentials 278/332 · confidential 398/554 · tool-output records 505/662 |
| rejected because | placeholders missing or extra 386 · verifier on the twin 231 · verifier on the payload 220 · unusable twin 112 · unparseable 51 · wrong language 36 |
| items by split | train 18,300 · dev 1,120 · cal 1,160 · test 2,380 · test_ood 952 |
| language | Polish 15,088 · English 8,824 |
| action labels | allow 3,992 · block 1,749 · redact 921 · ask the user 702 |
| category labels | none 1,791 · direct PII 903 · combining details 505 · test fixture 505 · confidential 398 · credentials 278 · special category 212 |

Checks after the build:

- No case or payload text is shared between train and dev/cal/test.
- Every action label matches its option text.
- 26 eleven-digit numbers that fail the PESEL checksum are digits inside generated Slack tokens, plus 4 extra
  identifiers the model added in direct-PII payloads. Those payloads are still direct PII.
- The 2 twins that repeat a payload value repeat `test@example.com`-style addresses.
- Known noise: in 304 accepted payloads and 81 twins, exactly one verifier (almost always Qwen3.8) raised
  `confidential_business` where that flag was not checked. Votes are kept in `raw_cases.jsonl` if stricter filtering
  is wanted.
- Polish names stay in the nominative after prepositions ("z Zbigniew Kowalski").
