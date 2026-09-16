<div align="center">

# 🫀 PulseIQ

### Cardiac screening that explains itself.

**The application lives here. This folder is the complete implementation — backend, agents,
frontend and model.**

[![License: MIT](https://img.shields.io/badge/License-MIT-35d1ba?style=flat-square)](../LICENSE)

[**📘 Full overview, screenshots and quickstart**](../README.md) ·
[**🌐 Project page**](https://aabyyss.github.io/PulseIQ-/) ·
[**▶ Walkthrough video**](docs/demo/pulseiq-demo.mp4)

</div>

---

## What's in here

| Path | Contents |
|---|---|
| `backend/` | FastAPI server, training script (with the inverted-label fix), pipeline checks |
| `agents/` | 17 rule-grounded clinical modules — guidelines, uncertainty, causality, fairness, explainability… |
| `frontend/` | React 18 + Vite + TypeScript application (see its [own README](frontend/README.md)) |
| `models/` | Trained model and metadata |
| `data/` | Public heart dataset |
| `docs/` | Screenshots and the demo walkthrough |
| `scripts/` | `capture-screenshots.cjs` — regenerates the documentation screenshots |
| `*.ps1`, `*.cmd` | Setup, run and one-click launcher scripts |

## Fast start

```powershell
# Windows — or double-click Start-PulseIQ.cmd
.\setup.ps1
.\run-backend.ps1     # terminal 1
.\run-frontend.ps1    # terminal 2  →  http://localhost:5173
```

<details>
<summary><b>macOS / Linux</b></summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

uvicorn backend.api_server:app --port 8000                 # terminal 1
cd frontend && npm install && npm run dev                  # terminal 2
```
</details>

No API keys, no accounts. The built-in clinical engine works fully offline; an optional
[Ollama](https://ollama.com) install upgrades the text quality automatically.

## Scope

A screening and documentation aid — **not** a diagnostic device. Output must be reviewed by a
qualified clinician before informing care. See the full
[scope note](../README.md#%EF%B8%8F-scope) in the main README.
