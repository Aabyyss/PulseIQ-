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

## ADR-010 · Multi-user accounts with server-side, owner-scoped history
**Status:** Accepted (2026-09-23) — supersedes ADR-006

The product now serves multiple cardiologists on one machine. Each clinician
gets an account; screenings and consultations are stored server-side in
SQLite (`backend/data/pulseiq.db`) and are visible **only** to the account
that created them. This replaces the single-user localStorage history model.

**Why SQLite, not Postgres:** zero-install, file-based, matches the
device-local deployment posture (ADR-008), and the concurrency profile (a
handful of clinicians, one server) is trivial. The store is stdlib `sqlite3`
behind a lock with WAL mode — no ORM, no new dependencies.

**Why bearer tokens, not cookies:** the SPA already speaks `fetch` with
headers; tokens keep `allow_credentials=False` correct with the wide CORS
posture (ADR-005); WebSockets authenticate via `?token=`. Tokens are stored
hashed (SHA-256) so the DB file alone grants no sessions. Passwords are
PBKDF2-SHA256 (200k iters, per-user salt).

**Invariants (enforced by `backend/test_auth.py`):** every history query
filters by `owner_id` from the token-resolved user; cross-account reads and
deletes are structurally impossible (delete → 404); `/health` stays public;
the WS closes with 4401 without a valid token.

**Consequences:** ADR-006's "no server-side database" stance is retired; the
DB file becomes PHI-bearing once real records exist (see `SECURITY.md`). Any
new user-data endpoint must take `Depends(get_current_user)` and pass the id
into `auth_store` — never accept an owner id from the client.

## ADR-011 · Reliability hardening for the multi-user server
**Status:** Accepted (2026-09-23)

With accounts now holding irreplaceable clinical records, four cheap guards
were added: (1) **login rate limiting** — in-memory fixed-window counters,
5 failures ⇒ 15-minute lockout per (IP, email), 429 responses; resets on
restart by design since the threat is on-device credential stuffing.
(2) **Startup DB backups** — SQLite backup API + WAL checkpoint on every
server start, last 10 kept in `backend/data/backups/`; a failed backup never
blocks startup. (3) **8 MB request cap** via middleware — 413 above it.
(4) **Frontend resilience** — 15 s fetch timeout with one automatic retry
for transient network errors, and a top-level React error boundary so a
render crash shows a recovery screen instead of a white page.

**Consequences:** Restore procedure = stop server, copy a backup over
`pulseiq.db`, restart. CI now runs the auth suite (`test_auth.py`, 24
checks) so isolation and lockout regressions fail the build.

## ADR-012 · Negation-aware extraction, patient timeline and session controls

Date: 2026-09-24. Status: accepted.

Three changes shipped together because they share one motivation — a
cardiologist must be able to defend every number the workspace shows.

1. **Negation-aware extraction.** The dictionary matcher is substring-based,
   so "denies chest pain" previously scored as chest pain. A cue window (3
   meaningful words, connectors transparent) now suppresses negated mentions.
   Limitation: cue-after-subject forms ("chest pain denied") still match —
   accepted because dictated narratives put the cue first, and the false
   positive is visible in the concepts list.
2. **Patient timeline.** Tagged screenings, notes and consultations roll up
   per patient (`/patients`, `/patients/timeline`), owner-scoped like every
   other record. Name variants merge case-insensitively after whitespace
   normalisation; the deliberately-typed note spelling wins for display.
3. **Session controls and audit.** Password change rotates all sessions,
   revocation is per-session or "everyone else", and an append-only audit
   log records auth events for the account owner. The UI auto-locks after
   15 idle minutes.

## ADR-013 · Patient-language symptom vocabulary

Date: 2026-09-25. Status: accepted.

The matcher only recognised clinical phrasings ("dizziness",
"shortness of breath"), so narrated speech — "I feel dizzy and tired",
"heart is racing", "saans lene mein taklif hai" — extracted nothing.
Decisions:

- The dictionary now covers **casual English, Roman Urdu and Urdu
  script** for nine concepts: chest pain, shortness of breath,
  dizziness, palpitations, fatigue, nausea, sweating, leg swelling and
  cough. Matching stays lowercase substring, so entries double as
  stems ("chakkar" catches "chakkar aa rahe hain").
- Bare high-collision stems ("tired", "weak") match **whole words
  only** via a small regex pass — bare "tired" would otherwise match
  "retired". No other regex matching is introduced.
- **"but" terminates the negation window** instead of bridging it:
  polarity flips at contrast ("no chest pain but severe dizziness").
- Referred-pain phrasings ("pain radiating to my jaw") map to the
  chest-pain concept; isolated orthopedic complaints still match
  nothing. Bare "سوجن" (swelling) is excluded so abdominal swelling
  cannot trigger the cardiac edema concept.
- New concepts are carried through the pipeline: calibrated feature
  shifts (isolated edema lands Medium; isolated cough stays Low),
  copilot follow-up questions with acute-cardiac priority, SNOMED/UMLS
  links, pain-map points and cardiac-region inferences.
- `POST /symptom-match` returns concepts plus matched surface phrases
  without persisting, so vocabulary can be tuned against real
  transcripts without code changes.

Known limitation (unchanged from ADR-012): cue-after-subject negation
("chest pain denied") still matches; the concepts list stays visible to
the clinician for exactly this reason.


## ADR-014 · Urdu-robust capture, dual-text extraction and hands-free control

Date: 2026-09-26. Status: accepted.

Real Urdu consultations exposed three failure layers: the same word
arrives with arabic or urdu codepoints and optional vowel marks, the
negator sits AFTER the noun phrase where the matcher only looked
before it, and a flaky LLM translation could erase the findings
entirely. Voice UX had no "is it hearing me?" signal, and ending a
visit always required a click. Decisions:

- **Normalisation before matching.** Urdu-script text is canonicalised
  (alef/yeh/heh variants unified, harakat/tatweel/ZWNJ stripped) on
  both server and client; the word count is preserved so negation
  windows stay valid. The frontend mirrors the backend map.
- **Post-phrase negation window.** A lookahead window carries only
  symptom-ceasing cues ("nahi", "resolved", "gone") so "chest pain
  without sweating" still flags both, closing the gap ADR-013 noted.
  Punctuation rides on words ("resolved,"), so window tokens are
  cleaned before cue comparison.
- **Roman Urdu as whole words.** Loosely transliterated symptom words
  (chakkar, dharkan, pasina, saans, khansi, matli, thak) match as
  whole words with every plausible spelling; negation applies to
  whole-word matches too, and collision-prone strings ("hospital")
  stay unmatched.
- **Dual-text extraction.** The dictionary understands Urdu directly,
  so extraction runs on BOTH the original and translated line and
  unions the findings; translation failure degrades coverage instead
  of losing the encounter. The translated narrative remains the
  diagnosis input.
- **Hands-free commands.** Final speech results are checked against
  command patterns BEFORE joining the transcript: "save visit" (and
  Urdu "save karo") triggers the same guarded save as the button,
  "clear transcript" resets the session; commands never enter the
  record.
- **Mic level meter.** A second AudioContext tap renders a smoothed
  RMS bar with a speech-active state, making muted or blocked input
  visible in seconds. It is cosmetic and tears down with the session.
- **Korean capture.** ko-KR joins the input languages; analysis is
  translation-based like the other non-English locales.

Consequence: the vocabulary test suite covers orthography variants,
post-phrase negation and whole-word collisions; the copilot page
shows instant concepts per line regardless of translator health, and
the whole visit can be run without touching the keyboard.

## ADR-015 · Clinician-in-the-loop learned vocabulary (self-learning)
**Status:** Accepted (2026-09-29)

Every deployment serves patients whose own words never appear in any
dictionary — regional idioms, family phrasings, ASR quirks specific to
one clinic's microphone. Hard-coding every variant does not scale and
cannot anticipate a vocabulary that is local to one practice. PulseIQ
therefore lets the clinician teach the extractor, per account:

- **Teach a phrase → concept.** "This phrase means chest pain" is stored
  and honoured by every extraction from the next line onward.
- **Teach a suppression.** A regex whose matches never count as symptoms
  (admin chatter, recording artifacts) — a matching line extracts as
  nothing.
- **One-line correction in the live UI.** Each matched concept chip carries
  a "not a symptom" action that teaches the suppression from the encounter
  itself.

Decisions:

- **Per-clinician scoping, SQL-enforced.** Learned rows carry ``owner_id``
  and every read/write filters on it — the same isolation model as
  screenings and consultations (ADR-012). What one clinician teaches never
  leaks into another account; cross-account deletes are structurally 404.
- **Separate SQLite database** (``backend/data/learned_vocabulary.db``).
  The security-critical accounts store is never schema-coupled to
  fast-moving learning features; the learned DB can be inspected or reset
  independently.
- **Overlay, not fork.** Learned phrases extend the extraction at one well-
  defined seam — an optional ``learned`` argument — rather than mutating
  the built-in dictionary. Built-in behaviour is byte-identical when no
  overlay is passed, and the model/feature pipeline never sees a concept
  outside the nine it maps (the API rejects unknown concepts).
- **Negation is not bypassable.** Taught phrases run through the same
  before/after negation windows as the dictionary, so "no <taught phrase>"
  is still a denial. Learning extends recall; it cannot weaken polarity.
- **Hot reload via generation counter.** Writes bump a ``meta.generation``
  row; extraction overlays are cached per owner and reloaded only when the
  generation changes (one small SELECT per line, no timers, no restart).
- **Full auditability.** Every teach/forget is recorded in the account audit
  log with the phrase, and learned matches are labelled "(learned)" in the
  matched-phrase details so clinicians always see which findings came from
  their own teaching.

Rejected alternatives: global shared vocabulary (privacy + wrong for
region-specific idioms); fine-tuning the LLM on corrections (needs GPU,
hours to apply, opaque); background auto-learning from transcripts
(unreviewed vocabulary in a clinical tool is a safety hazard — a human
must authorise every learned entry).

Consequence: ``backend/test_learning.py`` covers the teach→apply→forget
round-trip, isolation, negation interaction, suppression and the REST
surface; the consultation page exposes the correction controls and the
vocabulary panel in both consult modes.

---

## ADR-016 · Privacy, grounding and evaluation hardening (review wave)
**Status:** Accepted (2026-10-02)

A seven-point external review (privacy, self-learning safety, hallucination
control, speech/NLP, report screening, pain localisation, evaluation)
produced this wave of changes. Each point was audited against the existing
code first; what already held was left alone, what was missing was added
in the same rule-first, offline-capable style as the rest of the system.

Decisions:

- **De-identification at the chokepoint** (``backend/deidentify.py``).
  CNIC, phone (PK + international), email and *labelled* names (``patient
  name: …``, honorifics) are replaced with tagged placeholders before any
  free text reaches storage (screenings, consultations) or the learned
  vocabulary (teach phrases are de-identified too). Bare capitalised words
  are never touched — clinical text is full of them — and redaction events
  are written to the account audit log (``privacy.redacted``). Deliberate
  clinician-entered filing labels (patient name field) stay as-is; the
  record is theirs to label.
- **Explicit recording consent in the capture card.** The microphone
  cannot start until the clinician ticks "Patient consent obtained";
  consent state is stored with the saved visit (``consent_obtained``) and
  withdrawal immediately blocks restart. Audio itself is never stored —
  the browser transcribes it — so consent covers transcription, not
  retention.
- **A source beside every suggestion** (``agents/attribution_agent.py``).
  Deterministic keyword→guideline map (ACC/AHA, ESC, ACEP, OPQRST, HRS)
  labels each doctor question, test and next step; the honest fallback
  says "derived from this encounter" rather than faking a citation. The
  map is rule-derived so sources are stable and verifiable — an LLM
  asked to cite itself is exactly the hallucination channel this guards.
- **Plan confidence with an "insufficient information" state.** Three
  honest tiers (low/moderate/high) from corroborating concepts +
  probability; when nothing has been detected the plan explicitly says
  "Not enough information yet" instead of emitting a direction. Shown as
  a badge on the Suggested-questions panel with the reason on hover.
- **Reference-range report screening** (``backend/lab_report.py``,
  ``POST /screen-report``). 16 cardiac-relevant analytes with unit-aware
  bands (mg/dL vs mmol/L, ng/mL vs ng/L), 9 text-only ECG findings, and a
  hard rule: every flag carries matched text, the reference band and a
  plain-language explanation, sorted critical→abnormal→normal. This is
  flagging, never diagnosis — a reference-range check a clinician can
  overrule.
- **Medical entity extraction + SOAP note** (``backend/medical_entities.py``).
  Medications (with dose), durations, and negation-aware risk factors,
  extracted in the same deterministic style as symptoms; the SOAP note is
  a *structured restatement* of captured content, not LLM prose, so it
  cannot invent findings. Empty encounter → the note says so.
- **Pain characteristics (OPQRST) in the front end** (``bodyPain.ts``).
  Character, duration, triggers/relief and radiation are regex-extracted
  over the accumulated transcript (English + Urdu/Roman-Urdu) and shown
  as a four-quadrant card; an empty quadrant reads "not stated yet" — the
  UI prompts the clinician to ask rather than guessing.
- **An offline evaluation harness** (``backend/evaluation.py``). Standard
  WER (Levenshtein, corpus-aggregated), symptom-extraction P/R/F1 against
  a 16-case labelled dataset (every case carries its ``source``), and a
  correctly-scored SUS instrument. The benchmark runs with no network and
  no LLM so numbers are reproducible; the WER sanity set is explicitly
  marked as placeholder until real ASR output is captured.

Rejected alternatives: cloud de-identification services (leaves the
clinic network — defeats the local-first premise); LLM-written sources
(hallucinated citations); auto-generating SOAP prose from the LLM
(plausible-but-wrong is the failure mode the review warned about);
storing audio for later re-analysis (retention without need — the
review's own point); claiming Whisper-level WER without measuring it.

Consequence: 56+ new/existing offline tests pass, frontend typecheck and
build are green; the new endpoints (``/screen-report``, ``/soap-note``,
``/extract-entities``) are auth-gated and store nothing.

## ADR-017 · Medication recommendation and safety review (pharmacology agent)
**Status:** Accepted (2026-10-10)

The pipeline answered "how urgent is this presentation?" but not the next
question a clinician asks: *which drugs are reasonable here, and which are
unsafe for this patient?* Trainees running the demo asked for exactly that —
options that respect the conditions, the past history, the allergies and the
current medication list.

Decision: an 18th rule-grounded agent (``agents/pharmacology_agent.py``) with a
thin orchestrator entry (``run_medication_review``), an auth-gated endpoint
(``POST /medication-review``) and a workspace page (``/medications``). The agent
is deterministic and offline like every other agent: a curated cardiac drug
table, a condition/history vocabulary, allergy matching by drug *and* drug
class, numeric laboratory gates (eGFR, creatinine, potassium, sodium,
haemoglobin, platelets, LDL, LVEF, troponin), an interaction table and a
monitoring plan.

Rules that keep the output reviewable rather than authoritative:

- **Every entry names its trigger.** An option carries ``triggered_by``
  ("history of myocardial infarction", "LVEF 30%"); a block carries
  ``blocks[].trigger`` with kind allergy / condition / lab. Nothing appears
  because a model felt like it.
- **An allergy resolves the therapy question.** Blocking aspirin returns the
  aspirin-free route (P2Y12 inhibitor per protocol) instead of leaving a hole.
- **One RAAS strategy at a time.** Because ACE inhibitor + ARB is a harmful
  combination, the ARB comes back as ``status: "alternative"`` when the ACE
  inhibitor is offered, so the pair is never presented in parallel.
- **Blocked agents the patient already takes are called out** ("already
  documented — review and consider stopping with the prescriber"), because the
  dangerous finding in practice is often a drug the patient should not be on.
- **Missing facts are reported, not assumed.** No allergy list, no age, no
  current medications, no eGFR/potassium → explicit ``missing_information``
  entries; a patient of childbearing age with unknown pregnancy status is a gap.
- **Escalation is independent of the drug list.** ``pathway.urgency`` is
  emergency on the High band or a raised troponin, so a tidy medication list can
  never soften an ACS presentation.

Rejected alternatives: LLM-written medication advice (the plausible-but-wrong
failure mode ADR-016 guards against — a plausible drug recommendation is worse
than none); calling a commercial drug-interaction API (breaks the
never-require-network rule, adds a licence and a data-sharing question, and the
common cardiac interactions fit a reviewable local table); auto-dosing (doses
stay protocol-anchored text in ``dose_note`` for the clinician to prescribe);
folding the review into the ``/diagnose`` payload (silently changes an existing
contract and forces every screening to carry patient context it does not have).

Consequence: the backend suite is 81 tests (24 new directional cases — allergy
blocks, asthma blocks beta-blockade, eGFR 26 blocks metformin, hyperkalaemia
blocks RAAS blockade and MRAs, pregnancy blocks statin/ACE inhibitor,
antiplatelet + anticoagulant is a major interaction, missing input is reported);
no new dependency; nothing stored; the endpoint returns 401 unauthenticated.

## ADR-018 · Live medication safety screen inside the consultation loop
**Status:** Accepted (2026-10-11)

ADR-017 shipped the medication review as a page: the clinician types the
encounter, submits, reads the options and the blocks. But the question it answers
— *which drugs are reasonable here, and which are unsafe for this patient?* — is
asked **during** the consultation, not after it. A patient who says "and I am
allergic to aspirin" on the fourth line, a lab note that reads "eGFR 26", or a
condition mentioned in passing all change the answer while the clinician is
still talking.

Decision: the same deterministic review is now part of every live copilot line.
Each ``analysis`` frame on ``WS /ws/consultation`` carries a
``medication_review`` field, rebuilt from (a) the visit details the clinician
recorded on the consultation screen — age, sex, conditions/history, allergies,
current medications, pregnancy — and (b) everything said so far. It rides on the
existing frame rather than a second endpoint, and the frontend renders it as a
"Medication safety" card beside the body map: a field filled mid-consultation
applies to the next line without a reconnect.

Rules that keep the live screen honest:

- **One set of union rules.** The context a review is judged against (recorded
  facts ∪ extracted entities ∪ condition vocabulary ∪ allergy phrases ∪
  unit-aware labs from the report text ∪ narrative symptoms) lives in
  ``backend/encounter_context.build_medication_context``, used by both
  ``POST /medication-review`` and the live loop. Two assemblies would eventually
  disagree about the same patient — the worst possible outcome for a safety
  screen, and the reason the endpoint's own extraction moved there too.
- **Stateless recomputation beats remembered state.** The review is rebuilt from
  the encounter text the client sends, not accumulated in a per-connection
  buffer: a cleared transcript therefore clears the screen instead of leaving
  stale findings behind, and a reconnecting client gets the same answer.
- **Gaps stay gaps.** Blank form fields are omitted from the wire payload rather
  than sent as "none", and an unset pregnancy select means *not recorded*, not
  *not pregnant* — the review reports them in ``missing_information`` instead of
  screening against an assumed healthy patient.
- **The screen can never soften the presentation.** ``pathway.urgency`` still
  escalates on the diagnosis band or a raised troponin, independent of the drug
  list (ADR-017).
- **Nothing new is required.** No new endpoint, no new dependency, nothing
  stored; the field is additive, so a client that ignores ``medication_review``
  keeps working.

Rejected alternatives: a ``POST /medication-review`` call per spoken line from
browser (two round-trips per line, and the same visit details would travel twice
in two different shapes); caching the review per socket session and patching it
incrementally (state that can drift from the recorded facts, and it survives a
cleared transcript as stale advice); an LLM-written live safety note (the
plausible-but-wrong failure mode ADR-016/017 reject — a hallucinated allergy
clearance is the worst output this system could produce); auto-prescribing from
live options (doses stay protocol-anchored text for the clinician).

Consequence: 13 new directional cases in
``backend/test_live_medication_review.py`` — a recorded allergy blocks before a
single line is spoken, an allergy/condition/medication said out loud counts with
the form empty, later lines add without erasing earlier findings, a cleared
transcript leaves nothing stale, report values from the visit note reach the
laboratory gates, and the socket frame carries the review (LLM tier stubbed) —
bringing the backend suite to 94 tests. The page and the live loop serve the same
rules; nothing stored; no new dependency.
