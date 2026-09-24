import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, currentTheme, storedTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * Light/dark switch. Persists the choice; first visit follows the system
 * preference via the boot snippet in index.html.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? currentTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <button
      type="button"
      role="switch"
      aria-checked={theme === "dark"}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
      onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      className={cn(
        "flex h-9 items-center gap-1 rounded-lg border border-line bg-elev/70 p-1 text-xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg",
        className
      )}
    >
      <span
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-md transition-colors",
          theme === "light" ? "bg-accent text-accent-ink shadow-sm" : "text-faint"
        )}
      >
        <Sun className="h-3.5 w-3.5" strokeWidth={1.75} />
      </span>
      <span
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-md transition-colors",
          theme === "dark" ? "bg-accent text-accent-ink shadow-sm" : "text-faint"
        )}
      >
        <Moon className="h-3.5 w-3.5" strokeWidth={1.75} />
      </span>
    </button>
  );
}
