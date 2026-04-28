// Minimal service worker — just enough to make the dashboard installable
// as a PWA. We intentionally don't cache aggressively because the dashboard
// is data-heavy and needs to fetch fresh forecasts on every load.

const VERSION = 'shallweflytomorrow-v1';

self.addEventListener('install', (event) => {
  // Activate immediately so old service workers don't linger.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // Clean up any older caches.
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

// Network-first for everything. PWA installability only requires a service
// worker to exist with a fetch handler — we don't want to cache dashboard
// data because the value of this app is freshness.
self.addEventListener('fetch', (event) => {
  // Let the browser handle it normally.
  return;
});
