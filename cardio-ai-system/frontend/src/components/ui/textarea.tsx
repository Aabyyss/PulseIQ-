import * as React from "react";
import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[92px] w-full resize-y rounded-lg border border-line bg-inset px-3 py-2.5 text-sm leading-relaxed text-fg shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";

export { Textarea };
