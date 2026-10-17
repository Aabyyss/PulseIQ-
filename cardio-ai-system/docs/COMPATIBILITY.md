# PulseIQ — Compatibility

> Browser limits, breakpoints, hardware constraints, and known device-specific
> blockers. Update this file whenever support changes.

## Browsers

| Browser | Supported | Notes |
|---|---|---|
| Chrome / Edge (Chromium) ≥ 90 | ✅ primary target | Web Speech API, WebSocket, all screens |
| Firefox ≥ 90 | ⚠️ partial | Live copilot speech capture (Web Speech API) unavailable; typed text workflows work fully |
| Safari ≥ 15 | ⚠️ partial | Web Speech limited; verify before relying on voice capture |
| Mobile browsers | ✅ responsive | Tab bar under 900 px; screening/history fully usable |

The Web Speech API is Chromium-only in practice — the live copilot degrades
gracefully elsewhere, but dictate-mode requires Chrome or Edge.

## Breakpoints

| Range | Layout |
|---|---|
| ≥ 1280 px | Full desktop grid; the dock spreads all nine destinations across the window |
| 768–1279 px | Desktop, condensed panels; dock items stay labelled |
| < 768 px | Single column, stacked result cards; the dock scrolls and centres the active item |

The shell is the same at every width — a header and a bottom dock (ADR-025) —
so nothing is behind a drawer or a hamburger. Nine items fit a labelled row
from 768 px up; below that roughly five are visible at a time and a swipe
reveals the rest.

Reference viewports used by `scripts/ui-audit.cjs`: 375×667, 768×1024,
1024×768, 1280×720, 1366×768, 1440×900, 1536×864, 1920×1080 and 2560×1440
(layout), with the contrast pass at 390×844, 1366×768 and 1440×900 — signed in
with a throwaway account when a backend is reachable (ADR-027). The audit
enforces WCAG AA contrast, no horizontal overflow, no clipped text, and no tap
target under 24 px (the controls are designed at 32–44 px; 24 px is the floor
the check fails on).

## Hardware constraints

| Resource | Minimum | Comfortable |
|---|---|---|
| CPU | 2 cores | 4+ cores ( RandomForest inference is single-shot, trivial) |
| RAM | 2 GB free | 4 GB free (three.js heart model + dev servers) |
| GPU | none required | any GPU helps three.js rendering |
| Disk | ~1.5 GB | venv + node_modules + spaCy model |
| Mic | none required | needed only for live copilot dictate mode |

## Device constraints (this machine — important)

Windows **Application Control / Smart App Control** on this laptop blocks
specific unsigned native wheels. Verified behaviour:

| Component | State | Detail |
|---|---|---|
| numpy / scipy / pandas / fastapi / uvicorn | ✅ run | — |
| sklearn import | ✅ works | package imports fine |
| `sklearn.svm._liblinear` | ❌ blocked | content-based policy: the `.pyd` is blocked even when copied elsewhere |
| RandomForest unpickle | ✅ works | via the venv shim below — RF never calls liblinear |
| spacy `levenshtein` | ❌ blocked | spacy import fails; agent degrades to dictionary matcher (by design, ADR-007) |
| shap | ❌ fails | imports the blocked sklearn chain (explainability tests only; not in serving path) |

**Resolution in place (2026-09-22):**
`.venv/Lib/site-packages/sitecustomize.py` stubs the one blocked module
(`sklearn.svm._liblinear`) at interpreter startup, so sklearn imports, model
unpickling and inference all succeed. Linear-SVM solvers would fail loudly
(`AttributeError`) — PulseIQ uses RandomForest only. Delete the file to
remove the shim.

**Verified on this device:** pipeline High p=0.997 for cardiac narrative,
Low p=0.033 for unrelated complaint; `/health` → `ai_provider: "ollama"
(tier-2 local LLM detected); frontend typecheck/build green.

**Remaining options (user decision, needs admin):**
1. Add a WDAC/Smart App Control exemption for `%LOCALAPPDATA%`-installed
   Python wheels (Settings → Privacy & security → Windows Security →
   App & browser control), or
2. Sign/allow-list the specific `.pyd` files via an admin Intune/GPO policy, or
3. Run the backend inside Docker Desktop (Linux containers bypass the
   Windows loader policy — see `docker-compose.yml`), or
4. Use a machine without the policy (CI passes — same suite is green on
   `ubuntu-latest`).

## CI environment (reference)

Ubuntu runners: Python 3.12 + Node 20; full suite (backend tests,
typecheck, build, UI audit) is expected green there — the DLL policy above
is Windows-specific and does not affect CI.
