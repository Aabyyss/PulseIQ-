/**
 * PulseIQ service worker: install the shell, never cache patient data.
 *
 * The app is a static bundle plus a FastAPI backend. What makes it feel like an
 * installed app is the shell opening instantly and surviving a dead connection;
 * what makes it safe in a clinic is that no `/api` or `/ws` response is ever
 * stored by the worker. Those paths are excluded before any strategy runs, so
 * there is one place to check rather than a cache rule that could be widened by
 * accident.
 *
 * Strategies:
 * - navigation → network first, cached `index.html` as the offline fallback;
 * - hashed build assets → cache first, then network (the filename changes when
 *   the bytes change, so a hit is always the right build);
 * - everything else → left to the browser.
 *
 * Version the cache when the shell list changes; `activate` deletes every older
 * cache so an update cannot leave a previous build's icons behind.
 */
const VERSION = "pulseiq-shell-v1";

const SHELL = [
  "/index.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png"
];

/**
 * Cache the shell and the bundle it references.
 *
 * The build's JavaScript and CSS carry content hashes, so a static list cannot
 * name them. They are read out of the built `index.html` instead: without them
 * an offline navigation would return the HTML and then fail to load the app,
 * which renders an empty page and reads as "the shell did not work".
 */
async function precache() {
  const cache = await caches.open(VERSION);
  await cache.addAll(SHELL);
  const html = await (await fetch("/index.html", { cache: "reload" })).text();
  const assets = [...new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]))];
  if (assets.length) await cache.addAll(assets);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    // `addAll` rejects the whole install if one URL 404s; the shell list is
    // small and versioned, so a failure here means the build is broken and
    // installing anyway would cache a half-shell.
    precache().then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Clinical data and the live socket are never cached, by policy.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/index.html", { ignoreSearch: true, ignoreVary: true }))
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      // `ignoreVary` is load-bearing: the preview server answers with
      // `Vary: Origin`, and a module script request carries an Origin that the
      // install-time fetch did not, so a strict match misses the asset it just
      // cached and the offline shell loads without its JavaScript.
      caches.match(request, { ignoreVary: true }).then((hit) => {
        if (hit) return hit;
        return fetch(request).then((response) => {
          // Only a complete, same-origin, OK response is worth storing.
          if (response.ok && response.type === "basic") {
            const copy = response.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        });
      })
    );
  }
});
