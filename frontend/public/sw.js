/* BPF WorkHub SPA — Service Worker (scope /app/)
 * v2.37.8: JANGAN pernah menyentuh /api/* — respons API tidak boleh di-cache.
 * SW sebelumnya (stale-while-revalidate utk semua GET) membuat list API
 * menampilkan data lama setelah verifikasi/kehadiran sampai refresh manual.
 * v2.38.0: cache bump saja — stamp SPA v2.38.0 (migrasi worker gevent di backend).
 */
const CACHE = 'bpf-spa-20260913-v2400';
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

  // v2.37.8: API (dan semua data dinamis) SELALU lewat jaringan —
  // jangan intercept, jangan cache. SW hanya untuk shell SPA + asset.
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/socket.io/')) {
    return; // biarkan browser menangani (no event.respondWith)
  }

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
