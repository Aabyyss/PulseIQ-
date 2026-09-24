# PulseIQ — Security & Privacy Boundaries

> What this system may and may not do with data, and the rules contributors
> (human or AI) must follow to keep insecure patterns out.

## Threat model in one line

A local-first, **multi-user** clinical screening aid: several clinician
accounts share one machine-level server, so the primary risks are
**cross-account data leakage** and data egress off the device. Everything
below follows from those two.

Patient notes (`/notes`) and the optional patient tag on screenings follow
the same owner-scoping rule as every other record: queries filter by the
authenticated user id, never by a client-supplied name. Note bodies stay
inside the local database and are excluded from exports and logs.

## Session controls (added 2026-09-24)

- Clinicians can list their active sessions, revoke any of them, or revoke
  everything except the current device (`/auth/sessions*`).
- Changing the password revokes **all** sessions immediately; the caller
  receives the only surviving token.
- An append-only audit trail records account creation, sign-ins, sign-outs,
  password changes and session revocations, visible to the account owner at
  `/auth/audit`.
- The workspace auto-locks after 15 minutes without input: the session token
  is revoked and the clinician must sign in again.

## Authentication (multi-user, added 2026-09-23)

- Accounts are per-clinician: email + password, stored in SQLite at
  `backend/data/pulseiq.db` (override with `PULSEIQ_DB`).
- Passwords: PBKDF2-HMAC-SHA256, 200k iterations, per-user 16-byte random
  salt. Verification uses constant-time comparison; unknown accounts burn a
  comparable hash to avoid user enumeration by timing.
- Sessions: 32-byte URL-safe bearer tokens. **Only the SHA-256 hash of a
  token is stored** — a DB leak does not leak usable sessions. Tokens expire
  after 30 days; `POST /auth/logout` revokes immediately.
- The WebSocket (`/ws/consultation`) requires a valid token as the
  `?token=` query parameter and closes with code 4401 otherwise.
- **Brute-force protection (ADR-011):** 5 failed logins per (IP, email)
  trigger a 15-minute lockout returning 429. Counters are in-memory and
  reset on restart — acceptable because the deployment is device-local.
- **Request cap:** bodies above 8 MB are rejected with 413 before routing.
- `/health` and `/` stay public for the frontend engine probe.

## Data isolation rules (highest priority)

1. **Every history read/write must be owner-scoped at the SQL level.**
   `auth_store` filters all screenings/consultations by `owner_id`. Never
   add a query that selects or mutates history rows without the owner
   predicate, and never accept a user-supplied owner id — it always comes
   from the resolved token.
2. **New per-user data must live behind `get_current_user`.** Any endpoint
   that reads or writes user content and lacks the dependency is a bug.
3. **Cross-account delete is a 404, not a 403** (do not confirm existence
   of another user's resources). `backend/test_auth.py` enforces this.
4. Consultation records may contain patient names/ages — they are owner-
   scoped like screenings and never logged.

## Data handling rules

1. **No logging of narrative text, transcripts, or report payloads.** The
   screening request/response cycle persists only into the owner-scoped
   history tables — never to log files or console.
2. **Client persistence is bounded.** localStorage holds only the session
   token and cached user profile (cleared on sign-out/401). History no
   longer lives in the browser — it is server-side per account.
3. **The only network egress is optional and explicit:**
   - Ollama at `http://localhost:11434` (loopback, user-installed), or
   - Gemini API when `GEMINI_API_KEY` is set by the user.
   Any new outbound call needs an ADR and an env-var opt-in.
4. **Images** (`/analyze-report-image`) are base64 in the request body,
   forwarded only to the active vision tier, never stored.

## Network & CORS stance (ADR-005)

```python
allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
```

- Acceptable **because the server binds localhost** for local use. Bearer
  tokens are not cookies, so `allow_credentials=False` stays correct with
  origins `*`; but any non-loopback deployment must restrict origins.
- **Before any public/deployed use:** restrict origins to the serving
  origin, put a reverse proxy with TLS in front (tokens must not travel
  plain over a LAN), rotate the token TTL down, and re-derive this file +
  ADR-008. The `/final-report` and image routes especially must not be
  internet-exposed as-is.

## Secrets

- No secrets belong in the repo. `GEMINI_API_KEY` is read from the process
  environment only. `.env` files are gitignored — never commit one with a
  real key.
- The model artifact and dataset are public-data derived; no PHI is embedded.
- The SQLite database file is gitignored-class data: treat it as PHI-bearing
  once real accounts exist. It lives under `backend/data/` and must never be
  committed or synced off the machine.

## Input validation posture

- Auth payloads are Pydantic models: email pattern + password length bounds;
  store layer re-validates (defense in depth) and raises `ValueError` on
  duplicate emails (surfaced as HTTP 400).
- Route handlers validate required fields (`text`, `image_base64`) and
  return `{"error": …}` on failure; WS frames validate `speaker`/
  `language_code` types. Numeric model inputs come from the mapper's fixed
  tiers, not user arithmetic — keep it that way (no free-form numeric input
  reaches the model).
- The LLM boundary treats model output as untrusted: `_safe_parse_json`
  tolerates malformed output and every consumer falls back to the local
  engine on parse failure.

## Verification commands

```bash
# Auth + isolation + lockout suite (24 checks, incl. cross-account denial):
.venv/Scripts/python.exe backend/test_auth.py
# Full regression (all suites):
for t in test_orchestrator test_nlp_agent test_feature_mapper \
         test_prediction_agent test_full_pipeline \
         test_explainability_agent test_auth; do
  .venv/Scripts/python.exe backend/$t.py || echo "FAIL: $t"
done
```
