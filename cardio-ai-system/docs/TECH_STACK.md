# PulseIQ — Tech Stack (pinned)

> Strict reference for exact framework/runtime versions. Code and docs must
> match this file. Environment-enforcing files: `.nvmrc` (Node), `.tool-versions`
> (asdf/mise: python + node), `requirements.txt` (Python floor), and
> `frontend/package.json` (JS deps).

## Runtimes

| Runtime | Required | Pinned here | Installed on this device | Notes |
|---|---|---|---|---|
| Python | ≥ 3.10 | `3.12` (CI, `.tool-versions`) | **3.14.7** | ≥3.10 per README; CI uses 3.12. 3.14 works on this device. |
| Node.js | ≥ 18 | `20` (`nvmrc`, `.tool-versions`, CI) | **v26.7.0** | v26 runs the toolchain fine. |
| npm | ships with Node | — | **11.19.0** | `package-lock.json` is authoritative for installs. |

## Backend (Python)

| Package | Requirement (requirements.txt) | Installed on this device |
|---|---|---|
| fastapi | ≥ 0.116 | 0.141.1 |
| uvicorn[standard] | ≥ 0.35 | 0.53.0 |
| pandas | ≥ 2.2 | 3.0.5 |
| scikit-learn | ≥ 1.5 | 1.9.1 (matches model metadata) |
| shap | ≥ 0.46 | 0.52.0 |
| spacy | ≥ 3.8 | 3.8.16 |
| en_core_web_sm | 3.8.0 | 3.8.0 (installed) |

**Rule:** the trained artifact (`models/heart_model.pkl`) is version-coupled to
scikit-learn — check `models/heart_model_meta.json` → `sklearn_version`
(1.9.1) and retrain if you bump the major version.

## Frontend (JS/TS)

| Package | Pinned (package.json) |
|---|---|
| react / react-dom | ^18.3.1 |
| react-router-dom | ^6.28.0 |
| vite | ^5.4.11 |
| typescript | ^5.6.3 |
| tailwindcss | ^3.4.15 |
| @vitejs/plugin-react | ^4.3.3 |
| three / @react-three/fiber / @react-three/drei | ^0.171.0 / ^8.17.10 / ^9.121.4 |
| @radix-ui/* (tabs, slot, tabs, separator, alert-dialog) | ^1.x |
| lucide-react | ^0.468.0 |
| jspdf | ^2.5.2 |
| class-variance-authority / clsx / tailwind-merge | ^0.7 / ^2.1 / ^2.5 |
| playwright-core (dev, UI audit) | ^1.63.0 |

`bun.lock` exists but **npm is the package manager of record**
(`package-lock.json` + CI `npm ci`).

## Build & test commands

| Task | Command (from `cardio-ai-system/`) |
|---|---|
| Backend API | `.venv/Scripts/python -m uvicorn backend.api_server:app --port 8000` (Windows) |
| Backend tests | `.venv/Scripts/python -m pytest backend -q` |
| Frontend dev | `cd frontend && npm run dev` → :5173 |
| Typecheck | `cd frontend && npm run typecheck` |
| Production build | `cd frontend && npm run build` |
| UI audit | `cd frontend && npm run ui-audit` |
| Makefile equivalents | `make help` (see `Makefile`) |

## Environment enforcement files

| File | Purpose |
|---|---|
| `frontend/.nvmrc` | Node 20 for nvm/fnm/volta users |
| `cardio-ai-system/.tool-versions` | asdf/mise: python 3.12, nodejs 20 |
| `requirements.txt` | Python floors |
| `frontend/package-lock.json` | exact JS tree |

## Known device constraint (this machine)

Windows **Application Control** blocks certain unsigned native wheels
(`sklearn.svm._liblinear`, spacy `levenshtein`) — content-based, survives file
copies. A venv-local `sitecustomize.py` shim stubs the blocked module so the
model loads and the API serves on this device (spacy still degrades to its
dictionary matcher, by design). Full detail: `COMPATIBILITY.md` §Device
constraints.
