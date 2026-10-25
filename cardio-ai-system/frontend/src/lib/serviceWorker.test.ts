import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

/**
 * The worker is the one place where a mistake can put patient data on a disk or
 * serve last week's bundle. Neither is visible in a screenshot, and a browser
 * test cannot easily reproduce "offline" twice, so the worker is run here
 * against fake `caches`/`fetch` globals: the policy is what is being tested,
 * not the browser's implementation of it.
 *
 * `public/sw.js` is a classic worker script (no modules) by design — it must
 * work before any bundler runs — so it is evaluated with the globals it expects
 * rather than imported.
 */
const ORIGIN = "https://app.test";
// vitest runs with the frontend package as its root, and jsdom's `import.meta.url`
// is an http URL, so the worker is read from the working directory.
const source = readFileSync(resolve(process.cwd(), "public/sw.js"), "utf8");

type Requestish = { method: string; mode: string; url: string };
const request = (path: string, overrides: Partial<Requestish> = {}): Requestish => ({
  method: "GET",
  mode: "no-cors",
  url: ORIGIN + path,
  ...overrides
});

function makeResponse(label: string) {
  const response = {
    ok: true,
    type: "basic",
    label,
    clone: () => ({ ok: true, type: "basic", label })
  };
  // The worker only reads `ok`, `type` and `clone`; the cast keeps the test
  // free of a full Response implementation.
  return response as unknown as never;
}

/**
 * Minimal CacheStorage: one Map per cache, keyed by absolute URL, plus the
 * cross-cache `match` the worker uses for its offline fallback.
 */
function harness() {
  const stores = new Map<string, Map<string, unknown>>();
  const ensure = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    return stores.get(name)!;
  };
  const cacheFor = (name: string) => {
    const store = ensure(name);
    return {
      addAll: async (urls: string[]) => {
        for (const url of urls) store.set(new URL(url, ORIGIN).href, makeResponse(url));
      },
      put: async (req: Requestish, res: unknown) => {
        store.set(new URL(req.url, ORIGIN).href, res);
      },
      match: async (req: unknown) => {
        const key = new URL(String((req as Requestish)?.url ?? req), ORIGIN).href;
        return store.get(key);
      }
    };
  };

  const caches = {
    open: async (name: string) => cacheFor(name),
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async (req: unknown) => {
      const key = new URL(String((req as Requestish)?.url ?? req), ORIGIN).href;
      for (const store of stores.values()) if (store.has(key)) return store.get(key);
      return undefined;
    }
  };

  const listeners: Record<string, (event: never) => void> = {};
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, handler: (event: never) => void) => {
      listeners[type] = handler;
    },
    skipWaiting: vi.fn(async () => {}),
    clients: { claim: vi.fn(async () => {}) }
  };

  const fetchMock = vi.fn(async () => makeResponse("network"));
  new Function("self", "caches", "fetch", source)(self, caches, fetchMock);

  async function dispatch(type: string, event: unknown) {
    const handler = listeners[type];
    if (!handler) throw new Error(`no ${type} listener registered`);
    return handler(event as never);
  }

  async function dispatchFetch(req: Requestish) {
    const respondWith = vi.fn();
    await dispatch("fetch", { request: req, respondWith });
    if (!respondWith.mock.calls.length) return null;
    return await (respondWith.mock.calls[0] as unknown[])[0];
  }

  return { stores, ensure, fetchMock, self, dispatch, dispatchFetch };
}

describe("service worker", () => {
  it("caches the shell on install and drops older versions on activate", async () => {
    const worker = harness();
    const waits: Promise<unknown>[] = [];
    await worker.dispatch("install", { waitUntil: (promise: Promise<unknown>) => waits.push(promise) });
    await Promise.all(waits);

    expect(worker.self.skipWaiting).toHaveBeenCalled();
    const shell = worker.ensure("pulseiq-shell-v1");
    expect(shell.has(ORIGIN + "/index.html")).toBe(true);
    expect(shell.has(ORIGIN + "/manifest.webmanifest")).toBe(true);

    // A previous version's cache must not survive an update.
    worker.ensure("pulseiq-shell-v0").set(ORIGIN + "/index.html", makeResponse("old"));
    await worker.dispatch("activate", { waitUntil: (promise: Promise<unknown>) => waits.push(promise) });
    await Promise.all(waits);
    expect(worker.stores.has("pulseiq-shell-v0")).toBe(false);
    expect(worker.self.clients.claim).toHaveBeenCalled();
  });

  it("never intercepts API or socket traffic, or a mutation", async () => {
    const worker = harness();
    // This is the safety property: clinical responses must not reach a cache.
    expect(await worker.dispatchFetch(request("/api/consultations"))).toBeNull();
    expect(await worker.dispatchFetch(request("/api/auth/me"))).toBeNull();
    expect(await worker.dispatchFetch(request("/ws"))).toBeNull();
    expect(await worker.dispatchFetch(request("/api/notes", { method: "POST" }))).toBeNull();
    expect(worker.fetchMock).not.toHaveBeenCalled();
  });

  it("serves the cached shell when a navigation fails offline", async () => {
    const worker = harness();
    const waits: Promise<unknown>[] = [];
    await worker.dispatch("install", { waitUntil: (promise: Promise<unknown>) => waits.push(promise) });
    await Promise.all(waits);

    worker.fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    const response = (await worker.dispatchFetch(
      request("/history", { mode: "navigate" })
    )) as { label?: string } | null;
    expect(response?.label).toBe("/index.html");
  });

  it("prefers the network for a navigation when it is available", async () => {
    const worker = harness();
    const response = (await worker.dispatchFetch(
      request("/medications", { mode: "navigate" })
    )) as { label?: string } | null;
    expect(response?.label).toBe("network");
  });

  it("stores a hashed asset on first use and serves it from cache afterwards", async () => {
    const worker = harness();
    const asset = request("/assets/index-abc123.js");
    await worker.dispatchFetch(asset);
    expect(worker.fetchMock).toHaveBeenCalledTimes(1);
    expect(worker.ensure("pulseiq-shell-v1").has(asset.url)).toBe(true);

    await worker.dispatchFetch(asset);
    expect(worker.fetchMock).toHaveBeenCalledTimes(1);
  });
});
