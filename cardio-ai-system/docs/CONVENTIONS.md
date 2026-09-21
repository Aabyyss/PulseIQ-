# PulseIQ — Conventions (code style manifesto)

> The style contract for this repo. Human and AI contributors follow it.
> Enforcement today: ESLint + `tsc -b` (frontend), pytest suite (backend),
> UI audit (contrast/layout). Keep new code consistent with what's here.

## Python (backend/ + agents/)

- **Stdlib-first.** No new heavyweight dependency without an ADR entry.
  `ai_assistant.py` deliberately uses `urllib` instead of an HTTP client lib.
- **Module layout:** one concern per file in `agents/`; the filename is the
  contract (`nlp_symptom_agent.py` → symptom extraction). Backend services
  (`api_server`, `orchestrator`, `ai_assistant`, `realtime_service`) stay
  thin; logic belongs in agents.
- **Import direction:** `api_server → orchestrator/ai_assistant/realtime_service
  → agents`. Never agent → agent, never agents → backend.
- **Errors:** domain failures return `{"error": "…"}` payloads with HTTP 200
  (API_SPEC conventions). Raise `RuntimeError` inside ai_assistant when a
  tier is unusable; catch and degrade at the route boundary.
- **Tests:** `backend/test_*.py`, plain functions + `main()` asserting
  clinical directions, runnable via pytest **and** directly (`python
  backend/test_x.py`). New pipeline behaviour needs a directional test
  (e.g. exertional presentation → High band).
- **Model hygiene:** never hand-edit `models/`. Retrain via
  `backend/train_model.py`, which rewrites the pickle + metadata and asserts
  the label direction.

## TypeScript / React (frontend/)

- **Functional components + hooks only.** No class components.
- **Path alias:** import app code via `@/…` (tsconfig + vite alias).
- **UI kit:** reuse `@/components/ui` (shadcn/Radix) primitives before
  rolling custom controls; compose with `cn()` from `@/lib/utils`.
- **Styling:** Tailwind utility classes; avoid inline `style={{}}` except
  dynamic values (chart bars, map markers). Design tokens live in
  `tailwind.config.ts` / CSS variables.
- **Icons:** lucide-react, sized consistently (14–20px stroke icons).
- **Routing:** routes registered in `src/App.tsx`; pages in
  `src/pages/*Page.tsx`; wildcard redirects to `/`.
- **State:** local hooks + fetch. No global state library; history persists
  to localStorage (cap 20) with a single helper module.
- **Types:** no `any` in new code; API payloads typed against
  `docs/API_SPEC.md`; strict mode stays on (`tsc -b` must pass).
- **Hooks discipline:** eslint-plugin-react-hooks is authoritative — early
  returns fine, conditional hooks never.

## Errors & logging

- Backend: `print`/tracebacks only in tests; the server logs via uvicorn.
  Degrade loudly in payloads (`ai_provider` tells the truth) rather than
  swallowing.
- Frontend: show the offline/degraded banner instead of crashing screens;
  every fetch path has a non-hanging catch.

## Git & PRs

- Conventional, imperative subject lines ("Fix copilot fallback when Ollama
  times out").
- A PR that changes the API contract without updating `docs/API_SPEC.md` is
  incomplete; same for version bumps vs `docs/TECH_STACK.md`.
- Run before submitting (README contract):
  `npm run typecheck && npm run build` in `frontend/`, plus the backend
  pytest suite when Python changed.

## Docs map

`docs/ARCHITECTURE.md` (structure) · `docs/DATA_FLOW.md` (sequences) ·
`docs/API_SPEC.md` (contract) · `docs/ADR.md` (decisions) ·
`docs/TECH_STACK.md` (versions) · `docs/COMPATIBILITY.md` (limits) ·
`docs/SECURITY.md` (boundaries).
