import { useEffect, useRef, useState } from "react";
import { Activity, BookOpen, LogOut, Search } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LogoMark, Wordmark } from "@/components/app/logo";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { EngineStatus } from "@/components/app/engine-status";
import { WorkspaceNav } from "@/components/app/workspace-nav";
import { CommandPalette } from "@/components/app/command-palette";
import { useAuth } from "@/lib/authContext";
import { initialsOf } from "@/lib/authSession";
import { activeItem } from "@/lib/navigation";
import { CONTACT_URL, SITE_NAME } from "@/lib/site";

/**
 * Account controls. Identity, sign-out and the source link collapse into one
 * menu button in the top bar — present at every width, so the rail can stay
 * navigation only.
 */
function AccountMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Signed out (login/legal pages): nothing to show.
  if (!user) return null;

  async function handleSignOut() {
    setOpen(false);
    await signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-elev/70 text-xs font-semibold text-accent transition-colors hover:bg-elev"
      >
        {initialsOf(user)}
      </button>

      {open ? (
        <div
          role="menu"
          className="animate-slide-in absolute right-0 top-[calc(100%+8px)] z-50 w-64 overflow-hidden rounded-xl border border-line bg-panel p-1 shadow-pop"
        >
          <div className="px-3 pb-2 pt-2.5">
            <p className="truncate text-xs font-medium text-fg">{user.name || user.email}</p>
            {user.name ? <p className="truncate text-2xs text-faint">{user.email}</p> : null}
          </div>
          <div className="rule" />
          <Link
            to="/guidance"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted transition-colors hover:bg-elev hover:text-fg"
          >
            <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} />
            How to use PulseIQ
          </Link>
          <a
            href={CONTACT_URL}
            role="menuitem"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted transition-colors hover:bg-elev hover:text-fg"
          >
            <Activity className="h-3.5 w-3.5" strokeWidth={1.75} />
            Source &amp; contact
          </a>
          <div className="rule my-1" />
          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The top bar. On a phone it carries the brand; from `lg` up the rail does, so
 * the bar is the page's own header — where you are, engine state, theme and the
 * account menu — and the logo is not drawn twice.
 */
function Topbar({ title, onOpenPalette }: { title?: string; onOpenPalette: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6 lg:px-8">
      <Link to="/" aria-label="PulseIQ overview" className="flex items-center gap-2.5 lg:hidden">
        <LogoMark className="h-7 w-7" />
        <span className="hidden sm:block">
          <Wordmark />
        </span>
      </Link>

      {/* The breadcrumb names the current destination. On a phone the page's own
          heading and the bar's active tab already say where you are, and the
          fragment that fits there is "Consult…". Pages outside the navigation
          have no destination to name, so they render no crumb at all. */}
      {title ? (
        <>
          <span aria-hidden="true" className="hidden text-faint/60 sm:inline">
            /
          </span>
          <span className="hidden truncate text-xs font-medium text-fg sm:block">{title}</span>
        </>
      ) : null}

      <div className="ml-auto flex items-center gap-2">
        {/* The palette's discoverable entry point. The shortcut alone would be
            a feature only its author knows about. */}
        <button
          type="button"
          onClick={onOpenPalette}
          aria-label="Search destinations"
          aria-keyshortcuts="Control+K Meta+K"
          title="Jump to a destination (Ctrl K)"
          className="flex h-9 items-center gap-2 rounded-lg border border-line bg-elev/70 px-2 text-xs text-muted transition-colors hover:bg-elev hover:text-fg sm:px-2.5"
        >
          <Search className="h-3.5 w-3.5" strokeWidth={1.75} />
          <span className="hidden md:inline">Jump to…</span>
          <kbd className="hidden rounded border border-line bg-inset px-1 py-0.5 font-mono text-[10px] text-faint md:inline">
            Ctrl K
          </kbd>
        </button>
        <div className="hidden sm:block">
          <EngineStatus />
        </div>
        <div className="sm:hidden">
          <EngineStatus compact />
        </div>
        <ThemeToggle />
        <AccountMenu />
      </div>
    </header>
  );
}

/**
 * Slim site footer: legal pages plus the real contact address (the public
 * project repository). Keeps privacy/terms reachable from every screen.
 */
function SiteFooter() {
  return (
    <footer className="border-t border-line bg-canvas/60 px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-8">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <p className="text-2xs text-faint">
          {SITE_NAME} · runs entirely on this device · no cookies, no tracking
        </p>
        <nav aria-label="Site" className="flex items-center gap-4 text-2xs">
          <Link to="/privacy" className="text-faint transition-colors hover:text-muted">
            Privacy policy
          </Link>
          <Link to="/terms" className="text-faint transition-colors hover:text-muted">
            Terms of use
          </Link>
          <a
            href={CONTACT_URL}
            target="_blank"
            rel="noreferrer"
            className="text-faint transition-colors hover:text-muted"
          >
            Contact
          </a>
        </nav>
      </div>
    </footer>
  );
}

/**
 * The app shell: a rail and a content column from `lg` up, a single column with
 * a bottom bar below it.
 *
 * The rail is sticky and in normal flow rather than fixed, so the content
 * column can never be laid out underneath it — the failure mode of a fixed
 * sidebar at an intermediate width. `min-w-0` on the column is what lets long
 * clinical text shrink instead of forcing the page wider than the viewport.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active = activeItem(pathname);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Ctrl/⌘ K from anywhere. The listener is on the window because the shortcut
  // has to work while focus is inside a form field, which is exactly when
  // reaching for the mouse is most annoying.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <WorkspaceNav />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={active?.label} onOpenPalette={() => setPaletteOpen(true)} />
        <main
          id="main"
          className="mx-auto w-full max-w-[1240px] flex-1 px-4 pb-8 pt-5 sm:px-6 lg:px-8 lg:pt-8 xl:max-w-[1320px] 2xl:max-w-[1440px]"
        >
          {children}
        </main>
        <SiteFooter />
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
