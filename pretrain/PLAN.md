# Plan: larger basal-scratch MoE (revised after the basal-1.0 report)

Status: **approved for planning only; nothing started.** Revised with the findings in `BASAL_REPORT_NOTES.md`.
Mac time ≈ 17 days (A 2.5 d → B 13–14 d → C 1 d). Phase A is useful even if B never runs.
Related design: `QUALITY_CLASSIFIER.md` (replaces the P(HIGH) > 0.9 filter for the Phase B corpus).

## What the report changed

| Before | After | Evidence (basal-1.0 report) |
|---|---|---|
| Go straight to a 15-day pretraining run | First 2–3 days of data / readout / evaluation fixes on the current 126M model | Steps 7/9: decomposition took the filing question 0.48 → 1.00 on the same model (a data fix) |
| Composite "Czy złożono w terminie?" in training | Primitives ("last day of the period", "filing date") compared in code; last-day items; recall-heavy rules stated in the state | Steps 7/9: all systems at chance on the composite question; primitives 0.998–1.000 |
| Pointer readout fixed | Readout ablation: pointer + cross-option attention layer vs pointer vs letters | Step 7: a pointer that can't compare options fell to 0.144 on date choice |
| Expected knowledge to scale with the run | Lower targets on knowledge-heavy sets | Steps 1/9: knowledge 0.55 → 0.58 with data, up mainly with model size; Bielik saw 292B tokens, M sees 5B |
| Select on test | Select on calibration; replacement rules written before runs; one sealed holdout scored once | Sections 3/10/13 |
| Distil from all basal-1.5B labels | Distil where the teacher is likely right: full soft-target weight where basal-1.5B and 4.5B agree, reduced weight elsewhere | Step 8 |
| No generator audit | Independent unit-test recomputation of every rule generator | Section 18: one wrong rule → 125 mislabelled items |
| Plain-text pretraining mix | +~2% instruction / decision-format text | Bielik mixes instruction data into pretraining; basal's letter readout relies on an instruct base |
| Single runs | 2 seeds for cheap 126M ablations | Section 23 |

## Phase A — fix data, readout, evaluation on the 126M model (~2.5 d)

1. **Data v6 (~4 h):**
   - Replace composite deadline/filing items with primitives (last day; filing date by submission mode), compared in
     code.
   - Add ~6k last-day items and the primitives.
   - State recall-heavy rules (fees, interest, price lists) in the state.
   - Independent unit tests recompute every generator from hand-worked cases.
2. **Readout ablation (~10 h):** joint-v4 recipe on a 300k-row subset, 2 seeds; pointer vs pointer + cross-option
   attention vs letter readout. Measured on date-choice families, thresholds, pl_real and Open-Jev OOD.
3. **Distillation gating (~6 h):** relabel the 45k round-1 items with basal-4.5B (~1.7–1.8 decisions/s); where 1.5B and
   4.5B disagree, reduce the soft-target weight.
4. **Evaluation protocol (~3 h):**
   - Sealed holdout: 2–3k items from new templates, generated after freeze.
   - Human-checked set from the 100 spot-check items, grown to 300–500.
   - Replacement rules written before training.
5. **Gate A** (on calibration data):
   - Decomposed deadline ≥0.85 on 126M.
   - The best readout beats the current one by ≥2 points on choice items, on both seeds.
   - Gated distillation doesn't lower pl_real.
   - If decomposed deadline < 0.6, it is a capacity problem → becomes a Phase B criterion.

## Phase B — pretraining M = 744M total / 149M active (~13–14 d)

- **Architecture:** 16 layers × 768, GQA 12/4, 48 experts × 384 top-6 + shared 384, fp32 router, best readout from
  Phase A. Measured: benchmark 7.1k tok/s, ≈4.8k sustained, 46 GiB peak at micro-batch 8×2048.
- **Data, ~5.5B unique tokens:**
  - FineWeb-2 PL ~2.5B, HPLT 2.0 PL ~1B (CC0), SpeakLeash ~1.3B, FineWeb-Edu EN ~0.7B.
  - Web sources at P(HIGH) > 0.9.
  - +~2% instruction/decision-format text.
  - Decontaminated against the sealed holdout and every test set.
- **Code changes:** `train.py --model-config`; branching decay from a checkpoint; skip non-finite steps; parity check
  at each eval; shard-wise streaming in `build_tokens.py` with raw-file deletion.
- **Hyperparameters:**
  - LR sweep 3e-4 / 4.5e-4 / 6e-4 (3 × 20M tokens, alongside data building).
  - ~0.5M-token batches, 300 warmup steps, 20% decay.
  - Balancing loss 0.01, bias step 0.01.
- **Gates:**
  - At 1B tokens: val loss ≤2.7 (126M reached 2.96).
  - At 2.5B tokens: decayed side branch + quick fine-tune. Stop and switch to the Bielik-1.5B route if pl_real and the
    decomposed deadline task gain < 3 points over 126M.

## Phase C — fine-tuning, calibration, final evaluation (~1 d)

- **Recipe:** joint recipe with data v6 + gated distillation; LR 1e-4–2e-4.
- **Selection:** by calibration accuracy (ties: coverage at 1%); per-type × per-language temperatures fitted on the
  served (order-averaged) predictor.
- **Final scoring:** once on the sealed holdout and the human-checked set; `compare_basal.py` vs basal-1.5B/4.5B on the
  same items, with confidence intervals.
- **Replacement rule:** M replaces v4 only if the Polish test and pl_real don't drop, and coverage at 1% holds at
  ≤1.5% observed error.

## Targets for M

| Set | v4 | Target |
|---|---:|---:|
| Decomposed deadline primitives | 0.37–0.41 (composite) | ≥0.90 |
| Polish test (data v6) | 0.56 | ≥0.62 |
| pl_real | 0.79 | ≥0.85 |
| basal examples (44) | 0.34 | ≥0.50 |
| tasksource / kaivoss | 0.45 / 0.40–0.47 | ≥0.50 / ≥0.50 |
| Coverage at 1% on the holdout | — | ≥20% at ≤1.5% observed error |

## Open decisions

1. Approve Phase A only, then decide on B after Gate A (recommended), or commit to the whole plan.
2. **Disk:** ~36 GiB free. Permission to delete the OLMoE cache (~14 GB), Bielik-11B (~14 GB) and processed raw
   downloads (~19 GB)?
3. Human review: 100 spot-check items (~20 min), then ~300 more.
4. Optional parallel track: Bielik-1.5B-base comparison (~1 d after Phase A).

## Risks

- Knowledge stays below basal (5B vs 292B tokens).
- Thermal throttling and 2 weeks of a busy Mac (training resumes from checkpoints).
- MoE serving keeps the router in fp32 (determinism over speed).
- The disk limit.
