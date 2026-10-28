# ADR-draft: Brama open decisions D-B1–D-B6

The number is assigned when this stub is filed through the P0-07 process, after the P0-10 ADRs (`ADR-0007…`).

## Status

proposed

## Context

P0-11 designs the Brama benchmark (`docs/bench/BRAMA.md`) and leaves six decisions open. P0-12 built the v0
examples split and a pilot runner with the interim defaults below, so the pilot could run; none of them is final.

## Decision

| Id | Question | Proposed default | Used in v0 |
|---|---|---|---|
| D-B1 | Does gate 3 move from the handwritten v1 set (P3-04) to Brama official, with P3-04 as its human core? | Brama official becomes the gate-3 set from v1; P3-04 items form its human-written core | not applicable (no official split) |
| D-B2 | Where does official live, who holds the key, when is external submission offered? | Private repo under the project owner, two key holders; submissions from v1.1 | not applicable |
| D-B3 | Single gold vs `acceptable` sets | Sets only in T2/T6, only when both labellers chose a member | 11 items carry sets in T1/T5/T6/T7/T9; see `BRAMA.md` |
| D-B4 | Headline M-01 (operating point) vs M-03 (expected cost) | M-01 headline, M-03 tie-break | M-01 headline; M-03 not computed (costs unconfirmed) |
| D-B5 | Licence for dev and examples | CC-BY-4.0 (ADR-0002, P5-04) | CC-BY-4.0 stated in `data/brama/CARD.md` |
| D-B6 | Tool-permission decision (D-SEC-03): Brama track in v2 or separate benchmark? | Separate benchmark; revisit at v2 | not applicable |

## Consequences

Until this ADR is accepted, every Brama score is labelled "v0, interim defaults". If D-B3 ends with single gold
only, the 11 v0 items with two-action sets are relabelled and the pilot rescored (`run_brama report`, no reruns
needed since runs store full distributions).

## Revisit when

The P0-11 review meeting is held, or before the P1-13 dev/official v0.5 draw, whichever comes first.
