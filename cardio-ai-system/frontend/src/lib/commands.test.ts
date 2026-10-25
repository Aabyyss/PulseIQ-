import { describe, expect, it } from "vitest";
import { COMMANDS, searchCommands } from "@/lib/commands";
import { NAV } from "@/lib/navigation";

/**
 * Ranking is what makes a palette feel like it knows the app: typing "med"
 * should open the medication review, not sort it after "Medication review"
 * because of a tie broken by list order. Each expectation below is a thing a
 * clinician would type, not a function name.
 */
describe("command palette search", () => {
  it("offers every destination when the query is empty", () => {
    expect(searchCommands("").map((command) => command.label)).toEqual(
      NAV.map((item) => item.label)
    );
    expect(COMMANDS).toHaveLength(NAV.length);
  });

  it("ranks a name prefix above a keyword match", () => {
    expect(searchCommands("med")[0].label).toBe("Medication review");
    expect(searchCommands("note")[0].label).toBe("My notes");
  });

  it("finds destinations by the words a clinician uses", () => {
    expect(searchCommands("drugs")[0].to).toBe("/medications");
    expect(searchCommands("interactions")[0].to).toBe("/medications");
    expect(searchCommands("records")[0].to).toBe("/history");
    expect(searchCommands("privacy")[0].to).toBe("/security");
    expect(searchCommands("help")[0].to).toBe("/guidance");
  });

  it("requires every token to match, so one word cannot drag in the rest", () => {
    expect(searchCommands("med review").map((c) => c.to)).toEqual(["/medications"]);
    expect(searchCommands("med visit")).toEqual([]);
  });

  it("says nothing rather than something wrong", () => {
    expect(searchCommands("zzzz")).toEqual([]);
    expect(searchCommands("   ")).toHaveLength(NAV.length);
  });

  it("is case-insensitive and stable for equal matches", () => {
    expect(searchCommands("HISTORY")[0].to).toBe("/history");
    // "a" appears in several labels; order must stay navigation order.
    const first = searchCommands("a").map((c) => c.to);
    const second = searchCommands("a").map((c) => c.to);
    expect(first).toEqual(second);
  });
});
