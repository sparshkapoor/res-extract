// Minimal app-shell cache only. Deliberately does NOT cache /api or /media —
// iOS aggressively evicts cached media anyway, and recipe results are
// already server-side cached by URL hash, so there's no reliability upside
// to caching heavy frame images here, only complexity.
const CACHE_NAME = "res-extract-shell-v1";
const SHELL_URLS = ["/", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/media")) return;
  if (event.request.method !== "GET") return;

  // Network-first, cache as offline fallback only — a cache-first shell
  // means every future deploy needs someone to remember to bump CACHE_NAME,
  // and if they don't (as happened once already), the browser keeps serving
  // an arbitrarily old shell forever with no way for a normal reload to fix
  // it. This still gives the shell offline resilience (the whole point of
  // caching it), it just no longer wins over a reachable, up-to-date server.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
