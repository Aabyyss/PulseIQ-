import { cn } from "@/lib/utils";

/**
 * The PulseIQ mark: an ECG deflection inside a dark tile.
 * Rendered as inline SVG so it stays crisp at every size and needs no asset pipeline.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] border border-line2/80 bg-elev shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]",
        className
      )}
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="h-5 w-5">
        <path
          d="M3.6 17.2h4.6l2.3-5.9 3.5 12 3-7.9 2 4.4h9.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-accent"
        />
      </svg>
    </span>
  );
}

export function Wordmark({ subtitle = "Clinical Workspace" }: { subtitle?: string }) {
  return (
    <span className="flex min-w-0 flex-col">
      <span className="text-[15px] font-semibold leading-none tracking-[-0.02em] text-fg">PulseIQ</span>
      <span className="mt-1 truncate text-2xs font-medium uppercase tracking-[0.16em] text-faint">
        {subtitle}
      </span>
    </span>
  );
}
