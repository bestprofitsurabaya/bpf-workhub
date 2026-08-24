# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-24  
**Branch:** `main`  
**Versi terbaru:** v2.24.0

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.24.0 (Overtime Driver Form + Audit Fix + Deployment Ready) |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| Pytest | 223/243 passed (20 = integration tests butuh DB) |
| Vitest | 82/82 ✅ |
| App Running | `https://nasbpfsby.duckdns.org:5000` |

---

## ✅ Yang Sudah Selesai

### Core Features
- [x] Sistem BBM (klaim, verifikasi, pencairan)
- [x] Sistem Kasbon (kode unik, LPJ, alur relay)
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
- [x] **Form Overtime Driver di PWA** (foto + watermark + GPS) ⭐ NEW
- [x] **Form Overtime OB/Security** (foto + watermark + GPS) ⭐ NEW
- [x] **Source tracking** ('sheet' vs 'form') di database ⭐ NEW
- [x] **Filter source** di dashboard GA HR & PDF report ⭐ NEW
- [x] **Offline support** untuk overtime driver (overtime_queue) ⭐ NEW
- [x] Auto-refresh saat login/logout
- [x] Notifikasi realtime

### Multi-Cabang
- [x] Isolasi data penuh per cabang
- [x] Ringkasan cabang di dashboard
- [x] Audit log bertanda cabang
- [x] PDF konsolidasi lintas cabang

### PWA Driver
- [x] **5 tab: BBM, Kasbon, Trip, OT, Rapor** ⭐ UPDATED
- [x] **Foto upload: kamera + galeri** ⭐ UPDATED
- [x] Offline-first (IndexedDB)
- [x] Watermark foto (GPS + timestamp)
- [x] Notifikasi real-time

### News Scraper (IT Surabaya)
- [x] Scrape artikel dari newsmaker.id (struktur baru Tailwind)
- [x] WordPress integration (multi-site)
- [x] SEO optimization + backlinks
- [x] **Parser tanggal Indonesia** (Agu/Agustus) ⭐ NEW

### Keamanan
- [x] Login PIN + session-based
- [x] CSRF protection
- [x] Role-based access (11 role)
- [x] Audit trail (30+ action types)
- [x] Security headers (CSP, X-Frame-Options)
- [x] Rate limiting
- [x] Backup DB otomatis

### Deployment
- [x] **Docker Compose ready** (db, web, redis, backup) ⭐ NEW
- [x] **nginx.conf** untuk HTTPS (nextcloud_nginx) ⭐ NEW
- [x] **DEPLOY_FRESH.md** — step-by-step guide ⭐ NEW
- [x] **init.sql** — 35 tabel (termasuk 16 tabel v2.x) ⭐ UPDATED
- [x] **requirements.txt** — termasuk beautifulsoup4 + lxml ⭐ UPDATED

### Testing & CI/CD
- [x] 243 pytest (backend)
- [x] 82 Vitest (frontend)
- [x] Browser verification (Puppeteer)
- [x] GitHub Actions CI/CD

### Dokumentasi
- [x] README.md v2.24
- [x] CHANGELOG.md v2.24
- [x] DEPLOY_FRESH.md (baru)
- [x] SECURITY.md
- [x] USER_GUIDE.md
- [x] USER_LIST.md
- [x] PELATIHAN.md
- [x] PRESENTASI.md
- [x] ONEPAGER.md

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
- ✅ Fixed: error 500 `/api/scraper/check` — bs4 tidak terinstall
- ✅ Fixed: scraper parsing newsmaker.id — struktur HTML berubah
- ✅ Fixed: 10 anomaly PWA driver (audit menyeluruh)

---

## 📝 Catatan untuk Sesi Berikutnya

Ketik di awal sesi:
> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

Setelah selesai kerja, update file ini dengan status terbaru.

### Sesi 2026-08-24 (v2.24.0)
1. ✅ Fix error 500 `/api/scraper/check` — install bs4 di Docker container
2. ✅ Update scraper parsing — struktur baru newsmaker.id (Tailwind CSS)
3. ✅ Fix parser tanggal Indonesia (Agu/Agustus)
4. ✅ Deployment readiness — docker-compose, nginx, init.sql, DEPLOY_FRESH.md
5. ✅ Foto bukti timestamp — form OB/Security + watermark otomatis
6. ✅ Form Overtime Driver di PWA — tab baru ⏰ OT
7. ✅ Source tracking — pisahkan data 'sheet' vs 'form'
8. ✅ Filter source di dashboard GA HR & PDF report
9. ✅ Audit PWA driver — 10 anomaly diperbaiki
10. ✅ Foto upload support galeri + kamera (hapus capture attr)
11. ✅ Update semua .md files

### Sesi 2026-08-21 (v2.23.0)
1. ✅ Tambah role `it_ef` (IT Surabaya) — backend + frontend
2. ✅ Buat `routes_news_scraper.py` — 14 API endpoints
3. ✅ Buat `ItEfView.vue` — UI News Scraper & Content Management
4. ✅ Register module di `app.py`
5. ✅ Update router, sidebar menu, ROLES list

---

## 🔗 Link Penting

| Link | URL |
|------|-----|
| App (online) | `https://nasbpfsby.duckdns.org:5000` |
| App (local) | `http://localhost:5001` |
| GitHub | `https://github.com/bestprofitsurabaya/bpf-workhub` |
| Login | `https://nasbpfsby.duckdns.org:5000/app/login` |
| Form OT OB/Security | `https://nasbpfsby.duckdns.org:5000/app/overtime-form` |
| GA HR | `https://nasbpfsby.duckdns.org:5000/app/ga-hr` |
| News Scraper | `https://nasbpfsby.duckdns.org:5000/app/it-ef` |

---

## 👥 Akun Penting

| Role | Username | PIN | Home |
|------|----------|-----|------|
| Admin | `admin` | `123456` | `/app/dashboard` |
| GA | `ga_officer` | `123456` | `/app/ga` |
| Finance | `finance_officer` | `123456` | `/app/finance` |
| Driver | `wicak` | `123456` | `/app/driver` |
| GA HR | `ga_hr_officer` | `123456` | `/app/ga-hr` |
| IT Surabaya | `it_ef` | `123456` | `/app/it-ef` |

---

*BPF WorkHub v2.24.0 · Progres Tracker*
