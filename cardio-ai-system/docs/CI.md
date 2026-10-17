# Continuous integration

`.github/workflows/tests.yml` runs on every push to `main`, on every pull
request, and on `workflow_dispatch`. All three jobs are pinned to
`ubuntu-24.04` deliberately: `ubuntu-latest` migrates to Ubuntu 26 and the
toolchain here (Playwright/Chromium, `pip`, the audit's contrast maths) should
move on purpose, not overnight.

| Job | Proves |
|---|---|
| `backend` | The pytest suite (259 cases) and the script checks: clinical direction, the published score tables against their sources, de-identification, the local stores, the login limiter, the FHIR bundle, the live medication screen. |
| `frontend` | `tsc -b`, the vitest suite (55 cases: extraction patterns, session/retry behaviour, PDF layout, the microphone meter's thresholds) and the production build. |
| `ui-audit` | The built app, **signed in**, swept at 3 contrast viewports × 9 routes and 9 layout widths × 9 routes: WCAG AA contrast against each element's real rendered background, no horizontal overflow, no clipped text, no tap target under 24 px. |

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

## Artifacts

`ui-audit-report` is uploaded whether the job passes or fails and contains:

- `scripts/ui-audit-report.json` — `sampledTotal`, every contrast violation,
  every layout issue (page overflow, clipped text, small target), plus
  `signedIn`, `requireSignIn` and `redirects` so the artifact states what was
  audited, not only that it passed.
- `backend-audit.log` — the server's stdout. A red audit has two possible
  authors, the layout and the server the pages were reading from.

The job is capped at `timeout-minutes: 25`: it installs a Python stack, builds
the bundle, starts a server and walks 108 page loads.

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

With the servers already up and a browser in hand, `npm run ui-audit` from
`frontend/` runs the same sweep without `--require-sign-in`, and
`npm run e2e` runs the journey instead of the audit. Both need the backend.

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
