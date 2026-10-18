+++
id = "P1-01"
title = "Tier-1 deterministic detectors and redaction (`warda/guard/tier1.py`)"
labels = ["phase:1", "team:tools", "type:feature", "gate:2"]
milestone = "Phase 1 — Data and trials (weeks 2–6)"
depends_on = ["P0-01", "P0-06"]
estimate_hours = 8
hardware = "laptop"
github_issue = 11
+++

## Context

FINDINGS §2 "Design settled": tier 1 (explicit identifiers and secrets) stays deterministic and authoritative; the
model only sees tiers 2–3. `pii_gen.py` already has format-valid generators and validators (`pesel_valid`,
`nip_valid`, `iban_valid`, `luhn_valid`, l.271–322) used to *make* synthetic data; the guard needs the detection
side: find spans in arbitrary text, validate checksums, classify, redact. This decider is also gate 2's "pattern
matching" baseline.

## Scope

- `warda/guard/checksums.py` (moved validators), `warda/guard/tier1.py` (detectors + redaction),
  `warda/bench/deciders/tier1.py` (bench adapter).
- Out of scope: ML, provenance, inbound redaction (P4-07).

## Deliverables

- Move `pesel_valid`, `nip_valid`, `iban_valid`, `luhn_valid` from `pii_gen.py` to `warda/guard/checksums.py`
  and add `regon_valid` (9- and 14-digit weights); `pii_gen.py` imports them (its generators stay). Existing
  `test_pii_gen.py::test_generated_identifiers_pass_their_checksums` keeps passing through the import.
- `warda/guard/tier1.py`: `@dataclass(frozen=True) class Hit: kind: str; start: int; end: int; value: str;
  checksum_ok: bool | None`; `detect(text: str) -> list[Hit]` for kinds: `pesel`, `nip`, `regon`, `iban`,
  `card`, `email`, `phone_pl` (+48 and 9-digit forms with separators), `api_key` (prefixes: `sk-`, `ghp_`,
  `gho_`, `github_pat_`, `xoxb-`, `xoxp-`, `AKIA`, `AIza`, `-----BEGIN … PRIVATE KEY-----`), `password_in_url`,
  `high_entropy` (≥ 32 chars, Shannon entropy ≥ 4.0 bits/char, no spaces, not a sha-like hex of length 40/64 in a
  `git`/`commit` context); PESEL/NIP/REGON/IBAN/card hits with failing checksum are returned with
  `checksum_ok=False` and ignored by `classify`.
- `classify(hits) -> str | None`: `credential` if any of `api_key|password_in_url|high_entropy|private_key`,
  else `direct_pii` if any checksum-ok identifier or email/phone, else `None`.
- `redact(text, hits) -> str` replacing each hit with `[{KIND}]` (e.g. `[PESEL]`), non-overlapping, longest first.
- `Tier1Decider` (in `warda/bench/deciders/tier1.py`, registered as `tier1`): category from `classify`, action
  from the shared request policy table through `warda.bench.policies.gold_action`; no title matching or fixed
  synthetic-policy lookup. No hits maps to category `none`; relevant exceptions unsupported by a deterministic
  table produce `ask_user` rather than an invented allow; `confidence` 1.0 when a credential/checksum
  hit exists, 0.5 otherwise; `redacted_payload` set when action is `redact`.

## Definition of done

- [ ] `detect` finds every identifier that `pii_gen` generators produce (500 random samples per kind) with
      `checksum_ok=True` and zero hits on a 5 kB English/Polish prose fixture without identifiers
- [ ] On `test.jsonl` via `warda.bench.run --decider tier1`, accuracy > `always_allow` and recall on
      `category in (direct_pii, credential)` ≥ 0.95
- [ ] `redact` output never contains the original hit values and keeps all other text byte-identical

## Automated tests

- `warda/guard/tests/test_checksums.py`: textbook PESEL `44051401458` valid / `…59` invalid; NIP, REGON 9/14,
  IBAN PL + DE example, Luhn `4111 1111 1111 1111`.
- `warda/guard/tests/test_tier1.py`: parametrised over generator kinds (seeded `random.Random(0)`, 200 each) →
  one hit with `checksum_ok`; false-positive fixture (`warda/guard/tests/fixtures/prose_pl_en.txt`, fictional,
  contains 11-digit order numbers that fail PESEL checksum and a git SHA) → no checksum-ok hits and no
  `high_entropy` on the SHA; overlapping hits (IBAN containing digits that look like a phone) → longest wins;
  `redact` idempotent; `classify` precedence credential > direct_pii.
- `warda/bench/tests/test_tier1_decider.py`: all synthetic policies × 2 languages; a custom policy table; unsupported
  exception → ask_user.

## Documentation

- `docs/guard/TIER1.md`: kinds, patterns, checksum rules, entropy rule and its known false positives, redaction
  tokens; `pretrain/README.md` "Harness decider": validators moved to `warda/guard/checksums.py`.

## Manual test (human, before the PR)

1. `uv run python -c "from warda.guard.tier1 import detect, redact; t='PESEL 44051401458, karta 4111 1111 1111
   1111, token ghp_abcdefghijklmnopqrstuvwxyz0123456789'; h=detect(t); print(h); print(redact(t,h))"` → three
   hits, redacted string shows `[PESEL]`, `[CARD]`, `[API_KEY]`.
2. Paste a real-looking but fictional `.env` block (made up by you) → every `KEY=value` with ≥ 32 random chars is
   flagged `high_entropy`; a line `COMMIT=<40-hex>` is not.
3. Bench run on `test.jsonl` with `--limit 500`: `report.md` row `tier1` beats `always_allow` on accuracy.
