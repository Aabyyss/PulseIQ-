/**
 * Light-mode screenshots for the LinkedIn post.
 *
 * Usage:
 *   1. backend  (.venv/Scripts/python -m uvicorn backend.api_server:app --port 8000)
 *   2. frontend (cd frontend && npm run dev)
 *   3. node scripts/capture-light-linkedin.cjs
 *
 * Drives the installed Edge (channel: "msedge"), same approach as
 * capture-screenshots.cjs, but forces LIGHT theme (pulseiq.theme=light)
 * and signs in with the shared E2E account.
 */
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const FRONTEND = path.resolve(__dirname, "..", "frontend");
const requireFromFrontend = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = requireFromFrontend("playwright-core");

const OUT = path.resolve(__dirname, "../docs/screenshots/linkedin");
const BASE = process.env.PULSEIQ_URL || "http://localhost:5173";
const VIEWPORT = { width: 1440, height: 940 };
const SCALE = 2;
const EMAIL = "e2e-verify@cardio.local";
const PASSWORD = "E2ePass123";

const errors = [];

async function settle(page, ms = 700) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(ms);
}

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file });
  console.log(`  ${name}  ${(fs.statSync(file).size / 1024).toFixed(0)} kB`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    colorScheme: "light",
  });
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  // Light theme before any app page paints.
  await page.addInitScript(() => {
    try {
      localStorage.setItem("pulseiq.theme", "light");
    } catch {}
  });

  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await settle(page, 600);
  await page.getByPlaceholder("name@hospital.org").fill(EMAIL);
  await page.getByPlaceholder("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /Sign in/i }).click();
  await page.waitForURL(/consultation|\/(?!login)/, { timeout: 20000 });
  await settle(page, 900);

  // 1 — Consultation, Quick consult mode, ready state.
  await page.goto(`${BASE}/consultation`, { waitUntil: "domcontentloaded" });
  await settle(page, 900);
  await shot(page, "linkedin-01-consultation.png");

  // 2 — Live line: transcript + concepts + body map.
  await page.locator("textarea").first().fill(
    "I get tight chest pain walking uphill that eases with rest, and it pains in the left side of my heart."
  );
  await page.getByRole("button", { name: /Submit line/i }).click();
  await page.getByText(/chest pain/i).first().waitFor({ timeout: 30000 });
  await settle(page, 1200);
  await shot(page, "linkedin-02-live-analysis.png");

  // 3 — History, Consultations tab with the saved visits.
  await page.goto(`${BASE}/history`, { waitUntil: "domcontentloaded" });
  await settle(page, 800);
  await page.getByRole("tab", { name: /Consultations/i }).click();
  await page.getByText("Ayesha Khan").first().waitFor({ timeout: 15000 });
  await settle(page, 900);
  await shot(page, "linkedin-03-history.png");

  // 4 — Agents registry (local AI stack).
  await page.goto(`${BASE}/agents`, { waitUntil: "domcontentloaded" });
  await settle(page, 900);
  await shot(page, "linkedin-04-agents.png");

  await browser.close();

  if (errors.length) {
    console.log("\nConsole errors observed while capturing:");
    errors.forEach((e) => console.log("  - " + e));
  } else {
    console.log("\nNo console errors.");
  }
  console.log("Screenshots written to " + OUT);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
