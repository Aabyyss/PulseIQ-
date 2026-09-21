# PulseIQ — Security & Privacy Boundaries

> What this system may and may not do with data, and the rules contributors
> (human or AI) must follow to keep insecure patterns out.

## Threat model in one line

A local-first clinical screening aid with **no accounts, no auth, and no
server-side storage** — the primary risks are data leakage off the device
and scope-creep into a deployed service without revisiting this file.

## Data handling rules

1. **No patient identifiers server-side.** The backend is stateless per
   request: nothing from `/diagnose`, `/ai-insights`, `/final-report`, or
   the WebSocket loop is written to disk. Do not add logging of narrative
   text, transcripts, or report payloads.
2. **Client persistence is bounded.** Screening history lives in browser
   localStorage, capped at 20 entries, containing the narrative the user
   typed. Clearing site data must clear it. Never persist full report
   payloads or images.
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

- Acceptable **because the server binds localhost for local use** and holds
  no state or secrets.
- `allow_credentials` must stay `False` while origins are `*`.
- **Before any public/deployed use:** restrict origins to the serving origin,
  add authn/authz, put a reverse proxy with TLS in front, and re-derive this
  file + ADR-008. The `/final-report` and image routes especially must not
  be internet-exposed as-is.

## Secrets

- No secrets belong in the repo. `GEMINI_API_KEY` is read from the process
  environment only. `.env` files are gitignored (see `.gitignore`) — never
  commit one with a real key.
- The model artifact and dataset are public-data derived; no PHI is embedded.

## Input validation posture

- Route handlers validate required fields (`text`, `image_base64`) and
  return `{"error": …}` on failure; WS frames validate `speaker`/
  `language_code` types. Numeric model inputs come from the mapper's fixed
  tiers, not user arithmetic — keep it that way (no free-form numeric input
  reaches the model).
- The LLM boundary treats model output as untrusted: `_safe_parse_json`
  tolerates malformed output and every consumer falls back to the local
  engine on parse failure.

## Medical scope (product-level safety)

- PulseIQ is decision **support**, not diagnosis. UI copy, reports, and the
  copilot `safety_note` must keep the "confirm with a qualified clinician"
  framing. Red-flag escalation copy must never be weakened.
- Don't remove the inverted-target assertion in `train_model.py` — it is a
  patient-safety control (ADR-002), not housekeeping.

## Dependency hygiene

- New Python deps: pin floors in `requirements.txt`, document in
  `docs/TECH_STACK.md`. Prefer wheels you can audit; this codebase runs on
  machines with strict Application Control (see `docs/COMPATIBILITY.md`).
- Frontend: `npm ci` in CI; don't commit lockfile drift from other
  package managers (`bun.lock` is legacy here).

## Reporting

This is an open-source reference implementation with no bug bounty. Report
issues via the repository issue tracker; do not open issues containing real
patient data.
