import { Link } from "react-router-dom";
import { FileText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePageMeta } from "@/lib/usePageMeta";
import { CONTACT_URL, SITE_NAME } from "@/lib/site";

/**
 * Terms of use — clinical decision-support framing: the tool supports, it
 * does not diagnose; the responsible clinician stays the decision-maker;
 * local-first usage and account responsibilities spelled out.
 */
export function TermsPage() {
  usePageMeta(
    "Terms of use",
    "The terms that apply when using PulseIQ: decision-support scope, clinician responsibility, acceptable use and disclaimer."
  );

  const sections = [
    {
      title: "Decision support, not a diagnosis",
      body: [
        `${SITE_NAME} is a clinical decision-support tool. It organises what you capture, screens text against reference ranges, extracts concepts and drafts documents. It does not diagnose, prescribe or replace clinical judgement.`,
        "Every output — risk bands, suggested questions, reference-range flags, SOAP drafts — is decision support that a qualified clinician must review before acting on."
      ]
    },
    {
      title: "The clinician stays responsible",
      body: [
        "You are responsible for verifying extracted values, entities and drafted notes against the source material, and for the clinical decisions you make with the tool's assistance.",
        "Risk scores and reference-range flags are computed deterministically from the inputs shown; if an input is missing, the tool says so rather than guessing."
      ]
    },
    {
      title: "Eligible use",
      body: [
        "Use PulseIQ only for lawful clinical, educational or evaluation purposes, and only with patient consent as required in your jurisdiction.",
        "Do not attempt to access accounts or records that are not yours, circumvent authentication, or reverse engineer the service to expose other users' data."
      ]
    },
    {
      title: "Your account, your device",
      body: [
        "You are responsible for access to the machine PulseIQ runs on. Sign out when you step away — the workspace also auto-locks after 15 minutes of inactivity.",
        "Because everything is stored locally, backing up the machine is how you back up your records. Deleting local data is permanent and cannot be undone by us."
      ]
    },
    {
      title: "No warranty",
      body: [
        `${SITE_NAME} is provided "as is" without warranties of any kind. It is research and prototype software, not a certified medical device, and it is not intended for use as the sole basis for any medical decision.`,
        "To the maximum extent permitted by law, the authors are not liable for any decision made or action taken in reliance on the software's output."
      ]
    }
  ];

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pb-6">
        <p className="label">Legal</p>
        <h1 className="mt-2 flex items-center gap-2.5 text-2xl font-semibold text-fg">
          <FileText className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.75} />
          Terms of use
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          By using {SITE_NAME} you agree to these terms. They are deliberately short: the tool
          supports clinical work, the clinician decides.
        </p>
        <p className="mt-2 text-2xs text-faint">Last updated: 3 October 2026.</p>
      </header>

      <div className="space-y-4">
        {sections.map((section) => (
          <Card key={section.title}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">{section.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {section.body.map((paragraph) => (
                <p key={paragraph} className="text-xs leading-relaxed text-muted">
                  {paragraph}
                </p>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      <footer className="mt-6 rounded-xl border border-line bg-elev/30 px-5 py-4 text-xs leading-relaxed text-faint">
        Questions or concerns? Reach {SITE_NAME} through the{" "}
        <a
          href={CONTACT_URL}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-accent hover:underline"
        >
          project repository
        </a>
        . See also the{" "}
        <Link to="/privacy" className="font-medium text-accent hover:underline">
          privacy policy
        </Link>
        .
      </footer>
    </div>
  );
}
