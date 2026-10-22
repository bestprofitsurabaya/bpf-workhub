/* BPF WorkHub SPA — Service Worker (scope /app/)
 * v2.37.8: JANGAN pernah menyentuh /api/* — respons API tidak boleh di-cache.
 * SW sebelumnya (stale-while-revalidate utk semua GET) membuat list API
 * menampilkan data lama setelah verifikasi/kehadiran sampai refresh manual.
 * v2.38.0: cache bump saja — stamp SPA v2.38.0 (migrasi worker gevent di backend).
 */
const CACHE = 'bpf-spa-20261022-v2.49.1';
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
// v2.43.3 — perbaikan dua bug:
//   1) respondWith TIDAK BOLEH menerima undefined ("Failed to convert
//      value to 'Response'") — semua jalur kini selalu mengembalikan
//      Response (fallback cache atau Response.error()).
//   2) RACUN CACHE: setelah deploy, chunk lama dihapus di server → SPA
//      fallback menjawab HTML 200 utk URL .js yang hilang → sebelumnya
//      respons HTML ini DI-SIMPAN utk URL js → MIME error berulang.
//      Kini respons text/html utk request asset DITOLAK (Response.error)
//      & tidak pernah disimpan — module import gagal bersih lalu SPA
//      auto-reload (router.onError di main.js) dan mendapat shell baru.
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
    event.respondWith((async () => {
      try {
        // redirect: 'follow' — ikuti redirect (mis. / → /app/login)
        const res = await fetch(request, { redirect: 'follow' });
        if (res && res.ok) cachePut(request, res.clone());
        return res;
      } catch {
        const cached = (await caches.match(request)) ||
                       (await caches.match('/app/index.html'));
        return cached || Response.error(); // selalu Response, bukan undefined
      }
    })());
    return;
  }

  // Asset Vite ber-hash: cache-first + revalidate di belakang
  event.respondWith((async () => {
    const hit = await caches.match(request);
    if (hit) {
      event.waitUntil((async () => {
        try {
          const fresh = await fetch(request, { redirect: 'follow' });
          if (fresh && fresh.ok) cachePut(request, fresh.clone());
        } catch { /* offline — biarkan hit dipakai */ }
      })());
      return hit;
    }
    try {
      const res = await fetch(request, { redirect: 'follow' });
      const ct = (res.headers.get('Content-Type') || '').toLowerCase();
      if (ct.includes('text/html')) {
        // Chunk tak ada di server (post-deploy) — JANGAN pakai & JANGAN simpan.
        return Response.error();
      }
      if (res.ok) cachePut(request, res.clone());
      return res;
    } catch {
      return Response.error(); // selalu Response, bukan undefined
    }
  })());
});

function cachePut(request, response) {
  if (response.ok) caches.open(CACHE).then((c) => c.put(request, response)).catch(() => {});
}
