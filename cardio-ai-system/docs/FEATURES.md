# PulseIQ — feature inventory and what comes next

What the workspace does now, what it could do next, and what it should not do.
Everything proposed here is buildable with free and open tools and needs no paid
service, no account and no cloud dependency — the same constraint the rest of the
app runs under.

---

## 1. What exists today

### The session
- **Consultation capture** — typed or dictated, nine languages, live concept
  chips, body map, risk estimate and guidance updating as the transcript grows.
  Quick and full modes on one screen.
- **Risk estimation** — a gradient-boosted model over 13 mapped features, with
  per-feature attribution and a triage band rather than a bare probability.
- **Hands-free finish** — "save visit" ends the session without the mouse; the
  saved record carries concepts, not the raw sentence.
- **Save & export** — PDF report generated in the browser, visit stored per
  clinician account.
- **Laboratory report parsing** — pasted or uploaded text, unit-aware, feeding
  the medication safety gates.

### Clinical reference
- **Medication review** — 36 options with indications, allergy and condition
  blocks, laboratory gates, monitoring and dose notes; 53 interaction rules, each
  traceable to one of 12 cited documents.
- **Risk scores** — published equations pinned to their sources with the inputs
  they need, and the gaps in the record called out.
- **Guidance** — how to use each workflow, and the clinical principles the tool
  follows.
- **Agent registry** — what each pipeline stage does and where it runs.

### Records
- **History** — every screening and saved visit, re-exportable, filterable by
  patient, with a per-patient trail.
- **Patients** — notes, timelines and a printable summary grouped by name.
- **Notes** — private notes that follow the case across screens.
- **FHIR export** — a standard bundle for the records that need to leave.

### The app itself
- **Adaptive navigation** — five destinations plus More on a phone, a labelled
  rail from 1024px, both from one list.
- **Command palette** — Ctrl/⌘ K, ranked for the words clinicians actually type.
- **Both palettes** — teal-on-graphite and violet-on-white, switched in the top
  bar, remembered, and synced to the browser chrome colour.
- **Installable and offline-capable** — manifest, service worker, cached shell,
  and no clinical response ever cached.
- **Accounts and idle lock** — per-clinician workspace, sign-out after 15 idle
  minutes.

---

## 2. Next, in the order the evidence recommends

Each item names the user problem, the cost, and how it would be verified. "Free"
means no paid service; some items still cost engineering time, which is the real
budget.

### Small (a session or two each)

1. **PWA shortcuts and share target.** Long-press the installed icon to get "New
   consultation" and "History"; share a laboratory report straight into the
   medication screen. *Manifest only (`shortcuts`, `share_target`), no new
   dependency.* Verify: manifest keys present, shortcut URLs resolve, the share
   POST lands on the right route.
2. **Update-available prompt.** A waiting service worker currently activates on
   the next natural reload. A small "New version — reload" toast, driven by
   `registration.waiting` and `controllerchange`, closes the gap where a
   clinician keeps a stale bundle for days. *Free; ~40 lines.* Verify: unit test
   the state machine, and an E2E that swaps the worker in a browser.
3. **Keyboard shortcut sheet.** `?` opens the list (Ctrl/Cmd K, arrows, Enter,
   Escape, skip link). *Free.* Verify: palette-style audit state and a unit test
   for the toggle logic.
4. **Print stylesheet for the consult summary.** Patients' pages print today by
   chance; a proper `@media print` rule set (no rail, no bar, no shadows, black
   on white) makes the summary usable as a handout. *Free.* Verify: render to
   PDF in Chromium and assert page count and text; print emulation in the audit.
5. **Risk trend chart on the patient timeline.** A small SVG of the last N
   screenings, no chart library, keyboard-focusable points with text
   alternatives. *Free.* Verify: pure-function geometry tests + audit contrast.
6. **Three-state theme.** Light / dark / follow system, with the existing boot
   snippet learning the third value. *Free.* Verify: unit tests for the stored
   value and a state that toggles through all three.
7. **Disabled-state audit.** The audit measures visible text; disabled controls
   are exempt from WCAG contrast but not from being legible. Add an explicit
   contrast floor for disabled text so a greyed-out Save is still readable.

### Medium

8. **Offline draft queue.** Capture works offline but saving does not; a visit
   that cannot reach the API should be kept in IndexedDB, replayed on reconnect,
   and clearly marked "not yet filed". This is the highest-value reliability
   feature, and the service worker already proves the offline path.
   *Free; needs a durable local store and conflict rules.* Verify: fake-indexeddb
   unit tests, an E2E that saves with the API stopped and replays with it up, and
   a visible banner state in the audit.
9. **Local search across history and notes.** A client-side index (patient name,
   concept, date, medication) with the palette's ranking. No search service.
   *Free.* Verify: query-ranking unit tests and a journey step that finds a saved
   visit by concept.
10. **FHIR import.** The app exports a bundle but cannot read one back, so a
    record from another system has to be retyped. A local, validating importer
    (patients, conditions, medications, observations) closes the loop.
    *Free.* Verify: round-trip property test (export → import → same facts) and a
    rejected-malformed-bundle test.
11. **Encrypted local backup.** One file containing the workspace's records,
    encrypted with a passphrase (WebCrypto AES-GCM), restorable on another
    device. *Free; the hard part is the key-handling UX, not the crypto.*
    Verify: round-trip tests, wrong-passphrase failure, and a documented threat
    model in [SECURITY.md](SECURITY.md).

### Larger

12. **Full internationalisation of the interface.** Capture understands nine
    languages; the chrome is English. Translation files plus a language switch,
    with the clinical strings reviewed per language rather than machine-
    translated. *Free; the review is the cost.* Verify: missing-key lint, a
    pseudo-locale layout sweep (long words are where the layout breaks), and the
    audit run once per locale.
13. **Visual regression snapshots.** The audit proves contrast and layout
    numerically; it cannot see a card that moved 4px and looks wrong. Playwright
    screenshots with a fixed viewport and font loading, diffed against committed
    baselines, would catch that. *Free; storage and maintenance are the cost.*
    Verify: a deliberate 4px change must fail the diff before it is trusted.
14. **True-device verification.** A documented one-page procedure (Chrome remote
    debugging over USB, iOS Safari Web Inspector, Android home-screen install,
    split view on an iPad) that a second person can follow. *Free.* This is the
    only way to verify safe areas, the on-screen keyboard, and real orientation
    changes — see the limits in [VERIFICATION.md](VERIFICATION.md).

---

## 3. Functions worth improving

| Area | Today | Improvement |
|---|---|---|
| Bundle weight | One 805 kB chunk (gzip 252 kB); jsPDF and the 3D body map are imported eagerly | Route-level `import()` for the PDF writer, the 3D scene and the FHIR exporter; the initial chunk should not carry a PDF renderer |
| Live stream | Reconnects, but the UI says little when it drops | A visible "live concepts paused — retrying" state, with the transcript still captured locally |
| Transcript | Lines are appended and can be cleared; no edit-in-place | Per-line edit and delete with undo, because dictation mishears names |
| Medication catalogue | 36 options, curated | Grow toward common outpatient cardiology (SGLT2, MRA, loop diuretics, antianginals), every addition a directional test plus a source |
| Risk explanations | Per-feature attribution | Plain-language "what drove this" sentences, with the model's known limits stated next to them |
| History | Cards, tabs, patient filter | Sort and filter by date, band, concept; the data is already local |
| PDF report | Paginated by measurement | Tagged text, language set, and a print stylesheet path — a PDF a screen reader can follow |
| Empty states | Text plus a link | Show the action that fills the empty state (e.g. "start a consultation" on an empty history) |
| Audit | Numbers, no pixels | Snapshot diffs (item 13) beside the measured checks |
| Accounts | Local store, limiter, idle lock | Passkey/WebAuthn sign-in (free, browser-native) and an audit trail of sign-ins per account |

---

## 4. What this project should not do

- **No paid APIs or hosted services** in the clinical path: no model API, no
  cloud database, no telemetry vendor. The app's claim is that it runs on the
  device, and every one of those would make the claim false.
- **No cloud sync of patient data** without an explicit, encrypted,
  user-controlled design. "Local only" is a feature, not a gap.
- **No automatic dose adjustment.** The catalogue is decision support; the
  prescriber stays responsible, and the disclaimer says so.
- **No dark patterns in the install prompt.** One line in the account menu is
  enough; a modal demanding installation is not.
