/**
 * PulseIQ UI audit — automated contrast + layout regression check.
 *
 * Runs the built app (vite preview, or any base URL) through two passes:
 *
 * 1. Contrast: every visible text element's resolved foreground is compared
 *    against its real rendered background (nearest ancestor that paints one,
 *    alpha-composited) at 1440px and 390px. Fails below WCAG AA — 4.5:1 for
 *    body text, 3:1 for large text (24px+, or 19px+ bold). CSS animations
 *    are disabled first so entrance transitions are audited at final state.
 *
 * 2. Layout: per route at 375 / 768 / 1280 / 1440 px — horizontal page
 *    overflow, clipped text (scrollWidth > clientWidth), and tap targets
 *    under 24px.
 *
 * Usage:
 *   node scripts/ui-audit.cjs                        # build + vite preview
 *   node scripts/ui-audit.cjs --base-url <url>       # audit a running app
 *
 * Exits 1 with a summary table when any violation is found.
 */
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn, execSync } = require("node:child_process");

const FRONTEND = path.resolve(__dirname, "..", "frontend");
// resolve playwright-core from the frontend install, not from scripts/
const requireFromFrontend = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = requireFromFrontend("playwright-core");
const REPORT = path.join(__dirname, "ui-audit-report.json");

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

const ROUTES = [
  { path: "/", name: "home" },
  { path: "/diagnose", name: "diagnose" },
  { path: "/live", name: "live" },
  { path: "/workflow/start", name: "workflow-start" },
  { path: "/workflow/session", name: "workflow-session" },
  { path: "/history", name: "history" },
  { path: "/agents", name: "agents" },
];

const CONTRAST_VIEWPORTS = [
  { width: 1440, height: 900, name: "1440" },
  { width: 390, height: 844, name: "390" },
];

const LAYOUT_VIEWPORTS = [
  { width: 375, height: 667, name: "375" },
  { width: 768, height: 1024, name: "768" },
  { width: 1280, height: 800, name: "1280" },
  { width: 1440, height: 900, name: "1440" },
];

function findChrome() {
  for (const p of CHROME_CANDIDATES) if (fs.existsSync(p)) return p;
  throw new Error("No Chrome/Edge found. Set EDGE_PATH to a Chromium-based browser.");
}

/* ---------- color math ---------- */

function relLuminance(r, g, b) {
  const lin = [r, g, b].map((v) => {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function parseColor(str) {
  const m = String(str).match(/rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\)/);
  if (!m) return null;
  let a = 1;
  if (m[4] !== undefined) a = m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
  return { r: +m[1], g: +m[2], b: +m[3], a };
}

function composite(over, under) {
  const a = over.a + under.a * (1 - over.a);
  if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
  const ch = (o, u) => Math.round((o * over.a + u * under.a * (1 - over.a)) / a);
  return { r: ch(over.r, under.r), g: ch(over.g, under.g), b: ch(over.b, under.b), a };
}

function contrastRatio(fg, bg) {
  const l1 = relLuminance(fg.r, fg.g, fg.b);
  const l2 = relLuminance(bg.r, bg.g, bg.b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/* ---------- page-side audit (serialized into the browser) ---------- */

function contrastAuditScript() {
  function parseColor(str) {
    const m = String(str).match(/rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\)/);
    if (!m) return null;
    let a = 1;
    if (m[4] !== undefined) a = m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return { r: +m[1], g: +m[2], b: +m[3], a };
  }
  function lum(c) {
    const lin = [c.r, c.g, c.b].map((v) => {
      v /= 255;
      return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  }
  function composite(o, u) {
    const a = o.a + u.a * (1 - o.a);
    if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
    const ch = (x, y) => Math.round((x * o.a + y * u.a * (1 - o.a)) / a);
    return { r: ch(o.r, u.r), g: ch(o.g, u.g), b: ch(o.b, u.b), a };
  }
  function ratio(a, b) {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }
  function backgroundOf(el) {
    let node = el;
    let acc = null; // accumulated translucent layers, closest element on top
    while (node && node !== document.documentElement) {
      const cs = getComputedStyle(node);
      // A node paints background-image OVER background-color, so both layers
      // must be stacked, not either/or.
      const solid = parseColor(cs.backgroundColor);
      const img =
        cs.backgroundImage && cs.backgroundImage !== "none" && cs.backgroundImage.includes("gradient")
          ? parseColor(cs.backgroundImage) // first color stop (page gradients are near-flat)
          : null;
      let nodeColor = null;
      if (img) nodeColor = solid ? composite(img, solid) : img;
      else if (solid) nodeColor = solid;
      if (nodeColor && nodeColor.a > 0) {
        acc = acc ? composite(acc, nodeColor) : nodeColor;
        if (acc.a >= 0.999) return acc;
      }
      node = node.parentElement;
    }
    const root = parseColor(getComputedStyle(document.documentElement).backgroundColor) ||
      { r: 255, g: 255, b: 255, a: 1 };
    return acc ? composite(acc, root) : root;
  }
  const violations = [];
  let sampled = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const el = walker.currentNode;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < 0.05) continue;
    // Decorative / presentation-only text is exempt from WCAG 1.4.3.
    if (el.getAttribute("aria-hidden") === "true") continue;
    // only elements with direct text
    const direct = [...el.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim().length > 0
    );
    if (!direct) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    const fg = parseColor(cs.color);
    if (!fg) continue;
    const bg = backgroundOf(el);
    sampled++;
    const r = ratio(fg, bg);
    const size = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 19 && bold);
    const required = large ? 3 : 4.5;
    if (r + 1e-6 < required) {
      violations.push({
        where: el.tagName.toLowerCase() +
          (el.className && typeof el.className === "string" ? "." + el.className.split(/\s+/).slice(0, 2).join(".") : ""),
        text: (el.textContent || "").trim().slice(0, 60),
        ratio: Math.round(r * 100) / 100,
        required,
      });
    }
  }
  return { violations, sampled };
}

function layoutAuditScript() {
  const issues = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 1) {
    issues.push({ kind: "page-overflow", detail: `scrollWidth ${doc.scrollWidth} > viewport ${window.innerWidth}` });
  }
  const all = document.querySelectorAll("body *");
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const hasDirectText = [...el.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim().length > 0
    );
    if (hasDirectText && el.scrollWidth > el.clientWidth + 1) {
      issues.push({
        kind: "clipped-text",
        detail: `<${el.tagName.toLowerCase()}> "${(el.textContent || "").trim().slice(0, 40)}"`,
      });
    }
    const role = el.getAttribute("role");
    if ((el.tagName === "A" || el.tagName === "BUTTON" || role === "button") && rect.width < 24 && rect.height < 24) {
      issues.push({ kind: "small-target", detail: `<${el.tagName.toLowerCase()}> ${Math.round(rect.width)}x${Math.round(rect.height)}` });
    }
  }
  return issues;
}

/* ---------- driver ---------- */

function parseArgs() {
  const args = process.argv.slice(2);
  const i = args.indexOf("--base-url");
  return i >= 0 ? { baseUrl: args[i + 1] } : { baseUrl: null };
}

function waitFor(url, timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const res = await fetch(url);
        if (res.ok) return resolve();
      } catch {}
      if (Date.now() - start > timeoutMs) return reject(new Error(`Server never answered at ${url}`));
      setTimeout(tick, 400);
    };
    tick();
  });
}

(async () => {
  const { baseUrl } = parseArgs();
  let server = null;
  let built = false;

  if (!baseUrl) {
    console.log("Building frontend (tsc -b && vite build)…");
    execSync("npm run build", { cwd: FRONTEND, stdio: "inherit" });
    built = true;
    server = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", "4173", "--strictPort"], {
      cwd: FRONTEND,
      stdio: "ignore",
      shell: process.platform === "win32",
    });
    await waitFor("http://127.0.0.1:4173/", 30000);
    console.log("vite preview ready on http://127.0.0.1:4173");
  }
  const base = baseUrl || "http://127.0.0.1:4173";

  try {
    const browser = await chromium.launch({
      executablePath: findChrome(),
      headless: true,
      args: ["--force-color-profile=srgb", "--disable-lcd-text"],
    });

    const violations = [];
    let sampledTotal = 0;

    for (const vp of CONTRAST_VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
      await page.emulateMedia({ reducedMotion: "reduce" });
      for (const route of ROUTES) {
        await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
        // Freeze animations/transitions so entrance states are audited at final values
        await page.addStyleTag({
          content: `*, *::before, *::after {
            animation: none !important; transition: none !important;
          }`,
        });
        await page.waitForTimeout(150);
        const out = await page.evaluate(`(${contrastAuditScript})()`);
        sampledTotal += out.sampled;
        for (const v of out.violations) violations.push({ viewport: vp.name, route: route.name, ...v });
      }
      await page.close();
    }

    const layoutIssues = [];
    for (const vp of LAYOUT_VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
      for (const route of ROUTES) {
        await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
        const issues = await page.evaluate(`(${layoutAuditScript})()`);
        for (const i of issues) layoutIssues.push({ viewport: vp.name, route: route.name, ...i });
      }
      await page.close();
    }

    await browser.close();

    fs.writeFileSync(
      REPORT,
      JSON.stringify({ generatedAt: new Date().toISOString(), base, sampledTotal, violations, layoutIssues }, null, 2)
    );

    console.log(`\nContrast: ${sampledTotal} text elements sampled across ${CONTRAST_VIEWPORTS.length} viewports × ${ROUTES.length} routes`);
    console.log(`Layout:   ${LAYOUT_VIEWPORTS.length} viewports × ${ROUTES.length} routes checked\n`);

    let failed = false;
    if (violations.length) {
      failed = true;
      console.log(`✗ Contrast violations (${violations.length}):`);
      for (const v of violations.slice(0, 25)) {
        console.log(`  [${v.viewport} ${v.route}] ${v.where} — ${v.ratio}:1 (needs ${v.required}:1) "${v.text}"`);
      }
      if (violations.length > 25) console.log(`  … and ${violations.length - 25} more (see ${REPORT})`);
    } else {
      console.log("✓ Contrast: no WCAG AA violations");
    }
    if (layoutIssues.length) {
      failed = true;
      console.log(`\n✗ Layout issues (${layoutIssues.length}):`);
      for (const i of layoutIssues.slice(0, 25)) {
        console.log(`  [${i.viewport} ${i.route}] ${i.kind}: ${i.detail}`);
      }
      if (layoutIssues.length > 25) console.log(`  … and ${layoutIssues.length - 25} more (see ${REPORT})`);
    } else {
      console.log("✓ Layout: no overflow, clipping, or undersized targets");
    }

    process.exit(failed ? 1 : 0);
  } finally {
    if (server) {
      try {
        server.kill();
        if (process.platform === "win32" && server.pid) {
          execSync(`taskkill /PID ${server.pid} /T /F`, { stdio: "ignore" });
        }
      } catch {}
    }
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
