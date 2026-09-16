import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bot,
  FileDown,
  Gauge,
  History,
  Mic,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const features = [
  {
    to: "/diagnose",
    icon: Gauge,
    title: "Smart Screening",
    description: "Describe symptoms in plain language. Get an instant ML risk score with the factors behind it.",
    accent: "from-teal-500/20 to-transparent",
    iconColor: "text-teal-400",
  },
  {
    to: "/live",
    icon: Mic,
    title: "Live Copilot",
    description: "Real-time speech-to-text consultation with doctor prompts, patient guidance, and body maps.",
    accent: "from-sky-500/20 to-transparent",
    iconColor: "text-sky-400",
  },
  {
    to: "/workflow/start",
    icon: FileDown,
    title: "Consultation Reports",
    description: "Structured visit capture with pain mapping and one-click professional PDF export.",
    accent: "from-violet-500/20 to-transparent",
    iconColor: "text-violet-400",
  },
  {
    to: "/history",
    icon: History,
    title: "Screening History",
    description: "Track past screenings and risk trends locally — your data never leaves the device.",
    accent: "from-amber-500/20 to-transparent",
    iconColor: "text-amber-400",
  },
];

const trust = [
  { icon: Zap, title: "Zero setup", text: "No API keys. No accounts. No paid services — ever." },
  { icon: ShieldCheck, title: "Private by design", text: "Everything runs on your machine; history stays in your browser." },
  { icon: Sparkles, title: "Upgradeable AI", text: "Optional free Ollama integration unlocks richer AI language, still offline." },
];

export function HomePage() {
  return (
    <div className="space-y-6">
      {/* Hero */}
      <Card className="card-animate relative overflow-hidden border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900/80 to-slate-950">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-teal-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-64 w-64 rounded-full bg-sky-500/10 blur-3xl" />
        <CardContent className="relative flex flex-col items-start gap-8 p-8 sm:flex-row sm:items-center sm:justify-between lg:p-10">
          <div className="max-w-xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-teal-500/30 bg-teal-500/10 px-3 py-1 text-xs font-semibold text-teal-300">
              <Activity className="h-3.5 w-3.5" />
              Free · Local · Private
            </div>
            <h1 className="text-3xl font-bold leading-tight tracking-tight text-white sm:text-4xl">
              Your AI heart-health copilot,{" "}
              <span className="bg-gradient-to-r from-teal-300 to-sky-400 bg-clip-text text-transparent">
                completely free.
              </span>
            </h1>
            <p className="text-sm leading-relaxed text-slate-400 sm:text-base">
              Screen symptoms with an explainable ML model, run live consultations with an AI
              copilot, and export clinical PDF reports — all offline, with zero API keys.
            </p>
            <div className="flex flex-wrap gap-3 pt-2">
              <Button asChild size="lg" className="bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400">
                <Link to="/diagnose" className="inline-flex items-center gap-2">
                  Start screening
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="border-slate-700 bg-slate-900/60 hover:bg-slate-800">
                <Link to="/live">Open live copilot</Link>
              </Button>
            </div>
          </div>

          {/* ECG art */}
          <div className="relative hidden w-64 shrink-0 sm:block">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5 shadow-2xl">
              <svg viewBox="0 0 200 200" className="h-40 w-full">
                <circle cx="100" cy="100" r="86" stroke="rgba(45,212,191,0.15)" strokeWidth="10" fill="none" />
                <circle
                  cx="100"
                  cy="100"
                  r="86"
                  stroke="url(#g)"
                  strokeWidth="10"
                  fill="none"
                  strokeDasharray="540"
                  strokeDashoffset="135"
                  strokeLinecap="round"
                />
                <defs>
                  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#2dd4bf" />
                    <stop offset="100%" stopColor="#0ea5e9" />
                  </linearGradient>
                </defs>
                <path
                  className="ecg-line"
                  d="M30 100 h30 l8 -18 l10 34 l10 -26 l8 10 h28"
                  stroke="#2dd4bf"
                  strokeWidth="3"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                {[
                  ["Risk model", "ML"],
                  ["Agents", "17"],
                  ["Cost", "$0"],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-slate-900 px-2 py-1.5">
                    <p className="text-sm font-bold text-teal-300">{v}</p>
                    <p className="text-[10px] text-slate-500">{k}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Feature grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {features.map((f, i) => (
          <Link key={f.to} to={f.to} className="card-animate" style={{ animationDelay: `${i * 70}ms` }}>
            <Card className="group h-full border-slate-800 bg-slate-900/50 transition-all hover:border-teal-500/40 hover:bg-slate-900 hover:shadow-lg hover:shadow-teal-500/5">
              <CardContent className="flex items-start gap-4 p-5">
                <div
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${f.accent} border border-slate-800`}
                >
                  <f.icon className={`h-5 w-5 ${f.iconColor}`} />
                </div>
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-semibold text-white">
                    {f.title}
                    <ArrowRight className="h-3.5 w-3.5 text-slate-600 transition-transform group-hover:translate-x-1 group-hover:text-teal-400" />
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-400">{f.description}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Trust strip */}
      <div className="grid gap-4 md:grid-cols-3">
        {trust.map((t) => (
          <Card key={t.title} className="border-slate-800 bg-slate-900/40">
            <CardContent className="flex items-start gap-3 p-5">
              <t.icon className="mt-0.5 h-5 w-5 shrink-0 text-teal-400" />
              <div>
                <p className="text-sm font-semibold text-white">{t.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{t.text}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Guidelines note */}
      <Card className="border-slate-800 bg-slate-900/40">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base text-white">
            <Bot className="h-4 w-4 text-teal-400" />
            Clinical guardrails built in
          </CardTitle>
          <CardDescription>Guideline-aligned safety logic runs on every screening.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm text-slate-400 sm:grid-cols-3">
          <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            Capture structured symptom history: onset, severity, duration, triggers.
          </p>
          <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            Chest pain patterns prioritize the ECG + serial troponin pathway.
          </p>
          <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            Urgent escalation for red flags: persistent severe pain, syncope, respiratory distress.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
