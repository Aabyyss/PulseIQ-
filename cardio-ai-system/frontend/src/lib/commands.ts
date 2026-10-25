import { NAV } from "@/lib/navigation";

/**
 * What the command palette can do: jump to a destination, by the name on the
 * bar, the name a clinician might use for it, or an abbreviation.
 *
 * Deliberately data-only. The ranking is the part that can be wrong in a way a
 * screenshot never shows — the right command sitting third behind two weaker
 * matches — so it lives here, away from the dialog, and is unit-tested.
 */
export interface Command {
  id: string;
  label: string;
  /** The route it opens. Every command navigates; nothing here mutates data. */
  to: string;
  keywords: string[];
}

/** The words a clinician actually types for each destination. */
const KEYWORDS: Record<string, string[]> = {
  "/": ["home", "start", "overview", "dashboard"],
  "/consultation": ["consult", "screening", "capture", "new", "dictate", "visit"],
  "/medications": ["meds", "drugs", "interactions", "pharmacy", "prescription"],
  "/history": ["past", "visits", "records", "screenings", "consultations"],
  "/patients": ["people", "roster", "timeline"],
  "/notes": ["private", "notes", "scratch"],
  "/guidance": ["help", "how", "documentation", "guide"],
  "/security": ["privacy", "security", "settings", "device"],
  "/agents": ["agents", "registry", "pipeline", "models"]
};

export const COMMANDS: Command[] = NAV.map((item) => ({
  id: item.to,
  label: item.label,
  to: item.to,
  keywords: KEYWORDS[item.to] ?? []
}));

const normalise = (value: string) => value.trim().toLowerCase();

/**
 * Rank commands for a query.
 *
 * Tiers rather than one score, because the tiers are what a reader expects: an
 * exact name wins, a name that starts with the query beats one that only
 * contains it, and a keyword match sits just below a label match. Ties keep
 * navigation order, so the list does not reshuffle between keystrokes.
 *
 * Every token must match somewhere, so "med review" finds the medication
 * review rather than everything containing "med" or "review".
 */
export function searchCommands(query: string, commands: Command[] = COMMANDS): Command[] {
  const needle = normalise(query);
  if (!needle) return [...commands];
  const tokens = needle.split(/\s+/).filter(Boolean);

  const ranked: { command: Command; tier: number; index: number }[] = [];
  commands.forEach((command, index) => {
    const label = normalise(command.label);
    const keywords = command.keywords.map(normalise);
    let worst = 0;
    for (const token of tokens) {
      let tier = Infinity;
      if (label === token) tier = 0;
      else if (label.startsWith(token)) tier = 1;
      else if (label.split(/[\s&]+/).some((word) => word.startsWith(token))) tier = 2;
      else if (keywords.some((word) => word.startsWith(token))) tier = 3;
      else if (label.includes(token)) tier = 4;
      else if (keywords.some((word) => word.includes(token))) tier = 5;
      if (!Number.isFinite(tier)) return;
      worst = Math.max(worst, tier);
    }
    ranked.push({ command, tier: worst, index });
  });

  return ranked
    .sort((a, b) => a.tier - b.tier || a.index - b.index)
    .map((entry) => entry.command);
}
