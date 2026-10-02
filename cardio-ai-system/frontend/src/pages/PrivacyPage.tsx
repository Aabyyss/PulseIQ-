import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePageMeta } from "@/lib/usePageMeta";
import { CONTACT_URL, SITE_NAME } from "@/lib/site";

/**
 * Privacy policy — describes what PulseIQ actually does, not aspirational
 * language: everything runs on this device, auth uses bearer tokens (not
 * cookies), encounter text is de-identified before storage (ADR-016), and
 * each clinician's data stays in their own account.
 */
export function PrivacyPage() {
  usePageMeta(
    "Privacy policy",
    "How PulseIQ handles consultation audio, transcripts and records: on-device processing, de-identification before storage, and per-account isolation."
  );

  const sections = [
    {
      title: "Everything stays on this device",
      body: [
        "PulseIQ runs fully locally: the FastAPI backend, the database and the language model (via Ollama) all execute on this machine. No consultation content, recordings or reports are sent to any external service.",
        "Audio is transcribed in the browser; only transcript text is passed to the local backend."
      ]
    },
    {
      title: "What is stored, and where",
      body: [
        "Screenings, saved visits, notes and taught phrases are stored in the local database, one account per clinician. Accounts are isolated: one clinician's records are never visible to another, and cross-account reads return a 404 rather than confirming the record exists.",
        "Frontend history and preferences (theme, language) are kept in this browser's local storage."
      ]
    },
    {
      title: "De-identification before storage (ADR-016)",
      body: [
        "Identifiers are redacted before anything is persisted: CNIC numbers (dashed or 13-digit), Pakistani and international phone numbers, email addresses, and names written in labelled or honorific form (e.g. \"Mr. Khan\", \"patient Ali\"). Redacted text is replaced with tagged placeholders such as [NAME_1].",
        "The live analysis still sees the original wording during the consultation; only the stored copy is redacted. When redaction happens, an entry is written to your account audit log as privacy.redacted.",
        "Redaction is idempotent — running it again over already-redacted text changes nothing."
      ]
    },
    {
      title: "Recording consent",
      body: [
        "The microphone cannot start until the clinician confirms that the patient consents to the consultation being recorded and analysed. The consent decision is stored with the saved visit."
      ]
    },
    {
      title: "No cookies, no trackers",
      body: [
        "Authentication uses a bearer token held in this browser's local storage, not cookies — so there is no cookie banner to dismiss and no cross-site tracking in any version of this app.",
        "PulseIQ ships no analytics, advertising or third-party tracking scripts."
      ]
    },
    {
      title: "Learning stays yours",
      body: [
        "Clinician-taught phrases form a private vocabulary overlay for that account only. It is never forked into other accounts, and taught phrases are de-identified before they are stored so a name can never enter the vocabulary store."
      ]
    }
  ];

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pb-6">
        <p className="label">Legal</p>
        <h1 className="mt-2 flex items-center gap-2.5 text-2xl font-semibold text-fg">
          <ShieldCheck className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.75} />
          Privacy policy
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          PulseIQ is a local-first clinical workspace. This page describes what it stores, what it
          redacts and what it never leaves the device — in plain language, matching how the
          software actually behaves.
        </p>
        <p className="mt-2 text-2xs text-fact">Last updated: 3 October 2026.</p>
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
        Questions about this policy? {SITE_NAME} is open source — reach out through the{" "}
        <a
          href={CONTACT_URL}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-accent hover:underline"
        >
          project repository
        </a>
        . See also the{" "}
        <Link to="/terms" className="font-medium text-accent hover:underline">
          terms of use
        </Link>
        .
      </footer>
    </div>
  );
}
