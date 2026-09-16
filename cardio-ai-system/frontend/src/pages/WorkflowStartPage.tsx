import { Link } from "react-router-dom";
import { ArrowRight, ClipboardList, FileText, MapPin, Mic, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STEPS = [
  { title: "Capture", detail: "Patient or clinician speech is transcribed live, or typed directly." },
  { title: "Guide", detail: "The copilot proposes follow-up questions and relevant investigations." },
  { title: "Map", detail: "Reported pain is plotted onto a body diagram as the visit progresses." },
  { title: "Collect", detail: "Cardiac symptom terms are gathered into structured visit notes." },
  { title: "Export", detail: "Close the encounter and download a formatted consultation report." }
];

const DELIVERABLES = [
  { icon: Mic, label: "Live transcript", detail: "Speaker-attributed lines with language selection" },
  { icon: MapPin, label: "Regional pain map", detail: "Body diagram driven by described symptoms" },
  { icon: FileText, label: "Structured report", detail: "Summary, advice, plan and red flags as PDF" }
];

export function WorkflowStartPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Records"
        icon={ClipboardList}
        title="Consultation workflow"
        description="A guided path from the first spoken sentence to a finished, exportable visit record."
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Five stages</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-0">
              {STEPS.map((step, index) => (
                <li key={step.title} className="relative flex gap-4 pb-5 last:pb-0">
                  {index < STEPS.length - 1 ? (
                    <span className="absolute left-[13px] top-7 h-[calc(100%-1.25rem)] w-px bg-line" />
                  ) : null}
                  <span className="num relative z-10 mt-0.5 flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border border-line bg-elev text-[11px] font-medium text-muted">
                    {index + 1}
                  </span>
                  <span className="min-w-0 pt-0.5">
                    <span className="block text-sm font-medium text-fg">{step.title}</span>
                    <span className="mt-1 block text-xs leading-relaxed text-muted">{step.detail}</span>
                  </span>
                </li>
              ))}
            </ol>

            <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-5">
              <Button asChild size="lg">
                <Link to="/workflow/session" className="inline-flex items-center gap-2">
                  Start consultation
                  <ArrowRight className="h-4 w-4" strokeWidth={2} />
                </Link>
              </Button>
              <Button asChild variant="ghost" size="lg">
                <Link to="/live">Try the live copilot first</Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>What the encounter produces</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {DELIVERABLES.map((item) => (
                <div key={item.label} className="flex gap-3">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-elev">
                    <item.icon className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-fg">{item.label}</p>
                    <p className="mt-0.5 text-2xs leading-relaxed text-faint">{item.detail}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Alert variant="warning">
            <ShieldAlert />
            <AlertTitle>Before you begin</AlertTitle>
            <AlertDescription>
              The workflow records real clinical content. Use anonymised data unless you have a lawful
              basis for holding identifiable patient information on this device.
            </AlertDescription>
          </Alert>
        </div>
      </div>
    </div>
  );
}
