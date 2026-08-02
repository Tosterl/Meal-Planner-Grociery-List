/* Meal Planner Pro service worker.
 *
 * Strategy:
 *  - HTML navigations: network-first (updates always win when online),
 *    cache fallback so the app opens offline in the store.
 *  - Other same-origin GETs (manifest, icon): cache-first.
 *  - API calls (/api/*) and cross-origin (Supabase, Kroger images, fonts):
 *    never intercepted — pass through to the network.
 */
const CACHE = 'mp2-shell-v1';
const SHELL = ['./', './index.html', './vote.html', './manifest.webmanifest', './icon.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.origin !== location.origin) return;      // Supabase, fonts, images
  if (url.pathname.includes('/api/')) return;      // live data only

  if (e.request.mode === 'navigate' || url.pathname.endsWith('.html')) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match(e.request).then((m) => m || caches.match('./index.html')))
    );
    return;
  }

  e.respondWith(
    caches.match(e.request).then((m) => m || fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    }))
  );
});
