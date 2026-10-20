"""Fast, language-agnostic loop and Polish/multilingual signals for quality review.

LID is deliberately lazy: importing the package never imports StyloMetrix or loads
its model. Fetch fastText's ``lid.176.bin`` (preferred) or ``lid.176.ftz`` into
``pretrain/work/quality/models/`` with ``uv run python -m pretrain.quality.fetch_lid``
(checksum-verified; the bin is ~126 MB, the compressed model ~917 KB).
fasttext-wheel's low-level binding is used for NumPy 2 compatibility.
"""

from __future__ import annotations

import itertools
import re
import zlib
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class _SuffixState(TypedDict):
    link: int
    length: int
    next: dict[str, int]
    count: int


MODEL_DIR = Path(__file__).resolve().parents[1] / "work" / "quality" / "models"
LID_FILENAMES = ("lid.176.bin", "lid.176.ftz")  # load order: the full model mislabels less short Polish text
FETCH_LID_COMMAND = "uv run python -m pretrain.quality.fetch_lid"

# Common Polish function words. This is an intentionally small cue, not a language filter.
_POLISH_STOPWORDS = frozenset(
    [
        "a",
        "aby",
        "albo",
        "ale",
        "aż",
        "bardziej",
        "bardzo",
        "bez",
        "bo",
        "być",
        "była",
        "były",
        "będzie",
        "było",
        "by",
        "więc",
        "dla",
        "do",
        "gdy",
        "i",
        "ich",
        "ile",
        "im",
        "inny",
        "ja",
        "jak",
        "jako",
        "jest",
        "jeszcze",
        "już",
        "ją",
        "jego",
        "jej",
        "jeśli",
        "kiedy",
        "który",
        "która",
        "które",
        "kto",
        "ma",
        "mam",
        "mi",
        "mnie",
        "może",
        "na",
        "nad",
        "nam",
        "nas",
        "nie",
        "nich",
        "nic",
        "niż",
        "o",
        "od",
        "on",
        "ona",
        "one",
        "oni",
        "ono",
        "oraz",
        "po",
        "pod",
        "przez",
        "przy",
        "się",
        "są",
        "ta",
        "tak",
        "te",
        "tego",
        "tej",
        "ten",
        "to",
        "tu",
        "w",
        "we",
        "za",
        "ze",
        "że",
    ]
)
_POLISH_DIACRITICS = frozenset("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?…])(?:[\"”’)]*)\s+|\n+")
_SCRIPT_RANGES = {
    "latin": ((0x0041, 0x024F), (0x1E00, 0x1EFF)),
    "cyrillic": ((0x0400, 0x052F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F)),
    "greek": ((0x0370, 0x03FF), (0x1F00, 0x1FFF)),
    "arabic": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)),
    "cjk": ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x3040, 0x30FF), (0xAC00, 0xD7AF)),
}


class LidUnavailableError(RuntimeError):
    """fastText language ID cannot run: the library or the model file is missing."""


def lid_model_path() -> Path | None:
    """The LID model file `_load_lid` would load, or None when none is present."""
    return next((path for path in (MODEL_DIR / name for name in LID_FILENAMES) if path.is_file()), None)


def _load_lid():
    try:
        import fasttext
    except ImportError as exc:
        raise LidUnavailableError("LID requires fasttext-wheel; run `uv sync --locked`") from exc
    path = lid_model_path()
    if path is None:
        raise LidUnavailableError(
            f"No fastText LID model in {MODEL_DIR} (expected {' or '.join(LID_FILENAMES)}); run `{FETCH_LID_COMMAND}`"
        )
    return fasttext.load_model(str(path))


@lru_cache(maxsize=1)
def _lid_model():
    return _load_lid()


def _predict(text: str) -> tuple[str, float]:
    # The public model.predict wrapper has a NumPy 2 incompatibility in some wheels.
    # The C++ binding accepts a single line and returns (probability, label) tuples.
    result = _lid_model().f.predict(text.replace("\n", " "), 1, 0.0, "strict")
    if not result:
        return "unknown", 0.0
    probability, label = result[0]
    return label.removeprefix("__label__"), float(probability)


MIN_LID_CHARS = 20  # alphabetic characters needed before a fastText label is trusted
MIN_LID_PROB = 0.5  # below this the unit is "uncertain" and inherits the document's dominant language
MAX_UNIT_CHARS = 400  # longer lines are split at sentence ends so a switch inside a line is visible


def _units(text: str) -> list[tuple[int, int, str]]:
    """Nonempty lines (long ones split at sentence ends) as (start, end, text). Units are never merged across
    lines: merging put a Polish line and an English line into one segment, which then read as Polish."""
    units: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+", text):
        line = match.group()
        if not line.strip():
            continue
        if len(line) <= MAX_UNIT_CHARS:
            pieces = [(0, len(line))]
        else:
            pieces, start = [], 0
            for end in [m.end() for m in re.finditer(r"[.!?…]+\s+", line)] + [len(line)]:
                if end - start >= 40 or end == len(line):
                    pieces.append((start, end))
                    start = end
        for s, e in pieces:
            seg = line[s:e]
            left = s + len(seg) - len(seg.lstrip())
            right = s + len(seg.rstrip())
            if right > left:
                units.append((match.start() + left, match.start() + right, line[left:right]))
    return units


def _polish_cue(text: str) -> bool:
    """Strong Polish evidence for short or low-confidence units: Polish diacritics on ≥15% of words, or ≥12%
    Polish function words. (A single diacritic — e.g. a Polish name in English text — is not enough.)"""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False
    diacritic_words = sum(any(c in _POLISH_DIACRITICS for c in w) for w in words) / len(words)
    stopwords = sum(w in _POLISH_STOPWORDS for w in words) / len(words)
    return diacritic_words >= 0.15 or stopwords >= 0.12


def _label_units(text: str) -> list[tuple[int, int, str, int]]:
    """(start, end, language, alphabetic chars) per unit. Confident fastText labels first; units that are short or
    below MIN_LID_PROB take "pl" when they carry strong Polish cues, otherwise the document's dominant language:
    the most common confident unit label, else fastText on the whole document (e.g. a forum post made of short
    lines), else "unknown"."""
    labelled: list[list] = []
    confident: Counter[str] = Counter()
    for start, end, unit in _units(text):
        chars = sum(ch.isalpha() for ch in unit)
        if not chars:
            continue
        lang, prob = _predict(unit) if chars >= MIN_LID_CHARS else ("", 0.0)
        if lang and prob >= MIN_LID_PROB:
            confident[lang] += chars
            labelled.append([start, end, lang, chars])
        else:
            labelled.append([start, end, "pl" if _polish_cue(unit) else None, chars])
    if confident:
        dominant = confident.most_common(1)[0][0]
    else:
        lang, prob = _predict(text) if any(ch.isalpha() for ch in text) else ("unknown", 0.0)
        dominant = lang if prob >= MIN_LID_PROB else ("pl" if _polish_cue(text) else "unknown")
    return [(s, e, lang or dominant, c) for s, e, lang, c in labelled]


def _script(char: str) -> str:
    cp = ord(char)
    for name, ranges in _SCRIPT_RANGES.items():
        if any(start <= cp <= end for start, end in ranges):
            return name
    return "other"


def multilingual_metrics(text: str) -> dict:
    """Return char-weighted LID, script-mixture and Polish-cue features.

    LID runs per line (long lines split at sentence ends) with fastText lid.176; short or low-confidence units use
    Polish cues or inherit the dominant language, so they neither hide nor invent a language switch.
    """
    languages: Counter[str] = Counter()
    segment_labels: list[str] = []
    for _, _, lang, chars in _label_units(text):
        languages[lang] += chars
        segment_labels.append(lang)
    alpha_chars = sum(languages.values())
    shares = {lang: count / alpha_chars for lang, count in languages.items() if count} if alpha_chars else {}
    top_lang = max(shares, key=lambda lang: shares[lang]) if shares else "unknown"
    pl_share = shares.get("pl", 0.0)
    switch_rate = (
        sum(a != b for a, b in itertools.pairwise(segment_labels)) / (len(segment_labels) - 1)
        if len(segment_labels) > 1
        else 0.0
    )

    script_counts: Counter[str] = Counter()
    for char in text:
        if char.isalpha():
            script_counts[_script(char)] += 1
    n_script_chars = sum(script_counts.values())
    script_shares = {
        name: script_counts[name] / n_script_chars if n_script_chars else 0.0 for name in (*_SCRIPT_RANGES, "other")
    }
    script_mix = 1.0 - max(script_shares.values(), default=0.0) if n_script_chars else 0.0

    words = [word.lower() for word in _WORD_RE.findall(text)]
    diacritic_words = sum(any(ch in _POLISH_DIACRITICS for ch in word) for word in words)
    diacritic_chars = sum(sum(ch in _POLISH_DIACRITICS for ch in word) for word in words)
    stopword_ratio = sum(word in _POLISH_STOPWORDS for word in words) / len(words) if words else 0.0
    non_polish = max(0.0, 1.0 - pl_share)
    diversity = min(1.0, max(0, len([v for v in shares.values() if v > 0.05]) - 1) / 3)
    multilingual_score = min(1.0, max(0.0, 0.85 * non_polish + 0.10 * diversity + 0.05 * switch_rate))
    return {
        "top_lang": top_lang,
        "lang_shares": shares,
        "pl_share": pl_share,
        "n_langs_over_5pct": sum(value > 0.05 for value in shares.values()),
        "switch_rate": switch_rate,
        **{f"{name}_share": share for name, share in script_shares.items()},
        "script_mix": script_mix,
        "polish_diacritics_per_word": diacritic_chars / len(words) if words else 0.0,
        "polish_diacritic_word_ratio": diacritic_words / len(words) if words else 0.0,
        "polish_stopword_ratio": stopword_ratio,
        "multilingual_score": multilingual_score,
    }


def _fraction_duplicate_units(units: list[str]) -> tuple[float, float, set[str]]:
    nonempty = [unit.strip() for unit in units if unit.strip()]
    counts = Counter(nonempty)
    repeated = {unit for unit, count in counts.items() if count > 1}
    n = len(nonempty)
    char_count = sum(map(len, nonempty))
    duplicate_units = [unit for unit in nonempty if unit in repeated]
    return (
        len(duplicate_units) / n if n else 0.0,
        sum(map(len, duplicate_units)) / char_count if char_count else 0.0,
        repeated,
    )


def _ngram_char_fractions(
    words: list[tuple[str, int, int]], tokens: list[str], size: int, total_chars: int
) -> tuple[float, float]:
    """(top, duplicate) character fractions, Gopher-style: characters covered by occurrences of the most frequent
    repeated n-gram / of any repeated n-gram, each character counted once (overlapping occurrences used to be summed,
    which pushed short repetitive texts to 1.0)."""
    ngrams = [
        (tuple(tokens[index : index + size]), words[index][1], words[index + size - 1][2])
        for index in range(max(0, len(words) - size + 1))
    ]
    if not ngrams:
        return 0.0, 0.0
    counts = Counter(gram for gram, _, _ in ngrams)
    top = max(counts.values())
    top_gram = max(counts, key=lambda gram: counts[gram]) if top > 1 else None

    def covered(spans: list[tuple[int, int]]) -> int:
        total, reach = 0, -1
        for start, end in sorted(spans):
            if end > reach:
                total += end - max(start, reach)
                reach = end
        return total

    duplicate = covered([(s, e) for gram, s, e in ngrams if counts[gram] > 1])
    top_cov = covered([(s, e) for gram, s, e in ngrams if gram == top_gram]) if top_gram else 0
    return top_cov / max(1, total_chars), duplicate / max(1, total_chars)


def _longest_repeated_substring(text: str) -> int:
    """Longest repeated substring via a linear-time suffix automaton."""
    states: list[_SuffixState] = [{"link": -1, "length": 0, "next": {}, "count": 0}]
    last = 0
    for char in text:
        current = len(states)
        states.append({"link": 0, "length": states[last]["length"] + 1, "next": {}, "count": 1})
        p = last
        while p >= 0 and char not in states[p]["next"]:
            states[p]["next"][char] = current
            p = states[p]["link"]
        if p >= 0:
            q = states[p]["next"][char]
            if states[p]["length"] + 1 == states[q]["length"]:
                states[current]["link"] = q
            else:
                clone = len(states)
                states.append(
                    {
                        "link": states[q]["link"],
                        "length": states[p]["length"] + 1,
                        "next": states[q]["next"].copy(),
                        "count": 0,
                    }
                )
                while p >= 0 and states[p]["next"].get(char) == q:
                    states[p]["next"][char] = clone
                    p = states[p]["link"]
                states[q]["link"] = states[current]["link"] = clone
        last = current
    by_length: list[list[int]] = [[] for _ in range(len(text) + 1)]
    for index in range(1, len(states)):
        by_length[states[index]["length"]].append(index)
    for length in range(len(text), 0, -1):
        for index in by_length[length]:
            states[states[index]["link"]]["count"] += states[index]["count"]
    return max((state["length"] for state in states if state["count"] > 1), default=0)


def _run_max(units: list[str]) -> int:
    maximum = run = 0
    previous = None
    for unit in units:
        value = unit.strip().casefold()
        if not value:
            continue
        run = run + 1 if value == previous else 1
        maximum = max(maximum, run)
        previous = value
    return maximum


def loop_metrics(text: str) -> dict[str, float]:
    """Compute repetition signals. Scores are diagnostics, not rejection rules.

    ``loop_score`` is the mean of capped ratios to the published Gopher cutoffs:
    line/paragraph count fractions (0.30), their character fractions (0.20),
    top 2/3/4 word-ngram character fractions (0.20/0.18/0.16), and duplicate
    5..10-word-ngram character fractions (0.15..0.10). It is bounded to [0,1].
    """
    lines = [line for line in text.split("\n") if line.strip()]
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    line_fraction, line_char_fraction, _ = _fraction_duplicate_units(lines)
    para_fraction, para_char_fraction, _ = _fraction_duplicate_units(paragraphs)
    words = [(m.group().casefold(), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
    tokens = [word for word, _, _ in words]
    total_chars = len(text)
    result: dict[str, float] = {
        "duplicate_line_fraction": line_fraction,
        "duplicate_paragraph_fraction": para_fraction,
        "duplicate_line_char_fraction": line_char_fraction,
        "duplicate_paragraph_char_fraction": para_char_fraction,
    }
    ratios = [line_fraction / 0.30, para_fraction / 0.30, line_char_fraction / 0.20, para_char_fraction / 0.20]
    for size, threshold in ((2, 0.20), (3, 0.18), (4, 0.16)):
        top, _ = _ngram_char_fractions(words, tokens, size, total_chars)
        result[f"top_{size}gram_char_fraction"] = top
        ratios.append(top / threshold)
    for size, threshold in zip(range(5, 11), (0.15, 0.14, 0.13, 0.12, 0.11, 0.10), strict=False):
        _, duplicate_fraction = _ngram_char_fractions(words, tokens, size, total_chars)
        result[f"duplicate_{size}gram_char_fraction"] = duplicate_fraction
        ratios.append(duplicate_fraction / threshold)
    longest = _longest_repeated_substring(text)
    result["longest_repeated_substring_chars"] = float(longest)
    result["longest_repeated_substring_fraction"] = longest / len(text) if text else 0.0
    compressed = len(zlib.compress(text.encode("utf-8")))
    result["zlib_compression_ratio"] = compressed / max(1, len(text.encode("utf-8")))
    result["line_repeat_run_max"] = float(_run_max(lines))
    sentences = [part for part in _SENTENCE_RE.split(text) if part.strip()]
    result["sentence_repeat_run_max"] = float(_run_max(sentences))
    ratios.extend(
        (
            result["longest_repeated_substring_fraction"] / 0.20,
            result["line_repeat_run_max"] / 5,
            result["sentence_repeat_run_max"] / 5,
            max(0.0, 0.8 - result["zlib_compression_ratio"]) / 0.6,
        )
    )
    result["loop_score"] = min(1.0, sum(min(1.0, max(0.0, ratio)) for ratio in ratios) / len(ratios))
    return result


def _merge_spans(spans: list[tuple[int, int]], limit: int = 50) -> list[list[int]]:
    if not spans:
        return []
    ordered = sorted(spans)
    merged: list[list[int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sorted(merged, key=lambda item: item[1] - item[0], reverse=True)[:limit]


def highlight_spans(text: str) -> dict[str, list]:
    """Return repeated character spans and non-Polish LID segments."""
    _, _, repeated_lines = _fraction_duplicate_units([line for line in text.split("\n") if line.strip()])
    loop_spans = [
        (match.start(), match.end())
        for match in re.finditer(r"[^\n]+", text)
        if match.group().strip() in repeated_lines
    ]
    _, _, repeated_paragraphs = _fraction_duplicate_units(
        [paragraph for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    )
    loop_spans.extend(
        (match.start(), match.end())
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|$)", text, re.DOTALL)
        if match.group().strip() in repeated_paragraphs
    )
    foreign_spans: list[list] = []
    foreign_spans = [[start, end, lang] for start, end, lang, _ in _label_units(text) if lang != "pl"]
    return {"loop_spans": _merge_spans(loop_spans), "foreign_spans": foreign_spans}


METRIC_DOCS = {
    "duplicate_line_fraction": "Fraction of nonempty lines whose exact text occurs more than once.",
    "duplicate_paragraph_fraction": "Fraction of paragraphs whose exact text occurs more than once.",
    "duplicate_line_char_fraction": "Fraction of nonempty line characters belonging to repeated lines.",
    "duplicate_paragraph_char_fraction": "Fraction of paragraph characters belonging to repeated paragraphs.",
    "top_2gram_char_fraction": "Document character share covered by occurrences of its most frequent repeated two-word sequence; zero if none repeat.",
    "top_3gram_char_fraction": "Document character share covered by occurrences of its most frequent repeated three-word sequence; zero if none repeat.",
    "top_4gram_char_fraction": "Document character share covered by occurrences of its most frequent repeated four-word sequence; zero if none repeat.",
    **{
        f"duplicate_{n}gram_char_fraction": f"Character share covered by repeated {n}-word sequences."
        for n in range(5, 11)
    },
    "longest_repeated_substring_chars": "Length of the longest exact substring occurring at least twice.",
    "longest_repeated_substring_fraction": "Longest repeated substring length divided by document characters.",
    "zlib_compression_ratio": "UTF-8 byte length after zlib compression divided by original UTF-8 byte length.",
    "line_repeat_run_max": "Longest run of identical adjacent nonempty lines, measured in lines.",
    "sentence_repeat_run_max": "Longest run of identical adjacent sentences, measured in sentences.",
    "loop_score": "Mean of capped repetition-feature-to-Gopher-cutoff ratios, clipped to [0,1].",
    "top_lang": "Most prevalent predicted ISO 639-1 language by alphabetic character count.",
    "lang_shares": "Language proportions weighted by alphabetic characters, LID per line (long lines per sentence).",
    "pl_share": "Predicted Polish share of alphabetic characters.",
    "n_langs_over_5pct": "Number of predicted languages with more than 5% of alphabetic characters.",
    "switch_rate": "Fraction of adjacent line/sentence units assigned different languages.",
    **{
        f"{script}_share": f"Share of alphabetic characters written in Unicode {script.title()} script."
        for script in (*_SCRIPT_RANGES, "other")
    },
    "script_mix": "One minus the largest Unicode script share; zero means a single script.",
    "polish_diacritics_per_word": "Count of Polish-specific diacritic characters divided by word-token count.",
    "polish_diacritic_word_ratio": "Fraction of word tokens containing at least one Polish-specific diacritic.",
    "polish_stopword_ratio": "Fraction of word tokens matching the built-in Polish function-word list.",
    "multilingual_score": "0.85*(1-pl_share)+0.10*min((languages over 5% minus 1)/3,1)+0.05*switch_rate, clipped to [0,1].",
}
