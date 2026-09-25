import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  History,
  ServerCog,
  ShieldCheck,
  Stethoscope
} from "lucide-react";
import { EcgTrace } from "@/components/app/ecg-trace";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const PIPELINE = [
  { step: "01", label: "Narrative intake", detail: "Free-text or dictated symptoms" },
  { step: "02", label: "Symptom extraction", detail: "Terminology normalised to clinical concepts" },
  { step: "03", label: "Feature mapping", detail: "Concepts resolved to 13 model inputs" },
  { step: "04", label: "Risk estimation", detail: "Gradient-boosted forest, calibrated output" },
  { step: "05", label: "Attribution", detail: "Per-feature contribution to the score" }
];

const ACTIONS = [
  {
    to: "/consultation",
    icon: Stethoscope,
    title: "Run a consultation",
    detail: "Speak or type in nine languages — concepts, risk, body map and guidance update live; say \"save visit\" to finish hands-free.",
    cta: "Open consultation"
  },
  {
    to: "/history",
    icon: History,
    title: "Review records",
    detail: "Every screening and saved visit, with re-exportable PDFs and per-patient trails.",
    cta: "Open history"
  }
];

const CAPABILITIES = [
  {
    icon: ServerCog,
    title: "Instant, on-demand screening",
    detail:
      "Turn a narrative into a probability, a triage band and per-feature attribution in seconds."
  },
  {
    icon: ShieldCheck,
    title: "Private to your account",
    detail:
      "Every clinician signs in to their own workspace. Screening and consultation history is stored per account and never shared between them."
  },
  {
    icon: Stethoscope,
    title: "Patient notes that follow the case",
    detail:
      "Keep a private note per patient; tag screenings with the same name and the trail stays together."
  }
];

export function HomePage() {
  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl border border-line bg-panel shadow-panel">
        <div className="grid-veil pointer-events-none absolute inset-0 opacity-70" />
        <div className="relative grid gap-10 px-6 py-9 lg:grid-cols-[1.15fr_0.85fr] lg:px-10 lg:py-12">
          <div className="flex flex-col justify-center">
            <p className="label flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Cardiac screening workspace
            </p>
            <h1 className="mt-4 max-w-xl text-4xl font-semibold text-fg">
              Read the signal behind a symptom description.
            </h1>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-muted">
              PulseIQ takes a patient's own words, resolves them against a curated cardiac vocabulary,
              and returns an explained risk estimate alongside the questions and tests a clinician
              would reach for next.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Button asChild size="lg">
                <Link to="/consultation" className="inline-flex items-center gap-2">
                  Start a consultation
                  <ArrowRight className="h-4 w-4" strokeWidth={2} />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/history">Review past visits</Link>
              </Button>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-2xs text-faint">
              {["Per-clinician accounts", "Private notes", "9 capture languages"].map((item) => (
                <span key={item} className="flex items-center gap-1.5">
                  <span className="h-1 w-1 rounded-full bg-line2" />
                  {item}
                </span>
              ))}
            </div>
          </div>

          {/* Pipeline card */}
          <div className="panel-flat flex flex-col bg-inset/70 p-5">
            <div className="flex items-center justify-between">
              <p className="label">Screening pipeline</p>
              <Activity className="h-3.5 w-3.5 text-accent/70" strokeWidth={1.75} />
            </div>

            <ol className="mt-4 space-y-0">
              {PIPELINE.map((entry, index) => (
                <li key={entry.step} className="relative flex gap-3.5 pb-4 last:pb-0">
                  {index < PIPELINE.length - 1 ? (
                    <span className="absolute left-[11px] top-6 h-[calc(100%-1rem)] w-px bg-line" />
                  ) : null}
                  <span className="num relative z-10 mt-px flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border border-line bg-panel text-[10px] font-medium text-faint">
                    {entry.step}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-medium text-fg">{entry.label}</span>
                    <span className="mt-0.5 block text-2xs leading-relaxed text-faint">{entry.detail}</span>
                  </span>
                </li>
              ))}
            </ol>

            <div className="mt-auto overflow-hidden rounded-md border border-line bg-panel px-2 pt-1">
              <EcgTrace className="-mx-2 h-10 text-accent/50" speed="8s" />
            </div>
          </div>
        </div>
      </section>

      {/* Quick actions */}
      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="label">Start here</p>
            <h2 className="mt-1.5 text-lg font-semibold">Two ways into the workspace</h2>
          </div>
          <Link
            to="/history"
            className="hidden h-7 items-center gap-1.5 rounded-md border border-line px-2.5 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg sm:inline-flex"
          >
            <History className="h-3.5 w-3.5" strokeWidth={1.75} />
            Review past screenings
          </Link>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {ACTIONS.map((action, index) => (
            <Link key={action.to} to={action.to} className="group block animate-fade-up" style={{ animationDelay: `${index * 60}ms` }}>
              <Card className="h-full transition-colors duration-200 hover:border-line2 hover:bg-elev/40">
                <CardContent className="flex h-full flex-col p-5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-elev">
                    <action.icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  </span>
                  <h3 className="mt-4 text-sm font-semibold text-fg">{action.title}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted">{action.detail}</p>
                  <span className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-accent">
                    {action.cta}
                    <ArrowRight
                      className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                      strokeWidth={2}
                    />
                  </span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Capabilities */}
      <section>
        <div className="mb-4">
          <p className="label">Design constraints</p>
          <h2 className="mt-1.5 text-lg font-semibold">Decisions that shaped the build</h2>
        </div>

        <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
          {CAPABILITIES.map((item) => (
            <div key={item.title} className="bg-panel p-5">
              <item.icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
              <h3 className="mt-3 text-sm font-semibold text-fg">{item.title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{item.detail}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-xl border border-line bg-elev/30 px-5 py-4">
          <p className="text-xs leading-relaxed text-faint">
            <span className="font-medium text-muted">New to the workspace?</span> The{" "}
            <Link to="/guidance" className="font-medium text-accent hover:underline">
              Guidance page
            </Link>{" "}
            walks through every workflow and the clinical principles behind the tool.
          </p>
        </div>
      </section>
    </div>
  );
}
