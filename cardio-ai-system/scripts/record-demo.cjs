/**
 * Records the PulseIQ demo video (light mode, 1440x940) in two takes:
 *   take 1 — login → consultation → live lines (English + Urdu) → concepts/body map/risk
 *   take 2 — (after the LLM save completes) "Visit saved" → History → Consultations tab
 * The slow on-device LLM report (~36s) is CUT between the takes; the converter
 * (scripts/convert-demo.cjs) concatenates them so the video has no dead air.
 *
 * Usage:
 *   1. backend (:8000) + frontend (:5173) running
 *   2. node scripts/record-demo.cjs
 * Outputs: docs/demo/raw-take1.webm, docs/demo/raw-take2.webm
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
const EMAIL = "e2e-verify@cardio.local";
const PASSWORD = "E2ePass123";

const errors = [];

function stamp(ms) {
  return `[${(ms / 1000).toFixed(1)}s]`;
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500); // let the viewer see the sign-in screen
  await page.getByPlaceholder("name@hospital.org").fill(EMAIL);
  await page.getByPlaceholder("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /Sign in/i }).click();
  await page.waitForURL((u) => !String(u).includes("/login"), { timeout: 20000 });
  await page.waitForTimeout(2500); // overview page dwell
  await page.goto(`${BASE}/consultation`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
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
  const ctx1 = await browser.newContext({
    viewport: VIEWPORT,
    colorScheme: "light",
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  const p1 = await ctx1.newPage();
  p1.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  const t0 = Date.now();
  await login(p1);

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
  await p1.getByText(/chest pain/i).first().waitFor({ timeout: 20000 }); // instant ack
  console.log(stamp(Date.now() - t0), "line 1 ack");
  await p1
    .getByText(/High risk|Moderate risk/i)
    .first()
    .waitFor({ timeout: 45000 }) // async LLM analysis (fast when Ollama is paused)
    .catch(() => console.log("  (risk pill not updated in time — continuing)"));
  await p1.waitForTimeout(2000);

  // Line 2 — Urdu: chest pain + sweating.
  await p1.locator("textarea").first().fill("دل میں درد ہے اور پسینہ آ رہا ہے");
  await p1.getByRole("button", { name: /Submit line/i }).click();
  await p1.getByText(/sweating/i).first().waitFor({ timeout: 20000 });
  console.log(stamp(Date.now() - t0), "line 2 ack (Urdu)");
  await p1.waitForTimeout(6000); // dwell on concepts + body map

  // Fill visit details so the saved record carries a name.
  await p1.getByRole("tab", { name: /Full consult/i }).click();
  await p1.waitForTimeout(800);
  await p1.getByPlaceholder(/patient name/i).fill("Demo Patient");
  await p1.getByPlaceholder(/age/i).fill("58");
  await p1.waitForTimeout(600);

  await p1.getByRole("button", { name: /Save visit & export PDF/i }).click();
  console.log(stamp(Date.now() - t0), "save clicked — take 1 ends here (LLM wait is cut)");
  await p1.waitForTimeout(1500); // show the "Saving visit…" state briefly
  await ctx1.close(); // flush + finalize take 1 video
  await p1.video().saveAs(path.join(OUT, "raw-take1.webm"));

  // ---------------------------------------------------------------- take 2
  const ctx2 = await browser.newContext({
    viewport: VIEWPORT,
    colorScheme: "light",
    recordVideo: { dir: OUT, size: VIEWPORT },
    storageState: undefined,
  });
  const p2 = await ctx2.newPage();
  p2.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

  // Resume "after the save": fresh session, History with the just-saved visit.
  await p2.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await p2.getByPlaceholder("name@hospital.org").fill(EMAIL);
  await p2.getByPlaceholder("Password").fill(PASSWORD);
  await p2.getByRole("button", { name: /Sign in/i }).click();
  await p2.waitForURL((u) => !String(u).includes("/login"), { timeout: 20000 });
  await p2.goto(`${BASE}/history`, { waitUntil: "domcontentloaded" });
  await p2.waitForTimeout(1200);
  await p2.getByRole("tab", { name: /Consultations/i }).click();
  await p2.getByText("Demo Patient").first().waitFor({ timeout: 20000 });
  console.log(stamp(Date.now() - t0), "take 2: history shows the saved visit");
  await p2.waitForTimeout(6000); // dwell on the saved visit card

  await ctx2.close();
  await p2.video().saveAs(path.join(OUT, "raw-take2.webm"));
  await browser.close();

  if (errors.length) {
    console.log("\nPage errors observed:");
    errors.forEach((e) => console.log("  - " + e));
  } else {
    console.log("\nNo page errors.");
  }
  console.log("Takes written to " + OUT);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
