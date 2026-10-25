import { Link } from "react-router-dom";
import { usePageMeta } from "@/lib/usePageMeta";
import {
  Activity,
  ArrowRight,
  History,
  NotebookPen,
  Pill,
  ServerCog,
  ShieldCheck,
  Stethoscope,
  Users
} from "lucide-react";
import { EcgTrace } from "@/components/app/ecg-trace";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";

const PIPELINE = [
  { step: "01", label: "Narrative intake", detail: "Free-text or dictated symptoms" },
  { step: "02", label: "Symptom extraction", detail: "Terminology normalised to clinical concepts" },
  { step: "03", label: "Feature mapping", detail: "Concepts resolved to 13 model inputs" },
  { step: "04", label: "Risk estimation", detail: "Gradient-boosted forest, calibrated output" },
  { step: "05", label: "Attribution", detail: "Per-feature contribution to the score" }
];

/**
 * The four destinations a visit reaches for next. Ordered by how often a
 * session ends up there: check the plan, then the record behind it.
 */
const SHORTCUTS = [
  {
    to: "/medications",
    icon: Pill,
    title: "Medication review",
    detail: "Options, blocks and interactions, each with its source"
  },
  {
    to: "/history",
    icon: History,
    title: "History & visits",
    detail: "Every screening, saved visit and per-patient trail"
  },
  {
    to: "/patients",
    icon: Users,
    title: "Patients",
    detail: "Notes and timelines grouped by the name on them"
  },
  {
    to: "/notes",
    icon: NotebookPen,
    title: "My notes",
    detail: "Private notes that follow the case across screens"
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
  usePageMeta(
    "Overview",
    "PulseIQ turns a patient's own words into an explained cardiac risk estimate with the questions and tests a clinician would reach for next."
  );

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
      <div className="min-w-0 space-y-8">
        {/* Hero: the action first. A clinician arriving here is starting a
            session, not reading a brochure. */}
        <section className="relative overflow-hidden rounded-2xl border border-line bg-panel shadow-panel">
          <div className="grid-veil pointer-events-none absolute inset-0 opacity-70" />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-16 -top-24 h-56 w-56 rounded-full bg-accent/10 blur-3xl"
          />
          <div className="relative px-5 py-7 sm:px-7 sm:py-9 lg:px-9">
            <p className="label flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Cardiac screening workspace
            </p>

            <h1 className="mt-3 max-w-xl text-3xl font-semibold sm:text-4xl">
              Start a consultation.
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted sm:text-base">
              Speak or type the patient's own words. PulseIQ resolves them against a curated
              cardiac vocabulary and returns an explained risk estimate alongside the questions and
              tests a clinician would reach for next.
            </p>

            <div className="mt-6 flex flex-col gap-2.5 sm:flex-row sm:flex-wrap sm:items-center">
              <Button asChild size="lg" className="w-full sm:w-auto">
                <Link to="/consultation" className="inline-flex items-center justify-center gap-2">
                  Start a consultation
                  <ArrowRight className="h-4 w-4" strokeWidth={2} />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
                <Link to="/history">Review past visits</Link>
              </Button>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-2xs text-faint">
              {["Per-clinician accounts", "Private notes", "9 capture languages"].map((item) => (
                <span key={item} className="flex items-center gap-1.5">
                  <span aria-hidden="true" className="h-1 w-1 rounded-full bg-line2" />
                  {item}
                </span>
              ))}
            </div>

            <div className="mt-6 overflow-hidden rounded-lg border border-line bg-inset/60">
              <EcgTrace className="h-10 w-full text-accent/50" speed="8s" />
            </div>
          </div>
        </section>

        {/* Shortcuts: a snap-scrolling rail on a phone (the app gesture) and a
            grid once there is room for one. */}
        <section aria-labelledby="start-here">
          <SectionHeading
            id="start-here"
            eyebrow="Start here"
            title="Where a visit goes next"
            icon={Activity}
            action={
              <Link
                to="/history"
                className="hidden h-7 items-center gap-1.5 rounded-md border border-line px-2.5 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg sm:inline-flex"
              >
                <History className="h-3.5 w-3.5" strokeWidth={1.75} />
                Past screenings
              </Link>
            }
          />
          <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 no-scrollbar sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 lg:grid-cols-4">
            {SHORTCUTS.map((shortcut) => (
              <Link
                key={shortcut.to}
                to={shortcut.to}
                className="group min-w-[220px] snap-start rounded-xl border border-line bg-panel p-4 transition-colors hover:border-line2 hover:bg-elev/40 sm:min-w-0"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <shortcut.icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                </span>
                <p className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-fg">
                  {shortcut.title}
                  <ArrowRight
                    className="h-3.5 w-3.5 text-faint transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-accent"
                    strokeWidth={2}
                  />
                </p>
                <p className="mt-1 text-2xs leading-relaxed text-muted">{shortcut.detail}</p>
              </Link>
            ))}
          </div>
        </section>

        {/* The pipeline as a feed post: what happens between the words and the
            number, which is the part a clinician is being asked to trust. */}
        <section aria-labelledby="pipeline">
          <SectionHeading
            id="pipeline"
            eyebrow="Inside a screening"
            title="From narrative to attribution"
          />
          <Card>
            <CardContent className="p-5">
              <ol className="space-y-0">
                {PIPELINE.map((entry, index) => (
                  <li key={entry.step} className="relative flex gap-3.5 pb-4 last:pb-0">
                    {index < PIPELINE.length - 1 ? (
                      <span
                        aria-hidden="true"
                        className="absolute left-[11px] top-6 h-[calc(100%-1rem)] w-px bg-line"
                      />
                    ) : null}
                    <span className="num relative z-10 mt-px flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border border-line bg-panel text-[10px] font-medium text-faint">
                      {entry.step}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-medium text-fg">{entry.label}</span>
                      <span className="mt-0.5 block text-2xs leading-relaxed text-faint">
                        {entry.detail}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </section>

        <section aria-labelledby="constraints">
          <SectionHeading
            id="constraints"
            eyebrow="Design constraints"
            title="Decisions that shaped the build"
          />
          <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
            {CAPABILITIES.map((item) => (
              <div key={item.title} className="bg-panel p-5">
                <item.icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
                <h3 className="mt-3 text-sm font-semibold text-fg">{item.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Aside: the desktop-only column that makes the wide layout a feed
          rather than a stretched page. It never carries unique information, so
          a phone loses nothing by not showing it. */}
      <aside
        className="hidden space-y-4 print:hidden xl:sticky xl:top-20 xl:block"
        aria-label="Workspace shortcuts"
      >
        <Card>
          <CardContent className="p-5">
            <p className="label">This workspace</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Screening, capture and reporting run on this device against the local engine. Nothing
              is sent anywhere else, and no analytics cookies are set.
            </p>
            <div className="mt-4 space-y-2">
              <Link
                to="/guidance"
                className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg"
              >
                How to use PulseIQ
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
              </Link>
              <Link
                to="/security"
                className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg"
              >
                Privacy &amp; security
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
              </Link>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <p className="label">Before you start</p>
            <ul className="mt-3 space-y-2.5 text-2xs leading-relaxed text-muted">
              <li className="flex gap-2">
                <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                Record consent before dictating; the transcript stores the patient's own words.
              </li>
              <li className="flex gap-2">
                <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                Attach the laboratory report to unlock the values the safety gates read.
              </li>
              <li className="flex gap-2">
                <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                Every recommendation is decision support — review it against the full history.
              </li>
            </ul>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
