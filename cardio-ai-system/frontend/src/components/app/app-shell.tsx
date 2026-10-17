import { useEffect, useRef, useState } from "react";
import {
  Activity,
  BookOpen,
  Bot,
  History,
  LayoutGrid,
  LogOut,
  NotebookPen,
  Pill,
  ShieldCheck,
  Stethoscope,
  Users,
  type LucideIcon
} from "lucide-react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { LogoMark, Wordmark } from "@/components/app/logo";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { useAuth } from "@/lib/authContext";
import { initialsOf } from "@/lib/authSession";
import { providerLabel, useEngineStatus } from "@/lib/engine";
import { CONTACT_URL, SITE_NAME } from "@/lib/site";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  /** Tighter label for the dock, where nine destinations share one row. */
  short: string;
  icon: LucideIcon;
  end?: boolean;
  /**
   * The workspace's main action. Drawn a shade bolder than its neighbours so
   * the dock still reads as "open this to work" rather than as a flat menu —
   * but it sits second, because the overview is where a session starts.
   */
  primary?: boolean;
}

/**
 * One destination list for every screen size. The dock is the app's only
 * navigation: the overview leads (it is the page that says "start a
 * consultation"), and the rest follow in the order a visit moves through
 * them — consult, then review medications, then the records behind them.
 */
const NAV: NavItem[] = [
  { to: "/", label: "Overview", short: "Home", icon: LayoutGrid, end: true },
  { to: "/consultation", label: "Consultation", short: "Consult", icon: Stethoscope, primary: true },
  { to: "/medications", label: "Medication review", short: "Meds", icon: Pill },
  { to: "/history", label: "History & visits", short: "History", icon: History },
  { to: "/notes", label: "My notes", short: "Notes", icon: NotebookPen },
  { to: "/patients", label: "Patients", short: "Patients", icon: Users },
  { to: "/guidance", label: "Guidance", short: "Guide", icon: BookOpen },
  { to: "/security", label: "Security", short: "Security", icon: ShieldCheck },
  { to: "/agents", label: "Agent registry", short: "Agents", icon: Bot }
];

/** Longest prefix wins, so `/history` doesn't swallow a deeper route. */
function activeItem(pathname: string): NavItem {
  return (
    NAV.filter((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to))).sort(
      (a, b) => b.to.length - a.to.length
    )[0] ??
    // Unknown path: the breadcrumb names the overview page, not whichever item
    // happens to sit first.
    NAV.find((item) => item.end) ??
    NAV[0]
  );
}

function EngineStatus({ compact = false }: { compact?: boolean }) {
  const { status, provider } = useEngineStatus();

  const copy =
    status === "checking" ? "Connecting" : status === "online" ? "Engine ready" : "Engine offline";
  const dot = status === "online" ? "bg-ok" : status === "offline" ? "bg-danger" : "bg-warn";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-line bg-inset px-2.5 py-1.5",
        compact && "border-transparent bg-transparent px-0 py-0"
      )}
      title={providerLabel(provider)}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot, status === "online" && "animate-pulse-soft")} />
      <span className="text-2xs font-medium text-muted">{copy}</span>
      {status === "online" && !compact ? (
        <span className="ml-auto truncate rounded border border-line bg-elev px-1.5 py-px text-[10px] font-medium text-faint">
          {providerLabel(provider)}
        </span>
      ) : null}
    </div>
  );
}

/**
 * Account controls that used to live in the sidebar footer. The workspace has
 * no sidebar now, so identity, sign-out and the source link collapse into one
 * menu button in the top bar — present at every width.
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
            Source & contact
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

function Topbar({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
      {/* The mark is aria-hidden and the wordmark is hidden on phones, so the
          link needs its own name at every width. */}
      <Link to="/" aria-label="PulseIQ overview" className="flex items-center gap-2.5">
        <LogoMark className="h-7 w-7" />
        <span className="hidden sm:block">
          <Wordmark />
        </span>
      </Link>

      {/* The breadcrumb is a wide-screen nicety: on a phone the page's own
          heading and the dock's active tab already name where you are, and
          the fragment that fits there is "Consult…". */}
      <span aria-hidden="true" className="hidden text-faint/60 sm:inline">
        /
      </span>
      <span className="hidden truncate text-xs font-medium text-fg sm:block">{title}</span>

      <div className="ml-auto flex items-center gap-2">
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
 * The bottom dock: every destination in one app-style bar, always visible.
 *
 * Wide screens spread the nine items evenly with labels; narrow ones keep the
 * same order in a horizontally scrollable strip and centre whichever item is
 * active, so nothing is hidden and nothing needs a "more" menu.
 */
function AppDock() {
  const { pathname } = useLocation();
  const listRef = useRef<HTMLUListElement | null>(null);
  const active = activeItem(pathname);

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    // `block: "nearest"` keeps this from scrolling the page itself.
    node?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [pathname]);

  return (
    <nav
      aria-label="Workspace"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-canvas/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md print:hidden"
    >
      <ul
        ref={listRef}
        className="no-scrollbar mx-auto flex w-full max-w-[1240px] snap-x snap-mandatory items-stretch overflow-x-auto px-1 sm:px-2"
      >
        {NAV.map((item) => (
          <li key={item.to} className="min-w-[68px] flex-1 snap-center sm:min-w-0">
            <NavLink
              to={item.to}
              end={item.end}
              data-active={active.to === item.to}
              // The dock prints short labels; the accessible name stays the
              // full destination so screen readers and the E2E scripts agree.
              aria-label={item.label}
              aria-current={active.to === item.to ? "page" : undefined}
              title={item.label}
              className={({ isActive }) =>
                cn(
                  "group relative flex h-[62px] flex-col items-center justify-center gap-1 px-1 text-[10px] transition-colors duration-150",
                  isActive ? "text-accent" : "text-faint hover:text-muted"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      "absolute inset-x-3 top-0 h-[2px] rounded-b-full bg-accent transition-opacity duration-200",
                      isActive ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <span
                    className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-lg transition-colors duration-150",
                      isActive ? "bg-accent/15" : "bg-transparent group-hover:bg-elev/70"
                    )}
                  >
                    <item.icon
                      className={cn(item.primary ? "h-[19px] w-[19px]" : "h-[17px] w-[17px]")}
                      strokeWidth={item.primary ? 2 : 1.75}
                    />
                  </span>
                  <span
                    className={cn(
                      "max-w-full truncate leading-none",
                      item.primary && "font-semibold"
                    )}
                  >
                    {item.short}
                  </span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * Slim site footer: legal pages plus the real contact address (the public
 * project repository). Keeps privacy/terms reachable from every screen.
 */
function SiteFooter() {
  return (
    <footer className="border-t border-line bg-canvas/60 px-4 pb-20 pt-5 sm:px-6 lg:px-10 lg:pb-24">
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

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active = activeItem(pathname);

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={active.label} />
        <main
          id="main"
          className="mx-auto w-full max-w-[1240px] flex-1 px-4 pb-10 pt-6 sm:px-6 lg:px-10 lg:pt-8 xl:max-w-[1320px] 2xl:max-w-[1440px]"
        >
          {children}
        </main>
        <SiteFooter />
      </div>

      <AppDock />
    </div>
  );
}
