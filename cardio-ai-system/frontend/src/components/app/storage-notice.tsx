import { useState } from "react";
import { Link } from "react-router-dom";
import { Cookie, X } from "lucide-react";

const DISMISS_KEY = "pulseiq.storageNotice.v1";

/**
 * First-visit notice in place of a cookie banner: PulseIQ sets no cookies —
 * auth is a bearer token in local storage — so the notice says exactly that
 * and points at the privacy policy. Dismissal is remembered locally.
 *
 * Positioning: floating bottom-right only where it provably clears centred
 * page content (≥640px wide AND ≥850px tall). On narrower or shorter
 * viewports it drops into normal flow (position: static) at the top of the
 * document, so it can never sit on top of a primary action like the Sign in
 * button — the two media branches are disjoint so their margins never race.
 */
export function StorageNotice() {
  const [visible, setVisible] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) !== "1";
    } catch {
      return false; // private mode / storage blocked → don't nag
    }
  });

  if (!visible) return null;

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* storage blocked — the notice simply returns next time */
    }
    setVisible(false);
  }

  return (
    <aside
      role="region"
      aria-label="Data storage notice"
      className="fixed inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+4.5rem)] z-50 mx-auto max-w-xl rounded-xl border border-line bg-panel/95 p-4 shadow-panel backdrop-blur-md sm:inset-x-auto sm:right-5 sm:bottom-5 max-sm:static max-sm:m-[12px] [@media(min-width:640px)_and_(max-height:849px)]:static [@media(min-width:640px)_and_(max-height:849px)]:m-[12px_auto]"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-line bg-inset">
          <Cookie className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-fg">No cookies here</p>
          <p className="mt-1 text-2xs leading-relaxed text-muted">
            PulseIQ runs entirely on this device and sets no tracking cookies. Your session and
            preferences live in this browser's local storage.{" "}
            <Link to="/privacy" className="font-medium text-accent hover:underline">
              Read the privacy policy
            </Link>
            .
          </p>
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              onClick={dismiss}
              className="rounded-md border border-line bg-elev px-2.5 py-1 text-2xs font-medium text-fg transition-colors hover:bg-elev/70"
            >
              Got it
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="text-2xs text-faint transition-colors hover:text-muted"
            >
              Dismiss
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss storage notice"
          className="shrink-0 rounded-md p-1.5 text-faint transition-colors hover:bg-elev hover:text-fg"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.9} />
        </button>
      </div>
    </aside>
  );
}
