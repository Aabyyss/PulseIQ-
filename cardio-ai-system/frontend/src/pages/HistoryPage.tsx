import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Clock, Database, ShieldCheck, Trash2, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { StatTile } from "@/components/app/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { loadHistory, saveHistory } from "@/lib/history";

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
  const [history, setHistory] = useState(() => loadHistory());

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

  function clearHistory() {
    saveHistory([]);
    setHistory([]);
  }

  return (
    <div>
      <PageHeader
        eyebrow="Records"
        icon={Clock}
        title="Screening history"
        description="The most recent screenings recorded on this device, newest first. Entries are held in local browser storage and are never uploaded."
        actions={
          history.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clearHistory} className="hover:text-danger-strong">
              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              Clear history
            </Button>
          ) : null
        }
      />

      <div className="space-y-5">
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
                value="20"
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
            {history.length === 0 ? (
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
                        </div>
                        <span className="num rounded border border-line bg-elev px-2 py-0.5 text-2xs font-medium text-muted">
                          {(item.probability * 100).toFixed(1)}%
                        </span>
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
      </div>
    </div>
  );
}
