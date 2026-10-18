# Where a Jev-like decider pays off — research notes (Oct 2026)

A Jev-like (System One) model reads a **state** and answers **typed questions** (choice / yes-no / score) with
calibrated probabilities in one forward pass. Everything below is judged against what that buys:

- **Cheap per decision.** Local, ~5–15 ms on a GPU for basal-1.5B/4.5B. Several questions about the same state cost
  about one pass (shared prefix).
- **Calibrated.** A threshold means something, so a decision can be made automatically or escalated
  (basal-4.5B: 58.6% of test decisions automated at 1.2% error).
- **Closed answers.** It can't produce an option you didn't list, but it can't generate arguments, diffs or prose either.
- **Known weak spots (basal report):** arithmetic and exact thresholds, composite rules, long states (latency flat
  only to ~1k tokens). Compute numbers in code, and split composite questions into simple ones.

Rule of thumb from every source below: the decider earns its place where a **frontier-model call** or a **human
approval** would otherwise be spent on a closed question.

---

## 1. Routing add-on for coding harnesses (choose the model in flight)

### Evidence that routing pays

| Source | Setup | Result |
|---|---|---|
| [RouteLLM](https://www.lmsys.org/blog/2024-07-01-routellm/) (LMSYS 2024) | strong/weak pair, routers trained on Arena preferences | 95% of GPT-4 quality at **−85% cost on MT-Bench**, −45% MMLU, −35% GSM8K; routers transfer to new model pairs without retraining |
| [Hybrid LLM](https://arxiv.org/abs/2404.14618) | difficulty router, tunable quality level | up to 40% fewer large-model calls with no quality drop |
| [FrugalGPT](https://arxiv.org/abs/2305.05176) | cascade + answer scorer | matches GPT-4 at up to −98% cost |
| [AgentRouter](https://arxiv.org/abs/2609.22951) (Sep 2026) | **per-step** routing in agent trajectories, **12M-param classifier**, 5 features, <5 ms | **−72% cost, 97.3% of frontier quality**; RouteLLM/FrugalGPT applied per step: only −31% / −44% |
| [Applied Compute](https://www.appliedcompute.com/research/training-an-agentic-router) (Jun 2026) | small router across Nemotron 3 Ultra / GPT-5.5 / Opus 4.7 on SWE-bench Verified | ~76% pass ≈ GPT-5.5 quality at −25% cost; **frontier models used as routers did worse than the trained small router**; oracle 0.890 vs best single 0.834 |
| [LangChain × Switchyard](https://www.langchain.com/blog/switchyard-agent-routing-benchmark) (Aug 2026) | escalation routing, 145 agent tasks | −74% cost, −6 pts accuracy; 7% of calls (the frontier ones) were 68% of the bill; **the LLM judge itself was 21.2% of routed spend** |
| [GPT-5 system card](https://openai.com/index/gpt-5-system-card/) | production real-time router (fast vs thinking) | routes on conversation type, complexity, tool needs, explicit intent; trained on user switches and correctness |
| [LangChain `ModelRouterMiddleware`](https://www.langchain.com/blog/building-a-harness-with-jev) (Sep 2026) | Jev chooses the model from the latest user message | shipped (experimental); picks once per run |

### What breaks naive "in flight" switching

1. **The prompt cache decides where a switch may happen.** Each model has its own cache, so switching mid-session
   re-reads the whole conversation uncached ([Claude Code docs](https://code.claude.com/docs/en/prompt-caching#switching-models)).
   Break-even on Anthropic's Sep 2026 prices: ~27 requests (Opus 5 → Sonnet 5 and back) before a switch pays off
   (arXiv 2609.28919, [summarised here](https://www.agentpatterns.ai/patterns/agent-design/cache-safe-routing-boundaries/)).
   Copilot auto-mode routes "along natural cache boundaries" for this reason. Places where a switch is safe:
   **session start, subagent launch, and a fresh side lane**. The knob you *can* turn per turn is
   **reasoning effort**: OpenAI says effort changes don't break the cache.
2. **The task description alone has a Bayes-error floor.** A near-identical issue can hide a typo or a
   multi-module refactor. [SWE-Router](https://arxiv.org/abs/2607.00053) lets the cheap model run K=3–4 turns, then
   reads the partial trajectory: Route-AUC 0.627 → 0.780 on SWE-bench Verified.
3. **Handoff tax.** When escalating, give the strong model the repository state plus a fresh brief, *not* the cheap
   model's transcript. Quality recovered goes from 47% to 64% (Claude) and 36% to 84% (GPT), and passing the raw
   transcript cost more than starting on the strong model (arXiv 2608.24358,
   [summary](https://www.agentpatterns.ai/context-engineering/handoff-tax-model-switch-context/)). On easy/medium
   tasks no escalation paid off.
4. **Break-even.** `minimum offload = judge cost / (expensive − cheap)`. Routing can't pay when the two models are
   close in price **unless the judge and cheap tier are local**, which is exactly a local Jev-like model's position.
5. **Many routers don't beat simple baselines** (LLMRouterBench, 400K instances, cited by the break-even page above).
   Measure on your own traffic.

### How a Jev-like decider fits

- **One pass, several questions about the same state:** `tier` (Choice: fast / balanced / frontier),
  `effort` (Score: low…high), `needs_tools`, `high_risk` (Noul). Same shape as
  [jev-usecases/model_routing.py](https://github.com/kenhuangus/jev-usecases/blob/main/src/jev_usecases/use_cases/model_routing.py).
- **Calibration does the work.** Act automatically above a threshold. Below it, default to the frontier model (cost
  of a wrong downgrade > cost of an unneeded upgrade). Set thresholds per action class from labelled traffic.
- **A local judge removes the 21% "judge tax"** found in the Switchyard benchmark and runs on every turn without a
  network round-trip.

### Proposed design for a coding-harness add-on

| Decision point | Question(s) | Cache-safe? |
|---|---|---|
| Session start | tier + effort from the first user message and repo summary | yes |
| Subagent launch | tier for the subagent's brief (explore/edit/review) | yes (fresh conversation) |
| Every turn | **effort only** (raise/lower), `goal_complete`, `blocked` | yes for effort; model stays fixed |
| After K=3–4 cheap turns | `escalate?` (Noul) on trajectory signals: failing tests, repeated edits to the same file, error loops, diff spread | switch = one cold write; hand over repo state + fresh brief |

- **State must be compact.** Basal latency is flat only to ~1k tokens, so engineered features + a short summary,
  not the transcript (AgentRouter uses 5 features).
- **Ready-made labels:** CodeRouterBench (~10K tasks, verified scores from 8 LLMs,
  [Agent-as-a-Router](https://arxiv.org/abs/2606.22902)), the SWE-Router multi-LLM trajectory dataset, and oracle
  labels "cheapest model that passes" (Applied Compute recipe; binary reward, because partial credit collapsed onto
  the strongest model).

---

## 2. Tool calling — saving tokens

Five distinct mechanisms, from largest saving to smallest:

| Mechanism | Evidence | Decider question | Caveat |
|---|---|---|---|
| **Which tool definitions to load** | [Anthropic Tool Search](https://www.anthropic.com/engineering/advanced-tool-use): 58 MCP tools = 55K tokens; on-demand **−85% tokens**, Opus 4 accuracy 49% → 74%. [RAG-MCP](https://arxiv.org/abs/2505.03275): >50% fewer prompt tokens, selection accuracy 13.6% → 43.1%. [TinyAgent ToolRAG](https://bair.berkeley.edu/blog/2024/05/29/tiny-agent/): multi-label classifier (DeBERTa-small), **recall 0.998**, prompt 2762 → 1397 tokens, success *up* | one Noul per tool (or per MCP server) over the request: "this tool is needed" | Tools sit in the cached prefix. Choose at session/subagent start, or append (like `defer_loading`), never remove mid-session. A classifier beats embedding search because auxiliary tools (e.g. `get_email` for "create invite") aren't similar to the query |
| **Prune tool output before it enters context** | [SWE-Pruner](https://arxiv.org/abs/2601.16746): −23–54% tokens on agent tasks; [SWE-Pruner Pro](https://arxiv.org/abs/2607.18213): up to −39% tokens and +3.8 pts on SWE-bench Verified | keep/prune per line or block given the current subgoal | Many questions over one state, the multi-select/pointer readout we already have. Long outputs exceed the ~1k-token sweet spot, so chunk them |
| **Skip the LLM for closed-catalog calls** | [jev-usecases/function_calling.py](https://github.com/kenhuangus/jev-usecases/blob/main/src/jev_usecases/use_cases/function_calling.py): Choice over functions + `none`, Choice per enum argument, `should_call` Noul | function + enumerable arguments | Only enumerable arguments; free strings (paths, code) still need a generator. Good fit for harness actions like "run tests / lint / git status / open the failing file from this list" |
| **Whether to call a tool at all** | [When2Call](https://arxiv.org/abs/2504.18851) (NVIDIA): call / ask a follow-up / can't answer with the given tools. SOTA tool-callers leave a lot of room; the multiple-choice format suits preference training | Choice: call / ask / cannot / answer-directly | Saves a round trip and a wrong call; training set released |
| **Speculative next call (latency, not tokens)** | [Speculative tool calls](https://arxiv.org/abs/2512.15834); [Speculate While You Reason](https://arxiv.org/abs/2607.25816): next-call Hit@1 44 → 61 (4B) | Choice over the likely next read-only tool + argument from a candidate list | Read-only tools only; on a miss, discard the result |

**Permission gating** (Claude Code auto mode) is the same pattern applied to human time instead of tokens.
[Anthropic's stage 1](https://www.anthropic.com/engineering/claude-code-auto-mode) is a **single-token yes/no**
filter (8.5% false positives, 6.6% false negatives on real overeager actions). Stage-2 chain of thought runs only on
flagged calls (full pipeline: 0.4% false positives, 17% false negatives). Users approve 93% of prompts manually.
LangChain ships `AutoModeMiddleware` with Jev for this ([post](https://www.langchain.com/blog/building-a-harness-with-jev)).
A local calibrated decider is a direct stage-1 replacement. Design lessons from Anthropic: show it **user messages +
tool calls only** (strip the agent's prose and tool outputs, which defends against injection and against the agent
talking the gate round); **deny-and-continue** rather than halting; escalate to a human after 3 consecutive / 20
total denials.

---

## 2a. Restricted-data / disclosure policy hook for coding harnesses (user idea)

A hook checks whether data is restricted under a given policy (GDPR/RODO, client NDA, company data
classification) before it flows somewhere it shouldn't, then allows, redacts, asks the user, or blocks. "Somewhere"
means **any external system**, not only the AI provider: git remotes, PR/issue trackers, HTTP APIs, package
registries, search engines, SaaS integrations.

### Three tiers of restricted data

| Tier | Example | Detectable by | Who decides |
|---|---|---|---|
| 1. Explicit identifiers and secrets | PESEL, IBAN, card, email, API key, private key | regex + checksums, secret scanners | deterministic; **the easy part** |
| 2. Combinations of non-identifying facts (quasi-identifiers / mosaic) | "the only senior QA in the Gdańsk office, on sick leave since March" in a PR comment; client codename + deal size + date in a commit message; internal hostnames + versions in a public issue | nothing pattern-based; each fact alone is harmless | contextual judgement |
| 3. Inappropriate flow (contextual integrity) | the same text is fine in the internal repo and a breach in a public GitHub issue, a web-search query or a published package | depends on destination + policy, not on the text | contextual judgement |

Evidence that tiers 2–3 are real and that the acting model isn't a reliable guard:
- Combination identifies people: 99.98% of Americans are re-identifiable from 15 demographic attributes; date of
  birth + location + marital status + gender alone single out 78.7% of a 3M population
  ([Rocher et al. 2019, Nature Communications](https://www.nature.com/articles/s41467-019-10933-3)). GDPR treats
  such pseudonymous data as personal data.
- Agents leak contextual private information: GPT-4 and Llama-3-70B leak in 25.7% / 38.7% of agent actions **even
  with privacy-enhancing instructions** ([PrivacyLens](https://arxiv.org/abs/2409.00138)). GPT-4 reveals
  private information humans wouldn't in 39% of cases ([ConfAIde](https://arxiv.org/abs/2310.17884)).
- PrivacyLens also finds models answer *probing* questions about norms better than they *act* on them. That argues
  for a **separate judge at the sink** rather than instructing the acting agent.
- Limiting what the agent can see works: [AirGapAgent](https://arxiv.org/abs/2405.05175) holds 97% data protection
  under a context-hijacking attack that drops a plain Gemini Ultra agent from 94% to 45%.

### Where data enters and leaves (measured on the local harness logs, 2026-10-12)

Regex/checksum and command-pattern scans; counts only, no values stored. Codex user prompts weren't parsed.

| Channel | Items scanned | Finding |
|---|---:|---|
| User prompts (omp/pi) | 2,485 | 1 tier-1 hit (API key) |
| Tool outputs, inbound (omp/pi/Codex) | 133,197 | tier-1 hits: email 1,082 · checksum-valid PESEL 363 · Polish phone 163 · Luhn-valid card 108 · API key 80 · NIP 36 · IBAN PL 7 · private key 1 |
| Outbound tool calls (all harnesses) | 206,146 | git commit 2,585 · git push 2,129 · `gh` PR/issue/API writes 2,054 · HTTP uploads 488 · web-search queries 258 · publish 26 · scp/ssh 5 → **~7.5k sink events, ~3.6% of calls** |

- **Inbound:** restricted data enters through file reads, DB queries and logs. Many tier-1 hits are probably test
  fixtures; telling them from real data is a judgement call.
- **Outbound:** this is where tiers 2–3 matter, and where leaks reach systems other than the AI provider. Outbound
  payloads (commit message, PR body, issue comment, request body, search query) are **short**, so they fit the
  decider's ≤1k-token state well, unlike long tool outputs.

### Hook points (Claude Code hooks reference; Codex has the same five core events)

| Hook | Can do | Role |
|---|---|---|
| `UserPromptSubmit` | block with a reason, add context; **cannot rewrite the prompt** | block-or-allow gate on the prompt |
| `PreToolUse` | deny, or rewrite tool input (`updatedInput`) | **the outbound disclosure gate**: commits, pushes, `gh` writes, HTTP uploads, publishes, search queries, external MCP tools |
| `PostToolUse` | **`updatedToolOutput` replaces the result before the model sees it** | redact inbound tool output (tier 1 + fixture vs real) |
| Managed settings + `allowManagedHooksOnly` | organisation-enforced hooks users can't disable | how a company would deploy it |

Caveats from the docs:
- `PostToolUse` runs after the tool, so side effects already happened, and **OpenTelemetry/analytics capture the
  original output** before the hook runs.
- A hook that times out fails open unless it is set to `onFailure: "block"`. Agent SDK prompt callbacks fail
  closed.

### Design

1. **Tier 1 is deterministic and authoritative.** Regex + checksums (PESEL, NIP, REGON, IBAN mod-97, Luhn),
   secret patterns, entropy. Credentials are always redacted or blocked, with no model involved.
2. **Provenance (taint) tracking, deterministic.** Mark tool results that came from policy-restricted sources
   (paths, DB tables, client repos, `.env`). Fingerprint them with hashed n-grams, and on every outbound call
   check the payload for overlap. This catches verbatim copies (the "exact data match" technique of
   data-loss-prevention tools) and supplies the decider with "this payload draws on restricted source X".
3. **Typed decider on outbound payloads** (tiers 2–3). The state is short: policy text, payload, destination
   (internal remote / client system / public), provenance summary, task description. One pass answers:
   - Noul `singles_out_person`: the payload, alone or combined with obvious context, identifies or singles out a
     person.
   - Noul `confidential_business`: the payload reveals client-confidential or internal-only facts (codenames,
     deals, incidents, infrastructure).
   - Noul per policy clause.
   - Choice `destination_ok`: this flow fits the policy for this destination (contextual integrity).
   - Choice `action`: allow / rewrite (ask the agent to generalise the text) / ask the user / block.
4. **Inbound decider (tier 1 context).** Same questions on a candidate span from step 1: real vs fixture vs the
   user's own data → redact or allow. Redaction uses stable placeholders (`<PESEL_1>`) so the agent can still
   reason about joins.
5. **Calibrated bands per destination.** A public destination needs high confidence to allow; an internal one can
   allow at lower confidence. Uncertain → *deny-and-continue* with the reason, so the agent rewrites the commit
   or PR text (Anthropic's auto-mode pattern), and only after repeated denials ask the user.
6. **Shared with the permission gate.** Anthropic's auto-mode block rules already include "sending internal data
   externally". One local decider, one `PreToolUse` hook, two question sets (risk/authorization and disclosure).

### Why this fits a *local* Jev-like model particularly well

- **It must be local.** Sending suspected restricted data to a hosted classifier (Jev's API) is itself the leak;
  LangChain's TypeSafe docs warn against putting secrets in the state. basal/basal-scratch run on the user's machine.
- **The policy goes in the state.** "Rules stated in the state" is basal's strongest family (rule families 0.921 vs
  Jev 0.635 in the basal report). A company policy or NDA list is just another rule text.
- **Polish is the advantage.** PESEL/NIP/REGON/dowód formats, Polish names and addresses, RODO wording, Polish
  commit/PR text. basal leads Jev by ~10 points on Polish decisions, and no English-first guard covers this well
  [INFERENCE for the last claim].
- **Cheap.** Outbound sinks are ~3.6% of tool calls with short payloads; inbound checks run only on prefilter hits
  (~1% of outputs). basal-1.5B takes ~5 ms per decision on an H100.

### Risks

- **Tier-2/3 recall is the hard part.** Frontier models fail at it as actors (26–57% leakage). A judge only has to
  classify a short payload, which is easier, but whether a 1.5B–4.5B (let alone 126M) decider gets there is
  unmeasured. Tier 1 and provenance must stay deterministic so recall there doesn't depend on the model.
- Mosaic leaks spread over several payloads (one fact per commit) are invisible to a per-call check. A
  per-session disclosure ledger (what was already sent to each destination) belongs in the state.
- Obfuscated data (base64, split across lines, images) evades every layer.
- Over-blocking breaks the agent. Deny-and-continue with a reason (rewrite the text) costs one retry instead of a
  stalled session.
- Telemetry and transcripts on disk keep the original data (the hook only changes what the model sees). The
  local logs above contain this data today.

**Rating: ★★★★½.** Tier 1 alone is easy and needs no model. The value is tiers 2–3 at the outbound gate:
evidence shows acting models leak there, the harnesses have the hook point, the payloads are short, the model has
to be local, the policy goes in the state, and the call volume is tiny. Main work: labelled tier-2/3 data. Sources:
PrivacyLens seeds/trajectories (data subject, sender, recipient, data type map directly to a typed state);
synthetic Polish twins built like basal v2 (the same commit/PR text with and without the identifying combination,
kept only when two verifiers agree); and the ~4.6k commit messages and PR/issue bodies plus 258 search queries in
the local logs, labelled locally and never exported.

---

## 3. Other places it fits (ranked by fit for us)

1. **Agent-loop control.** Continue / retry / ask the user / stop-success / stop-failure, `goal_complete`, `blocked`,
   plus "which skill to load". The skill choice is a typed Choice that avoids putting every skill in context.
   ([jev-usecases/agent_harness.py](https://github.com/kenhuangus/jev-usecases/blob/main/src/jev_usecases/use_cases/agent_harness.py)).
   Saves wasted turns, and complements routing.
2. **Prompt-injection probe on tool results.** Anthropic's input layer: a warning is added when a result looks
   like a hijack. A Noul per tool result. Baseline to beat: Meta Prompt Guard 2 (86M/22M DeBERTa). Adversarial
   inputs (e.g. GCG suffixes) flip small classifiers, so pair the probe with the action gate; it shouldn't be the
   only defence.
3. **Retrieval decisions.** Reranking: [Qwen3-Reranker](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) is
   literally a yes/no-logit readout, the same mechanism as our Noul. Whether retrieval is needed / which strategy:
   [Adaptive-RAG](https://arxiv.org/abs/2403.14403) classifies query complexity into 3 levels to pick
   no / single / multi-step retrieval, which is the same problem as model routing.
4. **Memory operations.** [Mem0](https://arxiv.org/abs/2504.19413) decides ADD / UPDATE / DELETE / NOOP per extracted
   fact with an LLM call. That is a typed Choice. Mem0 reports >90% token savings vs full context (that saving comes
   from the memory architecture; the decider makes each update cheap).
5. **Semantic-cache verification.** [vCache](https://arxiv.org/abs/2502.03771): whether a cached answer is valid for
   a new prompt. A Noul over (new prompt, cached prompt, cached answer) replaces a fixed similarity threshold.
6. **Output checks.** Claim-vs-source support, "does the draft follow the decision", CI semantic lints
   (jev-usecases `citation_check`, `security_guarded_assistant`, `semantic_linting`).
7. **Data curation.** Our own text-quality classifier (QUALITY_CLASSIFIER.md) is the same shape. Pretraining-data
   filtering at corpus scale is where per-decision cost matters most.
8. **Basal's home turf.** Polish business decisions (ticket triage, document routing, deadlines decomposed into
   primitives, moderation). Basal leads Jev by 10+ points here; it doesn't lead on English coding traffic.

---

## 4. What this means for basal / basal-scratch

- **Language mismatch.** Coding-harness traffic is English + code; basal is a Polish specialist. On English it ties
  Jev 1.13 (0.741 vs 0.736) and is weaker on general English. Routing/tool decisions need English+code decision
  data (the datasets above), not more Polish.
- **Size is not the bottleneck for routing.** AgentRouter is 12M parameters on 5 features.
  [INFERENCE] The 126M scratch model is plausible as a *task-specific* router/tool selector trained on
  CodeRouterBench / When2Call / ToolRAG-style labels, but not as a general Jev replacement. Long-trajectory
  understanding would need the 1.5B/4.5B.
- **State budget.** Keep states ≤1k tokens: feature summary + last error + test status + brief. Never the raw
  transcript (latency, and the handoff findings).
- **Metric.** Reuse basal's own: coverage at a fixed error rate, plus $ saved against always-frontier, checked with
  the break-even formula and against "cheap model alone" (in the Switchyard benchmark the cheap model alone wasn't
  beaten by routing).

## 5. Suggested first experiments (not started)

1. **Tool-definition selection** (cheapest to validate). Multi-label Noul over an MCP catalog; offline metric =
   recall@selected vs tokens saved; data from BFCL/ToolBench-style queries. Expected: TinyAgent-like recall ≥0.99
   at ~2× fewer prompt tokens.
2. **Session-start + subagent routing** on CodeRouterBench: tier + effort, threshold for 1% wrong-downgrade rate;
   report coverage and cost against the oracle and single-model baselines.
3. **Trajectory escalation** (SWE-Router style) using the released trajectories, with the escalation handoff
   carrying repo state + a fresh brief.
4. **Disclosure gate (outbound first).** Build ~1–2k tier-2/3 items: PrivacyLens-derived states, synthetic Polish
   twins, and locally labelled commit/PR/issue/search payloads from the logs. Train/evaluate the
   `singles_out_person` / `confidential_business` / `destination_ok` / `action` questions. Ship as a `PreToolUse`
   hook on outbound sinks (plus `PostToolUse` tier-1 redaction) for Claude Code/Codex and an omp extension.
   Metric: recall of restricted disclosures at a fixed false-block rate, reported separately per tier and per
   destination (internal / client / public).
