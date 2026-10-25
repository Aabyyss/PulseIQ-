import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The heading above a feed section: eyebrow, title, optional trailing action.
 *
 * Overview sections used to hand-roll this — three slightly different gaps and
 * two label treatments on one screen — which is the kind of drift that makes a
 * page feel assembled rather than designed. One component, one rhythm.
 */
export function SectionHeading({
  id,
  eyebrow,
  title,
  icon: Icon,
  action,
  className
}: {
  /** Lets a section point `aria-labelledby` at this heading. */
  id?: string;
  eyebrow?: string;
  title: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="label">{eyebrow}</p> : null}
        <h2 id={id} className="mt-1.5 flex items-center gap-2 text-lg font-semibold">
          {Icon ? <Icon className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} /> : null}
          <span className="truncate">{title}</span>
        </h2>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
