# Decision labelling app (`warda/label`)

A local web app for labelling decision items. In **review** mode a labeller confirms, fixes, rejects or marks unsure
the proposed gold. In **blind** mode (Brama R-08) the gold is hidden and the labeller decides from the decider's view
alone. Two labellers' SQLite files merge into one agreement report.

## Install

```bash
uv sync --locked
```

No model or network is needed; the app binds `127.0.0.1` only.

## Input

Any decision-item JSONL, in one of three formats (`warda/label/items.py`):

| Format | Fields the app reads | Proposed gold |
|---|---|---|
| `pii_gen` (`pretrain/work/harness_pii/items/*.jsonl`) | `state` (policy block, blank line, call), `question`, `options`, `gold` | `category`, `action` |
| Brama (`data/brama/examples-v0.jsonl`, P0-11/P0-12) | `policy`, `channel`, `destination`, `task`, `provenance`, `facts`, `payload`; `group`, `role`, `twin_of`, `track`, `scenario`, `use_case` | `gold_category`, `gold_action`, `acceptable`, `clause`, `protected`, `tier`, `rationale` |
| Handwritten (P1-10) | as Brama, with `policy_id` | `gold_category`, `gold_action` once adjudicated |

Items without a proposed gold can only be fixed (review) or labelled (blind), not confirmed.

- **Policies.** For Brama and handwritten rows the app shows the policy text from a directory of Markdown files.
  Brama's carry TOML front matter between `+++` lines with `id`, `name` and `clauses`. The directory defaults to
  `policies/` next to the items file; pass `--policies DIR` otherwise. Declared clauses (plus `silence`) become the
  clause choices, and clicking a clause paragraph in the policy cites it.
- **Identifiers.** Brama payloads hold `{kind:key}` placeholders. The app resolves them from the ids sidecar
  (default `<items stem>.ids.json`, or `--ids FILE`) and underlines them. Placeholders the sidecar does not store
  (Brama derives credential-shaped `token`/`dsn` values at load time) stay visible as `{token:heron}`.
- **Contrast twins.** In review mode a Brama twin shows a word diff against the item it is a twin of, plus every
  changed context field (destination, policy, facts).

## Run two labellers

Each person runs the app on their own laptop with their own database. `--order seed` (default) gives everyone the same
fixed order, so `--limit 20` gives everyone the same 20 items.

```bash
# synthetic verification (gate 1): review the generator's gold
uv run python -m warda.label.app --items pretrain/work/harness_pii/items/dev.jsonl \
  --db labels-alice.sqlite --labeller alice --limit 20
# Brama / handwritten sets: two independent blind labels (R-08)
uv run python -m warda.label.app --items data/brama/examples-v0.jsonl --db labels-bob.sqlite --labeller bob --blind
# open http://127.0.0.1:8766 ; a second app on the same laptop needs --port
```

| Flag | Default | Meaning |
|---|---|---|
| `--items` | required | decision-item JSONL |
| `--db` | required | SQLite file; created if missing, append-only |
| `--labeller` | required | name stored on every label |
| `--blind` | off | hide the proposed gold, the twin and every hinting field (`track`, `role`, `scenario`, …) |
| `--policies` | `policies/` next to the items | policy Markdown directory |
| `--ids` | `<items stem>.ids.json` | Brama identifier sidecar |
| `--port` | `8766` | port on `127.0.0.1` |
| `--order` | `seed` | `seed`: fixed hash order shared by all labellers; `file`: file order |
| `--limit` | all | label only the first N items in that order |

## What a label holds

| Field | Review mode | Blind mode |
|---|---|---|
| `verdict` | `confirm` (stores the proposed gold), `fix`, `reject`, `unsure` | `label`, `reject`, `unsure` |
| `action`, `category` | required for `fix`; must be in `warda/schema.py` (`ACTIONS`, `CATEGORIES`) | required for `label` |
| `clause` | optional; one of the policy's declared clauses or `silence` | same |
| `protected` | spans that must not survive a rewrite (R-11); each must occur in the payload | same |
| `reason`, `seconds` | free text; time spent on the item | same |

`reject` means the item itself is broken or unrealistic (for example its gold does not follow from the state, R-02);
say why in the reason. Protected spans are stored with placeholders (`{pesel:wk}`), as in Brama's `protected`.
In review mode a redact item starts with the proposed spans; in blind mode the labeller marks them. The panel warns
when `redact` has no spans.

## Keyboard

| Keys | Does |
|---|---|
| `1`–`4` | action: allow, redact, ask_user, block |
| `⇧1`–`⇧7` | category, in the order shown |
| `[` `]` | previous / next clause (or click a clause in the policy) |
| `m` / `⇧m` | mark the selected payload text protected / drop the last span |
| `Space` | review mode: confirm the proposed gold and save, one key per agreeing item |
| `c` `f` `r` `u` | confirm (reset to proposed), fix, reject, unsure |
| `Enter` | save and open the next unlabelled item (`⇧Enter` in the reason: new line) |
| `/` · `Esc` | write a reason · leave the field |
| `j` `k` · `→` `←` | next / previous item |
| `n` | next unlabelled item |
| `p` · `t` | collapse the policy · hide the contrast twin |
| `?` | shortcut help |

Changing the action, category, clause or spans turns a review into `fix` (or back into `confirm` when it equals the
proposal); in blind mode it makes a `label`. Keys pressed while a save or load is in flight are ignored, so a fast
burst never labels the item that is being replaced. On reload the app reopens the item you labelled last; `#item-id`
in the URL opens that item.

## Merge and read the report

```bash
uv run python -m warda.label.export --db labels-alice.sqlite --db labels-bob.sqlite --out agree/ \
  --items data/brama/examples-v0.jsonl
```

| File | Content |
|---|---|
| `labels.jsonl` | latest label per (item, labeller) across all databases |
| `labels_audit.jsonl` | every saved row, tagged with its source `db` |
| `agreement.json` | `labellers`, `n`, `kappa`, `alpha`, `disagreements`, `conflicts`; with `--items` also `by_track`, `by_language` |

- "Latest" is decided inside each database by row order, never by the laptop clock. If one labeller appears in two
  databases, the database given later wins and the clash is listed under `conflicts`.
- `kappa`: for each labeller pair, Cohen's kappa on category and on action. It counts only items where both gave that
  field (`confirm`, `fix` or `label`), with `n_category` / `n_action` as the counts. `by_track` and `by_language` give
  the same pairwise kappas per Brama track and language (R-10 / V-08: κ ≥ 0.7 per track).
- `alpha`: nominal Krippendorff's alpha per field across all labellers; missing labels are allowed.
- `disagreements`: every item where the labellers' outcomes differ, with each verdict, category, action and reason.
  `confirm`, `fix` and `label` with the same values agree; `reject` and `unsure` are outcomes of their own.

`GET /api/stats` in a running review-mode app shows the same report for the labels in that one database. In blind
mode `/api/stats` and `/api/export` return 403, so labellers sharing a database stay blind to each other.
