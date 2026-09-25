import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Clock,
  Database,
  FileDown,
  ShieldCheck,
  Stethoscope,
  Trash2,
  TrendingUp,
  Users
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { StatTile } from "@/components/app/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { exportConsultationPdf } from "@/lib/pdfReport";
import {
  clearConsultations,
  clearHistory,
  deleteConsultation,
  deleteHistoryItem,
  loadConsultations,
  loadHistory
} from "@/lib/history";
import type { FinalReport } from "@/lib/types";
import type { DiagnosisHistoryItem } from "@/lib/types";

type ConsultationRecord = {
  id?: number;
  createdAt: string;
  title?: string;
  patient_name?: string;
  patient_age?: string;
  patient_gender?: string;
  visit_date?: string;
  doctor_name?: string;
  chief_complaint?: string;
  risk_level?: string;
  symptom_notes?: string[];
  spoken_language?: string;
  transcript?: { speaker: string; text: string; timestamp?: string }[];
  report?: FinalReport;
};

const BANDS: { level: RiskLevel; bar: string }[] = [
  { level: "Low", bar: "bg-ok" },
  { level: "Medium", bar: "bg-warn" },
  { level: "High", bar: "bg-danger" }
];

function formatStamp(iso: string) {
  const date = new Date(iso);
  return {
    date: date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }),
    time: date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  };
}

export function HistoryPage() {
  const [history, setHistory] = useState<DiagnosisHistoryItem[]>([]);
  const [consultations, setConsultations] = useState<ConsultationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [consultLoading, setConsultLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setConsultLoading(true);
    const [items, visits] = await Promise.all([loadHistory(), loadConsultations<ConsultationRecord>()]);
    setHistory(items);
    setConsultations(visits);
    setLoading(false);
    setConsultLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const summary = useMemo(() => {
    if (history.length === 0) return null;
    const counts = {
      Low: history.filter((item) => item.risk_level === "Low").length,
      Medium: history.filter((item) => item.risk_level === "Medium").length,
      High: history.filter((item) => item.risk_level === "High").length
    };
    const average = history.reduce((sum, item) => sum + item.probability, 0) / history.length;
    return { counts, average, total: history.length };
  }, [history]);

  async function handleClear() {
    await clearHistory();
    setHistory([]);
  }

  async function handleDelete(id: number | undefined) {
    if (id === undefined) return;
    const ok = await deleteHistoryItem(id);
    if (ok) setHistory((prev) => prev.filter((item) => item.id !== id));
  }

  async function handleDeleteConsultation(id: number | undefined) {
    if (id === undefined) return;
    const ok = await deleteConsultation(id);
    if (ok) setConsultations((prev) => prev.filter((item) => item.id !== id));
  }

  function handleExportConsultation(visit: ConsultationRecord) {
    if (!visit.report) return;
    exportConsultationPdf(visit.report, {
      patientName: visit.patient_name,
      patientAge: visit.patient_age,
      patientGender: visit.patient_gender,
      visitDate: visit.visit_date,
      doctorName: visit.doctor_name,
      chiefComplaint: visit.chief_complaint
    });
  }

  return (
    <div>
      <PageHeader
        eyebrow="Records"
        icon={Clock}
        title="Screening history"
        description="Every screening you run is saved to your account, newest first."
        actions={
          history.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={handleClear} className="hover:text-danger-strong">
              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              Clear history
            </Button>
          ) : null
        }
      />

      <div className="space-y-5">
        <Tabs defaultValue="screenings">
          <TabsList className="w-full sm:w-auto">
            <TabsTrigger value="screenings">
              <Activity className="h-3.5 w-3.5" strokeWidth={1.75} />
              Screenings
            </TabsTrigger>
            <TabsTrigger value="consultations">
              <Stethoscope className="h-3.5 w-3.5" strokeWidth={1.75} />
              Consultations
            </TabsTrigger>
          </TabsList>

          <TabsContent value="screenings">
            {summary ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile label="Screenings recorded" value={summary.total} icon={Activity} />
              <StatTile
                label="Mean probability"
                value={`${(summary.average * 100).toFixed(1)}%`}
                icon={TrendingUp}
                tone="accent"
              />
              <StatTile
                label="Flagged high"
                value={summary.counts.High}
                icon={ShieldCheck}
                tone={summary.counts.High > 0 ? "danger" : "neutral"}
                hint="Escalation band"
              />
              <StatTile
                label="Retention"
                value="200"
                unit="entries"
                icon={Database}
                hint="Oldest entries roll off"
              />
            </div>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle>Band distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex h-2.5 w-full overflow-hidden rounded-full border border-line bg-inset">
                  {BANDS.map((band) => {
                    const count = summary.counts[band.level];
                    if (count === 0) return null;
                    return (
                      <span
                        key={band.level}
                        className={band.bar}
                        style={{ width: `${(count / summary.total) * 100}%` }}
                        title={`${band.level}: ${count}`}
                      />
                    );
                  })}
                </div>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
                  {BANDS.map((band) => (
                    <span key={band.level} className="flex items-center gap-2 text-2xs text-muted">
                      <span className={`h-2 w-2 rounded-full ${band.bar}`} />
                      {band.level === "Medium" ? "Moderate" : band.level}
                      <span className="num text-faint">{summary.counts[band.level]}</span>
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        ) : null}

        <Card>
          <CardHeader className="border-b border-line pb-4">
            <CardTitle>Log</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : history.length === 0 ? (
              <EmptyState
                icon={Activity}
                title="No screenings recorded yet"
                description="Run a screening and the result will appear here with its risk band and detected concepts."
                action={
                  <Button asChild size="sm">
                    <Link to="/diagnose">Run a screening</Link>
                  </Button>
                }
              />
            ) : (
              <ul className="space-y-2">
                {history.map((item, index) => {
                  const stamp = formatStamp(item.createdAt);
                  return (
                    <li
                      key={item.createdAt}
                      className="animate-fade-up rounded-lg border border-line bg-inset/60 p-4 transition-colors duration-150 hover:border-line2"
                      style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2.5">
                          <RiskPill level={item.risk_level as RiskLevel} />
                          <span className="num text-xs text-faint">
                            {stamp.date} · {stamp.time}
                          </span>
                          {item.patient_name ? (
                            <span className="rounded border border-accent/30 bg-accent/10 px-2 py-0.5 text-2xs font-medium text-accent">
                              {item.patient_name}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="num rounded border border-line bg-elev px-2 py-0.5 text-2xs font-medium text-muted">
                            {(item.probability * 100).toFixed(1)}%
                          </span>
                          <button
                            type="button"
                            title="Delete entry"
                            onClick={() => void handleDelete(item.id)}
                            className="rounded border border-line p-1 text-faint transition-colors hover:border-danger/40 hover:text-danger"
                          >
                            <Trash2 className="h-3 w-3" strokeWidth={1.75} />
                          </button>
                        </div>
                      </div>

                      <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-muted">{item.text}</p>

                      {item.symptoms?.length ? (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {item.symptoms.slice(0, 5).map((symptom) => (
                            <Badge key={symptom} variant="outline">
                              {symptom}
                            </Badge>
                          ))}
                          {item.symptoms.length > 5 ? (
                            <Badge variant="outline">+{item.symptoms.length - 5}</Badge>
                          ) : null}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
          </TabsContent>

          <TabsContent value="consultations">
            <Card>
              <CardHeader className="border-b border-line pb-4">
                <div>
                  <CardTitle>Saved visits</CardTitle>
                  <CardDescription className="mt-1">
                    Every consultation you saved from the consultation screen, newest first. Re-export the PDF any time.
                  </CardDescription>
                </div>
                {consultations.length > 0 ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                      await clearConsultations();
                      setConsultations([]);
                    }}
                    className="hover:text-danger-strong"
                  >
                    <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                    Clear visits
                  </Button>
                ) : null}
              </CardHeader>
              <CardContent className="pt-4">
                {consultLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                ) : consultations.length === 0 ? (
                  <EmptyState
                    icon={Users}
                    title="No saved visits yet"
                    description="Run a consultation and press Save visit — the record lands here with its transcript and a re-exportable PDF."
                    action={
                      <Button asChild size="sm">
                        <Link to="/consultation">Start a consultation</Link>
                      </Button>
                    }
                  />
                ) : (
                  <ul className="space-y-2">
                    {consultations.map((visit, index) => {
                      const stamp = formatStamp(visit.createdAt);
                      const risk = (visit.risk_level ?? "Low") as RiskLevel;
                      return (
                        <li
                          key={visit.id ?? `${visit.createdAt}-${index}`}
                          className="animate-fade-up rounded-lg border border-line bg-inset/60 p-4 transition-colors duration-150 hover:border-line2"
                          style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex min-w-0 flex-wrap items-center gap-2.5">
                              <RiskPill level={risk} />
                              <span className="num text-xs text-faint">
                                {stamp.date} · {stamp.time}
                              </span>
                              {visit.patient_name ? (
                                <span className="rounded border border-accent/30 bg-accent/10 px-2 py-0.5 text-2xs font-medium text-accent">
                                  {visit.patient_name}
                                  {visit.patient_age ? `, ${visit.patient_age}` : ""}
                                </span>
                              ) : null}
                              {visit.spoken_language ? (
                                <span className="num rounded border border-line bg-elev px-1.5 py-0.5 text-2xs font-medium text-faint">
                                  {visit.spoken_language}
                                </span>
                              ) : null}
                              {visit.chief_complaint ? (
                                <span className="truncate text-2xs text-faint">{visit.chief_complaint}</span>
                              ) : null}
                            </div>
                            <div className="flex items-center gap-2">
                              {visit.report ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleExportConsultation(visit)}
                                >
                                  <FileDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                                  Export PDF
                                </Button>
                              ) : null}
                              <button
                                type="button"
                                title="Delete visit"
                                onClick={() => void handleDeleteConsultation(visit.id)}
                                className="rounded border border-line p-1 text-faint transition-colors hover:border-danger/40 hover:text-danger"
                              >
                                <Trash2 className="h-3 w-3" strokeWidth={1.75} />
                              </button>
                            </div>
                          </div>

                          {visit.symptom_notes?.length ? (
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {visit.symptom_notes.slice(0, 6).map((symptom) => (
                                <Badge key={symptom} variant="outline">
                                  {symptom}
                                </Badge>
                              ))}
                              {visit.symptom_notes.length > 6 ? (
                                <Badge variant="outline">+{visit.symptom_notes.length - 6}</Badge>
                              ) : null}
                            </div>
                          ) : null}
r
                          {visit.transcript?.length ? (
                            <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-faint">
                              {visit.transcript.length} transcript line
                              {visit.transcript.length === 1 ? "" : "s"} captured
                            </p>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
