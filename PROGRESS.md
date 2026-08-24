# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-21  
**Branch:** `main`  
**Versi terbaru:** v2.23.0

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.23.0 (News Scraper + role it_ef / IT Surabaya) |
| Docs | v1.0 (commit `48a439c`) |
| CI Fix | v1.0+fix (commit `03f5f17`) |
| Pytest | 223/243 passed (20 = integration tests butuh DB) |
| Vitest | 82/82 ✅ |
| Video | 10 mp4 (7 role + 3 baru) |
| App Running | `http://localhost:5001` |
| Online | `https://nasbpfsby.duckdns.org:5000` |

---

## ✅ Yang Sudah Selesai

### Core Features
- [x] Sistem BBM (klaim, verifikasi, pencairan)
- [x] Sistem Kasbon ( kode unik, LPJ, alur relay)
- [x] Log Perjalanan / Trip
- [x] Dashboard per role (Admin, GA, Finance)
- [x] Dark mode + High contrast mode

### Appointment & Rute
- [x] Marketing Hub (input appointment)
- [x] Chief Driver (board penugasan)
- [x] Atur Rute Otomatis (VRPTW heuristic)
- [x] Atur Rute Manual
- [x] Geocoding (Nominatim/OpenStreetMap)
- [x] Estimasi penghematan BBM

### Air Minum
- [x] Form pengajuan OB (foto before/after)
- [x] Verifikasi Finance
- [x] PDF tanda terima (Finance + GA)

### Pelamar Kerja
- [x] Form publik `/app/apply`
- [x] Dashboard Receptionist (verifikasi, kehadiran)
- [x] Dashboard Traineer (read-only)
- [x] Laporan PDF per tahap
- [x] Dropdown User diatur Receptionist

### Aset & Pemeliharaan
- [x] 15 unit AC kantor
- [x] 8 kendaraan asli
- [x] 12 komponen
- [x] Health score otomatis 0–100
- [x] Rekomendasi maintenance

### Overtime
- [x] Overtime Driver (8.665 baris dari Google Sheet)
- [x] Overtime OB/Security (546 baris + form publik)
- [x] Auto-refresh saat login/logout
- [x] Notifikasi realtime

### Multi-Cabang
- [x] Isolasi data penuh per cabang
- [x] Ringkasan cabang di dashboard
- [x] Audit log bertanda cabang
- [x] PDF konsolidasi lintas cabang

### PWA Driver
- [x] 4 tab: BBM, Kasbon, Trip, Rapor
- [x] Offline-first (IndexedDB)
- [x] Watermark foto (GPS + timestamp)
- [x] Notifikasi real-time

### Keamanan
- [x] Login PIN + session-based
- [x] CSRF protection
- [x] Role-based access (10 role)
- [x] Audit trail (30+ action types)
- [x] Security headers (CSP, X-Frame-Options)
- [x] Rate limiting
- [x] Backup DB otomatis

### Testing & CI/CD
- [x] 243 pytest (backend)
- [x] 82 Vitest (frontend)
- [x] Browser verification (Puppeteer)
- [x] GitHub Actions CI/CD

### Dokumentasi
- [x] README.md v1.0
- [x] CHANGELOG.md v1.0
- [x] DEPLOYMENT.md v1.0
- [x] SECURITY.md v1.0
- [x] USER_GUIDE.md v1.0
- [x] USER_LIST.md v1.0
- [x] PELATIHAN.md v1.0
- [x] PRESENTASI.md v1.0
- [x] ONEPAGER.md v1.0

### Video Walkthrough
- [x] admin.mp4
- [x] ob.mp4
- [x] finance.mp4
- [x] ga.mp4
- [x] marketing.mp4
- [x] chief.mp4
- [x] driver.mp4
- [x] receptionist.mp4 (baru)
- [x] traineer.mp4 (baru)
- [x] ga_hr.mp4 (baru)
- [x] walkthrough-all.mp4

---

## 🔄 Yang Sedang Dikerjakan

- (kosong — semua fix sudah selesai)

---

## 📋 Yang Belum Dikerjakan

### Fitur Baru (Ide)
- [ ] Laporan otomatis mingguan via email
- [ ] Approval berjenjang (multi-level)
- [ ] Integrasi payment gateway
- [ ] Dashboard mobile khusus admin
- [ ] Export PDF batch (multi-report)
- [ ] Sistem absensi digital
- [ ] Integrasi fingerprint / face recognition
- [ ] Chat in-app antar role
- [ ] Sistem ticketing / helpdesk

### Peningkatan
- [ ] Optimasi performa query database
- [ ] Caching lebih agresif untuk data statis
- [ ] PWA untuk semua role (bukan hanya driver)
- [ ] Multi-bahasa (Indonesia + English)
- [ ] Aksesibilitas lebih baik (screen reader)

---

## 🐛 Bug / Issue Terbuka

- Backend tests: 20 test gagal di local = integration tests butuh DB (berjalan di CI Docker)
- ✅ Fixed 2026-08-24: error 500 `/api/scraper/check` — bs4 tidak terinstall di root Python

---

## 📝 Catatan untuk Sesi Berikutnya

Ketik di awal sesi:
> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

Setelah selesai kerja, update file ini dengan status terbaru.

### Sesi 2026-08-24
1. ✅ Fix error 500 di `/api/scraper/check` — add top-level try/except ke semua scraper routes
2. ✅ Install `beautifulsoup4` + `lxml` di server (root Python)
3. ✅ Tambah `beautifulsoup4`, `lxml` ke `requirements.txt`
4. ✅ Fix broken indentation di `upload_articles()` dan `check_duplicates()`
5. ✅ App restart (HUP) — bs4 terload

### Sesi 2026-08-21
1. ✅ Tambah role `it_ef` (IT Surabaya) — backend + frontend
2. ✅ Buat `routes_news_scraper.py` — API WordPress site management, scrape, upload, SEO, backlinks, duplicates
3. ✅ Buat `ItEfView.vue` — UI News Scraper & Content Management
4. ✅ Register module di `app.py`
5. ✅ Update router, sidebar menu, ROLES list
6. ✅ 82/82 Vitest ✅ | Module import ✅
7. ✅ `beautifulsoup4` + `lxml` terinstall di server

### Sesi Terakhir (2026-08-20)
1. ✅ Restrukturisasi 9 file .md ke v1.0 (bahasa humanis)
2. ✅ Fix rehearsal.mjs & record.mjs (user RIVAN → wicak, tambah 3 role)
3. ✅ Generate 3 video baru (ga_hr, receptionist, traineer)
4. ✅ Buat PROGRESS.md sebagai tracker lintas sesi
5. ✅ Fix CI: UsersView.test.js — tambah Pinia setup
6. ✅ Analisis fitur: tidak ada penurunan fungsi dari versi lama
7. ✅ Push 3 commit: `48a439c`, `a2c5e46`, `03f5f17`

---

## 🔗 Link Penting

| Link | URL |
|------|-----|
| App (local) | `http://localhost:5001` |
| App (online) | `https://nasbpfsby.duckdns.org:5000` |
| GitHub | `https://github.com/bestprofitsurabaya/bpf-workhub` |
| Login | `http://localhost:5001/app/login` |
| GA HR | `http://localhost:5001/app/ga-hr` |

---

## 👥 Akun Penting

| Role | Username | PIN | Home |
|------|----------|-----|------|
| Admin | `admin` | `123456` | `/app/dashboard` |
| GA | `ga_officer` | `123456` | `/app/ga` |
| Finance | `finance_officer` | `123456` | `/app/finance` |
| Driver | `wicak` | `123456` | `/app/driver` |
| GA HR | `ga_hr_officer` | `123456` | `/app/ga-hr` |
| IT Surabaya | `it_ef` | `123456` | `/app/it-ef` | (branch SBY) |

---

*BPF WorkHub · Progres Tracker*
