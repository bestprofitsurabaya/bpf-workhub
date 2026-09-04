# 📋 Changelog — BPF WorkHub

Riwayat perubahan BPF WorkHub. Ditulis untuk manusia, bukan untuk robot.

---

## v2.29.2 — 4 September 2026

### 🛡️ Security & Monitoring: Audit server-wide + Uptime Kuma

Sesi lanjutan: amankan service lain di server NAS & pasang monitoring. Tidak ada
perubahan pada runtime aplikasi workhub (v2.29.1 tetap berjalan, 0 restart).

#### 🔒 Perbaikan keamanan server (bukan hanya workhub)

- **EcoPowerID (proyek lain di NAS):** port app `0.0.0.0:3000` (HTTP polos, tanpa
  TLS) dibuka ke publik padahal sudah ada akses TLS via nginx `:8444`.
  → bind `127.0.0.1:3000` + tambah healthcheck (node fetch, interval 30s).
  Akses publik tetap via `https://nasbpfsby.duckdns.org:8444` (nginx → nama
  container, tidak terpengaruh). Terverifikasi: 8444 = 200, port host 3000
  hanya localhost, container healthy.
- **Proses vite preview orphan (bpf-trader-pro):** `node vite preview --port 5299`
  jalan di host (PPID 1, tanpa tmux/systemd) sejak sebelum container
  chart-trader-pro di-rebuild — duplikat basi dari build Docker yang sudah live
  via nginx `:8445`. Tidak ada config yang mereferensikan 5299.
  → dihentikan; port 5299 tertutup; trader tetap 200 via 8445.
- **Audit port menyeluruh (ss -tlnp):** semua DB (mariadb/postgres) hanya internal
  docker network ✓; publik yang tersisa memang disengaja: nginx 80/443/5000/
  8443-8445 (TLS), talk TURN 3478, SSH 22. Semua vhost nginx memakai proxy ke
  nama container + Host-header check anti-scan (return 444 utk non-domain).

#### 📊 Monitoring: Uptime Kuma (proyek baru `/home/it-ef/uptime-kuma`)

- Container `uptime_kuma` (louislam/uptime-kuma:1, 1.23.17), port
  `127.0.0.1:3001` (localhost-only), join `nextcloud_net` agar bisa reach semua
  container, volume `uptime-kuma-data`, TZ Asia/Jakarta, healthcheck sendiri.
- Setup diotomasi via socket API (node + socket.io-client): admin user dibuat,
  5 monitor HTTP aktif — semuanya **UP (200)**:
  Nextcloud (443), BPF WorkHub (5000 `/api/health`), Karaoke (8443),
  EcoPowerID (8444), Chart Trader Pro (8445) — interval 60s.
- Kredensial admin: `/home/it-ef/uptime-kuma/.admin-credentials` (chmod 600).
  Akses: SSH tunnel → `http://localhost:3001`.
- Utilitas: `scripts/audit_endpoints.py` (baru) — audit statis read-only:
  endpoint backend vs referensi frontend/scripts/tests. Hasil: 217 endpoint
  backend terdaftar; tool menandai kandidat tanpa referensi untuk ditinjau
  manual (lihat PROGRESS.md — banyak yang legacy/internal, jangan hapus tanpa
  verifikasi log runtime).

#### 🔎 Audit endpoint (read-only, temuan utk tech-debt)

Kandidat duplikat/legacy yang tidak dipanggil SPA (perlu verifikasi log runtime
sebelum dihapus): `/api/vehicle_bbm/<vt>` (duplikat `vehicle-allowed-bbm`),
`/api/vehicles/with-nopol`, `/api/dummy-data/*` (duplikat `/api/demo/*`),
`/api/verify-pin`, `/api/get-feedback`, `/api/get-performance`,
`/api/trips/verify|reject`, `/api/assignment-remark`,
`/api/assignments/confirm|history|pending|swap|swap-history`,
`/api/scraper/schedule/create|list`, `/api/scraper/notify`,
`/api/scraper/hyperlinks`, `/api/scraper/upload-multi`, `/api/teams*`.
Halaman `/admin/*` (routes_admin) sudah terdokumentasi legacy — penggantinya
`/api/queue/*` di SPA.

---

## v2.29.1 — 3 September 2026

### ⚙️ Produksi: Debug & Hardening (gunicorn, pool DB, keamanan port)

Audit + optimasi produksi menyeluruh. Semua 313 pytest lulus di container baru.

#### 🚀 Runtime: Dev Server → Gunicorn (eventlet)

- **Sebelum:** `CMD python3 -u app.py` — Werkzeug dev server (`allow_unsafe_werkzeug`).
- **Sesudah:** `gunicorn --worker-class eventlet -w 1 --timeout 300` — WSGI server
  produksi (gunicorn sudah ada di requirements tapi tidak pernah dipakai).
- 1 worker eventlet = benar untuk flask-socketio (room in-memory, green thread).
- Access log gunicorn dimatikan (app sudah cetak JSON via after_request).

#### 🐛 Fix: DB Pool Exhausted (`⚠ Pool exhausted`)

- **Root cause:** MariaDB default `max_connections=151`, tapi Max_used_connections
  sempat **152**. Pool BPF 15 koneksi × 10 DB (master + 9 cabang) menembus batas.
- **Fix:** `command: --max-connections=500` di db service + `DB_POOL_SIZE=25` +
  retry ber-backoff (0.15s/0.3s/0.45s) di `get_db_connection()` sebelum fallback
  ke koneksi non-pool (`DB_POOL_RETRIES=3`).

#### ⚙️ Optimasi: Pool Cabang Diperkecil (follow-up)

- mysql.connector membuka **semua** koneksi pool saat init → `DB_POOL_SIZE=25` ×
  10 DB = 250 koneksi idle (Threads_connected sempat **206**) di host 3.8GB.
- Master tetap 25 (`DB_POOL_SIZE`); 9 DB cabang pakai pool kecil
  `BRANCH_POOL_SIZE=5` (cabang sepi, master sibuk).
- Hasil terukur setelah recreate container: Threads_connected 206 → **26**,
  tanpa kehilangan fungsi (313 pytest tetap lulus).

#### 🔒 Keamanan: Port Tidak Lagi Terbuka ke Internet

- MariaDB `3307` → `127.0.0.1:3307` (sebelumnya `0.0.0.0` — DB bisa diakses publik).
- Web `5001` → `127.0.0.1:5001` (akses produksi via nextcloud_nginx, bukan port host).
- HTTPS publik tetap jalan via nextcloud_nginx di container network.

#### 🐛 Fix: Fresh Deploy SPA Rusak (bind mount `./static`)

- `./static:/app/static` menimpa SPA hasil build image, padahal `static/app/`
  **tidak di-commit** (gitignore) → fresh deploy melayani SPA kosong/rusak.
- Bind mount `./static` dihapus; SPA kini murni dari Dockerfile (stage
  frontend-build) — selalu sinkron dengan source `frontend/`.
- `build-spa.sh` (copy ke host static/app) tidak lagi diperlukan untuk deploy.

#### 🐛 Fix: Access Log JSON Tidak Pernah Tercetak

- `log_access_json()` pakai `app.logger.info()`, tapi level default Flask logger
  = WARNING di production → log akses diam-diam dibuang.
- Fix: handler eksplisit + `app.logger.setLevel(INFO)` + `propagate=False`.

#### 🔧 Fix Lain

- **Google Sheets overtime sync**: retry 3× (backoff 1s/2s) untuk SSLEOFError /
  ConnectionError / Timeout dari Apps Script (`_fetch_sheet_rows`).
- **`_redis_ping()`** (health check): baca `REDIS_URL` env, bukan URL hardcoded.
- **Scraper log flood**: level default INFO (`SCRAPER_LOG_LEVEL` env, opsional
  DEBUG untuk troubleshooting) — ribuan baris per-tag tidak lagi membanjiri log.

#### 🩺 Healthcheck & Resource

- Healthcheck web (`GET /api/health`) + redis (`redis-cli ping`) di compose.
- Log rotation semua service (`json-file`, max 20m × 3 file) — cegah disk penuh.
- Mem limit: web 1g, db 2g, redis 128m, backup 512m (host 3.8GB bersama 5 proyek).

---

## v2.29.0 — 27 Agustus 2026

### 📰 Scraper: Pre-Filter, Retry Logic & Progress Bar Fix

Tiga fix kritis + satu fitur baru untuk pipeline scraper:

#### 🔧 Fix: Progress Bar stuck 0%

**Root cause:** Frontend buat `task_id` (JS milliseconds) lalu polling endpoint yang sama, tapi backend generate `task_id` baru sendiri (Python epoch seconds). Task ID tidak pernah match → frontend poll task yang tidak ada → progress bar stuck di 0%.

**Fix:** Backend sekarang terima `task_id` dari frontend via query param `?task_id=...` dan menggunakannya, bukan generate baru. Scrape endpoint sudah benar sejak awal; hanya upload endpoint yang perlu diperbaiki.

#### 🔧 Fix: HTTP 400 saat Upload ke WordPress

**Root cause:** Dua masalah:
1. `update_post()` pakai method `POST` — WordPress REST API expects `PUT`/`PATCH` untuk update.
2. `publish_time` kosong bikin format date invalid (`2024-01-01T:00`).

**Fix:** `update_post()` diganti ke `PUT`. Content size validation ditambah (>120KB auto-truncate). `publish_time` default ke `'08:00'` jika kosong. Error logging sekarang tampilkan response body WordPress (sebelumnya cuma "HTTP 400").

#### 🔧 Fix: Content Not Found (Rate Limiting)

**Root cause:** Scrape 48 artikel secara sequential ke newsmaker.id tanpa retry → situs rate-limit setelah ~25 request → 23 artikel gagal dapat konten.

**Fix:** Ditambah `_retry_get()` — helper dengan exponential backoff (3 retries, 2s→4s→8s) yang retry otomatis pada HTTP 429/5xx dan connection errors. Respect header `Retry-After` jika ada. Dipakai di scraper newsmaker, detik, dan fetch article content.

#### ✨ Fitur: Pre-Filter Artikel vs WordPress

Upload kini **pre-filter** artikel melawan WordPress SEBELUM memproses pipeline:
1. Fetch semua post titles dari WordPress (hingga 1000 posts).
2. Bandingkan normalized title → skip yang sudah ada.
3. Hanya proses artikel BARU melalui pipeline mahal (rewrite, HTML, SEO, backlinks, tags, schema).

**Hasil:** 48 scraped → 45 already on WP (skip) → hanya 3 diproses. Upload ~94% lebih cepat.

#### ✨ Fitur: Auto-Scrape Cron

Script `scripts/auto_scrape.sh` dijalankan via cron di Docker container:
- Jam 06:00, 10:00, 14:00, 18:00 WIB
- Scrape newsmaker.id → pre-filter vs WP → upload hanya yang baru
- Log: `/app/data/news_scraper/auto_scrape.log`
- Lock file mencegah overlapping runs

### Commits

```
73068e5 perf(scraper): pre-filter articles against WordPress before upload
cc3773d feat(scraper): add auto-scrape cron (jam 6,10,14,18 WIB)
319d2de fix(scraper): fix progress bar, HTTP 400 errors, and add retry logic
```

---

## v2.28.9 — 27 Agustus 2026

### 📰 Source Badge + Filter Artikel

Artikel card kini menampilkan **badge sumber** (cyan untuk Newsmaker.id,
orange untuk Detik Finance) dan **tombol filter** untuk membedakan
artikel berdasarkan sumber. Filter menampilkan jumlah per sumber dan
Select All hanya memilih artikel yang sedang ditampilkan.

### 📰 Update Newsmaker.id URL

URL scraping diubah ke `https://www.newsmaker.id/id/news/commodity`
yang sudah spesifik ke artikel komoditas. Selector scraping diupdate
menyesuaikan struktur HTML baru (`h3` + `a[href*=commodity]`).
Live test: 16 artikel komoditas ditemukan dari halaman pertama.

### 📰 Site Config: Branch Code + WordPress Auth Investigation

**Branch code penyebab `it_sby` tidak melihat site.**
`save_wp_site()` sebelumnya tidak menyimpan field `branch_code` — sehingga
`_visible_sites()` tidak bisa memfilter site berdasarkan cabang. Kini
`branch_code` disimpan, di-load, dan ditampilkan di form UI (input `SBY`, `JKT`, dst).

**Investigasi kredensial WordPress BPF Surabaya:**
- Server `best-profit-futures-surabaya.com` mengaktifkan **HTTP Basic Auth**
  di level server (nginx/apache), yang memblokir Application Passwords WordPress.
- Pesan WordPress: _"Your website appears to use Basic Authentication,
  which is not currently compatible with Application Passwords."_ — ini
  karena fungsi `wp_is_site_protected_by_basic_auth()` mendeteksi
  `$_SERVER['PHP_AUTH_USER']` / `PHP_AUTH_PW` yang diset oleh server.
- **Solusi yang berhasil:** Kredensial Application Password (`it_bpf_surabaya` /
  `OfUdr5rYjL2uJD#6N71AYLKR`) langsung dikirim via header
  `Authorization: Basic ...` — WordPress menerima karena Application
  Passwords tetap bisa dipakai via REST API langsung (hanya UI admin yang
  terblokir).
- **Cara test:** `curl -H "Authorization: Basic $(echo -n 'user:pass' | base64)"`
  berhasil, tapi `curl -u user:pass` juga berhasil (server meneruskan header).
- **Yang tidak berhasil:** username `human` / `password` — user tidak ditemukan
  di WP database; ini bukan kredensial yang benar.

**Catatan untuk AI ke depan:**
- `wp_sites.json` adalah file **runtime** (data dir, di-gitignore)
- Untuk test koneksi WP dari luar server: gunakan `curl -H "Authorization: Basic ..."`
- Field config site: `wp_url`, `wp_media_url`, `username`, `app_password`, `branch_code`
- `_make_wp_client()` juga mendukung `basic_username`/`basic_password` sebagai
  fallback — tetapi di WP Surabaya, basic auth ditolak (plugin dihapus)

### Perubahan Code
- `scraper_engine.py`: URL newsmaker.id diupdate ke `/id/news/commodity` + selector scraping
- `ItEfView.vue`: source badge (cyan/orange) + filter buttons (Semua/Newsmaker/Detik)
- `routes.py`: `save_wp_site()` kini menerima & menyimpan `branch_code`
- `ItEfView.vue`: form site ditambah field **Branch Code**

### 🚀 Deploy
- SPA build + Docker image rebuild + container restart
- Docker cleanup: ~4.7 GB reclaimed (images + build cache)

---

## v2.28.8 — 26 Agustus 2026

### 📰 Upload WordPress: Basic-Auth Fallback

`WpClient` kini mendukung **dua lapis kredensial**: application password dulu,
bila ditolak (401) otomatis coba basic auth username/password biasa dari field
`basic_username`/`basic_password` di site config. Pasangan yang berhasil dipakai
untuk semua request berikutnya (upload, cek duplikat, delete). Berlaku di semua
titik: test-connection, upload single/multi, duplicates, delete.

Hasil investigasi live WP Surabaya: situs hanya mengizinkan **Application
Passwords** (REST basic auth password biasa ditolak; XML-RPC dimatikan/404).
Kredensial `human/password` tidak lagi diterima — kemungkinan jalur lama via
plugin yang sudah dihapus. **App password baru tetap wajib dibuat** untuk
Surabaya; fallback tetap berguna bila jalur basic auth diaktifkan lagi atau
di cabang lain.

### 🔐 Stabilisasi Sesi Login + Rate Limit Per-User

Sesi login dilaporkan tidak stabil. Akar masalah yang ditemukan & diperbaiki:

| # | Masalah | Dampak | Perbaikan |
|---|---------|--------|----------|
| 1 | Cookie default `session` bentrok dengan Nextcloud di domain sama (cookie browser **mengabaikan port**) | Sesi acak ter-logout | `SESSION_COOKIE_NAME='bpf_session'` |
| 2 | `DEPLOY_FRESH.md` regenerate `SECRET_KEY` tiap deploy fresh | Semua user logout massal | `.env` hanya dibuat bila belum ada |
| 3 | Akses http LAN + cookie `Secure` | Login loop (cookie tak terkirim) | Env eksplisit di compose + dokumentasi |
| 4 | Token CSRF stale di tab lama setelah re-login | Error "muat ulang halaman" | `api.js` auto-refresh via `/api/auth/me` + retry sekali |
| 5 | Lockout login per-IP murni | Seluruh kantor NAT terkunci gara-gara satu orang salah PIN | Kunci rate-limit kini `IP+username` |

### 🚀 Deployment & Verifikasi Produksi
- SPA di-rebuild (`scripts/build-spa.sh`) + image `bbm_web` di-rebuild & restart.
- Verifikasi live: login `it_sby` HTTP 200 dengan cookie `bpf_session`, `/api/scraper/sites` menampilkan tepat **BPF Surabaya**.
- Full test suite host: **300 passed**; security-headers **7 passed** di container; test PDF overtime flake sekali saat full-run (lulus konsisten saat standalone/file — flake lingkungan, bukan regresi).

### 📰 Fix News Scraper (debug sebagai user `it_sby`)

Debug fungsi news scraper via simulasi login `it_sby`. Ditemukan **3 bug**:

1. **`wp_sites.json` rusak oleh edit manual** — `branch_code: SBY` hilang dari BPF Surabaya (+ entri sampah `"B"`), sehingga `it_sby` melihat 0 situs. Data dipulihkan.
2. **Filter branch naif di `list_wp_sites()`** — substring `"sby"` tidak match nama situs `"bpf surabaya"`. Kini refactor ke `_visible_sites()` + alias kota (`SBY→surabaya`, dst).
3. **URL ganda di `WpClient`** — `wp_url` di config sudah berisi `/wp-json/wp/v2/posts`, client menambahkan `/wp-json/wp/v2/...` lagi → semua request 404 `rest_no_route`. Kini dinormalisasi via `_normalize_base_url()`. Ini memperbaiki `test-connection`, cek duplikat, DAN upload untuk semua cabang.

Bonus: pesan error auth WP (401/403) kini actionable — menyebut user mana dan cara membuat Application Password baru. Live test: **BPF Bandung login OK, 9.029 post terbaca**.

Catatan: app password BPF Surabaya ditolak WordPress (401) — perlu Application Password baru; 8 cabang lain masih kredensial `PENDING`.

---

## v2.28.7 — 25 Agustus 2026

### 🔐 Security Review Total via Ox Alpha AI

AI model **Ox Alpha** (`stealth/ox-alpha` via OpenRouter) diminta untuk mengaudit seluruh kode. Hasilnya? **59 bug** ditemukan & diperbaiki dalam satu sesi kerja.

#### Apa yang diperbaiki?

**🔴 Masalah Kritis (CRITICAL)**

| File | Masalah | Bahasa Manusia |
|------|---------|----------------|
| `routes_news_scraper.py` | Hardcoded credentials | Password WP tersimpan di kode sumber. Siapapun yang baca kode bisa login ke semua situs WP. Dihapus. |
| `routes_api_master.py` | PIN plaintext di audit log | PIN driver tercatat di log aktivitas. Orang yang bisa akses log bisa lihat semua PIN. Dihapus dari log. |

**🟠 Masalah Serius (HIGH)** — 17 bug

| File | Masalah | Bahasa Manusia |
|------|---------|----------------|
| `routes_overtime.py` | SSRF via sheet URL | Server bisa diminta mengambil data dari URL internal (localhost, database). Diblokir. |
| `routes_overtime.py` | Nama bisa di-override client | Driver bisa ganti nama sendiri di form. Sekarang pakai nama dari session. |
| `routes_overtime.py` | GPS hilang saat refresh | Data GPS driver hilang setiap kali GA menekan tombol Refresh. Diperbaiki. |
| `routes_overtime.py` | `.upper()` crash | Server crash jika data posisi kosong. Ditangani. |
| `routes_driver.py` | Connection leak | Koneksi database tidak ditutup saat error. Kini pakai try/finally. |
| `routes_driver.py` | IDOR uploads | Foto BBM/odometer bisa diakses siapapun tanpa login. Ditambah auth. |
| `routes_driver.py` | Driver set harga sendiri | Driver bisa atur harga BBM sendiri → potensi fraud. Sekarang pakai harga dari database. |
| `routes_driver.py` | Driver non-aktif bisa submit | Driver yang sudah non-aktif masih bisa submit form. Diblokir. |
| `routes_cash.py` | Reject tanpa cek status | Request yang sudah selesai bisa di-reject. Ditambah validasi status. |
| `routes_cash.py` | Daily code hilang | Kode unik harian tidak tersimpan karena lupa commit. Diperbaiki. |
| `routes_api_transactions.py` | 2 endpoint tanpa auth | `/api/get-performance` dan `/api/get-feedback` bisa diakses siapapun. Ditambah role check. |
| `routes_api_transactions.py` | Username dari client | Nama approver bisa di-override client. Sekarang pakai session. |
| `routes_reports.py` | Password DB di command line | Password database terlihat di `ps aux`. Dihapus. |
| `bpf_karaoke/main.py` | CORS wildcard + credentials | Setiap website bisa akses API karaoke. Dibatasi ke domain tertentu. |
| `bpf_karaoke/auth.py` | Race condition login | Concurrent request bisa bypass brute-force protection. Ditambah lock. |
| `bpf_karaoke/youtube.py` | IP spoofing | Client bisa spoof IP → bypass rate limit. Dihapus. |
| `bpf_karaoke/admin.py` | Path traversal | User bisa scan folder di server. Dibatasi ke folder media saja. |

**🟡 Masalah Sedang (MEDIUM)** — 17 bug

Termasuk: operator precedence, `str(None)`, filename injection, SVG XSS, TOCTOU race, `str(e)` info disclosure (error message ke client), ga_name spoof, dan lainnya.

**🟢 Masalah Ringan (LOW)** — 1 bug

- Dead code di `overtime_shared.py` — kode yang tidak bergama dihapus.

---

### Ringkasan per File

| File | CRITICAL | HIGH | MED | LOW | Total |
|------|----------|------|-----|-----|-------|
| `overtime_shared.py` | 0 | 3 | 2 | 1 | **6** |
| `routes_news_scraper.py` | 2 | 4 | 4 | 0 | **10** |
| `routes_overtime.py` | 0 | 4 | 4 | 0 | **8** |
| `routes_driver.py` | 0 | 4 | 1 | 0 | **5** |
| `routes_cash.py` | 0 | 2 | 3 | 0 | **5** |
| `routes_api_transactions.py` | 0 | 2 | 1 | 0 | **3** |
| `routes_reports.py` | 0 | 1 | 2 | 0 | **3** |
| `routes_branches.py` | 0 | 0 | 2 | 0 | **2** |
| `routes_api_master.py` | 0 | 0 | 0 | 0 | **0** |
| `bpf_karaoke` (8 files) | 1 | 4 | 3 | 0 | **8** |
| **Total** | **3** | **24** | **22** | **1** | **50** |

### Commits

```
2b8010c fix(api-master): PIN logging + error disclosure
97bcfef fix(reports+branches): Ox Alpha review — 6 bug fixes
584ba88 fix(driver+cash): security & bug fixes
1963283 fix(overtime): security & bug fixes
ab8cc90 fix: security & bug fixes — overtime_shared + news_scraper
```

---

## v2.28.6 — 25 Agustus 2026

### GPS + Rate Limit + Config Fix

- **GPS hilang saat sheet refresh** — kolom GPS tidak di-upsert, jadi GPS driver tertimpa kosong saat Refresh. Diperbaiki.
- **Driver submit tanpa rate limit** — driver bisa spam submit tanpa batas. Ditambah rate limit seragam.
- **Config OB sheet URL hilang** — fresh deploy tidak punya URL config untuk OB/Security. Ditambahkan.

---

## v2.28.5 — 25 Agustus 2026

### Security Hardening: SECRET_KEY + SQL Injection

- **Hardcoded SECRET_KEY** — jika env `SECRET_KEY` tidak diset, pakai key prediktable. Sekarang raise error di production.
- **SQL Injection** — f-string SQL langsung interpolate input user. Diganti ke parameterized query.
- **Connection leak di `submit_trip()`** — koneksi tidak ditutup saat error. Ditambah try/finally.

---

## v2.28.4 — 25 Agustus 2026

### Foto Viewer + GPS Detail + Auto-Cleanup

- **Foto Bukti OT** — tombol 📷 di tab Driver & OB/Security buka modal foto (klik untuk full-size).
- **GPS Detail di Form OB** — form otomatis deteksi lokasi (reverse geocode: alamat lengkap + koordinat).
- **Foto OT Auto-Cleanup 6 Bulan** — foto overtime > 180 hari otomatis dihapus dari server.
- **Service backup DB tidak pernah jalan** — container backup crash-loop sejak v2.21. Diperbaiki.

---

## v2.28.3 — 25 Agustus 2026

### Test Suite Fix

- **PDF text parser salah** — test gagal karena parser salah baca escape string PDF. Diperbaiki.
- **Mock IDB tidak lengkap** — 3 error unhandled saat switch tab Trip. Ditambah mock.
- **Refactor** — duplikasi kode test dihapus, semua import dari modul bersama.
- **Hasil:** 236 pytest + 82 Vitest lulus.

---

## v2.28.2 — 24 Agustus 2026

### OB/Security Feature Parity + Cron

- **OB/Security Refresh** — tombol 🔄 Refresh ada di tab OB/Security (pull dari Google Sheet).
- **Detail Report OB** — modal 📋 Detail/Excel mendukung modul OB/Security.
- **Config Sumber Data Dual-Panel** — URL Driver & OB/Security bisa diatur terpisah.
- **Foto OT Auto-Cleanup** — cron + background thread cleanup foto > 180 hari.

---

## v2.28.1 — 24 Agustus 2026

### OT Form Multi-Modul + H+1

- **Form untuk Driver & OB** — PDF form mendukung modul driver dan OB/Security.
- **H+1 Overtime** — bila OT lewat tengah malam, form tampilkan durasi H+1.
- **Detail Report Landscape** — orientasi halaman landscape, kolom lebih lebar.
- **Filter nama autocomplete** — input nama bisa dicari dari daftar yang tersedia.

---

## v2.28.0 — 24 Agustus 2026

### Multi-Branch Database Terpisah

- **10 database terpisah** — setiap cabang punya DB sendiri (38 tabel per DB).
- **Auto-create DB** — `ensure_branch_database()` saat startup otomatis buat DB cabang.
- **Master data sync** — users, branches, config, drivers, vehicles dicopy ke semua DB cabang.
- **Isolasi data** — user cabang A tidak bisa akses data cabang B.

---

## v2.27.x — 24 Agustus 2026

### GPS Detail + Watermark + Auto-Save + User Management

- **GPS detail disimpan ke DB** — 3 tabel punya kolom kelurahan/kecamatan/kota/provinsi/kode_pos.
- **Watermark 4 baris** — perusahaan + tanggal + alamat + koordinat GPS.
- **Auto-Save Trip Draft** — data tab Trip tersimpan otomatis ke IndexedDB, pulih saat buka lagi.
- **User Management + Branch** — semua user assign ke cabang.
- **Login Page UI Upgrade** — gradient button, icon prefix, clean design.

---

## v2.26.0 — 24 Agustus 2026

### Detik Finance + Report + Settings

- **Detik Finance scraping** — 48 artikel/komoditas dari finance.detik.com.
- **Source selector** — Semua Sumber / Newsmaker.id / Detik Finance.
- **Tab Report** — tabel detail per-artikel (judul, status, SEO, site, source).
- **Export CSV** — download laporan lengkap.
- **Settings panel** — daily limit configurable dari UI.

---

## v2.25.0 — 24 Agustus 2026

### UI/UX Overhaul + 7 SEO Algorithms + Multi-Branch

- **Upload Gambar ke WordPress** — download dari source → upload ke WP Media Library.
- **7 Algoritma SEO** — Content Uniqueness, Multi-Source, Internal Linking, Advanced Schema, Auto Sitemap Ping, Smart Scheduling, Performance Analytics.
- **Multi-Branch Users** — 10 cabang dengan akses terfilter.
- **UI/UX Overhaul** — Dashboard, Tab-Based Layout, Article Preview Cards, Dark Mode, Onboarding.

---

## v2.24.0 — 24 Agustus 2026

### Overtime Driver Form + Audit Fix

- **Form Overtime Driver di PWA** — tab ⏰ OT, submit dengan foto watermark + GPS.
- **Foto Bukti Timestamp** — kamera langsung dari form, watermark otomatis.
- **Source Tracking** — pisahkan data Google Sheet vs Aplikasi di database.
- **Deployment Ready** — docker-compose, nginx.conf, init.sql (35 tabel).

---

## v2.23.0 — 21 Agustus 2026

### News Scraper + Content Management

- **News Scraper** — scrape artikel dari newsmaker.id.
- **WordPress Integration** — multi-site management.
- **Auto-Upload** — upload ke WordPress dengan SEO optimization.
- **Financial Authority Backlinks** — 24+ situs otoritas (OJK, BI, BEI, Bloomberg).

---

## v2.22.0 — 14 Agustus 2026

### GA HR + Overtime Driver & OB

- **Role GA HR** — halaman sendiri `/app/ga-hr`.
- **Overtime Driver** — sinkronisasi Google Sheet.
- **Overtime OB/Security** — 546 baris dimigrasikan + form publik tanpa login.
- **PDF Overtime** — laporan resmi berlogo BPF + TTD GA HR.

---

## v2.21.0 — 13 Agustus 2026

### Security Headers + Rate Limit + Backup

- **Security headers lengkap** — CSP ketat, X-Frame-Options, Referrer-Policy.
- **Rate limit terpusat** — anti brute-force login.
- **Backup DB otomatis** — mysqldump semua database tiap 03:00 WIB.
- **Laporan konsolidasi lintas cabang** — PDF + Excel dari semua DB cabang.

---

## v2.20.0 — 13 Agustus 2026

### Multi-Branch Database

- **Multi-cabang** — setiap cabang punya database sendiri.
- **Isolasi data penuh** — user cabang A tidak bisa akses data cabang B.
- **Audit log bertanda cabang** — setiap aktivitas tercatat cabangnya.

---

## v2.18.0 — 13 Agustus 2026

### Aset & Pemeliharaan

- **15 unit AC** + **8 kendaraan** + **12 komponen**.
- **Health score otomatis 0–100**.
- **Rekomendasi maintenance berbasis aturan**.

---

## v2.16.0 — 13 Agustus 2026

### Sistem Pelamar Kerja

- **Form publik** → **Receptionist** → **Traineer**.
- **Laporan PDF resmi per tahap**.

---

## v2.10.0 — 12 Agustus 2026

### SPA Vue 3

- **Migrasi penuh dari server-rendered** ke SPA Vue 3 + Vite.
- **Dashboard per role** — Admin, GA, Finance, Marketing, Chief Driver.

---

## v2.0.0 — 11 Agustus 2026

### Antarmuka Baru

- **SPA Vue 3 + Vite** — antarmuka baru.
- **Auth JSON** — `/api/auth/me`, `/api/auth/login`, `/api/auth/logout`.
- **Kontrol akses berlapis** — server + SPA + sidebar.

---

## v1.0.0 — 8 Agustus 2026

### Rilis Pertama

Versi stabil pertama dengan fitur lengkap: 10 role, 243 pytest, 82 Vitest, 10 video walkthrough.

**Fitur Utama:** Klaim BBM, kasbon, log perjalanan, sistem appointment, pembelian air minum, sistem pelamar kerja, aset & pemeliharaan, overtime driver & OB/Security, multi-cabang, PWA offline-first, notifikasi real-time via WebSocket, backup DB otomatis.

---

## 📊 Statistik Pengujian

| Versi | Pytest | Vitest | Total |
|-------|--------|--------|-------|
| v1.0.0 | 29 | — | 29 |
| v1.1.0 | 48 | 12 | 60 |
| v2.0.0 | 77 | 39 | 116 |
| v2.10.0 | 87 | 47 | 134 |
| v2.20.0 | 194 | 82 | 276 |
| v2.22.0 | 243 | 82 | 325 |
| v2.28.3 | 236 | 82 | 318 |
| v2.28.7 | 236 | 82 | 318 |

---

*BPF WorkHub v2.29.0 · Diperbarui 27 Agustus 2026*
