from __future__ import annotations

from pretrain.quality import textstats
from pretrain.quality.textstats import highlight_spans, loop_metrics, multilingual_metrics

POLISH = (
    "Wczoraj rano mieszkańcy Warszawy spotkali się na rynku, aby porozmawiać o nowych planach dla miasta. "
    "Podczas spotkania przedstawiono wyniki badań oraz propozycje dotyczące transportu publicznego. "
    "Uczestnicy zadawali pytania, a przedstawiciele urzędu odpowiadali na nie i zapisywali uwagi. "
    "Na zakończenie wszyscy zgodzili się, że dalsza rozmowa będzie potrzebna."
)
ENGLISH = (
    "The community gathered in the town square to discuss plans for the coming year. "
    "Residents shared their experiences, asked questions, and considered several practical proposals. "
    "The organizers will publish a summary of the meeting next week."
)
CYRILLIC = (
    "Сегодня жители города встретились на площади, чтобы обсудить новые планы и важные вопросы. "
    "Участники поделились своими мыслями и предложили несколько полезных решений для сообщества."
)


def test_polish_paragraph_has_polish_cues_and_low_multilingual_score():
    stats = multilingual_metrics(POLISH)
    assert stats["top_lang"] == "pl"
    assert stats["pl_share"] > 0.9
    assert stats["polish_stopword_ratio"] > 0.05
    assert stats["polish_diacritics_per_word"] > 0
    assert stats["multilingual_score"] < 0.2
    assert loop_metrics(POLISH)["loop_score"] < 0.5


def test_repeated_paragraph_increases_repetition_metrics_and_highlights():
    repeated = "\n\n".join([POLISH] * 5)
    clean = loop_metrics(POLISH)
    looped = loop_metrics(repeated)
    assert looped["duplicate_paragraph_fraction"] > clean["duplicate_paragraph_fraction"]
    assert looped["top_2gram_char_fraction"] > clean["top_2gram_char_fraction"]
    assert looped["duplicate_5gram_char_fraction"] > clean["duplicate_5gram_char_fraction"]
    assert looped["duplicate_paragraph_char_fraction"] > 0.9
    assert looped["longest_repeated_substring_chars"] >= len(POLISH)
    assert looped["line_repeat_run_max"] >= 1
    assert looped["loop_score"] > clean["loop_score"]
    spans = highlight_spans(repeated)["loop_spans"]
    assert len(spans) >= 2
    assert len(spans) <= 50
    assert all(0 <= start < end <= len(repeated) for start, end in spans)


def test_polish_with_english_paragraph_is_multilingual_and_marks_foreign_text():
    text = POLISH + "\n\n" + ENGLISH
    stats = multilingual_metrics(text)
    assert stats["pl_share"] > 0.3
    assert stats["lang_shares"].get("en", 0) > 0.2
    assert stats["n_langs_over_5pct"] >= 2
    assert stats["switch_rate"] > 0
    assert stats["multilingual_score"] > multilingual_metrics(POLISH)["multilingual_score"]
    foreign = highlight_spans(text)["foreign_spans"]
    assert any(lang == "en" and start >= len(POLISH) for start, _, lang in foreign)


def test_cyrillic_changes_script_mix_and_language_share():
    text = POLISH + "\n\n" + CYRILLIC
    stats = multilingual_metrics(text)
    assert stats["pl_share"] > 0.2
    assert stats["cyrillic_share"] > 0.25
    assert stats["script_mix"] > 0.2
    assert stats["multilingual_score"] > multilingual_metrics(POLISH)["multilingual_score"]
    assert any(script == "ru" for _, _, script in highlight_spans(text)["foreign_spans"])


def test_pure_english_is_not_misclassified_as_polish():
    stats = multilingual_metrics(ENGLISH * 2)
    assert stats["top_lang"] == "en"
    assert stats["lang_shares"].get("en", 0) > 0.9
    assert stats["pl_share"] < 0.1
    assert stats["multilingual_score"] > 0.8


def test_duplicate_ngram_fraction_counts_each_character_once():
    # Overlapping occurrences of a repeated phrase used to be summed, pushing a partly repeated text to 1.0.
    repeated = "Kup teraz! " * 6
    text = POLISH + "\n" + repeated.strip()
    stats = loop_metrics(text)
    share = len(repeated.strip()) / len(text)
    for n in range(5, 11):
        assert abs(stats[f"duplicate_{n}gram_char_fraction"] - share) < 0.02
    assert stats["top_3gram_char_fraction"] <= share + 0.02


def test_single_line_language_switches_are_not_absorbed_by_a_polish_neighbour():
    # Short lines of different languages used to be merged into one segment that read as Polish.
    text = (
        "Rada Gminy uchwaliła budżet na przyszły rok i zapowiedziała konsultacje.\n"
        "The council approved the budget for next year and announced consultations with residents.\n"
        "В городе утвердили бюджет на следующий год."
    )
    stats = multilingual_metrics(text)
    assert stats["lang_shares"].get("en", 0) > 0.3
    assert stats["lang_shares"].get("ru", 0) > 0.1
    assert stats["switch_rate"] == 1.0
    assert {lang for _, _, lang in highlight_spans(text)["foreign_spans"]} == {"en", "ru"}


def test_polish_name_in_english_text_does_not_make_it_polish():
    stats = multilingual_metrics(
        "The meeting with Jan Kowalski from Łódź was postponed until next week because of rain."
    )
    assert stats["top_lang"] == "en"
    assert stats["pl_share"] < 0.1


def test_polish_forum_post_of_short_lines_is_polish_not_unknown():
    stats = multilingual_metrics("Witam\nmam problem z autem\nnie odpala rano\nco robic?\nPozdrawiam")
    assert stats["top_lang"] == "pl"
    assert stats["multilingual_score"] < 0.2


def test_empty_and_short_text_are_safe():
    assert multilingual_metrics("")["top_lang"] == "unknown"
    assert loop_metrics("")["loop_score"] == 0
    tiny = multilingual_metrics("Ala ma kota i psa")
    assert tiny["top_lang"] == "pl"
    assert tiny["pl_share"] == 1
    assert highlight_spans("Ala ma kota i psa") == {"loop_spans": [], "foreign_spans": []}


def test_loop_score_is_bounded_and_short_repeated_string_is_found():
    stats = loop_metrics("abcabcabc")
    assert stats["longest_repeated_substring_chars"] >= 6
    assert 0 <= stats["loop_score"] <= 1


def test_lid_model_loads_once_across_many_documents(monkeypatch):
    # The throughput regression that matters is reloading the fastText model per document (~100x slower). Count loads
    # instead of timing, so the check is deterministic on shared CI runners.
    loads: list[int] = []
    real_load = textstats._load_lid

    def counted_load():
        loads.append(1)
        return real_load()

    monkeypatch.setattr(textstats, "_load_lid", counted_load)
    textstats._lid_model.cache_clear()
    text = " ".join([POLISH, ENGLISH, CYRILLIC] * 3)
    for _ in range(40):
        multilingual_metrics(text)
        loop_metrics(text)
    assert len(loads) == 1
