/* Marbles — optional service worker.
   DROP THIS FILE next to marbles.html (renamed to index.html) on your host
   to guarantee the app loads offline forever, even after a cache clear.
   It is not required: the app installs, stores marbles, and works offline
   without it. It only makes the very first offline page-load bulletproof. */
const CACHE = 'marbles-v2';

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['./', 'index.html']).catch(() => {})));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.open(CACHE).then(cache =>
      cache.match(e.request).then(hit => {
        const net = fetch(e.request).then(res => {
          try { cache.put(e.request, res.clone()); } catch (_) {}
          return res;
        }).catch(() => hit);
        return hit || net;   // cache-first, fall back to network
      })
    )
  );
});
