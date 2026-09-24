import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  ClipboardList,
  FileText,
  LoaderCircle,
  NotebookPen,
  Printer,
  Search,
  Users
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill } from "@/components/app/risk-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/app/stat-tile";
import { authFetch } from "@/lib/auth";
import { cn } from "@/lib/utils";

export type PatientSummary = {
  patient_name: string;
  screenings: number;
  notes: number;
  consultations: number;
  last_activity: string;
};

export type PatientTimeline = {
  patient_name: string;
  screenings: {
    id: number;
    createdAt: string;
    text: string;
    probability: number;
    risk_level: "Low" | "Medium" | "High";
    symptoms: string[];
  }[];
  note: { body: string; updated_at: string } | null;
  consultations: { id: number; createdAt: string; title: string }[];
};

async function fetchPatients(): Promise<PatientSummary[]> {
  const response = await authFetch("/api/patients");
  if (!response.ok) throw new Error("Failed to load patients.");
  const payload = (await response.json()) as { items?: PatientSummary[] };
  return payload.items ?? [];
}

async function fetchTimeline(name: string): Promise<PatientTimeline> {
  const response = await authFetch(`/api/patients/timeline?patient=${encodeURIComponent(name)}`);
  if (!response.ok) throw new Error("Failed to load the patient timeline.");
  return (await response.json()) as PatientTimeline;
}

function formatDate(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function PatientsPage() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<PatientTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setPatients(await fetchPatients());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function openPatient(name: string) {
    setSelected(name);
    setTimelineLoading(true);
    setTimeline(null);
    try {
      setTimeline(await fetchTimeline(name));
    } finally {
      setTimelineLoading(false);
    }
  }

  const visible = patients.filter((p) =>
    p.patient_name.toLowerCase().includes(query.trim().toLowerCase())
  );

  if (selected) {
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-3 print:hidden">
          <Button variant="ghost" size="sm" onClick={() => { setSelected(null); setTimeline(null); }}>
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
            All patients
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()} className="ml-auto">
            <Printer className="h-3.5 w-3.5" strokeWidth={1.75} />
            Print summary
          </Button>
        </div>

        {timelineLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-56" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : timeline ? (
          <div className="space-y-5">
            <PageHeader
              eyebrow="Patient record"
              icon={FileText}
              title={timeline.patient_name}
              description={`${timeline.screenings.length} screening(s) · ${timeline.consultations.length} consultation(s) · ${timeline.note ? "note on file" : "no note"}`}
            />

            {timeline.note ? (
              <Card>
                <CardContent className="p-5">
                  <p className="label mb-2 flex items-center gap-1.5">
                    <NotebookPen className="h-3 w-3" strokeWidth={1.75} />
                    My note · updated {formatDate(timeline.note.updated_at)}
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">
                    {timeline.note.body || "Empty note."}
                  </p>
                </CardContent>
              </Card>
            ) : null}

            {timeline.screenings.length > 0 ? (
              <div>
                <p className="label mb-3">Screening history</p>
                <ul className="space-y-2">
                  {timeline.screenings.map((s) => (
                    <li
                      key={s.id}
                      className="rounded-lg border border-line bg-inset/60 p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2.5">
                        <RiskPill level={s.risk_level} />
                        <span className="num text-xs text-faint">{formatDate(s.createdAt)}</span>
                        <span className="num ml-auto rounded border border-line bg-elev px-2 py-0.5 text-2xs font-medium text-muted">
                          {(s.probability * 100).toFixed(1)}%
                        </span>
                      </div>
                      <p className="mt-2.5 text-sm leading-relaxed text-muted">{s.text}</p>
                      {s.symptoms.length > 0 ? (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {s.symptoms.map((symptom) => (
                            <Badge key={symptom} variant="outline">{symptom}</Badge>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <EmptyState
                icon={FileText}
                title="No tagged screenings"
                description="Tag a screening with this patient name and it will appear here."
              />
            )}

            {timeline.consultations.length > 0 ? (
              <div>
                <p className="label mb-3">Consultations</p>
                <ul className="space-y-2">
                  {timeline.consultations.map((c) => (
                    <li key={c.id} className="flex items-center gap-3 rounded-lg border border-line bg-inset/60 p-4">
                      <ClipboardList className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-fg">{c.title}</span>
                      <span className="num text-xs text-faint">{formatDate(c.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Records"
        icon={Users}
        title="Patients"
        description="Everyone you have tagged in a screening, note or consultation. Open one to see the full story on a printable timeline."
      />

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : patients.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No patients yet"
          description="Tag a screening or note with a patient name and they will appear here automatically."
        />
      ) : (
        <>
          <div className="relative max-w-sm print:hidden">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" strokeWidth={1.75} />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search patients…" className="pl-8" />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((p) => (
              <button key={p.patient_name} type="button" onClick={() => void openPatient(p.patient_name)} className="text-left">
                <Card className={cn("h-full transition-colors duration-150 hover:border-line2 hover:bg-elev/40")}>
                  <CardContent className="p-4">
                    <p className="truncate text-sm font-semibold text-fg">{p.patient_name}</p>
                    <p className="mt-1 text-2xs text-faint">
                      Last activity {formatDate(p.last_activity)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      <Badge variant="secondary">{p.screenings} screening{p.screenings === 1 ? "" : "s"}</Badge>
                      {p.consultations > 0 ? <Badge variant="outline">{p.consultations} consult{p.consultations === 1 ? "" : "s"}</Badge> : null}
                      {p.notes > 0 ? <Badge variant="outline">note</Badge> : null}
                    </div>
                  </CardContent>
                </Card>
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-3 print:hidden">
            <StatTile label="Patients tracked" value={patients.length} icon={Users} />
            <StatTile
              label="Tagged screenings"
              value={patients.reduce((sum, p) => sum + p.screenings, 0)}
              icon={FileText}
              tone="accent"
            />
            <StatTile
              label="Consultations filed"
              value={patients.reduce((sum, p) => sum + p.consultations, 0)}
              icon={ClipboardList}
            />
          </div>
        </>
      )}
    </div>
  );
}
