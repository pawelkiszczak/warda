# Warda — lokalny strażnik danych dla agentów programistycznych — plan

## 1. Cel

Agenci programistyczni (Claude Code, Codex, Cursor, OpenCode i inne) sami wysyłają treści na zewnątrz: commity, PR-y,
komentarze w zgłoszeniach, wiadomości na czacie, zapytania do wyszukiwarki, prompty do modeli w chmurze. Mogą przy tym
wyciec:

- dane osobowe (imię i nazwisko, PESEL, e-mail, telefon, adres, konto);
- dane wrażliwe (zdrowie, religia, związki zawodowe, karalność);
- hasła, klucze, tokeny;
- poufne informacje firmy (umowy, incydenty, plany, infrastruktura);
- połączenia niewinnych szczegółów wskazujące konkretną osobę („jedyna księgowa w biurze w Opolu, która wczoraj
  złożyła wypowiedzenie”). Tego nie wyłapie żaden regex.

Budujemy **od zera własny, mały model decyzyjny**, działający lokalnie. Przed wysłaniem treści czyta politykę danych
firmy, miejsce docelowe i treść. Decyduje: **zezwól / zamaskuj / zapytaj użytkownika / zablokuj**, z podaną pewnością.
Inspiracja: modele decyzyjne, które wybierają jedną z podanych odpowiedzi zamiast generować tekst. Model, dane
i narzędzia tworzymy sami.

Dlaczego:

- **Lokalnie.** Wysłanie podejrzanych danych do zewnętrznej usługi samo jest wyciekiem.
- **Polityka zwykłym tekstem.** Model ją czyta; nie trenujemy go osobno dla każdej firmy.
- **Znana pewność.** Pewne decyzje automatycznie, niepewne do człowieka.
- **Przewaga:** polski i RODO.

## 2. Co mamy

- **~24 tys. syntetycznych przykładów** (PL + EN), wyłącznie z wymyślonymi osobami i firmami.
  - Każdy ma bezpieczną wersję bez danych chronionych.
  - Ta sama treść dostaje różne decyzje zależnie od polityki i miejsca docelowego.
  - Część testu używa polityki niewidzianej w treningu. Sprawdza, czy model rozumie zasady.
- **Doświadczenie:** mały model trenowany od zera na jednym komputerze nauczył się prostych decyzji i dobrze oceniał
  swoją pewność. Znamy jego granice (np. liczenie dat).
- **Research:** potrzeba, konkurencja, ryzyka.
- **Narzędzie do labelowania** z liczeniem zgodności między osobami.

## 3. Bramki (kiedy idziemy dalej)

1. **Dane poprawne:** ręczna weryfikacja potwierdza ≥ 95% etykiet.
2. **Model się uczy:** bije proste rozwiązania („zawsze zezwól”, samo szukanie wzorców), radzi sobie z nową polityką.
3. **Działa na prawdziwych tekstach:** na ręcznym zbiorze wyłapuje ≥ 80% wycieków do miejsc publicznych przy ≤ 5%
   niepotrzebnych blokad.
4. **Działa w praktyce:** u testerów rzadkie fałszywe alarmy, szybkie działanie, realne wyłapania.

Bramka niezaliczona: poprawiamy dane lub model albo się zatrzymujemy.

## 4. Zespoły

Każdy zespół ma jednego właściciela. ~5 h tygodniowo na osobę. Jedna osoba może należeć do kilku zespołów.

- **Koordynacja (1):** plan, tablica zadań, decyzje na bramkach, łączenie wyników.
- **Dane ogólne (2–3):** duży zbiór tekstów PL, EN i programistycznych; licencje, czyszczenie. Mocny komputer.
- **Dane decyzyjne (1–2):** kolejne rundy przykładów syntetycznych pod wykryte braki. Mocny komputer.
- **Labelowanie (3–5):**
  - wytyczne z przykładami;
  - sprawdzanie przykładów syntetycznych;
  - ~300 realistycznych przykładów pisanych ręcznie, każdy oceniany przez dwie osoby.
- **Research (2–4):** istniejące rozwiązania, publikacje, realizm polityk (z osobą od RODO).
- **Benchmarki (2–3):** jeden wspólny sposób oceny, porównania z istniejącymi narzędziami.
- **Model i trening (2):** najważniejsza ścieżka. Trening od zera, nauka decyzji, kalibracja.
- **Narzędzia (2–3):** lokalna usługa z decyzjami, integracje z agentami, tryb cieniowy, przystosowanie narzędzia do
  labelowania.

**Szukamy też:**

- osoby od RODO (2–3 h tygodniowo);
- 3–5 testerów na ostatnią fazę;
- drugiej osoby do treningu jako zastępstwa.

Razem: **trzon 7–9 osób** plus osoba od RODO i testerzy.

### Zapisy

Wpisz się w kolumnie „Chętni”: nick, godziny tygodniowo, sprzęt (np. `pawix, 5 h, Mac 32 GB`). Właściciela wybieramy
spośród chętnych na pierwszym spotkaniu.

| Zespół | Ile osób | Sprzęt | Właściciel | Chętni (nick, h/tydz., sprzęt) |
|---|---|---|---|---|
| Koordynacja | 1 | laptop | | |
| Dane ogólne | 2–3 | mocny lub zdalny dostęp | | |
| Dane decyzyjne | 1–2 | mocny; mała skala na CPU | | |
| Labelowanie | 3–5 | laptop | | |
| Research | 2–4 | laptop | | |
| Benchmarki | 2–3 | laptop, darmowa chmura | | |
| Model i trening | 2 | mocny lub chmura | | |
| Narzędzia | 2–3 | laptop | | |
| Osoba od RODO | 1 | laptop | | |
| Zastępstwo: trening | 1 | mocny lub chmura | | |
| Testerzy (faza 5) | 3–5 | laptop z agentem | | |

## 5. Harmonogram (~4–5 miesięcy)

- **Faza 0, tyg. 1–2 — start.**
  - utworzenie `AGENTS.md` w repo; tablica zadań, właściciele, spis sprzętu.
  - Wytyczne labelowania; 100 przykładów sprawdzonych przez dwie osoby.
  - Wspólny sposób oceny, wyniki prostych rozwiązań.
  - **Bramka 1.**
- **Faza 1, tyg. 2–6 — dane i próby.**
  - Zbiór tekstów ogólnych.
  - Krótkie próbne treningi (wielkość modelu, ustawienia).
  - Przegląd rozwiązań i polityk.
  - Start ręcznego zbioru.
- **Faza 2, tyg. 6–10 — trening podstawowy.**
  - Trening od zera.
  - Druga runda danych decyzyjnych.
  - Szkielet lokalnej usługi i pierwszej integracji.
- **Faza 3, tyg. 10–13 — nauka decyzji.**
  - Trening decyzyjny, kalibracja.
  - Ręczny zbiór gotowy.
  - Pełne porównanie z istniejącymi rozwiązaniami.
  - **Bramki 2 i 3.**
- **Faza 4, tyg. 13–16 — integracje.**
  - Agenci z punktu 7.
  - Szybkość na zwykłych laptopach.
- **Faza 5, tyg. 16–20 — tryb cieniowy.**
  - 2–4 tygodnie u testerów, tylko zapis decyzji, bez blokowania.
  - Cotygodniowy przegląd.
  - Decyzja o publikacji. **Bramka 4.**

## 6. Narzędzia i sprzęt

Prawie wszystko darmowe i otwarte.

- **Wszyscy:** Discord, repo [github.com/pawelkiszczak/warda](https://github.com/pawelkiszczak/warda) (publiczne: żadnych
  danych ani sekretów), GitHub Projects jako tablica, dokumenty w Markdown w repo.
- **Kod:** Python 3.11+ z uv, Jupyter, pandas / DuckDB / pyarrow, pytest.
- **Trening:** MLX (Mac), PyTorch (NVIDIA), biblioteki Hugging Face, MLflow (lokalny zapis treningów). Opcjonalnie
  wynajem GPU (RunPod, Lambda, vast.ai).
- **Wnętrze modelu (pod przyszły pruning):** podgląd na żywo, które warstwy, głowice uwagi i eksperci najbardziej
  wpływają na decyzję.
  - nnsight, TransformerLens, pyvene: odczyt i podmiana aktywacji w trakcie działania modelu;
  - logit lens / tuned lens: co model „odpowiedziałby” po każdej warstwie;
  - Captum, Inseq: które fragmenty treści przesądziły o decyzji;
  - statystyki routera (jeśli model będzie typu MoE): którzy eksperci pracują, a którzy są zbędni;
  - metody przycinania do porównań: ShortGPT (usuwanie całych warstw), Wanda, SparseGPT, Torch-Pruning.
  - W MLX brak gotowej biblioteki: własne hooki na warstwach (kilkanaście linii).
- **Dane ogólne:**
  - źródła: SpeakLeash, FineWeb-2, HPLT (PL), FineWeb-Edu (EN), kod na licencjach pozwalających na trening;
  - fastText (rozpoznawanie języka), `datasketch` (duplikaty);
  - dysk na dziesiątki GB.
- **Dane decyzyjne:** lokalny serwer modeli (LM Studio, Ollama, llama.cpp), otwarte modele z Hugging Face, generator
  z repo (wznawialny, może chodzić całą noc).
- **Labelowanie:** nasza aplikacja w przeglądarce; zapas: Label Studio lub Argilla; arkusz do szybkich przeglądów.
- **Benchmarki:** wspólny skrypt oceny. Punkty odniesienia:
  - Microsoft Presidio;
  - GitGuardian ggshield (darmowe konto);
  - Bielik-Guard, Llama Prompt Guard;
  - modele decyzyjne w stylu Jev;
  - proste reguły.
- **Integracje:** lekki serwer HTTP (FastAPI / Starlette); formaty modelu MLX (Mac), GGUF (Linux / Windows),
  opcjonalnie Core ML.
- **Sprzęt:**
  - labelowanie, research, benchmarki, integracje: dowolny laptop;
  - generowanie danych: Mac z ≥ 64 GB lub NVIDIA z ≥ 24 GB;
  - trening od zera: Mac z 96–128 GB lub wynajęte GPU.
- **Słabszy sprzęt (zwykły laptop, 8–16 GB, bez GPU):** pełnoprawny udział.
  - Role bez wymagań sprzętowych: labelowanie, research, benchmarki, integracje, koordynacja, wytyczne.
  - Generowanie danych w małej skali: mniejsze, mocno skwantyzowane modele (np. 3–8B w GGUF przez llama.cpp lub
    Ollama) na CPU. Wolniej, ale generator jest wznawialny: paczka na noc, potem weryfikacja na mocniejszej maszynie.
  - Eksperymenty na małym modelu i wycinku danych, np. kilka tysięcy przykładów. Pomysł sprawdzony w małej skali
    puszczamy w dużej na mocnym sprzęcie.
  - Darmowe GPU w chmurze z limitem godzin: Kaggle Notebooks, Google Colab. Do krótkich treningów i ocen.
  - Zdalny dostęp do wspólnej mocnej maszyny (SSH / Tailscale), z kolejką zadań zamiast „kto pierwszy”.
  - **Testy szybkości na słabych laptopach są potrzebne:** strażnik ma działać u każdego, nie tylko na stacjach
    roboczych.
- **Zasada:** każdy skrypt da się uruchomić na CPU z flagą „mała próbka”. Mocny sprzęt przyspiesza pracę, ale nie
  jest warunkiem udziału.

## 7. Development agentowy

Projekt robimy z agentami programistycznymi i dla nich.

**Czym pracujemy:** Orca (wiele agentów równolegle, osobne worktree), Claude Code, Codex CLI, omp, OpenCode, Qwen Code,
Cursor, Gemini CLI. Każdy wybiera swojego; ważny jest wspólny kontrakt w repo.

**Kontrakt w repo (pliki do utworzenia w fazie 0):**

- `AGENTS.md` (i link `CLAUDE.md`): jak uruchomić testy, struktura repo, format danych, zakazy (prawdziwe dane,
  klucze w kodzie).
- Wspólne skille / prompty do powtarzalnych zadań: generowanie przypadków, przegląd etykiet, uruchomienie oceny.
- Jedno zadanie = jedna gałąź / worktree. Agenci nie wchodzą sobie w drogę.

**Zasady:**

- Agent pisze, człowiek przegląda. Mały PR, testy przechodzą przed scaleniem.
- Agent może proponować przypadki i etykiety. Ostateczna ocena przykładów wzorcowych należy do ludzi.
- Do promptów nie wklejamy kluczy ani danych z pracy. Przy danych wrażliwych lokalny model, np. Qwen Code z lokalnym
  Qwenem: darmowe i offline.

**Ci sami agenci to cele integracji.** Strażnik wpina się przez ich hooki / wtyczki. Claude Code, Codex i Cursor mają
hooki; omp i OpenCode mają rozszerzenia. Mechanizm pozostałych (Qwen Code, Gemini CLI, Orca) sprawdzamy w fazie 1.

**Dogfooding:** od fazy 4 strażnik działa w trybie cieniowym w naszych własnych agentach. Pierwszymi testerami
jesteśmy my.

## 8. Zasady pracy

- **Żadnych prawdziwych danych osobowych.** Tylko syntetyczne lub pisane ręcznie z wymyślonymi osobami. Bez danych
  z pracy i zapisów prawdziwych rozmów.
- **Dane i modele zostają u nas.**
- **Zadania 2–5 h**, każde z opisem „gotowe gdy…”.
- **Spotkanie co tydzień (30 min)** plus Discord. Decyzje zapisujemy w repo.
- **Przykłady wzorcowe oceniają zawsze dwie osoby.** Rozbieżności zapisujemy.
- **Jeden wspólny sposób oceny.**

## 9. Jak dołączyć

1. Wpisz się w tabelę zapisów (punkt 4). Na kanale napisz, jakiego agenta używasz.
2. Przeczytaj ten dokument oraz `AGENTS.md` (po jego utworzeniu w fazie 0).
3. Weź wolne zadanie swojego zespołu z tablicy.

## 10. Słowniczek

- **Agent programistyczny:** asystent AI, który sam edytuje kod, uruchamia polecenia i wysyła zmiany.
- **Hook:** skrypt uruchamiany przez agenta przed lub po akcji; może ją zatrzymać.
- **Model decyzyjny:** wybiera jedną z podanych odpowiedzi i mówi, na ile jest pewny.
- **Kalibracja:** „90% pewności” ma znaczyć ~90% trafnych decyzji.
- **Tryb cieniowy:** strażnik ocenia i zapisuje, nic nie blokuje.
- **Trening od zera:** model uczy się najpierw języka z dużego zbioru tekstów, potem decyzji.
- **Pruning:** usuwanie z modelu warstw, głowic lub ekspertów, które mało wnoszą. Model mniejszy i szybszy przy
  podobnej jakości.
- **Worktree:** osobna kopia robocza repo dla jednego zadania lub agenta.

## 11. Otwarte decyzje

- Jak mały może być model, żeby działał szybko na każdym laptopie i był skuteczny.
- Licencja i forma publikacji (otwarty model? sam zbiór?).
- Tylko macOS czy od razu Linux / Windows.
- Kto rozstrzyga spory w ocenie przykładów: koordynator czy osoba od RODO.
- Sprzęt do treningu: komputery uczestników czy wynajem.
