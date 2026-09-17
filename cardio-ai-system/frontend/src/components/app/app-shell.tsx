import {
  Activity,
  Bot,
  ClipboardList,
  History,
  LayoutGrid,
  Mic,
  ShieldCheck,
  type LucideIcon
} from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { EcgTrace } from "@/components/app/ecg-trace";
import { LogoMark, Wordmark } from "@/components/app/logo";
import { providerLabel, useEngineStatus } from "@/lib/engine";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  short: string;
  icon: LucideIcon;
  group: string;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Overview", short: "Overview", icon: LayoutGrid, group: "Workspace", end: true },
  { to: "/diagnose", label: "Symptom screening", short: "Screen", icon: Activity, group: "Workspace" },
  { to: "/live", label: "Live copilot", short: "Copilot", icon: Mic, group: "Workspace" },
  { to: "/workflow/start", label: "Consultations", short: "Consult", icon: ClipboardList, group: "Records" },
  { to: "/history", label: "Screening history", short: "History", icon: History, group: "Records" },
  { to: "/agents", label: "Agent registry", short: "Agents", icon: Bot, group: "System" }
];

function groupBy(items: NavItem[], key: keyof NavItem) {
  return items.reduce<Record<string, NavItem[]>>((acc, item) => {
    const bucket = String(item[key]);
    acc[bucket] = acc[bucket] ? [...acc[bucket], item] : [item];
    return acc;
  }, {});
}

const NAV_GROUPS = groupBy(NAV, "group");

function EngineStatus() {
  const { status, provider } = useEngineStatus();

  const copy =
    status === "checking" ? "Connecting" : status === "online" ? "Engine ready" : "Engine offline";
  const dot =
    status === "online" ? "bg-ok" : status === "offline" ? "bg-danger" : "bg-warn";
  const animate = status === "online" ? "animate-pulse-soft" : "";

  return (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-inset px-2.5 py-1.5">
      <span className={cn("h-1.5 w-1.5 rounded-full", dot, animate)} />
      <span className="text-2xs font-medium text-muted">{copy}</span>
      {status === "online" ? (
        <span className="ml-auto truncate rounded border border-line bg-elev px-1.5 py-px text-[10px] font-medium text-faint">
          {providerLabel(provider)}
        </span>
      ) : null}
    </div>
  );
}

function SidebarNav() {
  return (
    <nav className="flex-1 overflow-y-auto px-3 py-4">
      {Object.entries(NAV_GROUPS).map(([group, items]) => (
        <div key={group} className="mb-5 last:mb-0">
          <p className="label px-2.5 pb-2">{group}</p>
          <ul className="space-y-0.5">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      "group relative flex items-center gap-2.5 rounded-lg py-2 pl-3.5 pr-2.5 text-sm transition-colors duration-150",
                      isActive
                        ? "bg-elev font-medium text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                        : "text-muted hover:bg-elev/50 hover:text-fg"
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span
                        className={cn(
                          "absolute left-0 top-1/2 h-3.5 w-[2px] -translate-y-1/2 rounded-r-full bg-accent transition-opacity duration-200",
                          isActive ? "opacity-100" : "opacity-0"
                        )}
                      />
                      <item.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isActive ? "text-accent" : "text-faint group-hover:text-muted"
                        )}
                        strokeWidth={1.75}
                      />
                      <span className="truncate">{item.label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line bg-canvas/70 lg:flex">
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
        <LogoMark />
        <Wordmark />
      </div>

      <SidebarNav />

      <div className="shrink-0 space-y-3 border-t border-line p-3">
        <EngineStatus />
        <div className="relative overflow-hidden rounded-lg border border-line bg-inset px-3 pt-1">
          <EcgTrace className="-mx-1 h-9 opacity-70" speed="7s" />
          <p className="flex items-center gap-1.5 pb-2.5 pt-0.5 text-2xs text-faint">
            <ShieldCheck className="h-3 w-3" strokeWidth={1.75} />
            On-device · No accounts or keys
          </p>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
      <Link to="/" className="flex items-center gap-2.5 lg:hidden">
        <LogoMark className="h-7 w-7" />
        <span className="text-sm font-semibold tracking-[-0.01em]">PulseIQ</span>
      </Link>

      <div className="hidden min-w-0 items-center gap-2 lg:flex">
        <span className="text-2xs font-medium uppercase tracking-[0.14em] text-faint">PulseIQ</span>
        <span aria-hidden="true" className="text-faint/60">/</span>
        <span className="truncate text-xs font-medium text-fg">{title}</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="hidden sm:block">
          <EngineStatus />
        </div>
        <a
          href="https://github.com/Aabyyss/PulseIQ-"
          target="_blank"
          rel="noreferrer"
          className="hidden h-9 items-center gap-1.5 rounded-lg border border-line bg-elev/70 px-3 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg sm:inline-flex"
        >
          <Activity className="h-3.5 w-3.5" strokeWidth={1.75} />
          Source
        </a>
      </div>
    </header>
  );
}

function MobileNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-canvas/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
      <ul className="flex items-stretch">
        {NAV.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "relative flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium transition-colors",
                  isActive ? "text-accent" : "text-faint"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      "absolute inset-x-4 top-0 h-[2px] rounded-b-full bg-accent transition-opacity",
                      isActive ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <item.icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                  {item.short}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  const active =
    NAV.filter((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to))).sort(
      (a, b) => b.to.length - a.to.length
    )[0] ?? NAV[0];

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={active.label} />
        <main id="main" className="mx-auto w-full max-w-[1240px] flex-1 px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-16 lg:pt-8">
          {children}
        </main>
      </div>

      <MobileNav />
    </div>
  );
}
