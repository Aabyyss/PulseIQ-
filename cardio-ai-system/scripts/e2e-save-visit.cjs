/**
 * PulseIQ end-to-end journey test: login → save visit → thank-you page.
 *
 * Walks the exact flow a clinician takes on first use:
 *
 *   1. /login            storage notice dismisses and stays dismissed,
 *                        sign-in with the E2E account (auto-registers on a
 *                        fresh database via the API so the UI login path is
 *                        always exercised exactly once)
 *   2. /consultation     Save is disabled with an empty transcript; typing a
 *                        line and submitting enables it; consent checkbox
 *                        ticks
 *   3. save visit         POST /api/final-report and POST /api/consultations
 *                        both return 2xx, a PDF download starts, the visit
 *                        count on the server increases by exactly one
 *   4. /thank-you        correct title, confirmation heading, next-steps
 *                        cards and both CTAs
 *   5. /history          the new visit is the newest entry under the
 *                        Consultations tab with "1 transcript line"
 *
 * Fails (exit 1) on any uncaught page error, any /api/* response ≥ 400, or
 * any console error other than aborted requests (navigation races).
 *
 * Servers are reused when already running; otherwise the backend (uvicorn)
 * and frontend (vite) are started by this script and stopped when it ends.
 *
 * Usage:
 *   node scripts/e2e-save-visit.cjs                    # or: cd frontend && npm run e2e
 *   node scripts/e2e-save-visit.cjs --base-url <url>   # test an already-running app
 *   PULSEIQ_URL=<url> node scripts/e2e-save-visit.cjs
 */
const path = require("node:path");
const fs = require("node:fs");
const { createRequire } = require("node:module");
const { spawn, execSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const FRONTEND = path.join(ROOT, "frontend");
// resolve playwright-core from the frontend install, not from scripts/
const requireFromFrontend = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = requireFromFrontend("playwright-core");

const BACKEND_HEALTH = "http://127.0.0.1:8000/health";
const EMAIL = "e2e-verify@cardio.local";
const PASSWORD = "E2ePass123";
const TRANSCRIPT_LINE =
  "Chest pressure for 2 days, tightness in the centre of my chest when I climb stairs, " +
  "relieved within a few minutes of resting. No fever.";

const CHROME_CANDIDATES = [
  process.env.EDGE_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/microsoft-edge",
  "/usr/bin/microsoft-edge-stable",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

function findChrome() {
  for (const p of CHROME_CANDIDATES) if (fs.existsSync(p)) return p;
  throw new Error("No Chrome/Edge found. Set EDGE_PATH to a Chromium-based browser.");
}

function parseArgs() {
  const args = process.argv.slice(2);
  const i = args.indexOf("--base-url");
  const baseUrl =
    i >= 0 ? args[i + 1] : process.env.PULSEIQ_URL || "http://localhost:5173";
  return { baseUrl };
}

async function isUp(url, timeoutMs = 2500) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    return res.ok;
  } catch {
    return false;
  }
}

function waitFor(url, timeoutMs, what) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (await isUp(url)) return resolve();
      if (Date.now() - start > timeoutMs)
        return reject(new Error(`${what} never answered at ${url}`));
      setTimeout(tick, 500);
    };
    tick();
  });
}

/* ---------- tiny step log ---------- */

const steps = [];
function step(name) {
  steps.push(name);
  console.log(`\n▶ ${name}`);
}
function pass(detail) {
  console.log(`  ✓ ${detail}`);
}
function assert(cond, detail) {
  if (!cond) throw new Error(`assertion failed: ${detail}`);
  pass(detail);
}

/**
 * Fresh databases have no E2E account. Ensure one exists so the UI login
 * path always succeeds on the first (and only) attempt — a failed UI login
 * would count toward the backend's brute-force lockout (5 per 15 min).
 * Pre-flight uses the API: at most one wrong-password failure, cleared by
 * the successful login that follows; registration never touches the limiter.
 */
async function ensureAccount(baseUrl) {
  const post = (p, body) =>
    fetch(`${baseUrl}/api${p}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const loginRes = await post("/auth/login", { email: EMAIL, password: PASSWORD });
  if (loginRes.ok) return pass("E2E account exists (API pre-flight login ok)");
  const regRes = await post("/auth/register", { email: EMAIL, password: PASSWORD, name: "E2E Verify" });
  if (regRes.ok) return pass("E2E account created on fresh database");
  throw new Error(
    `could not ensure E2E account: login ${loginRes.status}, register ${regRes.status} ` +
      `(${await regRes.text()})`
  );
}

(async () => {
  const base = parseArgs().baseUrl;
  const spawned = [];
  let browser;

  try {
    /* ---------- servers: reuse when up, otherwise start our own ---------- */
    step("Servers");
    if (await isUp(BACKEND_HEALTH)) {
      pass(`backend already running at ${BACKEND_HEALTH}`);
    } else {
      const python = path.join(
        ROOT,
        process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"
      );
      if (!fs.existsSync(python))
        throw new Error(`backend is down and no venv at ${python} — start it manually`);
      spawned.push({
        what: "backend",
        pid: spawn(python, ["-m", "uvicorn", "backend.api_server:app", "--host", "0.0.0.0", "--port", "8000"], {
          cwd: ROOT,
          stdio: "ignore",
          windowsHide: true,
        }).pid,
      });
      await waitFor(BACKEND_HEALTH, 90000, "backend");
      pass("backend started");
    }
    if (await isUp(base)) {
      pass(`frontend already running at ${base}`);
    } else {
      spawned.push({
        what: "frontend",
        // Single command string (not args + shell:true) — avoids DEP0190 and
        // keeps npx resolvable on Windows, where it is a .cmd shim.
        pid: spawn("npx vite --host 127.0.0.1 --port 5173 --strictPort", {
          cwd: FRONTEND,
          stdio: "ignore",
          shell: process.platform === "win32",
        }).pid,
      });
      await waitFor(base, 60000, "frontend");
      pass("frontend started");
    }

    await ensureAccount(base);

    /* ---------- browser + telemetry ---------- */
    step("Browser");
    browser = await chromium.launch({ executablePath: findChrome(), headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    context.setDefaultTimeout(30000);
    const page = await context.newPage();

    const pageErrors = [];
    const consoleErrors = [];
    const apiFailures = [];
    const apiLog = []; // every /api/* response, so success paths can be asserted too
    let finalReportBody = null; // captured so "200 but {error}" cannot pass silently
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("response", async (res) => {
      const url = res.url();
      if (!url.includes("/api/")) return;
      const entry = `${res.request().method()} ${url.replace(base, "")} → ${res.status()}`;
      apiLog.push(entry);
      if (res.status() >= 400) apiFailures.push(entry);
      if (url.includes("/api/final-report")) {
        try {
          finalReportBody = await res.json();
        } catch {
          /* body unreadable — the report assertion below will fail loudly */
        }
      }
    });
    pass(`headless chromium at ${base}`);

    /* ---------- 1. login ---------- */
    step("Login page");
    await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
    assert((await page.title()) === "Sign in · PulseIQ", "login page title");

    // Fresh context → first-visit storage notice renders; it must dismiss permanently.
    const gotIt = page.getByRole("button", { name: "Got it" });
    if (await gotIt.isVisible().catch(() => false)) {
      await gotIt.click();
      await gotIt.waitFor({ state: "detached", timeout: 5000 });
      const key = await page.evaluate(() => localStorage.getItem("pulseiq.storageNotice.v1"));
      assert(key === "1", "storage notice dismissed and remembered");
    } else {
      pass("storage notice already dismissed");
    }

    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
    const token = await page.evaluate(() => localStorage.getItem("pulseiq_token"));
    assert(token && token.length > 0, `signed in, session persisted (POST /api/auth/login → 200)`);

    /* ---------- 2. consultation capture ---------- */
    step("Consultation capture");
    await page.goto(`${base}/consultation`, { waitUntil: "domcontentloaded" });
    const saveBtn = page.getByRole("button", { name: "Save visit & export PDF" });
    await saveBtn.waitFor({ state: "visible" });
    assert(await saveBtn.isDisabled(), "Save disabled with an empty transcript");

    const countOf = async () => {
      const res = await page.request.get(`${base}/api/consultations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      assert(res.ok(), `GET /api/consultations → ${res.status()}`);
      return (await res.json()).items.length;
    };
    const visitsBefore = await countOf();

    await page.getByPlaceholder(/transcript line instead of speaking/).fill(TRANSCRIPT_LINE);
    await page.getByRole("button", { name: "Submit line" }).click();
    await saveBtn.waitFor({ state: "visible", timeout: 15000 });
    await page.waitForFunction(
      () => {
        const btn = [...document.querySelectorAll("button")].find((b) =>
          b.textContent.includes("Save visit & export PDF")
        );
        return btn && !btn.disabled;
      },
      undefined,
      { timeout: 15000 }
    );
    pass("one typed line enables Save (1 transcript line captured)");

    // Concepts arrive asynchronously via the WebSocket line_ack and feed both
    // chief_complaint and symptom_notes on save. The manual walkthrough takes
    // this time naturally; the test must wait for the chips or it would race
    // the ack and save an empty-concept record.
    await page
      .getByText("Detected concepts appear here the moment a line is captured.")
      .waitFor({ state: "hidden", timeout: 20000 });
    // Scope to <span> so the Teach panel's hidden <option> can't match.
    await page
      .locator("span")
      .filter({ hasText: /^chest pain$/ })
      .first()
      .waitFor({ timeout: 5000 });
    pass('concepts arrived over the copilot stream ("chest pain" chip)');

    const consent = page.locator('[aria-label="Patient consents to recording"]');
    await consent.click();
    const consented = await consent.evaluate(
      (el) => el.checked === true || el.getAttribute("aria-checked") === "true"
    );
    assert(consented, "consent checkbox ticked");

    /* ---------- 3. save → report + store + PDF ---------- */
    step("Save visit");
    const downloadPromise = page
      .waitForEvent("download", { timeout: 150000 })
      .catch(() => null);
    await saveBtn.click();
    await page.waitForURL("**/thank-you", { timeout: 150000 });

    const download = await downloadPromise;
    assert(download, "PDF download started by 'Save visit & export PDF'");
    // Let the async response handler finish reading bodies before asserting.
    await page.waitForTimeout(500);
    const okHit = (method, suffix) =>
      apiLog.some((e) => e.startsWith(method) && e.includes(suffix) && e.endsWith("→ 200"));
    assert(okHit("POST", "/api/consultations"), "POST /api/consultations → 200");
    assert(
      Boolean(finalReportBody && finalReportBody.report),
      `POST /api/final-report returned a report plan${
        finalReportBody && finalReportBody.error ? ` (backend said: ${finalReportBody.error})` : ""
      }`
    );
    const visitsAfter = await countOf();
    assert(visitsAfter === visitsBefore + 1, `visit stored (count ${visitsBefore} → ${visitsAfter})`);

    /* ---------- 4. thank-you page ---------- */
    step("Thank-you page");
    await page.waitForFunction(() => document.title === "Visit saved · PulseIQ", undefined, {
      timeout: 15000,
    });
    pass('title "Visit saved · PulseIQ"');
    const body = await page.locator("main").innerText();
    assert(
      body.includes("Thank you — the consultation is filed"),
      "confirmation heading rendered"
    );
    assert(body.includes("What happens next"), "next-steps section rendered");
    for (const card of ["Find it in History", "Per-patient trail", "De-identified at rest"]) {
      assert(body.includes(card), `next-steps card "${card}"`);
    }
    await page.getByRole("link", { name: "Start a new consultation" }).waitFor();
    await page.getByRole("link", { name: "Review past visits" }).waitFor();
    pass("both CTAs present");

    /* ---------- 5. history ---------- */
    step("History");
    await page.goto(`${base}/history`, { waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: "Consultations" }).click();
    const newest = page.locator('[role="tabpanel"][data-state="active"] li').first();
    await newest.waitFor();
    const entry = await newest.innerText();
    assert(entry.includes("1 transcript line"), 'newest visit shows "1 transcript line"');
    // chief complaint falls back to the extracted concepts ("chest pain"),
    // not the raw sentence — HistoryPage renders badges, not the transcript.
    assert(entry.includes("chest pain"), "newest visit carries its detected concepts");
    await newest.getByRole("button", { name: "Export PDF" }).waitFor();
    pass("re-export available on the stored visit");

    /* ---------- telemetry gates ---------- */
    step("Telemetry");
    assert(pageErrors.length === 0, `no uncaught page errors${pageErrors.length ? `: ${pageErrors[0]}` : ""}`);
    assert(apiFailures.length === 0, `no failed /api/* calls${apiFailures.length ? `: ${apiFailures[0]}` : ""}`);
    const realConsoleErrors = consoleErrors.filter((t) => !t.includes("ERR_ABORTED"));
    assert(
      realConsoleErrors.length === 0,
      `no console errors${realConsoleErrors.length ? `: ${realConsoleErrors[0]}` : ""}`
    );
    if (consoleErrors.length) {
      console.log(`  · ${consoleErrors.length} aborted-request console notice(s) ignored (navigation race)`);
    }

    console.log(`\n✓ E2E journey passed — login → save-visit → thank-you → history (${steps.length} steps)`);
  } catch (err) {
    console.error(`\n✗ E2E journey FAILED in step "${steps[steps.length - 1] || "startup"}"`);
    console.error(`  ${err.message}`);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    for (const s of spawned) {
      try {
        if (process.platform === "win32") {
          execSync(`taskkill /PID ${s.pid} /T /F`, { stdio: "ignore" });
        } else {
          process.kill(s.pid, "SIGTERM");
        }
        console.log(`· stopped ${s.what} (pid ${s.pid})`);
      } catch {
        /* already gone */
      }
    }
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
