# Decision labelling app (`warda/label`)

A local web app for reviewing the proposed gold label of decision items: each labeller confirms, fixes, rejects or
marks an item unsure, and two labellers' SQLite files merge into one agreement report.

## Install

```bash
uv sync --locked
```

No model or network is needed; the app binds `127.0.0.1` only.

## Input

Any decision-item JSONL:

- `pii_gen` items (`pretrain/work/harness_pii/items/*.jsonl`): `state` (policy block, a blank line, then the call),
  `question`, `options`, `gold` (option index), `category`, `action`.
- Handwritten rows (P1-10): `payload`, `task`, `channel`, `destination`, `policy_id`, and `gold_category` /
  `gold_action` once adjudicated. Rows without a proposed gold can only be fixed, not confirmed.

The proposed gold under review is `gold_category`/`gold_action` if present, else `category`/`action`.

## Run two labellers

Each person runs the app on their own laptop with their own database. `--order seed` (default) gives everyone the same
fixed order, so `--limit 20` gives everyone the same 20 items.

```bash
uv run python -m warda.label.app --items pretrain/work/harness_pii/items/dev.jsonl \
  --db labels-alice.sqlite --labeller alice --limit 20
# open http://127.0.0.1:8766 ; the second person uses --labeller bob --db labels-bob.sqlite
```

| Flag | Default | Meaning |
|---|---|---|
| `--items` | required | decision-item JSONL |
| `--db` | required | SQLite file; created if missing, append-only |
| `--labeller` | required | name stored on every label |
| `--port` | `8766` | port on `127.0.0.1` |
| `--order` | `seed` | `seed`: fixed hash order shared by all labellers; `file`: file order |
| `--limit` | all | label only the first N items in that order |

### Verdicts

| Key | Verdict | Stored category / action |
|---|---|---|
| `c` | confirm | the proposed gold |
| `f` | fix | your choice; both must be in `warda/schema.py` (`CATEGORIES`, `ACTIONS`), else the save fails |
| `r` | reject | none: the item itself is broken or unrealistic; say why |
| `u` | unsure | none |

`Enter` saves and moves to the next unlabelled item; `Shift+Enter` adds a new line to the reason; `Esc` leaves a
field; `←`/`→` move one item; `n` jumps to the next unlabelled item. After `f`, the category list has focus: arrow
keys pick a value, `Tab` moves to the action and then the reason. A timer records the seconds spent on each item.
Saving again replaces your earlier label for that item (the old row stays in the audit trail). On reload the app
reopens the item you labelled last.

## Merge and read the report

```bash
uv run python -m warda.label.export --db labels-alice.sqlite --db labels-bob.sqlite --out agree/
```

| File | Content |
|---|---|
| `labels.jsonl` | latest label per (item, labeller) across all databases |
| `labels_audit.jsonl` | every saved row, tagged with its source `db` |
| `agreement.json` | `labellers` (items each labelled), `n` (items), `kappa`, `alpha`, `disagreements` |

- `kappa`: for each labeller pair, Cohen's kappa on category and on action. It counts only items where both gave
  that field (`confirm` or `fix`), with `n_category` / `n_action` as the counts.
- `alpha`: nominal Krippendorff's alpha per field across all labellers; missing labels are allowed.
- `disagreements`: every item where the labellers' outcomes differ, with each verdict, category, action and reason.
  `confirm` and a `fix` to the same values agree; `reject` and `unsure` are outcomes of their own.

`GET /api/stats` in the running app shows the same report for the labels in that one database.
