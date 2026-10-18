# Notes: basal-1.0 technical report (`docs/basal-1.pdf`, 39 pp., R. Kinas)

"basal-1.0: Reliable, Highly Optimized Typed Decisions for Polish — a calibrated 4.5B model at 12.5 ms per decision".
The report is organised as 13 steps, each stating *what was done → what was measured → the decision*. References below
are to those steps and sections.

## 1. Goal and headline results

- **Task:** typed decisions. A state plus typed questions (choice / noul = P(yes) / score) go in; one forward pass
  returns calibrated probabilities over the allowed answers, with no text generation.
- **Goals:**
  1. At least Jev 1.13.0 accuracy on Polish decisions.
  2. Trustworthy probabilities, measured as **coverage at 1% / 5% error**.
  3. Order robustness.
  4. Local and fast.
  5. Keep English.
- **basal-1.0-4.5B:**
  - Polish decisions: 0.884 vs Jev 0.780 and 0.779 for the best of 11 open systems.
  - English decisions: 0.741 vs Jev 0.736, not distinguishable.
  - **Coverage: 58.6% of test decisions at 1.2% observed error** with a frozen 1% threshold (Jev: 18.1%).
- **basal-1.0-1.5B** (distilled lite variant): −2.9 points, 2.5× throughput.
- **Serving:** 177 ms → **12.5 ms** per two-order decision on an H100 (8.8 ms on a B300; 1.5B: 4.7 ms).
- **Weak spots:** Polish general knowledge 0.737 (AutoJev-27B 0.833) and the public English JevBench (0.74 vs 0.76–0.88
  for the open systems). Polish knowledge is 0.58 against Jev's 0.79.

## 2. Related work (Section 2)

- **Jev:** architecture, parameter count and data are unpublished; trained with "RL for calibrated decisions";
  70–500 ms per request. Its documented weaknesses are arithmetic, dates, literal reading, and English as the primary
  language.
- **Ecosystem:** 60 open Jev-like models within about 10 days. JevBench (frozen, hashed items) ranks 71 systems.
- **Five open designs:**
  1. Training-free letter readout (uncalibrated, order-sensitive).
  2. **Fine-tuned letter readout with LoRA and one temperature** (most of the best systems; basal's choice).
  3. Trained decision heads: kev's packed options + pointer head, or set-level heads.
  4. Bidirectional encoders (0.15–0.4B) with option markers: cheap, weak on long states and multi-step rules.
  5. Discrete diffusion.
- No system used early exits or looped models before basal.

## 3. Evaluation protocol (Section 3)

- **Readout:** options lettered A, B, C…, chat template, assistant prefilled with `{"answer": "`, softmax over the
  letter logits only. Each letter is checked to be a single token.
- **Two option orders:** original and reversed; the served decision is the argmax of the averaged canonical
  distributions. Flip rate = share of items whose top answer changes between orders. This is not full permutation
  invariance for k ≥ 3.
- **Calibration as served:** one order-averaged vector per item, one temperature per type fitted by NLL on the
  calibration split, frozen and applied to test. Thresholds for 1% / 5% accepted error are chosen on calibration
  (equal confidences accepted together) **before** the test is scored.
- **Precision:** bf16 made decisions depend on batch composition (MoE: up to 0.37; dense fine-tuned: 0.03). **All
  evaluation runs in fp32, and every run starts with a batched-vs-single parity check (≤0.02).**
- **Splits:**
  - Generated data is split by template / statute / domain, never by item.
  - Converted English data follows the source's own split; its test part is split into calibration and test by
    question ID, with shared-state items removed from calibration.
- **Honest caveat:** the v4 test was consulted repeatedly during development, so the results are adaptive. A fresh
  holdout scored once is future work.

## 4. The process, step by step

| Step | What | Key measurement | Decision |
|---|---|---|---|
| 1 Baseline | 3,079-item Polish dev suite (knowledge, general, decisions, understanding, English control); Jev + 11 open models | The gap to Jev is **knowledge** (12–13 points); on understanding/decisions the best open models are within 2–4 points. **One temperature brings every model to ECE ≤0.05** | Build on Bielik v3; compete on coverage, not raw ECE; treat knowledge separately |
| 2 Tokenizer | 7 tokenizers on identical texts, latency vs length on the 4.5B | APT4 (32k): 2.11 tokens/word on Polish decisions; others need 17–51% more tokens and make 15–34% fewer decisions/s at batch 32. English costs about 1.6× more. Batch-1 latency is flat to about 1k tokens (~32 ms, launch-bound) | APT4. A shared tokenizer across 1.5B/4.5B/11B makes exact teacher–student distillation possible |
| 3 Generic-text KD | Full-vocabulary KD 11B → 4.5B on Polish web/wiki, stopped at 63M of 150M tokens | Knowledge −2.0, general knowledge −2.2, decisions unchanged. The ECE gain was worse than a plain temperature (0.037 vs 0.018) | **Stopped.** Spend compute on decision data. (Single run, no CE controls: open question) |
| 4 Logit lens | Option distribution read from every layer through the final head | Chance up to layer 49 of 60; 90% agreement with the final layer only at layer 54 | No untrained early exit; at best 1.11× |
| 5 First decision training (v1) | 8k deadlines, 8k amounts, 1.7k statute questions, PolEmo/SIB; 8 templates per generator (5/1/1/1); LoRA r32 all linear, 1 epoch, CE over letters | 0.476 → 0.825–0.835 on unseen templates (Jev 0.686). **Random option order: flip 0.164 → 0.031.** Consistency (JS) loss: no gain. "Was filing on time?" stays at chance for everyone. Untrained decision types did not improve | Always shuffle order; drop consistency loss; next: breadth of decision types |
| 6 MoE base? | LFM2.5-8B-A1B (≈1B active) | Polish knowledge 0.362 (vs 0.550); **flip 0.74**; bf16 router made outputs batch-dependent (up to 0.37), fp32 exact | **Reject.** A MoE base needs a router stable in low precision. The parity check becomes mandatory |
| 7 Breadth (v2) | 12 broad types × 14 domains × 7 registers; each case → base + counterfactual + 2 sufficiency items; kept only if **2 blind verifiers agree** (37% of 15k cases) | 4.5B 0.876 vs Jev 0.808; coverage@1% 67% vs 34%. Sufficiency "no": 0.95 vs Jev 0.82 | See the ablations in §5 |
| 8 Bilingual + decision KD (v3) | +13.5k English items from bev-decision-150K (debiased, domain cap 12%); KD (1−α)CE + α·KL(p_T‖p_S), α=0.5, teacher = 11B on v2 | English helped (0.756 vs Jev 0.736) without hurting Polish; Polish knowledge rose for the first time. KD lowered overall (0.843 vs 0.852) and **hurt English** (the teacher never saw English) but helped dates | Distil only from a teacher strong in the domain, and only on items it gets right |
| 9 Rule families (v4) | 10 statute rule families as **twins**; rules that would need recall are stated in the state, well-established law must be known; +6k last-day items, +4,962 decomposition primitives | Rule families 0.921 vs Jev 0.635; last-day 0.998; decomposed filing 1.000. Weakest: consumer withdrawal 0.64, tiered price lists 0.82. Generator bug (notice period) reproduced by the model | v4 = released data. Retrain teacher and student |
| 10 Freeze | Choose among v4 candidates on **calibration accuracy**, not test; fit temperatures on the served predictor | 0.858 test, ECE 0.010, 58.6% @1% (1.22% observed), 75.0% @5% (4.41%). Temperatures: choice 1.07, noul 1.48, score 1.11 | Release CE 4.5B v4 (KD twin 0.844 vs 0.847 on calibration, not chosen) |
| 11 Early exit + compression | Exit heads (RMSNorm + low-rank adapter into the frozen head) at layers 30–55; pruning; looped shared block; 1.5B distillation | Exits: 1.22× fewer layers, 1.13–1.16× latency. 1.5B distilled: −2.9. **Pruned to 36 layers: −8.1; 26 layers: 0.547. Looped model did not train** (averaging layers destroyed the network) | Exits as an opt-in per-request setting; 1.5B as lite; no pruning, no looping. "A model pretrained at small size has learned to use its depth" |
| 12 Serving | bf16 → CUDA graphs (right-pad, no mask) → compile → **shared prefix for both orders** → token-budget batching (≤12,288 padded tokens) | 176.5 → 32.9 → 23.3 → 16.5 → **12.5 ms** on an H100, 25 → 63 decisions/s, agreement with fp32 ≥0.993. FP8 helps only compiled, and only on compute- or bandwidth-bound GPUs | bf16 compiled path by default; FP8 opt-in; NVFP4 only for batched throughput (−3 points) |
| 13 Reasoning data (v5) | Long policies (2.5–3.2k tokens), quantitative reasoning / rule priority, judging answers; 25.7k train items, twins, 15% injected instructions | New tasks 0.49 → 0.76; JevBench +3.9 and half the ECE; but Polish decisions −0.6 and Polish general −1.5 | **Rule fixed before the run:** replace only if Polish holds, so v4 is kept |

## 5. Ablations that matter (Steps 5–9)

- **Learning rate:** 1e-4 diverged on v2 (stable on v1); 5e-5 is stable. The trainer skips non-finite steps.
- **Pointer head** (each option in its own segment, shared positions, block mask): flip exactly 0, but 0.860 vs
  0.876, lower coverage. It **cannot compare options**: choosing the last day among candidate dates falls to 0.144.
  Kept only for independent labels such as routing.
- **Full fine-tuning of the base model** (bf16 AdamW, 1e-5): 0.823 vs 0.876 for LoRA on the instruct model, with no
  knowledge gain.
- **Scale:** the same recipe on 11B gives +2.7 points and +9 points Polish knowledge.
- **Per-type temperatures:** coverage changes by <0.01 (kept anyway).
- **Decomposition:** "was the filing on time?" requires recall + day counting + submission-mode rule in one pass. The
  model answered "no" 79% of the time. Splitting it into two primitives ("last day of the period", "legal filing
  date") and comparing in code: 0.48 → 0.92 (4.5B), 0.52 → 0.69 (Jev); with targeted data **1.000**. The composite
  question is served only through decomposition.
- **Knowledge across iterations:** decision training never damaged knowledge. Polish knowledge moves little with data
  (0.550 → 0.579) but clearly with size (11B: 0.669).

## 6. Data (Section 18)

- **Item format:** state, instructions, 2–10 options, gold index, type; plus family, template, generator/verifier
  models, language, split. Items are rendered exactly as served.
- **Three ways to make items:**
  1. **Code-generated** (51% of v4, 65% of v5): Python samples facts, renders them through hand-written templates and
     computes the label with a rule engine (holiday calendar, exact fractions, requirement checkers). No LM involved.
     Distractors are typical mistakes (no weekend shift, net vs gross, inclusive vs exclusive).
  2. **LM-written, LM-verified** (22% / 16%): open-weight generators (Qwen3.6-27B, DeepSeek-V4-Flash, GLM 5.3), each
     item checked by 2 blind verifiers. Statute questions need a verbatim quote. Broad items involve commercial models.
  3. **Converted public data** (27% / 19%): bev-decision-150K (13.5k English, provenance not traceable row by row),
     PolEmo 2.0, SIB-200.
- **Constructs:**
  - **Twins:** one changed fact flips the answer; non-flipping pairs are discarded; both twins stay in one split.
  - **Sufficiency pairs:** the full state answers "yes, decidable"; with the deciding fact removed, "no".
- **Hygiene:**
  - Split by template / statute / domain / case.
  - Remove external states shared with test.
  - 8-gram overlap check against the public benchmark.
  - Drop items over 4,000 tokens.
  - Debias converted English (correct-first 39–65%, 70% "no").
  - Domain cap 12%; options shuffled in training.
- **Sizes:** v4 63,663 train / 8,560 test. v5 89,321 / 11,240 / 12,531 / 13,614.
  - Group sizes (train, v5): deadlines 18,427; amounts 6,198; statute rules 7,548; statute text 1,173; broad 7,970;
    sufficiency 5,146; long policies 6,736; quantitative 10,092; judging 8,830; English 13,500; Polish public 3,701.
  - 71% Polish / 29% English; choice 66%, noul 28%, score 6%.
- **Audit:** a post-release independent recomputation of all statute families found **one wrong rule**: the
  notice-period generator ignored seniority reached during the notice (125 items). Evaluation labels were corrected
  (v4-fix1); the released weights keep the error.

## 7. Architecture and training recipe (Section 17, Step 11)

- **4.5B:** 60 layers, d=2048, SwiGLU 11,008, GQA 16/2 (head 128), RMSNorm, RoPE, 32k context, APT4 32k, untied head.
  Starts from Bielik-4.5B-v3.0-Instruct; LoRA r32 on all linear layers, merged.
- **1.5B:** 32 layers, d=1536, FF 8,960, GQA 12/2. Full fine-tuning + decision distillation from the frozen 4.5B:
  - Loss 0.5·CE + 0.5·KL over the option letters, p_teacher order-averaged, option order shuffled.
  - 2 epochs of v4: 1,990 steps × 64 items on 8 GPUs.
  - AdamW (0.9 / 0.95), no weight decay, lr 2e-5, 20-step warmup, cosine to 10%, max length 1,536.

## 8. Benchmarks (Section 20)

- **Same harness for everyone:** one H100, each system behind its own official server, same HTTP client. Four sets:
  PL decisions 7,081; PL general 3,079; EN decisions 1,479; JevBench public 231.
- **Polish decisions:** open 4B systems score 0.59–0.71; models at 0.81–0.86 on the English benchmark lose 13–23
  points on Polish decisions.
- **Speed over HTTP:** basal-4.5B 13.9 ms p50, 57 req/s; basal-1.5B 7.7 ms, 147 req/s (the fastest system tested);
  decider-35B-A3B 36.5 ms. basal's single request already includes both orders; other systems would need 2 calls (up
  to −3.2 points with one call).
- **Hardware:** server GPUs are launch-bound (compile + graphs matter); consumer/workstation GPUs are compute-bound
  (the shared prefix matters most); DGX Spark is bandwidth-bound (FP8 halves latency). The test items are not
  published (evaluation available on request; leaderboard shows scores only).

## 9. Moderation case study (Section 21)

- **Setup:** one-sentence definitions per category, no Polish moderation training (587 English moderation items in
  fine-tuning). 4.5B beats Sójka-0.1B on 4 of 5 benchmarks.
- **Against Sójka-0.5B:** better on HateCheck-PL and PolyGuard-PL, worse on Gadzi macro, inconclusive on the rest.
- **New questions without training:** target group 92.5% accuracy, threat AUROC 0.91. A slur definition that was too
  broad shows the model answers the question as written.
- **Cost:** 5–10× the latency and ~100× lower throughput than the encoder guards. Text is not shared across questions
  (10 ms for 1 question, 39 ms for 5, 100 ms for 12).

## 10. Limitations and next steps (Sections 23–24)

- Same generators in train and test; **a human-reviewed benchmark from real Polish documents is "the most important
  remaining step".**
- Verifier agreement selects easy broad items; single seeds; adaptive test use; the known notice-period label error;
  only reversal-based order robustness; quantised checkpoints' calibration not validated; English corpus provenance
  open.
- **Next:**
  - Retrain on the corrected labels.
  - A fresh holdout scored once.
  - A v5 mix that keeps Polish.
  - Quantisation-aware training for 4-bit.
  - Prefix sharing across questions (not implemented).

## 11. Implications for basal-scratch (our from-scratch MoE)

**Already aligned with the report:**
- fp32 router + parity check: ours is 2.7e-7.
- Both-order averaging.
- Per-type temperatures, plus per language.
- Thresholds frozen on calibration.
- Template-disjoint splits, twins, sufficiency pairs, 12% domain cap, option shuffling.
- APT4 tokenizer.

**Where the report explains what we saw:**
- **Our deadline and threshold families stuck near chance.** Our deadline noul asks the composite "Czy złożono w
  terminie?", the exact question basal found at chance for *every* system, solved only by **decomposition**. We should
  replace it with primitives ("ostatni dzień terminu", "data wniesienia") compared in code, and add last-day and
  decomposition primitive items, as v4 did.
- **Knowledge gap (tasksource, kaivoss, basal examples):** the report shows knowledge scales with base-model size, not
  decision data (0.55 → 0.58 with data; 11B 0.67), and that generic-text KD lost knowledge. Matching basal requires a
  model pretrained on far more tokens (Bielik v3: 292B) or knowledge supplied in the state.
- **Letter readout failed for us but works for basal:** basal fine-tunes an *instruct* model that already binds
  letters to options. Our pointer readout differs from basal's rejected pointer head: theirs puts each option in an
  isolated segment, while ours reads causal states of a shared sequence (later options see earlier ones; the answer
  slot sees all). Basal's finding that isolated pointers cannot compare options (dates 0.144) is a plausible
  contributor to our weak date-choice families. Worth an ablation: a set-level head over all options, or a letter
  readout after more pretraining.
- **Pruning and looping failed; small pretrained models use their depth.** This supports pretraining a bigger MoE from
  scratch over compressing basal.
- **MoE caveat:** basal's MoE rejection was about weak Polish knowledge, position bias and bf16 router
  nondeterminism. Our fp32 router fixes determinism, but it gives up low-precision serving speed on the router path.

**Practices to adopt:**
- **Fix replacement rules before runs:** e.g. "v4 replaces v3 only if Polish holds".
- **Select checkpoints on calibration accuracy, not on test.** We consulted test across v2–v4 too: same adaptivity
  caveat.
- **Distil only where the teacher is right and strong.** Our real-text distillation has no gold, so teacher-correct
  gating can't be applied; keep code-labelled data as the anchor.
- **A fresh, frozen holdout scored once, and a human-reviewed real-document set:** the spot-check file is a start.
- **State rules in the state** when they would otherwise need recall (court fees, tax, interest), so the label follows
  from evidence.
- **Remaining serving ideas:** a compiled forward + shared prefix for both orders is basal's main latency win; ours
  already runs both orders but without prefix sharing.
