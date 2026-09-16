import { useEffect, useState } from "react";
import {
  Activity,
  Bot,
  HeartPulse,
  History,
  LayoutDashboard,
  Mic,
  Stethoscope,
  Workflow,
} from "lucide-react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { HomePage } from "@/pages/HomePage";
import { DiagnosePage } from "@/pages/DiagnosePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { LiveConsultationPage } from "@/pages/LiveConsultationPage";
import { ResearchAgentsPage } from "@/pages/ResearchAgentsPage";
import { WorkflowStartPage } from "@/pages/WorkflowStartPage";
import { WorkflowSessionPage } from "@/pages/WorkflowSessionPage";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Home", icon: LayoutDashboard, end: true },
  { to: "/diagnose", label: "Screen", icon: HeartPulse, end: false },
  { to: "/live", label: "Live Copilot", icon: Mic, end: false },
  { to: "/workflow/start", label: "Consultation", icon: Workflow, end: false },
  { to: "/history", label: "History", icon: History, end: false },
  { to: "/agents", label: "Agents", icon: Bot, end: false },
];

function useBackendHealth() {
  const [state, setState] = useState<"checking" | "online" | "offline">("checking");
  const [provider, setProvider] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        const res = await fetch("/api/health", { signal: AbortSignal.timeout(4000) });
        const body = await res.json();
        if (cancelled) return;
        setState("online");
        setProvider(String(body.ai_provider ?? ""));
      } catch {
        if (cancelled) return;
        setState("offline");
        setProvider("");
      }
    };

    probe();
    const timer = window.setInterval(probe, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { state, provider };
}

function EcgLine({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 40" className={className} fill="none" preserveAspectRatio="none">
      <path
        className="ecg-line"
        d="M0 20 H60 l6 -12 l6 24 l6 -18 l8 6 h60 l6 -12 l6 24 l6 -18 l8 6 h60 l6 -12 l6 24 l6 -18 l8 6 H400"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function BrandMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-400 to-sky-600 shadow-lg shadow-teal-500/20",
        className
      )}
    >
      <HeartPulse className="h-5 w-5 text-slate-950" />
    </div>
  );
}

function StatusPill() {
  const { state, provider } = useBackendHealth();

  const label =
    state === "checking" ? "Checking…" : state === "online" ? "Engine online" : "Engine offline";
  const dot =
    state === "online" ? "bg-teal-400 pulse-dot" : state === "offline" ? "bg-rose-500" : "bg-amber-400";

  const providerLabel =
    provider === "ollama"
      ? "Local LLM"
      : provider === "gemini"
        ? "Gemini"
        : provider === "local"
          ? "Built-in AI"
          : "";

  return (
    <div className="flex items-center gap-2 rounded-full border border-slate-700/70 bg-slate-900/60 px-3 py-1.5 text-xs">
      <span className={cn("h-2 w-2 rounded-full", dot)} />
      <span className="font-medium text-slate-200">{label}</span>
      {providerLabel ? (
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-teal-300">
          {providerLabel}
        </span>
      ) : null}
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-screen lg:flex">
      {/* Sidebar (desktop) */}
      <aside className="glass sticky top-0 z-40 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-800/80 lg:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          <BrandMark />
          <div>
            <p className="text-lg font-bold leading-tight tracking-tight text-white">PulseIQ</p>
            <p className="text-[11px] font-medium uppercase tracking-wider text-teal-400">
              Heart Health AI
            </p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                  isActive
                    ? "bg-gradient-to-r from-teal-500/15 to-sky-500/10 text-teal-300 shadow-[inset_0_0_0_1px_rgba(45,212,191,0.25)]"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
                )
              }
            >
              <item.icon className="h-4.5 w-4.5 h-[18px] w-[18px]" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-3 border-t border-slate-800/80 p-4">
          <StatusPill />
          <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70 p-3">
            <EcgLine className="h-8 w-full text-teal-400/70" />
            <p className="mt-1 text-[10px] leading-snug text-slate-500">
              100% free · runs locally · no API keys
            </p>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="glass sticky top-0 z-40 flex items-center justify-between border-b border-slate-800/80 px-4 py-3 lg:hidden">
          <Link to="/" className="flex items-center gap-2.5">
            <BrandMark className="h-9 w-9" />
            <div>
              <p className="text-base font-bold leading-none text-white">PulseIQ</p>
              <p className="text-[10px] font-medium uppercase tracking-wider text-teal-400">
                Heart Health AI
              </p>
            </div>
          </Link>
          <StatusPill />
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-28 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-8">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/diagnose" element={<DiagnosePage />} />
            <Route path="/live" element={<LiveConsultationPage />} />
            <Route path="/workflow/start" element={<WorkflowStartPage />} />
            <Route path="/workflow/session" element={<WorkflowSessionPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/agents" element={<ResearchAgentsPage />} />
          </Routes>
        </main>

        {/* Mobile bottom nav */}
        <nav className="glass fixed inset-x-0 bottom-0 z-40 flex items-center justify-around border-t border-slate-800/80 px-2 py-2 lg:hidden">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium transition-colors",
                  isActive ? "text-teal-300" : "text-slate-500"
                )
              }
            >
              <item.icon className="h-5 w-5" />
              {item.label.split(" ")[0]}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
