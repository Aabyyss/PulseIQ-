import { useEffect, useState } from "react";
import { AlertCircle, Boxes, Cpu } from "lucide-react";
import { fetchResearchAgents } from "@/lib/api";
import type { ResearchAgent } from "@/lib/types";
import { EmptyState } from "@/components/app/empty-state";
import { PageHeader } from "@/components/app/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function ResearchAgentsPage() {
  const [agents, setAgents] = useState<ResearchAgent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchResearchAgents()
      .then((items) => setAgents(items))
      .catch(() => setError("The registry could not be loaded from the backend."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="System"
        icon={Boxes}
        title="Agent registry"
        description="Each capability in PulseIQ is an isolated, rule-grounded module with an explicit responsibility. Modules can be replaced or extended without disturbing the rest of the pipeline."
      />

      {error ? (
        <Alert variant="destructive" className="mb-5">
          <AlertCircle />
          <AlertTitle>Registry unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Card key={index}>
              <CardContent className="space-y-3 pt-5">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : agents.length === 0 && !error ? (
        <EmptyState
          icon={Cpu}
          title="No agents reported"
          description="The backend responded, but the registry returned no modules."
        />
      ) : (
        <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent, index) => (
            <article
              key={agent.name}
              className="group animate-fade-up bg-panel p-5 transition-colors duration-150 hover:bg-elev/50"
              style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
            >
              <p className="num label">{String(index + 1).padStart(2, "0")}</p>
              <h3 className="mt-2.5 text-sm font-semibold text-fg">{agent.name}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{agent.focus}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
