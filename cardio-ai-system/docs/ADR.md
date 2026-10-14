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
