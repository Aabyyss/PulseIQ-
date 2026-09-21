# PulseIQ — Architecture Decision Records

> Running log of *why* the system is the way it is. Newest ADRs at the bottom.
> When a decision is reversed, mark the old one "Superseded by ADR-XXX" — do
> not delete history.

**Status legend:** Accepted · Proposed · Superseded

---

## ADR-001 · Random Forest as the screening model
**Status:** Accepted (2026-09-16)

The public heart dataset (1,025 rows × 13 features) is small and tabular.
Tree ensembles dominate there; deep nets overfit and add GPU requirements.
`RandomForestClassifier(n_estimators=300, random_state=42)` reached
accuracy 0.971, F1 0.971, ROC-AUC 1.0 in stratified 5-fold CV, and RF gives
usable feature importances for the explainability agent. No serving infra:
the model is a pickle loaded once at import.

**Consequences:** Model and sklearn version are coupled (see
`heart_model_meta.json`); retrain after any sklearn major upgrade.

## ADR-002 · The inverted-target fix is enforced in code, not docs
**Status:** Accepted (2026-09-16)

The widely circulated `heart.csv` ships with `target=1` meaning *healthy* —
a genuine defect that silently inverts every downstream score. PulseIQ flips
the label at training time **and** `train_model.py` asserts that textbook
disease profiles score *higher* than textbook healthy profiles before writing
the artifact.

**Consequences:** The defect can never silently return; anyone retraining
inherits the assertion.

## ADR-003 · Three-tier AI with a mandatory local fallback
**Status:** Accepted (2026-09-16)

No paid key and no network may ever be a prerequisite: the demo must work for
a clinician with no LLM at all. Strategy: built-in rule engine (tier 1, always
on) → Ollama local LLM (tier 2, auto-detected) → Gemini free tier (tier 3,
only if a key is already present). Every LLM call is wrapped so any failure
degrades to tier 1 rather than erroring the route.

**Consequences:** `get_active_provider()` is cached; after changing Ollama
or key state, the process must restart (or `reset_provider_cache()` called)
for re-probing. Outputs differ by tier — tests only assert on tier 1.

## ADR-004 · Rule-grounded agents instead of LLM-agents
**Status:** Accepted (2026-09-16)

The 17 modules in `agents/` are deterministic, dictionary-driven and
testable. LLM behaviour would make the clinical pipeline untestable and
non-reproducible. LLMs sit *outside* the deterministic core (ai_assistant /
realtime translation only) and never gate it.

**Consequences:** Adding vocabulary = editing a dictionary; adding behaviour
= one isolated module. No prompt changes can alter risk scores.

## ADR-005 · FastAPI + Vite proxy, no CORS friction in dev
**Status:** Accepted (2026-09-16)

FastAPI gives async + WebSockets + automatic OpenAPI with one dependency.
The Vite dev server proxies `/api/*` → `:8000` (prefix stripped) and `/ws`
as WebSocket, so the SPA never targets an absolute backend URL and CORS
never bites in development.

**Consequences:** `allow_origins=["*"]` with `allow_credentials=False` is a
dev posture. If the app is ever served publicly, tighten per `SECURITY.md`.

## ADR-006 · No server-side database; localStorage only
**Status:** Accepted (2026-09-16)

The product is local-first: zero accounts, zero cloud. History = last 20
screenings in localStorage; the consultation workflow is per-session. A DB
would add setup steps that contradict the zero-configuration promise.

**Consequences:** No multi-device sync, no audit trail. Revisit via a new
ADR if a store is ever added (see ADR-008 posture).

## ADR-007 · spaCy optional, dictionary matcher essential
**Status:** Accepted (2026-09-16)

spaCy (`en_core_web_sm`) is used for tokenisation/UX, but the real symptom
extraction is a curated multi-lingual dictionary. spaCy (and its native
deps) can be missing — e.g. blocked by Windows Application Control on some
machines — and screening still works identically; the agent degrades to a
no-op tokenizer.

**Consequences:** Don't add logic that *requires* spaCy; the dictionary is
the contract. CI installs the model best-effort and still passes without it.

## ADR-008 · Deployment posture: local device, not a server
**Status:** Accepted (2026-09-16)

PulseIQ ships to *devices*, not servers: PowerShell/cmd launchers, no
containers required, no secrets to manage. That is why docker-compose is
provided as an optional parity environment (Linux containers on Windows)
rather than the primary path.

**Consequences:** If PulseIQ is ever deployed as a public service, ADR-005's
CORS posture, the no-auth stance, and `SECURITY.md` must be revisited first.

## ADR-009 · Governance-by-docs for AI agents and humans
**Status:** Accepted (2026-09-22)

This documentation set (ARCHITECTURE / DATA_FLOW / API_SPEC / TECH_STACK /
COMPATIBILITY / CONVENTIONS / SECURITY / CLAUDE.md / .cursorrules / ai.md /
Makefile / docker-compose) is the contract that keeps human and AI
contributors from drifting: routes must match API_SPEC, versions must match
TECH_STACK, style must match CONVENTIONS. AI workspace rules live in
`CLAUDE.md`, `.cursorrules`, and `ai.md` — keep the three in sync.

**Consequences:** Documentation updates are part of "done" for any contract
change; a PR that edits routes without editing API_SPEC is incomplete.
