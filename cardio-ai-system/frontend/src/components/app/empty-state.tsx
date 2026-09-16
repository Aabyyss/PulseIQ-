import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line px-6 py-10 text-center",
        className
      )}
    >
      {Icon ? (
        <span className="mb-1 flex h-9 w-9 items-center justify-center rounded-full border border-line bg-elev">
          <Icon className="h-4 w-4 text-faint" strokeWidth={1.75} />
        </span>
      ) : null}
      <p className="text-sm font-medium text-muted">{title}</p>
      {description ? <p className="max-w-sm text-xs leading-relaxed text-faint">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
