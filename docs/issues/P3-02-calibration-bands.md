+++
id = "P3-02"
title = "Calibrated bands per destination class and deny-and-continue escalation"
labels = ["phase:3", "team:model", "type:feature", "gate:3"]
milestone = "Phase 3 — Decision training and gates 2–3 (weeks 10–13)"
depends_on = ["P3-01"]
estimate_hours = 5
hardware = "laptop"
github_issue = 29
+++

## Context

FINDINGS "Design settled": a public destination needs high confidence to allow; uncertain → deny-and-continue with
a reason so the agent rewrites; ask the user only after repeated denials (3 consecutive / 20 per session, from
Anthropic's auto-mode lesson). `sft.py` already fits per-type temperatures and 1 %/5 % error thresholds into
`calibration.json`; the service needs a rule that turns `(action, confidence, destination class)` into the final
action.

## Scope

- `warda/guard/bands.py` + fitting script; session counters in the service; config keys.
- Out of scope: model loading (P3-03).

## Deliverables

- `warda/guard/bands.py`: `@dataclass Bands: allow_min: dict[str, float]` (per destination class: minimum
  calibrated confidence to let a model `allow` stand), `escalate_after_consecutive: int = 3`,
  `escalate_after_total: int = 20`; `apply(bands, action, confidence, dest_class, session: SessionState) ->
  tuple[str, str]` (final action, reason code): model `allow` below `allow_min[dest_class]` becomes `block` with
  reason `uncertain_allow` (deny-and-continue); model `redact`/`block` stand; `ask_user` stands; after
  `escalate_after_consecutive` consecutive non-allow decisions in a session or `escalate_after_total` total, the
  next non-allow becomes `ask_user` with reason `escalated`. Tier-1 `credential` blocks bypass bands.
- `warda/guard/fit_bands.py`: from a `report.json` produced by `warda.bench.run` on `cal` items (with
  confidences), fit `allow_min` per class as the smallest threshold with observed error on allowed items ≤ target
  (`--target-error public=0.01 saas=0.02 llm=0.02 client=0.02 internal=0.05` defaults); writes `bands.json`;
  prints coverage per class.
- Config: `[bands] file = "bands.json"` (P2-03 loader extended; absent → defaults `allow_min = 0.9` for public,
  0.8 others).
- Service: `SessionState` keyed by `agent.session` with the two counters, kept in memory, expired after 8 h.

## Definition of done

- [ ] `fit_bands` on `cand-v1`'s cal report yields `allow_min["public"] ≥ allow_min["internal"]`
- [ ] On `test.jsonl` with bands applied, `false_block_rate` increases by ≤ 3 pts while `leak_recall_public`
      increases (report both in the PR)
- [ ] Fourth consecutive deny in one session returns `ask_user` with reason `escalated`

## Automated tests

- `warda/guard/tests/test_bands.py`: each rule in `apply`; counter reset on allow; expiry; credential bypass.
- `warda/guard/tests/test_fit_bands.py`: on a synthetic report with known confidences/errors the fitted threshold
  equals the hand-computed value; empty class → default.

## Documentation

- `docs/guard/BANDS.md`: rationale (FINDINGS), rules, defaults, how to refit per backend (FINDINGS §3: thresholds
  are refit per backend); `docs/service/CONFIG.md` `[bands]`.

## Manual test (human, before the PR)

1. `python -m warda.guard.fit_bands --report /tmp/cal/report.json --out /tmp/bands.json` → prints per-class
   thresholds and coverage; thresholds non-decreasing from internal → public.
2. With the service in enforce mode and a fake decider that always returns `allow` at 0.5 (`--decider
   fake:allow:0.5` debug flag in `serve`), send 4 payloads to `public_repo` → responses: block, block, block,
   ask_user.
