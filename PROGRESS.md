# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-09-04  
**Branch:** `main`  
**Versi terbaru:** v2.29.3 (Fix login production + fix PDF air minum; redeploy 4 Sep)

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.29.3 (Fix login "not a function" + PDF water receipt orphan heading) |
| Deploy | ✅ 4 Sep 2026 — rebuild image + restart `bbm_web` (fix login, CSRF, bundle baru) |
| Pool DB | ✅ Master 25 + cabang 5 (Threads_connected 206 → 26) — lihat CHANGELOG v2.29.1 |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| App Running | `https://nasbpfsby.duckdns.org:5000` (health 200) |
| Databases | 10 DB terpisah (1 master + 9 cabang) |
| GPS Detail | ✅ Nominatim reverse geocode + disimpan ke DB |
| Watermark | ✅ 4 baris: perusahaan + tanggal + alamat + koordinat |
| Test Suite | ✅ 313 pytest + vitest auth store (7) |
| Kestabilan | ✅ bbm_web healthy — 0 restart, 0 error di log sejak deploy terakhir |

---

## 🗂️ Riwayat Sesi

### Sesi 2026-09-04 — Fix login production + PDF air minum (v2.29.3) ✅ SELESAI

> Konteks: lanjutan sesi v2.29.2. Workhub di-restart & di-rebuild pertama kali
> setelah v2.29.1 untuk men-deploy fix login & perbaikan PDF.

#### 🔑 Yang dikerjakan

1. **Fix login "k.login is not a function"** — regresi sejak 27 Agu: aksi
   `login` tidak sengaja terhapus dari auth store (commit `0450822`) padahal
   `LoginView` tetap memanggilnya. Source sudah difix di `e8c9281` (login +
   CSRF); 4 Sep image di-rebuild (`docker compose build web`) + restart
   (`up -d web`). Verifikasi: container healthy, `/api/health` 200, bundle baru
   berisi `/api/auth/login` + `bpf_csrf`.
2. **Verifikasi login live via HTTPS** (`nasbpfsby.duckdns.org:5000`): alur
   `/api/auth/me` → login admin/123456 → 200, sesi terkonfirmasi
   (`authenticated: true`). `ga_sby`/`finance_sby` PIN `123456` → 401 (bukan
   default — perlu PIN asli utk verifikasi lanjutan).
3. **Anti-regresi login:** test kontrak store di `frontend/src/stores/auth.test.js`
   (7 vitest lulus) — gagal cepat bila `login`/`bootstrap`/`logout` hilang.
4. **Fix PDF Tanda Terima Air Minum** — judul seksi 'TANDA TANGAN'/'LAMPIRAN
   FOTO' bisa orphan di dasar halaman saat dokumen panjang; cek ruang pindah ke
   sebelum judul + test regresi multi-halaman (`tests/test_water.py`, 16 pytest
   lulus). Lihat CHANGELOG v2.29.3.

#### ⚠️ Catatan

- Browser pengguna yang masih menampilkan error login lama: hard-refresh atau
  bersihkan service worker (`sw.js` cache `index.html` lama).
- Dokumen PDF diperiksa menyeluruh (render + ekstraksi teks + layout 1 & 2
  halaman) — isi & TTD Finance/GA sesuai konfigurasi `system_config`.

---

## 🗂️ Riwayat Sesi

### Sesi 2026-09-04 — Security server-wide + Monitoring (v2.29.2) ✅ SELESAI

---

## 🗂️ Riwayat Sesi

### Sesi 2026-09-04 — Security server-wide + Monitoring (v2.29.2) ✅ SELESAI

> Konteks: lanjutan sesi sebelumnya. Workhub sudah production — sesi ini
> mengerjakan rekomendasi #1 (amankan service lain) & #2 (monitoring) dari
> PROGRESS. Runtime bpf-workhub TIDAK diubah.

#### 🔑 Akses Server (BERUBAH — penting)

- ⚠️ **SSH kini via LAN `192.168.2.31:22`** (port 2211 hanya forward WAN &
  duckdns resolve ke IP LAN dulu → timeout dari jaringan internal).
- Host publik tetap `nasbpfsby.duckdns.org` (port 2211 untuk akses luar).
- Semua perintah sesi ini pakai `ssh -p 22 it-ef@192.168.2.31`.

#### 🛡️ Yang Dikerjakan

1. **Audit port server (read-only, `ss -tlnp` + docker ps)** — hasil: semua DB
   internal ✓; publik yang tersisa memang disengaja (nginx TLS 80/443/5000/
   8443-8445, talk 3478, SSH). Semua vhost nginx proxy ke nama container +
   Host-check anti-scan.
2. **EcoPowerID hardening** — `0.0.0.0:3000` (HTTP polos publik) →
   `127.0.0.1:3000` + healthcheck node-fetch. TLS publik via nginx :8444 tetap
   200. Backup compose: `docker-compose.yml.bak-20260904`.
3. **Kill proses orphan** — `vite preview --port 5299` (bpf-trader-pro, host,
   PPID 1, basi dari sebelum container di-rebuild). Port 5299 tertutup; trader
   via 8445 tetap 200.
4. **Uptime Kuma deployed** — `/home/it-ef/uptime-kuma/` (compose + kredensial
   `.admin-credentials` chmod 600). Localhost:3001, join nextcloud_net.
   Setup otomatis via socket API: admin + **5 monitor UP (200)**: Nextcloud,
   BPF WorkHub `/api/health`, Karaoke, EcoPowerID, Chart Trader Pro.
   Verifikasi: monitorList + DB heartbeat status=1 semua.
5. **Audit endpoint (read-only)** — tool baru `scripts/audit_endpoints.py`:
   217 endpoint terdaftar; daftar kandidat unused → CHANGELOG v2.29.2. Semua
   masih PERLU verifikasi log runtime sebelum dihapus (banyak endpoint internal
   cron/sheet/legacy yang sah). Jangan hapus tanpa data.

#### 📄 File yang Diubah/Ditambah

- Server: `/home/it-ef/EcoPowerID/docker-compose.yml` (bukan repo workhub),
  `/home/it-ef/uptime-kuma/` (baru).
- Repo workhub: `scripts/audit_endpoints.py` (baru), `CHANGELOG.md`,
  `PROGRESS.md` (lokal + perlu sync ke server).

---

### Sesi 2026-09-03 — Debug & Optimasi Production (v2.29.1) ✅ SELESAI

> Konteks: sesi ini melakukan debug + optimasi menyeluruh sampai level production
> atas perintah user. Semua pekerjaan tuntas, terverifikasi, dan ter-deploy.

#### 🔑 Akses Server

| Item | Nilai |
|------|-------|
| Host | `nasbpfsby.duckdns.org` |
| SSH port | `2211` |
| User | `it-ef` |
| Lokasi codebase | `/home/it-ef/bpf-workhub` |
| Compose project | `bpf-bbm-system` (containers: `bbm_web`, `bbm_mariadb`, `bbm_redis`, `bbm_backup`) |
| App URL | `https://nasbpfsby.duckdns.org:5000` (via nextcloud_nginx) |
| Web host port | `127.0.0.1:5001` (localhost-only, akses dev via SSH tunnel) |
| DB host port | `127.0.0.1:3307` (localhost-only) |

#### 🔍 Temuan & Perbaikan

1. **DB pool exhaustion (`Pool exhausted`)** — MariaDB `max_connections=151` tapi
   `Max_used_connections=152`; pool 15×10 DB menembus batas, lalu code fallback
   bikin koneksi non-pool baru (makin parah).
   → `--max-connections=500` + retry ber-backoff (`DB_POOL_RETRIES=3`) di
   `get_db_connection()`, tanpa fallback non-pool.
2. **Dev server di production** — Dockerfile CMD `python3 -u app.py` (Werkzeug,
   `allow_unsafe_werkzeug=True`). Gunicorn ada di requirements tapi tak pernah dipakai.
   → `gunicorn --worker-class eventlet -w 1 --timeout 300` (benar untuk flask-socketio).
3. **Keamanan port** — MariaDB `0.0.0.0:3307` & web `0.0.0.0:5001` terbuka ke internet.
   → keduanya di-bind `127.0.0.1`; HTTPS publik tetap via nextcloud_nginx.
4. **Fresh-deploy SPA rusak** — bind mount `./static` menimpa SPA hasil build image
   (padahal `static/app/` gitignored). → bind mount dihapus; SPA murni dari image.
5. **Access log JSON tak pernah tercetak** — Flask logger default WARNING di production.
   → `app.logger.setLevel(INFO)` + handler eksplisit.
6. **Google Sheets overtime sync error (SSL EOF)** — tanpa retry.
   → retry 3× (backoff 1s/2s) di `_fetch_sheet_rows()`.
7. **`_redis_ping()` hardcoded URL** → baca `REDIS_URL` env.
8. **Scraper DEBUG log flood** → default `INFO` (`SCRAPER_LOG_LEVEL` env).
9. **Pool idle berlebih** — mysql.connector buka SEMUA koneksi saat init:
   `DB_POOL_SIZE=25` × 10 DB = 250 (Threads_connected sempat 206).
   → `BRANCH_POOL_SIZE=5` untuk 9 DB cabang; master tetap 25.
   Hasil terukur: **Threads_connected 206 → 26**.

#### ✅ Verifikasi Akhir (setelah deploy)

- Semua container `Up` + `(healthy)`; `bbm_web` restart count 0.
- Gunicorn master + eventlet worker jalan (cek via `docker top bbm_web`).
- Health `GET /api/health` → 200.
- Login end-to-end: `GET /api/auth/me` (ambil csrf_token) → `POST /api/auth/login`
  (`admin`/`123456` + header `X-CSRF-Token`) → `status: success` (role admin, SBY).
- SPA `/app/login` → 200.
- `docker logs bbm_web --since 5m` → 0 baris error/traceback/pool exhausted.
- Test suite di container rebuilt: **313 passed, 6 skipped**.

#### 📄 File yang Diubah (semua sudah ter-deploy + tersinkron)

`Dockerfile`, `docker-compose.yml`, `app.py`, `modules/config.py`,
`modules/security.py`, `modules/routes_overtime.py`,
`modules/news_scraper/scraper_logger.py`, `CHANGELOG.md`, `PROGRESS.md`,
`README.md`, `DEPLOYMENT.md`, `DEPLOY_FRESH.md`.

---

## 🗄️ Database Architecture

### Arsitektur Multi-Branch DB

```
┌─────────────────────────────────────────────────────┐
│                 MariaDB 10.11                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  bpf_asset_system  ← Master DB (SBY + shared data) │
│    ├── users (33)                                   │
│    ├── branches (10)                                │
│    ├── system_config                                │
│    ├── transactions (135 — BBM SBY)                 │
│    ├── overtime_driver (8,676 — OT SBY)             │
│    ├── trip_masters (Trip SBY)                      │
│    ├── appointments                                 │
│    └── ...38 tables                                 │
│                                                     │
│  bpf_branch_jkt  ← Jakarta HO (Equity Tower)       │
│    └── 38 tables (kosong, siap data baru)           │
│                                                     │
│  bpf_branch_jkt2 ← Jakarta 2 (Pacific Place)       │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_bdg  ← Bandung                         │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_smg  ← Semarang                        │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_malang ← Malang                        │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_mdn  ← Medan                           │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_bjm  ← Banjarmasin                     │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_plm  ← Palembang                       │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_lpg  ← Lampung                         │
│    └── 38 tables                                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Branch → Database Mapping

| Code | Nama Cabang | Database | Kota |
|------|-------------|----------|------|
| SBY | Kantor Pusat Surabaya | `bpf_asset_system` (master) | Surabaya |
| JKT | Kantor Pusat Jakarta | `bpf_branch_jkt` | Jakarta |
| JKT2 | Cabang Pacific Place | `bpf_branch_jkt2` | Jakarta |
| BDG | Cabang Bandung | `bpf_branch_bdg` | Bandung |
| SMG | Cabang Semarang | `bpf_branch_smg` | Semarang |
| MLG | Cabang Malang | `bpf_branch_malang` | Malang |
| MDN | Cabang Medan | `bpf_branch_mdn` | Medan |
| BJM | Cabang Banjarmasin | `bpf_branch_bjm` | Banjarmasin |
| PLM | Cabang Palembang | `bpf_branch_plm` | Palembang |
| LPG | Cabang Lampung | `bpf_branch_lpg` | Lampung |

### Keuntungan Multi-Branch DB

| Aspek | Manfaat |
|-------|---------|
| **Isolasi Data** | Data BBM/OT/Trip satu cabang tidak tercampur cabang lain |
| **Mirror Server** | Backup/restore per cabang — cukup copy 1 DB |
| **Performance** | Query lebih cepat (data lebih sedikit per DB) |
| **Security** | User cabang A tidak bisa akses data cabang B |
| **Compliance** | Sesuai ISO 27001 — isolasi data per unit bisnis |
| **Disaster Recovery** | Restore cabang tertentu tanpa ganggu cabang lain |

### Cara Kerja

```
1. User login → session['branch_code'] = 'BDG'
2. get_db_connection() → resolve_db_name('BDG') → 'bpf_branch_bdg'
3. Semua query operasional → ke bpf_branch_bdg
4. Query users/branches → selalu ke bpf_asset_system (master)
5. Login/logout → garansi session bersih
```

---

## ✅ Yang Sudah Selesai

### Core Features
- [x] Sistem BBM (klaim, verifikasi, pencairan)
- [x] Sistem Kasbon (kode unik, LPJ, alur relay)
- [x] Log Perjalanan / Trip (auto-save ke IndexedDB)
- [x] Dashboard per role (Admin, GA, Finance)
- [x] Dark mode + High contrast mode

### Multi-Branch Database ⭐ v2.28.0
- [x] **10 database terpisah** (1 master + 9 cabang)
- [x] **Schema sync** — semua DB punya 38 tabel identik
- [x] **Master data sync** — users, branches, config, drivers, vehicles disetiap DB
- [x] **Auto-create** — `ensure_branch_database()` saat startup
- [x] **Backward compatible** — SBY tetap di master DB

### Appointment & Rute
- [x] Marketing Hub (input appointment)
- [x] Chief Driver (board penugasan)
- [x] Atur Rute Otomatis (VRPTW heuristic)
- [x] Geocoding (Nominatim/OpenStreetMap)

### Air Minum
- [x] Form pengajuan OB (foto before/after)
- [x] Verifikasi Finance + PDF tanda terima

### Pelamar Kerja
- [x] Form publik + Dashboard Receptionist + Laporan PDF

### Aset & Pemeliharaan
- [x] 15 unit AC + 8 kendaraan + Health score otomatis

### Overtime
- [x] Driver + OB/Security + Form PWA
- [x] 3 format PDF + Excel export
- [x] GPS detail disimpan ke DB
- [x] Form Permohonan untuk Driver & OB/Security (modul param)
- [x] H+1 OT — maksimal terhitung dari jam terakhir selesai OT
- [x] Filter nama autocomplete (searchable + selectable) di laporan
- [x] Detail Report Landscape A4 + kolom Lokasi (GPS detail)
- [x] OB/Security Refresh dari Google Sheet (dashboard GA HR)
- [x] Detail Report modul-aware (driver/ob) — kolom Posisi vs Plat
- [x] Config sumber data dual-panel (Driver + OB/Security)
- [x] Foto OT auto-cleanup > 6 bulan (cron + background thread + manual API)
- [x] Cron di Docker container — langsung bekerja saat fresh deploy
- [x] Viewer foto bukti 📷 di tab Driver & OB/Security (modal, klik utk full-size)
- [x] Filter Sumber (Sheet/Aplikasi/Migrasi) di tab OB/Security — paritas Driver
- [x] GPS detail di form publik OB/Security (auto-detect Nominatim + simpan ke DB)

### PWA Driver
- [x] 5 tab: BBM, Kasbon, Trip, OT, Rapor
- [x] Foto: 📷 Kamera + 🖼️ Galeri
- [x] Auto-save trip draft (IndexedDB)
- [x] GPS detail box + auto-detect
- [x] Watermark 4 baris (proporsional)

### News Scraper (IT — Multi-Cabang)
- [x] Newsmaker + Detik Finance (64 artikel/scrape)
- [x] Multi-WordPress site (10 cabang)
- [x] Tab Report + Settings + Daily Limit configurable
- [x] SEO 7 Algoritma + Backlinks
- [x] **v2.28.8** — fix filter branch (alias kota) + normalisasi URL WpClient; live test Bandung OK

### Security & Infrastructure
- [x] CSP connect-src — Nominatim diizinkan
- [x] Service Worker — fix redirect error
- [x] Nginx cache-busting
- [x] GPS detail disimpan ke DB
- [x] **SECRET_KEY hardening** — RuntimeError jika env tidak ada di production
- [x] **SQL Injection fix** — parameterized query di `_get_sheet_url()`
- [x] **Connection leak fix** — try/finally + null check di `submit_trip()`

### QA / Test Suite (v2.28.3)
- [x] Fix parser `_pdf_text` — escape string PDF (§7.3.4.2): `\r`/`\n`/oktal kini dibaca benar; PDF aplikasi tidak pernah rusak, murni bug utilitas test
- [x] Refactor — ekstraktor teks PDF digabung ke `tests/pdf_text.py` (sebelumnya 3 salinan duplikat antar file test)
- [x] Fix mock idb di DriverView.test.js (saveTripDraft/loadTripDraft/deleteTripDraft) — hilang 3 error unhandled Vitest
- [x] Hapus dead code `return None` ganda di helpers.resolve_driver_scope()
- [x] Verifikasi host: **236/236 pytest + 82/82 Vitest lulus**
- Catatan: 5 test security-headers butuh DB container (`docker exec bbm_web python3 -m pytest tests/test_security_headers.py`); versi paket host bisa menyimpang dari requirements.txt — container tetap pakai versi pin

---

## 🔄 Yang Sedang Dikerjakan

### Roadmap v2.29.0
- [ ] **Approval berjenjang (multi-level)** — OT/BBM/Kasbon perlu approval atasan sebelum diproses GA/Finance
- [ ] **Dashboard mobile khusus admin** — monitoring real-time dari HP (bukan hanya desktop)
- [ ] **Laporan otomatis mingguan via email** — ringkasan OT, BBM, kasbon terkirim otomatis tiap Senin

### Tech Debt
- [ ] **Audit endpoint unused** — 160/161 endpoint terpakai, sisanya perlu dipetakan atau dihapus
- [ ] **Upgrade MariaDB 10.11 → 11.x** — fitur JSON table, better window functions
- [ ] **Migrate Vue 2 → Vue 3 Composition API sepenuhnya** — beberapa komponen masih pakai Options API

---

## 📋 Yang Belum Dikerjakan

### Fitur Baru
- [ ] Laporan otomatis mingguan via email
- [ ] Approval berjenjang (multi-level)
- [ ] Dashboard mobile khusus admin

---

## 🐛 Bug yang Sudah Diperbaiki

### v2.28.9 — News Scraper Improvements + WP Auth + Deploy
- ✅ **Source badge + filter**: setiap artikel card menampilkan badge sumber (cyan=newsmaker, orange=detik) + tombol filter per sumber
- ✅ **Newsmaker URL updated**: `https://www.newsmaker.id/id/news/commodity` — spesifik komoditas, selector scraping diupdate (live test: 16 artikel)
- ✅ `save_wp_site()` tidak menyimpan `branch_code` → `it_sby` tidak bisa melihat site → kini `branch_code` disimpan di backend & form UI
- ✅ Investigasi kredensial WP Surabaya: `human/password` tidak ada di WP DB (user tidak ditemukan)
- ✅ Kredensial benar: `it_bpf_surabaya` / Application Password → terverifikasi via curl (HTTP 200)
- ✅ Server WP Surabaya aktifkan HTTP Basic Auth → memblokir UI Application Passwords, tapi REST API tetap bisa via header `Authorization: Basic ...`
- ✅ Deploy: SPA build + Docker image rebuild + container restart — HTTP 200 verified
- ✅ Docker cleanup: ~4.7 GB reclaimed (3.85 GB images + 893 MB build cache)
- ✅ Test suite: 39 passed, 6 skipped (news_scraper) — tidak ada regressi

### v2.28.8 — News Scraper + Stabilitas Sesi Login
- ✅ `it_sby` melihat 0 situs — `wp_sites.json` rusak edit manual + fallback substring branch gagal; kini alias kota (`SBY→surabaya`)
- ✅ Semua request WP 404 `rest_no_route` — URL ganda `/wp-json/` di WpClient; kini dinormalisasi
- ✅ Pesan error auth WP tidak actionable — kini sebut user + cara buat Application Password baru
- ✅ Cookie `session` bentrok Nextcloud (domain sama, port diabaikan) → `SESSION_COOKIE_NAME='bpf_session'`
- ✅ `SECRET_KEY` regenerate tiap deploy → logout massal; DEPLOY_FRESH kini menjaga `.env` lama
- ✅ CSRF stale token di tab lama → `api.js` auto-refresh + retry sekali
- ✅ Lockout login per-IP murni mengunci seluruh kantor NAT → rate-limit kini per kombinasi IP+username
- ✅ WpClient fallback basic auth (`basic_username`/`basic_password`) saat application password ditolak — aktif di semua endpoint scraper
- ⚠️ App password BPF Surabaya ditolak WP (perlu Application Password baru); 8 cabang kredensial masih `PENDING`. Investigaasi live: WP Surabaya hanya izinkan application passwords (basic auth ditolak, XML-RPC 404) — kredensial `human/password` tidak berlaku lagi
- ℹ️ Full suite host: 300 passed; security-headers 7 passed (di container); test PDF overtime flake sekali saat full-run (lulus konsisten standalone — flake lingkungan)
- 🚀 Deployed v2.28.8 ke bbm_web (build SPA + image rebuild) — login it_sby & scraper sites terverifikasi live

### v2.28.5 — Security Hardening
- ✅ **Hardcoded SECRET_KEY (v2.28.5)** — app.py fallback insecure key; kini raise RuntimeError di production jika SECRET_KEY env tidak ada
- ✅ **SQL Injection di _get_sheet_url() (v2.28.5)** — f-string SQL → parameterized query (`%s`)
- ✅ **Dead code di routes_cash.py (v2.28.5)** — return statement kedua yang unreachable dihapus
- ✅ **Missing DB connection check (v2.28.5)** — submit_trip() crash bila conn=None; kini return 500 dengan pesan
- ✅ **Connection leak di submit_trip() (v2.28.5)** — sekarang pakai try/finally + conn=None pattern

### v2.28.4 — OT Parity & Infrastructure
- ✅ **Kolom GPS tidak ada di kode migrasi** — gps_* overtime_driver & trip_masters sebelumnya hanya manual di DB produksi; fresh deploy gagal saat submit OT/Trip ber-GPS. Kini migrasi idempoten ×3 tabel (overtime_driver, overtime_ob_security, trip_masters) + init.sql
- ✅ **Service backup DB tidak pernah jalan** — mariadb:10.11 tidak punya crond → bbm_backup crash-loop sejak v2.21. Kini loop scheduler tanpa cron; dump 10 DB terverifikasi
- ✅ **record.mjs selector login usang** — LoginView v2.27 tak lagi pakai #login-pin; skenario driver (5 tab) & GA HR diperbarui
- ✅ Presentasi & video demo di-regenerate dari data produksi cabang Surabaya (PPTX 12 slide + PDF + 11 mp4) — tersedia di Nextcloud `BPF /Presentasi_BPF_WorkHub_v2.28.4/`

### v2.27.1 — GPS & Infrastructure
- ✅ GPS kecamatan kosong — municipality/district fallback
- ✅ GPS ReferenceError — variable addr undefined
- ✅ CSP blokir Nominatim
- ✅ Service Worker redirect error
- ✅ Photo upload 1 tombol → 2 tombol
- ✅ Watermark font terlalu besar

---

## 📝 Catatan untuk Sesi Berikutnya

> Mulai dari sini: baca `PROGRESS.md` + `CHANGELOG.md` (bagian v2.29.1), lalu
> lanjutkan ke item di bawah. Semua pekerjaan v2.29.1 sudah live di server.

### 🏗️ State Saat Ini (harus diketahui sebelum ubah apa pun)
- Codebase: `/home/it-ef/bpf-workhub` (SSH port 2211, user `it-ef` — kredensial dari tim).
- Compose project `bpf-bbm-system`; container: `bbm_web` (gunicorn), `bbm_mariadb`
  (max_connections=500), `bbm_redis`, `bbm_backup` (cron 03:00 WIB).
- Port host 5001/3307 **localhost-only** — akses dev via SSH tunnel
  (`ssh -L 5001:127.0.0.1:5001 -p 2211 it-ef@nasbpfsby.duckdns.org`).
- SPA di-serve dari image (build via Dockerfile, stage frontend-build) —
  **jangan** pasang bind mount `./static` lagi.
- Env pool: `DB_POOL_SIZE=25` (master), `BRANCH_POOL_SIZE=5` (cabang),
  `DB_POOL_RETRIES=3`.
- Login API butuh CSRF: `GET /api/auth/me` → token → `POST /api/auth/login`
  dengan header `X-CSRF-Token`. Akun test: `admin`/`123456`.
- Deploy cara cepat: edit → sync ke server → `docker compose up -d --build` →
  verifikasi health + login + `docker logs`. Test: `docker exec bbm_web python3 -m pytest tests/ -q`.

### 🎯 Status Rekomendasi Sebelumnya
- ✅ **#1 Amankan service lain** — selesai sesi 2026-09-04 (EcoPowerID port +
  healthcheck, vite orphan 5299, audit port menyeluruh). Karaoke/snipe-it
  belum punya healthcheck di compose — nilai saat deploy ulang berikutnya.
- ✅ **#2 Monitoring** — Uptime Kuma live (5 monitor UP), akses localhost:3001.
  Belum: notifikasi alert (email/Telegram) & watchtower — konfigurasi via UI.
- ⏳ **#3 Roadmap fitur** — approval berjenjang, dashboard mobile admin,
  laporan mingguan email. Butuh keputusan produk dulu.
- ⏳ **#4 Tech debt** — audit endpoint sudah (tool + temuan CHANGELOG v2.29.2);
  upgrade MariaDB & migrasi Vue masih terbuka (butuh window + keputusan).

### 🎯 Rekomendasi Langkah Berikutnya
1. **Verifikasi endpoint legacy via log runtime** — grep `docker logs bbm_web`
   (JSON access log) 1-2 minggu utk endpoint kandidat unused di CHANGELOG
   v2.29.2; baru hapus yang benar-benar nol pemanggilan.
2. **Notifikasi Uptime Kuma** — login UI (tunnel :3001) → set alert email/
   Telegram utk 5 monitor.
3. **Roadmap fitur** (lihat "Yang Sedang Dikerjakan") — pilih 1, butuh spesifikasi.
4. **Tech debt besar** (butuh window + backup): MariaDB 10.11 → 11.x,
   migrasi Vue Options → Composition API.

### DB Architecture
- Master: `bpf_asset_system` (SBY + shared)
- Cabang: `bpf_branch_{code}` (terpisah)
- Startup: `ensure_branch_database()` auto-create

---

## 🔗 Link Penting

| Link | URL |
|------|-----|
| App | `https://nasbpfsby.duckdns.org:5000` |
| GitHub | `https://github.com/bestprofitsurabaya/bpf-workhub` |

---

## 👥 Akun IT Cabang

| Role | Username | PIN | Branch | DB |
|------|----------|-----|--------|-----|
| IT HO | `it_hu` | `123456` | JKT | bpf_branch_jkt |
| IT Surabaya | `it_sby` | `123456` | SBY | bpf_asset_system |
| IT Bandung | `it_bdg` | `123456` | BDG | bpf_branch_bdg |
| IT Semarang | `it_smg` | `123456` | SMG | bpf_branch_smg |
| IT Malang | `it_mlg` | `123456` | MLG | bpf_branch_malang |
| IT Medan | `it_mdn` | `123456` | MDN | bpf_branch_mdn |
| IT Banjarmasin | `it_bjm` | `123456` | BJM | bpf_branch_bjm |
| IT Palembang | `it_plm` | `123456` | PLM | bpf_branch_plm |
| IT Lampung | `it_lpg` | `123456` | LPG | bpf_branch_lpg |
| IT Jakarta 2 | `it_jkt2` | `123456` | JKT2 | bpf_branch_jkt2 |

---

*BPF WorkHub v2.29.2 · Progres Tracker · Last updated: 2026-09-04*
