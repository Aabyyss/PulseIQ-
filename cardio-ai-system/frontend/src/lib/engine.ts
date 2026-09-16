import { useEffect, useState } from "react";

export type EngineProvider = "ollama" | "gemini" | "local" | "unknown";
export type EngineStatus = "checking" | "online" | "offline";

export interface EngineState {
  status: EngineStatus;
  provider: EngineProvider;
}

const PROVIDER_LABELS: Record<EngineProvider, string> = {
  local: "Built-in engine",
  ollama: "Local model",
  gemini: "Gemini",
  unknown: "Unknown provider"
};

export function providerLabel(provider: EngineProvider): string {
  return PROVIDER_LABELS[provider] ?? PROVIDER_LABELS.unknown;
}

function normalise(value: unknown): EngineProvider {
  return value === "ollama" || value === "gemini" || value === "local" ? value : "unknown";
}

/**
 * Polls the local API so the shell can report whether the reasoning engine is
 * reachable. A miss is a normal state, not an error — the UI keeps working.
 */
export function useEngineStatus(pollMs = 20000): EngineState {
  const [state, setState] = useState<EngineState>({ status: "checking", provider: "unknown" });

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        const response = await fetch("/api/health", { signal: AbortSignal.timeout(4000) });
        if (!response.ok) throw new Error("unhealthy");
        const body = (await response.json()) as { ai_provider?: string };
        if (cancelled) return;
        setState({ status: "online", provider: normalise(body.ai_provider) });
      } catch {
        if (cancelled) return;
        setState({ status: "offline", provider: "unknown" });
      }
    };

    void probe();
    const timer = window.setInterval(probe, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pollMs]);

  return state;
}
