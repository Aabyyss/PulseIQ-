# Continuous integration

`.github/workflows/tests.yml` runs on every push to `main`, on every pull
request, and on `workflow_dispatch`. All seven jobs are pinned to
`ubuntu-24.04` deliberately: `ubuntu-latest` migrates to Ubuntu 26 and the
toolchain here (Playwright/Chromium, `pip`, the audit's contrast maths) should
move on purpose, not overnight.

| Job | Proves |
|---|---|
| `backend` | The pytest suite (600 cases) and the script checks: clinical direction, the published score tables against their sources, the 36-option medication catalogue and its 53 sourced rules, de-identification, the local stores, the login limiter, the FHIR bundle, the live medication screen, and the CI definition (below). |
| `frontend` | `tsc -b`, the vitest suite (82 cases: extraction patterns, session/retry behaviour, PDF layout, microphone thresholds, the theme boot path and browser-chrome colour, navigation and palette ranking, the service worker's caching policy) and the production build. |
| `ui-audit` | The built app, **signed in**, swept in **both themes**: contrast at 4 viewports × 12 routes × 2 palettes, layout at 11 widths (320–2560 px, both tablet orientations) × 12 routes, and 22 open-state audits (account menu, both consult tabs, More sheet, command palette, theme switch). Also WCAG 1.4.12 text-spacing overrides, 2.4.11 focus-obscured checks, and the manifest/icons/service-worker/offline-shell pass. |
| `e2e` | The journey a clinician takes — sign in, adaptive navigation (rail, More sheet, Ctrl-K), capture a transcript line, save the visit, download the PDF, land on thank-you, find it in history — against the **built bundle** served by `vite preview` and a live API (ADR-030). |
| `sources` | Every drug and rule cites a registered source and every registered source is cited (`scripts/verify_sources.py`, no network). |
| `dataset` | The committed `data/heart.csv` is still what the importer builds from the licensed UCI source: every value, the provenance record (licence, counts, pinned hashes) and the CC BY 4.0 attribution notice (`scripts/import_uci_heart.py --check`). |
| `gate` | Nothing of its own: it is red unless the six jobs above are green. This is the single check to require in branch protection. |

`.github/workflows/deploy-pages.yml` publishes the frontend to GitHub Pages; it
builds the same bundle the `frontend` job builds, so a Pages deploy that
succeeds while `frontend` is red means the two have drifted.

`.github/workflows/toolchain-drift.yml` is the one workflow that is not part of
the gate: it runs weekly and asks whether the released floors have moved past
the pinned toolchain. It is described under [the weekly drift
check](#the-weekly-drift-check) and deliberately does not run on push.


## The toolchain is pinned, not floated

`requirements.txt` and `requirements-dev.txt` state floors (`>=`) because that is
what the app needs. A runner installs more than floors: on 2026-10-28 it resolved
`pandas 3.1.0`, `scikit-learn 1.9.1`, `pytest 9.2.0` and 67 other distributions —
70 in all — and a release published the next morning would have replaced any of
them without a commit. Two identical pushes could then disagree, which is the one thing a gate
cannot afford.

`requirements.lock.txt` is that resolved closure — every package the green run
installed, pinned with `==`, with the run and commit it came from in the header.
Every install step passes it as constraints:

```bash
pip install -r requirements-dev.txt -c requirements.lock.txt
```

Constraints pin what is being installed and install nothing themselves, so the
Linux-only wheels (`uvloop`, `httptools`) stay harmless on a Windows checkout.
Moving the toolchain is now an edit to that file, deliberately, rather than a
side effect of pushing on a different day. `backend/test_declared_dependencies.py`
keeps it honest: every direct requirement must appear in it, every line must be an
exact pin, and no package may be pinned twice.

### Moving it deliberately

The pin is not meant to be permanent; it is meant to move in a commit a reviewer
can read. The rule is that the move is proved, not assumed.

1. **Read the drift first.** The [weekly check](#the-weekly-drift-check) names
every distribution whose released version differs, with both versions. No drift
and no other reason means there is nothing to do.
2. **Resolve the floors in the gate's image** — Python 3.12 on ubuntu-24.04,
in a clean environment:

   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements-dev.txt        # no -c: the floors are the input
   ```

3. **Emit the block.** `python scripts/toolchain.py --freeze` prints sorted
`name==version` lines. Replace the package lines in `requirements.lock.txt`,
and update the provenance comment at the top (run number, commit, date, Python
version) — that header is the only record of where the pins came from. The
weekly job's `toolchain-drift` artifact already contains this exact block, so
the common path is a download rather than a reproduction.
4. **Prove the pin.** `python scripts/toolchain.py --check` must exit 0 and say
the environment matches. A non-zero exit here means the paste is incomplete or
the environment has an extra package.
5. **Prove the suite.** `python -m pytest backend -q` and the eight backend
script checks, both exactly as the `backend` job runs them. If a pinned wheel
changed, run the audit and journey locally too (`docs/CI.md` above) — they are
the only checks that load the app in a browser.
6. **Look at the model card if `scikit-learn` moved.** The metadata records
`sklearn_version` next to the pickle, so a moved library means the artifact was
trained on a different one. Retrain (`python backend/train_model.py`) and review
the metric diff instead of shipping a version label that no longer describes
what is in the file.
7. **Push, then read the gate.** The pins only exist once a runner installs from
them; the backend job's log shows `pip install -r requirements-dev.txt -c
requirements.lock.txt` and the versions that followed.

Nothing else needs editing. `backend/test_declared_dependencies.py` fails if a
direct requirement has no pin, if a lock line is not an exact `==`, or if a
package is pinned twice, so a half-finished move fails on a laptop instead of on
the runner.

### The weekly drift check

`.github/workflows/toolchain-drift.yml` runs on Mondays at 06:00 UTC, and on
demand through `workflow_dispatch`. It installs **without** the lock — that is
the point — installs the same spaCy model the gate uses, runs the backend suite,
then compares the environment with the pins:

```bash
pip install -r requirements-dev.txt                          # the floors
python -m pytest backend -q                                  # do they still pass?
python scripts/toolchain.py --check                          # where do they differ?
python scripts/toolchain.py --freeze > resolved-requirements.txt
```

Red means one of two things, and the job summary separates them:

- **Drift.** One row per added, removed or bumped distribution, with the locked
  and installed versions and which kind of change it is.
- **The suite fails on the floors.** The upstream breakage the pin is currently
  hiding — the case that would otherwise arrive inside an unrelated push once
  someone relaxes a floor.

It never runs on push, so it cannot fail a commit for a release that commit did
not touch, and it is not required by `gate`. The `toolchain-drift` artifact
carries `resolved-requirements.txt` (the block to paste) and `pytest-floors.log`,
so the runbook above starts from a download.

`pip` and `en-core-web-sm` are excluded from the comparison by
`scripts/toolchain.py`: the workflow upgrades the installer and fetches the model
by URL, so neither belongs in a lock that describes third-party pins.

## What the dataset job needs

`--check` rebuilds the dataset from the UCI archive, verifies the pinned
SHA-256 of the member file, and compares the result with what is committed —
value by value, plus the provenance JSON and the attribution text. It writes
nothing but the archive cache. Standard library only, so the job installs no
dependencies and has a 10-minute bound; the failure it guards against is a
hand-edited or silently swapped dataset, not a toolchain problem.

**The archive is cached under its own pin.** `actions/cache@v5` restores
`~/.cache/pulseiq/uci-heart-disease.zip` under a key that *is* the archive's
SHA-256, and the check is pointed at it with `--archive`. On a hit the job
touches no network at all: the bytes come from disk, and the member file is
still verified against its own pinned hash before anything is compared, so a
tampered cache fails exactly like a tampered download. There are deliberately no
`restore-keys` — falling back to some other archive would defeat the check. On a
miss the importer downloads once and writes the archive to that path, and the
post-job cache save makes the next run a hit.

The pin is what makes caching safe here. GitHub's cache is not a trust boundary,
but a pinned hash is: a cache hit that does not match the source fails closed.
If the publisher is unreachable *and* the cache is cold, the job still fails,
because a gate that quietly skipped the provenance check would be green about
nothing.

## What the audit job needs

The audit is not a static check. It signs in and reads the API, so the job
provisions the app it audits (ADR-027, ADR-028):

1. `setup-python@v6` (3.12) and `pip install -r requirements.txt` — the runtime
   set, not `requirements-dev.txt`: the job starts the server, it does not test
   it.
2. `uvicorn backend.api_server:app --host 127.0.0.1 --port 8000`, output in
   `backend-audit.log`. Port 8000 is where `vite preview` forwards `/api`
   (`preview.proxy` in `vite.config.ts`), so the built bundle talks to this
   server.
3. The step waits for `/health` — not for the port. `uvicorn` binds before the
   pipeline is warm, and with `--strictPort` a half-started preview looks
   identical to a running one.
4. `node scripts/ui-audit.cjs --require-sign-in`.

The sweep registers `demo@cardio.local` through the public `/auth/register`
endpoint when the account does not exist, so a fresh CI database exercises the
registration path on every run. Override with `PULSEIQ_AUDIT_EMAIL` /
`PULSEIQ_AUDIT_PASSWORD`.

`--require-sign-in` is the contract CI relies on. Without it the sweep degrades:
an unreachable backend means the public pages are audited and the summary says
`(signed out)`. That fallback is right for a laptop and wrong for a gate that
exists to prove the workspace renders, so CI passes the flag and a missing
backend fails the job. The sweep also compares the URL each page landed on with
the route it requested, and fails on any redirect to `/login` while signed in —
a page that renders the sign-in form is not the page it was asked for.

## What the audit covers beyond a first paint

These checks exist because measuring one render of each route was not enough
(ADR-029):

- **Both palettes.** Each contrast viewport and route is loaded once per theme
  with `pulseiq.theme` written before the document boots, and the *system*
  preference emulated as the other theme — so only the stored preference can
  produce the audited palette. Every load asserts the class it asked for took
  effect; `themeChecks` and `themeIssues` record how many did. Deleting the
  stored write fails all 90 loads, which is how the check was proved to have
  teeth.
- **The screens behind a click.** The account menu, both consult tabs, the
  More sheet (at 390 only — it does not exist above `lg`), the command palette
  with a query typed, and the theme switch are opened, proved to have arrived,
  then audited for contrast and layout. A state that never opens fails the job
  as `stateIssues` — auditing the page behind a panel that did not appear is the
  same blind spot as auditing `/login` as the workspace.
- **The shell.** Every signed-in route must render the navigation with nine
  destinations (counted from the list, not the rail's brand link), the item that
  matches the route by accessible name, and the account menu. Visibility is
  measured, not assumed: at `lg` and above all nine must be on screen and the
  phone More control absent; below it exactly five plus a reachable More.
- **Focus, spacing and the app.** Every control on three routes is focused in
  turn to prove nothing lands entirely under a bar (2.4.11); the reader's
  spacing overrides are applied and the clipping checks re-run (1.4.12); the
  manifest, icons, active worker and an offline navigation are checked against
  the built bundle.

The audit found two real defects on its first run: the dock marked "Overview" as
current on `/privacy`, `/terms` and `/thank-you` while `NavLink` dropped the
matching `aria-current`, and three delete buttons in the consultations tab were
22 px square.

## What the journey job needs

The e2e job is the audit job's sibling with a different question. It builds the
same bundle, starts the same API on 8000, then serves the build with
`vite preview` on 4173 and runs the journey against that URL:

```bash
node scripts/e2e-save-visit.cjs --base-url http://127.0.0.1:4173
```

- **`vite preview`, not `vite dev`.** A save path that only works under the dev
transform is not the app. `preview.proxy` forwards `/api` and `/ws`, so the REST
save and the WebSocket concept stream both run against one origin.
- **`--base-url` starts nothing.** If nothing answers at the URL, the journey
  stops in its Servers step and names it, instead of quietly starting a dev
  server on another port and walking the one nobody is serving.
- **The browser is checked by name.** `playwright-core` drives an existing
  browser; the job fails with `no Chrome on this runner` when the image stops
  shipping one, rather than surfacing a thirty-second locator timeout.
- **The journey registers `e2e-verify@cardio.local`** on the fresh database and
  stores one visit per run. The assertion on the visit count is `before + 1`, so
  repeated runs do not make it lie.

## Artifacts

`backend-pytest-log` is uploaded by the `backend` job whether it passes or fails
and contains `pytest-backend.log` — the suite's full output, written through
`tee` with `set -o pipefail` so the pipe cannot turn a failure into its own exit
0. That artifact exists because the run that exposed the CRLF fingerprint
(2026-10-28) failed with a log the API would not serve without repository admin
rights; the failure had to be reconstructed from a checkout instead of read.

`ui-audit-report` is uploaded whether the job passes or fails and contains:

- `scripts/ui-audit-report.json` — `sampledTotal` and `sampledByTheme`, every
  contrast violation (tagged with theme and, for a state, its name), every
  layout issue (page overflow, clipped text by width or height, small target),
  every `focusIssues`, `textSpacingIssues` and `pwaIssues` entry, plus
  `signedIn`, `requireSignIn`, `themes`, `themeChecks`, `statesAudited`,
  `redirects`, `themeIssues`, `shellIssues` and `stateIssues` so the artifact
  states what was audited and what failed, not only that it did.
- `backend-audit.log` — the server's stdout. A red audit has two possible
  authors, the layout and the server the pages were reading from.

The job is capped at `timeout-minutes: 25`: it installs a Python stack, builds
the bundle, starts a server and walks 96 contrast loads, 132 layout loads, 22
state loads, six focus loads, 24 spacing loads and the PWA pass.

## The CI definition is tested, not assumed

`backend/test_ci_workflow.py` parses this workflow — and the drift workflow —
and asserts the parts a reader would otherwise have to verify by eye: the job
set, that `gate` needs every job
with `if: always()` and reads every result, that the audit job starts the API and
waits for `/health`, that the journey points at the built bundle with
`--base-url`, that every repository path and `npm run` target exists, that
runners are pinned, that every `pip install -r` is constrained by
`requirements.lock.txt`, that the pytest step tees its output with `pipefail` and
that the log is uploaded with `if: always()`, and that timeouts are bounded. For
the drift workflow it asserts the weekly cron, the absence of `push`/
`pull_request` triggers, an install line *without* the lock, and the `--check`
and `--freeze` steps. It proves the definitions are what the docs claim; only a
real run proves GitHub executes them, and that needs a push (or a dispatch).

## Reproducing any job locally

```bash
# backend + frontend, the same commands CI runs
cd cardio-ai-system
# Optional but exact: resolve the versions the green run used.
pip install -r requirements-dev.txt -c requirements.lock.txt
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000 &   # leave running
python -m pytest backend -q
cd frontend && npm ci && npm run typecheck && npm run test && npm run lint && npm run build
```

The audit job, exactly as CI runs it — the backend first, in its own shell:

```bash
cd cardio-ai-system
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000   # terminal 1
node scripts/ui-audit.cjs --require-sign-in                              # terminal 2
```

The journey job, exactly as CI runs it — backend, then the built bundle:

```bash
cd cardio-ai-system
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000   # terminal 1
cd frontend && npm run build && npx vite preview --host 127.0.0.1 --port 4173   # terminal 2
cd .. && node scripts/e2e-save-visit.cjs --base-url http://127.0.0.1:4173       # terminal 3
```

With the servers already up and a browser in hand, `npm run ui-audit` from
`frontend/` runs the same sweep without `--require-sign-in`, and
`npm run e2e` runs the journey against the dev server instead of a build. Both
need the backend.

Require `Gate` in branch protection. It is the only check that cannot pass while
one of the four is red or missing.

## Limits

- **Not a clinical check.** Anything that would call an external model falls
  back to the rule-based path, because no CI job has a model server. The pages
  render real data from that path; what the model *infers* is covered by
  `pytest backend`, on fixtures, not here.
- **No microphone.** `getUserMedia` and `AudioContext` are exercised by hand and
  by the demo recording; jsdom has neither, and Chromium's fake device does not
  reproduce a quiet room, a non-default headset or a denied permission.
- **CSS pixels, not panels.** 2560 px is audited as a viewport, not on a 4K
  panel with OS display scaling.
- **One browser.** Chromium (the runner's, or `EDGE_PATH` locally). The dictate
  mode requires Chrome or Edge, so that is the browser class the audit covers.
