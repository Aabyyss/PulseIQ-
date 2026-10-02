import { useEffect } from "react";
import { SITE_NAME, SITE_URL } from "@/lib/site";

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

/**
 * Per-page <title>, meta description and Open Graph tags. The app is a SPA,
 * so crawlers and the browser tab both read these from the live DOM; index.html
 * carries the static defaults for the first paint.
 */
export function usePageMeta(title: string, description: string) {
  useEffect(() => {
    const fullTitle = `${title} · ${SITE_NAME}`;
    const path = window.location.pathname;
    document.title = fullTitle;
    upsertMeta("name", "description", description);
    upsertMeta("property", "og:title", fullTitle);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:url", `${SITE_URL}${path}`);
    upsertMeta("property", "og:site_name", SITE_NAME);
  }, [title, description]);
}
