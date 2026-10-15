import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch, clearSession, getToken, initialsOf, persistSession } from "@/lib/authSession";

/**
 * The session layer is what every authenticated call goes through, and its two
 * interesting behaviours are invisible in review: which failures it retries, and
 * what it does to the stored session on a 401. Both are asserted here against a
 * stubbed fetch, so the app's own code is what is under test.
 */
describe("authFetch", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the bearer token and a JSON content type", async () => {
    persistSession("token-123", { id: 1, email: "doc@cardio.local", name: "Doc" });
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await authFetch("/api/consultations", { method: "POST", body: "{}" });

    const [path, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/consultations");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer token-123");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("retries a read once after a network failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await authFetch("/api/history/screenings");

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry a write after a network failure", async () => {
    // The request may have been applied and only the response lost; sending it
    // again is how a saved visit appears twice in History.
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(authFetch("/api/consultations", { method: "POST", body: "{}" })).rejects.toThrow(
      "Failed to fetch"
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("clears the stored session when the server says 401", async () => {
    persistSession("stale-token", { id: 1, email: "doc@cardio.local", name: "Doc" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));

    await authFetch("/api/history/screenings");

    expect(getToken()).toBe("");
  });

  it("does not clear a session on an ordinary error", async () => {
    persistSession("token-123", { id: 1, email: "doc@cardio.local", name: "Doc" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));

    await authFetch("/api/history/screenings");

    expect(getToken()).toBe("token-123");
  });

  it("keeps the token out of a signed-out request", async () => {
    clearSession();
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await authFetch("/api/health");

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Headers).get("Authorization")).toBeNull();
  });
});

describe("initialsOf", () => {
  it("uses the name, then the email, and never throws on an empty account", () => {
    expect(initialsOf({ id: 1, email: "doc@cardio.local", name: "Ayesha Khan" })).toBe("AK");
    expect(initialsOf({ id: 2, email: "ayesha.khan@cardio.local", name: "" })).toBe("AK");
    expect(initialsOf(null)).toBe("?");
  });
});
