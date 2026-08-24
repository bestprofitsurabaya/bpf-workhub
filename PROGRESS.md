# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-24  
**Branch:** `main`  
**Versi terbaru:** v2.26.0

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.26.0 (Detik Finance + Report + Settings + Fixes) |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| Pytest | 223/243 passed (20 = integration tests butuh DB) |
| Vitest | 82/82 ✅ |
| App Running | `https://nasbpfsby.duckdns.org:5000` |
| WordPress Posts | 10,239 articles on BPF Surabaya site |
| Sources | Newsmaker.id + Detik Finance (64 articles/scrape) |

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
- [x] Form Overtime Driver di PWA (foto + watermark + GPS)
- [x] Form Overtime OB/Security (foto + watermark + GPS)
- [x] Source tracking ('sheet' vs 'form') di database
- [x] Filter source di dashboard GA HR & PDF report
- [x] Offline support untuk overtime driver (overtime_queue)
- [x] Auto-refresh saat login/logout
- [x] Notifikasi realtime

### Multi-Cabang
- [x] Isolasi data penuh per cabang
- [x] Ringkasan cabang di dashboard
- [x] Audit log bertanda cabang
- [x] PDF konsolidasi lintas cabang

### PWA Driver
- [x] 5 tab: BBM, Kasbon, Trip, OT, Rapor
- [x] Foto upload: kamera + galeri
- [x] Offline-first (IndexedDB)
- [x] Watermark foto (GPS + timestamp)
- [x] Notifikasi real-time

### News Scraper (IT — Multi-Cabang) ⭐ v2.26.0

#### Scraping
- [x] Scrape artikel dari newsmaker.id (struktur baru Tailwind)
- [x] **Scrape Detik Finance** (finance.detik.com + keyword filter) ⭐ NEW
- [x] **Scrape Detik Tag** (/tag/emas, /tag/komoditas) ⭐ NEW
- [x] **Source selector** — Semua Sumber / Newsmaker / Detik ⭐ NEW
- [x] Total 64 artikel unik per scrape (16 NM + 48 DT)
- [x] Source backlink otomatis di setiap artikel
- [x] Parser tanggal Indonesia (Agu/Agustus)

#### WordPress Integration
- [x] WordPress integration (multi-site, 10 cabang)
- [x] Upload gambar ke WordPress (featured image + inline)
- [x] **Password view/hide toggle** di site card & form ⭐ NEW
- [x] **Edit form tampilkan password tersimpan** ⭐ NEW
- [x] Duplicate prevention (500 posts + fuzzy title match)
- [x] User-friendly error messages (DNS/SSL/Timeout)

#### SEO
- [x] 7 Algoritma SEO
- [x] SEO Backlinks (5 BPF sites + 23 authority + CTA widget)
- [x] **Newsmaker.id backlink** di setiap artikel ⭐ NEW
- [x] **Detik Finance backlink** di setiap artikel ⭐ NEW
- [x] Content uniqueness (parafrase 25+ sinonim)
- [x] Internal linking (keyword overlap)
- [x] Advanced Schema (NewsArticle + Breadcrumb + Org + FAQ)
- [x] Sitemap ping (Google + IndexNow)
- [x] Smart scheduling

#### UI/UX
- [x] UI/UX Overhaul (10 upgrades: dashboard, tabs, cards, dark mode, FAB, onboarding)
- [x] **Tab Report** — detail per-artikel + filter + export CSV ⭐ NEW
- [x] **Settings panel** — daily limit configurable (1-100) ⭐ NEW
- [x] **Badge dinamis** — limit tampilkan angka real-time ⭐ NEW
- [x] **Password toggle** — 👁/🙈 di site card & form ⭐ NEW
- [x] Progress tracking (SSE polling)
- [x] Upload history (filter tanggal/aksi)

#### Multi-Branch & Users
- [x] Multi-Branch Users (10 cabang + access filtering)
- [x] **Rename it_ef → it_sby** (URL: `/app/it`) ⭐ NEW
- [x] **Role per cabang** (it_sby, it_hu, it_bdg, dll) ⭐ NEW
- [x] **URL pattern** — best-profit-futures-<city>.com ⭐ NEW
- [x] **WP URL fixed** — SBY, BDG, SMG, MLG, MDN, BJM, LPG active ⭐ NEW

#### Reports & Analytics
- [x] **Upload Report** — per-article detail (judul, status, SEO, site, source) ⭐ NEW
- [x] **Filter report** — tanggal, site, status, source, search ⭐ NEW
- [x] **Export CSV** — download laporan lengkap ⭐ NEW
- [x] **Summary cards** — total, new, updated, error, avg SEO ⭐ NEW
- [x] Performance analytics (by site, by date)

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
- [x] init.sql — 35 tabel (termasuk 16 tabel v2.x)
- [x] requirements.txt — termasuk beautifulsoup4 + lxml

### Testing & CI/CD
- [x] 243 pytest (backend)
- [x] 82 Vitest (frontend)
- [x] Browser verification (Puppeteer)
- [x] GitHub Actions CI/CD

### Dokumentasi
- [x] README.md v2.26.0
- [x] CHANGELOG.md v2.26.0
- [x] DEPLOY_FRESH.md
- [x] SECURITY.md
- [x] USER_GUIDE.md
- [x] USER_LIST.md
- [x] PELATIHAN.md
- [x] PRESENTASI.md
- [x] ONEPAGER.md

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
- [ ] Sistem absensi digital

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
- ✅ Fixed: duplicate prevention — paginate 500 + fuzzy matching
- ✅ Fixed: WordPress image upload (featured + inline)
- ✅ Fixed: upload history + progress tracking
- ✅ Fixed: rename it_ef → it_sby + URL update
- ✅ Fixed: password tidak tampil di site card & edit form
- ✅ Fixed: edit form selalu reset password ke kosong
- ✅ Fixed: error DNS/SSL/Timeout → pesan jelas untuk user
- ✅ Fixed: daily limit hardcoded → configurable dari UI
- ✅ Fixed: badge "🔴 Limit" → "⏸️ Jeda — X/10 hari ini"

---

## 📝 Catatan untuk Sesi Berikutnya

Ketik di awal sesi:
> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

Setelah selesai kerja, update file ini dengan status terbaru.

### Sesi 2026-08-24 — Sesi Besar (v2.26.0) ⭐⭐⭐
**25+ commits dalam 1 sesi!**

1. ✅ Fix error 500 `/api/scraper/check` — install bs4 di Docker container
2. ✅ Update scraper parsing — struktur baru newsmaker.id (Tailwind CSS)
3. ✅ Deployment readiness — docker-compose, nginx, init.sql, DEPLOY_FRESH.md
4. ✅ Foto bukti timestamp — form OB/Security + watermark otomatis
5. ✅ Form Overtime Driver di PWA — tab baru ⏰ OT
6. ✅ Source tracking — pisahkan data 'sheet' vs 'form'
7. ✅ Filter source di dashboard GA HR & PDF report
8. ✅ Audit PWA driver — 10 anomaly diperbaiki
9. ✅ Foto upload support galeri + kamera
10. ✅ Update semua .md files
11. ✅ Progress tracking + upload history
12. ✅ Upload gambar ke WordPress (featured + inline)
13. ✅ SEO backlinks — 5 BPF sites + 23 authority + CTA widget
14. ✅ 7 Algoritma SEO
15. ✅ Multi-Branch — 10 cabang + user access filtering
16. ✅ Duplicate prevention — paginate 500 + fuzzy title matching
17. ✅ UI/UX Overhaul — 10 upgrades
18. ✅ Rename it_ef → it_sby (URL: `/app/it`)
19. ✅ Role per cabang (10 users)
20. ✅ Detik Finance scraping — 48 artikel/commodity keyword
21. ✅ Source selector — Semua Sumber / Newsmaker / Detik
22. ✅ Source backlink — Newsmaker + Detik di setiap artikel
23. ✅ Password toggle — 👁/🙈 di site card & form
24. ✅ WP URL fixed — pattern best-profit-futures-<city>.com
25. ✅ Daily limit configurable — settings panel di Dashboard
26. ✅ Tab Report — detail per-artikel + filter + export CSV
27. ✅ Error handling — DNS/SSL/Timeout → pesan user-friendly

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
| News Scraper (semua) | `https://nasbpfsby.duckdns.org:5000/app/it` |

---

## 👥 Akun Penting

| Role | Username | PIN | Home | Branch |
|------|----------|-----|------|--------|
| Admin | `admin` | `123456` | `/app/dashboard` | All |
| GA | `ga_officer` | `123456` | `/app/ga` | SBY |
| Finance | `finance_officer` | `123456` | `/app/finance` | SBY |
| Driver | `wicak` | `123456` | `/app/driver` | SBY |
| GA HR | `ga_hr_officer` | `123456` | `/app/ga-hr` | SBY |
| IT HO | `it_hu` | `123456` | `/app/it` | JKT |
| IT Surabaya | `it_sby` | `123456` | `/app/it` | SBY |
| IT Jakarta 2 | `it_jkt2` | `123456` | `/app/it` | JKT2 |
| IT Bandung | `it_bdg` | `123456` | `/app/it` | BDG |
| IT Semarang | `it_smg` | `123456` | `/app/it` | SMG |
| IT Malang | `it_mlg` | `123456` | `/app/it` | MLG |
| IT Medan | `it_mdn` | `123456` | `/app/it` | MDN |
| IT Banjarmasin | `it_bjm` | `123456` | `/app/it` | BJM |
| IT Palembang | `it_plm` | `123456` | `/app/it` | PLM |
| IT Lampung | `it_lpg` | `123456` | `/app/it` | LPG |

### WordPress URL Pattern

| Cabang | Domain | Status |
|--------|--------|--------|
| SBY | `best-profit-futures-surabaya.com` | ✅ Aktif |
| JKT HO | `best-profit-futures-equitytower.com` | ⏳ Pending |
| JKT2 | `best-profit-futures-pacificplace.com` | ⏳ Pending |
| BDG | `best-profit-futures-bandung.com` | ✅ Resolve |
| SMG | `best-profit-futures-semarang.com` | ✅ Resolve |
| MLG | `best-profit-futures-malang.com` | ✅ Resolve |
| MDN | `best-profit-futures-medan.com` | ✅ Resolve |
| BJM | `best-profit-futures-banjarmasin.com` | ✅ Resolve |
| PLM | `best-profit-futures-palembang.com` | ⏳ Pending |
| LPG | `best-profit-futures-lampung.com` | ✅ Resolve |

### Daily Limit Settings
- Default: 10 artikel/hari
- Configurable dari UI: Tab Dashboard → ⚙️ Pengaturan
- Range: 1-100
- Disimpan ke: `data/news_scraper/scraper_settings.json`

---

*BPF WorkHub v2.26.0 · Progres Tracker*
