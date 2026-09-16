import { Link } from "react-router-dom";
import { ArrowRight, ClipboardCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const steps = [
  { n: 1, title: "Capture", text: "Patient speech or typed transcript, in any supported language." },
  { n: 2, title: "Guide", text: "AI suggests doctor questions and recommended tests as you go." },
  { n: 3, title: "Map", text: "Body diagram highlights reported pain regions automatically." },
  { n: 4, title: "Collect", text: "Disease-focused symptom notes are gathered into structured notes." },
  { n: 5, title: "Export", text: "End the consultation and download a professional PDF report." },
];

export function WorkflowStartPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Card className="card-animate border-slate-800 bg-slate-900/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-2xl text-white">
            <ClipboardCheck className="h-6 w-6 text-teal-400" />
            Consultation workflow
          </CardTitle>
          <CardDescription>
            A structured five-step flow: live transcript guidance, body pain mapping, symptom notes, and a PDF export.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ol className="space-y-3">
            {steps.map((step) => (
              <li key={step.n} className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3.5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-500 to-sky-500 text-xs font-bold text-slate-950">
                  {step.n}
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">{step.title}</p>
                  <p className="text-xs text-slate-400">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <Button asChild size="lg" className="bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400">
            <Link to="/workflow/session" className="inline-flex items-center gap-2">
              Start consultation
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
