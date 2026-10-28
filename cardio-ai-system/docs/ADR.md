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

> The accuracy, F1 and ROC-AUC quoted above were measured on a leaked split
> and are **superseded by ADR-035**. The algorithm choice stands; the numbers
> do not.

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
**Status:** Accepted (2026-10-11) — delivery amended 2026-10-12 (the review
rides the instant ``line_ack`` as well as the ``analysis`` frame)

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
  unit-aware labs from the report text or read out loud ∪ narrative symptoms)
  lives in
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
- **The screen is model-free, so it ships with the line.** The review is
  computed twice per line, deliberately: once in the socket handler, where the
  line, the transcript so far and the visit details are already in hand, and it
  goes out on the instant ``line_ack``; then again in the ``analysis`` frame with
  the diagnosis band and the English translation folded in. Riding only the
  analysis frame made a security-critical screen wait on the copilot plan — a
  local model call measured at ~22 s on CPU for the first analysed line of a
  visit — on a screen whose entire value is being current while the visit is
  spoken. The early snapshot leaves ``pathway.urgency`` to the presentation
  itself (a suspected ACS indication is an emergency with or without a screening
  band), so it cannot soften  the presentation, and the two stages are asserted to
  agree on what they *block* even when their wording differs. The one honest gap
  in the early stage: it reads the line as spoken, so a non-English line can gain
  findings once the translation arrives.
- **A slow plan cannot hold up the next line.** Shipping the review on the ack
  was only half of it: the receiving loop awaited the plan before it would read
  the next message, so line 2's ack waited for line 1's model call and the
  "instant" screen was seconds behind as soon as a plan was slow. Plans now run
  on a per-connection worker, in order, and the loop goes straight back to
  reading. That makes frames interleave (line 2's ack can precede line 1's plan),
  so both frames of a line carry its `line_seq` and the UI applies a screen only
  when it is not older than the one on show — a late plan may refine the screen,
  never rewind it, and nothing in flight repopulates a cleared transcript.
- **Nothing new is required.** No new endpoint, no new dependency, nothing
  stored; the field is additive, so a client that ignores ``medication_review``
  keeps working — and a client that still reads only the ``analysis`` frame sees
  exactly what it saw before.

Rejected alternatives: a ``POST /medication-review`` call per spoken line from
browser (two round-trips per line, and the same visit details would travel twice
in two different shapes); caching the review per socket session and patching it
incrementally (state that can drift from the recorded facts, and it survives a
cleared transcript as stale advice); an LLM-written live safety note (the
plausible-but-wrong failure mode ADR-016/017 reject — a hallucinated allergy
clearance is the worst output this system could produce); auto-prescribing from
live options (doses stay protocol-anchored text for the clinician).

Consequence: ``backend/test_live_medication_review.py`` holds 22 directional
cases (13 at first acceptance, 9 added with the instant-ack path and the worker)
— a recorded allergy blocks before a single line is spoken, an
allergy/condition/medication said out loud counts with the form empty, later
lines add without erasing earlier findings, a cleared transcript leaves nothing
stale, report values from the visit note and values read aloud reach the
laboratory gates, the socket frame carries the review (LLM tier stubbed), the
early ack snapshot blocks on the line that reported it while agreeing with the
analysis frame on every block and interaction it reports, and a second line is
acked in under a second even while the first line's plan is still sleeping on
the model — the case that fails by 2.2 s if the plan is awaited inline again.
With the extractor and screener regressions that brings the backend suite to
130 tests. The page and the live loop serve the same rules; nothing stored; no
new dependency.

Amending this decision surfaced a false positive the live path made obvious: the
allergy phrase pattern used to swallow the rest of its clause, so *"allergic to
aspirin and I take warfarin"* recorded **warfarin** as a reported allergy and
blocked a drug the patient was actually taking — a wrong block on a safety
screen, arriving faster than ever once the screen moved onto the ack. The clause
now ends at the next actor or sentence break ("and I take…", "but takes…"), two
substances in one breath ("aspirin and sulfa") are still both kept, and
``backend/test_pharmacology_agent.py`` plus the live suite pin both directions.

Building the live screen also exposed a second gap, this one in the context
rules: only the report-text box was parsed for laboratory values, so a clinician
*reading* "eGFR 26" off the note out loud changed nothing, even though ADR-018
claimed a lab note read during the visit reaches the gates. Labs are now parsed
from the spoken encounter as well, with a deliberate precedence — speech, then
the written report text, then the values recorded on the form — so a number the
clinician typed always wins over the same number heard in passing.

## ADR-019 · FHIR R4 export of the structured findings
**Status:** Accepted (2026-10-11)

Every other output here is a dead end: a PDF for a human, a SOAP note on screen,
a saved visit only this app can read. The competitive assessment named the
zero-cost fix — *"FHIR JSON export (Condition / Observation / DocumentReference
resources) so the data is EHR-shaped and demonstrable without a hospital
system."* A clinician who cannot hand the findings to their record system keeps
typing them in by hand, and a demo cannot show what an interoperable hand-off
would look like.

Decision: ``backend/fhir_export.py`` turns one encounter's structured findings
into a FHIR R4 ``Bundle`` (type ``collection``), exposed unchanged by the
auth-gated, stateless ``POST /fhir-export`` and downloaded from the consultation
screen as ``application/fhir+json``. The bundle carries the trio the assessment
named plus every resource this codebase already holds facts for: **Patient**,
**Practitioner**, **Encounter**, **Condition**, **Observation**,
**AllergyIntolerance**, **MedicationStatement**, **DetectedIssue** and
**DocumentReference**. It is built from the same modules the rest of the pipeline
uses (``encounter_context``, ``screen_report_text``, ``detect_conditions``,
``review_medications``, ``build_soap_note``), so the export cannot disagree with
what the workspace shows.

Rules that keep the export honest:

- **Only curated codes are emitted.** The one terminological source in this
  codebase is ``agents/knowledge_graph_agent`` (SNOMED + UMLS for the nine
  symptom concepts), so reported symptoms carry those codings. History terms
  and laboratory values are text-first: a ``CodeableConcept`` with ``text`` and
  no ``coding``. Guessing a SNOMED/ICD-10 code for "hypertension" or a LOINC
  code for potassium from memory would silently mis-code a problem list — the
  plausible-but-wrong failure this project exists to avoid (ADR-016/017).
- **Decision support stays visible.** Symptoms are ``provisional`` Conditions
  noted as reported rather than diagnosed; history is ``unconfirmed``; the
  screening band is a ``survey`` Observation whose code says decision-support;
  the medication safety findings are ``preliminary`` ``DetectedIssue`` resources
  with severity and mitigation. A reviewer can tell what was observed from what
  was suggested without reading the code.
- **Gaps are reported, not filled.** ``missing_information`` names what could not
  be represented (no age, no allergy list, no laboratory text, text-only
  conditions) and ``caveats`` names what was derived (a birth year from a
  recorded age, accurate to about ±1 year). The UI shows both next to the
  download instead of quietly shipping a confident-looking bundle.
- **No invented units.** Quantities carry unit text only; UCUM codes are
  deliberately absent rather than guessed, and the reference range travels as
  ``referenceRange[].text`` exactly as the screener printed it.
- **The raw recording stays out.** The ``DocumentReference`` carries the
  deterministic consultation note (or the final report when one was generated),
  never the transcript — so the existing de-identification, retention and
  "note bodies are excluded from exports" rules are unchanged.
- **An export, not an integration.** The file is rendered on the clinician's own
  machine and downloaded by their browser; nothing is pushed to an EHR, no
  terminology server is contacted, no new dependency is added (stdlib only), and
  nothing is stored server-side. ``SECURITY.md``'s "new egress needs an ADR" rule
  is satisfied by this record, which is why the caveat text is part of the API
  response rather than the Bundle.

Rejected alternatives: a live EHR/FHIR write-back (needs a hospital system, its
API contract and a credentials story — the assessment already prices that as
infrastructure, not code); ``Application/fhir+json`` POST to a public validation
server for tests (network dependency in an offline-first project); authoring a
full terminology table for history and laboratory codes (a licensing and
correctness problem sold as a feature); putting the transcript in a
``DocumentReference`` attachment (egress of the raw encounter for no clinical
gain); emitting one ``Composition``-style document instead of a resource Bundle
(less useful to an importing system, and it would have to re-encode the
findings the agents already produce).

Consequence: 24 new cases in ``backend/test_fhir_export.py`` — referential
completeness of every ``Reference``, Patient demographics with the age-derived
birth year and its caveat, one Condition per canonical problem with history
text-only, SNOMED-coded provisional symptom Conditions, laboratory Observations
with units/interpretation/reference range, ``unknown`` gender for unrecognised
values, placeholders like "NKDA" never becoming an ``AllergyIntolerance``,
active ``MedicationStatement``s, ``DetectedIssue`` severity and mitigation for
allergy/renal/interaction findings, the DocumentReference round-trip, and that
the exported document does not embed the transcript — bringing the backend suite
to 118 tests. The frontend adds an "Export FHIR JSON" action and shows the
resource counts, gaps and caveats next to it; ``docs/API_SPEC.md`` and
``docs/DATA_FLOW.md`` describe the contract.

## ADR-020 · Deterministic HEART, GRACE and CHA₂DS₂-VASc instead of hand-derived urgency
**Status:** Accepted (2026-10-12)

Until now the urgency of an encounter was hand-derived in two unrelated places:
the medication layer escalated on "chest pain is present" plus the model's
screening band, and the diagnosis layer reported that band alone. Neither is an
instrument. A clinician cannot check a model probability against a published
cut-off, two layers can disagree about the same patient, and a band derived from
13 dataset features cannot express *why* an encounter is being called an
emergency.

Decision: three published scores are computed deterministically — HEART for
chest pain, GRACE (in-hospital, classic point score) for ACS risk, and
CHA₂DS₂-VASc for stroke risk in atrial fibrillation — in
``agents/risk_scores_agent.py``, with their inputs assembled once in
``backend/risk_score_context.py`` and consumed by both layers:

- the **medication layer** grades ``pathway.urgency`` from them (high HEART or
  GRACE → emergency, intermediate → urgent) and reports ``pathway.drivers``, so
  the urgency names the instrument that decided it;
- the **diagnosis layer** returns ``risk_scores`` beside the model band, in
  ``/diagnose``, in the medication review payload and on every live
  ``analysis`` frame;
- CHA₂DS₂-VASc grades the *reason* behind the anticoagulation option when atrial
  fibrillation is captured — it never orders anticoagulation, and a score below
  the conventional threshold says so on the option's review flags.

Rules that keep the scores honest:

- **An unknown input is never a zero.** A score with a missing component reports
  ``score: null``, ``complete: false``, the points it *could* compute
  (``known_points``) and the list of what to supply. A falsely low score is the
  worst possible output of a safety screen, so the scores refuse to produce one.
- **Scores escalate; they never soften the presentation.** Chest pain still
  triggers the ACS pathway regardless of a lower HEART band (ADR-018's rule),
  and the score's numbers are shown in the rationale so the reason the urgency
  exceeds the score is explicit rather than unexplained. Where the presentation
  rule does not fire, the score decides — which is how an intermediate GRACE in
  a dyspnoeic patient becomes *urgent* instead of routine.
- **Every derived reading is stated as a convention.** HEART's History item is
  derived from the captured features (two or more of radiation / exertional
  onset / sweating / nausea / dyspnoea = typical, one = atypical, none =
  non-specific) and returned with the features that drove it; the ECG item maps
  documented statements (ST deviation = 2, repolarisation change = 1, documented
  normal ECG = 0, nothing documented = missing); HEART's troponin item is the
  value over *that assay's* reference ceiling from ADR-005's table.
- **Units are converted, not assumed.** GRACE's creatinine point table is in
  mg/dL, so µmol/L is divided by 88.4 before binning; troponin in ng/L is
  converted to ng/mL, and a qualitative "troponin positive" is passed as an
  elevated marker while the HEART item stays missing (it needs a number).
- **Mortality is a nomogram, and says so.** GRACE published a nomogram, not an
  equation, so the in-hospital mortality is read from the printed table and any
  value between rows is flagged ``interpolated: true`` with both anchor rows —
  not presented as a quoted figure.
- **Vitals are captured, not invented.** Heart rate, blood pressure and Killip
  class are read from the clinical text ("BP 90/60, HR 110, Killip II") or
  supplied explicitly; absent vitals leave GRACE incomplete and name what to
  supply, rather than assuming Killip I.

Rejected alternatives: implementing GRACE 2.0's logistic model (its coefficients
cannot be checked offline against the original paper here, and the classic point
score is the published, reproducible one — the point tables are the artefact a
clinician recognises); computing the scores in the frontend (two implementations
of a safety-critical number would drift, exactly as ADR-018 rejected two context
assemblies); treating an absent input as normal; switching to CHA₂DS₂-VA (the
2024 ESC score that omits sex) — noted as a future option, but mixing its
thresholds with CHA₂DS₂-VASc's published tiers would be wrong.

Consequences: 29 new cases in ``backend/test_risk_scores.py`` — every point
table boundary, the published bands, the nomogram anchors (140 → 2.9%), the
µmol/L conversion, the incomplete-score contract, the CHA₂DS₂-VASc sex modifier
and tiers, the pathway consuming the scores (including that a lower band cannot
soften chest pain), the AF stroke-risk reason, and the live frame carrying the
same block the review used — bringing the backend suite to 159 tests. The
consultation card shows the scores with the block they produced and names the
driver; the medication workspace shows the full breakdown with each point's
input.

Known limits: GRACE needs vitals and a Killip class, which arrive only when they
are stated in the report text or read aloud, so it is often reported incomplete
by design; a bare "troponin 0.06" without the I/T specifier is not parsed (the
assay determines the ceiling, so guessing would change the points); and the
annual stroke-risk percentages are cohort- and source-dependent, so they are
labelled as published estimates rather than universal constants.

## ADR-021 · Add the ASCVD Pooled Cohort Equations as the fourth deterministic score
**Status:** Accepted (2026-10-14)

ADR-020 closed the calculator gap for the *acute* encounter and for atrial
fibrillation, and named the ASCVD 10-year risk equation as the one still missing
because it needs the pooled cohort coefficients. It is the primary-prevention
instrument: HEART and GRACE grade a presentation that already looks cardiac,
whereas the pooled cohort equations estimate the risk of a *first*
atherosclerotic event — the number a statin decision is actually thresholded on.

Decision: ``agents/risk_scores_agent.py`` gains ``ascvd_score``, over the four
published models (white men, white women, African American men, African American
women). Each is a thirteen-term linear predictor with the guideline's group
centering value and baseline survival: ``risk = 1 - S10^exp(sum(beta*x) - mean)``.
Inputs are assembled in the same ``backend/risk_score_context.py`` block as the
other three and travel in the same payloads — ``/diagnose``,
``/medication-review`` and every live ``analysis`` frame — and through the same
consultation card and medication-workspace breakdown.

Rules that keep it honest, and the conventions it adds:

- **A probability needs every input.** Age, sex, total cholesterol, HDL,
  systolic BP, hypertension-treatment, smoking and diabetes status must all be
  captured; otherwise ``score: null``, ``complete: false`` and the list of what
  to supply. An unstated smoking or diabetes status is *unknown*, not "no" — and
  because the condition vocabulary matches "smoker" inside *ex-smoker*, an
  explicit denial ("never smoked", "non-diabetic") is read first, so an ex-smoker
  scores as a non-smoker.
- **Race/ethnicity selects the model and is never guessed.** The guideline
  publishes one coefficient set per group, so the group is read from the record
  or the wording. When it is not captured, the *higher* of the two sex-matched
  equations is reported, the other is returned beside it in ``alternative``, and
  ``note`` names the choice. Defaulting to one group would quietly under-estimate
  half the patients; erring high errs towards treating. This is a convention of
  this implementation, not of the guideline.
- **The derived ranges are carried, not hidden.** The equations were derived over
  age 40-79, total cholesterol 130-320 mg/dL, HDL 20-100 mg/dL and systolic BP
  90-200 mmHg. Outside them the number is still computed, but ``in_range`` is
  false and ``out_of_range`` names the input, so a caller deciding on treatment
  can require ``in_range``.
- **Every term of the sum is returned.** ``components`` carries each term's
  coefficient, value and contribution — the SBP half that does not apply and any
  term the group's model does not use are omitted — plus ``linear_predictor``
  (sum, mean, baseline survival), so the arithmetic can be checked by hand the
  way a point score's components can.
- **Units are converted, not assumed.** Cholesterol and HDL in mmol/L are
  multiplied by 38.67, the rule ADR-020 already set for creatinine in umol/L.
- **It never escalates an encounter.** A ten-year probability is a chronic risk:
  it grades the reason behind the lipid-lowering option (a moderate-intensity
  statin at or above 7.5%, and a note saying why not below it), exactly as
  CHA2DS2-VASc grades the anticoagulation reason. ``pathway.drivers`` stays the
  acute instruments' business.

Rejected alternatives: implementing PREVENT (the 2023 AHA equations) instead —
noted as the successor, but the pooled cohort equations are what the published
worked example and a reference implementation can be checked against offline;
defaulting an unstated race to one group; reporting a risk outside the derived
ranges without a flag; and computing the probability in the frontend (two
implementations of a safety-critical number would drift, the ground ADR-018 and
ADR-020 already rejected).

Consequences: 13 new cases in ``backend/test_risk_scores.py`` — the guideline's
worked example for all four groups, the unrounded values against the reference
implementation (5.3786% white men, 6.0611% African American men), the
incomplete-score contract, the higher-group convention, the out-of-range flag,
the term-by-term sum, the mmol/L conversion, the treated/untreated BP branch, the
named gap in the encounter's ``missing`` list, the statin option the threshold
offers, the below-threshold note, and that an ungradable equation is named when a
laboratory panel did arrive — bringing the backend suite to 172 tests. A
``statin_primary_prevention`` entry in the curated drug table is what the
indication resolves to.

Known limits: these are the 2013 equations (ACC has since moved to PREVENT, and
the equations' risk magnitude is no longer endorsed for current decision-making);
the white-men example prints 5.4% here against the guideline's rounded 5.3%
because the reference coefficient table is itself rounded; and an encounter that
never captures a lipid panel reports ASCVD incomplete by design.

## ADR-022 · Read a lipid panel the way it is written (abbreviations and fraction labels)
**Status:** Accepted (2026-10-14)

A panel reaches the screening endpoint typed, pasted or read off a printout, so
the ward's short forms are what arrives — Chol, TG, HDL-C, LDL-C, non-HDL — and
the analyte names overlap: the word "cholesterol" sits inside "LDL cholesterol",
and "HDL" sits inside "non-HDL". Measured against the module before this change:
"Chol: 5.5 mmol/L" and "TGs 2.1 mmol/L" were not parsed at all; **"non-HDL
4.2 mmol/L" was reported as HDL 4.2 mmol/L, within reference** — the finding
inverted, because a high non-HDL came back as a healthy HDL; "LDL cholesterol
120 mg/dL" produced both LDL 120 and a *total cholesterol of 120*; and "VLDL
cholesterol 30 mg/dL" was reported as total cholesterol.

Decision: the abbreviations join the alias lists, and the overlapping names are
resolved by the label around the match, in ``backend/lab_report.py``:

- **Chol** is a total-cholesterol alias, with the word boundary that keeps it out
  of "cholesterol", "cholestasis" and "cholesteryl"; **TG/TGs** join
  triglycerides. HDL-C and LDL-C were already recognised and are now covered by
  tests.
- **Non-HDL is its own fraction** (``non_hdl``), not an alias of HDL and not
  folded into the total. Its threshold is defined relative to LDL-C — the
  international convention sets it **30 mg/dL (0.8 mmol/L) higher** — so its band
  is LDL's 130/190 mg/dL shifted to 160/220 (3.4/4.9 to 4.2/5.7 mmol/L), and it
  converts into the flattened lab map like the rest of the panel (x38.67).
- **A match is dropped when the words around it name a different fraction**
  (``_CONTEXT_EXCLUDES``, each pattern anchored to the end of the match):
  "non-HDL" and "non-LDL" are not HDL and LDL, "very low density lipoprotein" is
  not LDL, and a "cholesterol" preceded by a lipoprotein name belongs to that
  fraction rather than to the total.

Rejected alternatives: keeping "non-HDL" as an HDL alias (the inversion above);
accepting only the exact spelling "non-HDL-C" (reports write "non-HDL", "nonHDL"
and "non-HDL-C"); grading non-HDL against the total's ceiling (a high non-HDL
would read as within range) or against HDL's floor; folding a non-HDL figure into
total cholesterol when both appear on one line; and computing derived lipids
inside the parser (HDL from total minus non-HDL, or non-HDL from total minus HDL)
— a derived number is a different kind of claim from a printed one and belongs in
a named calculation, not in extraction. VLDL is left unreported: no fraction and
no band is defined for it here.

Consequences: the screening module grows from 17 analytes to 18 — which also
corrects the count API_SPEC had been carrying; ``/screen-report`` and the
``labs_used`` map can carry a ``non_hdl`` key; 5 new cases in
``backend/test_lab_report.py`` — every abbreviation attributed to its own
fraction *and to nothing else*, abbreviations not matched inside longer words, a
lipoprotein cholesterol not claimed as the total, non-HDL's own band including
its boundaries, and the panel's short forms converting into the flattened lab map
— bringing the backend suite to 198 tests. Four of the five fail against the
previous parser; the fifth (over-matching) passes before and after by design.

Known limits: "non-LDL" and "VLDL" values are dropped rather than attributed to a
fraction, since no band is defined for either; a non-HDL is not derived from a
printed total and HDL; and the lipid-lowering gate in the pharmacology agent
still keys on LDL alone, so a report stating only non-HDL does not raise that
indication — which this key now makes possible to fix.

## ADR-023 · Work out the lipid fraction a panel implies, and gate on non-HDL as well as LDL
**Status:** Accepted (2026-10-15)

ADR-022 gave non-HDL its own fraction and its own band, and stopped deliberately
at two boundaries: it would not derive a fraction inside the parser, and it left
the lipid-lowering gate reading LDL alone. Both were the right scope for that
change, and both leave the same hole — the fraction the lipid decision turns on is
not always the one the report prints. Measured against the module before this
change: "Total cholesterol 248 mg/dL, HDL 34 mg/dL." reported two values and no
non-HDL, so a non-HDL of 214 mg/dL, over its own 160 mg/dL band, was invisible;
and a panel written "non-HDL 4.2 mmol/L" reached the medication review as 162
mg/dL with no lipid-lowering option offered, because ``lab_tags()`` read LDL alone.

Decision: the derived fraction and the gate both change, in
``backend/lab_report.py`` and ``agents/pharmacology_agent.py``.

- **The identity is worked out where the values are read.**
  ``non-HDL = total cholesterol - HDL`` and, rearranged, ``HDL = total cholesterol
  - non-HDL``: a panel that prints two of the three fractions states the third, so
  the third is computed once at parse time and every consumer — the screening
  payload, the flattened lab map, the FHIR export — sees one number instead of
  three opinions about it.
- **A derived value is a value, and says it is derived.** It carries the
  fraction's own band and severity (the band is about the number, not about how it
  arrived), plus ``computed: true``, ``unit_label`` "mg/dL (computed)",
  ``derivation`` (the arithmetic, with the printed spelling beside it when the
  report wrote the operands in another unit), ``computed_from`` (the operands as
  they were subtracted) and ``summary.computed``. Its ``matched_text`` is the
  arithmetic, which is the whole of its provenance.
- **The derivation refuses what the panel does not support.** A fraction the
  report printed is never overruled; a derived value is never an operand of the
  next derivation; an operand whose printed unit could not be read
  (``unit_read: false``) is not subtracted, because that value was only *banded*
  as if it were in the primary unit; an operand whose unit has no defined
  conversion is skipped; and a total below its own constituent yields nothing
  rather than a negative fraction.
- **The result is stated in the fraction's primary unit** (mg/dL) after converting
  both operands into it, because a panel can print the pair in different units and
  a difference is only arithmetically true in one of them.
- **The gate reads the fraction's own threshold**: 190 mg/dL for non-HDL, which is
  LDL-C's 160 shifted by the 30 mg/dL (0.8 mmol/L) the international convention
  places between them — the same relationship ADR-022's band already uses. It
  travels as its own tag and indication (``non_hdl_high``), so an option's reason
  names the fraction that was high ("non-HDL 193 mg/dL") instead of attributing to
  the panel an LDL figure it never printed.

Rejected alternatives: deriving inside the flattened lab map or the gate (the
clinician would not see the number, and the screening and the gates could disagree
about one panel); a second ``derived`` list in the payload (every consumer would
have to union it, and the screen would need a second list to render); leaving the
gate on LDL alone (the hole above); keeping both a printed and a derived value for
the same fraction; estimating LDL from total, HDL and triglycerides (Friedewald) —
a third identity, but it assumes fasting and fails above 400 mg/dL triglycerides,
while the panel's own arithmetic is exact; holding non-HDL to LDL's 160 mg/dL (one
fraction's number applied to another); and reporting the derivation in prose only,
with no structured field a caller can act on.

Consequences: 7 new cases in ``backend/test_lab_report.py``, 3 in
``backend/test_pharmacology_agent.py`` and 1 in ``backend/test_fhir_export.py`` —
bringing the backend suite to 209 tests. One existing case changes count rather
than meaning: "HDL 1.3 mmol/L. Total cholesterol 5.5 mmol/L." now also yields
non-HDL 162.4 mg/dL, which is over its band, so it reports two abnormal values
instead of one — neither of them the HDL, which is what that case is about.
``/screen-report`` values gain ``computed`` / ``derivation`` / ``computed_from`` /
``unit_read`` and the summary gains ``computed``; the flattened ``labs_used`` map
can carry a derived fraction; the FHIR export marks a derived observation in its
note; the consultation screen shows a computed badge and the arithmetic where a
printed value shows the snippet it came from; and ``lab_tags()`` gains
``non_hdl_high``.

Known limits: the derived number inherits the printed pair's rounding, so a panel
printed in mmol/L gives a rougher non-HDL than one printed in mg/dL — which is why
the arithmetic travels with it instead of being hidden; nothing checks that the
printed total and HDL came from the same draw, so an internally consistent but
mismatched pair still subtracts; a value whose unit could not be read is still
banded against the primary band (ADR-016's convention) and is excluded only from
derivation; and the gate's thresholds are the AHA/ACC "high" boundaries, which
other guidelines place elsewhere.

## ADR-024 · Record the group the pooled cohort equation selects its model from
**Status:** Accepted (2026-10-15)

ADR-021 added the pooled cohort equations and decided what a missing group means
(report the higher of the two sex-matched models, with the other one beside it) —
a fallback, not a way to record the fact. The API accepted a group from the day it
landed, but nothing in the workspace collected one, so on the two screens that
score an encounter the record was normally empty: the equation reported the
fallback while the clinician believed the visit details had been recorded, and a
family-history phrase in the narrative could override the group the record did
state.

Decision: the group becomes a visit field, like age and sex, in
``backend/risk_score_context.py`` and the two forms that carry patient details.

- **The record decides; the wording only fills the gap.** ``_race`` matches the
  recorded value first and reads the narrative only when the record names no
  published group. A value the equations have no model for ("Asian", "other")
  deliberately does not map onto one of them — it leaves the wording to speak,
  which is the same state as an unrecorded group.
- **One list of the published groups**
  (``frontend/src/lib/patientGroups.ts``), shared by the consultation form and the
  medication form, because two lists would eventually offer a group the equation
  has no coefficients for. The options are the two the equations publish and
  nothing else; the hint says what leaving the field empty does.
- **Neither form guesses.** An unrecorded group is sent as nothing rather than as
  a default, so the review still reports the fallback and both numbers; the live
  per-line rebuild carries the recorded group with the rest of the visit header.
- **The field is per encounter and is not persisted.** It shapes the scores for the
  visit in hand; it is not written into the saved visit, the PDF or the FHIR
  bundle, because a demographic field in new persistence needs its own decision and
  a retention story (CLAUDE.md rule 7), and no screen reads it back yet.
- **It is explained where it is asked.** The field's hint and the Guidance page say
  why the question is there (the equation is defined per group) and what an empty
  value does.

Rejected alternatives: leaving the prose-only route (the record stays empty, and
the narrative outranks it); offering categories the equations publish no model for
(they would be recorded and unusable, or silently mapped onto a published group);
defaulting a recorded-but-unpublished value to one of the two; writing the group
into the saved visit and the PDF; making the field required (it would push
clinicians to record something they have not asked the patient).

Consequences: 3 new cases — the review scoring a recorded group (2 model
comparisons in ``backend/test_risk_scores.py``), the record-beats-wording rule, and
the live rebuild carrying the header's group — bringing the backend suite to 212
tests. ``npm run typecheck`` was found to be checking nothing while this work was
being verified (the root tsconfig has ``files: []`` and ``tsc --noEmit`` does not
follow ``references``); it now names both projects and fails on a deliberate type
error.

Known limits: the group is not written into the saved visit, so re-opening one
cannot re-score its equation with it; the published groups are narrower than the
population, and everyone outside them is scored on the fallback the score reports;
and this is the one field in the workspace that is asked about the person rather
than the illness — it exists because the instrument is defined per group, and it
is not used to stratify anything else.

## ADR-025 · One bottom dock as the app's only navigation
**Status:** Accepted (2026-10-18)

The workspace had two navigations for the same nine destinations: a 248px
sidebar at `lg` and up, and a bottom tab bar below it. They were written
separately, they drifted (the sidebar gained the leading primary item and a
three-group split the tab bar never had), and between them they disagreed about
what the app *is* — a desktop tool with a phone fallback. The consultation
screen is used at a desk and at a bedside, and the product is a single React
app either way. Meanwhile the sidebar's own costs were invisible: 248px of
horizontal room taken from every data-dense screen for a menu a clinician
touches twice a visit, and the reachable content width stuck at 1240px on a
1440px laptop.

Decision: one dock at the bottom of the viewport at every width, in
``frontend/src/components/app/app-shell.tsx``, carrying all nine destinations.
It is the app's only navigation.

- **All nine, always visible.** The dock renders the whole `NAV` list — no
  "more" sheet, no overflow menu, nothing behind a tap. Nine items fit a
  768px-wide row with a label each; below that the strip scrolls horizontally
  and the active item is centred with `scrollIntoView({ block: "nearest" })`, so
  the destination you are on is on screen at any width and a swipe reveals the
  rest.
- **Order follows the visit, not the menu.** Overview leads (it is the page
  that says "start a consultation"), then Consultation, then Medication review,
  then the records — History, Notes, Patients — and the system pages last. The
  three sidebar groups are gone: with a single row, a heading that costs a
  whole band of height buys nothing.
- **Labels shorten, names do not.** Each item carries a short printed label
  ("Consult", "Meds", "Guide") and `aria-label` with the full destination, so a
  screen reader and the E2E/recording scripts still see "Medication review"
  while the row stays legible at 390px.
- **The top bar absorbs the sidebar's second job.** Identity, sign-out, the
  guidance link and the source link were the sidebar's footer; they are now one
  account menu in the header, available at every width, and the engine-status
  pill sits beside it. The fixed dock keeps `pb-[env(safe-area-inset-bottom)]`
  and the site footer carries extra bottom padding so its links never end up
  under the dock (measured clearance at the foot of a 1366×768 window: 33px).
- **Content uses the width it just won.** `main` grows to 1320px at `xl` and
  1440px at `2xl` instead of stopping at 1240px with 248px of permanent menu
  beside it.

Rejected alternatives: keeping the sidebar at `lg` and the tab bar below it
(two structures, two behaviours, one of them always wrong for the person using
it); five tabs plus a "More" sheet (the destinations a clinician reaches for are
not the same five for every clinician, and hiding four of nine makes the app
look smaller than it is); icons-only tabs (nine unlabelled glyphs — a stethoscope
and a pill are guessable, "Guidance" and "Agents" are not); a floating centred
pill dock that does not span the width (looks like a widget, and at nine items
it either overflows its own container or shrinks below a 44px target); a
hamburger drawer (the same menu, now behind a tap, on screens with room to show
it); and reordering the list to put the consultation first (the overview is
where a session starts, and it was given the action it lacked instead).

Consequences: the shell renders one navigation component instead of two; the
sidebar, its group headings and its footer are deleted; `AppShell` no longer
switches layout at `lg`; the dock prints labels at every width, so the items are
~136px wide on a desktop and 68px in the scrolling strip on a phone; the
account menu is a new interactive surface in the header with click-outside and
Escape handling; and the print stylesheet already hides `nav`, so a printed
report has no dock in it.

Known limits: on a phone the dock shows roughly five and a half of its nine
items and the rest are reached by swiping, which is a smaller glance than nine
visible tabs; the short labels are abbreviations a first-time user has to
connect to the page titles; the dock is fixed, so every page scrolls behind it
and any future full-bleed footer has to budget for it; and the active item is
matched on path prefix, so a future route nested under an existing prefix
(`/patients/import`) will highlight its parent rather than itself unless it is
added to the list.

## ADR-026 · One microphone stream, taken processed, and metered in dBFS
**Status:** Accepted (2026-10-18)

The capture path asked for the microphone twice. `preflightMic()` opened
`getUserMedia({ audio: true })` purely to see whether permission would be
granted, then closed the tracks; `startMeter()` opened a second stream for the
analyser. Two problems followed from that, and only one of them was a leak.
The browser chooses a device per request, so the stream the meter measured and
the stream the recogniser captured were not guaranteed to be the same one — a
clinician whose headset is not the system default could watch a bar move while
the transcript stayed empty, and the UI would insist it was hearing them. And
`{ audio: true }` asks for the raw device feed: no echo cancellation (the
recogniser hears the app's own audio), no noise suppression (a desk fan and a
keyboard are part of the input), no automatic gain (someone speaking from the
far side of a bed arrives below the recogniser's floor). Finally the meter was
`rms * 3.2` clamped to 1 — a scale with no units, which could not distinguish
"the room is quiet" from "the microphone is muted" from "you are shouting",
and reported all three as a short bar.

Decision: one stream, requested processed, measured in dBFS, in
``frontend/src/lib/audioInput.ts`` and ``frontend/src/lib/useConsultationCapture.ts``.

- **One `getUserMedia` call per listening session.** It answers the permission
  question, feeds the analyser and proves the device works, in that order, and
  its tracks are stopped when listening stops. The recogniser still opens its
  own capture — the Web Speech API accepts no stream — but there is no longer a
  second app-visible request to disagree with it.
- **Ask for the processed feed.** `echoCancellation`, `noiseSuppression`,
  `autoGainControl`, `channelCount: 1`. A device that cannot honour the set
  raises `OverconstrainedError` (a virtual cable, a capture card), and that is
  retried unconstrained rather than failing the consultation.
- **The meter reads a frame, not an average.** `readMicFrame()` returns RMS,
  peak, dBFS and a classification of one analyser frame; the UI draws the
  smoothed level as a fill and the instantaneous peak as a marker, red near
  full scale, so a clipped plosive is visible even when the average stays low.
  The smoothed level still attacks fast and decays slowly — a word has to show
  immediately, and a bar that flickers at the frame rate is unreadable.
- **The scale is perceptual and the thresholds are named.** The floor is −55
  dBFS, speech starts at −38, clipping at −6, and the mapping to 0–1 is pushed
  through a square root so quiet speech moves the bar instead of pinning it to
  zero — a meter that only reacts to shouting tells the clinician nothing.
- **A quiet room is not an error.** The hint ("no speech reaching the
  microphone yet") appears only after `QUIET_HINT_MS` (8s) with no
  speech-level frame. Reported on the first low frame it would be on screen for
  the whole consultation and mean nothing, because the pauses between sentences
  are the low frames. Clipping is reported immediately — that frame is being
  corrupted now.
- **Each failure names its fix.** `describeMicError` separates permission
  (address-bar instruction), no device, device busy in another app, and the
  rest, because the three have three different remedies and "microphone error"
  serves none of them.

Rejected alternatives: keeping the preflight stream (the reason for the split
was to avoid starting a recogniser that fails on permission, which the single
stream answers just as well by returning before the recogniser is constructed);
a voice-activity detector driving auto-stop (silence detection that ends a
session on a thinking pause is worse than a session left running); recording
with `MediaRecorder` and transcribing after the visit (loses the per-line
concept extraction the consultation screen is built around, and needs a
transcription path the Web Speech API was already providing); a `deviceId`
picker (a device-selection UI for a problem most machines do not have; the
system default is right far more often than a list is); printing the dBFS
number in the UI (a number needs a reference scale to mean anything to a
clinician, and the hint already says what to do); a fixed gain multiplier to
"make it louder" (it amplifies the room as much as the voice, and the device's
automatic gain control does it better); and showing the hint on the first quiet
frame (see above).

Consequences: `frontend/src/lib/audioInput.ts` holds the constraints, the level
arithmetic, the frame classifier, the hint rules and the error mapping, with 17
vitest cases in `audioInput.test.ts` covering the pure half; the analyser now
reads `fftSize` samples rather than `frequencyBinCount`; the consultation meter
has a second, peak-driven element and an `aria-valuetext` that includes it; the
hook exposes `micPeak` and `micHint`; and a denied permission now stops the
session before a recogniser is constructed, instead of after.

Known limits: the Web Speech API opens its own microphone capture, so the
constraints and the meter describe *a* working input device and not provably
the one the recogniser chose — the meter can no longer point at a different
device than the app requested, but it cannot observe the recogniser's;
`echoCancellation` and friends are requests, and a device is free to ignore
them; the dBFS thresholds are conventional rather than calibrated per device,
so an unusually hot or quiet microphone moves where "quiet" begins; there is no
input-device picker, so a machine whose default input is the wrong microphone
still needs the OS setting to be changed; the quiet hint is wall-clock based,
so a session started and left idle for eight seconds before the first sentence
shows it while everything is in fact fine; and nothing tests the browser half
of this, because jsdom has neither `AudioContext` nor `getUserMedia` — the
constraints and thresholds are covered by unit tests, the wiring only by hand.

## ADR-027 · The UI audit signs in, and covers the screens a laptop really has
**Status:** Accepted (2026-10-18)

The audit reported "✓ Contrast: no WCAG AA violations" for months while
checking nothing. Every route in `ROUTES` is behind `RequireAuth`, the sweep
never signed in, and an unauthenticated visit to `/consultation` renders the
sign-in page — so eight routes were the same form, measured eight times. The
layout pass had the same hole, which is why it never saw the anatomy figures,
the consultation grid or the medication cards. Two further blind spots:
`vite preview` (the default way the sweep starts the app) had no `/api` proxy,
so even a sweep that tried to sign in could not have reached the backend; and
the viewport ladder stopped at 1440×900, so nothing checked the two panels most
laptops actually ship (1366×768 and 1536×864), where the shell has the least
horizontal room to give.

Decision: the sweep authenticates, and the viewport ladder is the real one.

- **Sign in first, in every pass.** `ensureAuditAccount()` logs in as
  `demo@cardio.local` (or registers it), `signIn()` fills the form and waits for
  the URL to leave `/login`, and both the contrast and layout pages do it before
  walking the routes. Overridable with `PULSEIQ_AUDIT_EMAIL` /
  `PULSEIQ_AUDIT_PASSWORD`.
- **A missing backend is reported, not hidden.** If the account cannot be
  reached the run prints "auditing public pages only" and says `(signed out)` in
  the summary. A sweep that checks the sign-in form is still a useful check —
  what was wrong was that nothing said so.
- **The ladder is 9 widths: 375, 768, 1024, 1280, 1366, 1440, 1536, 1920, 2560**
  for layout, and 390 / 1366 / 1440 for the (slower) contrast pass. 1366×768 is
  the most common laptop panel in circulation and is now in both.
- **The clipped-text rule means what it says.** SVG `<text>` is skipped: it is
  laid out in the drawing's own coordinate system, where `scrollWidth` and
  `clientWidth` do not describe whether a label overflows, so the body map
  reported every label at every width. Elements whose computed `text-overflow`
  is `ellipsis` are skipped too — an ellipsis is the layout telling the reader
  the text continues, and the check exists for text cut off with no indication.

Rejected alternatives: enabling a preview proxy in the audit script instead of
the vite config (the dev server already proxied, so the difference was a config
bug, not an audit setting); generating a token by calling `/api/auth/login`
directly and injecting it into `localStorage` (faster, but it stops exercising
the sign-in form the user actually uses, and the form is a route the sweep
covers); keeping the 1440-only ladder and trusting CSS breakpoints (the failures
that matter are width-dependent, and 1366 is where a nine-item dock and a
data-dense grid meet); and treating SVG text as a real finding (it would have to
be suppressed per figure instead, with the same net effect and a permanent
noise floor).

Consequences: 2072 text elements are sampled across 3 viewports × 9 routes on the
first signed-in run — more than the 1847 the unsigned sweep managed over the same
routes, and a number that only ever grows as the demo account's History fills (the
count reached 2591 by the third run of the release); the first signed-in run found 12 AA failures in
light mode — the selected tab at 2.8:1 and two session-list readings just under
4.5:1 — all fixed in `light-theme.css` and `SecurityPage.tsx`; the run needs a
backend behind the base URL to be useful, and states when it does not have one;
and `preview.proxy` in `vite.config.ts` now mirrors the dev server so the built
bundle behaves like the audited app.

Known limits: the audit still runs unauthenticated for `/login`, `/privacy` and
`/terms`, which have their own layouts; the demo account accumulates whatever
the sweep and the recording leave behind, so a populated History makes the
sampled element count drift between runs; the contrast thresholds are static
(4.5:1 / 3:1) with no per-component exceptions, so a future design that
intentionally uses low-contrast text has to argue with the check rather than
configure past it; the layout pass measures a scroll position at the top of each
route, so anything that renders only below the fold is only checked for
overflow, not for contrast; and 2560px is audited in CSS pixels, not on a real
4K panel with OS scaling.

## ADR-028 · CI runs the audit against a real backend, and fails when a page redirects
**Status:** Accepted (2026-10-18)

ADR-027 made the sweep sign in. The job that runs it did not. `ui-audit` in
`.github/workflows/tests.yml` installed Node and nothing else: no Python, no API
on the port `preview.proxy` forwards to. `ensureAuditAccount()` therefore could
not reach `/api/auth/login`, the run printed "auditing public pages only", and
the job exited 0. The gate added to close the signed-out blind spot had the same
blind spot — green because the backend was missing, not because the workspace
was clean.

Decision: the audit job provisions the app it audits, and the sweep fails when a
page does not render itself.

- **The job installs and starts the API.** `setup-python@v6` + `pip install -r
  requirements.txt`, then `uvicorn` on `127.0.0.1:8000` — the target
  `preview.proxy` already forwards `/api` to — with its output in
  `backend-audit.log`.
- **Readiness is `/health`, not an open port.** `uvicorn` binds before the
  pipeline is warm, so the step polls `/health` for up to 60s and fails with the
  server log (`tail -50`) when it never answers. The audit step re-checks
  `/health` before building, because a backend that died between the steps is a
  different failure from a layout one.
- **`--require-sign-in` is what CI passes.** Without the flag an unreachable
  backend is a documented fallback for laptops; with it, that state is non-zero.
  A session dropped mid-sweep fails too — the sweep checks the URL it is on
  after signing in, at every viewport, in both passes.
- **Every page load is compared with the route requested.** The mismatch is
  recorded per viewport and pass, printed as `✗ Landing: … → /login`, and sets
  the failure flag. Recording alone was not enough: the run could still report
  "✓ Contrast: no WCAG AA violations" for nine pages it never rendered.
- **The artifact explains the failure.** `ui-audit-report.json` gained
  `signedIn`, `requireSignIn`, and `redirects`; the backend log is uploaded
  beside it under the same artifact name.
- **The job is bounded** at `timeout-minutes: 25`. It now installs a Python
  stack, builds the bundle, starts a server and walks 108 page loads; a wedged
  sweep should not burn the six-hour default.

Rejected alternatives: leaving CI on the signed-out fallback (that is the
failure this ADR exists to remove, and the fallback prints a notice nobody
reads in a green build); having `ui-audit.cjs` start the backend itself (it
hides the dependency from the job graph, and puts server lifecycle management
inside a browser sweep that already owns a preview server); minting a token by
POSTing to `/api/auth/login` and seeding `localStorage` (skips the sign-in form
the sweep covers, and adds a second place that knows the audit credentials);
stubbing `/api` (most audited screens are data-driven, so a stub would audit a
fiction and the contrast findings would describe markup no user sees); sharing
build or dependency caches across jobs (no filesystem between them, and a cache
that stale-hides a dependency bug is worse than the minutes it saves).

Consequences: the job now pays for the runtime requirements (pandas, scikit-learn
and shap) on every push; CI starts from an empty database, so the sweep registers
`demo@cardio.local` through the public `/auth/register` endpoint on each run —
which also means the green path exercises registration, not just login; a red
audit can be diagnosed from the artifacts alone, since the report and the server
log travel together; the local default path is unchanged, so a developer without
a backend still gets the public-pages sweep and is told so; and the count of
audited routes is now the count of *rendered* routes, so the summary's element
total stopped being inflated by eight copies of the sign-in page.

Known limits: CI audits layout and contrast, not clinical output — the backend
runs provider-agnostic, and anything that would call Ollama falls back to the
rule-based path (what the pages *render* from that is real, what they *infer* is
not being checked); the 25-minute ceiling is a bound chosen before the first
green CI run and should be revisited against a real duration; the sweep still
needs a Chromium binary, which the runner provides and a developer must point
`EDGE_PATH` at; and none of this touches the microphone, which no CI job
exercises (ADR-026).

## ADR-029 · Audit the palettes and the states a route does not show on first paint
**Status:** Accepted (2026-10-24)

The audit measured one palette and one paint per route. Both were half the app.
Light mode is not a tint of dark mode here — `light-theme.css` re-specifies every
surface, and the contrast failures this repo has actually shipped were light-mode
ones (a dark navy panel under dark-violet text on the login page). The account
menu, the "Full consult" tab and the "Consultations" list are screens no first
paint reveals, so nothing had ever measured them at all.

Decision: contrast runs in both themes, a state pass opens the screens a route
hides behind an interaction, and a signed-in route must carry the workspace shell.

- **The stored preference is the path, and the check proves it.** `primeTheme()`
  writes `pulseiq.theme` before the document boots, so the same boot snippet a
  returning clinician relies on paints the page. The *system* preference is
  emulated as the other theme, which leaves the stored value as the only way to
  land on the audited palette. This mattered immediately: the first version
  emulated the same preference it stored, so deleting the write changed nothing
  and the check still reported 90 loads on the requested theme. With the
  preference removed the sweep now fails all 90 ("asked for dark").
- **States are declared, opened and proved.** Each entry names the route, the
  gesture and a witness (the menu role; the tab in `selected` state). A state
  that never arrives is recorded as `stateIssues` and fails the sweep, because
  auditing the page behind a panel that did not open is the same blind spot as
  auditing `/login` as the workspace. Entrance animations are frozen first, so
  the opened panel is measured at its final values.
- **The shell is part of the page.** While signed in, every route must render the
  dock with nine destinations, its current item *by accessible name*, and the
  account menu. This is what caught the dock marking "Overview" as current on
  `/privacy`, `/terms` and `/thank-you` while `NavLink` dropped the matching
  `aria-current` — the dot and the accessible name disagreed.
- **Three routes joined the table**: `/thank-you` (where a save lands) and the two
  legal pages. They are exactly the routes that are not dock destinations, so the
  shell check requires the dock but no current item there.
- **Layout stays one palette.** A width bug is not a colour, and doubling the
  9-width ladder would double the slowest pass for no new information. States get
  1440 and 390: the laptop and the phone, where a menu can run off-screen and the
  dock scrolls.

Rejected alternatives: clicking the theme toggle mid-sweep (it is a state of its
own, it moves between pages, and it mutates the preference the next load reads);
screenshot baseline diffing (no baselines, and font/AA noise buries a real
regression); routing each state to a URL (none of these states is routable — that
would be a product change made for the test); requiring an active dock item
everywhere (the app correctly has none on pages outside the dock). The sweep
found two real defects on its first run: 45 loads with no current page and three
22 px delete buttons in the consultations tab.

Consequences: contrast page loads double (3 viewports × 12 routes × 2 themes),
the summary reports the split per theme, and the report separates `themeIssues`,
`shellIssues` and `stateIssues` so a failure names its own cause. Verified
locally at 8 327–10 853 sampled text elements across runs (the count follows the
data rendered), 0 contrast violations, 0 layout issues, 12/12 states reached,
90/90 loads on the requested palette; with the stored preference removed, and
with one state's tab renamed, the sweep exits 1 and names the failure.

Known limits: two widths per state, no hover/focus/drag states, no data-bearing
dialog (the app has none today), and the state pass is skipped when the sweep
runs signed out — the workspace is not reachable, and saying "skipped" is more
honest than auditing the sign-in form under three state names.

## ADR-030 · The end-to-end journey runs in CI, and one gate requires every check
**Status:** Accepted (2026-10-24)

Four gates existed on paper. Three ran on every push. The journey — sign in,
capture a line, save, get a PDF, land on the thank-you page, find the visit in
history — was a script someone ran by hand, so the app's main promise was the one
thing a push could not break loudly.

Decision: the journey runs in CI against a built bundle and a live API, and a
single `gate` job requires all four checks.

- **Its own job, its own servers.** The audit and the journey both need an API,
  but they fail for different reasons and at different speeds. One job means one
  timeout, one log and one red X for two unrelated failure classes; separate jobs
  keep the diagnosis and let the faster check report while the slower one runs.
- **`vite preview`, not `vite dev`.** The job builds the bundle and serves it on
  4173, then runs the journey with `--base-url http://127.0.0.1:4173`. A save path
  that only works under the dev transform is not the app. `--base-url` now
  refuses to start a server of its own, so the URL in the log is the app tested.
- **The browser is named, not assumed.** `playwright-core` drives a browser that
  already exists. The job checks `google-chrome` and prints its version before
  the journey, so an image change is a clear "no browser" failure rather than a
  thirty-second locator timeout inside a step.
- **The gate fails rather than skips.** `needs:` plus `if: always()` means a red
  backend makes `gate` red, not absent, and branch protection only has to require
  one check that cannot be forgotten.

Rejected alternatives: folding the journey into `ui-audit` (see above: two time
budgets, two artifacts, two causes); letting Playwright download its own Chromium
(another download on every push for a browser the image already has); running the
journey through `npm run e2e` with no arguments (it starts a dev server and tests
that instead); a composite action shared with the audit (two jobs' setup is
easier to read inline than one indirection used twice).

Consequences: CI grows a job that installs the Python runtime, builds the bundle
and starts two servers; the journey registers `e2e-verify@cardio.local` on the
fresh database and stores one visit per run; and a push that breaks the save path
now fails before merge. Locally, `node scripts/e2e-save-visit.cjs --base-url
http://127.0.0.1:4173` against a preview server reproduced the CI path exactly:
8 steps, exit 0; against a dead port it stopped in the Servers step and named the
URL.

Known limits: no microphone and no model server in CI (the journey types the
transcript line rather than speaking it, and the backend answers from the
rule-based path); the PDF is asserted by the download event, not by parsing the
file; and the job's wall-clock duration is a local measurement until the first CI
run reports its own.

## ADR-031 · Every drug option and interaction rule names a source, and indications are compound
**Status:** Accepted (2026-10-24)

The medication module had eighteen options and nineteen rules. Each drug named a
guideline in prose; no rule named anything. A clinician reading "P2Y12 inhibitor
plus anticoagulant markedly increases bleeding" had no way to check whether that
was a guideline statement, a label statement or something the author believed.
The catalogue was also too small for the app's own premise: a review that cannot
offer a non-statin lipid agent, a pregnancy antihypertensive or an ARNI is not a
second opinion on the plan, it is a partial one.

Decision: the tables are sourced through a registry, and the catalogue grows
past its original size without loosening what a rule means.

- **`SOURCES` is a registry, not prose.** Every drug and every rule names at
  least one id, and each id resolves to a title and a publisher URL. A rule
  that rests on a guideline says so; one that rests on a CYP/P-gp or dose-limit
  statement cites the prescribing information (`label`). An entry resting on two
  sources names both, because "beta-blockade after ACS and in HFrEF" is two
  statements.
- **The invariant is a test, not a style note.** `test_every_drug_and_rule_names_
  a_source_that_resolves` fails on a missing or dangling id; three siblings check
  unique keys/names/pairs, that every rule target is a drug, class or alias (a
  rule aimed at a key nothing produces can never fire), that every option can be
  recognised as a current medication, and that every option states its
  indications, allergens, monitoring, dose and evidence.
- **Compound indications where the evidence needs two facts.** An option is
  offered when *any* indication matches, so listing `diabetes` and `albuminuria`
  separately offered finerenone to every diabetic, and `pregnancy` +
  `hypertension` offered labetalol to every pregnant patient. The six cases that
  need two facts together now get a compound name built where the facts meet:
  `diabetic_kidney_disease`, `pregnancy_hypertension`,
  `diabetes_with_ascvd`, `residual_hypertriglyceridaemia`.
- **One prescription, one "already documented" line — by key, not class.** The
  class-based check reported a patient on amiodarone as already being on
  dronedarone, and on metoprolol as already being on labetalol; the duplicate was
  then hidden from the list, taking its interactions with it. Matching is now by
  the drug key the alias table already resolves to.
- **Aliases belong to one drug.** Ticagrelor and diltiazem/verapamil left
  clopidogrel's and amlodipine's alias lists when they got their own entries, so
  one prescription is no longer reported as two agents.
- **New thresholds are pinned at their boundary** (149/150, 499/500, 29/30,
  189/190) the way the score tables are pinned to their pages: a behavioural test
  reads the same table the code does, so a digit typed one row high would pass
  every case that does not name the boundary.

The catalogue is now 36 options and 53 rules, twice its original size, and the
sources are 12 documents. Every addition in that growth was checked against a
directional test: the fact in, the offer or block out.

Rejected alternatives: keeping prose evidence and adding URLs only to guidelines
(a rule still could not be checked); a URL per rule (most rules share a source,
and repeating the URL invites drift); generating the catalogue from an external
drug database at runtime (no network in this app, licensing, and a database's
interaction list is not a clinical recommendation); OR-ing tags and accepting the
over-offer (finerenone for every diabetic is a false statement about the evidence,
not a broad reading of it); pinning every drug's text to a page number (the
guidelines are revised; the citation and the id are what the test can hold).

Known limits: this is a curated catalogue, not a formulary — doses are notes for
a clinician, never adjusted automatically; the sources are document-level for
rules, so a reviewer follows the guideline rather than a page; the interaction
table covers what the catalogue can offer plus common current medications, not
every drug a patient may bring; and no external interaction database is consulted,
which is the same reason the app works offline.

---

## ADR-032 · One destination list, presented as a phone bar and a desktop rail

**Context.** The workspace's navigation was a single bottom dock holding all
nine destinations in one horizontally scrolling strip. It survived the earlier
app-shell work, but on a 390px phone it gave each item about 43px, pushed three
destinations off-screen behind a scroll gesture most people never try, and left
a desktop with no navigation furniture beyond the same bar floating under the
content. The user's brief — an app-like layout that works on phones, tablets,
laptops and desktops — could not be met by one presentation at every width.

**Decision.** There is one list (`frontend/src/lib/navigation.ts`), one active
rule and three presentations:

- below `lg` (1024px), a bottom bar of **five** destinations plus **More**, which
  opens the remaining four in a native `<dialog>` bottom sheet;
- from `lg`, a labelled sticky rail with all nine, a "New consultation" action
  and engine state at its foot;
- from `xl`, the overview adds an aside column.

The rail is sticky and in normal flow, not fixed, so content cannot be laid out
under it. The phone bar is fixed, adds `env(safe-area-inset-bottom)`, and the
document gets `scroll-padding` so focused controls and anchors do not land
behind either.

**Why five, and why a rail.** Material's navigation bar is specified for three
to five equally important destinations in compact windows; Apple's tab-bar
guidance warns against making More the default hiding place. The five chosen are
the destinations a session touches — overview, consult, medications, history,
patients. Material puts rail and drawer layouts above ~600–840dp; 1024px is
where the labelled rail fits comfortably beside a full content column, and it is
also where a laptop user expects application navigation.

**Rejected.** Nine items in one row (the original dock); a hamburger drawer at
every width (an extra tap for the most-used screen, and a modal for navigation);
a rail on tablets in portrait (768px leaves too little for the clinical column);
fixed sidebar (content can hide beneath it at intermediate widths); two separate
navigation lists for the two presentations (they drift the first time a route is
added to one).

**Consequences.** Every new destination must be added to `NAV` and, if it is one
of the first five, displaces another into the shelf; the audit counts visible
destinations at both presentations, and the E2E journey asserts nine at 1440, five
plus More at 390, and that the sheet actually navigates. The rail's brand link is
inside the `<nav>` but outside the list, which is what the state-counting checks
had to learn.

**Verification.** `scripts/ui-audit.cjs` shell pass (visible-count by width),
22 state audits including the More sheet, E2E "Adaptive navigation" step,
`navigation.test.ts` for the list and active rule. Documented in
[DESIGN.md](DESIGN.md).

---

## ADR-033 · Installable app with an offline shell, and clinical data never cached

**Context.** The app shipped icons for a home screen and a `viewport-fit=cover`
meta tag, but no manifest and no service worker — so it could only ever be a tab,
and a dropped connection meant a blank page. Chrome's install criteria need a
manifest with a name, `start_url`, 192 and 512 icons and a standalone-ish
`display`; iOS uses the manifest for standalone launch and the `apple-*` tags for
icon and status bar.

**Decision.** Ship `manifest.webmanifest` (`display: standalone`,
`start_url: /`, dark canvas colours, the existing 192/512 icons — verified at
their real pixel dimensions) and a service worker that:

- precaches `/index.html`, the manifest, the icons, **and the hashed `/assets/`
  files parsed out of the built HTML**;
- serves navigations network-first with the cached shell as the fallback, and
  hashed assets cache-first;
- **never intercepts `/api` or `/ws`**, or any non-GET request;
- registers only in production builds, after `load`, and never blocks the app if
  registration fails.

`theme-color` follows the stored palette (rewritten by `applyTheme` and by the
boot snippet), so an installed app's status bar matches the page.

**Why parse the HTML for assets.** A static precache list cannot name files whose
names change every build. Caching only `index.html` produced an offline page that
loaded its HTML and then failed its scripts — a blank screen that looks exactly
like "the worker did not work" from the outside. Reading the built HTML closes
that without a build-time manifest dependency.

**Why `ignoreVary`.** Vite's preview server answers with `Vary: Origin`.
Install-time `cache.addAll` sends no Origin; a module-script request does. A
strict `cache.match` therefore missed the asset that had just been stored, and
the offline shell was blank even with everything cached. `ignoreVary` is safe
here because every stored URL is same-origin and content-hashed.

**Rejected.** No service worker (tab-only, and no offline story); caching `/api`
responses for speed (patient data on disk, and a stale consultation shown as
current); a maskable 512 icon reusing the existing artwork (the artwork has no
safe zone, so a maskable declaration would be a lie that crops badly); an
install modal (an instruction to install is not worth a blocked screen); runtime
`import()` of the worker (workers are not modules by default and must work before
the bundle).

**Consequences.** A new build needs no worker version bump unless the shell list
changes; `activate` deletes every cache that is not the current version. The
audit's PWA pass loads the built bundle, validates the manifest and icons, waits
for an active worker, then turns the network off and requires `/history` to
render — which is how both bugs above were found.

**Verification.** `ui-audit.cjs` PWA pass; `serviceWorker.test.ts` (6 tests
against fake caches, including "no `/api`, `/ws` or POST is intercepted" and the
`ignoreVary` contract); `theme.test.ts` for the chrome colour.

---

## ADR-034 · A command palette with tiered ranking, built on a native dialog

**Context.** Nine destinations fit the rail, but reaching the seventh still
means finding it visually and moving the pointer to it, and the people who use
this app most are typing a note when they want to change screen. A jump-to
control is the conventional answer on a desktop app.

**Decision.** Ctrl/⌘ K (and a visible "Jump to…" button) opens a palette that
filters the same `NAV` list. Ranking lives in `lib/commands.ts` as a pure
function with explicit tiers — exact label, label prefix, word prefix, keyword
prefix, label substring, keyword substring — with every query token required to
match somewhere and ties resolved by navigation order. Destinations carry the
words a clinician uses for them: "drugs" finds the medication review, "records"
finds history, "privacy" finds security.

The overlay is a native `<dialog>` opened with `showModal()`, like the More
sheet: focus containment, Escape, inert background and focus return are the
browser's. The key listener is on the window, so the shortcut works while focus
is inside a form field. The palette only navigates; it does not mutate data,
which keeps the keyboard path free of irreversible actions.

**Rejected.** A dependency (cmdk and friends) for a listbox over nine items; a
single fuzzy score (it produces a ranking nobody can predict or test); sorting by
list order alone ("med" would find the right screen by luck and "drugs" not at
all); a modal built by hand (a focus trap that closes on the wrong Tab is the
usual result); palette actions that save or delete (a keyboard slip should not
file a visit).

**Consequences.** Adding a destination to `NAV` adds it to the palette, but its
keywords are a deliberate edit: the generic words that make search feel clever
are also the ones that make unrelated screens compete. The audit opens the
palette as a state with a query typed, in both palettes and both widths; the
journey types "med" and presses Enter against the built bundle.

**Verification.** `commands.test.ts` (6 cases, each a phrase a clinician would
type), `ui-audit.cjs` state `command-palette`, E2E step in "Adaptive
navigation".

## ADR-035 · De-duplicate before splitting, and report the number that survives
**Status:** Accepted (2026-10-28) · supersedes the metrics in ADR-001

The model card advertised ROC-AUC 1.000 and recall 1.000 on "1,025 rows".
The arithmetic was right and the evidence was worthless: `heart.csv` contains
1,025 rows but only 302 distinct feature vectors — 723 rows are exact copies of
another row. `train_model.py` split before de-duplicating, so identical profiles
landed in both training and holdout, and a 300-tree forest that had already seen
the test rows reported a perfect score. A reviewer reads 1.000 as a bug, not a
result, and they are right to.

**Decision.** `load_dataset()` returns the file's distinct rows and everything
downstream splits only those: 302 vectors, 80/20 stratified, `random_state=42`
(241 train / 61 test). Training asserts that the two sides share no feature
vector before any metric is computed, and the metadata records the rule next to
the numbers (`split`, `dataset_rows`, `dataset_unique_rows`,
`n_train`/`n_test`, `metrics_note`).

**Honest metrics.** Holdout accuracy 0.836, precision 0.800, recall 0.857, F1
0.828, ROC-AUC 0.884; 10-fold CV 0.838 ± 0.073 accuracy and 0.909 ± 0.024
ROC-AUC. Lower, and defensible: on distinct rows this is a 13-feature model
over 302 patients, not a perfect classifier.

**Rejected.** Keeping the perfect numbers and adding a disclaimer (a caveat
beside a 1.000 score still reads as a 1.000 score); reporting only cross-
validation on the full duplicate-laden file (the same profiles are in every
fold); quietly deleting the old claim (the correction is more credible than a
clean card).

**Consequences.** The dataset is now openly described as 302 unique patients,
which is the real sample size and bounds how much any downstream claim can
rest on it. `test_train_model.py` fails if the loader stops de-duplicating, if
the split leaks, if the metadata stops stating the rule, or if the file's
duplicates disappear (which would mean the fixture, not the fix, changed). It
also reproduces the leak on the raw file, so the guard is shown to detect the
bug it exists for. Retraining is still `python backend/train_model.py`.
