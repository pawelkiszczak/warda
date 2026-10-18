+++
id = "P4-09"
title = "Security hardening and threat model for the service and hooks"
labels = ["phase:4", "team:tools", "type:infra"]
milestone = "Phase 4 — Integrations (weeks 13–16)"
depends_on = ["P2-04", "P2-05", "P4-07"]
estimate_hours = 5
hardware = "laptop"
github_issue = 44
+++

## Context

The guard is a security control: a hook that fails open, a service bound to all interfaces, or a log readable by
other users defeats it. FINDINGS lists caveats (fail-open timeouts, transcripts keep originals, obfuscation
evasion). The repo runs CodeQL on push with Starlette models in `codeql/python-models/`.

## Scope

- Threat model doc, hardening fixes, CodeQL coverage for `warda/service`.
- Out of scope: auth between hook and service (localhost trust boundary stays; revisit at gate 4).

## Deliverables

- `docs/security/THREAT-MODEL.md`: assets, trust boundaries (agent ↔ hook ↔ service ↔ model ↔ log), threats
  (fail-open on timeout; service down; prompt injection via tool output trying to talk the gate round — FINDINGS
  lesson: the model sees only policy/payload/destination/provenance, never agent prose; log exfiltration; config
  tampering; obfuscated payloads base64/split lines; DoS via huge payloads), mitigations with the code location
  for each, residual risks.
- Hardening: payload size cap (64 kB → 413 with reason; hooks treat as `ask_user` in enforce mode); base64 and
  hex-blob detection in tier 1 (`encoded_blob` kind → `ask_user` to non-internal destinations); log and config
  files `0600`, directory `0700`, `doctor` checks them; service refuses to start if `host != 127.0.0.1` without
  `--i-know-what-i-am-doing`; hook timeout in installers set to 5 s with the agent's fail-closed option where the
  agent supports it (HOOKS.md), documented otherwise.
- `codeql/python-models/` extended so `warda/service/app.py` route handlers are remote sources (same pattern as
  the labelling app); `scripts/codeql-scan.sh` unchanged.

## Definition of done

- [ ] Threat model merged; every mitigation points to a test or a code line
- [ ] `uv run pre-commit run --hook-stage pre-push --all-files` (CodeQL) passes with the new models and no findings
- [ ] A 100 kB payload returns 413; a base64 blob of a fictional PESEL list to `public_repo` is not `allow`

## Automated tests

- `warda/service/tests/test_hardening.py`: size cap; bind refusal; permissions set on first log write.
- `warda/guard/tests/test_tier1.py`: `encoded_blob` detection (base64 ≥ 64 chars decoding to text with a
  tier-1 hit, hex ≥ 64 chars) and no hit on a git SHA / short hashes.

## Documentation

- `docs/security/THREAT-MODEL.md`; `docs/service/API.md` error 413; `docs/integrations/*.md` "fail-closed"
  paragraphs.

## Manual test (human, before the PR)

1. `python -m warda serve --host 0.0.0.0` → refuses with the flag hint.
2. `ls -l ~/.warda` → `drwx------`, files `-rw-------`.
3. Commit a message whose body is `echo <base64 of "PESEL 44051401458"> | base64 -d` to a public-mapped remote in
   enforce mode → not allowed; reason mentions `encoded_blob`.
