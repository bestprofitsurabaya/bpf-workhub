# 📋 Changelog — BPF WorkHub v2.28.7

Format: [Keep a Changelog](https://keepachangelog.com/id/ID/1.0.0/) · Versi: [Semantic Versioning](https://semver.org/lang/id/)

---

## Daftar Isi

- [Versi Terbaru](#versi-terbaru)
- [Riwayat Lengkap](#riwayat-lengkap)

---

## Versi Terbaru

### [2.28.7] - 2026-08-25

**Ox Alpha AI Security Review: 24 Bug Fixes — 3 File, CRITICAL + HIGH + MEDIUM**

AI model Ox Alpha (`stealth/ox-alpha` via OpenRouter) dijalankan via curl untuk review security & bug di seluruh codebase. Total **24 bug** ditemukan & di-fix dalam satu sesi.

---

#### `modules/overtime_shared.py` — 6 Fix

**HIGH:**
- **UnboundLocalError saat tanggal kosong** — `tanggal_iso` hanya didefinisikan di blok `else`, tapi dipakai setelah if/else → server crash jika user submit form tanpa tanggal
- **Foto base64 tanpa size limit** — foto 10MB+ bisa masuk ke DB → memory blowup. Kini truncate max 7M chars (~5MB)
- **GPS field simpan string "None"** — `str(None)` → literal `"None"` di DB saat GPS value Python `None`

**MEDIUM:**
- **Dead code waktu validation** — blok `if mulai > selesai: pass` tidak berguna
- **Driver cols list mismatch** — `sheet_row` di cols tapi tidak di params → potential zip mismatch

**LOW:**
- **Dead code serialize** — `if dict: ... else: ...` identik

---

#### `modules/routes_news_scraper.py` — 10 Fix

**CRITICAL:**
- **Hardcoded credentials** — `_WP_SERVER_AUTH = ('human', 'password')` di source code
- **Credential leak ke attacker** — Basic auth server dikirim ke SEMUA host WP termasuk attacker-controlled → dihapus

**HIGH:**
- **SSRF via image_url** — image dari scraped content di-fetch → kini validasi scheme + block private IPs
- **Race condition JSON** — `open(path, 'w')` → kini atomic write via temp file + `os.replace()`
- **HTML injection / XSS** — title, source_name di-interpolate ke HTML tanpa escaping → kini `html.escape()`
- **CSV injection** — nilai `=`, `+`, `-`, `@` bisa eksekusi formula di Excel → kini di-prefix `'`

**MEDIUM:**
- **Duplicate `_seo_analyze`** — didefinisikan 2x → hapus definisi pertama
- **Dead code `_auto_internal_links`** — return unchanged → kini insert "Baca juga" section
- **Silent error swallowing** — `except Exception: pass` → tambah logging

---

#### `modules/routes_overtime.py` — 8 Fix

**HIGH:**
- **SSRF via sheet URL** — admin-configurable URL di-fetch server-side → validasi scheme + block private IPs + `allow_redirects=False`
- **Nama impersonation** — client bisa override `nama` di driver submit → selalu pakai session name
- **GPS data wiped** — `ON DUPLICATE KEY UPDATE gps_lat=VALUES(gps_lat)` tapi GPS tidak di INSERT → GPS jadi NULL setiap refresh. Hapus GPS dari ODKU
- **`.upper()` crash on NULL** — `rows[0].get('posisi').upper()` → AttributeError jika NULL

**MEDIUM:**
- **Operator precedence bug** — `A or B if C else D` → query param `?full=1` diabaikan tanpa JSON body
- **`str(None)` → "None"** — JSON null jadi string literal di update endpoint
- **Filename header injection** — `nama` dengan `\r\n` bisa inject HTTP headers → sanitize dengan regex
- **SVG upload XSS** — `data:image/svg+xml` diterima → `<script>` bisa execute → block SVG

---

**Backend:**
- `modules/overtime_shared.py` — validasi tanggal, foto size limit, GPS None handling, dead code cleanup
- `modules/routes_news_scraper.py` — credentials removed, SSRF/HTML/CSV injection fixes, atomic writes
- `modules/routes_overtime.py` — SSRF, impersonation, GPS wipe, operator precedence, filename sanitize
- `tests/test_overtime_shared.py` — update driver cols test
- `OXALPHA_COMMUNICATION.md` — API reference untuk komunikasi dengan Ox Alpha

**Verifikasi:**
- 20/20 pytest overtime_shared tests lulus
- Container `bbm_web` rebuilt & restarted — HTTP 200
- Manual verification semua fix

**Commits:**
- `ab8cc90` fix: security & bug fixes via Ox Alpha AI review — overtime_shared + news_scraper
- `1963283` fix(overtime): security & bug fixes via Ox Alpha AI review — routes_overtime.py

---

### [2.28.6] - 2026-08-25

**Overtime GPS Upsert Parity + Driver Rate Limit + Schema Config**

**Fix:**
- **GPS columns hilang saat sheet refresh** — `ON DUPLICATE KEY UPDATE` di `_upsert_driver_rows()` dan `_upsert_ob_rows()` sebelumnya tidak menyertakan 8 kolom GPS (`gps_lat/lon/address/kelurahan/kecamatan/kota/provinsi/kode_pos`). Saat GA HR menekan Refresh, GPS data yang sudah ada di DB tertimpa dengan string kosong. Kini GPS preserved saat upsert
- **Driver submit tanpa rate limit** — endpoint `POST /api/overtime/driver/submit` sebelumnya tidak punya rate limit (berbeda dengan OB/Security yang punya 10/10menit per IP). Driver bisa spam submit tanpa batas. Kini rate limit seragam
- **Config `overtime_ob_sheet_url` tidak ada di startup** — `overtime_schema.py` hanya insert config untuk Driver sheet URL. OB/Security sheet URL belum ada di `system_config` saat fresh deploy. Kini INSERT IGNORE untuk kedua config key

**Backend:**
- `modules/routes_overtime.py` — GPS columns di ON DUPLICATE KEY UPDATE ×2 tabel + rate limit di driver submit
- `modules/overtime_schema.py` — INSERT IGNORE `overtime_ob_sheet_url` saat startup

**Verifikasi:**
- 55/55 pytest overtime tests lulus
- 82/82 vitest lulus
- Container `bbm_web` rebuilt & restarted

---

### [2.28.5] - 2026-08-25

**Security Hardening: SECRET_KEY + SQL Injection + DB Cleanup**

**Fix Kritis (Security):**
- **Hardcoded SECRET_KEY** — `app.py` sebelumnya fallback ke hardcoded key insecure saat env `SECRET_KEY` tidak diset. Kini raise `RuntimeError` di production jika `SECRET_KEY` env tidak ada — mencegah session hijacking & CSRF token prediktable
- **SQL Injection di `_get_sheet_url()`** — f-string SQL langsung interpolate input user → diganti ke parameterized query (`%s`) untuk mencegah SQL injection via Google Sheet URL
- **Dead code di `routes_cash.py`** — return statement kedua unreachable dihapus (code cleanup)
- **Missing DB connection check di `submit_trip()`** — crash bila `conn=None` karena koneksi gagal; kini return 500 dengan pesan error jelas
- **Connection leak di `submit_trip()`** — sekarang pakai `try/finally` + `conn=None` pattern untuk menjamin koneksi selalu ditutup

**Backend:**
- `app.py` — `SECRET_KEY` env check dengan `RuntimeError` di production
- `modules/helpers.py` — `_get_sheet_url()` → parameterized query
- `modules/routes_cash.py` — hapus dead code unreachable return
- `modules/routes_driver.py` — `submit_trip()` + null check & connection cleanup

---

### [2.28.4] - 2026-08-25

**OT OB/Security Full Parity: Foto Viewer + Filter Sumber + GPS Detail**

**Fitur Baru:**
- **Viewer Foto Bukti OT** — tombol 📷 di tab Driver & tab OB/Security membuka modal berisi foto mulai + foto selesai (klik untuk full-size). Mendukung foto lokal `/uploads/overtime/…` maupun URL eksternal dari sheet. Sebelumnya foto tersimpan tapi tidak ada UI untuk melihatnya
- **Filter Sumber di tab OB/Security** — dropdown Semua Sumber / Google Sheet / Aplikasi / Migrasi (paritas dengan tab Driver); endpoint list & report OB kini menerima param `source`
- **GPS Detail di Form Publik OB/Security** — form publik otomatis deteksi lokasi saat dibuka (reverse geocode Nominatim: alamat lengkap, kelurahan, kecamatan, kota, provinsi, kode pos) + tombol 🔄 Deteksi Ulang; data GPS ikut tersimpan ke DB dan muncul di Detail Report

**Fix Kritis (Fresh Deploy):**
- **Kolom GPS tidak pernah ada di kode migrasi** — kolom `gps_*` untuk `overtime_driver` & `trip_masters` (v2.27.1) hanya ditambah manual ke DB produksi. Fresh deploy baru akan GAGAL saat submit OT/Trip dengan GPS. Sekarang migrasi idempoten menambahkan 8 kolom GPS ke `overtime_driver`, `overtime_ob_security`, DAN `trip_masters` saat startup + kolom yang sama di `init.sql`
- **Service backup DB tidak pernah jalan** — image `mariadb:10.11` (Debian) tidak punya `crond`/`/etc/crontabs`, jadi container `bbm_backup` crash-loop sejak v2.21 dan backup otomatis tidak pernah tereksekusi. Entry point diganti loop scheduler tanpa dependensi (baca jam dari `BACKUP_CRON`); terverifikasi dump manual sukses untuk 10 DB (master + 9 cabang)

**Backend:**
- `POST /api/overtime` (form publik OB) — terima & simpan `gps_lat/lon/address/kelurahan/kecamatan/kota/provinsi/kode_pos`
- `GET /api/overtime/ob-security` — filter `source` (`sheet`/`form`/`migrasi`)
- `GET /api/overtime/report?modul=ob` — filter `source` mendukung nilai `migrasi`
- `modules/overtime_schema.py` — guarded ALTER GPS ×3 tabel (`overtime_driver`, `overtime_ob_security`, `trip_masters`) + kolom di CREATE TABLE — **idempoten & fresh-deploy safe**

---

### [2.28.3] - 2026-08-25

**Test Suite Fix: PDF Text Parser + Mock IDB + Refactor Duplikasi**

**Fix:**
- **Parser ekstraksi teks PDF di test** — `_pdf_text` salah menangani escape string PDF (spesifikasi §7.3.4.2): `\r`, `\n`, `\t`, `\b`, `\f` dan oktal `\ddd` dibaca sebagai huruf biasa, sehingga kode glyph 2-byte bergeser dan karakter hilang saat assert konten (`TANDA` → `TANA`, `REKAP DANA` → `REKAP ANA`). PDF yang dihasilkan aplikasi sendiri **selalu benar** — ini murni bug utilitas test (11 test gagal di host)
- **Mock idb tidak lengkap di DriverView.test.js** — hanya menyediakan `countAllQueues`; `TripTab.vue` juga memakai `saveTripDraft`/`loadTripDraft`/`deleteTripDraft` → 3 error unhandled Vitest saat switch tab Trip
- **Dead code** — hapus `return None` ganda di `helpers.resolve_driver_scope()`

**Refactor:**
- **`tests/pdf_text.py`** — sumber tunggal ekstraktor teks PDF untuk semua test (sebelumnya disalin duplikat di `test_water.py`, `test_pdf_compact.py`, `test_branches.py` — perbaikan harus diulang 3×)
- Semua file test (water, overtime, applicants, assets, pdf_compact, branches) kini import dari modul bersama

**Hasil Verifikasi:**
- Backend: **236/236 pytest lulus** di host (5 test security-headers memang didesain jalan di container: `docker exec bbm_web python3 -m pytest tests/test_security_headers.py`)
- Frontend: **82/82 Vitest lulus, 0 error unhandled**
- Net kode: −143 baris (9 file berubah)

---

### [2.28.2] - 2026-08-24

**OT OB/Security Feature Parity + Foto Auto-Cleanup 6 Bulan + Cron di Container**

**Fitur Baru:**
- **OB/Security Refresh dari Google Sheet** — tombol 🔄 Refresh sekarang ada di tab OB/Security, bisa pull data dari Google Sheet langsung dari dashboard GA HR
- **Detail Report untuk OB/Security** — modal 📋 Detail/Excel di tab OB sekarang mengirim `modul=ob`, label otomatis menyesuaikan ("Nama OB/Security"), file di-download dengan suffix `_OB`
- **Kolom Posisi di Detail Report** — PDF & Excel Detail Report menampilkan kolom POSISI (bukan PLAT KENDARAAN) untuk modul OB/Security
- **Config Sumber Data Dual-Panel** — modal ⚙️ Sumber Data sekarang menampilkan URL untuk Driver DAN OB/Security secara terpisah dengan tombol simpan masing-masing
- **Foto OT Auto-Cleanup 6 Bulan** — foto overtime yang lebih lama dari 180 hari (6 bulan) otomatis dihapus dari server untuk menghemat storage
- **Cron di Container Docker** — cleanup foto OT dijalankan otomatis tiap 30 menit via cron di dalam container `bbm_web`, bekerja langsung saat fresh deploy
- **Manual Cleanup Endpoint** — `POST /api/overtime/cleanup-photos` (admin only) untuk trigger cleanup manual
- **Background Thread Cleanup** — selain cron, Flask app juga punya background thread yang cleanup tiap 30 menit sebagai backup

**Backend:**
- `POST /api/overtime/cleanup-photos` — admin-only endpoint untuk trigger foto cleanup manual
- `_cleanup_old_photos(max_age_days=180)` — fungsi reusable yang scan `uploads/overtime/` dan hapus file lama
- `_periodic_photo_cleanup()` — background thread daemon di `app.py` yang cleanup tiap 30 menit
- `scripts/overtime-cleanup.sh` — shell script untuk cron di container
- Dockerfile: install `cron`, setup cron job, CMD jalankan cron + Flask

**Frontend (OvertimeView.vue):**
- OB tab: tambah tombol 🔄 Refresh, 📋 Detail/Excel
- Detail Report modal: param `modul` sesuai tab aktif (driver/ob)
- Config modal: dual-panel (Driver + OB/Security), masing-masing dengan input URL & tombol simpan terpisah

---

### [2.28.1] - 2026-08-24

**OT Form Multi-Modul + H+1 + Nama Filter + Landscape Detail**

**Perubahan:**
- **Form Permohonan untuk Driver & OB/Security** — endpoint `/api/overtime/form-pdf` sekarang mendukung parameter `modul` (driver/ob), PDF otomatis menyesuaikan isi (No. Kendaraan vs Posisi, Broker/Manager hanya untuk driver)
- **H+1 Overtime** — bila OT lewat tengah malam, form PDF menampilkan durasi H+1 yang dihitung dari jam 00:00 s/d waktu_selesai (maksimal terhitung dari jam terakhir selesai OT)
- **Detail Report Landscape** — orientasi halaman diubah ke Landscape A4 (267mm usable), kolom lebih lebar & profesional: No, Timestamp, No. Form, Nama, Plat, Tanggal OT, Jam Mulai, Jam Selesai, Keterangan, Lokasi (GPS), Biaya
- **Kolom Lokasi** — tambah kolom LOKASI di detail report (PDF & Excel) yang menampilkan data GPS detail (kelurahan/kecamatan/kota) atau alamat lengkap
- **Filter nama autocomplete** — input nama di Detail Report modal dan tab OB/Security sekarang bisa dicari dan dipilih dari daftar nama yang tersedia (API `/api/overtime/names`)
- **Tombol Cetak Form di tab OB/Security** — tombol 📄 Cetak Form Permohonan ditambahkan di tabel OB/Security (sebelumnya hanya ada di tab Driver)
- **Excel Landscape** — export Excel juga pakai orientasi landscape dengan kolom yang sama

**Backend:**
- `GET /api/overtime/form-pdf?modul=ob&id=xxx` — support modul ob/security
- `GET /api/overtime/names?modul=driver` — return nama unik dari tabel driver
- `GET /api/overtime/names?modul=ob` — return nama unik dari tabel ob/security
- `GET /api/overtime/names` — return nama unik dari kedua tabel

---

### [2.28.0] - 2026-08-24

**Multi-Branch Database Terpisah — 10 Database untuk 10 Cabang**

**Fitur Baru:**
- **10 database terpisah** — setiap cabang punya DB sendiri (38 tabel per DB)
- **Auto-create DB** — `ensure_branch_database()` saat startup otomatis buat DB cabang
- **Master data sync** — users, branches, config, drivers, vehicles dicopy ke semua DB cabang
- **Mirror server ready** — backup/restore per cabang, tidak ganggu cabang lain

**Database Architecture:**
- Master: `bpf_asset_system` (SBY + shared data)
- JKT: `bpf_branch_jkt` (Equity Tower)
- JKT2: `bpf_branch_jkt2` (Pacific Place)
- BDG: `bpf_branch_bdg`
- SMG: `bpf_branch_smg`
- MLG: `bpf_branch_malang`
- MDN: `bpf_branch_mdn`
- BJM: `bpf_branch_bjm`
- PLM: `bpf_branch_plm`
- LPG: `bpf_branch_lpg`

**Keuntungan:**
- Isolasi data penuh per cabang (ISO 27001)
- Query lebih cepat (data lebih sedikit per DB)
- Disaster recovery per cabang
- User cabang A tidak bisa akses data cabang B

---

### [2.27.1] - 2026-08-24

**GPS Detail + Watermark + Bug Fixes + Infrastructure**

**Fix:**
- **GPS kecamatan kosong** — tambah municipality, district, subdistrict sebagai fallback + parse display_name untuk Jakarta
- **GPS detailedLocation ReferenceError** — variable `addr` belum didefinisikan sebelum dipakai
- **GPS detail box tidak muncul** — tambah GPS box di TripTab + OvertimeDriverTab
- **CSP blokir Nominatim** — tambah `https://nominatim.openstreetmap.org` ke `connect-src`
- **Service Worker redirect error** — hapus `/app/` dari SHELL + tambah `redirect: 'follow'`
- **Photo upload 1 tombol** — tambah 2 tombol: 📷 Kamera + 🖼️ Galeri
- **GPS harus klik manual** — auto `store.locate()` saat DriverView mount
- **Watermark font terlalu besar** — proporsional (width/45) + tambah baris koordinat

**Fitur Baru:**
- **GPS detail disimpan ke DB** — 3 tabel (transactions, trip_masters, overtime_driver) punya kolom kelurahan/kecamatan/kota/provinsi/kode_pos
- **Backend terima GPS detail** — routes_driver.py, routes_overtime.py, routes_cash.py
- **Watermark 4 baris** — perusahaan + tanggal + alamat + koordinat GPS
- **Nginx cache-busting** — assets (1 tahun immutable), SPA routes (no-cache), static (30 hari)

**Database Migration:**
- `transactions` — tambah 5 kolom GPS detail
- `trip_masters` — tambah 8 kolom GPS detail
- `overtime_driver` — tambah 8 kolom GPS detail

---

### [2.27.0] - 2026-08-24

**Overtime Form PDF + GPS Detail + Auto-Save + User Management + Login UI**

**Fitur Baru:**
- **Formulir Permohonan Overtime PDF** — dokumen cetak untuk GA HR: ID form, detail OT, blok TTD (Manager/Finance/GA HR/Chief Driver/Kepala Cabang), foto sebagai link
- **Laporan Overtime PDF (File 1)** — tabel ringkas semua driver, ditandatangani GA HR
- **Report Detail Per Driver (File 2)** — per driver: timestamp, form no, plat, jam in/out, keterangan, kolom Biaya kosong (GA HR isi manual di Excel)
- **Excel Export** — download detail OT ke XLSX dengan kolom Biaya kosong
- **Detail Lokasi GPS** — reverse geocode lengkap: jalan, kelurahan, kecamatan, kota, provinsi, kode pos + SPBU terdekat
- **Auto-Save Trip Draft** — data tab Trip tersimpan otomatis ke IndexedDB, pulih saat buka lagi
- **User Management + Branch** — semua user assign ke cabang, tabel tampilkan nama cabang
- **Login Page UI Upgrade** — gradient button, icon prefix, clean design tanpa role badge list
- **Password toggle** 👁/🙈 di site card & edit form (News Scraper)
- **Configurable daily limit** — setting dari UI (1-100 artikel/hari)
- **Tab Report** — detail per-artikel + filter + export CSV (News Scraper)

**Perubahan:**
- Rename user `it_ef` → `it_sby`, URL `/app/it-ef` → `/app/it`
- Branch names: "Kantor Pusat Surabaya" → "Cabang Surabaya", "Jakarta 2" → "Cabang Pacific Place"
- Daily limit default: 5 → 10 (configurable)
- TripTab mobile: 3 kolom → 2 kolom di bawah 480px
- GPS box: tampilkan detail lokasi lengkap (bukan hanya koordinat)
- Site card: tampilkan password (hidden) + toggle show/hide

**Perbaikan Bug:**
- Password tidak tampil di site card (backend tidak return app_password)
- Edit form selalu reset password ke kosong
- showCardPassword tidak reaktif (pakai reactive() bukan ref({}))
- WP URL salah pattern (bestprofit → best-profit)
- branches API return object bukan array → .find() error
- TripTab mobile tidak responsive (3 kolom sempit)
- Access control loophole — site tanpa branch_code terlihat semua user

**API Endpoints Baru:**
- `GET /api/overtime/report` — laporan OT ringkas (PDF)
- `GET /api/overtime/detail-report` — report detail per driver (PDF/Excel)
- `GET /api/overtime/form-pdf?id=xxx` — Formulir Permohonan OT (PDF)
- `GET /api/scraper/report` — upload report per-article
- `GET /api/scraper/report/export` — export CSV
- `GET /api/scraper/settings` — ambil settings
- `POST /api/scraper/settings` — simpan settings

---

### [2.26.0] - 2026-08-24

**Detik Finance + Report + Settings + Multiple Fixes**

**Fitur Baru:**
- **Detik Finance scraping** — 48 artikel/komoditas dari finance.detik.com
- **Detik Tag scraping** — /tag/emas, /tag/komoditas (27-33 artikel)
- **Source selector** — Semua Sumber / Newsmaker.id / Detik Finance
- **Source backlink** — setiap artikel punya backlink ke sumber asli
- **Tab Report** — tabel detail per-artikel (judul, status, SEO, site, source)
- **Filter report** — tanggal, site, status, source, search
- **Export CSV** — download laporan lengkap
- **Settings panel** — daily limit configurable dari UI (1-100)
- **Password toggle** — 👁/🙈 di site card & form edit
- **User-friendly errors** — DNS/SSL/Timeout → pesan jelas

**Perubahan:**
- Daily limit: 5 → 10 (configurable)
- Upload history sekarang simpan per-article detail (status, SEO, source, link)
- Badge header: "🔴 Limit" → "⏸️ Jeda — X/10 hari ini"
- Stat card: format "X/10" (dinamis)

**Perbaikan Bug:**
- Password tidak tampil di site card (backend tidak return app_password)
- Edit form selalu reset password ke kosong (app_password: '')
- showCardPassword tidak reaktif (pakai reactive() bukan ref({}))
- WP URL salah pattern (bestprofit → best-profit)
- Badge limit hardcoded '/10' → dinamis '/daily_limit'

**URL Pattern (diperbaiki):**
- Semua cabang: `best-profit-futures-<city>.com`
- JKT HO: `best-profit-futures-equitytower.com`
- JKT2: `best-profit-futures-pacificplace.com`

**API Endpoints Baru:**
- `GET /api/scraper/report` — upload report dengan filter
- `GET /api/scraper/report/export` — export CSV
- `GET /api/scraper/settings` — ambil settings
- `POST /api/scraper/settings` — simpan settings

---

### [2.25.1] - 2026-08-24

**Rename it_ef → it_sby + URL Update + Role per Cabang**

**Breaking Changes:**
- **Login**: `it_ef` → `it_sby` (PIN tetap `123456`)
- **URL**: `/app/it-ef` → `/app/it`
- **Role Enum**: ditambah 9 role baru (it_hu, it_jkt2, it_bdg, it_smg, it_mlg, it_mdn, it_bjm, it_plm, it_lpg)

**Perubahan:**
- Rename user `it_ef` → `it_sby` di database
- Change URL `/app/it-ef` → `/app/it` (routing + sidebar + auth store)
- Add role per cabang: `it_sby`, `it_hu`, `it_jkt2`, `it_bdg`, `it_smg`, `it_mlg`, `it_mdn`, `it_bjm`, `it_plm`, `it_lpg`
- Update WordPress site URLs:
  - JKT HO: `bestprofit-futures-equitytower.com`
  - JKT2: `bestprofit-futures-pacificplace.com`
  - Others: `bestprofit-futures-{kota}.com`
- Update ROLE_HOME mapping untuk semua IT roles
- Update frontend: router, auth store, sidebar, UsersView
- Update backend: helpers.py, routes_api_master.py, routes_news_scraper.py

---

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
| v2.28.0 | 243 | 82 | 16 | 341 |
| v2.28.3 | 236 | 82 | — | 318 |
| v2.28.5 | 236 | 82 | — | 318 |

---

*BPF WorkHub v2.28.5 · Changelog*
