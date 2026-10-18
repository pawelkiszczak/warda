# Looping and language signals in pretraining corpora

*Research note for the review set; thresholds below are published pipeline settings, not universal quality boundaries.*

## Repetition and looping

**Gopher / MassiveText.** Rae et al. remove a web document if any repetition measurement exceeds its cutoff: duplicate-line and duplicate-paragraph fractions 0.30 each; duplicate line and paragraph character fractions 0.20 each; most frequent 2-, 3-, and 4-gram character fractions 0.20, 0.18, and 0.16; and repeated 5- through 10-gram character fractions 0.15, 0.14, 0.13, 0.12, 0.11, and 0.10. This catches both many small repeats and a few large copied blocks. It is interpretable and cheap, but English-oriented thresholds and a hard OR can remove legitimate formulaic text. FineWeb used the MassiveText rules as a starting point.

**FineWeb / C4 / Dolma.** FineWeb tested more than fifty candidate statistics with model-training ablations, retaining a character share in duplicated lines cutoff of 0.10 (vs MassiveText's 0.20), alongside line-ending punctuation and short-line signals. C4 uses simple extraction-era rules: punctuation-ending lines, short pages/lines, and patterns such as “lorem ipsum”, JavaScript, and policy text; these are cheap but can over-remove non-English or informal writing. Dolma retains Gopher heuristics and a C4 no-terminal-punctuation paragraph rule; the authors report that their combination outperformed either alone in their ablation. CCNet does paragraph hash deduplication at corpus level; this targets common template paragraphs, not necessarily repetitions within one document.

**RedPajama-V2.** Rather than committing to one quality decision, it releases 40+ per-document quality signals, including CCNet LID confidence/perplexity/length/line counts; C4 curly-brace and lorem-ipsum checks; natural-language ratios (stopwords, repeated lines, word lengths, punctuation, capitalization, symbol-to-word ratio, unique words and unigram entropy); and reference-corpus classifier / importance scores. This is useful for later policy selection, but a score is not a quality verdict.

**FineWeb-2.** The multilingual pipeline disables paragraph repetition filters because its text extraction does not preserve paragraph boundaries, and relaxes FineWeb's `char_dup_ratio` from 0.01 to 0.1; C4 filters were not included because they degraded its multilingual ablations. Per-language filtering thresholds are learned from language-specific reference distributions rather than copying English cutoffs.

**Other signals.** Compression ratio (compressed bytes / original bytes, e.g. zlib) is a model-free low-cost proxy: repeated boilerplate usually compresses unusually well, but legitimate short/function-word-rich text and noisy high-entropy garbage can both fool it. Longest repeated-substring algorithms use suffix arrays (or suffix automata) to find exact copied runs in linear or near-linear time; they locate a span but alone do not say whether its repetition is bad. Bielik v3 reports `looping_suspicion` among its Polish stylometric features and trains against hand-labelled plus synthetic looping examples; this validates it as a useful classifier feature, but its report does not publish a universal threshold for that feature. Low per-token LM NLL runs can flag repeated, predictable stretches when computed from the scorer's token losses, but are compute/model dependent and also mark ordinary formulae, boilerplate, and predictable Polish. LM perplexity is therefore a complementary feature, not a repetition rule.

## Language, script and code switching

Document LID is insufficient for mixed pages. FastText `lid.176` is a compact character n-gram classifier for 176 languages; FineWeb uses English confidence ≥0.65, CC-100 used ≥0.50, and Dolma's CCNet stage uses English ≥0.50. mC4 uses ≥0.70. FineWeb-2 moved to GlotLID (1,880 language labels, including script labels and noise classes) and chooses language-specific confidence cutoffs: its data-driven formula is `clip(median(confidence) - standard_deviation, 0.3, 0.9)`. It outperformed fastText for higher-resource canary languages but was slightly worse for some lower-resource ones. FastText is fast, small, and includes Polish, but has only one document prediction and can be unreliable on short fragments; its compressed 917 KB model is especially weak on short Polish strings. The full 126 MB model is more accurate. GlotLID has broad language/script coverage but a much larger model and confidence calibration remains language-specific.

Lingua is a lightweight multi-language identification library emphasizing short-text accuracy; CLD3 is a compact neural character n-gram LID used by mC4. Neither offers FineWeb-2's breadth of script-specific/noise labels. For a corpus-specific review tool, we select full fastText `lid.176.bin`: supported Polish, fast CPU inference, modest 126 MB download; it works via `fasttext-wheel`'s low-level binding with NumPy 2 (`model.f.predict`; the public `predict` breaks on NumPy 2). The compressed `lid.176.ftz` labels "Ala ma kota i psa." as Indonesian, and even the full model is unreliable below ~20 letters. LID therefore runs per line (lines over 400 chars are split at sentence ends). A unit is labelled only when it has ≥20 letters and fastText confidence ≥0.5. Other units take Polish when they carry strong Polish cues (diacritics on ≥15% of words, or ≥12% function words); otherwise they inherit the document's dominant language (fastText on the whole text when no unit is confident). Lines are not merged: an earlier merge-to-80-chars version fused a Polish line with an English one, and one Polish diacritic in the fused segment made the whole segment "Polish". This is deliberately a Polish corpus feature, not a replacement general multilingual classifier.

Sentence- or line-level LID reveals code-switching by language transitions and character-weighted language shares; this can over-count transitions in fragments and should be reviewed with highlighted spans. Recent code-switch LID research (e.g. MaskLID) likewise complements sentence-level classifiers rather than treating one document label as sufficient. Unicode script proportions (Latin, Cyrillic, Greek, Arabic, CJK, other) identify writing-system mixing even where language models confuse related or short text. They cannot distinguish languages that share a script. Polish cues are diacritics `ąćęłńóśźż` and common function words; these improve Polish recall on short segments but are heuristics, can miss undiacritized Polish, and should not by themselves mark a foreign language.

## Implemented features and rationale

`loop_metrics` exposes Gopher line/paragraph count and character fractions, most-frequent 2–4-word-ngram and repeated 5–10-word-ngram character fractions, zlib ratio, a suffix automaton longest repeated substring, and maximum identical adjacent line/sentence runs. Its documented `loop_score` averages each Gopher-derived signal normalized by its published cutoff (each ratio capped at 1), plus bounded longest-repeat, run-length, and compression contributions; it is a review ranking signal, not an automatic reject threshold. The app can display the raw features so a human can judge legitimate repetitions.

`multilingual_metrics` returns per-line (sentence for long lines) language shares weighted by alphabetic characters, Polish share, language switches, script shares/mix, Polish diacritic-word and stopword ratios, plus a bounded score: `clip(0.85*(1-pl_share) + 0.10*min((languages over 5% - 1)/3, 1) + 0.05*switch_rate, 0, 1)`. Thus an all-English document scores as strongly out-of-language for a Polish corpus, while added language diversity and switching increase the score. `highlight_spans` reports repeated lines/paragraphs and non-Polish segments. Keeping the underlying signals separate makes errors visible and lets future human labels calibrate a classifier instead of hard-coding English-centric corpus cutoffs.

## Sources

- Rae et al., *Scaling Language Models: Methods, Analysis & Insights from Training Gopher* (MassiveText Appendix A): https://arxiv.org/abs/2112.11446
- Penedo et al., *The FineWeb Datasets*: https://arxiv.org/abs/2406.17557
- Penedo et al., *FineWeb2*: https://arxiv.org/abs/2506.20920
- RedPajama-V2 repository and signal catalog: https://github.com/togethercomputer/RedPajama-Data
- Dolma technical report: https://arxiv.org/abs/2402.00159
- CCNet: https://arxiv.org/abs/1911.00359
- C4 (Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer): https://arxiv.org/abs/1910.10683
- Bielik v3 technical report: https://arxiv.org/abs/2505.02550
- FastText language-identification models and sizes: https://fasttext.cc/docs/en/language-identification.html
- GlotLID repository/model: https://github.com/cisnlp/GlotLID and https://huggingface.co/cis-lmu/glotlid
- Lingua docs: https://github.com/pemistahl/lingua-py
- CLD3: https://github.com/google/cld3
- MaskLID code-switch identification: https://arxiv.org/abs/2406.06263
- Compression as a quality feature (research paper): https://openreview.net/forum?id=KFafeqE5fe
