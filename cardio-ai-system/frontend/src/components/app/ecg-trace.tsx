import { cn } from "@/lib/utils";

/**
 * A slow-moving ECG trace. Used sparingly as an ambient "device is alive" cue —
 * it animates a dash offset rather than scaling or fading, so it reads as signal.
 */
export function EcgTrace({ className, speed = "5.5s" }: { className?: string; speed?: string }) {
  return (
    <svg
      viewBox="0 0 620 60"
      preserveAspectRatio="none"
      className={cn("trace h-14 w-full text-accent/60", className)}
      aria-hidden
    >
      <path
        d="M0 34 H96 l10 -20 l12 40 l10 -30 l9 10 H268 l10 -20 l12 40 l10 -30 l9 10 H468 l10 -20 l12 40 l10 -30 l9 10 H620"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ animationDuration: speed }}
      />
    </svg>
  );
}
