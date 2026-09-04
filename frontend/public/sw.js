/* BPF WorkHub SPA — Service Worker (scope /app/) */
const CACHE = 'bpf-spa-20260904-v297';
const SHELL = ['/app/index.html'];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch((err) => console.warn('[SPA SW] shell cache:', err))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('bpf-spa-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network-first untuk navigasi (fallback index.html saat offline),
// stale-while-revalidate untuk asset ber-hash.
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      // redirect: 'follow' — ikuti redirect (mis. / → /app/login)
      fetch(request, { redirect: 'follow' })
        .then((res) => { cachePut(request, res.clone()); return res; })
        .catch(() => caches.match('/app/index.html'))
    );
    return;
  }

  // Asset Vite ber-hash: cache-first
  event.respondWith(
    caches.match(request).then((hit) => {
      const network = fetch(request, { redirect: 'follow' })
        .then((res) => { if (res.ok) cachePut(request, res.clone()); return res; })
        .catch(() => hit);
      return hit || network;
    })
  );
});

function cachePut(request, response) {
  if (response.ok) caches.open(CACHE).then((c) => c.put(request, response)).catch(() => {});
}
