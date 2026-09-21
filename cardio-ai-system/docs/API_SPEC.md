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
- No authentication, no API keys. CORS is wide open (`*`) because the app is
  local-only by design — see `SECURITY.md` before deploying anywhere public.

---

## GET /
Root descriptor.

**200**
```json
{ "name": "PulseIQ API", "version": "2.0.0", "status": "ok", "ai_provider": "local|ollama|gemini" }
```

## GET /health
Liveness + active reasoning tier. Polled by the frontend.

**200**
```json
{ "status": "ok", "ai_provider": "local|ollama|gemini", "message": "All core features work with zero configuration." }
```

## POST /diagnose
The core 5-stage pipeline (see `DATA_FLOW.md` §1).

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

## POST /ai-insights
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

## POST /final-report
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

## POST /analyze-report-image
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

## WS /ws/consultation
Live copilot loop. One JSON frame per transcript line, response per line.

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

## Non-goals
- No pagination, filtering or auth headers anywhere.
- No batch endpoints; one narrative / one WS frame per call.
- The SPA at `:5173` is served by Vite, not by the API.
