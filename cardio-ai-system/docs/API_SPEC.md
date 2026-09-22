# PulseIQ — API Specification

> Source of truth for the backend contract at `http://localhost:8000`
> (proxied as `/api/*` by the Vite dev server). Implementations must match
> this file; if the contract changes, change this file in the same PR.
> Base URL in dev: `/api` (Vite strips the prefix). WebSocket base: `/ws`.

**Conventions**

- All bodies are JSON; responses are `application/json`.
- Errors are **not** HTTP status codes for domain failures: a missing field or
  a degraded capability returns `200` with a top-level `{"error": "…"}` object.
  Only transport-level failures (bad method/URL, WS protocol errors) yield
  non-200 codes. Callers must check for `error` in the body first.
- **Multi-user (added 2026-09-23):** every endpoint except `GET /`,
  `GET /health`, `POST /auth/register`, and `POST /auth/login` requires
  `Authorization: Bearer <token>`; missing/invalid tokens yield **401** with
  `{"detail": "…"}`. Resources are scoped to the token's owner — see
  `SECURITY.md`.

---

## POST /auth/register
Create a clinician account and start a session.

**Request**
```json
{ "email": "dr.chen@hospital.org", "password": "min8chars", "name": "Dr. Sarah Chen" }
```
| field | type | rules |
|---|---|---|
| email | string | required, email pattern |
| password | string | required, 8–256 chars |
| name | string | optional, ≤120 chars |

**200** `{ "token": "…", "user": { "id": 1, "email": "…", "name": "…" } }`
**400** duplicate email · **422** validation failure

## POST /auth/login
**Request** `{ "email": "…", "password": "…" }`
**200** same shape as register · **401** `{"detail": "Incorrect email or password."}`

## POST /auth/logout *(auth)*
Revokes the presented token. **200** `{ "ok": true }`

## GET /auth/me *(auth)*
**200** `{ "user": { "id": 1, "email": "…", "name": "…" } }`

---

## GET /
Root descriptor.

**200**
```json
{ "name": "PulseIQ API", "version": "2.0.0", "status": "ok", "ai_provider": "local|ollama|gemini" }
```

## GET /health
Liveness + active reasoning tier. Polled by the frontend (unauthenticated).

**200**
```json
{ "status": "ok", "ai_provider": "local|ollama|gemini", "message": "All core features work with zero configuration." }
```

## POST /diagnose *(auth)*
The core 5-stage pipeline (see `DATA_FLOW.md` §1). The result is persisted to
the signed-in user's history before the response is returned.

**Request**
```json
{ "text": "chest pain radiating to left arm since morning" }
```
| field | type | rules |
|---|---|---|
| text | string | required, non-blank |

**200**
```json
{
  "text": "…",
  "symptoms": ["chest pain"],
  "features": { "age": 52, "sex": 1, "cp": 2, "trestbps": 140, "chol": 240, "fbs": 0, "restecg": 0, "thalach": 150, "exang": 0, "oldpeak": 1.5, "slope": 2, "ca": 0, "thal": 2 },
  "prediction": 1,
  "probability": 0.83,
  "risk_level": "High|Medium|Low"
}
```
**200 (validation)**
```json
{ "error": "text is required" }
```

## POST /ai-insights *(auth)*
Diagnose + narrative insights from the active tier.

**Request** — same as `/diagnose`.

**200**
```json
{ "diagnosis": { …diagnose payload… }, "insights": "multi-line plain text", "ai_provider": "local|ollama|gemini" }
```
**200 (degraded)** — LLM tier raised: `{ "error": "<message>" }`

## GET /research-agents
Static registry of the 10 research-facing agents.

**200**
```json
{ "agents": [ { "name": "Uncertainty Quantification Agent", "focus": "…" }, … ] }
```

## POST /final-report *(auth)*
Turn structured visit fields into a report plan (PDF is produced client-side).

**Request** (all optional; sensible defaults filled)
```json
{
  "patient_name": "string",
  "doctor_name": "string",
  "chief_complaint": "string",
  "symptom_notes": ["string"],
  "recommended_tests": ["string"],
  "risk_level": "Low|Medium|High"
}
```

**200**
```json
{
  "report": {
    "title": "Consultation Report",
    "summary": "string",
    "probable_diagnosis": ["string"],
    "doctor_advice": ["string"],
    "medical_treatment_plan": ["string"],
    "follow_up_plan": ["string"],
    "red_flags": ["string"]
  }
}
```
Note: the internal `_recommended_tests` key is stripped server-side.
**200 (degraded)** — `{ "error": "<message>" }`

## POST /analyze-report-image *(auth)*
Read a lab report / scan. **Requires a vision-capable tier** (Ollama vision
model or Gemini); degrades to an explanatory payload otherwise.

**Request**
```json
{ "image_base64": "<no data: prefix>", "mime_type": "image/png" }
```

**200 (vision tier available)**
```json
{
  "analysis": { "summary": "…", "key_findings": [], "possible_diagnosis": [], "recommended_tests": [], "next_steps": [], "red_flags": [] },
  "ai_provider": "ollama|gemini"
}
```
**200 (no vision tier / validation)**
```json
{ "analysis": { "summary": "Local analysis could not read the image without an LLM vision model. …", "key_findings": [], "next_steps": ["Enter key findings manually in the report context field."], … }, "ai_provider": "local" }
```
or `{ "error": "image_base64 is required" }`

## WS /ws/consultation *(token required)*
Live copilot loop. One JSON frame per transcript line, response per line.
Connect as `ws://host:8000/ws/consultation?token=<bearer token>`; an invalid
or missing token is rejected with close code **4401** before accept.

**Client → server**
```json
{ "speaker": "patient|doctor", "text": "…", "report_text": "accumulated note", "language_code": "en-US" }
```
`speaker` defaults `patient`; blank `text` gets `{"error": "text is required"}`.

**Server → client** (success)
```json
{
  "speaker": "patient",
  "transcript": "english normalised text",
  "original_transcript": "as spoken",
  "language_code": "en-US",
  "report_text": "accumulated note",
  "symptoms": [],
  "diagnosis": { …diagnose payload… },
  "pain_points": [],
  "cardiac_regions": [],
  "doctor_next_questions": ["string"],
  "patient_recommendations": ["string"],
  "ai_copilot": { "doctor_questions": [], "recommended_tests": [], "next_steps": [], "diagnostic_impression": [], "urgency": "low|moderate|high", "safety_note": "…" }
}
```

---

## GET /history/screenings *(auth)*
The signed-in user's screening history, newest first (server-side, owner-scoped).

**200**
```json
{ "items": [ { "id": 1, "createdAt": "2026-09-23T03:54:14Z", "text": "…", "probability": 0.977, "risk_level": "High", "prediction": 1, "symptoms": ["chest pain"], "features": [55, 1, …] } ] }
```

## DELETE /history/screenings/{id} *(auth)*
**200** `{ "ok": true }` · **404** if the row is not owned by the caller.

## DELETE /history/screenings *(auth)*
Clears the caller's entire screening history. **200** `{ "ok": true }`

## POST /consultations *(auth)*
Persists a consultation record for the signed-in user.

**Request** — free-form JSON object; recognised keys include `patient_name`,
`patient_age`, `patient_gender`, `visit_date`, `doctor_name`,
`chief_complaint`, `risk_level`, `symptom_notes`, `report`. A `title` is
derived when absent.

**200** `{ "item": { "id": 2, "createdAt": "…", "title": "…", …payload } }`

## GET /consultations *(auth)*
**200** `{ "items": [ …same shape as POST response item… ] }` — caller's records only.

## DELETE /consultations/{id} *(auth)*
**200** `{ "ok": true }` · **404** if not owned by the caller.

## DELETE /consultations *(auth)*
Clears the caller's consultation records. **200** `{ "ok": true }`

---

## Non-goals
- No pagination or filtering; lists are capped (200 entries, newest first).
- No batch endpoints; one narrative / one WS frame per call.
- No cross-account access of any kind; there are no admin endpoints.
- The SPA at `:5173` is served by Vite, not by the API.
