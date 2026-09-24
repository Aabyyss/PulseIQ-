import { cn } from "@/lib/utils";

/**
 * The PulseIQ mark: a white ECG deflection with a terminal beat dot inside a
 * violet-gradient tile. Rendered as inline SVG so it stays crisp at every
 * size and needs no asset pipeline. The gradient id is fixed; if two marks
 * ever render on the same page it stays valid because they share the
 * definition.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] border border-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_2px_8px_-2px_rgba(109,40,217,0.6)]",
        className
      )}
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="absolute inset-0 h-full w-full rounded-[9px]">
        <defs>
          <linearGradient id="pulseiq-tile" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#8B5CF6" />
            <stop offset="0.55" stopColor="#7C3AED" />
            <stop offset="1" stopColor="#4C1D95" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill="url(#pulseiq-tile)" />
        <path
          d="M5 17.4h4.3l2.2-5.6 3.3 11.4 2.8-7.5 1.9 4.3 1.2-2.2h6.3"
          fill="none"
          stroke="#fff"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="26.6" cy="17.4" r="1.5" fill="#fff" />
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
