import { cn } from "@/lib/utils";
import { providerLabel, useEngineStatus } from "@/lib/engine";

/**
 * Engine readiness, shown in the top bar at every width and again at the foot of
 * the desktop rail. One component so the two never disagree about whether the
 * backend is reachable.
 */
export function EngineStatus({ compact = false }: { compact?: boolean }) {
  const { status, provider } = useEngineStatus();

  const copy =
    status === "checking" ? "Connecting" : status === "online" ? "Engine ready" : "Engine offline";
  const dot = status === "online" ? "bg-ok" : status === "offline" ? "bg-danger" : "bg-warn";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-line bg-inset px-2.5 py-1.5",
        compact && "border-transparent bg-transparent px-0 py-0"
      )}
      title={providerLabel(provider)}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot, status === "online" && "animate-pulse-soft")} />
      <span className="truncate text-2xs font-medium text-muted">{copy}</span>
      {status === "online" && !compact ? (
        <span className="ml-auto truncate rounded border border-line bg-elev px-1.5 py-px text-[10px] font-medium text-faint">
          {providerLabel(provider)}
        </span>
      ) : null}
    </div>
  );
}
