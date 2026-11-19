# Widget interaktif (roadmap)

"Widget interaktif" v1 telah tersedia **di dalam aplikasi**: panel kanan menampilkan
informasi tanggal ini secara realtime (SSE + fallback polling, otomatis segar saat
admin menerbitkan agenda, dan otomatis kosong saat berganti tanggal).

Untuk widget di layar beranda (home-screen), Android dan iOS memakai mekanisme yang
sangat berbeda dan keduanya butuh kode native:

## Android — Home Screen Widget (App Widget)
- Membuat plugin Cordova kecil dengan `AppWidgetProvider` (Java).
- Menampilkan 1–3 judul agenda hari ini di widget, refresh tiap 30–60 menit
  (`updatePeriodMillis`) + langsung refresh saat aplikasi dibuka.
- Fetch data pakai `HttpURLConnection` bawaan (tanpa dependensi).
- Klik widget membuka aplikasi.

Status: **belum diimplementasi** (sengaja ditunda agar build pertama tidak berisiko;
plugin bisa ditambahkan nanti tanpa mengubah aplikasi utama).

## iOS — Home Screen Widget (WidgetKit)
- Widget iOS **tidak bisa dibikin lewat Cordova**; harus menambahkan target
  **Widget Extension (SwiftUI + WidgetKit)** di Xcode pada proyek `platforms/ios`.
- Data widget ditarik sistem iOS (timeline provider), bukan realtime — menampilkan
  agenda tanggal berjalan (update terbaru setiap proses timeline berjalan).
- Butuh Mac + Xcode. TODO saat build iOS pertama: buat target extension dan
  gunakan `API_BASE` yang sama dengan `www/js/config.js`.

## Logo perusahaan
Tiga titik peletakan logo (beda tempat, fungsi beda):
1. **Aplikasi (header kiri)** — taruh PNG di `mobile/res/icon/` → file logo.png, lalu
   daftarkan pada `mobile/config.xml` (tag `<icon>`). PNG dipakai juga untuk ikon
   aplikasi Android/iOS.
2. **Server/admin (login + topbar)** — scp PNG ke NAS:
   `static/bpf-logo.png` di repo WorkHub → tampil di aplikasi lewat
   bridge (`/assets/logo.png`).
3. **Favicon web admin** — `data/assets/favicon.ico` (opsional).
