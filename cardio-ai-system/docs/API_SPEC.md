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
  "risk_level": "High|Medium|Low",
  "learned_generation": 17
}
```
Extraction unions the built-in dictionary with the caller's **learned
vocabulary** (taught phrases, see `/learning/teach` below), so a phrase the
clinician taught fires here exactly as it does in the live loop.
`learned_generation` is the store's change counter at extraction time — a
client that saw a smaller value is seeing stale vocabulary state.

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
Live copilot loop. One JSON frame per transcript line, **two** responses per
line: an instant ack, then the full analysis once the local LLM finishes.
Connect as `ws://host:8000/ws/consultation?token=<bearer token>`; an invalid
or missing token is rejected with close code **4401** before accept.

**Client → server**
```json
{ "speaker": "patient|doctor", "text": "…", "report_text": "accumulated note", "language_code": "en-US",
  "transcript": "everything said before this line",
  "patient": { "age": "68", "sex": "male", "conditions": ["prior MI"], "allergies": ["aspirin"], "current_medications": ["warfarin"], "pregnancy": false } }
```
`speaker` defaults `patient`; blank `text` gets `{"error": "text is required"}`.
`language_code` accepts any of the UI locales: en-US, ur-PK, hi-IN, ar-SA,
ko-KR, fr-FR, es-ES, de-DE, zh-CN.

`transcript` and `patient` are optional, and exist for the live medication
safety screen (ADR-018). `transcript` is the encounter so far *without* this
line; the server appends its own translation of `text`, so the screen reads the
whole encounter rather than one line — omit it (or clear the transcript) and the
review reflects only this line. `patient` carries the visit details recorded on
the consultation screen; blank or omitted fields are **reported as gaps**
instead of being treated as "none", and an absent `pregnancy` means *not
recorded*, not *not pregnant*.

**Server → client, frame 1 — `line_ack` (instant, no LLM):**
```json
{
  "kind": "line_ack", "speaker": "patient",
  "transcript": "as spoken", "original_transcript": "as spoken",
  "symptoms": ["extracted concepts"],
  "matched_phrases": { "chest pain": "seene mein dard" },
  "learned_generation": 17, "learned_count": 3, "learned_hit": false
}
```
Lets the UI show concepts, risk hints and the body map immediately; the
dictionary matches English, Urdu script and Roman Urdu directly, plus the
signed-in clinician's **learned vocabulary** (ADR-015). `matched_phrases`
maps concept → surface phrase that matched; learned phrases are suffixed
`" (learned)"` in the value. `learned_generation` is the vocabulary store's
change counter, `learned_count` is how many entries this clinician has,
and `learned_hit` is true when this line was recognised by a taught phrase
or suppressed by a taught suppression pattern (drives the "learned phrase
used" badge and the × not-a-symptom correction affordance).

**Server → client, frame 2 — `analysis` (after the copilot pipeline):**
```json
{
  "kind": "analysis",
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
  "medical_entities": { "medications": [{ "name", "dose_mg", "matched" }], "durations": [], "risk_factors": [] },
  "medication_review": { …the `medications` block from POST /medication-review… },
  "ai_copilot": { "doctor_questions": [], "recommended_tests": [], "next_steps": [], "diagnostic_impression": [], "urgency": "low|moderate|high", "safety_note": "…",
    "suggestion_sources": { "<exact suggestion text>": "ACC/AHA chest pain guideline — …" },
    "confidence": { "confidence": "low|moderate|high", "insufficient_information": "true|false", "reason": "…" } }
}
```
`symptoms` unions extraction over the original and the translated line
(ADR-014), so a degraded translation cannot erase findings. Clients that
ignore `kind` still work: the analysis frame carries the same fields as
before.

New in ADR-016: `suggestion_sources` maps every copilot suggestion to the
guideline (or honest fallback reason) behind it — the UI renders it under
each bullet. `confidence` is the plan-level trust tier; when
`insufficient_information` is `"true"` the copilot has replaced its
diagnostic direction with an explicit "Not enough information yet" line
rather than guessing. `medical_entities` carries medications/durations/
risk factors extracted from the line.

New in ADR-018: `medication_review` is the `POST /medication-review` payload
rebuilt for this line — options, allergy/condition/laboratory blocks,
interaction alerts, `missing_information` and the urgency band — from the
recorded visit details above plus every line spoken so far. It is recomputed
from the encounter on each line instead of being accumulated in connection
state, so a cleared transcript clears the screen; nothing is stored.

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

## POST /diagnose — patient tag *(auth)*

The `/diagnose` request accepts an optional `patient_name` string (trimmed,
1–120 chars). It is stored on the screening row and echoed back in the
response as `patient_name`, so history entries can be filed under a patient
label.

## GET /notes *(auth)*

List the signed-in clinician's patient notes, most recently updated first.

```json
{ "items": [{ "patient_name": "Jane Roe", "body": "…", "updated_at": "2026-09-23T23:49:44Z" }] }
```

## POST /notes *(auth)*

Create or replace the note for a patient (one note per patient name,
case-insensitive, whitespace-normalised).

```json
// request
{ "patient_name": "Jane Roe", "body": "Suspected angina; stress echo ordered." }

// 200 — the stored note
{ "patient_name": "Jane Roe", "body": "…", "updated_at": "…" }

// 422 — validation failure (empty or >120-char name)
```

## GET /patients *(auth)*

Distinct patient labels the clinician has tagged across screenings, notes and
consultations, with per-source counts and last activity, merged
case-insensitively (whitespace-normalised).

## GET /patients/timeline?patient=NAME *(auth)*

All of the clinician's records under that patient label: `screenings[]`,
`note`, `consultations[]`. Variants of the name (case/spacing) are merged.
404 when the clinician has no record under the name.

## POST /auth/change-password *(auth)*

Body `{ current_password, new_password }`. Verifies the current password,
rotates the stored hash, revokes **all** sessions, and returns a fresh
`{ token, user }` for the caller. 401 on wrong current password.

## GET /auth/sessions · DELETE /auth/sessions/{id} · POST /auth/sessions/revoke-others *(auth)*

List active sessions (`id` is a public 12-char prefix, `current` marks this
device), revoke one, or revoke every session except the caller's.

## GET /auth/audit *(auth)*

The clinician's own audit trail (sign-ins, sign-outs, password changes,
session revocations), newest first, capped at 100 entries.

## POST /symptom-match *(auth)*

Dictionary-tuning aid: what the NLP extractor finds in a narrative,
without saving anything to history.

**Request**
```json
{ "text": "seene mein dard hai aur pasina aa raha hai" }
```

**200**
```json
{
  "text": "seene mein dard hai aur pasina aa raha hai",
  "symptoms": ["chest pain", "sweating"],
  "matched_phrases": { "chest pain": "seene mein dard", "sweating": "pasina" },
  "count": 2,
  "learned_generation": 17, "learned_count": 3
}
```

Negation-aware: "no chest pain but severe dizziness" yields only
`dizziness` — "but" terminates the negation window (ADR-013). Urdu
script is normalised before matching and the negator may follow the
noun phrase ("دل کا درد نہیں ہے" yields nothing, ADR-014). Runs with
the signed-in clinician's learned vocabulary applied (ADR-015);
`learned_generation` / `learned_count` describe the overlay in effect,
and a taught phrase shows up in `matched_phrases` suffixed `" (learned)"`.

---

## Self-learning — per-clinician taught vocabulary (ADR-015)

Clinicians teach PulseIQ their patients' own words: teach that a phrase
means one of the nine clinical concepts, or teach a suppression regex for
phrasings that must never count as a symptom. Everything is scoped to the
signed-in account at the SQL level — one clinician's vocabulary never
affects another's extraction. Concepts are constrained to the nine the
pipeline knows (`valid_concepts` in the list response); unknown ones are
rejected with 422. Extraction hot-reloads on the next spoken line after
any write: a generation counter bumps on every mutation and per-owner
overlays reload when it changes. Stored in
`backend/data/learned_vocabulary.db` (env `PULSEIQ_LEARNED_DB`), capped at
500 entries per clinician. Teach/suppress/clear events land in
`GET /auth/audit`.

## GET /learning/vocabulary *(auth)*
Everything this clinician taught.

**200**
```json
{
  "phrases": [ { "id": 3, "concept": "dizziness", "phrase": "sir halka ho raha", "origin": "feedback", "created_at": "2026-09-30T10:12:00Z" } ],
  "suppressions": [ { "id": 1, "pattern": "my chest is a size", "note": "clothing, not symptom", "created_at": "…" } ],
  "generation": 17,
  "valid_concepts": ["chest pain", "…nine concepts…"]
}
```
`origin` is `feedback` (taught from the concept-chip controls during a
consultation) or `manual` (taught from the learning panel form).

## POST /learning/teach *(auth)*
**Request** `{ "concept": "dizziness", "phrase": "sir halka ho raha", "origin": "feedback" }`
— `origin` defaults to `manual`; phrase is normalised to lowercase,
whitespace-collapsed, ≤120 chars, deduplicated per (owner, concept).

**200** `{ "item": { …row as above, plus "created": true|false… }, "generation": 18 }`
**422** unknown concept, blank phrase, or vocabulary full (500 entries)

## POST /learning/suppress *(auth)*
Teach a regex that must never count as a symptom mention — checked
**before** the built-in dictionary, so a matching line yields no findings.

**Request** `{ "pattern": "my chest is a size", "note": "clothing, not symptom" }` — pattern ≤200 chars, validated at write time.

**200** `{ "item": { "id": 1, "pattern": "…", "note": "…", "created_at": "…" }, "generation": 19 }`
**422** blank/invalid regex, or duplicate of an existing pattern

## DELETE /learning/phrase/{id} *(auth)* · DELETE /learning/suppression/{id} *(auth)*
Forget one taught phrase or suppression. **200** `{ "ok": true, "generation": 20 }`
· **404** if the row is not owned by the caller.

## DELETE /learning/vocabulary *(auth)*
Forget everything this clinician taught.
**200** `{ "ok": true, "removed": 7, "generation": 21 }`

## POST /screen-report *(auth)*
Reference-range screening of report text — parses lab values (16
unit-aware analytes) and text-only ECG findings, flags
abnormal/critical results first, and explains every flag with the
matched text and the band it was judged against. Pure read; nothing is
stored. Additions in this wave (ADR-016).

**Request** `{ "text": "Troponin I: 0.05 ng/mL. Potassium 6.4 mmol/L. LVEF 35%." }`

**200** `{ "values": [{ "key", "name", "value", "value_text", "unit",
"reference", "status", "severity" (critical|abnormal|normal),
"matched_text", "explanation", "note" }], "text_flags": [{ "name",
"severity", "matched_text", "explanation" }], "summary": {
"critical", "abnormal", "normal", "parsed" }, "message" }`
**401** unauthenticated · **200** with `"error": "text is required"` on empty input

## POST /soap-note *(auth)*
Structured SOAP note built strictly from the encounter content —
Subjective/Objective from transcript entities and report context,
Assessment carries the screening band plus a not-a-diagnosis
qualifier. Deterministic, not LLM-generated, so it cannot invent
findings.

**Request** `{ "transcript": [{ "speaker", "text" }] | "free text…",
"symptoms": ["chest pain"], "report_text": "…", "risk_level": "Medium" }`

**200** `{ "note": { "subjective": [...], "objective": [...],
"assessment": [...], "plan": [...], "entities": { "medications",
"durations", "risk_factors" }, "note" } }`

## POST /extract-entities *(auth)*
Medications (with dose), duration expressions and negation-aware risk
factors found in a transcript. Not stored.

**Request** `{ "text": "On aspirin 75 mg, diabetic, chest pain for 3 days" }`
**200** `{ "entities": { "medications": [{ "name", "dose_mg",
"matched" }], "durations": [...], "risk_factors": [...] } }`

## POST /medication-review *(auth)*
Medication options and safety review for one encounter (ADR-017). Deterministic
rules over a curated cardiac drug table — no LLM — producing indication-driven
options, allergy/condition/laboratory blocks, interaction screening against the
documented medications, and an explicit list of what was *not* supplied. Nothing
is stored.

**Request** — at least one of `text`, `report_text` or patient context:
```json
{
  "text": "crushing chest pain radiating to the left arm, sweaty, allergic to aspirin",
  "report_text": "Troponin I: 0.09 ng/mL. Potassium 5.8 mmol/L. eGFR 28. LVEF 30%",
  "age": "68",
  "sex": "male",
  "conditions": ["hypertension", "prior MI"],
  "allergies": ["aspirin"],
  "current_medications": ["warfarin", "metoprolol 25 mg"],
  "labs": { "platelets": 90 }
}
```
| field | notes |
|---|---|
| text / report_text | narrative and lab/ECG text; concepts, mentioned medications and allergy phrases are extracted from them |
| conditions | free text or canonical tags — history phrasing ("stent 2023", "previous MI", "asthma") is mapped to tags |
| current_medications | names or common brand names (Disprin, Concor, Crestor, Xarelto…), used for interaction screening and "already documented" detection |
| labs | optional numeric additions/overrides (e.g. platelets, which the report parser does not cover) merged with values parsed from `report_text` |

**200**
```json
{
  "symptoms": ["sweating", "chest pain"],
  "diagnosis": { "…the /diagnose payload with risk_level…" },
  "medications": {
    "pathway": { "urgency": "emergency|urgent|routine", "statement": "…", "rationale": ["…"] },
    "indications": [ { "name": "suspected_acs", "triggered_by": "chest pain reported (suspected acute coronary syndrome)" } ],
    "patient_profile": { "age": 68, "sex": "male", "conditions": ["prior_mi"], "condition_text": [], "allergies": ["aspirin"], "current_medications": [], "current_medication_classes": [], "labs_considered": { "renal_severe": 28 } },
    "recommendations": [ { "drug": "Aspirin", "drug_class": "antiplatelet", "status": "recommended|alternative|already-documented", "priority": 1, "indications": ["suspected_acs"], "triggered_by": ["chest pain reported (…)"], "dose_note": "…", "monitoring": ["…"], "review_flags": ["…"], "evidence": "ACC/AHA chest pain guideline — …", "action": "…" } ],
    "contraindicated": [ { "drug": "Metformin", "drug_class": "biguanide", "status": "contraindicated|review-before-use", "severity": "absolute|relative", "blocks": [ { "kind": "allergy|condition|lab", "severity": "…", "trigger": "renal_severe", "note": "eGFR <30 mL/min — metformin is contraindicated." } ], "already_documented": false, "note": "…", "evidence": "…" } ],
    "allergy_alerts": [ { "drug": "Aspirin", "drug_class": "antiplatelet", "matched_terms": ["aspirin"], "action": "…", "alternative": "For suspected ACS/PCI, a P2Y12 inhibitor alone is the usual aspirin-free route…" } ],
    "interaction_alerts": [ { "pair": ["p2y12", "anticoagulant"], "drugs": ["clopidogrel", "anticoagulant"], "severity": "major|moderate", "note": "…", "action": "…" } ],
    "monitoring_plan": ["Potassium and creatinine at 1–2 weeks"],
    "missing_information": ["No drug allergies recorded — ask before prescribing (this blocks allergy screening)."],
    "summary": "6 option(s) offered, 7 blocked or flagged for review, 2 interaction(s) flagged — based on 6 captured indication(s).",
    "disclaimer": "Decision support only — these are options for a qualified clinician to review…"
  },
  "extracted": { "entities": { "medications": [], "durations": [], "risk_factors": [] }, "allergies_from_text": ["aspirin"], "labs_used": { "potassium": 5.8, "troponin": 0.09 } }
}
```
Every option and every block names the captured fact behind it (`triggered_by`,
`blocks[].trigger`), each allergy block ships with an alternative route, and only
one RAAS strategy is offered (an ARB alongside an ACE inhibitor comes back as
`status: "alternative"`). Values that were never supplied — allergies, age,
current medications, eGFR, potassium — are listed in `missing_information`
rather than assumed. `pathway.urgency` escalates on the screening band or a
raised troponin regardless of the medication list.

**401** unauthenticated · **200** `{"error": "text, report_text or patient context is required"}` on an empty request

## POST /fhir-export *(auth)*
One encounter's structured findings as a FHIR R4 ``Bundle`` (ADR-019) — the
EHR-shaped hand-off the competitive assessment asked for. Deterministic and
offline: no LLM, no terminology server, nothing stored, and no new dependency.

**Request** — the same visit fields the workspace already holds. At least one of
the narrative, the report text or the patient context is required:
```json
{
  "patient_name": "Demo Patient", "patient_age": "68", "patient_gender": "Male",
  "visit_date": "2026-10-11", "doctor_name": "Dr. Demo",
  "chief_complaint": "crushing chest pain",
  "text": "crushing chest pain radiating to the left arm, sweaty",
  "report_text": "Troponin I: 0.09 ng/mL. Potassium 6.1 mmol/L.",
  "risk_level": "High",
  "symptom_notes": ["chest pain", "sweating"],
  "conditions": ["hypertension", "prior MI"],
  "allergies": ["aspirin"],
  "current_medications": ["warfarin 5 mg"],
  "pregnancy": false,
  "report": { …the /final-report payload, optional… }
}
```
| field | notes |
|---|---|
| text / report_text | narrative and laboratory text; concepts, conditions, medications, allergy phrases and unit-aware values are derived from them — the same extraction the live copilot uses |
| conditions | free text or canonical tags; history phrasing is mapped to canonical problems, and unrecognised entries are exported as written |
| allergies / current_medications | recorded lists; placeholders ("none", "NKDA") are never emitted as clinical records |
| pregnancy | `true`/`false` when recorded; absent means *not recorded* |
| report | when supplied, its sections become the documented consultation note instead of the deterministic SOAP note |

**200**
```json
{
  "bundle": {
    "resourceType": "Bundle", "type": "collection", "timestamp": "2026-10-11T09:30:00Z",
    "meta": { "tag": [{ "system": "urn:pulseiq:source", "code": "pulseiq-export" }] },
    "entry": [ { "fullUrl": "urn:uuid:…", "resource": { "resourceType": "Patient", "id": "…" } } ]
  },
  "fhir_version": "4.0.1",
  "resource_counts": { "Patient": 1, "Practitioner": 1, "Encounter": 1, "Condition": 3, "Observation": 3 },
  "missing_information": ["No drug allergy recorded — allergy screening could not be represented."],
  "caveats": ["Patient.birthDate is the year derived from the recorded age (68) — accurate to about ±1 year, not a recorded date of birth."],
  "medication_summary": "6 option(s) offered, 7 blocked or flagged for review — based on 2 captured indication(s).",
  "disclaimer": "Decision-support export from PulseIQ. Resources are unconfirmed and must be reviewed by a clinician before being filed in an EHR."
}
```
Resources emitted, and what keeps each one reviewable:

| resource | represents | the marker that stops it reading as fact |
|---|---|---|
| Patient | the recorded name, administrative gender and a birth year derived from the recorded age | `birthDate` is year-only and the derivation is listed in `caveats`; `gender: "unknown"` when not stated |
| Practitioner | the clinician named on the visit | — |
| Encounter | the visit itself (ambulatory, `period.start`, `reasonCode` = chief complaint) | — |
| Condition | reported symptoms (SNOMED/UMLS from the curated knowledge-graph map) and recorded history | `verificationStatus: provisional` (symptoms, noted "not a diagnosis") / `unconfirmed` (history, text-only code) |
| Observation | laboratory values from `report_text` (quantity, unit text, reference range, interpretation) plus the screening risk band | the band is a `survey` Observation whose code says decision-support |
| AllergyIntolerance | each reported drug allergy | `verificationStatus: unconfirmed`, `criticality: unable-to-assess` |
| MedicationStatement | the documented current medications | `status: active` — recorded, not prescribed here |
| DetectedIssue | the medication safety findings (allergy conflicts, condition/laboratory blocks, interactions) | `status: preliminary`, `severity` `high`/`moderate`, mitigation = the alternative route |
| DocumentReference | the consultation note as a base64 `text/plain` attachment | `docStatus: preliminary` |

Coding is deliberately conservative: symptoms carry the SNOMED/UMLS codes this
repository already curates, everything else is `text` only (no guessed
SNOMED/ICD-10/LOINC), and quantities carry unit *text* without a UCUM code. The
DocumentReference holds the deterministic SOAP note (or the supplied final
report) — never the transcript.

**401** unauthenticated · **200** `{"error": "text, report_text or patient context is required"}` on an empty request

## Non-goals
- No pagination or filtering; lists are capped (200 entries, newest first;
  learned vocabulary is capped at 500 entries per clinician).
- No batch endpoints; one narrative / one WS frame per call.
- No cross-account access of any kind; there are no admin endpoints.
- No EHR write-back and no external terminology service: `/fhir-export` returns a
  file the clinician chooses to hand to a system. Nothing is pushed anywhere and
  no code is fetched from a terminology server.
- The SPA at `:5173` is served by Vite, not by the API.
