# What is verified, and what is not

A green gate is a list of claims, not a guarantee. This document says which
claims the repository actually checks, what each check can see, how to reproduce
it, and which claims still need a person — so nobody has to infer the boundary
from a checklist in a pull request.

---

## 1. The gate, and what each part proves

| Check | Command | Proves | Cannot see |
|---|---|---|---|
| Backend suite | `python -m pytest backend -q` | Clinical direction, published scores against their sources, the 36-option catalogue and 53 rules, de-identification, stores, limiter, FHIR, the CI definition itself | Anything outside Python; model accuracy on real patients |
| Frontend suite | `cd frontend && npm run test` | Extraction patterns, session/retry, PDF layout, theme path, palette ranking, service-worker policy, offline notice | Rendering, real browser APIs |
| Typecheck/lint/build | `npm run typecheck && npm run lint && npm run build` | Types, lint, the production bundle | Runtime behaviour |
| UI audit | `node scripts/ui-audit.cjs --require-sign-in` | Contrast, layout, states, palettes, focus, spacing, print, installability, offline shell — in a real Chromium against the built bundle | Screen readers, real devices, visual taste |
| E2E journey | `node scripts/e2e-save-visit.cjs --base-url …` | Sign-in → adaptive navigation → palette → capture → save → PDF → history against a live API | Other routes, other browsers |
| Sources | `python scripts/verify_sources.py` | Every citation resolves to a registered, cited, https entry | Live URLs (that needs `--network`) |
| CI definition | `pytest backend/test_ci_workflow.py` | Job graph, gate wiring, server boot order, pinned runners, paths and npm scripts that exist | That GitHub actually runs it |
| Workflow/live sources | `make verify-sources NETWORK=1` | DOIs resolve through Crossref with matching titles | Publisher pages behind bot protection |

Two of these exist because the previous answer was "read the YAML and hope": the
workflow test, and the citation verifier.

---

## 2. What was unverified, and what closed it

### "The CI jobs were never executed"

The jobs themselves still run only on a hosted runner, which cannot be exercised
from a laptop. What *can* be verified — and now is — is that the definition says
what the docs claim and would not fail for a mechanical reason:

- `backend/test_ci_workflow.py` parses `.github/workflows/tests.yml` with PyYAML
  and asserts: the seven jobs exist; `gate` needs all six and uses
  `always()`; the audit job starts uvicorn on 8000, waits on `/health` and runs
  `--require-sign-in`; the E2E job builds, serves on 4173, names a browser and
  passes `--base-url http://127.0.0.1:4173`; the dataset job runs
  `import_uci_heart.py --check` with no `pip install` in it; every `run` step's
  repository path exists; every `npm run` target exists and resolves to a file;
  runners are pinned and timeouts bounded; actions use pinned major versions.
- A negative test was run by hand: removing `--require-sign-in` from the audit
  step turns the suite red with the reason, and restoring it turns it green.
- Each job's commands were also run locally in the same order (`make gate`), so
  the failure surface left is the runner environment itself: image, Python/Node
  versions, Chrome availability.

**Still unverified:** a real GitHub Actions run. This work is committed locally
and has not been pushed, so no run exists to inspect. Pushing and reading the
`Gate` check is the remaining step, and it needs the repository owner.

### "The audit only saw the first paint of each route"

The sweep now opens and proves **22 states**, in both themes, at 390 and 1440 px
(the More sheet only where it exists):

account menu · consultation "Full consult" tab · history "Consultations" tab ·
More sheet (with four destinations reachable) · command palette (with a query
typed) · theme switch (flipped through the UI).

A state that fails to open is its own failure, so auditing the page behind a
panel that never appeared cannot pass. Contrast coverage is every text node in
those states, plus 12 routes × 4 widths × 2 palettes.

### "Two source URLs were never checked"

All 12 are now checked, and the check distinguishes its answers:

- 11 confirmed: DOIs resolved through the free Crossref API with a title that
  agrees with the registered title (AHA journals answer 403 to non-browser
  clients, so a direct fetch would have called them dead), or a direct 200 for
  the non-DOI links.
- 1 **protected**: Diabetes Care's supplement page answers 403 to automated
  clients. That is reported as bot protection, not as a broken citation, because
  a checker that fails on a paywall gets switched off and then checks nothing.
- The verifier's first run also found a registry defect — `gold-2025` was
  registered and cited by nothing — fixed by citing it on the beta-blocker entry
  with wording that matches GOLD's position on COPD.

**Still unverified:** that a reader with institutional access lands on the exact
section a rule refers to. The sources are document-level by design; the
catalogue says so rather than implying page-level precision.

### "Installability and offline behaviour were claims"

The audit's PWA pass loads the production bundle and checks the manifest
(`name`, `short_name`, `start_url`, accepted `display`, 192 and 512 icons, each
icon's HTTP status), waits for an active service worker, then **switches the
network off** and opens `/history`. The shell must render.

It failed on the first run, twice: the cached HTML could not start without its
hashed bundle, and `Vary: Origin` made the cache miss the assets it had just
stored. Both are fixed; the worker's policy is unit-tested against fake caches,
including "never intercept `/api`, `/ws` or a POST".

The same pass now also requires the offline notice — with a working cached shell,
an unreachable engine no longer looks like a failure until a save is attempted.
And the manifest's long-press shortcuts are validated like the rest: each must
name a route that answers 200.

### "Sizing and orientation"

Widths are audited from **320 to 2560 px**, including tablet portrait
(768×1024), tablet landscape (1024×768), phone portrait (390×844) and phone
landscape (844×390), plus the common laptop panels. The layout pass fails on
horizontal page overflow, clipped text (width or height), and targets under
24px. Text-spacing overrides are applied and re-checked, and focus is walked
control by control to ensure nothing lands under a bar.

**Still unverified:** real safe-area insets, the on-screen keyboard, an iPad's
split view, and rotation on a physical device. Chromium viewports are not a
notch.

---

## 3. Reproducing it

```bash
cd cardio-ai-system
.venv/Scripts/python.exe -m uvicorn backend.api_server:app --port 8000   # separate terminal
python -m pytest backend -q                                             # backend
python scripts/verify_sources.py --network                              # citations, live
cd frontend && npm run typecheck && npm run test && npm run lint && npm run build
cd .. && node scripts/ui-audit.cjs --require-sign-in                    # builds + serves itself
node scripts/e2e-save-visit.cjs                                         # starts servers if needed
```

`make gate` chains the code and browser gates; `make verify-sources NETWORK=1`
checks the citations. The audit and the journey both need Chrome or Edge;
`EDGE_PATH` points at a binary if the default locations miss.

Every failure writes its evidence: `scripts/ui-audit-report.json` records the
base URL, sign-in state, every sampled count, every violation with its route and
viewport, the states that failed to open, and each page's landing URL.

---

## 4. What still needs a human

These are not gaps in effort; they are things automation cannot establish.

1. **A hosted CI run.** Push, open the Actions tab, require `Gate`. Until then
   the pipeline is tested as a definition, not as a service.
2. **Real devices.** iPhone (notch, home indicator, standalone), iPad (split
   view, rotation), a small Android phone, a 1366×768 laptop at 125% zoom.
   Follow the procedure in [FEATURES.md](FEATURES.md) §2 item 14.
3. **Other browsers.** The audit drives Chromium only. Firefox and Safari each
   need one manual pass over sign-in, capture, save and history; Safari's Web
   Speech support differs and is already documented as partial.
4. **Screen readers.** VoiceOver on iOS/macOS and NVDA on Windows over the
   workspace: navigation names, the More sheet, the palette listbox, live
   concept updates and form errors. The markup is conventional and the audit
   checks names and current state, but announcements are not measured.
5. **Microphone and dictation.** `getUserMedia` and the Web Speech API are
   mocked nowhere; dictate mode is exercised by hand.
6. **Realtime with more than one client.** The concept stream is tested by the
   journey for one client. Two accounts on one visit, reconnect after sleep, and
   a dropped socket mid-save are manual.
7. **Performance on a low-end device.** The entry chunk is 446 kB (133 kB gzip)
   after the PDF writer was moved on demand; whether that is fast on a five-year-
   old phone still needs the phone, not a desktop viewport.
8. **Visual judgement.** Whether the feed, the rail and the palettes look good is
   a person's call. The audit can prove nothing is unreadable or broken; it
   cannot prove something is attractive.
