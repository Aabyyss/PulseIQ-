import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Analytics hook — intentionally disabled by default.
 *
 * The app ships no third-party tracker (see the privacy policy). To enable
 * first-party page-view logging later, point `COLLECT_URL` at an endpoint
 * you control; while it is null, `track()` is a no-op and nothing leaves
 * the browser.
 */
const COLLECT_URL: string | null = null;

export function track(event: string, payload?: Record<string, string>) {
  if (!COLLECT_URL) return;
  try {
    void fetch(COLLECT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, path: window.location.pathname, ...payload }),
      keepalive: true
    }).catch(() => {
      /* analytics must never break the app */
    });
  } catch {
    /* ignore */
  }
}

/** Route-change page-view tracker. Mount once, near the router root. */
export function PageViewTracker() {
  const location = useLocation();

  useEffect(() => {
    track("page_view", { path: location.pathname });
  }, [location.pathname]);

  return null;
}
