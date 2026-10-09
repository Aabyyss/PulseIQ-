# PulseIQ Frontend

React + Vite + TypeScript app for the PulseIQ FastAPI backend, styled with Tailwind and shadcn-compatible components.

**No API keys required.** The backend ships with a built-in clinical language engine that works fully offline; an optional [Ollama](https://ollama.com) install upgrades text quality automatically.

## Run locally

1. Start the backend (from the project root):

```powershell
.venv\Scripts\python -m uvicorn backend.api_server:app --reload --port 8000
```

2. Install and start the frontend (from `frontend/`):

```powershell
npm install
npm run dev
```

The dev server proxies `/api/*` (including the `/ws` WebSocket) to `http://localhost:8000`.

## Pages

| Route | What it does |
| --- | --- |
| `/` | Home: feature overview and quick actions |
| `/diagnose` | Symptom screening with risk gauge + AI guidance + report image reading |
| `/live` | Live consultation copilot: realtime speech-to-text, chat transcript, doctor prompts, body pain map |
| `/workflow/start` | Guided consultation workflow overview |
| `/workflow/session` | Full consultation capture: visit details, voice, pain map, PDF export |
| `/medications` | Medication review: options, allergy/condition/lab blocks and interactions from the encounter, conditions, history, allergies and current medications |
| `/notes` | Private per-patient notes |
| `/patients` | Per-patient timeline (screenings, note, saved visits) |
| `/security` | Active sessions and account activity |
| `/history` | Locally stored screening history with stats |
| `/agents` | Research agent registry |

The legacy `/diagnose`, `/live` and `/workflow/*` paths forward to
`/consultation`.

## Optional AI upgrades

- `ollama pull llama3.2` → richer AI text (auto-detected, free, local)
- `ollama pull llama3.2-vision` → enables report-image reading locally
- `GEMINI_API_KEY` env var → uses Gemini for LLM/vision if you already have a key

## Checks

```powershell
npm run typecheck
npm run build
```
