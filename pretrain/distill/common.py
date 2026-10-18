from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "pretrain" / "work" / "distill"
LICENSES = {
    "fineweb-2": "ODC-By-1.0",
    "plwiki": "CC-BY-SA 3.0",
    "wolne_lektury_corpus": "CC BY-SA 4.0 or Free Art License",
    "1000_novels_corpus_CLARIN-PL": "CC BY 4.0",
    "biblioteka_nauki_pl_corpus": "TBC",
    "europeana_eu_pl_corpus": "Public Domain, Creative Commons",
    "saos": "Not specified",
    "eurlex_corpus": "Public domain",
    "ISAP_corpus": "https://isap.sejm.gov.pl/",
    "PPC_corpus": "Public Domain",
    "CBOSA_corpus": "conditional licence",
    "open_subtitles_corpus": "Public Domain; CC BY-SA 3.0; Free Art License 1.3",
    "shopping_1_general_corpus": "conditional license",
    "forum_gazeta_pl_corpus": "conditional license",
    "forum_muratordom_pl_corpus": "conditional license",
    "web_artykuły_inne_1": "conditional license",
    "web_artykuły_inne_2": "conditional license",
    "pretrain_train_mixed": "Mixed; see pretrain/work/tokens/manifest.json",
}


def is_polish(text: str) -> bool:
    if len(re.findall(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", text)) >= 2:
        return True
    words = set(re.findall(r"\b[\wąćęłńóśźż]+\b", text.casefold()))
    cues = {
        "się",
        "jest",
        "są",
        "nie",
        "oraz",
        "który",
        "która",
        "które",
        "jako",
        "dla",
        "przez",
        "przy",
        "ale",
        "lub",
        "było",
        "był",
        "będzie",
        "co",
        "na",
        "do",
        "tego",
        "także",
        "może",
        "roku",
        "jego",
        "jej",
        "czy",
        "ten",
        "tej",
        "od",
    }
    return len(words & cues) >= 3


def log(message: str) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    print(message, flush=True)
    with (WORK / (Path(sys.argv[0]).stem + ".log")).open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def doc_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def load_prompt_tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained("speakleash/Bielik-1.5B-v3.0-Instruct")


# Every family has three natural Polish paraphrases and concrete applicability guidance.
BANK = [
    (
        "topic",
        "choice",
        "any",
        [
            "Jakiego tematu dotyczy tekst?",
            "Która kategoria najlepiej opisuje treść?",
            "O czym przede wszystkim jest ten tekst?",
        ],
        [
            "zakupy i produkty",
            "zdrowie",
            "edukacja",
            "prawo i administracja",
            "technologia",
            "podróże",
            "praca",
            "rodzina",
            "finanse",
            "kultura",
            "dom i budownictwo",
            "żywność",
            "transport",
            "środowisko",
            "polityka",
            "sport",
            "usługi",
            "media",
            "nauka",
            "inne",
        ],
    ),
    (
        "genre",
        "choice",
        "any",
        [
            "Jaki to rodzaj tekstu?",
            "Do jakiego gatunku należy ten fragment?",
            "Jak najlepiej określić formę wypowiedzi?",
        ],
        [
            "opinia lub recenzja",
            "wpis na forum",
            "artykuł informacyjny",
            "dokument prawny",
            "fragment literacki",
            "dialog lub napisy",
            "instrukcja",
            "ogłoszenie",
            "relacja",
            "inny rodzaj",
        ],
    ),
    (
        "sentiment",
        "score",
        "any",
        [
            "Jaki wydźwięk emocjonalny ma tekst?",
            "Jak oceniasz ogólny sentyment wypowiedzi?",
            "Jak pozytywny lub negatywny jest tekst?",
        ],
        [
            "1 — bardzo negatywny",
            "2 — raczej negatywny",
            "3 — neutralny",
            "4 — raczej pozytywny",
            "5 — bardzo pozytywny",
        ],
    ),
    (
        "tone",
        "choice",
        "any",
        [
            "Jaki ton dominuje w tekście?",
            "Który opis najlepiej oddaje emocjonalny ton wypowiedzi?",
            "Jak brzmi ta wypowiedź?",
        ],
        [
            "spokojny i rzeczowy",
            "entuzjastyczny",
            "niezadowolony",
            "żartobliwy",
            "zaniepokojony",
            "smutny",
            "agresywny",
            "neutralny",
        ],
    ),
    (
        "formality",
        "score",
        "any",
        [
            "Jak formalny jest język tekstu?",
            "Oceń stopień formalności wypowiedzi.",
            "Na ile oficjalnie brzmi ten tekst?",
        ],
        ["1 — bardzo potoczny", "2 — raczej potoczny", "3 — neutralny", "4 — raczej formalny", "5 — bardzo formalny"],
    ),
    (
        "advertisement",
        "noul",
        "any",
        [
            "Czy tekst jest reklamą lub zachętą do zakupu?",
            "Czy autor promuje produkt, usługę albo ofertę?",
            "Czy to przekaz reklamowy?",
        ],
        None,
    ),
    (
        "personal_data",
        "noul",
        "any",
        [
            "Czy tekst zawiera dane pozwalające zidentyfikować osobę?",
            "Czy podano tu dane osobowe, takie jak nazwisko, adres lub telefon?",
            "Czy w tekście występują dane osobowe?",
        ],
        None,
    ),
    (
        "reader_request",
        "noul",
        "any",
        [
            "Czy tekst zawiera prośbę lub pytanie skierowane do odbiorcy?",
            "Czy autor prosi czytelnika o działanie albo odpowiedź?",
            "Czy wypowiedź zwraca się do odbiorcy z pytaniem lub prośbą?",
        ],
        None,
    ),
    (
        "date",
        "noul",
        "any",
        [
            "Czy tekst wspomina konkretną datę lub termin?",
            "Czy pojawia się tu data, deadline albo okres?",
            "Czy treść zawiera odniesienie do terminu?",
        ],
        None,
    ),
    (
        "money",
        "noul",
        "any",
        [
            "Czy w tekście wspomniano kwotę lub pieniądze?",
            "Czy pojawia się cena, wynagrodzenie albo inna suma?",
            "Czy treść dotyczy pieniędzy lub kwot?",
        ],
        None,
    ),
    (
        "legal",
        "noul",
        "law",
        [
            "Czy jest to tekst prawny lub urzędowy?",
            "Czy fragment pochodzi z aktu prawnego albo dokumentu sądowego?",
            "Czy treść ma charakter prawny?",
        ],
        None,
    ),
    (
        "stance",
        "choice",
        "complaint",
        [
            "Jak autor ocenia opisywaną sprawę?",
            "Jaki jest stosunek autora do przedmiotu wypowiedzi?",
            "Czy autor wyraża aprobatę, krytykę czy brak oceny?",
        ],
        [
            "zdecydowanie pozytywny",
            "raczej pozytywny",
            "neutralny lub brak oceny",
            "raczej krytyczny",
            "zdecydowanie krytyczny",
        ],
    ),
    (
        "urgency",
        "score",
        "complaint",
        [
            "Jak pilna jest sprawa opisana w tekście?",
            "Oceń, jak szybko należy zająć się zgłoszeniem.",
            "Jaki poziom pilności wynika z tej skargi?",
        ],
        [
            "1 — może poczekać",
            "2 — warto zająć się wkrótce",
            "3 — wymaga szybkiej reakcji",
            "4 — pilne, natychmiastowa reakcja",
        ],
    ),
    (
        "department",
        "choice",
        "complaint",
        [
            "Do którego działu najlepiej skierować tę sprawę?",
            "Jaki zespół powinien zająć się zgłoszeniem?",
            "Wybierz właściwy obszar obsługi tej skargi.",
        ],
        [
            "obsługa klienta i reklamacje",
            "płatności i rozliczenia",
            "dostawa i logistyka",
            "produkt lub jakość",
            "konto i dostęp",
            "serwis techniczny",
            "inne",
        ],
    ),
    (
        "audience",
        "choice",
        "any",
        [
            "Do jakiego odbiorcy skierowany jest tekst?",
            "Kto jest głównym adresatem tej wypowiedzi?",
            "Jaka grupa odbiorców jest tu najbardziej prawdopodobna?",
        ],
        [
            "konsumenci",
            "specjaliści",
            "urzędnicy lub prawnicy",
            "uczniowie lub studenci",
            "mieszkańcy lokalnej społeczności",
            "czytelnicy ogólni",
        ],
    ),
    (
        "intent",
        "choice",
        "any",
        [
            "Jaki jest główny cel tekstu?",
            "Co autor przede wszystkim chce osiągnąć?",
            "Która intencja najlepiej pasuje do wypowiedzi?",
        ],
        [
            "poinformować",
            "przekonać",
            "złożyć skargę",
            "zadać pytanie lub poprosić",
            "opowiedzieć historię",
            "rozbawić",
            "opisać lub wyjaśnić",
            "inny cel",
        ],
    ),
    (
        "quality",
        "score",
        "any",
        [
            "Jak oceniasz czytelność i jakość tekstu?",
            "Oceń klarowność wypowiedzi.",
            "Na ile tekst jest zrozumiały i dobrze napisany?",
        ],
        [
            "1 — bardzo słaby i nieczytelny",
            "2 — raczej słaby",
            "3 — przeciętny",
            "4 — dobry i czytelny",
            "5 — bardzo klarowny",
        ],
    ),
    (
        "complete",
        "noul",
        "any",
        [
            "Czy tekst wydaje się kompletny, a nie urwany?",
            "Czy fragment ma zakończenie, czy wygląda na ucięty?",
            "Czy wypowiedź jest pełna?",
        ],
        None,
    ),
    (
        "question",
        "noul",
        "any",
        [
            "Czy autor zadaje pytanie?",
            "Czy tekst zawiera pytanie wymagające odpowiedzi?",
            "Czy pojawia się w nim pytanie?",
        ],
        None,
    ),
    (
        "instruction",
        "noul",
        "any",
        [
            "Czy tekst zawiera instrukcję lub polecenie?",
            "Czy odbiorca jest proszony o wykonanie konkretnej czynności?",
            "Czy wypowiedź instruuje czytelnika?",
        ],
        None,
    ),
    (
        "evidence",
        "choice",
        "any",
        ["Na czym głównie opiera się tekst?", "Jaki rodzaj treści dominuje?", "Co stanowi podstawę tej wypowiedzi?"],
        [
            "osobiste doświadczenie",
            "fakty lub dane",
            "argumenty i opinie",
            "przepisy lub procedury",
            "fikcja lub narracja",
            "rozmowa",
            "trudno określić",
        ],
    ),
    (
        "time",
        "choice",
        "any",
        [
            "Do jakiego okresu odnosi się tekst?",
            "Jaki horyzont czasowy dominuje?",
            "Czy wypowiedź dotyczy przeszłości, teraźniejszości czy przyszłości?",
        ],
        ["przeszłość", "teraźniejszość", "przyszłość", "różne okresy", "brak odniesień czasowych"],
    ),
    (
        "register",
        "choice",
        "any",
        [
            "Jaki rejestr języka dominuje?",
            "Czy tekst jest bardziej potoczny, specjalistyczny czy literacki?",
            "Który rejestr najlepiej opisuje słownictwo?",
        ],
        ["potoczny", "urzędowy", "specjalistyczny", "literacki", "publicystyczny", "mieszany"],
    ),
    (
        "persuasion",
        "noul",
        "any",
        [
            "Czy autor próbuje przekonać odbiorcę do swojego stanowiska?",
            "Czy tekst zawiera perswazję?",
            "Czy wypowiedź ma na celu zmianę opinii odbiorcy?",
        ],
        None,
    ),
    (
        "entity",
        "choice",
        "any",
        [
            "Jaki typ podmiotu jest najważniejszy w tekście?",
            "Kto lub co jest głównym bohaterem treści?",
            "Który rodzaj podmiotu dominuje?",
        ],
        [
            "osoba prywatna",
            "firma lub organizacja",
            "instytucja publiczna",
            "produkt lub usługa",
            "miejsce",
            "pojęcie lub wydarzenie",
            "brak wyraźnego podmiotu",
        ],
    ),
    (
        "specificity",
        "score",
        "any",
        [
            "Jak konkretny jest opis?",
            "Oceń poziom szczegółowości tekstu.",
            "Na ile wypowiedź podaje konkretne informacje?",
        ],
        [
            "1 — bardzo ogólny",
            "2 — raczej ogólny",
            "3 — umiarkowanie konkretny",
            "4 — szczegółowy",
            "5 — bardzo szczegółowy",
        ],
    ),
]

LAW_SOURCES = {"saos", "eurlex_corpus", "ISAP_corpus", "PPC_corpus", "CBOSA_corpus"}
COMPLAINT_SOURCES = {"shopping_1_general_corpus", "forum_gazeta_pl_corpus", "forum_muratordom_pl_corpus"}


def applicable(family: str, source: str, text: str) -> bool:
    rule = next(x[2] for x in BANK if x[0] == family)
    if rule == "law":
        return source in LAW_SOURCES or any(
            w in text.lower() for w in ("ustaw", "sąd", "przepis", "kodeks", "artykuł", "sygn.")
        )
    if rule == "complaint":
        return source in COMPLAINT_SOURCES or any(
            w in text.lower() for w in ("reklamac", "nie działa", "zwrot", "problem z")
        )
    return True


def make_question(family: str, variant: int, text: str = "") -> tuple[str, str, list[str]]:
    name, typ, _, paraphrases, choices = next(x for x in BANK if x[0] == family)
    question = paraphrases[variant % 3]
    if name == "topic":
        if choices is None:
            return question, typ, []
        value = text.casefold()
        clues = [
            ("zakupy i produkty", ("produkt", "zakup", "sklep", "cena", "klient", "zamów")),
            ("zdrowie", ("zdrow", "pacjent", "lekarz", "chorob", "leczeni")),
            ("edukacja", ("szkoł", "student", "uczni", "nauk", "lekcj")),
            ("prawo i administracja", ("ustaw", "sąd", "przepis", "wniosek", "urzęd")),
            ("technologia", ("system", "oprogram", "technolog", "komputer", "internet")),
            ("podróże", ("podróż", "hotel", "wakac", "turyst", "lotnisk")),
            ("praca", ("prac", "zatrud", "firma", "wynagrod", "zespół")),
            ("rodzina", ("rodzin", "dziec", "matk", "ojc", "małżeń")),
            ("finanse", ("pieni", "budżet", "kredyt", "podat", "kwot")),
            ("kultura", ("książ", "film", "muzyk", "teatr", "sztuk")),
            ("dom i budownictwo", ("dom", "budow", "mieszkan", "remont", "ścian")),
            ("żywność", ("jedzeni", "żywno", "restaur", "posił", "smak")),
            ("transport", ("samoch", "transport", "autobus", "pociąg", "droga")),
            ("środowisko", ("środow", "klimat", "energia", "woda", "przyrod")),
            ("polityka", ("polity", "rząd", "wybor", "parti", "prezydent")),
            ("sport", ("sport", "mecz", "drużyn", "zawod", "trening")),
            ("usługi", ("usług", "serwis", "obsług", "napraw", "dostaw")),
            ("media", ("media", "artykuł", "dziennik", "telewiz", "wiadomo")),
            ("nauka", ("badani", "naukow", "eksperyment", "teoria", "wynik")),
        ]
        likely = next((label for label, words in clues if any(word in value for word in words)), "inne")
        candidates = [likely]
        candidates.extend(
            choices[(variant * 3 + i) % len(choices)]
            for i in range(len(choices))
            if choices[(variant * 3 + i) % len(choices)] != likely
        )
        return question, typ, candidates[:6]
    if typ == "noul":
        return question, typ, ["tak", "nie"]
    if choices is None:
        return question, typ, []
    if typ == "score":
        return question, typ, choices
    return question, typ, choices[:8]
