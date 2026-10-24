# Continuous integration

`.github/workflows/tests.yml` runs on every push to `main`, on every pull
request, and on `workflow_dispatch`. All five jobs are pinned to
`ubuntu-24.04` deliberately: `ubuntu-latest` migrates to Ubuntu 26 and the
toolchain here (Playwright/Chromium, `pip`, the audit's contrast maths) should
move on purpose, not overnight.

| Job | Proves |
|---|---|
| `backend` | The pytest suite (280 cases) and the script checks: clinical direction, the published score tables against their sources, the 36-option medication catalogue and its 53 sourced rules, de-identification, the local stores, the login limiter, the FHIR bundle, the live medication screen. |
| `frontend` | `tsc -b`, the vitest suite (60 cases: extraction patterns, session/retry behaviour, PDF layout, the microphone meter's thresholds, the theme boot path) and the production build. |
| `ui-audit` | The built app, **signed in**, swept in **both themes**: contrast at 3 viewports × 12 routes × 2 palettes, layout at 9 widths × 12 routes, and 12 open-state audits (account menu, both consult tabs, each at 1440 and 390 in both themes). WCAG AA against each element's real rendered background, no horizontal overflow, no clipped text, no tap target under 24 px — plus the dock, its current item and the account menu on every signed-in route. |
| `e2e` | The journey a clinician takes — sign in, capture a transcript line, save the visit, download the PDF, land on thank-you, find it in history — against the **built bundle** served by `vite preview` and a live API (ADR-030). |
| `gate` | Nothing of its own: it is red unless the four jobs above are green. This is the single check to require in branch protection. |

`.github/workflows/deploy-pages.yml` publishes the frontend to GitHub Pages; it
builds the same bundle the `frontend` job builds, so a Pages deploy that
succeeds while `frontend` is red means the two have drifted.

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

Three checks in the sweep exist because measuring one render of each route was
not enough (ADR-029):

- **Both palettes.** Each contrast viewport and route is loaded once per theme
  with `pulseiq.theme` written before the document boots, and the *system*
  preference emulated as the other theme — so only the stored preference can
  produce the audited palette. Every load asserts the class it asked for took
  effect; `themeChecks` and `themeIssues` record how many did. Deleting the
  stored write fails all 90 loads, which is how the check was proved to have
  teeth.
- **The screens behind a click.** The account menu, the "Full consult" tab and
  the "Consultations" list are opened at 1440 and 390 in both themes, proved to
  have arrived (menu role; tab `selected`), then audited for contrast and
  layout. A state that never opens fails the job as `stateIssues` — auditing the
  page behind a panel that did not appear is the same blind spot as auditing
  `/login` as the workspace.
- **The shell.** Every signed-in route must render the dock with nine
  destinations, the dock item that matches the route (by accessible name) and
  the account menu. A page can render its own content and still not be the
  workspace; `shellIssues` names what was missing.

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

`ui-audit-report` is uploaded whether the job passes or fails and contains:

- `scripts/ui-audit-report.json` — `sampledTotal` and `sampledByTheme`, every
  contrast violation (tagged with theme and, for a state, its name), every
  layout issue (page overflow, clipped text, small target), plus `signedIn`,
  `requireSignIn`, `themes`, `themeChecks`, `statesAudited`, `redirects`,
  `themeIssues`, `shellIssues` and `stateIssues` so the artifact states what was
  audited and what failed, not only that it did.
- `backend-audit.log` — the server's stdout. A red audit has two possible
  authors, the layout and the server the pages were reading from.

The job is capped at `timeout-minutes: 25`: it installs a Python stack, builds
the bundle, starts a server and walks 72 contrast loads, 108 layout loads and 12
state loads.

## Reproducing any job locally

```bash
# backend + frontend, the same commands CI runs
cd cardio-ai-system
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
