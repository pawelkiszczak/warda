# Findings so far (as of 2026-10-18)

Results that live in other documents are only linked. Findings that existed only in working sessions are written out
here.

| Topic | Where |
|---|---|
| Pretraining a 126M MoE from scratch, decision fine-tuning, distillation, comparison with basal-1.0 | `pretrain/README.md` |
| Revised pretraining plan for the scratch model | `pretrain/PLAN.md` |
| Notes on the basal-1.0 technical report | `pretrain/BASAL_REPORT_NOTES.md` |
| Text-quality classifier design and labelling tool | `pretrain/QUALITY_CLASSIFIER.md`, `pretrain/quality/` |
| Where a Jev-like decider pays off (routing, tool calls, data guard) | `pretrain/USE_CASES_RESEARCH.md` |
| Synthetic PII / disclosure dataset (generator, verification, statistics) | `pretrain/README.md`, section "Harness decider" |
| Team plan (Polish) | `pretrain/HARNESS_DECIDER_PLAN.md` |

## 1. Ratings of the approaches tried or considered

Scale: one to five stars, combining strength of evidence, payoff and fit with what we have.

| Approach | Rating | Why |
|---|---|---|
| fp32 router + balance loss + selection bias for the MoE | ★★★★★ | The selection bias alone collapsed routing onto 4 of 32 experts; with both, load stays balanced |
| Pretraining a small MoE from scratch on one Mac | ★★★ as a research platform, ★★ as a product | Helps every decision metric. Arithmetic, dates and thresholds stay at chance |
| Jev-style public decision data, trained jointly rather than in stages | ★★★★ | Staged training overwrote stage 1. Joint training matches basal-4.5B on English Jev-style sets |
| Distillation from basal-1.5B | ★★★½ | Large gains on real Polish text. Part of the gain is imitation, because the eval set is labelled by the same family |
| Calibration on real text, per question type and language | ★★★★ | Thresholds hold on real text; they break on template-shifted synthetic data |
| **Local data guard (PII / disclosure) at the outbound tool-call gate** | ★★★★½ | Acting models leak; the payloads are short; the model must be local; the policy goes in the state |
| First-stage permission gate | ★★★★★ | Anthropic's auto-mode stage 1 is a single yes/no token; it shares a hook with the data guard |
| Routing models in coding harnesses | ★★★★ refined, ★★ as "switch on any turn" | Switching mid-session throws away the prompt cache. Route at session start and subagent launch; change only reasoning effort per turn |
| Tool-output pruning / tool selection | ★★★★ in general, ★★ with few tools loaded | Large token savings only with large MCP catalogues |
| Agent-loop control (continue / retry / ask / stop) | ★★★ | Clear fit, only weak labels |

## 2. Market and viability of the data guard

- **Secrets are already covered.** GitGuardian ships AI hooks for Claude Code, Cursor, Codex, Copilot CLI and others
  (Oct 2026). Reuse it for tier 1; don't rebuild it.
- **Integration point.** Anthropic inference hooks (Claude Enterprise, Aug 2026) send every prompt and tool response to
  the customer's own security server for a verdict, over an open webhook protocol with shadow mode. Large DLP vendors
  plug in there.
- **Context-aware classification is contested.** Cyberhaven combines data lineage with AI classification.
- **Remaining gaps:**
  - verdicts computed entirely on the machine;
  - Polish / CEE policy language (RODO, banking secrecy, trade secrets, legal privilege);
  - the policy given as plain text, with calibrated thresholds;
  - keeping client data apart in software houses.
- **Business models:**
  - local engine + paid onboarding (policy set-up, calibration on the client's traffic) ★★★★;
  - open model + enterprise tier ★★★½;
  - services only ★★★ to start;
  - OEM to DLP vendors ★★½;
  - hosted API ★, because it defeats the purpose.
- **Risks:**
  - quality on the hard tiers (combinations of details, wrong destination) is unproven at small size;
  - liability: sell it as risk reduction plus audit, never as a guarantee;
  - slow security sales cycles;
  - platforms building the same feature in.
- **Evidence that the problem is real:**
  - GPT-4 and Llama-3-70B leak in 26–39% of agent actions even with privacy instructions (PrivacyLens);
  - 15 demographic attributes re-identify 99.98% of Americans (Rocher et al. 2019).

## 3. Deployment on Apple hardware

- **Core ML / Core AI can run the decider; training stays in MLX or PyTorch.** One decision is a single forward pass
  over a short input, which is the easy case for Core ML.
- **Neural Engine vs GPU** (public benchmark, Qwen3-4B FP16 on an M5 Pro):
  - the GPU is 3.6× faster on a 1K-token input;
  - the Neural Engine uses 0.68–0.81× the GPU's energy for 500–2K-token inputs.

  The Neural Engine suits an always-on background daemon; MLX on the GPU is the faster default.
- **Neural Engine defects at the time:**
  - the 4-bit palettized preset silently falls back to the GPU;
  - grouped 4-bit returns wrong values;
  - a quantization multiply picks up the wrong scale.

  Use FP16 or W8A8, check agreement with the reference model, and refit thresholds per backend.
- **Apple Foundation Models adapters are a dead end.** The toolkit's last release does not support OS 27, and we found
  no way to get calibrated probabilities from it.
- **Cross-platform runtimes:** GGUF / llama.cpp or ONNX for Linux and Windows.

## 4. Local coding-harness logs as a data source

- **Size:** an inventory of one developer's local logs (omp, Codex, opencode, Claude Code, pi) held ~175k model calls
  and ~195k tool calls.
- **What they could provide:**
  - permission-gate teacher labels (Codex auto-review verdicts, 9,655, of which only 55 are denies);
  - tool-use labels;
  - loop-control signals;
  - weak routing signals (user model switches). There are no counterfactual labels showing whether another model would
    have passed.
- **Real data in them:** a scan of tool outputs found checksum-valid PESELs in 363 outputs, emails in 1,082 and API
  keys in 80. Outbound sinks (commits, pushes, PR/issue writes, HTTP uploads, web searches) were ~3.6% of tool calls,
  with short payloads.
- **Decision: the logs are not used.** They contain real personal data and work code; everything in this repository
  is synthetic.

## 5. Name

**Warda.** From Old English *weard*, "guardian". It matches the function (a gatekeeper deciding what may pass, not a
masker), and Polish readers hear *warta*, a sentry watch.
- **Known collision:** Wanda, a pruning method listed in our own tooling.
- **Other meanings:** Warda is also a given name, Arabic for "rose".
