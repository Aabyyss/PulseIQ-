import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, currentTheme, storedTheme, THEME_BOOT_SNIPPET, THEME_COLORS } from "./theme";

/**
 * The theme controller is what the UI audit now depends on for its second
 * palette: the sweep writes `pulseiq.theme` before the document boots and fails
 * unless the page lands on that palette. These cases cover the three pieces that
 * path uses — the stored value, the class, and the boot snippet's preference
 * order (stored value first, system second).
 */

const STORAGE_KEY = "pulseiq.theme";

function setSystemPrefersLight(prefersLight: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: prefersLight && query.includes("light"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
}

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.unstubAllGlobals();
});

describe("theme controller", () => {
  it("applies the theme to <html> and remembers it", () => {
    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBe("light");
    expect(currentTheme()).toBe("light");

    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("reads only the two palette names back from storage", () => {
    localStorage.setItem(STORAGE_KEY, "light");
    expect(storedTheme()).toBe("light");
    localStorage.setItem(STORAGE_KEY, "dark");
    expect(storedTheme()).toBe("dark");
    localStorage.setItem(STORAGE_KEY, "solarized");
    expect(storedTheme()).toBeNull();
  });
});

describe("boot snippet", () => {
  const run = () => new Function(THEME_BOOT_SNIPPET)();

  it("prefers the stored choice over the system preference", () => {
    setSystemPrefersLight(true);
    localStorage.setItem(STORAGE_KEY, "dark");
    run();
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    localStorage.setItem(STORAGE_KEY, "light");
    document.documentElement.classList.add("dark");
    run();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("follows the system preference when nothing is stored", () => {
    setSystemPrefersLight(false);
    run();
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    document.documentElement.classList.remove("dark");
    setSystemPrefersLight(true);
    run();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("moves the browser chrome colour with the palette", () => {
    document.head.querySelector('meta[name="theme-color"]')?.remove();
    const meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    meta.setAttribute("content", THEME_COLORS.dark);
    document.head.appendChild(meta);

    applyTheme("light");
    expect(meta.getAttribute("content")).toBe(THEME_COLORS.light);
    applyTheme("dark");
    expect(meta.getAttribute("content")).toBe(THEME_COLORS.dark);
    meta.remove();
  });

  it("falls back to dark when storage throws", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    run();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    getItem.mockRestore();
  });
});
