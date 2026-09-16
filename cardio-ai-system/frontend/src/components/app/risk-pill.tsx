import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type RiskLevel = "Low" | "Medium" | "High";

const TONES: Record<RiskLevel, { variant: "ok" | "warn" | "destructive"; label: string }> = {
  Low: { variant: "ok", label: "Low risk" },
  Medium: { variant: "warn", label: "Moderate risk" },
  High: { variant: "destructive", label: "High risk" }
};

export function riskVariant(level: RiskLevel) {
  return TONES[level]?.variant ?? "secondary";
}

export function RiskPill({
  level,
  withLabel = true,
  className
}: {
  level: RiskLevel;
  withLabel?: boolean;
  className?: string;
}) {
  const tone = TONES[level] ?? TONES.Low;
  return (
    <Badge variant={tone.variant} dot className={className}>
      {withLabel ? tone.label : level}
    </Badge>
  );
}
