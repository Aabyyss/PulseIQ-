import { useEffect } from "react";
import { SITE_NAME, SITE_URL } from "@/lib/site";

export type MetaTag = { attr: "name" | "property"; key: string; content: string };

/** The image every route shares unless it names its own. */
export const DEFAULT_SOCIAL_IMAGE = "/og-image.png";

/**
 * The tags a page needs, computed rather than written out at each call site.
 *
 * The hook used to update `og:title`/`og:description`/`og:url` and leave the
 * Twitter pair at whatever `index.html` shipped, so a link shared from
 * /consultation showed that route's title on one platform and the site's default
 * on another. The list below is the whole set in one place, including a canonical
 * link, which nothing set at all: a single-page app serves every route from the
 * same URL, and the canonical is what tells a crawler which one it is reading.
 */
export function pageMetaTags(options: {
  title: string;
  description: string;
  path: string;
  imagePath?: string;
}): { title: string; url: string; tags: MetaTag[] } {
  const fullTitle = `${options.title} · ${SITE_NAME}`;
  const url = `${SITE_URL}${options.path}`;
  const image = `${SITE_URL}${options.imagePath ?? DEFAULT_SOCIAL_IMAGE}`;
  return {
    title: fullTitle,
    url,
    tags: [
      { attr: "name", key: "description", content: options.description },
      { attr: "property", key: "og:title", content: fullTitle },
      { attr: "property", key: "og:description", content: options.description },
      { attr: "property", key: "og:url", content: url },
      { attr: "property", key: "og:site_name", content: SITE_NAME },
      { attr: "property", key: "og:image", content: image },
      { attr: "property", key: "og:image:alt", content: `${fullTitle} — cardiac screening workspace` },
      { attr: "name", key: "twitter:card", content: "summary_large_image" },
      { attr: "name", key: "twitter:title", content: fullTitle },
      { attr: "name", key: "twitter:description", content: options.description },
      { attr: "name", key: "twitter:image", content: image }
    ]
  };
}

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

/**
 * Per-page <title>, meta description, Open Graph and Twitter tags, and the
 * canonical URL. The app is a SPA, so crawlers and the browser tab both read
 * these from the live DOM; index.html carries the static defaults for the first
 * paint.
 */
export function usePageMeta(title: string, description: string) {
  useEffect(() => {
    const meta = pageMetaTags({ title, description, path: window.location.pathname });
    document.title = meta.title;
    for (const tag of meta.tags) {
      upsertMeta(tag.attr, tag.key, tag.content);
    }
    upsertCanonical(meta.url);
  }, [title, description]);
}
