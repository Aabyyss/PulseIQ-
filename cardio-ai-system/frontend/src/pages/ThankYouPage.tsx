import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, HeartHandshake } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePageMeta } from "@/lib/usePageMeta";

/**
 * Shown after a visit is saved successfully: confirms what was stored, where
 * to find it next, and offers the two follow-up actions (start another
 * consultation or review the record). Reached from the consultation screen.
 */
export function ThankYouPage() {
  usePageMeta(
    "Visit saved",
    "Your consultation was saved to history. Start the next visit or review the record you just filed."
  );

  const nextSteps = [
    {
      title: "Find it in History",
      detail: "The full transcript, guidance, body map and exported PDF live under History & visits."
    },
    {
      title: "Per-patient trail",
      detail: "If the visit carried a patient name, the same case shows up on the Patients timeline."
    },
    {
      title: "De-identified at rest",
      detail: "Identifiers spoken or pasted during the visit were redacted before anything was stored."
    }
  ];

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex flex-col items-center text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-ok/40 bg-ok/10">
          <CheckCircle2 className="h-7 w-7 text-ok-strong" strokeWidth={1.75} />
        </span>
        <p className="label mt-5">Visit saved</p>
        <h1 className="mt-2 text-2xl font-semibold text-fg">Thank you — the consultation is filed</h1>
        <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
          The transcript, detected concepts, guidance and body map are stored in your records and
          the structured report has been exported as a PDF.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button asChild>
            <Link to="/consultation" className="inline-flex items-center gap-2">
              Start a new consultation
              <ArrowRight className="h-4 w-4" strokeWidth={1.9} />
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/history">Review past visits</Link>
          </Button>
        </div>
      </div>

      <Card className="mt-8">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <HeartHandshake className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
            What happens next
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {nextSteps.map((step) => (
            <div key={step.title} className="rounded-lg border border-line bg-inset p-3">
              <p className="text-xs font-medium text-fg">{step.title}</p>
              <p className="mt-1 text-2xs leading-relaxed text-muted">{step.detail}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
