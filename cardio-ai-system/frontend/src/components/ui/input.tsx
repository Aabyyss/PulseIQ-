import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "h-9 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";

export { Input };
