import { Link } from "react-router-dom";
import { ArrowLeft, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePageMeta } from "@/lib/usePageMeta";

/**
 * Custom 404. Unknown routes land here instead of silently bouncing to the
 * overview, so a mistyped or stale link explains itself and offers a way back.
 */
export function NotFoundPage() {
  usePageMeta(
    "Page not found",
    "This PulseIQ link does not exist. Check the address or head back to the workspace overview."
  );

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-inset">
        <SearchX className="h-5 w-5 text-accent" strokeWidth={1.75} />
      </span>
      <p className="label mt-5">Error 404</p>
      <h1 className="mt-2 text-2xl font-semibold text-fg">This page doesn't exist</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
        The link may be out of date or the address may have a typo. Nothing was lost — your
        records and consultations are exactly where you left them.
      </p>
      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <Button asChild>
          <Link to="/" className="inline-flex items-center gap-2">
            <ArrowLeft className="h-4 w-4" strokeWidth={1.9} />
            Back to overview
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/history">Open history</Link>
        </Button>
      </div>
    </div>
  );
}
