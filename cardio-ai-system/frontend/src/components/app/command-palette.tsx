import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { COMMANDS, searchCommands } from "@/lib/commands";
import { NAV } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const ICONS = new Map(NAV.map((item) => [item.to, item.icon]));

/**
 * Jump to any destination without hunting for it.
 *
 * A native `<dialog>` again, for the same reasons as the More sheet: focus
 * containment, Escape and focus return are the browser's job. What is ours is
 * the keyboard model — arrows move, Enter opens, Escape closes, and the first
 * result is always selected so Enter works after typing a single word.
 */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const results = useMemo(() => searchCommands(query), [query]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      setQuery("");
      setActive(0);
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
      // Focus after the dialog is shown; a controlled input cannot take focus
      // while it is still hidden.
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      dialog.removeAttribute("open");
    }
  }, [open]);

  // Keep the selection inside the result list as it shrinks.
  useEffect(() => {
    setActive((index) => Math.min(index, Math.max(results.length - 1, 0)));
  }, [results.length]);

  function openCommand(to: string) {
    onClose();
    navigate(to);
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (results.length ? (index + 1) % results.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (results.length ? (index - 1 + results.length) % results.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = results[active];
      if (target) openCommand(target.to);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-label="Command palette"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className="fixed inset-x-3 top-[12vh] mx-auto max-h-[70dvh] w-auto max-w-lg overflow-hidden rounded-xl border border-line bg-panel p-0 text-fg shadow-pop backdrop:bg-black/50 backdrop:backdrop-blur-[2px] sm:inset-x-6"
    >
      <div className="flex items-center gap-2.5 border-b border-line px-3">
        <Search className="h-4 w-4 shrink-0 text-faint" strokeWidth={1.75} />
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls="command-results"
          aria-autocomplete="list"
          aria-label="Search destinations"
          placeholder="Search destinations…"
          className="h-12 w-full min-w-0 bg-transparent text-sm text-fg outline-none placeholder:text-faint"
        />
        <kbd className="hidden shrink-0 rounded border border-line bg-inset px-1.5 py-0.5 font-mono text-[10px] text-faint sm:block">
          Esc
        </kbd>
      </div>

      <ul
        id="command-results"
        role="listbox"
        aria-label="Destinations"
        className="max-h-[46dvh] overflow-y-auto p-1.5"
      >
        {results.length === 0 ? (
          <li className="px-3 py-6 text-center text-xs text-faint">
            Nothing matches “{query}”. Try a destination name.
          </li>
        ) : (
          results.map((command, index) => {
            const Icon = ICONS.get(command.to) ?? Search;
            return (
              <li key={command.id} role="option" aria-selected={index === active}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(index)}
                  onClick={() => openCommand(command.to)}
                  className={cn(
                    "flex min-h-[44px] w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                    index === active ? "bg-elev text-fg" : "text-muted hover:bg-elev/60"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
                  <span className="min-w-0 flex-1 truncate">{command.label}</span>
                  {index === active ? (
                    <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-faint" strokeWidth={1.75} />
                  ) : null}
                </button>
              </li>
            );
          })
        )}
      </ul>

      <div className="hidden items-center gap-4 border-t border-line px-3 py-2 text-2xs text-faint sm:flex">
        <span>
          <kbd className="font-mono">↑↓</kbd> to move
        </span>
        <span>
          <kbd className="font-mono">↵</kbd> to open
        </span>
        <span className="ml-auto">{COMMANDS.length} destinations</span>
      </div>
    </dialog>
  );
}
