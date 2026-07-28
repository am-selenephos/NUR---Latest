// Offline shell for the canonical V197 host.
//
// This was cache-first for every non-navigation request, against a cache name
// that never changed between builds:
//
//   const CACHE = "nur-v197-shell-v2";
//   caches.match(request).then(cached => cached || fetch(request))
//
// So the first copy of /assets/v197-bridge.js a browser ever saw was the copy
// it kept. `activate` only deletes caches with a *different* name, and the name
// was a constant, so nothing ever evicted it. Every subsequent deploy was
// invisible to anyone who had already loaded the app once — which is exactly
// how one machine kept showing an old build while a fresh browser profile
// showed the current one.
//
// Build assets are network-first now, falling back to cache only when the
// network genuinely fails. The shell stays cached so the app still opens
// offline.
const VERSION = "v3";
const CACHE = `nur-v197-shell-${VERSION}`;
const SHELL = ["/", "/offline.html", "/manifest.webmanifest", "/nur-icon.svg"];

self.addEventListener("install", event => {
  // Take over immediately instead of waiting for every existing tab to close,
  // otherwise the stale worker keeps serving stale assets for the whole session.
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", event => {
  const { request } = event;
  const url = new URL(request.url);

  if (url.pathname.startsWith("/api/")) return;
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline.html")));
    return;
  }

  // Network first, cache as fallback. A deploy reaches the user on the next
  // load instead of never, and going offline still works because the last good
  // response is written back on every success.
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response && response.ok && request.method === "GET") {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(request)),
  );
});
