+++
id = "P0-10"
title = "Question catalogue, answer composition and decider design decisions (from the P0-09 decision-use matrix)"
labels = ["phase:0", "team:model", "type:decision", "gate:2"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-09", "P0-07"]
estimate_hours = 10
hardware = "laptop"
github_issue = 0
+++

## Context

P0-09 adds a decision-use matrix (`D-PII-xx`, `D-SEC-xx`, `D-POL-xx`). It lists where a typed decision model
(Jev-style: state + question + closed options → one option with calibrated confidence) should help in PII, security
and policy-checking processes, and it ends with four open questions. This issue turns the matrix into something
data, training and benchmarks can build on. It also records the decisions that change the work of other teams.

What exists today:

- `pii_gen` emits eight question types per case: `action`, `category`, `flow_allowed`, `direct_identifier`,
  `singles_out_person`, `special_category`, `credential`, `confidential_business`.
- `sft.py` trains them jointly with a pointer readout and fits per-type temperature.
- `prompt.py` renders the option lines that `sft.py` depends on.
- The model answers `action` directly. Nothing yet composes `action` from sub-answers, uses deterministic facts in
  the state, or cites a policy clause. FINDINGS §2 ("Design settled") asks for typed questions per policy clause, and
  FINDINGS §1 says arithmetic, dates and thresholds stay at chance.

Without this issue, P1-03 (new case kinds), P2-03 (resolver and facts), P3-01 (SFT mix), P3-02 (bands) and P0-06
(report slices) would each invent their own question list.

## Scope

- A frozen v1 **question catalogue** (`Q-xx`). Each entry has its exact PL/EN wording and options, required state
  fields, required deterministic facts, gold source, calibration group, consumers, and the `D-xx` and `S-xx` it
  serves.
- The **composition rule**: how sub-answers, tier-1 results and the policy table give the final action and reason.
- The **deterministic facts contract**: which facts code computes and how they appear in the state.
- ADRs for the decisions `DEC-01`…`DEC-12` below. Each ADR is `accepted`, or `proposed` with an interim default, and
  follows the P0-07 template.
- An impact table: which existing issues change and how. Their files are edited in the same PR.
- Out of scope:
  - generating data for new questions (P1-03, P2-02);
  - training (P3-01);
  - implementing the composer (P2-04, P3-03);
  - changing `prompt.py` / `sft.py` formatting. If a decision requires it, this issue records it as a follow-up task.

## Deliverables

- `docs/decider/QUESTIONS.md`: the catalogue, one subsection per `Q-xx`, with these fields:
  - `question_id` (the string used in item JSONL);
  - domain;
  - served `D-xx` and `S-xx`;
  - priority;
  - PL and EN question text and option texts, exactly as rendered by `prompt.py`;
  - required state fields;
  - required facts (`FACTS.md` keys);
  - gold source (`table` / `verified-llm` / `human` / `external:<set>`);
  - calibration group;
  - consumer (composer, hook, report, human);
  - metric and target used in the bench;
  - status (`existing` / `new` / `deferred`).
- `data/questions/catalogue.toml`: the machine-readable form of the same catalogue (ids, options per language,
  required fields, priority, status). Generators and the bench read option texts from it, so the wording has a
  single source.
- `docs/decider/COMPOSITION.md`: the order of evaluation, the composition table and pseudocode, conflict and
  fallback rules, and how the `reason` string is built. It includes worked examples for at least 10 P0-09 seed
  scenarios: one per family S-01…S-10.
- `docs/decider/FACTS.md`: the facts block. For each fact: key, type, producer (tier 1, resolver, provenance tracker,
  clock, policy config), rendering in PL/EN, and what happens when it is unknown.
- `docs/decisions/ADR-0007…`: one ADR per `DEC-xx`, or grouped where they are inseparable. Each ADR states the
  options considered, the default proposed below, the evidence or experiment that would change it, and "Revisit
  when".
- `docs/decider/IMPACT.md` (or a section of `COMPOSITION.md`): issue → change. Edits to `P1-03`, `P2-03`, `P3-01`,
  `P3-02`, `P0-06` and `P1-10` go in the same PR.

### Proposed content: decisions to make

| Id | Decision | Options | Proposed default (for the ADR discussion) |
|---|---|---|---|
| DEC-01 | Domain scope of v1 | (a) PII + policy only; (b) + security disclosure and secret disambiguation (`D-SEC-01/02`); (c) + tool-permission gate `D-SEC-03` | (b). Revisit (c) at gate 2: same hook, cheap single yes/no, but different data |
| DEC-02 | How `action` is produced | (a) model answers `action` directly; (b) model answers sub-questions, code composes from the policy table; (c) hybrid | (c): compose when the table cell is defined and no exception or clause question is open; direct `action` when the policy has exceptions; always also predict `action` and log disagreement as an uncertainty signal |
| DEC-03 | One model or several | (a) one model, all `question_id`s; (b) one per domain; (c) one base + small per-domain heads | (a), as `FINDINGS` §1 joint training already showed. Split only if one domain degrades another by > 2 pts on dev |
| DEC-04 | Readout and options | pointer vs letter; "unsure" as an option or only via confidence; max option count | pointer (`sft.py` default); no "unsure" option on yes/no questions, uncertainty comes from bands; ≤ 7 options, except clause selection ≤ 12 + "none" |
| DEC-05 | Deterministic facts in the state | none / a minimal set / everything the code can know | minimal set from `FACTS.md` below; each fact must have a producer that exists by P2-04 |
| DEC-06 | Policy segmentation for clause questions | author markup in the policy file / automatic split by headings and bullets / both | P1-08 front matter gets clause ids; fall back to an automatic split with stable ids; clause text ≤ 60 words |
| DEC-07 | State budget per question | the same state for all / per-question subsets | the same core state (policy excerpt, channel, destination, payload, facts) ≤ 1k tokens; the policy is trimmed to the relevant clauses by the resolver when longer; payload chunking per A-11 |
| DEC-08 | Calibration granularity | per question / × language / × destination class | per question × language; destination class enters through the bands (P3-02). Merge groups with < 300 `cal` items |
| DEC-09 | Gold source per question | table / two-pass LLM verification / human | table for `action`/`flow_allowed` where defined; verified-LLM for content questions; human-only for clause, exception and conflict questions on the handwritten set |
| DEC-10 | Category taxonomy v2 | keep 7 / split `confidential_business` into `security_posture`, `client_confidential`, `sector_secret` / add `pseudonymous` | split `confidential_business` only if the P0-09 seed shows policies acting differently on the parts; otherwise keep 7 and use separate yes/no questions |
| DEC-11 | Public typed-decision data in the mix | keep the current Jev-style joint mix / filter it to related tasks / drop it | keep (FINDINGS §1 ★★★★), but report per-question dev with and without it in P3-01 |
| DEC-12 | Reason text | generated / template from the governing clause + facts / none | template: `"{clause_id}: {clause summary}; {decisive fact}"`; no generated text in v1 |

### Proposed content: question catalogue v1 (draft)

`existing` = already emitted by `pii_gen`. P1 = needed for gate 3.

| Q | `question_id` | Serves | Options | Gold source | Status | Prio |
|---|---|---|---|---|---|---|
| Q-01 | `action` | D-PII-01 | allow / redact / ask_user / block | table, or human for exceptions | existing | P1 |
| Q-02 | `category` | D-PII-02, D-PII-08 | 7 categories (DEC-10) | verified-llm | existing | P1 |
| Q-03 | `flow_allowed` | D-POL-01 | yes / no | table | existing | P1 |
| Q-04 | `direct_identifier` | D-PII-01 (tier-1 backstop for names/addresses without checksums) | yes / no | verified-llm | existing | P1 |
| Q-05 | `singles_out_person` | D-PII-03 | yes / no | verified-llm + human on handwritten | existing | P1 |
| Q-06 | `special_category` | D-PII-04 | yes / no | verified-llm | existing | P1 |
| Q-07 | `credential` | D-SEC-01 (after a tier-1 hit) | yes / no | verified-llm | existing | P1 |
| Q-08 | `confidential_business` | D-SEC-02, D-POL-08 | yes / no | verified-llm | existing | P1 |
| Q-09 | `secret_kind` | D-SEC-01 | real / documented dummy / test value / not a secret | generator + tier-1 corpus | new | P1 |
| Q-10 | `record_provenance` | D-PII-05 | fixture / production / unclear | generator (provenance field) | new | P1 |
| Q-11 | `governing_clause` | D-POL-02, reason (DEC-12) | clause ids of the policy + "none" | human (handwritten), generator for tables | new | P1 |
| Q-12 | `exception_applies` | D-POL-03 | yes / no | human | new | P1 |
| Q-13 | `policy_covers` | D-POL-05 | yes / no | generator (silence cases) + human | new | P1 |
| Q-14 | `cross_client` | D-POL-07 | yes / no | generator with provenance taint | new | P1 |
| Q-15 | `rewrite_safe` | D-PII-07 | yes / no | human-adjudicated rewrites (P1-10) | new | P1 |
| Q-16 | `security_disclosure` | D-SEC-02 | yes / no | verified-llm | new (or folded into Q-08, DEC-10) | P1 |
| Q-17 | `guard_instruction` | D-SEC-06, S-13 | yes / no | generator | new | P2 |
| Q-18 | `purpose_ok` | D-POL-06 | yes / no | human | new | P2 |
| Q-19 | `inbound_action` | D-PII-06 | pass / redact | table on inbound items (`pii_gen` inbound channels) | new | P2 |
| Q-20 | `tool_risk` | D-SEC-03 | allow / ask / deny | external + generator | deferred (DEC-01) | P2 |
| Q-21 | `destination_class` | D-SEC-05 | 5 classes + exfiltration | generator over URL/host lists | deferred | P2 |
| Q-22 | `field_disposition` | D-PII-09 | send / hash / drop | generator over log schemas | deferred | P2 |

The P3 rows of the matrix (`D-PII-10`, `D-SEC-07/08`, `D-POL-11`) get no question in v1. They are listed in
`QUESTIONS.md` as `deferred` with the reason.

### Proposed content: composition (sketch for `COMPOSITION.md`)

1. Tier 1 runs first. A valid credential match → `block` / verified `redact`, final (A-03). Q-09 can only downgrade a
   tier-1 hit to `allow` when the answer is `documented dummy` above the strictest band, and that downgrade is logged.
2. The resolver gives the destination class and named destination. The provenance tracker gives source and client.
   Code computes the facts.
3. Content questions Q-02, Q-04…Q-08, Q-10, Q-14 and Q-16 → the effective category. When several apply, the most
   restrictive cell wins.
4. The policy step:
   - Q-13 `policy_covers = no` → `ask_user` (A-07);
   - otherwise Q-11 selects the clause;
   - if the clause has an exception, Q-12 decides;
   - if a table cell is defined and no exception applies → composed action (DEC-02);
   - otherwise Q-01 decides directly.
5. Disagreement between the composed action and Q-01 lowers confidence by a rule fit on `cal` and is logged.
6. Bands per destination class (P3-02) turn (action, confidence) into the enforced outcome. `redact` needs Q-15 = yes
   on the produced rewrite, otherwise it becomes `block` (A-04).
7. Reason = DEC-12 template.

### Proposed content: facts contract (sketch for `FACTS.md`)

| Fact key | Producer | Example rendering (EN) |
|---|---|---|
| `tier1_hits` | tier-1 detectors | `tier-1: PESEL (valid checksum) ×1, e-mail ×2` |
| `dest_class`, `dest_name` | resolver (P2-03) | `destination: Sentry (saas, processor with DPA: yes)` |
| `processor_listed` | policy config | `listed processor: yes` |
| `source`, `source_client` | provenance tracker | `draws on: client_repo Bursztyn Bank` |
| `target_client` | resolver | `target client: Nordwind Energie` |
| `today_vs_embargo` | clock + policy config | `embargo "Kompas": active until 2026-11-15` |
| `group_size_vs_threshold` | code parsing counts in the payload where possible | `smallest count in text: 3 (policy threshold 10)` |
| `advisory_public` | config / CVE list | `advisory published: no` |
| `region` | resolver | `processing region: US (policy: EEA only)` |
| `session_disclosed` | ledger (later, A-02) | `already sent to this destination in session: role, office` |

An unknown fact is rendered as `unknown`, never omitted. Training data includes `unknown` cases so the model does not
treat missing facts as reassuring.

## Definition of done

- [ ] `QUESTIONS.md` and `catalogue.toml` agree (test below). Every P1 matrix row from P0-09 is served by at least
      one P1 question, or is marked deferred with a reason.
- [ ] `COMPOSITION.md` has the order, the table and ≥ 10 worked examples, one per family S-01…S-10, each
      reproducible by hand from the seed item.
- [ ] `FACTS.md` names a producer issue for every fact (P1-01, P2-03, P2-04 or a new task)
- [ ] ADRs for DEC-01…DEC-12, discussed in one meeting with the model, data-decision, benchmarks and GDPR roles.
      Each is `accepted`, or `proposed` with an interim default and a dated revisit condition.
- [ ] The impact edits are made in `P1-03`, `P2-03`, `P3-01`, `P3-02`, `P0-06` and `P1-10` (new kinds, facts, mix
      reporting, calibration groups, per-`question_id` slices, per-question gold fields). `issues_sync.py lint`
      passes.
- [ ] If DEC-04/06/12 require prompt or readout changes, a follow-up issue exists (no silent edit of
      `prompt.py` / `sft.py`)

## Automated tests

- `warda/tests/test_questions.py`:
  - `catalogue.toml` parses;
  - ids are unique and match `QUESTIONS.md` headings;
  - every `existing` id equals a key of `pii_gen.QUESTION["en"]` and `["pl"]`, and the option texts match what
    `pii_gen` renders (`YESNO`, `ACTION_TEXT`, `CATEGORY_TEXT`);
  - every required fact key exists in `FACTS.md`;
  - no question has more than the DEC-04 option limit.
- A table-driven test of the composition pseudocode on the worked examples, as plain data, without a model. The
  composer implementation in P2-04 must later pass the same cases.

## Documentation

- `docs/decider/QUESTIONS.md`, `COMPOSITION.md`, `FACTS.md`, the ADRs; `docs/decisions/README.md` index.
- `README.md` "Contents" adds `docs/decider/` and `data/questions/`; `AGENTS.md` "Key contracts" gains the question
  catalogue as the source of question ids and option texts.
- `docs/bench/USE_CASES.md` (P0-09): matrix rows link their `Q-xx`; `docs/bench/PROTOCOL.md` reports per
  `question_id`.

## Manual test (human, before the PR)

1. Take 5 seed items from P0-09 (from S-01, S-02, S-06, S-08, S-10). Fill each question by hand, compose per
   `COMPOSITION.md` → the result equals the seed gold. Any mismatch fixes either the doc or the seed.
2. A model-team member who did not write the catalogue renders one `existing` and one `new` question with
   `prompt.py` from `catalogue.toml` text and confirms the option lines match `sft.py` expectations.
3. The GDPR person reads DEC-02, DEC-09 and DEC-12 and confirms an auditor could follow a decision from its reason
   string to the policy clause.
