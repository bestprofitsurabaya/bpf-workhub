# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-24  
**Branch:** `main`  
**Versi terbaru:** v2.27.0

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.27.0 (Overtime Form + GPS Detail + Auto-Save + Mobile Fix) |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| Pytest | 223/243 passed (20 = integration tests butuh DB) |
| Vitest | 82/82 ✅ |
| App Running | `https://nasbpfsby.duckdns.org:5000` |
| WordPress Posts | 10,239 articles on BPF Surabaya site |
| Sources | Newsmaker.id + Detik Finance (64 articles/scrape) |
| Backend Endpoints | Semua ✅ tested (13 endpoints) |

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

### Overtime ⭐ v2.27.0
- [x] Overtime Driver (8.665 baris dari Google Sheet)
- [x] Overtime OB/Security (546 baris + form publik)
- [x] Form Overtime Driver di PWA (foto + watermark + GPS)
- [x] Form Overtime OB/Security (foto + watermark + GPS)
- [x] Source tracking ('sheet' vs 'form') di database
- [x] Filter source di dashboard GA HR & PDF report
- [x] Offline support untuk overtime driver (overtime_queue)
- [x] Auto-refresh saat login/logout
- [x] Notifikasi realtime
- [x] **Laporan Overtime PDF (File 1)** — tabel ringkas semua driver ⭐ NEW
- [x] **Report Detail Per Driver (File 2)** — timestamp, form no, plat, jam in/out ⭐ NEW
- [x] **Excel Export** — kolom Biaya kosong untuk GA HR isi manual ⭐ NEW
- [x] **Formulir Permohonan Overtime PDF** — ID form, detail OT, blok TTD, foto link ⭐ NEW
- [x] **Endpoint 3 PDF**: `/api/overtime/report`, `/api/overtime/detail-report`, `/api/overtime/form-pdf` ⭐ NEW

### Multi-Cabang
- [x] Isolasi data penuh per cabang
- [x] Ringkasan cabang di dashboard
- [x] Audit log bertanda cabang
- [x] PDF konsolidasi lintas cabang

### PWA Driver ⭐ v2.27.0
- [x] 5 tab: BBM, Kasbon, Trip, OT, Rapor
- [x] Foto upload: kamera + galeri
- [x] Offline-first (IndexedDB)
- [x] Watermark foto (GPS + timestamp)
- [x] Notifikasi real-time
- [x] **Detail Lokasi GPS** — kelurahan, kecamatan, kota, provinsi, kode pos ⭐ NEW
- [x] **Auto-Save Trip** — draft tersimpan otomatis di IndexedDB ⭐ NEW
- [x] **Trip Tab Mobile Responsive** — 3 kolom → 2 kolom di bawah 480px ⭐ NEW
- [x] **GPS Box** — tampilkan detail lokasi lengkap + SPBU terdekat ⭐ NEW

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
- [x] Newsmaker.id + Detik Finance backlinks
- [x] Content uniqueness (parafrase 25+ sinonim)
- [x] Internal linking (keyword overlap)
- [x] Advanced Schema (NewsArticle + Breadcrumb + Org + FAQ)
- [x] Sitemap ping (Google + IndexNow)
- [x] Smart scheduling

#### UI/UX
- [x] Tab-Based Layout (6 tabs: Dashboard/Sites/Scrape/Upload/SEO/Analytics/Report)
- [x] Article Preview Cards
- [x] Upload Queue
- [x] Real-Time Upload Log
- [x] **Tab Report** — detail per-artikel + filter + export CSV ⭐ NEW
- [x] **Settings panel** — daily limit configurable (1-100) ⭐ NEW
- [x] Progress tracking (SSE polling)
- [x] Upload history

#### Reports
- [x] **Upload Report** — per-article detail (judul, status, SEO, site, source) ⭐ NEW
- [x] **Filter report** — tanggal, site, status, source, search ⭐ NEW
- [x] **Export CSV** — download laporan lengkap ⭐ NEW
- [x] **Summary cards** — total, new, updated, error, avg SEO ⭐ NEW
- [x] Performance analytics (by site, by date)

### User Management ⭐ v2.27.0
- [x] **Branch assignment** — semua user punya branch_code ⭐ NEW
- [x] **Branch name display** — tabel tampilkan nama cabang (bukan kode) ⭐ NEW
- [x] **Access control** — user hanya lihat site cabang sendiri ⭐ NEW
- [x] **Branch names** — Cabang Surabaya, Cabang Pacific Place, dll ⭐ NEW

### Login Page ⭐ v2.27.0
- [x] **UI Upgrade** — gradient button, icon prefix, clean design ⭐ NEW
- [x] **Role badge removed** — lebih ringkas ⭐ NEW
- [x] **Background orbs** — dekoratif ⭐ NEW

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
- [x] init.sql — 35 tabel
- [x] requirements.txt — termasuk beautifulsoup4 + lxml + openpyxl

### Testing & CI/CD
- [x] 243 pytest (backend)
- [x] 82 Vitest (frontend)
- [x] Browser verification (Puppeteer)
- [x] GitHub Actions CI/CD

### Dokumentasi
- [x] README.md v2.27.0
- [x] CHANGELOG.md v2.27.0
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
- ✅ Fixed: rename it_ef → it_sby + URL update
- ✅ Fixed: password tidak tampil di site card & edit form
- ✅ Fixed: access control — branch_code semua site
- ✅ Fixed: branches API return {branches:[...]} — extract array
- ✅ Fixed: TripTab mobile responsive — 3 kolom → 2 kolom

---

## 📝 Catatan untuk Sesi Berikutnya

Ketik di awal sesi:
> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

### Sesi 2026-08-24 — Sesi Besar (v2.27.0) ⭐⭐⭐
**30+ commits dalam 1 sesi!**

1. ✅ Fix error 500 `/api/scraper/check`
2. ✅ Update scraper parsing newsmaker.id
3. ✅ Deployment readiness
4. ✅ Foto bukti timestamp form OT
5. ✅ Form Overtime Driver di PWA
6. ✅ Source tracking (sheet vs form)
7. ✅ Filter source di dashboard GA HR
8. ✅ Audit PWA driver — 10 anomaly
9. ✅ Foto upload galeri + kamera
10. ✅ Update .md files v2.24
11. ✅ Progress tracking + upload history
12. ✅ Upload gambar artikel ke WordPress
13. ✅ SEO backlinks + CTA widget
14. ✅ 7 Algoritma SEO
15. ✅ Multi-Branch — 10 cabang + access filtering
16. ✅ Duplicate prevention — paginate 500 + fuzzy
17. ✅ UI/UX Overhaul — 10 upgrades
18. ✅ Rename it_ef → it_sby (URL: `/app/it`)
19. ✅ Role per cabang (10 users)
20. ✅ Detik Finance scraping — 48 artikel
21. ✅ Source selector + backlink
22. ✅ Password toggle 👁/🙈
23. ✅ WP URL fixed — best-profit-futures-<city>.com
24. ✅ Daily limit configurable — settings panel
25. ✅ Tab Report — detail per-artikel + filter + CSV
26. ✅ Error handling — DNS/SSL/Timeout
27. ✅ Branch assignment — semua user punya branch_code
28. ✅ Branch name update — Cabang Surabaya, Cabang Pacific Place
29. ✅ Login page UI upgrade
30. ✅ Overtime Report — 3 format PDF + Excel
31. ✅ Detail Lokasi GPS — kelurahan, kecamatan, kota
32. ✅ Auto-Save Trip — IndexedDB draft
33. ✅ TripTab mobile responsive
34. ✅ Sistem cleanup — hapus 536 file lama

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
| GA | `ga_officer` | `123456` | `/app/ga` | Cabang Surabaya |
| Finance | `finance_officer` | `123456` | `/app/finance` | Cabang Surabaya |
| Driver | `wicak` | `123456` | `/app/driver` | Cabang Surabaya |
| GA HR | `ga_hr_officer` | `123456` | `/app/ga-hr` | Cabang Surabaya |
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

### Branch List

| Code | Name | Domain WP |
|------|------|-----------|
| SBY | Cabang Surabaya | best-profit-futures-surabaya.com |
| JKT | Kantor Pusat Jakarta | best-profit-futures-equitytower.com |
| JKT2 | Cabang Pacific Place | best-profit-futures-pacificplace.com |
| BDG | Cabang Bandung | best-profit-futures-bandung.com |
| SMG | Cabang Semarang | best-profit-futures-semarang.com |
| MLG | Cabang Malang | best-profit-futures-malang.com |
| MDN | Cabang Medan | best-profit-futures-medan.com |
| BJM | Cabang Banjarmasin | best-profit-futures-banjarmasin.com |
| PLM | Cabang Palembang | best-profit-futures-palembang.com |
| LPG | Cabang Lampung | best-profit-futures-lampung.com |

### Backend API Endpoints (13 endpoints tested ✅)

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

---

*BPF WorkHub v2.27.0 · Progres Tracker*
