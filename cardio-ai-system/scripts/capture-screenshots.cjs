/**
 * Regenerates the documentation screenshots in docs/screenshots.
 *
 * Usage:
 *   1. start the backend        (.venv/Scripts/python -m uvicorn backend.api_server:app --port 8000)
 *   2. start the frontend       (cd frontend && npm run dev)
 *   3. install the driver once  (cd frontend && npm i --no-save playwright-core)
 *   4. node scripts/capture-screenshots.cjs
 *
 * It drives your installed Microsoft Edge, so no browser download is needed.
 */
const path = require("path");
const fs = require("fs");

let chromium;
try {
  chromium = require("playwright-core").chromium;
} catch {
  console.error(
    "playwright-core is not installed. Run:  cd frontend && npm i --no-save playwright-core"
  );
  process.exit(1);
}

const OUT = path.resolve(__dirname, "../docs/screenshots");
const BASE = process.env.PULSEIQ_URL || "http://localhost:5173";
const VIEWPORT = { width: 1440, height: 940 };
const SCALE = 1.5;

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

async function screen(page, chip) {
  await page.goto(`${BASE}/consultation`, { waitUntil: "domcontentloaded" });
  await settle(page);
  if (chip) {
    await page.getByRole("button", { name: chip, exact: true }).click();
  } else {
    await page.locator("textarea").first().fill("Mild palpitations after coffee, no chest pain.");
  }
  await page.getByRole("button", { name: /Run screening/i }).click();
  await page.getByText("Probability").waitFor({ timeout: 20000 });
  await settle(page, 800);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    colorScheme: "dark"
  });
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await settle(page, 1200);
  await shot(page, "01-overview.png");

  await page.goto(`${BASE}/consultation`, { waitUntil: "domcontentloaded" });
  await settle(page);
  await shot(page, "02-consultation-quick.png");

  // A manual line shows transcript, concepts and the body map instantly.
  await page
    .locator("textarea")
    .first()
    .fill("I get tight chest pain walking uphill that eases with rest, and it pains in the left side of my heart.");
  await page.getByRole("button", { name: /Submit line/i }).click();
  await settle(page, 1600);
  await shot(page, "03-consultation-live.png");

  // Running a screening also seeds the history view.
  await screen(page, "Exertional chest pressure");
  await shot(page, "04-consultation-screening.png");

  await page.goto(`${BASE}/history`, { waitUntil: "domcontentloaded" });
  await settle(page, 900);
  await shot(page, "05-history.png");

  await page.goto(`${BASE}/agents`, { waitUntil: "domcontentloaded" });
  await settle(page, 900);
  await shot(page, "06-agent-registry.png");

  const mobile = await browser.newContext({
    viewport: { width: 414, height: 896 },
    deviceScaleFactor: 2,
    colorScheme: "dark"
  });
  const phone = await mobile.newPage();
  await phone.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await settle(phone, 1200);
  await shot(phone, "09-mobile-overview.png");

  await mobile.close();
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
