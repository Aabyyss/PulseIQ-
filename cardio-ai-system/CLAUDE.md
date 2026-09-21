# CLAUDE.md — AI workspace rules for PulseIQ

Read this before editing anything. These rules keep AI-generated changes
consistent with the architecture documented in `docs/`.

## Project in one line

Local-first clinical screening workspace: FastAPI backend (port 8000) +
React 18/Vite frontend (port 5173). No database, no auth, no API keys
required. Rules-driven 17-agent pipeline + optional LLM tier.

## Non-negotiables

1. **Never require an API key or network.** Every LLM feature must keep its
   `_local_*` fallback in `backend/ai_assistant.py`. New LLM features follow
   the same three-tier pattern (local → Ollama → Gemini).
2. **Never make the pipeline depend on spaCy.** The dictionary matcher in
   `agents/nlp_symptom_agent.py` is the contract (ADR-007). spaCy is optional
   garnish — some machines block its native wheels.
3. **Routes go through the orchestrator.** `api_server.py` handlers call
   `orchestrator.run_diagnosis_from_text`; they never import clinical agents
   directly. Risk banding lives only in `orchestrator.risk_from_probability`
   (>0.75 High / >0.45 Medium / else Low).
4. **Agents never import sibling agents.** Only the orchestrator, realtime
   service, and API layer import agent modules.
5. **Contract changes update docs in the same PR.** New/changed endpoints →
   `docs/API_SPEC.md`. New dependency/version → `docs/TECH_STACK.md`.
   Behaviour change → relevant `docs/*.md` + `docs/ADR.md` entry if it
   reverses a decision.
6. **Target labels are flipped at training time.** `heart.csv` ships
   inverted (target=1 = healthy). `train_model.py` flips and asserts
   directionality — never "fix" this away.
7. **Privacy:** no patient identifiers in new persistence. Frontend history
   stays in localStorage (max 20). No server-side storage without a new ADR.

## Where things live

```
backend/api_server.py        routes + CORS + WS loop        (edit routes here)
backend/orchestrator.py      5-stage pipeline               (pipeline changes here)
backend/ai_assistant.py      3-tier LLM + local fallbacks   (LLM features here)
backend/realtime_service.py  per-line WS fusion             (copilot behaviour here)
agents/*.py                  17 rule-grounded modules       (one concern per file)
models/                      heart_model.pkl + metadata     (never hand-edit)
data/heart.csv               training data                  (training only)
frontend/src/pages/          route screens
frontend/src/components/     app shell, body map, 3D heart, ui/ kit
docs/                        ARCHITECTURE · DATA_FLOW · API_SPEC · ADR ·
                             TECH_STACK · COMPATIBILITY · CONVENTIONS · SECURITY
```

## Commands

```bash
# from cardio-ai-system/
.venv/Scripts/python -m uvicorn backend.api_server:app --port 8000   # backend (Windows)
.venv/Scripts/python -m pytest backend -q                            # backend tests
cd frontend && npm run dev        # :5173
cd frontend && npm run typecheck  # tsc --noEmit
cd frontend && npm run build      # tsc -b && vite build
cd frontend && npm run ui-audit   # contrast/layout sweep
make test / make run-backend ...  # Makefile shortcuts (WSL/Git-Bash+make)
```

## Code style

- Python: stdlib + project patterns; no new heavyweight deps without an ADR.
  Type hints welcome, not enforced. Tests are plain pytest-style scripts in
  `backend/test_*.py` runnable both via pytest and directly.
- TS/React: functional components + hooks, `@/` path alias, existing
  shadcn/Radix components from `components/ui`, Tailwind classes (no inline
  style objects for layout), lucide-react icons.
- Errors: domain failures return `200 {"error": "…"}` (see API_SPEC
  conventions) — match that, don't introduce HTTP error codes ad hoc.

## Known device quirk (this laptop)

Windows Application Control blocks `sklearn.svm._liblinear` and spacy
`levenshtein` (content-based). A venv-local shim
(`.venv/Lib/site-packages/sitecustomize.py`) stubs the blocked module so the
model loads and the API serves; spacy degrades to the dictionary matcher.
Recreate the shim if the venv is rebuilt. Do not "fix" by removing
sklearn/shap — see `docs/COMPATIBILITY.md` §Device constraints.
