/* Temp capture script: real app screenshots for docs/demo (deleted after use). */
const { chromium } = require("playwright-core");
const path = require("path");
const fs = require("fs");

const OUT = path.resolve(__dirname, "../docs/screenshots");
const BASE = "http://localhost:5173";

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });

  // 1. Home
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, "01-home.png"), fullPage: true });
  console.log("01-home done");

  // 2. Diagnose with result
  await page.goto(BASE + "/diagnose", { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  await page.locator("textarea").first().fill("I feel chest pressure and shortness of breath when walking upstairs, with occasional dizziness.");
  await page.locator('button:has-text("Run screening")').click();
  await page.waitForSelector("text=Screening result", { timeout: 30000 });
  await page.waitForTimeout(1600);
  await page.screenshot({ path: path.join(OUT, "02-diagnose-result.png"), fullPage: true });
  console.log("02-diagnose done");

  // 3. AI guidance
  await page.locator('button:has-text("Generate AI guidance")').click();
  await page.waitForSelector("text=AI Guidance", { timeout: 30000 });
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "03-ai-guidance.png"), fullPage: true });
  console.log("03-guidance done");

  // 4. Live copilot
  await page.goto(BASE + "/live", { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);
  await page.locator('textarea[placeholder*="Type a transcript"]').fill("I have crushing chest pain and it goes into my left arm when I climb stairs.");
  await page.locator('button:has-text("Send line")').click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(OUT, "04-live-copilot.png"), fullPage: true });
  console.log("04-live done");

  // 5. Workflow session
  await page.goto(BASE + "/workflow/session", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await page.locator('input[placeholder="Patient name"]').fill("Demo Patient");
  await page.locator('input[placeholder="Age"]').fill("58");
  await page.locator('input[placeholder="Gender"]').fill("Male");
  await page.locator('input[placeholder="Doctor name"]').fill("Dr. A. Carter");
  await page.locator('input[placeholder="Chief complaint"]').fill("Exertional chest pressure");
  await page.locator('textarea[placeholder*="Manual transcript"]').fill("Patient reports chest tightness on exertion, relieved by rest. No syncope.");
  await page.locator('button:has-text("Submit transcript")').click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(OUT, "05-workflow.png"), fullPage: true });
  console.log("05-workflow done");

  // 6. History
  await page.goto(BASE + "/history", { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "06-history.png") });
  console.log("06-history done");

  // 7. Agents
  await page.goto(BASE + "/agents", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "07-agents.png"), fullPage: true });
  console.log("07-agents done");

  await browser.close();
  console.log("ALL CAPTURED ->", OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
