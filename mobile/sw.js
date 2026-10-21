/* BPF Mobile service worker — scope /m/.
   Strategi: app shell cache-first (v1); /api & Nominatim SELALU network. */
const CACHE = 'bpf-mobile-1';
const SHELL = ['.'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;                       // POST/PUT/DELETE tidak dicache — offline queue ada di app JS
  if (url.pathname.startsWith('/api/')) return;                 // data live: SELALU network (fetch gagal → caller beri pesan)
  if (url.hostname === 'nominatim.openstreetmap.org') return;
  if (!url.pathname.startsWith('/m/')) return;                  // hanya scope /m/

  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((resp) => {
      const copy = resp.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
      return resp;
    }))
  );
});
