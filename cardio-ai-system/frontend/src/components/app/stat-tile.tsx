import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function StatTile({
  label,
  value,
  unit,
  icon: Icon,
  tone = "neutral",
  hint,
  className
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon?: LucideIcon;
  tone?: "neutral" | "accent" | "danger" | "warn" | "ok";
  hint?: string;
  className?: string;
}) {
  const toneClass = {
    neutral: "text-fg",
    accent: "text-accent",
    danger: "text-danger-strong",
    warn: "text-warn-strong",
    ok: "text-ok-strong"
  }[tone];

  return (
    <div className={cn("panel-flat px-4 py-3.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="label truncate">{label}</p>
        {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 text-faint" strokeWidth={1.75} /> : null}
      </div>
      <p className={cn("num mt-2 flex items-baseline gap-1 text-xl font-semibold", toneClass)}>
        {value}
        {unit ? <span className="text-xs font-medium text-faint">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-2xs text-faint">{hint}</p> : null}
    </div>
  );
}
