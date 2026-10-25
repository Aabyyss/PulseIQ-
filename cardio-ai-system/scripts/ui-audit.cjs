/**
 * PulseIQ UI audit — automated contrast + layout regression check.
 *
 * Runs the built app (vite preview, or any base URL) through three passes:
 *
 * 1. Contrast: every visible text element's resolved foreground is compared
 *    against its real rendered background (nearest ancestor that paints one,
 *    alpha-composited) at laptop, tablet and phone widths, in **both themes**. Fails below
 *    WCAG AA — 4.5:1 for body text, 3:1 for large text (24px+, or 19px+ bold).
 *    CSS animations are disabled first so entrance transitions are audited at
 *    final state. The theme is applied through the stored preference before
 *    the page boots, and the sweep asserts it took effect: an emulation that
 *    silently failed would audit the dark palette twice and call it light.
 *
 * 2. Layout: per route at phone, tablet, laptop and desktop widths (320 through
 *    2560 px) — horizontal page overflow, clipped text (scrollWidth >
 *    clientWidth), and tap targets under 24px. 320px is WCAG 1.4.10's reflow
 *    width (1280px at 400% zoom), and the desktop sizes are the ones a real
 *    machine reports (1366x768 and 1536x864 are the most common laptop panels),
 *    because a layout that only holds at 1440 is not responsive.
 *
 * 3. States: the screens a route cannot show on first paint. The account menu,
 *    the "Full consult" tab and the "Consultations" history tab are opened at
 *    1440px and 390px in both themes, and the rendered state — not the route it
 *    sits on — is audited for contrast and layout. A state that fails to open
 *    is a failure of its own: auditing the page under the name of a panel that
 *    never appeared is the same blind spot as auditing /login as the workspace.
 *
 * All three passes sign in first. They used to run signed out, which meant every
 * protected route quietly redirected to /login and the sweep audited the same
 * form eight times — green, and blind to the workspace. While signed in, each
 * workspace route is also required to carry the real shell: the dock with its
 * active item and the account menu. A page that renders without them is a
 * different page from the one a clinician uses, whatever its URL says.
 *
 * Usage:
 *   node scripts/ui-audit.cjs                        # build + vite preview
 *   node scripts/ui-audit.cjs --base-url <url>       # audit a running app
 *   node scripts/ui-audit.cjs --require-sign-in      # fail instead of degrading
 *
 * --require-sign-in is what CI uses. Without it, an unreachable backend makes
 * the sweep fall back to the public pages and still exit 0 — honest, but a
 * green build that never looked at the workspace. With it, a backend that is
 * missing, unreachable, or drops the session mid-sweep fails the job.
 *
 * How the sweep is signed in is recorded, too: every page load is checked
 * against the route that was asked for, so a redirect to /login can never be
 * audited as if it were the page it replaced (ADR-028).
 *
 * The preview server is spawned as `node vite.js preview`, not through `npx`,
 * so the recorded PID is the process that holds the port: killing the npx
 * wrapper left the real server listening, and the next run's `--strictPort`
 * then failed to start — a leak that only showed up on the second run.
 *
 * Env: PULSEIQ_AUDIT_EMAIL / PULSEIQ_AUDIT_PASSWORD override the demo account
 * (registered on the fly when it does not exist yet). Without a reachable
 * backend the sweep says so and audits the public pages only.
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

// `dock` is the accessible name of the dock item that must be current on the
// route (the same string as NAV[].label in app-shell.tsx). Pages that are not a
// dock destination carry `dock: null`: they must still render the dock, but
// nothing may claim to be the current page there.
const ROUTES = [
  { path: "/", name: "home", dock: "Overview" },
  { path: "/consultation", name: "consultation", dock: "Consultation" },
  { path: "/medications", name: "medications", dock: "Medication review" },
  { path: "/history", name: "history", dock: "History & visits" },
  { path: "/notes", name: "notes", dock: "My notes" },
  { path: "/patients", name: "patients", dock: "Patients" },
  { path: "/guidance", name: "guidance", dock: "Guidance" },
  { path: "/security", name: "security", dock: "Security" },
  { path: "/agents", name: "agents", dock: "Agent registry" },
  // /thank-you is audited because a save lands here, but it is not a dock
  // destination.
  { path: "/thank-you", name: "thank-you", dock: null },
  { path: "/privacy", name: "privacy", dock: null },
  { path: "/terms", name: "terms", dock: null },
];

// The palette is class-based (`html.dark`), so the stored preference is what a
// returning clinician sees. Both are audited: light mode is the one this repo
// has historically regressed (`light-theme.css` overrides the dark defaults),
// and dark is the one the launch default paints.
const THEMES = ["dark", "light"];

// The two widths a state is opened at: a laptop and a phone. The dock and the
// account menu are the same components at both, but the phone is where a menu
// can overflow the viewport and where the dock scrolls.
const STATE_VIEWPORTS = [
  { width: 1440, height: 900, name: "1440" },
  { width: 390, height: 844, name: "390" },
];

const CONTRAST_VIEWPORTS = [
  { width: 1440, height: 900, name: "1440" },
  { width: 1366, height: 768, name: "1366" },
  // Tablet portrait: the width where the phone bar is still in charge and a
  // 9-item row used to be squeezed rather than split.
  { width: 820, height: 1180, name: "820" },
  { width: 390, height: 844, name: "390" },
];

const LAYOUT_VIEWPORTS = [
  // WCAG 1.4.10 reflow: 320 CSS px is 1280 px at 400% zoom.
  { width: 320, height: 640, name: "320" },
  { width: 375, height: 667, name: "375" },
  { width: 768, height: 1024, name: "768" },
  { width: 1024, height: 768, name: "1024" },
  { width: 1280, height: 720, name: "1280" },
  { width: 1366, height: 768, name: "1366" },
  { width: 1440, height: 900, name: "1440" },
  { width: 1536, height: 864, name: "1536" },
  { width: 1920, height: 1080, name: "1920" },
  { width: 2560, height: 1440, name: "2560" },
];

/**
 * Screens that only exist after an interaction. `open` performs the user
 * gesture; `witness` is what proves the state arrived. Both run inside the
 * sweep so a renamed tab or a menu that stopped opening fails the audit rather
 * than quietly auditing the page behind it.
 */
const STATES = [
  {
    name: "account-menu",
    route: ROUTES.find((r) => r.name === "home"),
    open: (page) => page.getByRole("button", { name: "Account menu" }).click(),
    witness: (page) => page.getByRole("menu").waitFor({ timeout: 5000 }),
  },
  {
    name: "consultation-full-tab",
    route: ROUTES.find((r) => r.name === "consultation"),
    open: (page) => page.getByRole("tab", { name: "Full consult" }).click(),
    witness: (page) =>
      page.getByRole("tab", { name: "Full consult", selected: true }).waitFor({ timeout: 5000 }),
  },
  {
    name: "history-consultations-tab",
    route: ROUTES.find((r) => r.name === "history"),
    open: (page) => page.getByRole("tab", { name: "Consultations" }).click(),
    witness: (page) =>
      page.getByRole("tab", { name: "Consultations", selected: true }).waitFor({ timeout: 5000 }),
  },
  {
    // The sheet is the only way to reach four destinations on a phone. It is a
    // modal, so it also exercises the contrast of the backdrop-darkened page.
    name: "more-sheet",
    route: ROUTES.find((r) => r.name === "home"),
    viewports: ["390"],
    open: (page) => page.getByRole("button", { name: "More destinations" }).click(),
    witness: async (page) => {
      const sheet = page.getByRole("dialog", { name: "More destinations" });
      await sheet.waitFor({ timeout: 5000 });
      const reached = await sheet.locator("a").count();
      if (reached < 4) throw new Error(`the sheet reached only ${reached} destinations`);
    },
  },
  {
    // The palette is a modal with a text field, a listbox and live filtering —
    // the densest surface in the app, and the one most likely to inherit an
    // unchecked colour from a hover state.
    name: "command-palette",
    route: ROUTES.find((r) => r.name === "home"),
    open: (page) => page.getByRole("button", { name: "Search destinations" }).click(),
    witness: async (page) => {
      await page.getByRole("dialog", { name: "Command palette" }).waitFor({ timeout: 5000 });
      await page.getByRole("combobox", { name: "Search destinations" }).fill("med");
      await page.getByRole("option").first().waitFor({ timeout: 5000 });
    },
  },
  {
    // The switch, not the stored preference: this is the path a clinician
    // actually takes, and it proves the toggle flips the palette live.
    name: "theme-switch",
    route: ROUTES.find((r) => r.name === "home"),
    open: async (page) => {
      const before = await page.evaluate(() => document.documentElement.classList.contains("dark"));
      await page.getByRole("switch").click();
      await page.waitForFunction(
        (was) => document.documentElement.classList.contains("dark") !== was,
        before,
        { timeout: 5000 }
      );
    },
    witness: async (page) => {
      await page.getByRole("switch", { name: /Switch to (light|dark) mode/ }).waitFor({ timeout: 5000 });
    },
  },
];

/**
 * WCAG 1.4.12: readers may override spacing to these values, and nothing may
 * disappear. Applied as a stylesheet rather than by changing the design, so the
 * sweep tests the same thing a browser extension would do to the running app.
 */
const TEXT_SPACING_CSS = `
  * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
  p { margin-bottom: 2em !important; }
`;

const TEXT_SPACING_VIEWPORTS = [
  { width: 1440, height: 900, name: "1440" },
  { width: 390, height: 844, name: "390" },
];

const AUDIT_EMAIL = process.env.PULSEIQ_AUDIT_EMAIL || "demo@cardio.local";
const AUDIT_PASSWORD = process.env.PULSEIQ_AUDIT_PASSWORD || "DemoPass123";

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
    // SVG text is laid out by its own coordinate system; scrollWidth/clientWidth
    // do not describe whether a label overflows its drawing, so the anatomy
    // figures reported every label as clipped at every width.
    if (el.namespaceURI === "http://www.w3.org/2000/svg" || el.closest("svg")) continue;
    // An ellipsis is the layout telling the reader the text continues; the
    // check is for text cut off with no indication at all.
    if (cs.textOverflow === "ellipsis") continue;
    const hasDirectText = [...el.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim().length > 0
    );
    if (hasDirectText && el.scrollWidth > el.clientWidth + 1) {
      issues.push({
        kind: "clipped-text",
        detail: `<${el.tagName.toLowerCase()}> "${(el.textContent || "").trim().slice(0, 40)}"`,
      });
    }
    // A fixed-height box with hidden overflow can cut a line in half, which the
    // width check above cannot see. Line clamping is deliberate truncation and
    // is exempt for the same reason an ellipsis is.
    const clamped = cs.webkitLineClamp && cs.webkitLineClamp !== "none";
    if (
      hasDirectText &&
      !clamped &&
      /hidden|clip/.test(cs.overflowY) &&
      el.scrollHeight > el.clientHeight + 1
    ) {
      issues.push({
        kind: "clipped-height",
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

/**
 * The shell a signed-in route has to carry. Returns what is missing.
 *
 * A route can render its own content and still not be the workspace: a broken
 * dock, a lost session and a page rendered outside `<AppShell>` all look like
 * "some HTML at the right URL". The dock's current item is checked by name so
 * `/medications` cannot pass with `Home` highlighted, and the account menu
 * proves the page knows who is signed in.
 */
function shellAuditScript(expectedDock) {
  const missing = [];
  const nav = document.querySelector('nav[aria-label="Workspace"]');
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  if (!nav) {
    missing.push("the workspace navigation");
  } else {
    const items = [...nav.querySelectorAll("a[aria-label]")];
    if (items.length < 9) missing.push(`navigation destinations (${items.length}/9)`);
    const current = nav.querySelector('[aria-current="page"]');
    if (expectedDock && !current) missing.push("the active destination");
    else if (expectedDock && current.getAttribute("aria-label") !== expectedDock) {
      missing.push(
        `the active destination (${"\u201c"}${current.getAttribute("aria-label")}${"\u201d"} instead of ${"\u201c"}${expectedDock}${"\u201d"})`
      );
    }
    // The adaptive shell is two presentations of one list. Counting links in
    // the DOM proves neither: hidden items count too. At `lg` every destination
    // must be on screen and the overflow control gone; below it, exactly five
    // destinations and a reachable More control.
    const shown = items.filter(visible);
    const more = [...nav.querySelectorAll("button[aria-label]")].find(
      (el) => el.getAttribute("aria-label") === "More destinations"
    );
    if (window.innerWidth >= 1024) {
      if (shown.length !== items.length) {
        missing.push(`the rail (${shown.length}/${items.length} destinations visible at ${window.innerWidth}px)`);
      }
      if (more && visible(more)) missing.push("the rail drew the phone More control");
    } else {
      if (shown.length !== 5) {
        missing.push(`a five-destination bar (${shown.length} visible at ${window.innerWidth}px)`);
      }
      if (!more || !visible(more)) missing.push("the More control that reaches the other destinations");
    }
  }
  if (!document.querySelector('[aria-label="Account menu"]')) missing.push("the account menu");
  return missing;
}

/* ---------- driver ---------- */

/** The path a route should leave the browser on, ignoring one trailing slash. */
function normalisePath(value) {
  const trimmed = String(value).replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

function parseArgs() {
  const args = process.argv.slice(2);
  const i = args.indexOf("--base-url");
  return {
    baseUrl: i >= 0 ? args[i + 1] : null,
    // CI turns the signed-out fallback into a failure: the fallback is only
    // useful on a laptop where no backend is running.
    requireSignIn: args.includes("--require-sign-in") || process.env.PULSEIQ_AUDIT_REQUIRE_SIGN_IN === "1",
  };
}

/**
 * Put the theme in the stored preference before the document boots, so the
 * boot snippet in index.html paints the right palette on the first frame — the
 * same path a returning clinician takes. Setting the class after load would
 * audit a page that had already rendered in the other theme.
 */
async function primeTheme(page, theme) {
  await page.addInitScript((value) => {
    try {
      localStorage.setItem("pulseiq.theme", value);
    } catch {
      /* storage unavailable — the sweep's theme check will fail, and should */
    }
  }, theme);
}

function oppositeOf(theme) {
  return theme === "dark" ? "light" : "dark";
}

/** Whether the boot snippet actually applied the theme we asked for. */
async function themeApplied(page, theme) {
  return page.evaluate(
    (want) => document.documentElement.classList.contains("dark") === (want === "dark"),
    theme
  );
}

/**
 * Make sure the audit account exists, so the sweep can see the workspace.
 * Returns false when no backend answers — the caller then audits the public
 * pages and says so, rather than reporting the sign-in form as a clean app.
 */
async function ensureAuditAccount(base) {
  const post = (route, body) =>
    fetch(`${base}/api${route}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  try {
    const login = await post("/auth/login", { email: AUDIT_EMAIL, password: AUDIT_PASSWORD });
    if (login.ok) return true;
    const register = await post("/auth/register", {
      email: AUDIT_EMAIL,
      password: AUDIT_PASSWORD,
      name: "Audit User",
    });
    return register.ok;
  } catch {
    return false;
  }
}

/** Sign the page in once; the session then persists for every route in it. */
async function signIn(page, base, signedIn) {
  if (!signedIn) return false;
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => {});
  const notice = page.getByRole("button", { name: "Got it" });
  if (await notice.isVisible().catch(() => false)) await notice.click();
  await page.locator('input[type="email"]').fill(AUDIT_EMAIL).catch(() => {});
  await page.locator('input[type="password"]').fill(AUDIT_PASSWORD).catch(() => {});
  await page.getByRole("button", { name: "Sign in", exact: true }).click().catch(() => {});
  await page
    .waitForURL((url) => !new URL(url).pathname.startsWith("/login"), { timeout: 15000 })
    .catch(() => {});
  return !new URL(page.url()).pathname.startsWith("/login");
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
  const { baseUrl, requireSignIn } = parseArgs();
  let server = null;
  let built = false;

  if (!baseUrl) {
    console.log("Building frontend (tsc -b && vite build)…");
    execSync("npm run build", { cwd: FRONTEND, stdio: "inherit" });
    built = true;
    // `node vite.js` directly: with `npx … { shell: true }` the PID kept here
    // belongs to the wrapper, so the cleanup below killed the wrapper and left
    // the server holding 4173.
    const viteBin = path.join(FRONTEND, "node_modules", "vite", "bin", "vite.js");
    server = spawn(process.execPath, [viteBin, "preview", "--host", "127.0.0.1", "--port", "4173", "--strictPort"], {
      cwd: FRONTEND,
      stdio: "ignore",
    });
    await waitFor("http://127.0.0.1:4173/", 30000);
    console.log("vite preview ready on http://127.0.0.1:4173");
  }
  const base = baseUrl || "http://127.0.0.1:4173";

  try {
    const signedIn = await ensureAuditAccount(base);
    if (!signedIn) {
      if (requireSignIn) {
        // Thrown, not process.exit'd, so the `finally` below still stops the
        // preview server this run started.
        throw new Error(
          `Sign-in required but no backend answered at ${base}/api/auth/login. ` +
            "Start the API (port 8000) or drop --require-sign-in to audit the public pages."
        );
      }
      console.log("! No backend behind this URL — auditing public pages only.");
    }

    const browser = await chromium.launch({
      executablePath: findChrome(),
      headless: true,
      args: ["--force-color-profile=srgb", "--disable-lcd-text"],
    });

    const violations = [];
    const layoutIssues = [];
    const redirects = [];
    const themeIssues = [];
    const shellIssues = [];
    const stateIssues = [];
    let sampledTotal = 0;
    let themeChecks = 0;
    const sampledByTheme = Object.fromEntries(THEMES.map((theme) => [theme, 0]));

    // Where each page actually landed. A redirect to /login is the failure this
    // flag exists to catch: the sweep would otherwise measure the sign-in form
    // under the name of the route it was asked for.
    const recordLanding = (page, route, viewport, pass) => {
      const landed = new URL(page.url()).pathname;
      if (normalisePath(landed) === normalisePath(route.path)) return;
      redirects.push({ viewport, route: route.name, pass, expected: route.path, landed });
    };
    const assertSession = (page, viewport, pass) => {
      if (!requireSignIn) return;
      const landed = new URL(page.url()).pathname;
      if (landed.startsWith("/login")) {
        throw new Error(`${pass} pass at ${viewport}px: session lost (landed on ${landed}).`);
      }
    };

    // The theme is only audited if it really applied: a preference the boot
    // snippet ignored would make both passes the same palette under two names.
    const checkTheme = async (page, theme, where) => {
      themeChecks += 1;
      if (await themeApplied(page, theme)) return;
      themeIssues.push({ theme, where });
    };

    // Signed out there is no account menu to require, so the shell check is a
    // workspace check by definition.
    const checkShell = async (page, route, where) => {
      if (!signedIn) return;
      const missing = await page.evaluate(`(${shellAuditScript})(${JSON.stringify(route.dock)})`);
      if (missing.length) shellIssues.push({ route: route.name, where, missing });
    };

    // Entrance transitions are audited at their final values, in every pass.
    const freeze = `*, *::before, *::after {
      animation: none !important; transition: none !important;
    }`;

    for (const theme of THEMES) {
      for (const vp of CONTRAST_VIEWPORTS) {
        const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
        await primeTheme(page, theme);
        // The system preference is set to the *other* theme on purpose: the
        // boot snippet prefers the stored value, so a page that still lands on
        // the requested palette proves it read what we stored. Emulating the
        // same theme here would let both paths agree and hide a broken one.
        await page.emulateMedia({ reducedMotion: "reduce", colorScheme: oppositeOf(theme) });
        await signIn(page, base, signedIn);
        await checkTheme(page, theme, `${vp.name}px sign-in`);
        assertSession(page, vp.name, `contrast/${theme}`);
        for (const route of ROUTES) {
          await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
          recordLanding(page, route, vp.name, `contrast/${theme}`);
          await checkTheme(page, theme, `${vp.name}px ${route.name}`);
          await checkShell(page, route, `contrast/${theme} ${vp.name}`);
          await page.addStyleTag({ content: freeze });
          await page.waitForTimeout(150);
          const out = await page.evaluate(`(${contrastAuditScript})()`);
          sampledTotal += out.sampled;
          sampledByTheme[theme] += out.sampled;
          for (const v of out.violations) {
            violations.push({ theme, viewport: vp.name, route: route.name, ...v });
          }
        }
        await page.close();
      }
    }

    // Layout does not depend on the palette, so one theme covers it: the width
    // ladder is what a layout bug shows up on.
    for (const vp of LAYOUT_VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
      await signIn(page, base, signedIn);
      assertSession(page, vp.name, "layout");
      for (const route of ROUTES) {
        await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
        recordLanding(page, route, vp.name, "layout");
        await checkShell(page, route, `layout ${vp.name}`);
        const issues = await page.evaluate(`(${layoutAuditScript})()`);
        for (const i of issues) layoutIssues.push({ viewport: vp.name, route: route.name, ...i });
      }
      await page.close();
    }

    // Text-spacing: the same layout pass with the reader's overrides applied.
    // 1.4.12 is a requirement on the page, not on a stylesheet we control, so
    // the sweep applies what a reader may apply and re-runs the clipping and
    // overflow checks.
    const textSpacingIssues = [];
    for (const vp of TEXT_SPACING_VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
      await signIn(page, base, signedIn);
      assertSession(page, vp.name, "text-spacing");
      for (const route of ROUTES) {
        await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
        recordLanding(page, route, vp.name, "text-spacing");
        await page.addStyleTag({ content: TEXT_SPACING_CSS });
        await page.waitForTimeout(60);
        for (const issue of await page.evaluate(`(${layoutAuditScript})()`)) {
          textSpacingIssues.push({ viewport: vp.name, route: route.name, ...issue });
        }
      }
      await page.close();
    }

    // Installability and the offline shell. These are properties of the built
    // bundle (manifest, worker, cached shell), not of a route, and none of them
    // are visible in a contrast sweep. Preview serves the production build, so
    // this is the same bundle a browser would install.
    const pwaIssues = [];
    {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      const context = page.context();
      try {
        await page.goto(base + "/", { waitUntil: "networkidle", timeout: 30000 });
        const manifest = await page.evaluate(async () => {
          const link = document.querySelector('link[rel="manifest"]');
          if (!link) return { error: "no manifest link" };
          const href = link.getAttribute("href");
          const response = await fetch(href);
          if (!response.ok) return { error: `manifest HTTP ${response.status}` };
          return { href, json: await response.json() };
        });
        if (manifest.error) {
          pwaIssues.push(manifest.error);
        } else {
          const m = manifest.json || {};
          if (!m.name || !m.short_name) pwaIssues.push("manifest has no name/short_name");
          if (!m.start_url) pwaIssues.push("manifest has no start_url");
          if (!["standalone", "fullscreen", "minimal-ui", "window-controls-overlay"].includes(m.display)) {
            pwaIssues.push(`manifest display is ${m.display}`);
          }
          const sizes = (m.icons || []).map((icon) => icon.sizes);
          if (!sizes.includes("192x192") || !sizes.includes("512x512")) {
            pwaIssues.push(`manifest icons are ${sizes.join(", ") || "missing"}`);
          }
          for (const icon of m.icons || []) {
            const status = await page.evaluate(async (src) => (await fetch(src)).status, icon.src);
            if (status !== 200) pwaIssues.push(`icon ${icon.src} answered ${status}`);
          }
        }

        const worker = await page.evaluate(async () => {
          if (!("serviceWorker" in navigator)) return { error: "no service worker support" };
          const registration = await Promise.race([
            navigator.serviceWorker.ready,
            new Promise((resolve) => setTimeout(() => resolve(null), 10000)),
          ]);
          return registration ? { scope: registration.scope, active: Boolean(registration.active) } : { error: "worker never became ready" };
        });
        if (worker.error) {
          pwaIssues.push(worker.error);
        } else if (!worker.active) {
          pwaIssues.push("service worker registered without an active worker");
        }

        // The point of the worker: a route opened with no network still renders
        // the app rather than the browser's offline error.
        await context.setOffline(true);
        await page.goto(base + "/history", { waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => {});
        const offlineOk = await page
          .evaluate(() => Boolean(document.querySelector("#root") && document.body.innerText.trim().length > 0))
          .catch(() => false);
        if (!offlineOk) pwaIssues.push("offline navigation did not render the cached shell");
        await context.setOffline(false);
      } catch (error) {
        pwaIssues.push(`PWA pass failed: ${String(error.message || error).split("\n")[0]}`);
      } finally {
        await context.setOffline(false).catch(() => {});
        await page.close();
      }
    }

    // The states a route cannot show on first paint. Each one is opened and
    // proved — a tab that never switched, or a menu that never rendered, is
    // recorded as its own failure instead of auditing the page behind it.
    let statesAudited = 0;
    // A state that only exists in one presentation (the phone More sheet) says
    // which widths it is opened at; everything else is opened at both.
    const expectedStates = STATES.reduce(
      (count, state) => count + (state.viewports ? state.viewports.length : STATE_VIEWPORTS.length),
      0
    ) * THEMES.length;
    if (signedIn) {
      for (const theme of THEMES) {
        for (const state of STATES) {
          const viewports = STATE_VIEWPORTS.filter(
            (vp) => !state.viewports || state.viewports.includes(vp.name)
          );
          for (const vp of viewports) {
            const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
            const where = `${state.name} @ ${vp.name}px ${theme}`;
            try {
              await primeTheme(page, theme);
              await page.emulateMedia({ reducedMotion: "reduce", colorScheme: oppositeOf(theme) });
              await signIn(page, base, signedIn);
              await page.goto(base + state.route.path, { waitUntil: "networkidle", timeout: 30000 });
              recordLanding(page, state.route, vp.name, `state:${state.name}`);
              await checkTheme(page, theme, where);
              await checkShell(page, state.route, where);
              await page.addStyleTag({ content: freeze });
              await state.open(page);
              await state.witness(page);
              await page.waitForTimeout(120);
              const out = await page.evaluate(`(${contrastAuditScript})()`);
              sampledTotal += out.sampled;
              sampledByTheme[theme] += out.sampled;
              for (const v of out.violations) {
                violations.push({ theme, viewport: vp.name, route: state.name, state: state.name, ...v });
              }
              for (const i of await page.evaluate(`(${layoutAuditScript})()`)) {
                layoutIssues.push({ theme, viewport: vp.name, route: state.name, state: state.name, ...i });
              }
              statesAudited += 1;
            } catch (err) {
              stateIssues.push({
                state: state.name,
                theme,
                viewport: vp.name,
                error: String(err.message || err).split("\n")[0],
              });
            } finally {
              await page.close();
            }
          }
        }
      }
    }

    await browser.close();

    fs.writeFileSync(
      REPORT,
      JSON.stringify(
        {
          generatedAt: new Date().toISOString(),
          base,
          signedIn,
          requireSignIn,
          themes: THEMES,
          sampledTotal,
          sampledByTheme,
          themeChecks,
          statesAudited,
          pwaIssues,
          violations,
          layoutIssues,
          textSpacingIssues,
          redirects,
          themeIssues,
          shellIssues,
          stateIssues,
        },
        null,
        2
      )
    );

    console.log(
      `\nContrast: ${sampledTotal} text elements sampled across ${CONTRAST_VIEWPORTS.length} viewports × ${ROUTES.length} routes × ${THEMES.length} themes` +
        (signedIn ? ` (${THEMES.map((t) => `${t} ${sampledByTheme[t]}`).join(", ")})` : "")
    );
    console.log(
      `Layout:   ${LAYOUT_VIEWPORTS.length} viewports × ${ROUTES.length} routes checked` +
        (signedIn ? " (signed in)" : " (signed out)")
    );
    console.log(
      signedIn
        ? `States:   ${statesAudited}/${expectedStates} open states audited`
        : "States:   skipped (signed out — the workspace is not reachable)"
    );
    console.log("");

    let failed = false;
    if (themeIssues.length) {
      failed = true;
      console.log(`\n✗ Theme: ${themeIssues.length} page load(s) did not apply the theme asked for`);
      for (const t of themeIssues.slice(0, 5)) {
        console.log(`  [${t.where}] asked for ${t.theme}`);
      }
      if (themeIssues.length > 5) console.log(`  … and ${themeIssues.length - 5} more (see ${REPORT})`);
    } else if (themeChecks) {
      console.log(`✓ Theme: ${themeChecks} page loads applied the requested palette`);
    }
    if (shellIssues.length) {
      failed = true;
      console.log(`\n✗ Shell: ${shellIssues.length} signed-in route(s) rendered without the workspace shell`);
      for (const s of shellIssues.slice(0, 5)) {
        console.log(`  [${s.where} ${s.route}] missing ${s.missing.join(", ")}`);
      }
      if (shellIssues.length > 5) console.log(`  … and ${shellIssues.length - 5} more (see ${REPORT})`);
    } else if (signedIn) {
      console.log("✓ Shell: every signed-in route carried the navigation, its active item and the account menu");
    }
    if (stateIssues.length) {
      failed = true;
      console.log(`\n✗ States: ${stateIssues.length} state(s) did not open`);
      for (const s of stateIssues.slice(0, 5)) {
        console.log(`  [${s.state} @ ${s.viewport}px ${s.theme}] ${s.error}`);
      }
      if (stateIssues.length > 5) console.log(`  … and ${stateIssues.length - 5} more (see ${REPORT})`);
    } else if (statesAudited) {
      console.log(`✓ States: all ${statesAudited} open-state audits reached the state they name`);
    }
    if (pwaIssues.length) {
      failed = true;
      console.log(`\n✗ Installable app: ${pwaIssues.length} issue(s)`);
      for (const issue of pwaIssues) console.log(`  - ${issue}`);
    } else {
      console.log("✓ Installable app: manifest fields and icons resolve, worker active, offline route renders the shell");
    }
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
    if (textSpacingIssues.length) {
      failed = true;
      console.log(`\n✗ Text spacing (WCAG 1.4.12): ${textSpacingIssues.length} issue(s) with the reader's overrides applied`);
      for (const i of textSpacingIssues.slice(0, 20)) {
        console.log(`  [${i.viewport} ${i.route}] ${i.kind}: ${i.detail}`);
      }
    } else {
      console.log(
        `✓ Text spacing: ${TEXT_SPACING_VIEWPORTS.length * ROUTES.length} pages hold at 1.5 line-height, 0.12em letter-spacing and 0.16em word-spacing`
      );
    }

    // A redirect seen while signed in means the session died mid-sweep; a
    // redirect seen while signed out is the documented public-pages fallback.
    if (redirects.length) {
      console.log(`\n${signedIn ? "✗" : "!"} Landing: ${redirects.length} page loads did not reach the route asked for`);
      for (const r of redirects.slice(0, 5)) {
        console.log(`  [${r.viewport} ${r.route}] ${r.expected} → ${r.landed}`);
      }
      if (redirects.length > 5) console.log(`  … and ${redirects.length - 5} more (see ${REPORT})`);
      // Signed in, a redirect means the session died under the sweep; in CI the
      // flag means the sweep was never signed in to begin with. Either way a
      // pass here would be a claim about pages nobody looked at.
      if (signedIn || requireSignIn) failed = true;
    } else if (signedIn) {
      console.log("✓ Landing: every route rendered itself");
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
