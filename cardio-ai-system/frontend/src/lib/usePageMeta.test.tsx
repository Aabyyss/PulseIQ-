import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SOCIAL_IMAGE, pageMetaTags, usePageMeta } from "@/lib/usePageMeta";
import { SITE_NAME, SITE_URL } from "@/lib/site";

/**
 * These tags are what a shared link looks like before anyone opens it, and the
 * failure they guard against is a half-updated set: Open Graph moved to the
 * current page while Twitter kept the site default, and no canonical URL was set
 * at all.
 */
function content(selector: string): string | null {
  return document.head.querySelector(selector)?.getAttribute("content") ?? null;
}

describe("pageMetaTags", () => {
  it("describes one route consistently across both platforms", () => {
    const meta = pageMetaTags({ title: "Live consultation", description: "Capture a visit", path: "/consultation" });
    const byKey = new Map(meta.tags.map((tag) => [tag.key, tag.content]));

    expect(meta.title).toBe(`Live consultation · ${SITE_NAME}`);
    expect(meta.url).toBe(`${SITE_URL}/consultation`);
    expect(byKey.get("og:title")).toBe(meta.title);
    expect(byKey.get("twitter:title")).toBe(meta.title);
    expect(byKey.get("og:description")).toBe("Capture a visit");
    expect(byKey.get("twitter:description")).toBe("Capture a visit");
    expect(byKey.get("og:image")).toBe(`${SITE_URL}${DEFAULT_SOCIAL_IMAGE}`);
    expect(byKey.get("twitter:image")).toBe(`${SITE_URL}${DEFAULT_SOCIAL_IMAGE}`);
    expect(byKey.get("twitter:card")).toBe("summary_large_image");
  });

  it("allows a route to name its own share image", () => {
    const meta = pageMetaTags({ title: "T", description: "D", path: "/x", imagePath: "/custom.png" });
    expect(meta.tags.find((tag) => tag.key === "og:image")?.content).toBe(`${SITE_URL}/custom.png`);
  });
});

describe("usePageMeta", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    window.history.replaceState({}, "", "/history");
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    document.head.querySelectorAll('link[rel="canonical"]').forEach((el) => el.remove());
    vi.unstubAllGlobals();
  });

  function Probe({ title, description }: { title: string; description: string }) {
    usePageMeta(title, description);
    return null;
  }

  it("writes the document title, both platforms' tags and the canonical link", () => {
    act(() => {
      root.render(<Probe title="History" description="Past screenings" />);
    });

    expect(document.title).toBe(`History · ${SITE_NAME}`);
    expect(content('meta[name="description"]')).toBe("Past screenings");
    expect(content('meta[property="og:url"]')).toBe(`${SITE_URL}/history`);
    expect(content('meta[name="twitter:title"]')).toBe(`History · ${SITE_NAME}`);
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(
      `${SITE_URL}/history`
    );
  });

  it("reuses the existing tags instead of appending a second copy", () => {
    act(() => {
      root.render(<Probe title="History" description="Past screenings" />);
    });
    act(() => {
      root.render(<Probe title="Notes" description="Private notes" />);
    });

    expect(document.head.querySelectorAll('meta[property="og:title"]')).toHaveLength(1);
    expect(content('meta[property="og:title"]')).toBe(`Notes · ${SITE_NAME}`);
    expect(document.head.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
  });
});
