import {
  Activity,
  BookOpen,
  Clock,
  GraduationCap,
  History,
  NotebookPen,
  ShieldCheck,
  Stethoscope
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const WORKFLOWS = [
  {
    icon: Stethoscope,
    title: "Consultation workspace",
    steps: [
      "Open Consultation — one screen runs the whole encounter. Quick consult is audio-first: press Start listening and speak naturally.",
      "The copilot attributes each line automatically: symptom-telling lines are marked patient, clinical or informing lines are marked doctor. Manual roles are there if you prefer.",
      "Concepts, the risk band, the body pain map and suggested questions update the moment a line is captured — no waiting for the language model to finish.",
      "Watch the level bar under the listening button: it rides your voice and turns green while speech is detected, so a muted or blocked mic is obvious immediately.",
      "Hands-free: say \"save visit\" to finish and store the encounter, or \"clear transcript\" to start over — spoken commands never enter the record.",
      "Full consult shows the same live transcript plus the patient-details form; both modes stay in sync.",
      "Assess a narrative any time on the same screen for a scored risk estimate, and upload a report image to pull out findings.",
      "Save visit downloads the structured PDF and stores the record in your account in one click; History → Consultations keeps every visit re-exportable."
    ]
  },
  {
    icon: History,
    title: "History & notes",
    steps: [
      "Every screening auto-saves to your account, newest first, with per-entry delete and clear-all.",
      "My notes is your private notebook: one note per patient name, editable any time.",
      "Patients gathers everything you tagged under one name — screenings, note, consultations — on a printable timeline.",
      "Security shows your active sessions and recent account activity; revoke any session you don't recognise."
    ]
  }
];

const PRINCIPLES = [
  {
    icon: Stethoscope,
    title: "Decision support only",
    detail:
      "PulseIQ is a screening and documentation aid. It does not diagnose, and its output must be reviewed by a qualified clinician before any clinical decision."
  },
  {
    icon: ShieldCheck,
    title: "Escalate on clinical grounds",
    detail:
      "Any presentation suggesting acute coronary syndrome — ongoing chest pain, syncope, or respiratory distress — should be escalated on clinical grounds alone, regardless of what the tool shows."
  },
  {
    icon: Activity,
    title: "Read inconclusive as inconclusive",
    detail:
      "A low score on a narrative the vocabulary did not recognise is not reassurance. Check which concepts were detected before weighing the number."
  },
  {
    icon: NotebookPen,
    title: "Your records are yours",
    detail:
      "Screenings, consultations and notes are scoped to the signed-in account. Other accounts on this machine can never see them, and the workspace auto-locks after 15 minutes without activity."
  }
];

const FAQ = [
  {
    q: "What does the risk band mean?",
    a: "The model outputs a probability; the band is how the workspace triages it for review. Low ≈ routine follow-up, Medium ≈ worth a closer look, High ≈ flagged for priority review. The band supports triage — it is not a diagnosis."
  },
  {
    q: "Why did a narrative score high with few concepts detected?",
    a: "The score combines the recognised concepts with the feature profile mapped from them. If the detected concepts are strong cardiac markers, the score can be high even from few words. The Attribution tab shows exactly which inputs moved it."
  },
  {
    q: "What languages does symptom extraction understand?",
    a: "The clinical vocabulary matches English, Urdu and Roman-Urdu phrasings for nine cardiac concepts: chest pain (including \"pain in my heart\"), shortness of breath, dizziness, palpitations, fatigue, nausea, sweating, leg swelling and cough. Korean can be captured and is translated before analysis; Urdu matching works even when the translator is offline."
  },
  {
    q: "Can I control the copilot by voice?",
    a: "Yes. While listening, say \"save visit\" to finish and store the encounter, or \"clear transcript\" to start over - in Urdu, \"save karo\" works too. Spoken commands are never added to the transcript."
  },
  {
    q: "Where is my data stored?",
    a: "In a local database on this machine, scoped to your account. There is no cloud component; nothing leaves the device."
  },
  {
    q: "Can two cardiologists share one machine?",
    a: "Yes. Each signs in to their own account. History, consultations and notes are private per account, and signing out immediately revokes the session."
  }
];

function SectionCard({
  icon: Icon,
  title,
  children,
  className
}: {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function GuidancePage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="System"
        icon={BookOpen}
        title="Guidance"
        description="How to run each workflow, and the clinical principles the workspace is built around. This is the single reference for scope and safe-use rules."
      />

      <section>
        <p className="label mb-3">Workflows</p>
        <div className="grid gap-4 lg:grid-cols-2">
          {WORKFLOWS.map((flow) => (
            <SectionCard key={flow.title} icon={flow.icon} title={flow.title}>
              <ol className="space-y-2.5">
                {flow.steps.map((step, index) => (
                  <li key={index} className="flex gap-2.5 text-xs leading-relaxed text-muted">
                    <span className="num mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border border-line bg-inset text-[10px] font-medium text-faint">
                      {index + 1}
                    </span>
                    {step}
                  </li>
                ))}
              </ol>
            </SectionCard>
          ))}
        </div>
      </section>

      <section>
        <p className="label mb-3">Clinical principles</p>
        <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
          {PRINCIPLES.map((item) => (
            <div key={item.title} className="bg-panel p-5">
              <item.icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
              <h3 className="mt-3 text-sm font-semibold text-fg">{item.title}</h3>
              <p className={cn("mt-1.5 text-xs leading-relaxed text-muted")}>{item.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <p className="label mb-3">Questions</p>
        <div className="grid gap-3 md:grid-cols-2">
          {FAQ.map((item) => (
            <SectionCard key={item.q} icon={GraduationCap} title={item.q} className="h-full">
              <p className="text-xs leading-relaxed text-muted">{item.a}</p>
            </SectionCard>
          ))}
        </div>
      </section>

      <section>
        <div className="rounded-xl border border-line bg-elev/30 px-5 py-4">
          <p className="flex items-center gap-1.5 text-xs font-medium text-fg">
            <Clock className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
            Version note
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-faint">
            Guidance reflects the current build of PulseIQ. If the workspace behaves differently from
            this page, trust the workspace and report the gap to your system administrator.
          </p>
        </div>
      </section>
    </div>
  );
}
