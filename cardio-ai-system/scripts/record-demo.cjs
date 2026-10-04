/**
 * Records the PulseIQ demo video (light mode, 1440x940) in two takes:
 *   take 1 — first-visit storage notice → login → overview → consultation:
 *            listening meter, English line + concept chips, Urdu line,
 *            body map, patient details, consent → Save → /thank-you
 *   take 2 — fresh session: History with the saved visit, then a tour of
 *            guidance / agents / security and a dark-mode pass of the app
 *
 * The save is recorded through to the thank-you page; with the built-in
 * rule engine that is quick, with an on-device LLM it can take ~30s of
 * "Saving visit…" (honest footage — the converter speeds it 1.2x).
 *
 * Usage:
 *   1. backend (:8000) + frontend (:5173) running
 *   2. node scripts/record-demo.cjs
 * Outputs: docs/demo/raw-take1.webm, docs/demo/raw-take2.webm
 * Then:    .venv/Scripts/python.exe scripts/convert_demo.py
 */
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const FRONTEND = path.resolve(__dirname, "..", "frontend");
const requireFromFrontend = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = requireFromFrontend("playwright-core");

const OUT = path.resolve(__dirname, "..", "docs", "demo");
const BASE = process.env.PULSEIQ_URL || "http://localhost:5173";
const VIEWPORT = { width: 1440, height: 940 };
// Dedicated demo account: the E2E account carries leftover chips/learned
// state from test runs, which would pre-fill the concepts panel on camera.
const EMAIL = "demo@cardio.local";
const PASSWORD = "DemoPass123";

const errors = [];
const TAKE2_ONLY = process.argv.includes("--take2-only"); // keep an existing raw-take1.webm
let t0 = Date.now();

/** Register the demo account when missing (registration never hits the
 *  brute-force limiter, so the first UI login always succeeds). */
async function ensureAccount() {
  const post = (p, body) =>
    fetch(`http://localhost:5173/api${p}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const loginRes = await post("/auth/login", { email: EMAIL, password: PASSWORD });
  if (loginRes.ok) return;
  const regRes = await post("/auth/register", { email: EMAIL, password: PASSWORD, name: "Demo User" });
  if (!regRes.ok) {
    throw new Error(`could not ensure demo account: login ${loginRes.status}, register ${regRes.status}`);
  }
}

function stamp(ms) {
  return `[${(ms / 1000).toFixed(1)}s]`;
}

/** First visit in every fresh context shows the data-storage notice. */
async function dismissNotice(page, dwellMs = 1800) {
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) {
    await page.waitForTimeout(dwellMs); // let the viewer read the notice
    await gotIt.click();
    await gotIt.waitFor({ state: "detached", timeout: 5000 });
    await page.waitForTimeout(500);
    return true;
  }
  return false;
}

async function login(page, noticeDwell) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500); // let the viewer see the sign-in screen
  await dismissNotice(page, noticeDwell);
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((u) => !String(u).includes("/login"), { timeout: 20000 });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  await ensureAccount();
  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  });

  // ---------------------------------------------------------------- take 1
  if (TAKE2_ONLY) {
    console.log("skipping take 1 — keeping the existing raw-take1.webm");
  } else {
  const ctx1 = await browser.newContext({
    viewport: VIEWPORT,
    colorScheme: "light",
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  const p1 = await ctx1.newPage();
  p1.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  t0 = Date.now();
  await login(p1, 2500); // full dwell: the notice is a new-version highlight

  await p1.waitForTimeout(2500); // overview page dwell
  await p1.goto(`${BASE}/consultation`, { waitUntil: "domcontentloaded" });
  await p1.waitForTimeout(2000);

  // Consent first — the mic gate asks for it before recording may start.
  await p1.locator('[aria-label="Patient consents to recording"]').click();
  await p1.waitForTimeout(800);

  // Hands-free visual: start listening, show the mic level bar, stop.
  await p1.getByRole("button", { name: /Start listening/i }).click();
  await p1.waitForTimeout(4000);
  console.log(stamp(Date.now() - t0), "listening state shown");
  await p1.getByRole("button", { name: /Stop listening/i }).click();
  await p1.waitForTimeout(800);

  // Line 1 — English exertional chest pain ("it pains in my heart" wording).
  await p1
    .locator("textarea")
    .first()
    .fill("I get tight chest pain walking uphill that eases with rest, and it pains in the left side of my heart.");
  await p1.getByRole("button", { name: /Submit line/i }).click();
  await p1
    .locator("span")
    .filter({ hasText: /^chest pain$/ })
    .first()
    .waitFor({ timeout: 45000 }); // instant line_ack chip
  console.log(stamp(Date.now() - t0), "line 1 ack");
  await p1.waitForTimeout(3000); // dwell on concepts + body map

  // Line 2 — Urdu: chest pain + sweating.
  await p1.locator("textarea").first().fill("دل میں درد ہے اور پسینہ آ رہا ہے");
  await p1.getByRole("button", { name: /Submit line/i }).click();
  await p1
    .locator("span")
    .filter({ hasText: /^sweat/i })
    .first()
    .waitFor({ timeout: 45000 });
  console.log(stamp(Date.now() - t0), "line 2 ack (Urdu)");
  await p1.waitForTimeout(6000); // dwell on concepts + body map

  // Fill visit details so the saved record carries a name.
  await p1.getByRole("tab", { name: /Full consult/i }).click();
  await p1.waitForTimeout(800);
  await p1.getByPlaceholder(/patient name/i).fill("Demo Patient");
  await p1.getByPlaceholder(/age/i).fill("58");
  await p1.waitForTimeout(1000);

  await p1.getByRole("button", { name: /Save visit & export PDF/i }).click();
  console.log(stamp(Date.now() - t0), "save clicked — recording through to the thank-you page");
  const tSave = Date.now();
  await p1.waitForURL("**/thank-you", { timeout: 150000 });
  console.log(stamp(Date.now() - t0), `thank-you reached after ${((Date.now() - tSave) / 1000).toFixed(1)}s`);
  await p1.waitForTimeout(6000); // dwell on the confirmation + next-steps cards

  await ctx1.close(); // flush + finalize take 1 video
  await p1.video().saveAs(path.join(OUT, "raw-take1.webm"));
  }

  // ---------------------------------------------------------------- take 2
  const ctx2 = await browser.newContext({
    viewport: VIEWPORT,
    colorScheme: "light",
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  const p2 = await ctx2.newPage();
  p2.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  // Resume: fresh session, History with the just-saved visit.
  await login(p2, 800);
  console.log(stamp(Date.now() - t0), "take 2: signed in");
  await p2.waitForTimeout(2000); // overview dwell
  await p2.goto(`${BASE}/history`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(1200);
  await p2.getByRole("tab", { name: /Consultations/i }).click();
  await p2.getByText("Demo Patient").first().waitFor({ timeout: 20000 });
  console.log(stamp(Date.now() - t0), "take 2: history shows the saved visit");
  await p2.waitForTimeout(6000); // dwell on the saved visit card

  // Feature tour of the new version.
  await p2.goto(`${BASE}/guidance`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(4000);
  console.log(stamp(Date.now() - t0), "guidance shown");
  await p2.goto(`${BASE}/agents`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(4000);
  console.log(stamp(Date.now() - t0), "agents shown");
  await p2.goto(`${BASE}/security`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(3500);
  console.log(stamp(Date.now() - t0), "security shown");

  // Dark-mode pass: toggle from the header control, then re-show the home.
  await p2.getByRole("switch", { name: "Switch to dark mode" }).click();
  await p2.waitForTimeout(2500);
  await p2.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(4500);
  console.log(stamp(Date.now() - t0), "dark-mode overview shown");

  await ctx2.close();
  await p2.video().saveAs(path.join(OUT, "raw-take2.webm"));
  await browser.close();

  if (errors.length) {
    console.log("\nPage errors observed:");
    errors.forEach((e) => console.log("  - " + e));
    process.exitCode = 1;
  } else {
    console.log("\nNo page errors.");
  }
  console.log("Takes written to " + OUT);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
