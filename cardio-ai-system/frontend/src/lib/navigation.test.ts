import { describe, expect, it } from "vitest";
import {
  NAV,
  PRIMARY_COUNT,
  PRIMARY_NAV,
  SECONDARY_NAV,
  activeItem,
  isSecondaryRoute
} from "@/lib/navigation";

/**
 * The shell's one piece of real logic. A wrong answer here is invisible in a
 * screenshot — the page looks fine with the wrong item marked current — and it
 * is what the UI audit checks by name on every route, so the rule is pinned
 * here as well as in the browser.
 */
describe("navigation", () => {
  it("keeps every destination unique and ordered overview-first", () => {
    expect(NAV[0].to).toBe("/");
    expect(new Set(NAV.map((item) => item.to)).size).toBe(NAV.length);
    expect(new Set(NAV.map((item) => item.label)).size).toBe(NAV.length);
    expect(NAV.filter((item) => item.end)).toHaveLength(1);
  });

  it("splits into five primary destinations and the rest", () => {
    // Five is Material's ceiling for a bottom navigation bar; nine in one row
    // is what the phone had, and what this split exists to fix.
    expect(PRIMARY_COUNT).toBe(5);
    expect(PRIMARY_NAV).toHaveLength(5);
    expect(SECONDARY_NAV.length).toBe(NAV.length - 5);
    expect([...PRIMARY_NAV, ...SECONDARY_NAV]).toEqual(NAV);
    expect(PRIMARY_NAV.map((item) => item.short)).toEqual([
      "Home",
      "Consult",
      "Meds",
      "History",
      "Patients"
    ]);
  });

  it("marks the longest matching prefix, not the first", () => {
    expect(activeItem("/")?.label).toBe("Overview");
    expect(activeItem("/consultation")?.label).toBe("Consultation");
    expect(activeItem("/patients/42")?.label).toBe("Patients");
  });

  it("does not claim a page for a route that is not a destination", () => {
    // The bug the audit caught: these used to mark Overview as current.
    for (const path of ["/privacy", "/terms", "/thank-you", "/nope"]) {
      expect(activeItem(path)).toBeNull();
      expect(isSecondaryRoute(path)).toBe(false);
    }
  });

  it("knows which routes the phone bar hides behind More", () => {
    expect(isSecondaryRoute("/")).toBe(false);
    expect(isSecondaryRoute("/medications")).toBe(false);
    expect(isSecondaryRoute("/notes")).toBe(true);
    expect(isSecondaryRoute("/agents")).toBe(true);
    expect(SECONDARY_NAV.every((item) => isSecondaryRoute(item.to))).toBe(true);
  });
});
