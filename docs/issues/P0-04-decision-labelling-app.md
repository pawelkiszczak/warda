+++
id = "P0-04"
title = "Decision labelling app (`warda/label`) with two-labeller agreement"
labels = ["phase:0", "team:tools", "type:feature", "gate:1"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-01"]
estimate_hours = 8
hardware = "laptop"
github_issue = 7
+++

## Context

`pretrain/quality/app.py` labels document quality (`HIGH/MEDIUM/LOW/SKIP`) with a Starlette API, SQLite audit
trail and pairwise Cohen's kappa in `stats_data`. Gate 1 and the handwritten set need the same workflow for
decision items: show `state`/`question`/`options`/proposed gold, collect `confirm|fix|reject|unsure`, compute
agreement between two labellers. The quality app stays untouched (research tool); a new app under `warda/label`
copies its proven pattern.

## Scope

- `warda/label/app.py` (Starlette + uvicorn, same stack), `warda/label/agreement.py`, `warda/label/static/`
  (plain HTML/JS/CSS, Biome-checked), `warda/label/export.py`.
- Input: any decision-item JSONL (`pii_gen` items or handwritten set). Output: SQLite + JSONL export.
- Out of scope: hosting; multi-user auth (labeller name is a CLI flag like the quality app's `--labeller`).

## Deliverables

- `warda/label/app.py`: `create_app(items_path: Path, db_path: Path, labeller: str) -> Starlette`; CLI `python -m
  warda.label.app --items PATH --db PATH --labeller NAME [--port 8766] [--order seed|file]`; binds `127.0.0.1`.
  Routes: `GET /` (UI), `GET /static/{name}`, `GET /api/items?labeller=` (ids + done flags), `GET /api/item/{id}`
  (item + rendered policy block + this labeller's latest label), `POST /api/label` body `{item_id, labeller,
  verdict: "confirm"|"fix"|"reject"|"unsure", category: str|null, action: str|null, reason: str, seconds: int}` —
  `fix` requires `category` and `action` in `warda.schema` sets else 400; `GET /api/stats` (per-labeller counts,
  pairwise kappa on category and on action, list of disagreements with both reasons); `GET /api/export` (latest
  label per item/labeller as JSONL).
- SQLite table `labels(id INTEGER PK, item_id TEXT, labeller TEXT, verdict TEXT, category TEXT, action TEXT,
  reason TEXT, seconds INTEGER, created_at TEXT, app_version TEXT)`; append-only, latest row per (item, labeller)
  wins (same rule as the quality app).
- `warda/label/agreement.py`: `cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float` and
  `krippendorff_alpha(rows: Sequence[Sequence[str | None]]) -> float` (nominal, handles missing), both pure
  Python; `disagreements(labels_by_labeller) -> list[dict]`.
- `warda/label/export.py`: CLI `--db --out DIR` writing `labels.jsonl` (latest), `labels_audit.jsonl` (all rows),
  `agreement.json` (kappas, alpha, n, disagreement list).
- UI: item text with the policy block visually separated; the proposed gold highlighted; keyboard shortcuts
  `c` confirm, `f` fix, `r` reject, `u` unsure, `Enter` save; a timer; progress `n/N`.

## Definition of done

- [ ] Two people can label the same 20 items on their own laptops and merge their SQLite files into one agreement
      report via `export.py --db a.sqlite --db b.sqlite --out DIR`
- [ ] `agreement.json` reports kappa on category and action, alpha, and lists every disagreement with reasons
- [ ] `fix` with an unknown category returns 400 and the UI shows the error
- [ ] Works with `pretrain/work/harness_pii/items/dev.jsonl` and with a 5-item handwritten JSONL

## Automated tests

- `warda/label/tests/test_agreement.py`: kappa of identical sequences is 1.0; of a textbook 2×2 table matches the
  hand-computed value (e.g. 0.4 for the standard example); alpha with one missing cell matches the hand-computed
  value; `disagreements` returns only mismatching items with both reasons.
- `warda/label/tests/test_app.py` (Starlette `TestClient`, `tmp_path` fixtures, mirrors
  `pretrain/quality/tests/test_app.py`): label round-trip; latest-wins on relabel; 400 on invalid `fix`; `/api/stats`
  kappa equals `agreement.cohen_kappa` on the same data; export writes three files.

## Documentation

- `docs/labelling/APP.md`: install, run two labellers, merge, read the report; screenshots not required.
- `README.md` "Contents" `warda/label` line; `AGENTS.md` "Run" gains the app command.

## Manual test (human, before the PR)

1. `uv run python -m warda.label.app --items pretrain/work/harness_pii/items/dev.jsonl --db /tmp/a.sqlite
   --labeller alice` and open `http://127.0.0.1:8766`.
2. Label 5 items using only the keyboard; reload → progress shows 5/N and the last item reopens with your label.
3. Repeat as `bob` into `/tmp/b.sqlite`, deliberately disagree on 2 items.
4. `uv run python -m warda.label.export --db /tmp/a.sqlite --db /tmp/b.sqlite --out /tmp/agree` → `agreement.json`
   lists exactly the 2 disagreements and kappa < 1.
