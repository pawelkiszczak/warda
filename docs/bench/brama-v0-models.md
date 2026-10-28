# Brama v0: decider list (2026-10-25)

The deciders run on the Brama v0 examples split for the second pilot round
([`reports/brama-v0-pilot-2026-10-25.md`](reports/brama-v0-pilot-2026-10-25.md)). The focus is **System-1 decision
models**: models that take a state and typed questions and return a probability per option without generating text
(`POST /v1/systemone` or an equivalent Python call). Two Bielik instruct models are kept as general-LLM reference
rows.

Admission rule, set by the project owner on 2026-10-25: every open-weight decision model that fits in **16 GB as
GGUF Q8_0 or FP8** (about ≤ 14 B parameters) is in. The pilot card is an RTX 3090 (24 GB, about 21 GB free with the
display attached, no FP8 kernels on sm86), so each model runs in bf16 when it fits that card and otherwise in
GGUF Q8_0 or 8-bit (bitsandbytes LLM.int8). The "Run as" column records which.

All revisions are the Hugging Face commit that was run; each result's `.meta.json` repeats it with the server
command and environment.

## Where the candidates come from

- **Tacit v0.2** (Polish typed decisions; basal and API models only), **Werdykt** (PL+EN, basal's own results).
- **JevBench v1.7.2** open-weight board (25.10.2026) and the Artificial Analysis Decision Index.
- **PIRB "Decision models"** board (Sławomir Dadas, 22.10.2026): Polish retrieval relevance (NDCG@10 over 41 tasks),
  which tests reading Polish text, not choosing a policy action. Rerankers wrapped as "-decide" (bge-reranker,
  KaLM, polish-reranker-roberta, PolDense) are left out: they score one passage, they cannot pick one of four
  actions.

Scores below are as published by the authors or the board on the dates above. None of the non-basal models has a
published Polish typed-decision score.

## Run

| Decider | Family / author | Params | Base | Licence | Revision | Run as | Interface | Published score |
|---|---|---|---|---|---|---|---|---|
| `basal-2.0-mini` | basal (Remek Kinas) | 1.6 B | Bielik-1.5B-v3 | Apache-2.0 | `cb81b32` | bf16 | basal-serve 2.4.1 `--mode eager` | Tacit PL 83.3, PIRB 60.9 |
| `basal-2.0-4.5B` | basal | 4.8 B | Bielik-4.5B-v3.0 | Apache-2.0 | `e5ba914` | bf16 | basal-serve, eager, `--template-prefix off` (as its card says) | Werdykt 72.9, Tacit PL 87.1, PIRB 65.0 |
| `basal-2.0-max` | basal | 11.2 B | Bielik-11B-v3 | Apache-2.0 | `2fffc5c`, GGUF `8af9c1e` | GGUF Q8_0 (author's) | basal-serve `--mode gguf`¹ | Werdykt 78.4, Tacit PL 91.4, PIRB 68.4 |
| `basal-omni-pico` | basal | 0.75 B | Qwen3.5-0.8B | Apache-2.0 | `a959cef` | bf16 | basal-serve, eager | Tacit PL 78.4 |
| `basal-omni-1.0-mini` | basal | 7.9 B | Gemma 4 E4B | Apache-2.0 | `d087a7b` | bf16 | basal-serve, eager | Werdykt 76.9, Tacit PL 90.3, PIRB 65.5 |
| `basal-omni-1.0-max` | basal | 12.0 B | Gemma 4 12B | Apache-2.0 | `3278a02`, GGUF `3c9c045` | GGUF Q8_0 (author's) | basal-serve `--mode gguf`¹ | PIRB 68.4 |
| `basal-omni-1.1-max` | basal | 12.0 B | Gemma 4 12B | Apache-2.0 | `a3af675` | GGUF Q8_0, converted here² | basal-serve `--mode gguf` | Werdykt 82.3, Tacit PL 94.8 |
| `d3-lite` | vLLM Semantic Router Decision 3.0 | 0.85 B | Qwen3.5-0.8B | Apache-2.0 | `03560c2` | bf16 | `AutoModel.system_one` (shim) | — |
| `d3-nano` | d3 | 2.2 B | Qwen3.5-2B | Apache-2.0 | `462efc3` | bf16 | `AutoModel.system_one` (shim) | — |
| `d3-mini` | d3 | 4.5 B | Qwen3.5-4B | Apache-2.0 | `bd0090d` | bf16 | `AutoModel.system_one` (shim) | PIRB 68.4 |
| `d3-flash` | d3 | 8.4 B | Qwen3.5-9B | Apache-2.0 | `13dc1cc` | bf16 | `AutoModel.system_one` (shim) | PIRB 69.7 (best open ≤ 9 B) |
| `pplx-decider-flash-v1.2` | Perplexity | 4.5 B | Qwen3.5-4B | Apache-2.0 | `9ff7cf9` | bf16 | `pplx_decider.Decider` (shim) | PIRB 67.3 |
| `clef-flash` | Cloudflare | 9.4 B | Qwen3.5-9B | Apache-2.0 | `f0b7d3c` | bf16 | `joint_schema_model.systemone` (shim) | JevBench 63.8 |
| `decider-12b` | Mapika (decider-ai) | 12.0 B | Gemma 4 12B | Apache-2.0 | `64d8d3f` | GGUF Q8_0, converted here² | `decider.infer.Decider` GGUF engine (shim) | JevBench 71.3 |
| `Jev-Omni` | akhilaaa3 | 12.0 B | Gemma 4 12B | Apache-2.0 | `fee89b0` | LLM.int8 | `jev_omni.JevOmni` (shim), env as its `requirements.txt` (transformers 5.17.0) | — |
| `Winnow-12B` | EldanRing | 12 B | Gemma 4 12B | Apache-2.0 | `0b5b7f9` | GGUF Q8_0 (author's) | winnow-inference `/v1/systemone`, reasoning off, MTP off | JevBench 71.2 |
| `h2o-lightning-4b` | H2O.ai | 4.7 B | Qwen3.5-4B | Apache-2.0 | `d428750` | bf16 | vLLM 0.30.0 + h2oai/vllm `6bc6d5a` patch, its `serve.sh` | JevBench 75.0 (best open ≤ 8 B) |
| `torchcast-decision-12b` | torchcast-ai | 12.0 B | Gemma 4 12B | **CC-BY-NC-4.0** | `49107b5` | FP8 weights (vLLM online FP8, Marlin W8A16)³ | vLLM 0.30.0 + `torchcast_shim.py` (v1.0.0) | — |
| `hopper` | HopitAI | 4 B (LoRA) | Qwen3.5-4B `851bf6e` | research-and-demo | `fa02eff` | bf16 | `hopper-serve` 1.1.1, `--allow-slow-kernels`⁴ | JevBench 67.5 |
| `Bespoke-Nimble-9B-v3` | Bespoke Labs | 9 B (LoRA) | Qwen3.5-9B `c202236` | **CC-BY-NC-4.0** | `8e927b9` | bf16 | `NimbleEngine` from the decision-index dataset `654b124` (shim) | — |
| `SPX-CD-Omni` | SurdAI | 12 B (LoRA) | Gemma 4 12B `707f0a3` | Apache-2.0 | `06a786a` | LLM.int8 base | `decision.decide` from the repo (shim) | — |
| `GLiNER2.5-multi-Decide` | Fastino | 0.29 B | GLiNER2.5-multi | Apache-2.0 | `e173bca` | fp32 | `gliner2` (in process) | — |
| `GLiNER2.5-Decide` | Fastino | 0.49 B | GLiNER2-large | Apache-2.0 | `9d1bfb8` | fp32 | `gliner2` | — |
| `GLiNER2.5-Decide-1B` | Fastino | 1.2 B | GLiNER2-xl | Apache-2.0 | `67af949` | fp32 | `gliner2` | — |
| `Bielik-PL-Minitron-7B-v3.0-Instruct` | SpeakLeash, reference | 7.5 B | — | Apache-2.0 | `6bf1d9a` | bf16 | letter-logit readout (`--decider hf`) | — |
| `Bielik-PL-11B-v3.0-Instruct` | SpeakLeash, reference (base of basal-2.0-max) | 11.2 B | — | Apache-2.0 | `a74fa85` | LLM.int8 | letter-logit readout (`--decider hf --load-8bit`) | — |

Floors and rules (unchanged from round 1): `always_allow`, `always_redact`, `always_ask_user`, `always_block`,
`tier1`.

1. The author's GGUF folders ship the tokenizer and calibration but no `chat_template.jinja`, which basal-serve needs
   to render the prompt; the bf16 repo's template (as the GGUF card says: "as in the bf16 model") is added to the
   folder. Calibration as each card says for `--mode gguf`: basal-2.0-max `CALIBRATION.json` (the bf16 fit),
   basal-omni-1.0-max `CALIBRATION.gguf.json` (fitted on its Q8_0 port).
2. No author GGUF at that revision: converted from the bf16 safetensors with llama.cpp's `convert_hf_to_gguf`
   (vendored in llama-cpp-python 0.3.36) to Q8_0. basal-omni-1.1-max then uses its bf16 `CALIBRATION.json`.
3. The RTX 3090 (sm86) has no FP8 tensor cores; vLLM's default FP8 kernels fail there, so every FP8 kernel but
   Marlin is disabled (`VLLM_DISABLED_KERNELS`): FP8 weights, bf16 activations.
4. Its fast linear-attention kernel (`causal-conv1d` 1.7.0 wheel) needs glibc 2.32 and this WSL image has an older
   one; the PyTorch reference path gives the same answers more slowly (the server says so). Its timing is not
   comparable.

## Not admitted

| Model | Params | Reason |
|---|---|---|
| `fastino/GLiDE` v1.2 | 26 B | Q8 is about 27 GB, over 16 GB |
| `vllm-sr/d3`, `vllm-sr/d3-turbo`, `perplexity-ai/pplx-decider-v1.2` | 26.1 B | over 16 GB at Q8 |
| `Remek/basal-omni-1.0-ultra` | 31.3 B | over 16 GB at Q8 |
| Quyet-1.0-Large | 31 B | over 16 GB at Q8 |
| Respan Span-02 | 15.8 B | Q8 about 16.8 GB, over 16 GB |
| `empiriolabsai/aplomb-1` | — | gated repository, no access |
| Cygnet | — | weights published only as a training recipe |
| Liquid d1-ultra, Jev 1.14, GPT-6 Luna Decisions | — | API only; Brama official items must stay on local models (R-16) |
