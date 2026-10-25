import {
  Bot,
  BookOpen,
  History,
  LayoutGrid,
  NotebookPen,
  Pill,
  ShieldCheck,
  Stethoscope,
  Users,
  type LucideIcon
} from "lucide-react";

/**
 * One destination list for every screen size.
 *
 * The shell presents it three ways — a five-item bar with a More sheet on
 * phones, the same bar on tablet portrait, and a labelled rail from `lg` up —
 * but there is one list, one order and one active-item rule, because two lists
 * drift the moment a route is added.
 *
 * The order is the order a visit moves through: the overview leads (it is the
 * page that says "start a consultation"), then the consult itself, then the
 * records and reference material behind it.
 *
 * `primary` marks the five destinations a phone bar can hold. Material's
 * navigation bar is specified for three to five equally important
 * destinations, and Apple's tab bar guidance is to avoid turning More into the
 * default hiding place — so the five here are the ones a clinician touches in a
 * session, and the rest are one tap away in the More sheet rather than a
 * sideways-scrolling strip of nine.
 */
export interface NavItem {
  to: string;
  label: string;
  /** Tighter label for the phone bar, where five destinations share one row. */
  short: string;
  icon: LucideIcon;
  /** Exact match only — used by the overview so it does not own every route. */
  end?: boolean;
  /** The main action. Drawn a shade bolder than its neighbours. */
  primary?: boolean;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", short: "Home", icon: LayoutGrid, end: true },
  { to: "/consultation", label: "Consultation", short: "Consult", icon: Stethoscope, primary: true },
  { to: "/medications", label: "Medication review", short: "Meds", icon: Pill },
  { to: "/history", label: "History & visits", short: "History", icon: History },
  { to: "/patients", label: "Patients", short: "Patients", icon: Users },
  // Secondary destinations: reachable from the rail at every width, and from
  // the More sheet below `lg`.
  { to: "/notes", label: "My notes", short: "Notes", icon: NotebookPen },
  { to: "/guidance", label: "Guidance", short: "Guide", icon: BookOpen },
  { to: "/security", label: "Security", short: "Security", icon: ShieldCheck },
  { to: "/agents", label: "Agent registry", short: "Agents", icon: Bot }
];

/** How many items the phone bar shows before its More control. */
export const PRIMARY_COUNT = 5;

export const PRIMARY_NAV = NAV.slice(0, PRIMARY_COUNT);
export const SECONDARY_NAV = NAV.slice(PRIMARY_COUNT);

/**
 * Longest prefix wins, so `/history` doesn't swallow a deeper route, and a path
 * that is not a destination returns null rather than the overview: the legal
 * pages and the saved-visit confirmation are not "Overview", and marking the
 * home item current there told screen readers they were somewhere they were not.
 */
export function activeItem(pathname: string): NavItem | null {
  return (
    NAV.filter((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to))).sort(
      (a, b) => b.to.length - a.to.length
    )[0] ?? null
  );
}

/** Whether the current route lives behind the More control on a phone. */
export function isSecondaryRoute(pathname: string): boolean {
  return SECONDARY_NAV.some((item) => item.to === activeItem(pathname)?.to);
}
