import { useEffect, useRef, useState } from "react";
import { ArrowRight, MoreHorizontal, X } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { LogoMark, Wordmark } from "@/components/app/logo";
import { EngineStatus } from "@/components/app/engine-status";
import { NAV, PRIMARY_NAV, SECONDARY_NAV, activeItem, isSecondaryRoute } from "@/lib/navigation";
import { cn } from "@/lib/utils";

/**
 * The workspace's only navigation, presented two ways from one list.
 *
 * Below `lg` it is an app-style bar fixed to the bottom edge: five destinations
 * — the ones a session actually touches — plus a More control that opens the
 * remaining four. Nine items in one row was a scroll strip that hid the last
 * three destinations on a phone; five is what Material's navigation bar is
 * specified for, and it leaves every target at least a fifth of the width.
 *
 * From `lg` up the same list becomes the labelled rail down the left edge,
 * which is where a desktop app puts navigation. The bar's items are hidden
 * there and the rail's are hidden below it; both are in the DOM, so the audit's
 * "nine destinations, one current" check holds at every width.
 *
 * The fixed bar adds `env(safe-area-inset-bottom)` so it clears the home
 * indicator on an edge-to-edge phone viewport, and the rail is sticky rather
 * than fixed: it is in the layout flow, so no content can end up underneath it.
 */
export function WorkspaceNav() {
  const { pathname } = useLocation();
  const active = activeItem(pathname);
  const inShelf = isSecondaryRoute(pathname);
  const [moreOpen, setMoreOpen] = useState(false);

  // A route change closes the sheet; navigating from it should land on the new
  // page, not on a sheet covering it.
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  return (
    <>
      <nav
        aria-label="Workspace"
        className={cn(
          "fixed inset-x-0 bottom-0 z-40 border-t border-line bg-canvas/95 backdrop-blur-md",
          // Rail presentation
          "lg:sticky lg:inset-x-auto lg:bottom-auto lg:top-0 lg:z-30 lg:h-dvh lg:w-[232px] lg:shrink-0",
          "lg:border-r lg:border-t-0 lg:bg-canvas/60 lg:backdrop-blur-none xl:w-[248px]"
        )}
      >
        <div className="flex h-full flex-col">
          {/* The brand lives in the rail on desktop and in the top bar below it. */}
          <Link
            to="/"
            aria-label="PulseIQ overview"
            className="hidden h-16 items-center gap-2.5 px-5 lg:flex"
          >
            <LogoMark className="h-7 w-7" />
            <Wordmark />
          </Link>

          <ul
            className={cn(
              "no-scrollbar flex w-full items-stretch px-1",
              "pb-[env(safe-area-inset-bottom)]",
              "lg:min-h-0 lg:flex-1 lg:flex-col lg:gap-0.5 lg:overflow-y-auto lg:px-3 lg:pb-0 lg:pt-2"
            )}
          >
            {NAV.map((item) => (
              <li
                key={item.to}
                className={cn(
                  "min-w-0 flex-1 lg:flex-none",
                  // Secondary destinations are one tap away through More below
                  // `lg`, and ordinary rail items above it.
                  SECONDARY_NAV.some((entry) => entry.to === item.to) && "hidden lg:block"
                )}
              >
                <NavLink
                  to={item.to}
                  end={item.end}
                  data-active={active?.to === item.to}
                  // The phone bar prints short labels; the accessible name stays
                  // the full destination so screen readers and the audit agree.
                  aria-label={item.label}
                  aria-current={active?.to === item.to ? "page" : undefined}
                  title={item.label}
                  className={({ isActive }) =>
                    cn(
                      "group relative flex h-[56px] flex-col items-center justify-center gap-1 rounded-lg px-1 text-[10px] transition-colors duration-150",
                      "lg:h-10 lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:text-sm lg:font-medium",
                      isActive ? "text-accent" : "text-faint hover:text-muted lg:hover:bg-elev/70"
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span
                        aria-hidden="true"
                        className={cn(
                          "absolute inset-x-4 top-0 h-[2px] rounded-b-full bg-accent transition-opacity duration-200 lg:hidden",
                          isActive ? "opacity-100" : "opacity-0"
                        )}
                      />
                      <span
                        aria-hidden="true"
                        className={cn(
                          "absolute left-0 top-1/2 hidden h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent lg:block",
                          isActive ? "opacity-100" : "opacity-0"
                        )}
                      />
                      <span
                        className={cn(
                          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-150",
                          isActive ? "bg-accent/15 lg:bg-transparent" : "group-hover:bg-elev/70 lg:group-hover:bg-transparent"
                        )}
                      >
                        <item.icon
                          className={cn(item.primary ? "h-[19px] w-[19px] lg:h-[18px] lg:w-[18px]" : "h-[17px] w-[17px] lg:h-[18px] lg:w-[18px]")}
                          strokeWidth={item.primary ? 2 : 1.75}
                        />
                      </span>
                      <span className={cn("max-w-full truncate leading-none", item.primary && "font-semibold lg:font-medium")}>
                        {/* Full labels in the rail, short ones in the bar. */}
                        <span className="lg:hidden">{item.short}</span>
                        <span className="hidden lg:inline">{item.label}</span>
                      </span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}

            {/* Phone-only overflow control. Its dot is the only visible sign
                that the current page lives behind it. */}
            <li className="min-w-0 flex-1 lg:hidden">
              <button
                type="button"
                onClick={() => setMoreOpen(true)}
                aria-haspopup="dialog"
                aria-expanded={moreOpen}
                aria-label="More destinations"
                data-active={inShelf}
                title="More destinations"
                className={cn(
                  "group relative flex h-[56px] w-full flex-col items-center justify-center gap-1 rounded-lg px-1 text-[10px] transition-colors duration-150",
                  inShelf ? "text-accent" : "text-faint hover:text-muted"
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute inset-x-4 top-0 h-[2px] rounded-b-full bg-accent transition-opacity duration-200",
                    inShelf ? "opacity-100" : "opacity-0"
                  )}
                />
                <span
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-lg transition-colors duration-150",
                    inShelf ? "bg-accent/15" : "bg-transparent group-hover:bg-elev/70"
                  )}
                >
                  <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.75} />
                </span>
                <span className="max-w-full truncate leading-none">More</span>
              </button>
            </li>
          </ul>

          {/* Rail footer: the session's main action, and engine state so a
              desktop user never has to open the top bar's badge. */}
          <div className="mt-auto hidden border-t border-line p-3 lg:block">
            <Link
              to="/consultation"
              className="flex h-9 items-center justify-center gap-2 rounded-lg bg-accent px-3 text-xs font-semibold text-accent-ink transition-colors hover:bg-accent-strong"
            >
              New consultation
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
            </Link>
            <div className="mt-3 px-0.5">
              <EngineStatus compact />
            </div>
          </div>
        </div>
      </nav>

      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  );
}

/**
 * The remaining destinations, as a bottom sheet.
 *
 * A native `<dialog>` opened with `showModal()`: the browser supplies the
 * focus trap, the Escape key, the inert background and the focus return to
 * whatever opened it, none of which a hand-rolled overlay gets right for free.
 * `onClose` covers Escape and the browser's own dismissal; the backdrop click
 * is handled explicitly because the backdrop is painted by the dialog box.
 */
export function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const headingId = "more-destinations-heading";

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      // jsdom (and anything else without the method) falls back to the `open`
      // attribute: the sheet is then visible but not modal, which is enough for
      // the unit tests that render the shell.
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
      dialog.querySelector<HTMLElement>("a,button")?.focus();
    } else if (dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={headingId}
      onClose={onClose}
      onClick={(event) => {
        // The dialog element itself is the backdrop target; a click inside the
        // sheet lands on a child.
        if (event.target === ref.current) onClose();
      }}
      className={cn(
        "fixed inset-x-0 bottom-0 top-auto m-0 max-h-[85dvh] w-full max-w-none overflow-y-auto",
        "rounded-t-2xl border-0 border-t border-line bg-panel p-0 text-fg shadow-pop",
        "backdrop:bg-black/55 backdrop:backdrop-blur-[2px] lg:hidden"
      )}
    >
      <div className="px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-2 sm:px-6">
        <div aria-hidden="true" className="mx-auto h-1 w-10 rounded-full bg-line2" />
        <div className="mt-4 flex items-center justify-between">
          <h2 id={headingId} className="text-sm font-semibold">
            More destinations
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-line text-faint transition-colors hover:bg-elev hover:text-fg"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        <nav aria-label="Secondary" className="mt-3 grid grid-cols-3 gap-1.5">
          {SECONDARY_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onClose}
              className="flex min-h-[84px] flex-col items-center justify-center gap-2 rounded-xl border border-line bg-inset px-2 py-3 text-center text-2xs font-medium text-muted transition-colors hover:bg-elev hover:text-fg"
            >
              <item.icon className="h-5 w-5 text-accent" strokeWidth={1.75} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3 text-2xs">
          {PRIMARY_NAV.map((item) => (
            <Link key={item.to} to={item.to} onClick={onClose} className="text-faint hover:text-muted">
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </dialog>
  );
}
