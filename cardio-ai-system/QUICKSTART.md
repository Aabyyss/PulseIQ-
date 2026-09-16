# PulseIQ - AI Heart Health Intelligence

**PulseIQ** (formerly Cardio AI System) is a clinical decision-support app that screens
symptoms for cardiovascular risk — with **zero API keys, zero paid services, and zero
configuration**. Everything runs locally on your machine, free forever.

## What's inside

| Feature | Description |
| --- | --- |
| Smart Screening | Describe symptoms in plain language → ML risk score + explanation |
| Live Consultation | Real-time speech-to-text copilot with doctor prompts & patient guidance |
| Body Pain Map | Interactive front/back body diagram highlighting reported pain regions |
| Report Reading | Upload lab reports/scans for AI-assisted key-finding extraction |
| Consultation Workflow | Structured visit capture → one-click PDF report export |
| History | Local record of past screenings with risk trends |

## How the free AI works

PulseIQ uses a **three-tier AI strategy — no key ever required**:

1. **Local engine (always on)** — built-in rule-based clinical language engine handles
   insights, copilot plans, reports, and translations entirely offline.
2. **Ollama (optional, free)** — for richer LLM responses, install [Ollama](https://ollama.com)
   and run `ollama pull llama3.2`. PulseIQ auto-detects it and upgrades automatically.
3. **Gemini (optional)** — if you already have a key, set `GEMINI_API_KEY`; it will be used
   for LLM/vision features. Never required.

## Quickstart (Windows)

```powershell
# 1. One-time setup
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1

# 2. Start backend  (no API key needed!)
.\run-backend.ps1

# 3. Start frontend in a second terminal
.\run-frontend.ps1

# 4. Open the app
# http://localhost:5173
```

Or just double-click **`Start-PulseIQ.cmd`**.

> macOS / Linux: `python -m venv .venv && .venv/bin/pip install -r requirements.txt &&
> .venv/bin/python -m spacy download en_core_web_sm && .venv/bin/uvicorn backend.api_server:app --port 8000`
> then `cd frontend && npm install && npm run dev`.

## Optional upgrades

| Setting | Effect |
| --- | --- |
| Install Ollama + `ollama pull llama3.2` | Smarter AI text everywhere (still free, still local) |
| `ollama pull llama3.2-vision` | Enables report-image reading locally |
| `GEMINI_API_KEY` env var | Uses Gemini as the LLM/vision provider |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Point at a custom Ollama instance |

## Tech stack

- **Backend**: FastAPI, scikit-learn (heart-disease model), spaCy NLP, SHAP explainability,
  17 rule-based clinical agents (guidelines, uncertainty, causality, fairness, ...)
- **Frontend**: React 18 + Vite + Tailwind + Radix UI, Web Speech API, jsPDF, react-three-fiber
- **Privacy**: all data stays on-device; history lives in browser local storage.

## Disclaimer

PulseIQ is an educational/decision-support tool. It does **not** diagnose disease and
does not replace professional medical care. Always consult a qualified clinician.
