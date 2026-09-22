# PulseIQ — System Architecture

> Macro-level view of how the frontend client, FastAPI server, clinical agents,
> and the trained model interact. Endpoint-level detail lives in
> [`API_SPEC.md`](API_SPEC.md); runtime sequencing lives in
> [`DATA_FLOW.md`](DATA_FLOW.md); rationale for each choice lives in
> [`ADR.md`](ADR.md).

## 1. Bird's-eye view

```
┌─────────────────────────────── Browser (localhost:5173) ───────────────────────────────┐
│  React 18 SPA (Vite dev server / static build)                                         │
│  ┌──────────┬──────────┬────────────┬─────────────┬────────────┬──────────────┐        │
│  │ Overview │ Diagnose │ Live       │ Workflow    │ History    │ Agents       │        │
│  │  /       │  /diagnose│ Copilot   │ /workflow/* │  /history  │  /agents     │        │
│  └────┬─────┴────┬─────┴─────┬──────┴──────┬──────┴─────┬──────┴──────┬───────┘        │
│       │ fetch    │ fetch     │ WebSocket   │ fetch      │ (local      │ fetch          │
│       │ /api/*   │ /api/*    │ /ws/*       │ /api/*     │  storage)   │ /api/*         │
└───────┼──────────┼───────────┼─────────────┼────────────┼─────────────┼────────────────┘
        │          │           │             │            │             │
        ▼          ▼           ▼             ▼            ▼             ▼
┌─────────────────────────────── FastAPI (localhost:8000) ────────────────────────────────┐
│  api_server.py   routes · CORS · /health · WebSocket endpoint                           │
│        │                                                                                │
│        ├──► orchestrator.py      extraction → feature map → model → risk band            │
│        │        │                                                                       │
│        │        ├──► agents/nlp_symptom_agent.py      (spaCy + dictionary matcher)       │
│        │        ├──► agents/feature_mapper_agent.py   (concepts → 13 model inputs)       │
│        │        └──► agents/prediction_agent.py       (joblib → RandomForest)            │
│        │                └──► models/heart_model.pkl + heart_model_meta.json              │
│        │                                                                                │
│        ├──► ai_assistant.py      three-tier reasoning (local ▸ Ollama ▸ Gemini)          │
│        │        ├── insights · copilot plan · final report · image analysis              │
│        │        └── graceful degradation to tier 1 on any LLM failure                    │
│        └──► realtime_service.py  per-line fusion for the live copilot (WS)               │
│                 └──► agents/pain_mapper_agent.py · agents/heart_region_agent.py          │
│                                                                                  │      │
│  17 rule-grounded modules in agents/ — each isolated, replaceable, dictionary-          │
│  driven (guidelines, uncertainty, causality, fairness, robustness, …)                   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
        │                        │
        ▼                        ▼
  data/heart.csv           Optional local LLM (Ollama :11434) or Gemini key
  (training only)          — auto-detected, never required
```

**No database exists.** Everything is stateless per request; persistence is the
browser's localStorage (last 20 screenings). See §5.

## 2. Layers & responsibilities

| Layer | Location | Responsibility | Talks to |
|---|---|---|---|
| Presentation | `frontend/src` | Auth gate, routing, screens, Web Speech capture, body-map rendering, PDF export (jsPDF) | Backend REST + WS |
| Auth & storage | `backend/auth_store.py` | SQLite store: users (PBKDF2), hashed session tokens, owner-scoped screenings & consultations | api_server |
| Auth dependency | `backend/auth.py` | Bearer-token resolution → `get_current_user`; 401 shape, WS `?token=` support | auth_store |
| API | `backend/api_server.py` | Route handlers, auth routes, CORS, validation of required fields, WS loop | Orchestrator, AI assistant, realtime service, auth_store |
| Orchestration | `backend/orchestrator.py` | The 5-stage pipeline: extract → map → predict → band → return | NLP, mapper, prediction agents |
| Clinical agents | `agents/*.py` | 17 isolated rule-grounded modules (symptom vocab, feature tiers, pain map, regions, …) | Each other via orchestrator / realtime service only |
| Reasoning | `backend/ai_assistant.py` | LLM strategy with mandatory local fallback; prompts, JSON parsing, provider probing | Ollama / Gemini / built-in rules |
| Realtime | `backend/realtime_service.py` | Per-transcript-line fusion: translation, diagnosis, pain map, copilot plan | Orchestrator, ai_assistant, pain/region agents |
| Model artifact | `models/heart_model.pkl` | Trained RandomForest (300 trees) over 13 features | Loaded once at import by prediction agent |
| Training | `backend/train_model.py` | Retrain from `data/heart.csv`, flip inverted target, assert directionality, write metadata | data/, models/ |

## 3. Key design rules

1. **The orchestrator is the only pipeline entry.** Routes never call agents
   directly; `run_diagnosis_from_text` is the single path (also reused by the
   realtime service), so banding (`>0.75 High / >0.45 Medium / else Low`) is
   consistent everywhere.
2. **Agents never import each other sideways.** A module is imported by the
   orchestrator, the realtime service, or the API layer — never by a sibling
   agent. This keeps every agent replaceable without ripple effects.
3. **Every LLM capability must degrade.** `ai_assistant` always keeps a
   rule-based `_local_*` implementation. Network/model failures are caught and
   silently downgraded — the app must never hard-require a key or a model.
4. **Every user-data route is owner-scoped.** Handlers take the user from
   `Depends(get_current_user)` only — never from the request body — and pass
   `user["id"]` into `auth_store`, which filters every query by `owner_id`.
   Cross-account access must be structurally impossible (enforced by
   `backend/test_auth.py`).
5. **The model artifact is load-once at import.** `prediction_agent` loads
   `heart_model.pkl` at module import; the API process assumes it exists.
   Retraining rewrites it and bumps `heart_model_meta.json`.
6. **The frontend never calls the backend origin directly in dev.** All HTTP
   goes through the Vite proxy (`/api/*` → `:8000` stripped, `/ws` proxied as
   WebSocket), so no CORS friction exists in development.

## 4. Frontend composition

- **Auth gate** (`src/App.tsx`): `RequireAuth` wraps every workspace route;
  unauthenticated visitors are redirected to `/login` (registration and
  sign-in share the page). Session restored from a stored bearer token via
  `GET /auth/me`.
- **Routes**: `/login` (public) · `/` overview · `/diagnose` · `/live` ·
  `/workflow/start` · `/workflow/session` · `/history` · `/agents`,
  wildcard → `/`.
- **Shell**: `components/app/app-shell.tsx` renders nav + mobile tab bar +
  per-user footer chip with sign-out.
- **UI kit**: shadcn-style primitives under `components/ui` (Radix + CVA +
  tailwind-merge), aliased as `@/…`.
- **3D**: `components/Heart3DModel.tsx` uses react-three-fiber on the overview.
- **State**: `AuthProvider` context for the session; all history is fetched
  from the backend per page — no global store.

## 5. Persistence model

| What | Where | Lifetime |
|---|---|---|
| Accounts + password hashes | `backend/data/pulseiq.db` (SQLite) | until deleted |
| Session tokens (SHA-256 hashes) | same DB, `tokens` table | 30 days rolling |
| Screening history (last 200) | same DB, `screenings` table, owner-scoped | until user clears |
| Consultation records | same DB, `consultations` table, owner-scoped | until user clears |
| Session token + cached profile | browser localStorage | until sign-out / 401 |
| Model + metadata | `models/` on disk | until retrained |
| Datasets | `data/heart.csv` | static |

The SQLite store is file-based, zero-dependency, and written behind a lock;
WAL mode keeps concurrent clinician sessions safe. The database file holds
patient-derived content once real records exist — treat it as PHI (see
`SECURITY.md`) and never commit or sync it.

## 6. Failure & degradation matrix

| Failure | Behaviour |
|---|---|
| Ollama not running | Auto-falls back to local rule engine |
| Gemini call fails / bad JSON | Falls back to local rule engine |
| spaCy or its model missing | Dictionary matcher still extracts symptoms |
| Model file missing | Process fails at import — run `train_model.py` (loud, intentional) |
| Backend down | Frontend shows its offline banner; sign-in disabled until it returns |

## 7. Extension points

- New symptom concept → `agents/nlp_symptom_agent.py` dictionary.
- New model input → mapper tiers + `feature_names` in prediction agent +
  retrain (see `DATA_FLOW.md` §3).
- New agent → one file in `agents/`, register in the realtime service or
  orchestrator, and add an entry in `API_SPEC.md` consumers if exposed.
