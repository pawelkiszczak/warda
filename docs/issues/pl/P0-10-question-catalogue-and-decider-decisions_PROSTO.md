# P0-10 w prostych słowach: jakie pytania zadajemy modelowi, jak składamy z nich decyzję i co trzeba postanowić

> Uproszczona wersja zadania P0-10 dla osób spoza projektu albo nowych w temacie. Opiera się na polskim tłumaczeniu
> [`P0-10-question-catalogue-and-decider-decisions.md`](P0-10-question-catalogue-and-decider-decisions.md), a to na
> angielskim oryginale
> [`../P0-10-question-catalogue-and-decider-decisions.md`](../P0-10-question-catalogue-and-decider-decisions.md).
> Przy rozbieżności obowiązuje oryginał. Ten plik nie tłumaczy szczegółowo każdego pojęcia. Przy trudniejszych
> miejscach podaje, **co warto sprawdzić**.

## W jednym akapicie

Warda to mały model, który przed wysłaniem tekstu przez asystenta AI decyduje: przepuść, zamaskuj, zapytaj człowieka
albo zablokuj. Zamiast jednego wielkiego pytania „co zrobić?” można zadać modelowi kilka mniejszych, np. „czy są tu
dane o zdrowiu?”, „czy polityka obejmuje ten przypadek?”, a potem złożyć z odpowiedzi decyzję zwykłym kodem. To
zadanie spisuje **katalog tych pytań**, **przepis na składanie** odpowiedzi w decyzję, **listę faktów**, które
liczy kod (a nie model), oraz **12 decyzji projektowych** do podjęcia przez zespół.

## Zanim zaczniesz

- Przeczytaj najpierw wersję prostą zadania P0-09:
  [`P0-09-use-cases-and-scenario-matrix_PROSTO.md`](P0-09-use-cases-and-scenario-matrix_PROSTO.md). Ma pełny
  słowniczek podstawowych pojęć (decydent, ładunek, miejsce docelowe, polityka, bramka, poziom, gold, RODO itd.).
  Tutaj są tylko pojęcia nowe.
- Przejrzyj w P0-09 sekcję „Macierz zastosowań decyzji”. Identyfikatory `D-PII-xx`, `D-SEC-xx`, `D-POL-xx` i
  `S-xx` pochodzą stamtąd.
- `pretrain/HARNESS_DECIDER_PLAN.md`, sekcja 10 („Słowniczek”) i `FINDINGS.md` §1 (oceny podejść; po angielsku).

## Nowe pojęcia w tym zadaniu

| Pojęcie | Co oznacza w tym dokumencie | Warto sprawdzić |
|---|---|---|
| katalog pytań, `Q-xx` | ponumerowana lista pytań, które zadajemy modelowi, z dokładnym brzmieniem i opcjami odpowiedzi | — |
| `question_id` | krótka nazwa pytania używana w danych, np. `special_category` | `pretrain/harness/pii_gen.py` (słownik `QUESTION`) |
| pytanie cząstkowe | małe pytanie (tak/nie albo wybór z listy), z którego potem składa się główną decyzję | — |
| składanie (composition), kompozytor | zwykły kod, który z odpowiedzi cząstkowych i tabeli polityki wylicza decyzję | sekcja „Składanie” poniżej |
| fakty deterministyczne | informacje policzone przez kod, nie przez model, np. „dziś jest przed datą embarga” | sekcja „Fakty” poniżej |
| stan (state) | wszystko, co model dostaje na wejściu: fragment polityki, kanał, miejsce, tekst i fakty | `pretrain/prompt.py` |
| resolver | część systemu, która rozpoznaje miejsce docelowe (np. „to adres Sentry, usługa SaaS”) | zadanie P2-03 |
| śledzenie pochodzenia | zapis, skąd pochodzą dane (produkcja, testy, repo innego klienta) | zadanie P4-07 |
| klauzula | jeden punkt polityki, np. „§3.2” | — |
| tabela polityki | uproszczona postać polityki: kategoria danych × miejsce docelowe → decyzja | — |
| `pii_gen` | generator syntetycznych przykładów w tym repo; dziś zadaje 8 typów pytań | `pretrain/harness/pii_gen.py` |
| `sft.py`, SFT | skrypt douczania modelu na przykładach decyzji (*supervised fine-tuning*) | `pretrain/sft.py`; hasło „supervised fine-tuning” |
| `prompt.py` | skrypt, który zamienia przykład w tekst pytania dla modelu; jego format musi pasować do `sft.py` | `AGENTS.md`, „Key contracts” |
| odczyt wskaźnikowy / literowy (pointer / letter) | dwa sposoby odczytania, którą opcję wybrał model: wskazanie opcji albo litera „A/B/C” | `AGENTS.md` („Readout”) |
| temperatura (kalibracji) | jedna liczba, którą skaluje się pewność modelu, żeby „80 %” znaczyło ~80 % trafień | hasło „temperature scaling calibration” |
| grupa kalibracji | zbiór przykładów, dla którego osobno ustawia się kalibrację (np. jedno pytanie w jednym języku) | — |
| `cal`, `dev` | części danych: do ustawiania kalibracji / do bieżących prób | `AGENTS.md` |
| źródło gold | skąd bierze się poprawna odpowiedź: z tabeli (`table`), z modelu sprawdzonego dwa razy (`verified-llm`), od człowieka (`human`), z zewnętrznego zbioru | — |
| ADR | krótki plik zapisujący decyzję projektową: opcje, wybór, powody, kiedy wrócić do tematu | zadanie P0-07 |
| `accepted` / `proposed` | status ADR: przyjęty / zaproponowany z tymczasowym ustawieniem | j.w. |
| taksonomia | lista kategorii; dziś jest ich 7 (np. `direct_pii`, `credential`) | `warda/schema.py` |
| TOML | prosty format plików konfiguracyjnych | hasło „TOML” |
| pseudokod | opis algorytmu krok po kroku, bez konkretnego języka programowania | — |
| głowica (head) | mała dodatkowa część modelu do konkretnego zadania | hasło „multi-head model” |
| logowanie | zapis zdarzenia do dziennika (logu) | — |
| eksfiltracja | wykradanie danych na zewnątrz | — |

**Uwaga na zapisy.** `P1`/`P2`/`P3` samodzielnie to priorytety (P1 = potrzebne do bramki 3). `P1-03`, `P2-03` itp.
to identyfikatory zadań. `DEC-xx` to decyzje z tego pliku, a `D-xx` to punkty decyzji z P0-09.

## Odwołania do innych zadań

| Zadanie | O czym jest |
|---|---|
| P0-06 | sposób oceniania i program do benchmarków; ma raportować wyniki osobno dla każdego pytania |
| P0-07 | zapis decyzji jako ADR-y i szablon ADR |
| P0-09 | przypadki użycia, scenariusze i macierz zastosowań, na której opiera się to zadanie |
| P1-01 | detektory poziomu 1 (numery, hasła) |
| P1-03, P2-02 | nowe rodzaje danych treningowych dla nowych pytań |
| P1-08 | realistyczne polityki; mają dostać identyfikatory klauzul |
| P1-10 | ręcznie pisany zestaw testowy; dostanie poprawne odpowiedzi dla każdego pytania |
| P2-03 | resolver i plik konfiguracji polityki, czyli producent wielu faktów |
| P2-04, P3-03 | usługa decyzyjna i w niej kompozytor |
| P3-01 | trening modelu na nowej mieszance danych |
| P3-02 | pasma pewności per miejsce docelowe |

## Kontekst: po co to zadanie

P0-09 wskazało, gdzie model decyzyjny ma pomagać, i zostawiło cztery otwarte pytania. To zadanie zamienia tamtą
listę w coś, na czym mogą pracować zespoły danych, treningu i testów.

Co już istnieje:

- generator `pii_gen` zadaje 8 typów pytań na każdy przykład (decyzja, kategoria, czy przepływ dozwolony, czy jest
  bezpośredni identyfikator, czy tekst wskazuje osobę, czy są dane szczególne, czy jest hasło, czy są poufne dane
  firmy);
- `sft.py` uczy model wszystkich naraz i ustawia kalibrację dla każdego typu pytania;
- model odpowiada od razu na pytanie o decyzję. Nic nie składa decyzji z mniejszych odpowiedzi, nie podaje modelowi
  policzonych faktów ani nie wskazuje klauzuli polityki;
- `FINDINGS.md` §1 pokazało, że model nie radzi sobie z liczeniem, datami i progami.

Bez tego zadania kilka innych (P1-03, P2-03, P3-01, P3-02, P0-06) wymyślałoby własne listy pytań.

## Zakres

Robi:

- zamrożony katalog pytań v1 (`Q-xx`): dokładne brzmienie i opcje po polsku i angielsku, co musi być w stanie, jakie
  fakty są potrzebne, skąd poprawna odpowiedź, kto z niej korzysta i któremu punktowi z P0-09 służy;
- regułę składania odpowiedzi w decyzję i uzasadnienie;
- listę faktów liczonych przez kod;
- ADR-y dla 12 decyzji `DEC-01`…`DEC-12`;
- tabelę wpływu: które inne zadania się zmieniają. Ich pliki poprawia się w tym samym PR.

Nie robi: generowania danych, treningu, budowy kompozytora ani zmian w `prompt.py` / `sft.py`. Jeśli decyzja wymaga
takiej zmiany, powstaje osobne zadanie.

## Rezultaty: jakie pliki powstaną

Tych plików jeszcze nie ma; to zadanie ma je utworzyć.

- `docs/decider/QUESTIONS.md`: katalog, po jednej podsekcji na pytanie, z kompletem pól (nazwa, domena, priorytet,
  teksty PL/EN, wymagane dane i fakty, źródło odpowiedzi, grupa kalibracji, odbiorca, miara w teście, status
  `existing` / `new` / `deferred`, czyli istniejące / nowe / odłożone).
- `data/questions/catalogue.toml`: ten sam katalog w formie czytelnej dla programów, żeby brzmienie pytań było w
  jednym miejscu.
- `docs/decider/COMPOSITION.md`: kolejność kroków, tabela składania, pseudokod, zasady na wypadek konfliktów i
  przykłady, po jednym dla każdej rodziny scenariuszy S-01…S-10.
- `docs/decider/FACTS.md`: lista faktów: nazwa, typ, kto ją liczy, jak wygląda w tekście dla modelu i co robić, gdy
  fakt jest nieznany.
- `docs/decisions/ADR-0007…`: ADR-y dla decyzji.
- `docs/decider/IMPACT.md`: zadanie → co się w nim zmienia.

## Decyzje do podjęcia (DEC-01…DEC-12)

Każda ma propozycję ustawienia domyślnego do dyskusji.

| Id | Pytanie w prostych słowach | Propozycja |
|---|---|---|
| DEC-01 | Co obejmuje pierwsza wersja? Tylko dane osobowe i politykę, czy też wykrywanie haseł i luk bezpieczeństwa, czy dodatkowo zgodę na ryzykowne polecenia? | dane osobowe + polityka + hasła i luki; ryzykowne polecenia rozważyć przy bramce 2 |
| DEC-02 | Skąd bierze się decyzja: model odpowiada wprost, kod składa ją z pytań cząstkowych, czy oba? | oba: kod składa, gdy tabela polityki jasno rozstrzyga; model odpowiada wprost, gdy polityka ma wyjątki. Zawsze pytamy też model wprost, a niezgodność traktujemy jako sygnał niepewności |
| DEC-03 | Jeden model do wszystkich pytań czy kilka? | jeden; dzielić tylko wtedy, gdy jedna dziedzina psuje drugą o > 2 punkty procentowe |
| DEC-04 | Jak odczytywać odpowiedź i ile opcji dawać? Czy dawać opcję „nie wiem”? | odczyt wskaźnikowy; bez „nie wiem” (niepewność wynika z pewności i pasm); najwyżej 7 opcji, przy wyborze klauzuli najwyżej 12 + „żadna” |
| DEC-05 | Które fakty policzone przez kod podajemy modelowi? | minimalny zestaw z `FACTS.md`; każdy fakt musi mieć kod, który go liczy |
| DEC-06 | Jak dzielić politykę na klauzule? | autor polityki nadaje klauzulom identyfikatory; awaryjnie automatyczny podział po nagłówkach; klauzula ≤ 60 słów |
| DEC-07 | Czy każde pytanie dostaje to samo wejście? | tak, wspólny rdzeń ≤ ~1000 tokenów; długą politykę przycina się do istotnych klauzul |
| DEC-08 | Jak szczegółowo ustawiać kalibrację? | osobno dla każdego pytania i języka; łączyć małe grupy (< 300 przykładów) |
| DEC-09 | Skąd poprawne odpowiedzi dla każdego pytania? | z tabeli, gdzie się da; z modelu sprawdzonego dwa razy dla pytań o treść; tylko od ludzi dla pytań o klauzule, wyjątki i konflikty |
| DEC-10 | Czy zmienić listę 7 kategorii (np. podzielić „poufne dane firmy” na bezpieczeństwo, dane klienta, tajemnicę branżową)? | dzielić tylko, jeśli przykłady z P0-09 pokażą, że polityki traktują te części różnie |
| DEC-11 | Czy zostawić w treningu publiczne dane z decyzjami w stylu Jev? | zostawić (dobrze wypadły w `FINDINGS.md` §1), ale porównać wyniki z nimi i bez nich |
| DEC-12 | Jak pisać uzasadnienie decyzji? | szablon „klauzula: streszczenie klauzuli; rozstrzygający fakt”, bez tekstu pisanego swobodnie przez model |

**Warto sprawdzić:** w `FINDINGS.md` §1 wiersze o „Jev-style public decision data” (DEC-11) i „Calibration on real
text” (DEC-08); w `AGENTS.md` akapit o odczycie `pointer` vs `letter` (DEC-04).

## Katalog pytań v1 (szkic)

„Istniejące” = generator `pii_gen` już je zadaje. P1 = potrzebne do bramki 3, P2 = do bramki 4.

| Q | Pytanie w prostych słowach | Odpowiedzi | Status | Prio |
|---|---|---|---|---|
| Q-01 | Co zrobić z tym tekstem? | przepuść / zamaskuj / zapytaj / zablokuj | istniejące | P1 |
| Q-02 | Jakiej kategorii są dane? | 7 kategorii | istniejące | P1 |
| Q-03 | Czy polityka pozwala na ten przepływ? | tak / nie | istniejące | P1 |
| Q-04 | Czy jest tu bezpośredni identyfikator (np. imię i nazwisko, adres)? | tak / nie | istniejące | P1 |
| Q-05 | Czy tekst wskazuje konkretną osobę? | tak / nie | istniejące | P1 |
| Q-06 | Czy są dane szczególne (zdrowie, wyroki itd.)? | tak / nie | istniejące | P1 |
| Q-07 | Czy jest tu hasło lub klucz? | tak / nie | istniejące | P1 |
| Q-08 | Czy są poufne dane firmy? | tak / nie | istniejące | P1 |
| Q-09 | Jaki to sekret? | prawdziwy / przykład z dokumentacji / testowy / to nie sekret | nowe | P1 |
| Q-10 | Skąd są te dane? | testowe / produkcja / niejasne | nowe | P1 |
| Q-11 | Która klauzula polityki rozstrzyga? | lista klauzul + „żadna” | nowe | P1 |
| Q-12 | Czy ma zastosowanie wyjątek? | tak / nie | nowe | P1 |
| Q-13 | Czy polityka w ogóle obejmuje ten przypadek? | tak / nie | nowe | P1 |
| Q-14 | Czy dane jednego klienta idą do drugiego? | tak / nie | nowe | P1 |
| Q-15 | Czy poprawiony (zamaskowany) tekst jest bezpieczny? | tak / nie | nowe | P1 |
| Q-16 | Czy tekst ujawnia lukę bezpieczeństwa? | tak / nie | nowe (albo część Q-08) | P1 |
| Q-17 | Czy w tekście jest polecenie skierowane do strażnika? | tak / nie | nowe | P2 |
| Q-18 | Czy cel użycia danych jest zgodny z polityką? | tak / nie | nowe | P2 |
| Q-19 | Co zrobić z danymi przychodzącymi? | przepuść / zamaskuj | nowe | P2 |
| Q-20 | Czy pozwolić na ryzykowne polecenie? | pozwól / zapytaj / odmów | odłożone | P2 |
| Q-21 | Jakiego rodzaju jest nieznane miejsce docelowe? | 5 klas + eksfiltracja | odłożone | P2 |
| Q-22 | Co zrobić z polem w logu? | wyślij / zahaszuj / usuń | odłożone | P2 |

Punkty z P0-09 o najniższym priorytecie (P3) nie dostają pytań w pierwszej wersji. W `QUESTIONS.md` są zapisane jako
odłożone, z podaniem powodu.

**Warto sprawdzić:** czym jest haszowanie (hasło „funkcja skrótu”), bo dotyczy Q-22.

## Składanie: jak z odpowiedzi powstaje decyzja

1. **Najpierw zwykły kod (poziom 1).** Znalezione prawdziwe hasło → `block` albo bezpieczne zamaskowanie, bez
   dyskusji. Wyjątek: jeśli Q-09 z bardzo dużą pewnością mówi „to przykład z dokumentacji”, można przepuścić, ale to
   się zapisuje.
2. **Resolver** ustala, dokąd idzie tekst, a **śledzenie pochodzenia**, skąd są dane. **Kod liczy fakty.**
3. **Pytania o treść** (Q-02, Q-04…Q-08, Q-10, Q-14, Q-16) dają kategorię. Gdy pasuje kilka, wygrywa najsurowsza.
4. **Krok polityki:**
   - polityka nie obejmuje przypadku (Q-13 = nie) → `ask_user`;
   - w przeciwnym razie Q-11 wybiera klauzulę, a jeśli klauzula ma wyjątek, rozstrzyga Q-12;
   - jeśli tabela polityki jasno rozstrzyga i nie ma wyjątku → decyzja z tabeli;
   - w przeciwnym razie decyduje model wprost (Q-01).
5. **Niezgodność** między decyzją z tabeli a odpowiedzią modelu wprost obniża pewność i jest zapisywana.
6. **Pasma pewności** dla danego miejsca zamieniają decyzję i pewność na to, co faktycznie się stanie. `redact`
   wymaga, żeby Q-15 potwierdziło bezpieczeństwo poprawionego tekstu; inaczej wychodzi `block`.
7. **Uzasadnienie** powstaje z szablonu (DEC-12).

## Fakty: co liczy kod, a nie model

| Fakt | Kto liczy | Przykład tego, co widzi model |
|---|---|---|
| znalezione numery i hasła | detektory poziomu 1 | „PESEL (poprawna suma kontrolna) ×1, e-mail ×2” |
| rodzaj i nazwa miejsca docelowego | resolver (P2-03) | „Sentry (SaaS, umowa powierzenia: tak)” |
| czy usługa jest na liście podmiotów przetwarzających | konfiguracja polityki | „na liście: tak” |
| skąd są dane i od którego klienta | śledzenie pochodzenia | „z repozytorium klienta Bursztyn Bank” |
| dokąd idą (który klient) | resolver | „klient docelowy: Nordwind Energie” |
| czy trwa embargo | zegar + konfiguracja | „embargo »Kompas«: aktywne do 2026-11-15” |
| najmniejsza liczba osób w tekście vs próg | kod czytający liczby | „najmniejsza liczba: 3 (próg w polityce: 10)” |
| czy komunikat o luce jest już publiczny | konfiguracja / lista CVE | „komunikat opublikowany: nie” |
| region przetwarzania | resolver | „region: USA (polityka: tylko EOG)” |
| co już wysłano w tej sesji | rejestr sesji (później) | „wysłano już: stanowisko, biuro” |

Nieznany fakt pokazuje się jako `unknown` („nieznane”), nigdy się go nie pomija. W danych treningowych są przykłady z
`unknown`, żeby model nie uznawał braku informacji za dobry znak.

Firmy w przykładach (Bursztyn Bank, Nordwind Energie, projekt „Kompas”) są wymyślone.

## Kiedy zadanie jest skończone

- `QUESTIONS.md` i `catalogue.toml` są zgodne. Każdy punkt P1 z P0-09 ma pytanie P1 albo jest odłożony z podaniem
  powodu.
- `COMPOSITION.md` ma co najmniej 10 przykładów składania (po jednym na rodzinę S-01…S-10), które da się odtworzyć
  ręcznie.
- `FACTS.md` dla każdego faktu wskazuje zadanie, które zbuduje kod liczący go.
- ADR-y dla DEC-01…DEC-12 są omówione na jednym spotkaniu (zespół modelu, danych, benchmarków i osoba od RODO). Każdy
  jest przyjęty albo zaproponowany z datą powrotu do tematu.
- Pliki zadań P1-03, P2-03, P3-01, P3-02, P0-06 i P1-10 są poprawione, a sprawdzenie katalogu zadań
  (`issues_sync.py lint`) przechodzi.
- Jeśli decyzje wymagają zmian w `prompt.py` lub `sft.py`, jest na to osobne zadanie, a nie cicha zmiana.

## Testy automatyczne

- `warda/tests/test_questions.py` sprawdzi, że plik katalogu się wczytuje, identyfikatory są unikalne i zgadzają się
  z dokumentem, istniejące pytania mają te same teksty co w `pii_gen`, wymagane fakty są opisane w `FACTS.md`, a
  żadne pytanie nie ma za dużo opcji.
- Osobny test sprawdzi przepis na składanie na spisanych przykładach, bez modelu. Później tę samą listę musi przejść
  prawdziwy kompozytor.

## Dokumentacja do zaktualizowania

Nowe pliki: `QUESTIONS.md`, `COMPOSITION.md`, `FACTS.md` i ADR-y (plus indeks ADR-ów). Linki do nich trzeba dodać w
`README.md`, `AGENTS.md` oraz w dokumentach z P0-09 i P0-06.

## Test ręczny przed PR

1. Weź 5 przykładów z P0-09 (z rodzin S-01, S-02, S-06, S-08, S-10). Odpowiedz ręcznie na każde pytanie i złóż
   decyzję według `COMPOSITION.md`. Wynik ma się zgodzić z poprawną odpowiedzią. Każda niezgodność to poprawka
   dokumentu albo przykładu.
2. Osoba z zespołu modelu, która nie pisała katalogu, generuje tekst jednego istniejącego i jednego nowego pytania
   przez `prompt.py` i sprawdza, że format pasuje do `sft.py`.
3. Osoba od RODO czyta DEC-02, DEC-09 i DEC-12 i potwierdza, że audytor mógłby przejść od uzasadnienia decyzji do
   konkretnej klauzuli polityki.
