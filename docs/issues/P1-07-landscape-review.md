+++
id = "P1-07"
title = "Research: landscape review of existing guards and classifiers"
labels = ["phase:1", "team:research", "type:docs"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = []
estimate_hours = 5
hardware = "laptop"
github_issue = 17
+++

## Context

Plan §5 phase 1 "review of solutions and policies"; FINDINGS §2 already lists GitGuardian ggshield hooks, Anthropic
inference hooks, Cyberhaven, PrivacyLens, ConfAIde, AirGapAgent. Benchmarks (P1-11, P3-05) need a settled list of
what we compare against and how each is run locally.

## Scope

- `docs/research/LANDSCAPE.md` covering at least: Microsoft Presidio, GitGuardian ggshield, Bielik-Guard, Llama
  Prompt Guard 2, Jev-style decision models, Cyberhaven (description only), Anthropic inference hooks (protocol),
  PrivacyLens / ConfAIde (datasets), AirGapAgent (design), and 3 more found during the review.
- Out of scope: running them (P1-11).

## Deliverables

- One section per item: what it detects (tier 1/2/3 per FINDINGS), input/output, runs locally? (yes/no, how),
  licence, Polish support, policy-awareness, calibration/confidence available, integration points with agents,
  cost; a one-line "what we take from it"; links.
- Closing comparison table `Tool | Tiers | Local | PL | Policy-aware | Confidence | Licence | In benchmark?` and a
  "Gaps Warda fills" paragraph consistent with FINDINGS §2.
- `docs/research/BIBLIOGRAPHY.md`: papers with one-line relevance each.

## Definition of done

- [ ] ≥ 12 items reviewed with every column filled (or "unknown" with a reason)
- [ ] The "In benchmark?" column is the authoritative input for P1-11 and P3-05 (each tool marked yes has a
      "how to run locally" subsection)
- [ ] Reviewed by one benchmarks-team member (comment on the PR)

## Automated tests

- None (docs). markdownlint.

## Documentation

- The two files; `FINDINGS.md` top table gains a row linking `docs/research/`.

## Manual test (human, before the PR)

1. Follow the "how to run locally" subsection for Presidio on a laptop: it works as written (`pip`/`uv` lines,
   sample call) — paste the output.
2. Every external link opens (spot-check 10).
