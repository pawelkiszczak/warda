+++
id = "P0-07"
title = "Architecture decision records for the five open decisions"
labels = ["phase:0", "team:coordination", "type:decision"]
milestone = "Phase 0 — Kick-off (weeks 1–2)"
depends_on = ["P0-02"]
estimate_hours = 4
hardware = "laptop"
github_issue = 10
+++

## Context

Plan §11 lists five open decisions; §8 says decisions are written in the repo. Several Phase 1–3 issues depend on
them (training hardware → P2-01; label disputes → P0-05; platforms → P3-03/P4-06; licence → P5-04).

## Scope

- ADR template and six ADRs (the five open decisions plus CI scope) with a decision each (a decision may be "defer
  until gate N, default X meanwhile").
- Out of scope: implementing any decision.

## Deliverables

- Make `docs/performance/APPLE_SILICON.md` the acceleration contract in ADR-0003/0005: prefer verified MLX/Metal
  GPU work wherever it improves end-to-end throughput/latency, keep native CPU for unsupported/slower stages,
  and require actual backend/fallback reporting, completed-output timing, parity and unified-memory headroom.
  P1-12 owns preprocessing adoption; training/serving tasks own MLX tuning. This does not claim those paths
  have already shipped or permit quality/calibration regressions.
- NVIDIA/cloud-GPU training is not executable with the current MLX trainer. Do not schedule it as a fallback
  without a separately estimated, approved training-port task and parity checks. CPU participation means
  non-ML tooling everywhere; MLX mini-training requires a supported Mac.

- `docs/decisions/README.md`: numbering, statuses (`proposed|accepted|superseded`), template:
  `# ADR-NNNN: title` / `Status` / `Context` / `Decision` / `Consequences` / `Revisit when`.
- `docs/decisions/ADR-0001-model-size.md`: decision rule rather than a number: the shipped model is the smallest
  size in the P1-05 sweep whose `dev_ood` accuracy is within 2 points of the largest tried, subject to the P4-06
  latency budget; interim default 126M MoE / 37M active (the existing `model.py` config).
- `docs/decisions/ADR-0002-license-and-release.md`: code stays Apache-2.0 (existing `LICENSE`); dataset and
  weights release decided at gate 4; interim: synthetic data committed under `data/` is Apache-2.0, weights not
  published before gate 4.
- `docs/decisions/ADR-0003-platforms.md`: macOS (MLX) first through phase 3; Linux/Windows via the portable CPU
  backend in P4-06; no Core ML before gate 4 (FINDINGS §3 Neural Engine defects).
- `docs/decisions/ADR-0004-label-disputes.md`: adjudicator = GDPR person for category disputes, coordinator for
  process disputes; tie → `unsure` and the item is excluded from gold until a third labeller votes.
- `docs/decisions/ADR-0005-training-hardware-and-targets.md`: participants' machines for pilots (P1-05), rented
  Apple-silicon Mac only for the P2-01 MLX full run if no 96–128 GB Mac is listed in `docs/team/HARDWARE.md`; also
  holds the
  default numeric targets other issues cite: latency p95 ≤ 300 ms on Apple silicon 8 GB, ≤ 1 s on x86 CPU 16 GB for
  a ≤ 1k-token state; labeller agreement floor kappa ≥ 0.7.
- Also records as ADR-0006 whether PRs get CI: current `tests.yml` deliberately runs on `main` only (macOS runners
  cost 10× minutes); decision: keep `main`-only CI, rely on the `pre-push` pytest hook, revisit at gate 2.

## Definition of done

- [ ] Six ADR files with status `accepted` or `proposed` and a "Revisit when" line
- [ ] Issues P0-05, P2-01, P3-03, P4-06, P5-04 link their ADR
- [ ] `docs/team/MEETINGS.md` references the ADR process

## Automated tests

- None (docs). markdownlint via pre-commit.

## Documentation

- The ADRs; `README.md` "Contents" adds `docs/decisions/`.

## Manual test (human, before the PR)

1. A team member reads ADR-0004 and answers "who decides if two labellers disagree on `special_category`?" in one
   sentence that matches the file.
2. Numbers in ADR-0005 are the ones quoted in P4-06 and P0-03 (grep the issue files for "ADR-0005").
