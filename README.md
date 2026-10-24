<div align="center">

<img src="cardio-ai-system/docs/screenshots/01-overview.png" alt="PulseIQ overview screen" width="100%">

# 🫀 PulseIQ

### Cardiac screening that explains itself.

**An open-source clinical workspace that turns a patient's own words into an explained
risk estimate — then carries the encounter through to a structured report.**

Runs locally. No cloud account, no API keys, no data leaves the device — the clinician account the first launch asks for is a row in a SQLite file on your own machine.

[![Test suite](https://github.com/Aabyyss/PulseIQ-/actions/workflows/tests.yml/badge.svg)](https://github.com/Aabyyss/PulseIQ-/actions/workflows/tests.yml)
[![Publish project page](https://github.com/Aabyyss/PulseIQ-/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/Aabyyss/PulseIQ-/actions/workflows/deploy-pages.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-35d1ba?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

[**🌐 Live project page**](https://aabyyss.github.io/PulseIQ-/) · [**▶ Watch the walkthrough**](cardio-ai-system/docs/demo/pulseiq-walkthrough.mp4) · [**📸 Screenshots**](cardio-ai-system/docs/screenshots) · [**🤝 Contributing**](#-contributing)

</div>

---

## Why PulseIQ exists

Most medical-AI demos quietly depend on a paid LLM key — the demo works until you try it.
**PulseIQ was built to need nothing.** A built-in clinical language engine does all of the
language work offline. An optional free local model upgrades the experience automatically if
one is running. A hosted model is an option, never a prerequisite.

And instead of returning a bare score, every screen shows its reasoning: which concepts were
detected, which model inputs they produced, and what a clinician would reach for next.

## ✨ What it does

| | Feature | What it does |
|---|---|---|
| 🩺 | **Symptom screening** | Free-text narrative → clinical concepts → 13 model inputs → an explained probability, with every step visible |
| 🎙️ | **Live copilot** | Realtime speech-to-text with speaker attribution, suggested questions, recommended investigations and red-flag escalation — plus hands-free voice commands ("save visit") and a live mic level meter |
| 🧍 | **Body pain mapping** | Described pain plots onto a front/back diagram as the encounter runs |
| 📄 | **Consultation reports** | Structured visit capture → one-click PDF export of summary, advice, plan and red flags |
| 🌍 | **Multilingual capture** | 9 capture languages — English, Urdu (script + Roman), Hindi, Arabic, Korean, French, Spanish, German, Mandarin — normalised to English for analysis |
| 🖼️ | **Report reading** | Lab reports and scans parsed for key findings (needs a vision model) |
| 🕘 | **History & review** | Screenings, notes and consultations kept in the local database (newest 200), with band distribution and mean probability |
| 🤖 | **20 clinical agents** | Guidelines, uncertainty, causality, fairness, robustness, explainability — each an isolated, replaceable module |

<div align="center">

| | |
|:---:|:---:|
| ![Screening result](cardio-ai-system/docs/screenshots/03-screening-result.png) | ![Live copilot](cardio-ai-system/docs/screenshots/04-live-copilot.png) |
| *Explained screening result* | *Live consultation copilot* |
| ![Consultation session](cardio-ai-system/docs/screenshots/06-consultation-session.png) | ![Mobile](cardio-ai-system/docs/screenshots/09-mobile-overview.png) |
| *Consultation capture* | *Narrow viewport* |

</div>

## 🆓 The free-AI model (three tiers, none required)

| Tier | What it provides | Setup |
|---|---|---|
| **1 · Always on** | Built-in rule-based clinical engine — insights, copilot plans, reports, fully offline | **Nothing. It's the default.** |
| **2 · Optional** | [Ollama](https://ollama.com) local LLM — richer AI text, still free & local, auto-detected | `ollama pull llama3.2` |
| **3 · Optional** | Gemini free tier — used automatically if you already have a key | `GEMINI_API_KEY` env var |

## 🚀 Quickstart

**What you need:** a Windows, macOS or Linux machine — that's it. On Windows, `setup.ps1`
installs Python 3.12 and Node.js automatically (via winget) if they are missing. First launch
opens a sign-in screen: create your clinician account (it lives only on your machine), then
explore. Optional but recommended for richer AI text: install [Ollama](https://ollama.com) and
run `ollama pull llama3.2` — PulseIQ detects it and upgrades automatically.

**Windows** — or just double-click `Start-PulseIQ.cmd`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1          # one-time: virtualenv, dependencies, spaCy model
.\run-backend.ps1    # terminal 1
.\run-frontend.ps1   # terminal 2  →  http://localhost:5173
```

<details>
<summary><b>macOS / Linux</b></summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

uvicorn backend.api_server:app --port 8000        # terminal 1

cd cardio-ai-system/frontend && npm install && npm run dev    # terminal 2
```
</details>

## 🧠 Model card

Random Forest over the public heart dataset (1,025 rows · 13 features).

> **⚠️ Inverted-target note.** The widely circulated `heart.csv` ships with `target=1` meaning
> *healthy*. PulseIQ flips the label at training time, and the training script asserts that
> textbook disease and healthy profiles score in the expected direction — so this real defect
> in the source data can never silently return.

| Metric | Value |
|---|---|
| Accuracy | 0.971 |
| Precision | 0.943 |
| Recall | 1.000 |
| F1 | 0.971 |
| ROC-AUC | 1.000 |
| 5-fold CV | 0.98 – 1.00 |

## 🏗️ Architecture

```
frontend  React 18 · Vite · TypeScript · Tailwind
  ├── /               overview
  ├── /consultation   live capture  WS /ws/consultation · POST /diagnose
  │                                POST /medication-review · POST /lab-report
  ├── /medications    narrative + record → POST /medication-review
  ├── /history        account-scoped screenings and saved consultations
  ├── /notes          private notes    /patients   per-patient timeline
  ├── /security       sessions, password, audit trail
  ├── /agents         GET /research-agents      /guidance   how to use it
  └── /login /privacy /terms /thank-you

backend  FastAPI (routes in api_server.py)
  ├── orchestrator.py       extraction → feature mapping → model → risk band
  ├── realtime_service.py   per-line fusion across the clinical agents
  ├── ai_assistant.py       three-tier reasoning, none of it required
  ├── auth_store.py         accounts, sessions, screenings, notes (SQLite)
  ├── risk_score_context.py record + wording → HEART · GRACE · CHA₂DS₂-VASc · ASCVD
  ├── lab_report.py         report text → reference-range flags (+ derived lipids)
  └── fhir_export.py        findings → a FHIR R4 Bundle, written to a file

agents/    20 rule-grounded clinical modules
models/    trained model + metadata
```

## 📁 Repository layout

```
cardio-ai-system/
├── backend/     FastAPI server, training script, pytest suite
├── agents/      20 rule-grounded clinical modules
├── frontend/    React application (vitest for the non-React logic)
├── models/      trained model and metadata
├── data/        dataset
├── docs/        design notes (ADR, API spec, data flow, security, CI, medication catalogue) · screenshots · walkthrough video
├── scripts/     demo recording + video encode, screenshot capture, E2E journey, UI audit
└── setup.ps1 · run-*.ps1 · Start-PulseIQ.cmd
```

## 🧪 Quality gates

| Gate | Runs | What it proves |
|---|---|---|
| Backend pytest suite | CI · every push | 280 cases: clinical direction (symptom text → expected risk band), the published scores pinned row-by-row against their sources, the 36-option medication catalogue and its 53 interaction rules pinned to 12 citations, de-identification, the local stores, the login limiter, the FHIR bundle, the live medication screen |
| Backend script checks | CI · every push | The older password-free runners, including the end-to-end pipeline walk (symptom text → mapped features → prediction) — nonzero exit fails the job |
| Frontend unit tests | CI · every push | `npm run test` (vitest + jsdom): extraction patterns, session and retry behaviour, page metadata, PDF pagination |
| Frontend typecheck & build | CI · every push | `tsc -b` plus a production Vite build |
| UI contrast & layout audit | CI · every push | WCAG AA contrast of every text node at 390/1366/1440 px in **both themes**, the account menu and both consult tabs opened and audited, and horizontal-overflow, clipped-text and tap-target sweeps of 12 routes × 9 widths (375–2560 px, the laptop panels included) — signed in, with the dock and account menu required on every route, and any violation fails the run |
| E2E journey | CI · every push | Playwright walks sign-in → capture a line → save → PDF → thank-you → history against the **built bundle** served by `vite preview` and a live API, failing on any console error or failed API call |
| Lint | local | `npm run lint` — zero errors, zero warnings without a `--max-warnings` guard |

## 🤝 Contributing

Issues and pull requests are welcome. Good first areas: more symptom vocabulary, additional
capture languages, and extending the agent registry.

Before submitting, run the suites that CI runs:

```bash
cd cardio-ai-system && make install-dev && python -m pytest backend -q   # 280 cases
cd frontend && npm ci && npm run typecheck && npm run test && npm run lint && npm run build
```

`npm run e2e` and `npm run ui-audit` (both need the servers up) cover the full journey and the
UI gates; `make check` chains the tests, typecheck, lint and build.

CI runs four gates on `ubuntu-24.04` and a `Gate` job that requires all of them
([docs/CI.md](cardio-ai-system/docs/CI.md)); require `Gate` in branch protection rather than
remembering four checks. The `ui-audit` job installs the runtime requirements, starts the API on
the port the built app forwards `/api` to, waits for `/health`, and then sweeps the app **signed
in** in both themes, failing if any route renders the sign-in page instead of itself, if a state
it opens never arrives, or if the workspace shell is missing. The `e2e` job builds the bundle,
serves it with `vite preview` and walks the save path against the real API. Both upload their
logs either way, so a red run can be diagnosed from its artifacts.

## ⚠️ Scope

PulseIQ is a **screening and documentation aid**. It does not diagnose, and its output must be
reviewed by a qualified clinician before informing care. Any presentation suggesting acute
coronary syndrome — ongoing chest pain, syncope or respiratory distress — must be escalated on
clinical grounds alone, regardless of what this software reports.

## 📄 License

MIT — see [LICENSE](LICENSE).

<div align="center">
<sub>Built as an open reference implementation of local-first clinical decision support.</sub>
</div>
