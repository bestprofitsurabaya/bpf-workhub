# 📋 Changelog — BPF WorkHub v2.25.0

Riwayat perubahan penting pada BPF WorkHub. Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/ID/1.0.0/) dan versi mengikuti [Semantic Versioning](https://semver.org/lang/id/).

**PT. Bestprofit Futures — Surabaya**  
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271  
Telp: 031-5349888

---

## 📋 Daftar Isi

- [Versi Terbaru](#versi-terbaru)
- [Riwayat Lengkap](#riwayat-lengkap)

---

## Versi Terbaru

### [2.25.0] - 2026-08-24

**UI/UX Overhaul + 7 SEO Algorithms + Multi-Branch + Duplicate Prevention**

**Fitur Baru:**
- **Upload Gambar ke WordPress**: download dari source → upload ke WP Media Library → featured image + inline
- **Progress Tracking**: SSE polling endpoint `/api/scraper/progress/<task_id>`
- **Upload History**: filter tanggal/aksi di `/api/scraper/history`
- **Duplicate Prevention**: paginate 500 posts + fuzzy title matching (normalize lowercase, strip punctuation)
- **7 Algoritma SEO**:
  1. Content Uniqueness (25+ sinonim, parafrase otomatis)
  2. Multi-Source Scraping (newsmaker + kontan + bisnis)
  3. Internal Linking (keyword overlap antar artikel)
  4. Advanced Schema (NewsArticle + BreadcrumbList + Organization + FAQ)
  5. Auto Sitemap Ping (Google + IndexNow)
  6. Smart Scheduling (9-11AM, 7-9PM WIB, max 5/hari)
  7. Performance Analytics (track per site/date)
- **SEO Backlinks**: 5 BPF target sites + 23 authority sites + CTA widget otomatis
- **Multi-Branch Users**: 10 cabang (JKT, JKT2, BDG, SMG, MLG, MDN, BJM, PLM, LPG, SBY)
- **Access Filtering**: user hanya lihat site cabang sendiri (HO & admin lihat semua)
- **UI/UX Overhaul**:
  1. Dashboard Overview (stats cards + recent activity)
  2. Tab-Based Layout (6 tabs: Dashboard/Sites/Scrape/Upload/SEO/Analytics)
  3. Article Preview Cards (thumbnail + checkbox select)
  4. Upload Queue (select individual articles)
  5. Real-Time Upload Log
  6. Mobile-First Design (responsive 640px)
  7. SEO Score Visual (stats grid + daily chart)
  8. Quick Actions FAB (floating action button)
  9. Dark Mode Support (toggle + localStorage)
  10. Onboarding Checklist (getting started guide)

**Fix:**
- `_check_bs4()` → `check_bs4()` (NameError causing 500)
- Content rewrite order: parafrase SEBELUM backlinks (bukan sesudah)
- Upload function: use `source_url` bukan `link` untuk gambar WordPress
- Featured image: set `featured_media` saat update post juga
- Duplicate check: paginate 500 posts + cache title→post_id
- Session key: `user_role` bukan `role` untuk access filtering

---

### [2.24.0] - 2026-08-24

**Overtime Driver Form + Audit Fix + Deployment Ready**

**Fitur Baru:**
- **Form Overtime Driver di PWA**: tab ⏰ OT — submit overtime dengan foto watermark + GPS
- **Foto Bukti Timestamp**: kamera langsung dari form, watermark otomatis (nama perusahaan + tanggal + GPS)
- **Source Tracking**: pisahkan data Google Sheet (`sheet`) vs Aplikasi (`form`) di database
- **Filter Source**: dropdown filter di dashboard GA HR (Sheet / Aplikasi / Semua)
- **PDF dengan Kolom Sumber**: laporan PDF menampilkan sumber data (Sheet/Aplikasi)
- **Single Record PDF**: parameter `display_id` untuk cetak 1 transaksi
- **Foto Upload Galeri + Kamera**: file picker HP tampilkan opsi kamera & galeri

**Fix:**
- **Error 500 `/api/scraper/check`**: install beautifulsoup4 di Docker container
- **Scraper Parsing**: update untuk struktur baru newsmaker.id (Tailwind CSS)
- **Parser Tanggal Indonesia**: handle abbreviasi (Agu/Agustus)
- **10 Anomaly PWA Driver**: GPS shared, offline support, pre-fill profile, toast events
- **Deployment Ready**: docker-compose, nginx.conf, init.sql (35 tabel), DEPLOY_FRESH.md

**Backend:**
- `POST /api/overtime/driver/submit` — submit overtime driver dari PWA
- Kolom `source` + `display_id` di tabel `overtime_driver`
- Filter `source` di driver list & report endpoint
- `_save_overtime_foto()` — simpan foto base64 ke `/uploads/overtime/`

**Frontend:**
- `OvertimeDriverTab.vue` — tab baru di PWA driver
- `OvertimeView.vue` — filter source + kolom Sumber di tabel
- `BBMTab.vue` — foto upload support galeri + kamera
- `driverStore.js` — overtime_queue untuk offline support

### [2.23.0] - 2026-08-21

**Role baru: IT Surabaya (`it_ef`)** — News Scraper & Content Management. ef = kode cabang internal Surabaya.

**Fitur Baru:**
- **News Scraper**: Scrape artikel dari newsmaker.id (market-news/commodity)
- **WordPress Integration**: Multi-site management (CRUD, test connection)
- **Auto-Upload**: Upload artikel ke WordPress dengan SEO optimization
- **Financial Authority Backlinks**: 24+ situs otoritas (OJK, BI, BEI, Bloomberg, dll)
- **Keyword → Backlink Mapping**: Ototomatis berdasarkan konten artikel
- **SEO Analyzer**: Word count, heading, link density, image check → score 0-100
- **Duplicate Checker**: Deteksi & hapus artikel duplikat di WordPress
- **Schema Markup**: JSON-LD Article schema untuk SEO
- **Guest Post Pitch**: Template otomatis untuk outreach
- **Activity Log**: Lacak semua aktivitas scraper

**Backend:**
- `modules/routes_news_scraper.py` — 14 API endpoints
- Role `it_ef` ditambahkan ke ROLE_HOME, auth store, sidebar menu

**Frontend:**
- `ItEfView.vue` — Dashboard scraper dengan 5 panel: Sites, Scrape, Upload, Duplicates, Backlinks

### [1.0.0] - 2026-08-20

Versi stabil pertama dengan fitur lengkap: 10 role, 243 pytest, 82 Vitest, 10 video walkthrough.

**Fitur Utama:**
- Klaim BBM, kasbon, log perjalanan
- Sistem appointment dengan rute otomatis
- Pembelian air minum dengan verifikasi Finance
- Sistem pelamar kerja (form → Receptionist → Traineer)
- Aset & pemeliharaan (AC + kendaraan)
- Overtime Driver & OB/Security
- Multi-cabang dengan isolasi data
- PWA offline-first untuk driver
- Notifikasi real-time via WebSocket
- Backup DB otomatis

**Keamanan:**
- Login PIN + session-based
- CSRF protection
- Role-based access (10 role)
- Audit trail lengkap
- Security headers (CSP, X-Frame-Options, dll)

**Testing:**
- 243 pytest (backend)
- 82 Vitest (frontend)
- Browser verification via Puppeteer
- CI/CD via GitHub Actions

---

## Riwayat Lengkap

### v2.22.2 (2026-08-20)
- **Integrasi Backend → Frontend**: Finance Review, Finance Remark, Transaction Flags, Fleet Health, Cash Detail, Completed Appointments
- **User List**: dokumentasi lengkap 10 role + audit sync backend ↔ frontend (160/161 endpoint terpakai, 99.4%)

### v2.22.1 (2026-08-18)
- **Migrasi Overtime Driver**: 8.665 baris dari Google Sheet via Apps Script Web App
- **Solusi sheet PRIVATE**: tanpa akses pemilik, cukup akun yang punya akses view
- **Parser ISO UTC → WIB**: konversi otomatis +7 jam
- **Auto-refresh saat login/logout**: debounce 30 detik anti-spam
- **Notifikasi data overtime baru**: bell 🔔 realtime
- **Edit & hapus data overtime**: modal edit + konfirmasi hapus
- **Testing**: 243 pytest + 82 Vitest

### v2.22.0 (2026-08-14)
- **Role baru GA HR** dengan halaman sendiri `/app/ga-hr`
- **Overtime Driver**: sinkronisasi Google Sheet, URL sumber data bisa diatur
- **Overtime OB/Security**: 546 baris dimigrasikan + form publik tanpa login
- **Keamanan**: endpoint khusus role ga_hr & admin, rate-limit form publik
- **PDF Overtime**: laporan resmi berlogo BPF + TTD GA HR

### v2.21.0 (2026-08-13)
- **Security headers lengkap**: CSP ketat, X-Frame-Options, Referrer-Policy
- **Rate limit terpusat**: anti brute-force login
- **Backup DB otomatis**: mysqldump semua database tiap 03:00 WIB
- **Laporan konsolidasi lintas cabang**: PDF + Excel dari semua DB cabang
- **UI/UX**: LoadingState, EmptyState, ErrorState, pagination, export Excel

### v2.20.x (2026-08-13)
- **Multi-cabang**: setiap cabang punya database sendiri (isolasi data penuh)
- **Ringkasan cabang di dashboard Admin**
- **Audit log bertanda cabang**
- **Filter cabang di Audit Log**
- **PDF ringkasan per cabang**

### v2.19.x (2026-08-13)
- **Nama akun driver dirapikan**: username huruf kecil
- **Data demo dikelola Admin**: buat & bersihkan dari Settings
- **Identitas perusahaan dinamis**: bisa diubah Admin
- **PDF generator compact**: palet monokrom, resmi
- **Debugging menyeluruh**: tab driver, notifikasi, error server

### v2.18.0 (2026-08-13)
- **Aset & Pemeliharaan**: migrasi dari Streamlit ke WorkHub
- **15 unit AC** + **8 kendaraan** + **12 komponen**
- **Health score otomatis 0–100**
- **Rekomendasi maintenance berbasis aturan**
- **PDF resmi berlogo BPF**

### v2.17.0 (2026-08-13)
- **Migrasi data Google Sheet**: 914 riwayat pelamar
- **Dropdown User diatur Receptionist**: kelola opsi form pelamar

### v2.16.x (2026-08-13)
- **Ganti nama aplikasi**: dari "BPF Fleet & BBM System" → **BPF WorkHub**
- **Sistem Pelamar Kerja**: form publik → Receptionist → Traineer
- **Laporan PDF resmi per tahap**

### v2.15.x (2026-08-13)
- **Rute canggih**: jam kunjungan, geocoding, optimasi rute otomatis
- **Estimasi penghematan BBM**: angka persentase efisiensi
- **Backfill koordinat data lama**

### v2.14.x (2026-08-12)
- **Gladi resik otomatis**: 20/20 cek per peran
- **Video walkthrough**: 8 mp4 + walkthrough-all
- **Fix kritis**: koneksi DB bocor + font self-host

### v2.13.0 (2026-08-12)
- **Paket presentasi lengkap**: PPTX editabel, PDF, slide deck interaktif
- **Data demo**: 70 transaksi riwayat

### v2.12.x (2026-08-12)
- **Chrome host berfungsi**: verifikasi UI via Puppeteer
- **Slide deck interaktif**: 12 slide dengan navigasi keyboard

### v2.11.0 (2026-08-12)
- **Aksesibilitas**: dialog, kontras, keyboard navigation
- **Mode Kontras Tinggi 🔆**

### v2.10.0 (2026-08-12)
- **SPA Vue 3**: migrasi penuh dari server-rendered
- **Dashboard per role**: Admin, GA, Finance, Marketing, Chief Driver

### v2.0.0 (2026-08-11)
- **SPA Vue 3 + Vite**: antarmuka baru
- **Auth JSON**: `/api/auth/me`, `/api/auth/login`, `/api/auth/logout`
- **Kontrol akses berlapis**: server + SPA + sidebar

### v1.2.0 (2026-08-10)
- **Sistem Appointment**: Marketing → Chief Driver → Driver
- **Integrasi Log Perjalanan**: appointment → trip otomatis
- **Login redirect per-role**

### v1.1.0 (2026-08-09)
- **Autentikasi PIN**: login/logout session-based
- **CSRF protection**: token di semua form
- **Notifikasi driver real-time**: WebSocket per-driver room
- **Dark mode**: toggle 🌙/☀️ di semua halaman

### v1.0.0 (2026-08-08)
- **Rilis pertama**: sistem BBM, kasbon, log perjalanan
- **Driver PWA**: submit BBM, kasbon, trip
- **GA/Finance**: verifikasi & pencairan
- **Admin**: manajemen user, settings, audit log

---

## 📊 Statistik Pengujian

| Versi | Pytest | Vitest | Browser | Total |
|-------|--------|--------|---------|-------|
| v1.0.0 | 29 | — | — | 29 |
| v1.1.0 | 48 | 12 | — | 60 |
| v1.2.0 | 66 | 29 | — | 95 |
| v2.0.0 | 77 | 39 | — | 116 |
| v2.10.0 | 87 | 47 | — | 134 |
| v2.15.0 | 131 | 67 | 8 | 206 |
| v2.18.0 | 160 | 82 | 8 | 250 |
| v2.20.0 | 194 | 82 | 16 | 292 |
| v2.22.0 | 243 | 82 | 16 | 341 |
| **v1.0.0 (final)** | **243** | **82** | **16** | **341** |

---

## 📞 Kontak

**PT. Bestprofit Futures — Surabaya**  
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271  
Telp: 031-5349888

---

*BPF WorkHub v1.0 · Changelog*
