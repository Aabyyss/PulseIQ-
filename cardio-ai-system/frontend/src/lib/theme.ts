/**
 * Theme controller for the class-based light/dark system.
 *
 * `applyTheme` toggles the `dark` class on <html>; `THEME_BOOT_SNIPPET` is
 * inlined into index.html so the stored preference paints before React mounts
 * (no light-flash on load for dark-mode users).
 */

export type Theme = "light" | "dark";

const STORAGE_KEY = "pulseiq.theme";

/**
 * The browser's own chrome colour, per palette. An installed app keeps its
 * status bar and address bar in the app's colour; leaving it dark under a white
 * page is the most visible way a web app stops looking installed.
 */
export const THEME_COLORS: Record<Theme, string> = {
  dark: "#0B0C0F",
  light: "#FFFFFF"
};

function syncBrowserColor(theme: Theme) {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLORS[theme]);
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  syncBrowserColor(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* storage unavailable (private mode) — preference just won't persist */
  }
}

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

/** Runs before React mounts to apply the saved preference (or system default). */
export const THEME_BOOT_SNIPPET = `(function(){try{var t=localStorage.getItem("pulseiq.theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}var d=document.documentElement;d.classList.toggle("dark",t==="dark");var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",t==="dark"?"#0B0C0F":"#FFFFFF");}catch(e){document.documentElement.classList.add("dark");}})();`;
