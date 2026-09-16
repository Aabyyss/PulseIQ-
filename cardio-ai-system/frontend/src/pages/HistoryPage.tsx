import { useMemo } from "react";
import { Clock, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { loadHistory, saveHistory } from "@/lib/history";

export function HistoryPage() {
  const history = useMemo(() => loadHistory(), []);

  const stats = useMemo(() => {
    if (history.length === 0) return null;
    const high = history.filter((h) => h.risk_level === "High").length;
    const avg = history.reduce((sum, h) => sum + h.probability, 0) / history.length;
    return { total: history.length, high, avg };
  }, [history]);

  return (
    <div className="space-y-5">
      {stats ? (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Total screenings", value: String(stats.total), color: "text-white" },
            { label: "High risk flags", value: String(stats.high), color: "text-rose-400" },
            { label: "Avg risk score", value: `${(stats.avg * 100).toFixed(0)}%`, color: "text-teal-300" },
          ].map((s) => (
            <Card key={s.label} className="border-slate-800 bg-slate-900/50">
              <CardContent className="p-4 text-center">
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-slate-500">{s.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      <Card className="card-animate border-slate-800 bg-slate-900/50">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-white">
              <Clock className="h-5 w-5 text-teal-400" />
              Screening history
            </CardTitle>
            <CardDescription>Saved locally in your browser — never uploaded anywhere.</CardDescription>
          </div>
          {history.length > 0 ? (
            <Button
              size="sm"
              variant="ghost"
              className="text-slate-400 hover:bg-rose-500/10 hover:text-rose-300"
              onClick={() => {
                saveHistory([]);
                window.location.reload();
              }}
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Clear
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-3">
          {history.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-800 py-10 text-center">
              <p className="text-sm text-slate-500">No screenings yet.</p>
              <p className="text-xs text-slate-600">Run a screening and it will appear here.</p>
            </div>
          ) : null}
          {history.map((item) => (
            <div
              key={item.createdAt}
              className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 transition-colors hover:border-slate-700"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-white">{new Date(item.createdAt).toLocaleString()}</p>
                <Badge
                  variant={item.risk_level === "High" ? "destructive" : item.risk_level === "Medium" ? "secondary" : "default"}
                >
                  {item.risk_level} risk
                </Badge>
              </div>
              <p className="mb-2 line-clamp-2 text-sm text-slate-400">{item.text}</p>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span className="rounded bg-slate-900 px-2 py-0.5">Probability {(item.probability * 100).toFixed(1)}%</span>
                {item.symptoms?.slice(0, 4).map((s) => (
                  <span key={s} className="rounded bg-slate-900 px-2 py-0.5 text-teal-300">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
