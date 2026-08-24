# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-24  
**Branch:** `main`  
**Versi terbaru:** v2.27.1

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.27.1 (GPS Detail + Watermark + Bug Fixes) |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| App Running | `https://nasbpfsby.duckdns.org:5000` |
| WordPress Posts | 10,239+ articles on BPF Surabaya site |
| Sources | Newsmaker.id + Detik Finance (64 articles/scrape) |
| Backend Endpoints | Semua ✅ tested (13+ endpoints) |
| GPS Detail | ✅ Nominatim reverse geocode — kecamatan via display_name fallback |
| Watermark | ✅ 4 baris: perusahaan + tanggal + alamat + koordinat |
| CSP | ✅ Nominatim diizinkan di connect-src |
| SW | ✅ Tidak ada redirect error |

---

## ✅ Yang Sudah Selesai

### Core Features
- [x] Sistem BBM (klaim, verifikasi, pencairan)
- [x] Sistem Kasbon (kode unik, LPJ, alur relay)
- [x] Log Perjalanan / Trip (auto-save ke IndexedDB)
- [x] Dashboard per role (Admin, GA, Finance)
- [x] Dark mode + High contrast mode

### Appointment & Rute
- [x] Marketing Hub (input appointment)
- [x] Chief Driver (board penugasan)
- [x] Atur Rute Otomatis (VRPTW heuristic)
- [x] Geocoding (Nominatim/OpenStreetMap)
- [x] Estimasi penghematan BBM

### Air Minum
- [x] Form pengajuan OB (foto before/after)
- [x] Verifikasi Finance
- [x] PDF tanda terima (Finance + GA)

### Pelamar Kerja
- [x] Form publik `/app/apply`
- [x] Dashboard Receptionist (verifikasi, kehadiran)
- [x] Laporan PDF per tahap

### Aset & Pemeliharaan
- [x] 15 unit AC kantor + 8 kendaraan
- [x] Health score otomatis 0–100
- [x] Rekomendasi maintenance

### Overtime ⭐ v2.27.0+
- [x] Overtime Driver (8.665 baris dari Google Sheet)
- [x] Overtime OB/Security (546 baris + form publik)
- [x] Form Overtime Driver di PWA (foto + watermark + GPS)
- [x] Laporan Overtime PDF (File 1) — tabel ringkas semua driver
- [x] Report Detail Per Driver (File 2) — PDF + Excel
- [x] Formulir Permohonan Overtime PDF — blok TTD + foto link
- [x] **GPS detail disimpan ke DB** — kelurahan/kecamatan/kota/provinsi/kode_pos ⭐ NEW

### Multi-Cabang
- [x] Isolasi data penuh per cabang
- [x] 10 cabang (SBY, JKT, JKT2, BDG, SMG, MLG, MDN, BJM, PLM, LPG)
- [x] Access filtering — user hanya lihat site cabang sendiri

### PWA Driver ⭐ v2.27.0+
- [x] 5 tab: BBM, Kasbon, Trip, OT, Rapor
- [x] Foto upload: **2 tombol (📷 Kamera + 🖼️ Galeri)** ⭐ FIXED
- [x] Offline-first (IndexedDB)
- [x] Auto-save trip draft ke IndexedDB ⭐ NEW
- [x] **GPS detail box di semua tab** — BBM, Trip, OT ⭐ FIXED
- [x] **GPS auto-detect saat mount** ⭐ FIXED
- [x] **Watermark 4 baris** — perusahaan + tanggal + alamat + koordinat ⭐ FIXED
- [x] **GPS detail disimpan ke DB** — BBM, Trip, OT ⭐ NEW

### News Scraper (IT — Multi-Cabang) ⭐ v2.26.0+

#### Scraping
- [x] Scrape newsmaker.id + Detik Finance (64 artikel/scrape)
- [x] Source selector — Semua Sumber / Newsmaker / Detik

#### WordPress Integration
- [x] Multi-site management (10 cabang)
- [x] Upload gambar ke WordPress (featured image + inline)
- [x] Password toggle 👁/🙈 di site card & form

#### SEO
- [x] 7 Algoritma SEO + Financial Authority Backlinks

#### UI/UX
- [x] Tab-Based Layout (7 tabs: Dashboard/Sites/Scrape/Upload/SEO/Analytics/Report)
- [x] Tab Report — detail per-artikel + filter + export CSV
- [x] Settings panel — daily limit configurable (1-100)

### User Management ⭐ v2.27.0
- [x] Branch assignment — semua user punya branch_code
- [x] Branch name display — tabel tampilkan nama cabang

### Login Page ⭐ v2.27.0
- [x] UI Upgrade — gradient button, icon prefix, clean design

### Security & Infrastructure ⭐ v2.27.1
- [x] **CSP connect-src** — tambah nominatim.openstreetmap.org untuk GPS detail ⭐ FIXED
- [x] **Service Worker** — hapus /app/ dari SHELL (redirect error) + redirect:'follow' ⭐ FIXED
- [x] **Nginx cache-busting** — assets (1 tahun), SPA routes (no-cache), static (30 hari) ⭐ NEW
- [x] **GPS kecamatan fallback** — municipality + district + subdistrict + display_name parse ⭐ FIXED

### Keamanan
- [x] Login PIN + session-based
- [x] CSRF protection
- [x] Role-based access (20 role)
- [x] Audit trail (30+ action types)
- [x] Security headers (CSP, X-Frame-Options)
- [x] Rate limiting
- [x] Backup DB otomatis

### Deployment
- [x] Docker Compose ready (db, web, redis, backup)
- [x] nginx.conf untuk HTTPS (nextcloud_nginx)
- [x] DEPLOY_FRESH.md — step-by-step guide

### Database ⭐ v2.27.1
- [x] **transactions** — tambah kolom GPS detail (kelurahan/kecamatan/kota/provinsi/kode_pos)
- [x] **trip_masters** — tambah kolom GPS detail (8 kolom)
- [x] **overtime_driver** — tambah kolom GPS detail (8 kolom)

---

## 🔄 Yang Sedang Dikerjakan

- (kosong — semua fitur sudah selesai)

---

## 📋 Yang Belum Dikerjakan

### Fitur Baru (Ide)
- [ ] Laporan otomatis mingguan via email
- [ ] Approval berjenjang (multi-level)
- [ ] Integrasi payment gateway
- [ ] Dashboard mobile khusus admin
- [ ] Export PDF batch (multi-report)

### Peningkatan
- [ ] Optimasi performa query database
- [ ] Multi-bahasa (Indonesia + English)
- [ ] Aksesibilitas lebih baik (screen reader)

---

## 🐛 Bug / Issue Terbuka

### Fixed in v2.27.1
- ✅ GPS detail kecamatan kosong — tambah municipality/district/subdistrict + display_name fallback
- ✅ GPS detailedLocation ReferenceError — variable addr belum didefinisikan
- ✅ GPS detail box tidak muncul di TripTab + OvertimeDriverTab
- ✅ CSP memblokir Nominatim — tambah ke connect-src
- ✅ Service Worker redirect error — hapus /app/ dari SHELL
- ✅ Photo upload hanya 1 tombol — tambah 📷 Kamera + 🖼️ Galeri
- ✅ GPS harus klik manual — auto locate saat mount
- ✅ Watermark font terlalu besar — proporsional + tambah koordinat

### Remaining
- Backend tests: 20 test gagal di local = integration tests butuh DB (berjalan di CI Docker)

---

## 📝 Catatan untuk Sesi Berikutnya

Ketik di awal sesi:
> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

### Sesi 2026-08-24 — Bug Fix & GPS Detail (v2.27.1)

1. ✅ Fix GPS kecamatan kosong (Nominatim municipality/district)
2. ✅ Fix GPS detailedLocation ReferenceError (addr undefined)
3. ✅ GPS detail box di TripTab + OvertimeDriverTab
4. ✅ CSP connect-src — tambah nominatim.openstreetmap.org
5. ✅ Service Worker — fix redirect error + redirect:'follow'
6. ✅ Photo upload 2 tombol (Kamera + Galeri)
7. ✅ GPS auto-detect saat mount
8. ✅ Watermark proporsional + koordinat
9. ✅ Nginx cache-busting config
10. ✅ GPS detail disimpan ke DB (3 tabel)
11. ✅ Backend BBM/OT/Trip terima GPS detail

---

## 🔗 Link Penting

| Link | URL |
|------|-----|
| App (online) | `https://nasbpfsby.duckdns.org:5000` |
| App (local) | `http://localhost:5001` |
| GitHub | `https://github.com/bestprofitsurabaya/bpf-workhub` |
| Login | `https://nasbpfsby.duckdns.org:5000/app/login` |
| News Scraper | `https://nasbpfsby.duckdns.org:5000/app/it` |

---

## 👥 Akun Penting

| Role | Username | PIN | Home | Branch |
|------|----------|-----|------|--------|
| Admin | `admin` | `123456` | `/app/dashboard` | All |
| IT HO | `it_hu` | `123456` | `/app/it` | Kantor Pusat Jakarta |
| IT Surabaya | `it_sby` | `123456` | `/app/it` | Cabang Surabaya |
| IT Jakarta 2 | `it_jkt2` | `123456` | `/app/it` | Cabang Pacific Place |
| IT Bandung | `it_bdg` | `123456` | `/app/it` | Cabang Bandung |
| IT Semarang | `it_smg` | `123456` | `/app/it` | Cabang Semarang |
| IT Malang | `it_mlg` | `123456` | `/app/it` | Cabang Malang |
| IT Medan | `it_mdn` | `123456` | `/app/it` | Cabang Medan |
| IT Banjarmasin | `it_bjm` | `123456` | `/app/it` | Cabang Banjarmasin |
| IT Palembang | `it_plm` | `123456` | `/app/it` | Cabang Palembang |
| IT Lampung | `it_lpg` | `123456` | `/app/it` | Cabang Lampung |

### Backend API Endpoints (tested ✅)

| Endpoint | Method | Fungsi |
|----------|--------|--------|
| `/api/auth/login` | POST | Login |
| `/api/auth/me` | GET | Current user |
| `/api/users` | GET | List users + branch_code |
| `/api/branches` | GET | List branches |
| `/api/scraper/sites` | GET | List WP sites (filtered by branch) |
| `/api/scraper/settings` | GET/POST | Daily limit settings |
| `/api/scraper/schedule` | GET | Optimal publish schedule |
| `/api/scraper/analytics` | GET | Performance analytics |
| `/api/scraper/report` | GET | Upload report per-article |
| `/api/scraper/report/export` | GET | Export CSV |
| `/api/overtime/report` | GET | Laporan OT ringkas (PDF) |
| `/api/overtime/detail-report` | GET | Report detail per driver (PDF/Excel) |
| `/api/overtime/form-pdf` | GET | Formulir Permohonan OT (PDF) |

### GPS Detail Fields (disimpan ke DB)

| Field | Tabel | Contoh |
|-------|-------|--------|
| `gps_lat` | transactions, trip_masters, overtime_driver | `-6.20800` |
| `gps_lon` | transactions, trip_masters, overtime_driver | `106.83320` |
| `gps_address` | transactions, trip_masters, overtime_driver | `Jl. Wilis, Guntur, Jakarta Selatan, 12980` |
| `gps_kelurahan` | transactions, trip_masters, overtime_driver | `Guntur` |
| `gps_kecamatan` | transactions, trip_masters, overtime_driver | `Setiabudi` |
| `gps_kota` | transactions, trip_masters, overtime_driver | `Jakarta Selatan` |
| `gps_provinsi` | transactions, trip_masters, overtime_driver | `DKI Jakarta` |
| `gps_kode_pos` | transactions, trip_masters, overtime_driver | `12980` |

---

*BPF WorkHub v2.27.1 · Progres Tracker*
