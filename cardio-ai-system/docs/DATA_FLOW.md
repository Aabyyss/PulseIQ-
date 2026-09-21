# PulseIQ — Data Flow

> How a sentence becomes a score, and how a live encounter becomes a report.
> Structural layers: [`ARCHITECTURE.md`](ARCHITECTURE.md). Contract-level
> payloads: [`API_SPEC.md`](API_SPEC.md).

## 1. Screening pipeline (POST /diagnose → 5 deterministic stages)

```
Narrative text  "chest pain going to my left arm since morning, sweating"
   │
   ▼
[1] nlp_symptom_agent.extract_symptoms_from_text
   │   spaCy pipeline (en_core_web_sm) + curated dictionary match
   │   multi-lingual phrases (English / Urdu script / Roman Urdu)
   │   → ["chest pain", "shortness of breath", …]
   ▼
[2] feature_mapper_agent.map_symptoms_to_features
   │   concept → empirical feature tiers → all 13 inputs with explicit ranges
   │   → {age:52, sex:1, cp:2, trestbps:140, chol:240, …}
   ▼
[3] prediction_agent.predict_heart_disease
   │   joblib → RandomForest(300) → predict + predict_proba
   │   → (prediction=1, probability=0.83)
   ▼
[4] orchestrator.risk_from_probability
   │   >0.75 → High · >0.45 → Medium · else Low
   ▼
[5] JSON response
   { text, symptoms[], features{}, prediction, probability, risk_level }
```

Every intermediate is returned to the client — the UI renders all five stages,
which is the product's core promise ("screening that explains itself").

## 2. AI reasoning flow (three tiers with forced fallback)

```
generate_ai_insights / copilot plan / final report / image analysis
   │
   ├─ provider probe (cached)
   │    Ollama reachable? ──► tier 2  (local LLM, JSON-mode prompt)
   │    GEMINI_API_KEY set? ─► tier 3  (Gemini HTTP, JSON-mode prompt)
   │    else ───────────────► tier 1  (built-in rule engine)
   │
   ├─ LLM path:  prompt → raw text → _safe_parse_json → validated keys
   │             any failure (timeout, HTTP, JSON) ─► tier 1 _local_* result
   └─ tier 1 path: deterministic composition from the diagnosis dict
```

The caller never knows which tier answered; only `/health` and route payloads
expose `ai_provider`.

## 3. Feature contract (the 13 model inputs)

| # | Feature | Type | Notes |
|---|---|---|---|
| 1 | age | int | years |
| 2 | sex | 0/1 | 1 = male |
| 3 | cp | 0–3 | chest-pain type |
| 4 | trestbps | int | resting BP (mm Hg) |
| 5 | chol | int | cholesterol (mg/dl) |
| 6 | fbs | 0/1 | fasting sugar >120 |
| 7 | restecg | 0–2 | resting ECG result |
| 8 | thalach | int | max heart rate |
| 9 | exang | 0/1 | exercise-induced angina |
| 10 | oldpeak | float | ST depression |
| 11 | slope | 0–2 | ST slope |
| 12 | ca | 0–4 | vessels seen in fluoroscopy |
| 13 | thal | 0–7 | thalassemia marker |

Mapper tiers were measured against the trained model, not guessed: a clear
exertional presentation must land High and an unrelated complaint Low. If you
touch the mapper, re-run `backend/test_orchestrator.py` — it asserts those
directions.

## 4. Realtime consultation (WebSocket /ws/consultation)

Per inbound line, in order:

```
{speaker, text, report_text, language_code}
   │
   ├─ translate_to_english        (LLM if non-en, else passthrough)
   ├─ run_diagnosis_from_text     (same 5-stage pipeline as §1)
   ├─ map_symptoms_to_pain_points (pain_mapper_agent)
   ├─ cardiac_regions             (heart_region_agent)
   └─ generate_ai_copilot_plan    (questions, tests, next steps, urgency)
   ▼
{speaker, transcript, original_transcript, language_code, report_text,
 symptoms, diagnosis, pain_points, cardiac_regions,
 doctor_next_questions, patient_recommendations, ai_copilot}
```

The connection is one loop per session; any single line that raises still
returns an `{"error": …}` frame so the UI keeps running.

## 5. Persistence & state flow

```
Screening:  React state ──► localStorage (max 20) ──► /history charts
Workflow:   page state (unstructured "session") ──► POST /final-report
            ──► jsPDF client-side ──► user's Downloads
Model:      data/heart.csv ──► train_model.py ──► models/heart_model.pkl
            + heart_model_meta.json (asserts label direction)
```

No identifiers, narratives, or transcripts ever persist server-side; the
backend is stateless per request. See [`SECURITY.md`](SECURITY.md).

## 6. Storage & "ERD" notes

There is no relational database. The only schema-like structures are:

- **localStorage records**: `{ id, timestamp, text, symptoms[], features{},
  prediction, probability, risk_level }` — capped at 20, LRU-evicted.
- **Model metadata JSON**: name, algorithm, trained_at, sklearn version,
  dataset, target encoding, 13 feature names, metrics block.
- **Agent registry** (`/research-agents`): static list of 10 research agents
  with name + focus strings (the other 7 runtime agents are pipeline-internal).

If a server-side store is ever introduced, start from ADR-008 and keep the
no-identifiers rule from `SECURITY.md`.
