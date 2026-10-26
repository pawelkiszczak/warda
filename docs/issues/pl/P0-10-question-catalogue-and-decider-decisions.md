+++
id = "P0-10"
title = "Katalog pytań, składanie odpowiedzi i decyzje projektowe decydenta (z macierzy zastosowań decyzji z P0-09)"
labels = ["phase:0", "team:model", "type:decision", "gate:2"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-09", "P0-07"]
estimate_hours = 10
hardware = "laptop"
github_issue = 0
+++

> Polskie tłumaczenie pliku
> [`../P0-10-question-catalogue-and-decider-decisions.md`](../P0-10-question-catalogue-and-decider-decisions.md).
> Źródłem prawdy jest wersja angielska: przy rozbieżności obowiązuje ona, a każda zmiana tamtego pliku wymaga
> aktualizacji tłumaczenia. Identyfikatory, nazwy pól, wartości enumeracji, ścieżki i fragmenty kodu pozostawiono bez
> zmian.

## Kontekst

P0-09 dodaje macierz zastosowań decyzji (`D-PII-xx`, `D-SEC-xx`, `D-POL-xx`). Wskazuje ona, gdzie typowany model
decyzyjny (w stylu Jev: stan + pytanie + zamknięte opcje → jedna opcja ze skalibrowaną pewnością) powinien pomagać w
procesach dotyczących PII, bezpieczeństwa i sprawdzania polityk, i kończy się czterema otwartymi pytaniami. To
zadanie zamienia macierz w coś, na czym mogą budować zespoły danych, treningu i benchmarków. Zapisuje też decyzje,
które zmieniają pracę innych zespołów.

Co istnieje dziś:

- `pii_gen` emituje osiem typów pytań na przypadek: `action`, `category`, `flow_allowed`, `direct_identifier`,
  `singles_out_person`, `special_category`, `credential`, `confidential_business`.
- `sft.py` trenuje je łącznie z odczytem wskaźnikowym (pointer) i dopasowuje temperaturę per typ.
- `prompt.py` renderuje linie opcji, od których zależy `sft.py`.
- Model odpowiada bezpośrednio na `action`. Nic jeszcze nie składa `action` z odpowiedzi cząstkowych, nie używa
  deterministycznych faktów w stanie ani nie cytuje klauzuli polityki. FINDINGS §2 („Design settled”) wymaga
  typowanych pytań per klauzula polityki, a FINDINGS §1 mówi, że arytmetyka, daty i progi pozostają na poziomie
  losowym.

Bez tego zadania P1-03 (nowe rodzaje przypadków), P2-03 (resolver i fakty), P3-01 (mieszanka SFT), P3-02 (pasma) i
P0-06 (przekroje raportu) wymyślałyby każde własną listę pytań.

## Zakres

- Zamrożony **katalog pytań** v1 (`Q-xx`). Każdy wpis ma dokładne brzmienie i opcje po polsku i angielsku, wymagane
  pola stanu, wymagane fakty deterministyczne, źródło gold, grupę kalibracji, odbiorców oraz `D-xx` i `S-xx`, którym
  służy.
- **Reguła składania**: jak odpowiedzi cząstkowe, wyniki poziomu 1 i tabela polityki dają końcową akcję i
  uzasadnienie.
- **Kontrakt faktów deterministycznych**: które fakty oblicza kod i jak pojawiają się w stanie.
- ADR-y dla decyzji `DEC-01`…`DEC-12` poniżej. Każdy ADR ma status `accepted` albo `proposed` z tymczasowym
  ustawieniem domyślnym i jest zgodny z szablonem P0-07.
- Tabela wpływu: które istniejące zadania się zmieniają i jak. Ich pliki są edytowane w tym samym PR.
- Poza zakresem:
  - generowanie danych dla nowych pytań (P1-03, P2-02);
  - trening (P3-01);
  - implementacja kompozytora (P2-04, P3-03);
  - zmiana formatowania w `prompt.py` / `sft.py`. Jeśli decyzja tego wymaga, to zadanie zapisuje ją jako zadanie
    następcze.

## Rezultaty

- `docs/decider/QUESTIONS.md`: katalog, jedna podsekcja na `Q-xx`, z polami:
  - `question_id` (napis używany w JSONL elementów);
  - domena;
  - obsługiwane `D-xx` i `S-xx`;
  - priorytet;
  - tekst pytania i teksty opcji po polsku i angielsku, dokładnie tak, jak renderuje je `prompt.py`;
  - wymagane pola stanu;
  - wymagane fakty (klucze z `FACTS.md`);
  - źródło gold (`table` / `verified-llm` / `human` / `external:<set>`);
  - grupa kalibracji;
  - odbiorca (kompozytor, hook, raport, człowiek);
  - metryka i cel używane w benchu;
  - status (`existing` / `new` / `deferred`).
- `data/questions/catalogue.toml`: maszynowo czytelna postać tego samego katalogu (identyfikatory, opcje per język,
  wymagane pola, priorytet, status). Generatory i bench czytają z niego teksty opcji, więc brzmienie ma jedno źródło.
- `docs/decider/COMPOSITION.md`: kolejność ewaluacji, tabela składania i pseudokod, reguły rozstrzygania konfliktów
  i rozwiązań awaryjnych oraz sposób budowania napisu `reason`. Zawiera rozpisane przykłady dla co najmniej 10
  scenariuszy startowych z P0-09: po jednym na rodzinę S-01…S-10.
- `docs/decider/FACTS.md`: blok faktów. Dla każdego faktu: klucz, typ, producent (poziom 1, resolver, śledzenie
  pochodzenia, zegar, konfiguracja polityki), renderowanie po polsku i angielsku oraz co się dzieje, gdy fakt jest
  nieznany.
- `docs/decisions/ADR-0007…`: jeden ADR na `DEC-xx` albo zgrupowane tam, gdzie decyzje są nierozłączne. Każdy ADR
  podaje rozważane opcje, proponowane poniżej ustawienie domyślne, dowody lub eksperyment, który by je zmienił, oraz
  „Revisit when”.
- `docs/decider/IMPACT.md` (albo sekcja `COMPOSITION.md`): zadanie → zmiana. Edycje `P1-03`, `P2-03`, `P3-01`,
  `P3-02`, `P0-06` i `P1-10` trafiają do tego samego PR.

### Proponowana treść: decyzje do podjęcia

| Id | Decyzja | Opcje | Proponowane ustawienie domyślne (do dyskusji nad ADR) |
|---|---|---|---|
| DEC-01 | Zakres domenowy v1 | (a) tylko PII + polityka; (b) + ujawnienia bezpieczeństwa i ujednoznacznianie sekretów (`D-SEC-01/02`); (c) + bramka uprawnień narzędzi `D-SEC-03` | (b). Wrócić do (c) na bramce 2: ten sam hook, tanie pojedyncze tak/nie, ale inne dane |
| DEC-02 | Jak powstaje `action` | (a) model odpowiada bezpośrednio na `action`; (b) model odpowiada na pytania cząstkowe, kod składa wynik z tabeli polityki; (c) hybryda | (c): składać, gdy komórka tabeli jest zdefiniowana i nie ma otwartego pytania o wyjątek ani klauzulę; bezpośrednie `action`, gdy polityka ma wyjątki; zawsze dodatkowo przewidywać `action` i logować niezgodność jako sygnał niepewności |
| DEC-03 | Jeden model czy kilka | (a) jeden model, wszystkie `question_id`; (b) jeden na domenę; (c) jedna baza + małe głowice per domena | (a), co pokazał już łączny trening z `FINDINGS` §1. Dzielić tylko wtedy, gdy jedna domena pogarsza inną o > 2 pkt na dev |
| DEC-04 | Odczyt i opcje | pointer vs letter; „nie wiem” jako opcja czy tylko przez pewność; maksymalna liczba opcji | pointer (domyślny w `sft.py`); brak opcji „nie wiem” w pytaniach tak/nie, niepewność pochodzi z pasm; ≤ 7 opcji, z wyjątkiem wyboru klauzuli ≤ 12 + „żadna” |
| DEC-05 | Fakty deterministyczne w stanie | żadne / minimalny zestaw / wszystko, co kod może wiedzieć | minimalny zestaw z `FACTS.md` poniżej; każdy fakt musi mieć producenta, który istnieje do czasu P2-04 |
| DEC-06 | Segmentacja polityki na potrzeby pytań o klauzule | znaczniki autora w pliku polityki / automatyczny podział według nagłówków i punktów / oba | front matter z P1-08 dostaje identyfikatory klauzul; awaryjnie automatyczny podział ze stabilnymi identyfikatorami; tekst klauzuli ≤ 60 słów |
| DEC-07 | Budżet stanu per pytanie | ten sam stan dla wszystkich / podzbiory per pytanie | ten sam rdzeń stanu (fragment polityki, kanał, miejsce docelowe, ładunek, fakty) ≤ 1 tys. tokenów; dłuższą politykę resolver przycina do istotnych klauzul; ładunek dzielony na fragmenty zgodnie z A-11 |
| DEC-08 | Granulacja kalibracji | per pytanie / × język / × klasa miejsca docelowego | per pytanie × język; klasa miejsca docelowego wchodzi przez pasma (P3-02). Łączyć grupy z < 300 elementami `cal` |
| DEC-09 | Źródło gold per pytanie | tabela / dwuprzebiegowa weryfikacja przez LLM / człowiek | tabela dla `action`/`flow_allowed` tam, gdzie jest zdefiniowana; zweryfikowany LLM dla pytań o treść; wyłącznie człowiek dla pytań o klauzulę, wyjątek i konflikt na zestawie ręcznym |
| DEC-10 | Taksonomia kategorii v2 | zachować 7 / podzielić `confidential_business` na `security_posture`, `client_confidential`, `sector_secret` / dodać `pseudonymous` | podzielić `confidential_business` tylko wtedy, gdy zestaw startowy z P0-09 pokaże, że polityki traktują te części różnie; w przeciwnym razie zachować 7 i użyć osobnych pytań tak/nie |
| DEC-11 | Publiczne dane z typowanymi decyzjami w mieszance | zachować obecną łączną mieszankę w stylu Jev / przefiltrować do pokrewnych zadań / usunąć | zachować (FINDINGS §1 ★★★★), ale w P3-01 raportować dev per pytanie z nimi i bez nich |
| DEC-12 | Tekst uzasadnienia | generowany / szablon z rozstrzygającej klauzuli + faktów / brak | szablon: `"{clause_id}: {clause summary}; {decisive fact}"`; w v1 bez generowanego tekstu |

### Proponowana treść: katalog pytań v1 (szkic)

`existing` = już emitowane przez `pii_gen`. P1 = potrzebne do bramki 3.

| Q | `question_id` | Obsługuje | Opcje | Źródło gold | Status | Prio |
|---|---|---|---|---|---|---|
| Q-01 | `action` | D-PII-01 | allow / redact / ask_user / block | tabela albo człowiek dla wyjątków | existing | P1 |
| Q-02 | `category` | D-PII-02, D-PII-08 | 7 kategorii (DEC-10) | verified-llm | existing | P1 |
| Q-03 | `flow_allowed` | D-POL-01 | tak / nie | tabela | existing | P1 |
| Q-04 | `direct_identifier` | D-PII-01 (zabezpieczenie poziomu 1 dla imion i nazwisk/adresów bez sum kontrolnych) | tak / nie | verified-llm | existing | P1 |
| Q-05 | `singles_out_person` | D-PII-03 | tak / nie | verified-llm + człowiek na zestawie ręcznym | existing | P1 |
| Q-06 | `special_category` | D-PII-04 | tak / nie | verified-llm | existing | P1 |
| Q-07 | `credential` | D-SEC-01 (po trafieniu poziomu 1) | tak / nie | verified-llm | existing | P1 |
| Q-08 | `confidential_business` | D-SEC-02, D-POL-08 | tak / nie | verified-llm | existing | P1 |
| Q-09 | `secret_kind` | D-SEC-01 | prawdziwy / udokumentowany przykład / wartość testowa / nie sekret | generator + korpus poziomu 1 | new | P1 |
| Q-10 | `record_provenance` | D-PII-05 | fixture / produkcja / niejasne | generator (pole pochodzenia) | new | P1 |
| Q-11 | `governing_clause` | D-POL-02, uzasadnienie (DEC-12) | identyfikatory klauzul polityki + „żadna” | człowiek (zestaw ręczny), generator dla tabel | new | P1 |
| Q-12 | `exception_applies` | D-POL-03 | tak / nie | człowiek | new | P1 |
| Q-13 | `policy_covers` | D-POL-05 | tak / nie | generator (przypadki milczenia) + człowiek | new | P1 |
| Q-14 | `cross_client` | D-POL-07 | tak / nie | generator ze skażeniem pochodzenia | new | P1 |
| Q-15 | `rewrite_safe` | D-PII-07 | tak / nie | przepisania rozstrzygnięte przez ludzi (P1-10) | new | P1 |
| Q-16 | `security_disclosure` | D-SEC-02 | tak / nie | verified-llm | new (albo włączone do Q-08, DEC-10) | P1 |
| Q-17 | `guard_instruction` | D-SEC-06, S-13 | tak / nie | generator | new | P2 |
| Q-18 | `purpose_ok` | D-POL-06 | tak / nie | człowiek | new | P2 |
| Q-19 | `inbound_action` | D-PII-06 | przepuść / redact | tabela na elementach przychodzących (kanały przychodzące `pii_gen`) | new | P2 |
| Q-20 | `tool_risk` | D-SEC-03 | pozwól / zapytaj / odmów | zewnętrzne + generator | deferred (DEC-01) | P2 |
| Q-21 | `destination_class` | D-SEC-05 | 5 klas + eksfiltracja | generator na listach URL/hostów | deferred | P2 |
| Q-22 | `field_disposition` | D-PII-09 | wyślij / zahaszuj / usuń | generator na schematach logów | deferred | P2 |

Wiersze P3 macierzy (`D-PII-10`, `D-SEC-07/08`, `D-POL-11`) nie dostają pytania w v1. Są wymienione w `QUESTIONS.md`
jako `deferred` z podaniem powodu.

### Proponowana treść: składanie (szkic do `COMPOSITION.md`)

1. Najpierw działa poziom 1. Trafienie poprawnych danych uwierzytelniających → `block` / zweryfikowany `redact`,
   ostatecznie (A-03). Q-09 może obniżyć trafienie poziomu 1 do `allow` tylko wtedy, gdy odpowiedź to `documented
   dummy` powyżej najostrzejszego pasma, a takie obniżenie jest logowane.
2. Resolver podaje klasę miejsca docelowego i nazwane miejsce docelowe. Śledzenie pochodzenia podaje źródło i
   klienta. Kod oblicza fakty.
3. Pytania o treść Q-02, Q-04…Q-08, Q-10, Q-14 i Q-16 → efektywna kategoria. Gdy pasuje kilka, wygrywa najbardziej
   restrykcyjna komórka.
4. Krok polityki:
   - Q-13 `policy_covers = no` → `ask_user` (A-07);
   - w przeciwnym razie Q-11 wybiera klauzulę;
   - jeśli klauzula ma wyjątek, decyduje Q-12;
   - jeśli komórka tabeli jest zdefiniowana i nie ma zastosowania żaden wyjątek → akcja złożona (DEC-02);
   - w przeciwnym razie Q-01 decyduje bezpośrednio.
5. Niezgodność między akcją złożoną a Q-01 obniża pewność według reguły dopasowanej na `cal` i jest logowana.
6. Pasma per klasa miejsca docelowego (P3-02) zamieniają (akcja, pewność) na egzekwowany wynik. `redact` wymaga
   Q-15 = tak dla wytworzonego przepisania, w przeciwnym razie staje się `block` (A-04).
7. Uzasadnienie = szablon z DEC-12.

### Proponowana treść: kontrakt faktów (szkic do `FACTS.md`)

| Klucz faktu | Producent | Przykładowe renderowanie (EN) |
|---|---|---|
| `tier1_hits` | detektory poziomu 1 | `tier-1: PESEL (valid checksum) ×1, e-mail ×2` |
| `dest_class`, `dest_name` | resolver (P2-03) | `destination: Sentry (saas, processor with DPA: yes)` |
| `processor_listed` | konfiguracja polityki | `listed processor: yes` |
| `source`, `source_client` | śledzenie pochodzenia | `draws on: client_repo Bursztyn Bank` |
| `target_client` | resolver | `target client: Nordwind Energie` |
| `today_vs_embargo` | zegar + konfiguracja polityki | `embargo "Kompas": active until 2026-11-15` |
| `group_size_vs_threshold` | kod parsujący liczby w ładunku tam, gdzie to możliwe | `smallest count in text: 3 (policy threshold 10)` |
| `advisory_public` | konfiguracja / lista CVE | `advisory published: no` |
| `region` | resolver | `processing region: US (policy: EEA only)` |
| `session_disclosed` | rejestr (później, A-02) | `already sent to this destination in session: role, office` |

Nieznany fakt jest renderowany jako `unknown`, nigdy pomijany. Dane treningowe zawierają przypadki `unknown`, aby
model nie traktował brakujących faktów jako uspokajających.

## Definicja ukończenia

- [ ] `QUESTIONS.md` i `catalogue.toml` są zgodne (test poniżej). Każdy wiersz P1 macierzy z P0-09 jest obsługiwany
      przez co najmniej jedno pytanie P1 albo oznaczony jako deferred z podaniem powodu.
- [ ] `COMPOSITION.md` ma kolejność, tabelę i ≥ 10 rozpisanych przykładów, po jednym na rodzinę S-01…S-10, każdy
      możliwy do odtworzenia ręcznie z elementu startowego.
- [ ] `FACTS.md` wskazuje zadanie-producenta dla każdego faktu (P1-01, P2-03, P2-04 albo nowe zadanie)
- [ ] ADR-y dla DEC-01…DEC-12, omówione na jednym spotkaniu z rolami: model, decyzje o danych, benchmarki i RODO.
      Każdy ma status `accepted` albo `proposed` z tymczasowym ustawieniem domyślnym i datowanym warunkiem powrotu
      do decyzji.
- [ ] Edycje wynikające z wpływu są wykonane w `P1-03`, `P2-03`, `P3-01`, `P3-02`, `P0-06` i `P1-10` (nowe rodzaje,
      fakty, raportowanie mieszanki, grupy kalibracji, przekroje per `question_id`, pola gold per pytanie).
      `issues_sync.py lint` przechodzi.
- [ ] Jeśli DEC-04/06/12 wymagają zmian w promptach lub odczycie, istnieje zadanie następcze (żadnej cichej edycji
      `prompt.py` / `sft.py`)

## Testy automatyczne

- `warda/tests/test_questions.py`:
  - `catalogue.toml` się parsuje;
  - identyfikatory są unikalne i pasują do nagłówków w `QUESTIONS.md`;
  - każdy identyfikator `existing` jest kluczem w `pii_gen.QUESTION["en"]` i `["pl"]`, a teksty opcji zgadzają się z
    tym, co renderuje `pii_gen` (`YESNO`, `ACTION_TEXT`, `CATEGORY_TEXT`);
  - każdy wymagany klucz faktu istnieje w `FACTS.md`;
  - żadne pytanie nie ma więcej opcji niż limit z DEC-04.
- Test tabelaryczny pseudokodu składania na rozpisanych przykładach, jako zwykłe dane, bez modelu. Implementacja
  kompozytora w P2-04 musi później przejść te same przypadki.

## Dokumentacja

- `docs/decider/QUESTIONS.md`, `COMPOSITION.md`, `FACTS.md`, ADR-y; indeks `docs/decisions/README.md`.
- `README.md` „Contents” dodaje `docs/decider/` i `data/questions/`; w `AGENTS.md` „Key contracts” pojawia się
  katalog pytań jako źródło identyfikatorów pytań i tekstów opcji.
- `docs/bench/USE_CASES.md` (P0-09): wiersze macierzy linkują swoje `Q-xx`; `docs/bench/PROTOCOL.md` raportuje per
  `question_id`.

## Test manualny (człowiek, przed PR)

1. Weź 5 elementów startowych z P0-09 (z S-01, S-02, S-06, S-08, S-10). Wypełnij ręcznie każde pytanie, złóż wynik
   według `COMPOSITION.md` → rezultat równa się gold elementu startowego. Każda niezgodność poprawia albo dokument,
   albo zestaw startowy.
2. Osoba z zespołu modelu, która nie pisała katalogu, renderuje jedno pytanie `existing` i jedno `new` za pomocą
   `prompt.py` z tekstu w `catalogue.toml` i potwierdza, że linie opcji zgadzają się z oczekiwaniami `sft.py`.
3. Osoba od RODO czyta DEC-02, DEC-09 i DEC-12 i potwierdza, że audytor byłby w stanie prześledzić decyzję od jej
   napisu uzasadnienia do klauzuli polityki.
