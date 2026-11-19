// Konfigurasi koneksi aplikasi ke bridge agenda WorkHub (read-only).
window.BPF_CONFIG = {
  // Server produksi (NAS, via nginx hybrid-nextcloud):
  API_BASE: 'https://nasbpfsby.duckdns.org:8444',

  // interval polling cadangan saat SSE tidak hidup (milidetik)
  POLL_MS: 15000,

  // tampilkan detik pembaruan terakhir
  SHOW_FRESHNESS: true,
};
