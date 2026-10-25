# PulseIQ — layout and visual system

This is the why behind the shell: which navigation appears at which width, how a
page is allowed to reflow, and what the palette is allowed to say. It is written
down because "make it feel like an app" is not a testable instruction, and the
next person to add a destination or a breakpoint should not have to reverse it
out of Tailwind classes.

Everything here is checked by `scripts/ui-audit.cjs`; the commands and their
limits are in [VERIFICATION.md](VERIFICATION.md).

---

## 1. One app, three presentations

The workspace has **nine destinations, one list, one active-item rule**
(`frontend/src/lib/navigation.ts`). Only the presentation changes with available
width — never the destination set, never the order.

| Width | Navigation | Why this presentation |
|---|---|---|
| **< 768px** (phone) | Bottom bar: five destinations + **More** | Material's navigation bar is specified for compact windows under 600dp and **3–5 equally important destinations**. Nine items in one scrolling row hid the last three behind a gesture nobody discovers. |
| **768–1023px** (tablet portrait) | Same bottom bar | A tablet in portrait has the width of a large phone. Apple's iPad guidance keeps a tab bar and cautions against turning More into the default home for destinations, so the same five lead here. |
| **≥ 1024px** (`lg`) | Labelled left rail, all nine | Material's rail/drawer territory. A rail also matches what people expect of a desktop app, and the content column keeps its own max-width. |
| **≥ 1280px** (`xl`) | Rail + feed aside on the overview | The extra width goes to a second column of context, not to longer lines of clinical text. |

The rail is `sticky`, **not fixed**: it participates in the layout, so content
can never be laid out underneath it at an intermediate width. The phone bar is
fixed, because it has to sit above the on-screen keyboard, and its container
adds `env(safe-area-inset-bottom)` so the last row clears a home indicator.

The five primary destinations are the ones a session touches — Overview,
Consultation, Medication review, History, Patients. Notes, Guidance, Security
and the Agent registry live behind More on a phone and sit as ordinary rail items
at `lg`.

**Rejected:** nine items in a scroll strip (the original dock — discoverability
and 43px targets at 390px); a hamburger drawer on phones (an extra tap for the
screen a clinician opens most often); a bottom bar at every width (wastes 56px of
a laptop's height and reads as a website, not an app).

Sources: [Material 3 navigation bar](https://m3.material.io/components/navigation-bar/overview)
· [navigation rail](https://m3.material.io/components/navigation-rail/overview)
· [breakpoints](https://m3.material.io/foundations/layout/breakpoints) ·
[Apple HIG tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars).

### Sizing and orientation across devices

Widths are fluid, not device classes: everything between 320 and 2560 CSS px is
audited, including both orientations of a tablet (`768×1024`, `1024×768`),
phone portrait (`390×844`), phone landscape (`844×390`), laptop panels
(`1366×768`, `1536×864`), desktop (`1920×1080`) and wide (`2560×1440`).

That is the answer to "can its orientation and sizing be variable?" — yes, and
the audit enforces it rather than assuming it. What the audit **cannot** prove is
how a real iPad's split view, abrowser's collapsing address bar, or a physical notch behaves; those need the device, and are listed as limits in
[VERIFICATION.md](VERIFICATION.md).

Content widths: `1240px` at desktop, `1320` at `xl`, `1440` at `2xl`, always
centred in the column beside the rail. Clinical prose inside a card is capped
near 65 characters; the overview's feed column is narrower than the page because
a 2560px single column of text is unreadable however tidy it looks.

---

## 2. The visual language

- **Surfaces.** Canvas, panel, elevated, inset. One hairline border and one soft
  shadow per panel; no second elevation system.
- **Palette.** A neutral graphite ramp, one accent for interactive intent
  (teal in dark, violet in light), and red/amber/green/blue reserved for clinical
  signal. A colour outside that vocabulary is a bug, not a style choice.
- **Type.** Inter for UI, JetBrains Mono for numerics and labels. `2xs`–`5xl`
  scale with negative tracking on headings; `text-wrap: balance` on headings so a
  two-line title does not end on one word.
- **Density.** 14px base on desktop, same on mobile — a clinical table is not the
  place to prove a 16px floor, and the audit holds every text node to WCAG AA.
- **Motion.** 150–280ms, eased out, and nothing that moves information. Every
  animation is disabled under `prefers-reduced-motion: reduce`, which the audit
  emulates in both palettes.
- **Focus.** A 2px accent ring with a canvas offset on every focusable element,
  `scroll-padding` clear of both bars, and a skip link that is the first tab stop.

The overview is a feed: the action first, a snap-scrolling row of the next four
destinations on a phone (a grid from `sm`), then pipeline and constraints as feed
sections. From `xl` a sticky aside carries workspace context — never information
that a phone would lose.

---

## 3. Overlays

Three overlays exist, all native `<dialog>` elements opened with `showModal()`:

| Overlay | Opens | Why native |
|---|---|---|
| More sheet | More, below `lg` | Browser supplies focus containment, Escape, inert background and focus return; the backdrop is themed for both palettes. |
| Command palette | Ctrl/⌘ K, or "Jump to…" | Same containment, plus a listbox with arrow keys and Enter. |
| Account menu | Avatar | A popover, not a modal; closes on outside click and Escape. |

Every overlay is a named audit state: opened, proved present, and swept for
contrast and clipping in both themes at phone and laptop widths.

---

## 4. Installable app

`manifest.webmanifest` declares `standalone`, a start URL at the overview, and
the existing 192/512 icons — all verified at their real pixel sizes. The service
worker caches the shell **and the hashed bundle referenced by the built
`index.html`**, because caching the HTML alone produced an offline page with no
JavaScript.

The policy is one branch: `/api` and `/ws` are never intercepted, so no patient
data can be cached by a later rule. Navigation is network-first with the cached
shell as the fallback; hashed assets are cache-first.

`viewport-fit=cover` and safe-area insets make the bar sit correctly on a
notched phone; `theme-color` follows the stored palette so the status bar matches
the app in standalone mode.

Sources: [web.dev install criteria](https://web.dev/articles/install-criteria)
· [manifest](https://web.dev/learn/pwa/web-app-manifest) ·
[WebKit safe areas](https://webkit.org/blog/7929/designing-websites-for-iphone-x/).

---

## 5. Accessibility baseline (WCAG 2.2 AA)

| Criterion | How it is held |
|---|---|
| 1.4.3 Contrast | Every text node measured against its composed background, both palettes, four widths, including 22 opened states. |
| 1.4.10 Reflow | 320px (1280px at 400% zoom) in the layout ladder; the rail becomes a bar instead of overflowing. |
| 1.4.12 Text spacing | Line-height 1.5, letter-spacing 0.12em, word-spacing 0.16em applied, then clipping/overflow re-checked. |
| 2.4.7 Focus visible | Accent ring on `:focus-visible`; overlays inherit it. |
| 2.4.11 Focus not obscured | Every control on three routes focused in turn at 390 and 1440; failure only if no point of it is visible. |
| 2.5.8 Target size | Every `a`, `button` and `role=button` at least 24×24, checked at ten widths; the phone bar's items are ≥ 64×56. |
| 3.2.6 Consistent help | Guidance, contact and the account menu are in the same place on every screen. |

Not automated: screen-reader announcement quality, caption/transcript
accessibility, and cognitive load. Those need a person and a device.
