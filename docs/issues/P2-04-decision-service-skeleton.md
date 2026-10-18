+++
id = "P2-04"
title = "Decision service skeleton: `POST /v1/decide`, tier-1 decider, shadow log"
labels = ["phase:2", "team:tools", "type:feature"]
milestone = "Phase 2 — Base training and service skeleton (weeks 6–10)"
depends_on = ["P1-01", "P2-03"]
estimate_hours = 8
hardware = "laptop"
github_issue = 25
+++

## Context

Plan §6: a light local HTTP service (FastAPI/Starlette — the repo already uses Starlette + uvicorn in
`pretrain/quality/app.py`, so Starlette). Hooks are short-lived processes; the model must stay loaded in a
daemon. Phase 2 ships the daemon with the deterministic tier-1 decider only; P3-03 plugs the model in behind the
same interface.

## Scope

- `warda/service/app.py` (Starlette), `warda/service/decider.py` (orchestration + `Decider` protocol reuse from
  `warda/bench/protocol.py`), `warda/service/log.py` (shadow log), `warda/service/client.py` (tiny HTTP client used
  by hooks, stdlib `urllib`).
- Out of scope: model backend (P3-03), bands (P3-02), provenance (P4-07).

## Deliverables

- Log schema also includes stable `reason_code`, `enforced`, decider name/version, policy/config/model hashes
  and optional tester ID. Human-readable reason text and arbitrary agent fields are not exported. These fields
  support reproducible gate-4 reports without payload storage.

- The public HTTP API always uses the configured policy; callers cannot override it. `Service` receives a
  `Config`/shared `Policy` at construction. Benchmarks instantiate an isolated service per policy (including
  synthetic policies), with disposable logs and reset session state; never reconfigure a running user service.
- A deterministic non-allow requirement cannot become allow through the model or bands. Credentials always
  block. A deterministic redact may be strengthened to block/ask by contextual analysis; contextual block/ask
  cannot be weakened to redact. Redact with missing/unsafe spans becomes block before enforcement.
- Validate non-JSON, invalid enums, malformed responses and timeouts at boundaries. Hooks determine failure
  mode from validated local configuration, even when the service is unreachable; `serve --mode` overrides must
  agree with the hook mode or startup/doctor refuses the mismatch.

- API (`docs/service/API.md`), request `POST /v1/decide` JSON: `{"channel": str, "destination": str|null,
  "target": {"scheme": str, "value": str}|null, "payload": str, "task": str|null, "language": "pl"|"en"|null,
  "agent": {"name": str, "session": str|null, "tool": str|null}}` — exactly one of `destination` / `target`
  required (target is resolved via P2-03). Response: `{"decision_id": uuid, "action": ACTIONS, "confidence":
  float, "reason": str, "redacted_payload": str|null, "category": str|null, "tier1": [{"kind","start","end"}],
  "destination": str, "mode": "shadow"|"enforce", "decider": {"name": str, "version": str}, "latency_ms": int}`.
  Errors: 400 with `{"error": str}` for schema violations; 503 `{"error": "decider not ready"}` while loading.
  `GET /healthz` → `{"ok": true, "mode", "decider", "uptime_s"}`. Binds `127.0.0.1:8787` only; no auth (localhost
  trust boundary stated in the doc).
- `warda/service/decider.py`: `class Service` holding `Config`, the active `Decider`, and `decide(req) ->
  Response`; pipeline: tier-1 `detect` → if `classify` gives `credential` → `block` with confidence 1.0, no model
  ever; else deterministic PII category → policy-table action (unsupported exceptions → `ask_user`);
  otherwise active decider result. P3-03 adds contextual decisions under the same precedence.
  Produce `redacted_payload` only for a safe deterministic rewrite; `reason` is a one-line template in the config
  language ("Zablokowano:
  dane uwierzytelniające (API_KEY) → miejsce docelowe: public_repo").
- Shadow log `warda/service/log.py`: one JSON line per decision to `log.path`: `ts`, `decision_id`, `agent`,
  `channel`, `destination`, `action`, `confidence`, `category`, `tier1_kinds`, `payload_sha256`, `payload_chars`,
  `latency_ms`, `mode`; `payload` only when `store_payload = true`. File created `0600`.
- `mode = "shadow"`: response still carries the real `action` but adds `"enforced": false`; hooks (P2-05) use
  `enforced` to decide whether to act. `enforce` → `"enforced": true`.
- `warda/service/client.py`: `decide(req: dict, timeout_s: float = 2.0) -> dict | None` returning `None` on
  connection error/timeout (hooks fail open in shadow mode, fail closed in enforce mode — the hook decides).

## Definition of done

- [ ] `uv run python -m warda.service.app` starts with `~/.warda/warda.toml`, `curl -s localhost:8787/healthz` ok
- [ ] A payload with a valid PESEL to `public_repo` under the strict policy returns `redact` with
      `redacted_payload`; with a `ghp_` token returns `block`, confidence 1.0; clean text returns `allow`
- [ ] Every request appends one shadow-log line without the payload by default
- [ ] p95 latency of the tier-1 path < 20 ms for a 1k-char payload (measured by the test below)

## Automated tests

- `warda/service/tests/test_app.py` (Starlette `TestClient`, temp config/log in `tmp_path`): the three DoD
  cases; 400 on missing `payload`; 400 when both `destination` and `target` given; `target` resolution path;
  shadow log line fields and absence of `payload`; `store_payload = true` includes it; `healthz`.
- `warda/service/tests/test_client.py`: `decide` returns `None` on refused connection within the timeout.
- `warda/service/tests/test_latency.py`: 200 requests through `TestClient`, assert p95 < 50 ms (bound is
  generous for CI runners; the 20 ms DoD figure is measured manually on a laptop).

## Documentation

- `docs/service/API.md` (new) with request/response, error table, shadow vs enforce semantics, the localhost trust
  boundary, and log schema; `README.md` gets a "Run the guard" section (3 commands); `AGENTS.md` "Run".

## Manual test (human, before the PR)

1. Start the service; send the three DoD payloads with `curl` (commands in `API.md`) and paste responses.
2. `tail -3 ~/.warda/decisions.jsonl` → three lines, no payload text, `payload_sha256` present.
3. Stop the service; `python -c "from warda.service.client import decide; print(decide({...}))"` → `None`
   within ~2 s.
