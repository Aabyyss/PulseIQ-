import { useEffect, useState } from "react";
import { Bot, FlaskConical } from "lucide-react";
import { fetchResearchAgents } from "@/lib/api";
import type { ResearchAgent } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function ResearchAgentsPage() {
  const [agents, setAgents] = useState<ResearchAgent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchResearchAgents()
      .then((items) => setAgents(items))
      .catch(() => setError("Could not load research agents from the backend."));
  }, []);

  return (
    <Card className="card-animate border-slate-800 bg-slate-900/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-white">
          <FlaskConical className="h-5 w-5 text-teal-400" />
          Research agent registry
        </CardTitle>
        <CardDescription>
          Modular agent architecture powering PulseIQ — each agent is an independent, rule-grounded module ready for research extension.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert variant="destructive" className="mb-3">
            <AlertTitle>Load error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent, i) => (
            <div
              key={agent.name}
              className="card-animate rounded-xl border border-slate-800 bg-slate-950/50 p-4 transition-colors hover:border-teal-500/40"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <p className="flex items-start gap-2 font-medium text-white">
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-teal-400" />
                {agent.name}
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{agent.focus}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
