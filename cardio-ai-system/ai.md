# ai.md — rules for any AI coding agent in this repo

(Mirror of CLAUDE.md and .cursorrules — keep all three in sync.)

## What this project is

PulseIQ: local-first cardiac screening + consultation workspace.
FastAPI backend on :8000, React 18 + Vite + TypeScript frontend on :5173.
No database. No auth. No API keys required. 17 rule-grounded clinical
agents under agents/. Model artifact under models/.

## Rules you must not break

1. Zero-key guarantee: every LLM-powered feature must degrade to the
   built-in rule engine (backend/ai_assistant.py `_local_*` functions).
   New LLM features implement the same three-tier pattern
   (local → Ollama auto-detect → Gemini-if-key).
2. spaCy is optional. Symptom extraction is a curated dictionary
   (agents/nlp_symptom_agent.py). Never gate pipeline behaviour on spaCy.
3. Pipeline entry is orchestrator.run_diagnosis_from_text only. Routes in
   api_server.py never import agents directly. Risk banding thresholds
   (>0.75 High / >0.45 Medium) exist only in orchestrator.risk_from_probability.
4. No agent imports another agent.
5. heart.csv labels are inverted upstream; train_model.py flips and asserts.
   Never remove that assertion.
6. No server-side persistence of patient data. Frontend history in
   localStorage, capped at 20 entries.
7. Domain errors: HTTP 200 + {"error": "..."} per docs/API_SPEC.md.
8. Doc sync: route/payload changes → docs/API_SPEC.md; dependency changes →
   docs/TECH_STACK.md; decision reversals → docs/ADR.md (new ADR at bottom).

## Verification checklist

- Backend tests: `.venv/Scripts/python -m pytest backend -q`
- Frontend: `cd frontend && npm run typecheck && npm run build`
- Optional UI sweep: `cd frontend && npm run ui-audit`
- If this machine blocks sklearn/spacy .pyd files (Windows Application
  Control), a venv-local shim (.venv/Lib/site-packages/sitecustomize.py)
  already stubs the blocked module so the model loads; recreate it if the
  venv is rebuilt — see docs/COMPATIBILITY.md. CI is green.

## Style summary

Python: stdlib-first, minimal deps. TypeScript/React: functional components,
hooks, `@/` alias, existing shadcn ui kit, Tailwind, lucide-react icons.
