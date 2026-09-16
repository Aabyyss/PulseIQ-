import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-2xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-accent/25 bg-accent/10 text-accent",
        secondary: "border-line bg-elev text-muted",
        destructive: "border-danger/25 bg-danger/10 text-danger-strong",
        warn: "border-warn/25 bg-warn/10 text-warn-strong",
        ok: "border-ok/25 bg-ok/10 text-ok-strong",
        info: "border-info/25 bg-info/10 text-info-strong",
        outline: "border-line2 bg-transparent text-muted"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  /** Renders a leading status dot — pair with the variant that carries the meaning. */
  dot?: boolean;
}

function Badge({ className, variant, dot = false, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" /> : null}
      {children}
    </span>
  );
}

export { Badge, badgeVariants };
