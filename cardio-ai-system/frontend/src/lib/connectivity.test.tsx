import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectionNotice } from "@/components/app/connection-notice";
import { isOnline } from "@/lib/connectivity";

/**
 * The notice exists for the failure that looks like success: an installed app
 * with a cached shell opens fine while the engine is unreachable, so a save
 * fails after the clinician has already moved on. The test pins the two states
 * and the event path that switches between them.
 */
function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { value, configurable: true });
}

describe("ConnectionNotice", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    setOnline(true);
    vi.unstubAllGlobals();
  });

  it("reports the browser's connectivity", () => {
    setOnline(false);
    expect(isOnline()).toBe(false);
    setOnline(true);
    expect(isOnline()).toBe(true);
  });

  it("stays out of the way while online", () => {
    setOnline(true);
    act(() => root.render(<ConnectionNotice />));
    expect(container.textContent).not.toContain("Offline");
  });

  it("appears while offline and disappears when the connection returns", () => {
    setOnline(false);
    act(() => root.render(<ConnectionNotice />));
    expect(container.textContent).toContain("Offline");
    expect(container.querySelector('[role="status"]')?.getAttribute("aria-live")).toBe("polite");

    act(() => {
      setOnline(true);
      window.dispatchEvent(new Event("online"));
    });
    expect(container.textContent).not.toContain("Offline");
  });

  it("reacts to going offline while mounted", () => {
    setOnline(true);
    act(() => root.render(<ConnectionNotice />));
    act(() => {
      setOnline(false);
      window.dispatchEvent(new Event("offline"));
    });
    expect(container.textContent).toContain("Offline");
  });
});
