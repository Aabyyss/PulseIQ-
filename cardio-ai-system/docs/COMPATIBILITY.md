# PulseIQ — Compatibility

> Browser limits, breakpoints, hardware constraints, and known device-specific
> blockers. Update this file whenever support changes.

## Browsers

| Browser | Supported | Notes |
|---|---|---|
| Chrome / Edge (Chromium) ≥ 90 | ✅ primary target | Web Speech API, WebSocket, all screens |
| Firefox ≥ 90 | ⚠️ partial | Live copilot speech capture (Web Speech API) unavailable; typed text workflows work fully |
| Safari ≥ 15 | ⚠️ partial | Web Speech limited; verify before relying on voice capture |
| Mobile browsers | ✅ responsive | Five-destination bar plus a More sheet below 1024 px; screening/history fully usable |
| Installed app (standalone) | ✅ Chrome/Edge, iOS 16.4+ | Manifest + service worker; offline shell, no cached `/api` |

The Web Speech API is Chromium-only in practice — the live copilot degrades
gracefully elsewhere, but dictate-mode requires Chrome or Edge.

## Breakpoints

| Range | Layout |
|---|---|
| ≥ 1280 px (`xl`) | Rail + content column; the overview adds its aside column |
| 1024–1279 px (`lg`) | Labelled rail with all nine destinations; no bottom bar |
| 768–1023 px | Phone presentation: five destinations + More; panels condense |
| < 768 px | Single column, stacked cards; five-destination bar, More sheet |
| < 360 px | Same layout; 320 px is the audited floor (WCAG 1.4.10 reflow) |

The shell is one destination list in two presentations (ADR-032): a bottom bar
with five destinations and a More sheet below `lg`, a labelled sticky rail at
`lg` and above. Nothing is behind a hamburger or a drawer. Orientation does not
change the layout rules — the available width does, which is why both tablet
orientations are in the ladder.

Reference viewports used by `scripts/ui-audit.cjs`

- layout (11): 320×640, 375×667, 844×390, 768×1024, 1024×768, 1280×720,
  1366×768, 1440×900, 1536×864, 1920×1080, 2560×1440;
- contrast (4): 390×844, 820×1180, 1366×768, 1440×900, each in both palettes;
- states (2): 1440×900 and 390×844, both palettes — 22 audits;
- focus (2): 1440×900 and 390×844, three routes;
- spacing (2): 1440×900 and 390×844, twelve routes.

Signed in with a throwaway account (ADR-027). The audit enforces WCAG AA
contrast, 1.4.12 spacing overrides, 2.4.11 focus not obscured, no horizontal
overflow, no clipped text (by width or height), and no tap target under 24 px
(controls are designed at 32–44 px; 24 px is the floor the check fails on). It
records where each page landed and fails when a route renders the sign-in page
instead of itself. CI runs it with `--require-sign-in`, which additionally fails
when no backend answers (ADR-028); locally, without that flag, an unreachable
backend still means the public pages are audited and the summary says
`(signed out)`. It also checks installability and that an offline navigation
renders the cached shell (ADR-033).

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

Ubuntu runners, pinned to `ubuntu-24.04`: Python 3.12 + Node 22; the full suite
(backend tests, typecheck, unit tests, build, UI audit) is expected green there —
the DLL policy above is Windows-specific and does not affect CI.

Six jobs. `backend` runs the pytest suite and the script checks (including the
workflow-definition tests), `frontend` typechecks, unit-tests and builds,
`ui-audit` installs the runtime requirements, starts the API on `:8000` (the
port `vite preview` forwards `/api` to), waits for `/health`, then runs the
sweep signed in (ADR-028), `e2e` builds, serves on `:4173` and walks the journey,
`sources` checks the catalogue's citations offline, and `gate` requires all
five. The browser jobs are bounded and upload their reports and server logs on
success as well as failure. Reproduction steps are in [CI.md](CI.md); what each
job proves, and what still needs a human, is in [VERIFICATION.md](VERIFICATION.md).
