# 📘 Panduan Lengkap BPF WorkHub
### Versi 2.29.6 · PT. Bestprofit Futures — Surabaya

> Dokumen ini adalah panduan untuk memasang, mengatur, dan merawat aplikasi **BPF WorkHub**.
> Ditulis dengan bahasa sederhana agar bisa dipahami siapa saja — bukan hanya teknisi.
> Untuk panduan pemasangan di server baru dari nol, lihat [DEPLOY_FRESH.md](DEPLOY_FRESH.md).
>
> 💡 **BPF WorkHub dalam satu kalimat:** aplikasi internal untuk mengelola penugasan kendaraan,
> pengajuan kasbon BBM driver, foto lembur (overtime Driver & OB/Security), pembelian air minum,
> hingga notifikasi langsung (*real-time*) ke ponsel driver.

---

## 🧭 Daftar Isi

1. [Istilah Penting — Baca Ini Dulu](#1-istilah-penting--baca-ini-dulu)
2. [Cara Kerja Sistem (Arsitektur & Port)](#2-cara-kerja-sistem-arsitektur--port)
3. [Yang Harus Disiapkan Sebelum Instalasi](#3-yang-harus-disiapkan-sebelum-instalasi)
4. [Pemasangan Pertama Kali](#4-pemasangan-pertama-kali)
5. [Pengaturan Aplikasi (Variabel Lingkungan)](#5-pengaturan-aplikasi-variabel-lingkungan)
6. [Memperbarui ke Versi Terbaru](#6-memperbarui-ke-versi-terbaru)
7. [Cadangkan & Pulihkan Data (Backup & Restore)](#7-cadangkan--pulihkan-data-backup--restore)
8. [Mengawasi Kondisi Aplikasi (Monitoring & Log)](#8-mengawasi-kondisi-aplikasi-monitoring--log)
9. [Akses Lewat Internet dengan Keamanan (HTTPS)](#9-akses-lewat-internet-dengan-keamanan-https)
10. [Kalau Ada Masalah? (Troubleshooting)](#10-kalau-ada-masalah-troubleshooting)
11. [Daftar Alamat Halaman & Layanan (Endpoint)](#11-daftar-alamat-halaman--layanan-endpoint)
12. [Akses Alternatif via Cloudflare Tunnel](#12-akses-alternatif-via-cloudflare-tunnel)
13. [Antarmuka Admin Vue 3 — Build & Deploy](#13-antarmuka-admin-vue-3--build--deploy)
14. [Checklist Akhir Sebelum Go-Live](#14-checklist-akhir-sebelum-go-live)

---

## 1. Istilah Penting — Baca Ini Dulu

Sebelum masuk ke panduan teknis, mari samakan pemahaman dulu. Beberapa istilah di dokumen ini mungkin asing bagi Anda:

| Istilah | Artinya dalam Bahasa Sederhana |
|---------|--------------------------------|
| **Docker** | "Kotak ajaib" yang mengemas aplikasi beserta segala kebutuhannya, supaya bisa berjalan sama persis di komputer mana pun. |
| **Container** | Satu kotak Docker yang berisi satu bagian aplikasi (misalnya: aplikasi web, database). |
| **Database** | Tempat penyimpanan data terstruktur — seperti lemari arsip digital yang rapi. |
| **Volume** | "Laci penyimpanan permanen." Meski aplikasi dimatikan atau di-update, isi laci ini tetap aman. |
| **Port** | Nomor "pintu" tempat sebuah program mendengarkan permintaan. Contoh: port 5000. |
| **Reverse Proxy** | "Resepsionis gedung" — penerima tamu di depan yang meneruskan permintaan ke ruangan yang tepat, sekaligus menjaga keamanan. |
| **HTTPS** | Versi aman dari HTTP. Data yang lewat dienkripsi (disandikan) sehingga tidak bisa dibaca pihak lain. |
| **Endpoint** | Alamat spesifik tempat aplikasi menerima permintaan. Contoh: `/login`, `/api/stats`. |
| **Backup** | Salinan data cadangan, disimpan agar bisa dikembalikan jika terjadi masalah. |
| **Log** | Catatan aktivitas harian aplikasi — sangat berguna saat mencari penyebab masalah. |
| **Apps Script** | Jembatan Google (script di `script.google.com`) yang dipakai membaca Google Sheet **private** untuk overtime — outputnya JSON publik yang dibaca server. |

---

## 2. Cara Kerja Sistem (Arsitektur & Port)

Bayangkan BPF WorkHub sebagai sebuah kantor kecil dengan beberapa ruangan:

```
        Internet / VPN (dunia luar)
                 │
                 ▼
   ┌─────────────────────────────────┐
   │   REVERSE PROXY (nginx :5000)   │  ← Resepsionis / pintu utama (HTTPS)
   └─────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
┌──────────────┐      ┌──────────────────┐
│   bbm_web    │◄────►│   bbm_mariadb    │
│  Aplikasi    │ data │    Database      │
│  port 5000   │      │    MariaDB       │
└──────────────┘      └──────────────────┘
      │        ▲
      │        │ (session & realtime)
      ▼        │
┌──────────────┐
│  bbm_redis   │   ← cache & Socket.IO
└──────────────┘
      │
      ├── 🗄️  bbm_db_data   → laci data (tetap ada walau aplikasi restart)
      ├── 📷  uploads/      → laci foto & bukti (juga permanen)
      └── 🗄️  bbm_backups   → hasil backup DB otomatis tiap 03:00 WIB
```

### 👥 Siapa Saja "Penghuninya"?

| Komponen | Nama Kotak | Port di Server | Tugasnya |
|----------|------------|----------------|----------|
| 🌐 Aplikasi Web | `bbm_web` | `5000` (di dalam network) · `5001` host (localhost-only) | Otak aplikasi, dijalankan **gunicorn (eventlet)** sejak v2.29.1. Sekalian menjadwalkan pembersihan foto lembur tiap 30 menit & auto-refresh sheet overtime saat login/logout GA HR/Admin. |
| 🗄️ Database | `bbm_mariadb` | `3306` (di dalam network) · `3307` host (localhost-only) | MariaDB 10.11 — menyimpan semua data: user, transaksi, overtime, riwayat, dst. |
| ⚡ Cache | `bbm_redis` | Hanya internal | "Catatan tempel cepat" — session, rate limit, dan backend real-time Socket.IO. |
| 🗄️ Backup | `bbm_backup` | Hanya internal | Mencadangkan **semua database** tiap **03:00 WIB** ke volume `bbm_backups` (retensi 30 hari). |

> 🔒 **Sejak v2.29.1:** port host `5001` (web) dan `3307` (DB) di-bind ke `127.0.0.1` —
> tidak lagi terbuka ke internet. Akses publik (HTTPS) lewat `nextcloud_nginx` (port 5000).
> Akses dev: SSH tunnel `ssh -L 5001:127.0.0.1:5001 user@server` → `http://localhost:5001`.

> ⚡ **Catatan WebSocket:** notifikasi real-time butuh koneksi *long-lived*. Reverse proxy wajib
> meneruskan header **Upgrade/Connection** (lihat §9) — tanpa itu notifikasi tidak jalan.

> ⏰ **Sinkronisasi Overtime:** data overtime (Driver **dan** OB/Security) ditarik dari Google Sheet
> lewat URL **Apps Script Web App** (`script.google.com/macros/s/…/exec`) yang disimpan di
> `system_config` (`overtime_driver_sheet_url` & `overtime_ob_sheet_url`). Server tidak pernah
> membaca sheet langsung — cukup JSON publik dari Apps Script (lihat USER_GUIDE §11.6).

---

## 3. Yang Harus Disiapkan Sebelum Instalasi

- **Docker Engine 20.10+** dan **Docker Compose v2** (`docker compose`). Cek:
  ```bash
  docker --version && docker compose version
  ```
- **RAM minimal 2 GB** (produksi saat ini: 4 GB, dipakai bersama ~5 proyek lain di NAS).
- **Ruang disk** cukup untuk volume DB + `uploads/` + `bbm_backups`.
- **Zona waktu server:** `Asia/Jakarta`.
- **Git** untuk menarik kode terbaru.
- (Opsional, untuk HTTPS publik) Domain DuckDNS + Let's Encrypt — atau ikuti Skenario Hybrid
  Nextcloud (`nextcloud_nginx` sebagai reverse proxy, seperti produksi).

---

## 4. Pemasangan Pertama Kali

Panduan langkah demi langkah dari server kosong ada di **[DEPLOY_FRESH.md](DEPLOY_FRESH.md)**.
Ringkasannya:

```bash
# 1. Clone repo
git clone https://github.com/bestprofitsurabaya/bpf-workhub.git
cd bpf-workhub

# 2. Pastikan .env berisi SECRET_KEY (lihat §5) — jangan regenerate saat re-deploy!

# 3. Build & jalankan
docker compose up -d --build

# 4. Verifikasi
docker compose ps                          # semua container "Up (healthy)"
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/app/login   # → 200
```

**Database dibuat otomatis** saat pertama jalan (dari `init.sql` + auto-create schema saat
startup). Akun awal (seed):

| Role | Username | PIN |
|------|----------|-----|
| Admin | `admin` | `123456` |
| GA | `ga_officer` | `123456` |
| Finance | `finance_officer` | `123456` |

> ⚠️ **Segera ganti PIN bawaan** setelah login pertama. User per-cabang (`{divisi}_{cabang}`,
> mis. `ga_sby`) dibuat Admin saat onboarding — jangan andalkan PIN `123456` untuk akun itu.

---

## 5. Pengaturan Aplikasi (Variabel Lingkungan)

Didefinisikan di `docker-compose.yml` (bagian `web`) atau file `.env` (gitignored):

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | `db` / `bpf_user` / `bpf_pass` / `bpf_asset_system` | Koneksi MariaDB (master) |
| `DB_POOL_SIZE` | `25` | Ukuran pool koneksi DB **master** (v2.29.1) |
| `BRANCH_POOL_SIZE` | `5` | Ukuran pool untuk 9 DB cabang (v2.29.1 — hemat koneksi idle) |
| `DB_POOL_RETRIES` | `3` | Retry ber-backoff (0.15s/0.3s/0.45s) sebelum koneksi dianggap gagal |
| `REDIS_URL` | `redis://redis:6379/0` | Session, rate limit, real-time. Mati → fallback memori |
| `SECRET_KEY` | wajib di `.env` | **WAJIB ada** — dipakai session & CSRF. Jangan regenerate saat re-deploy (semua user ter-logout) |
| `SESSION_COOKIE_NAME` | `bpf_session` | Nama cookie sesi (unik agar tidak bentrok dgn Nextcloud di domain sama) |
| `SESSION_HOURS` | `12` | Masa berlaku sesi login (jam) |
| `SESSION_COOKIE_SECURE` | `true` | Cookie hanya lewat HTTPS. `false` untuk dev lokal HTTP |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Proteksi CSRF tingkat cookie |
| `TZ` | `Asia/Jakarta` | Zona waktu |
| `SCRAPER_LOG_LEVEL` | `INFO` | Level log scraper (set `DEBUG` hanya saat troubleshooting) |
| `MAX_AGE_DAYS` | `180` | Umur maksimal foto overtime sebelum auto-cleanup |

**Generate `SECRET_KEY` aman (hanya saat pertama kali):**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Konfigurasi runtime di database** (`system_config`), dikelola via UI dashboard GA HR / Admin —
bukan `.env`:
- `overtime_driver_sheet_url` — URL Apps Script Web App sheet Driver
- `overtime_ob_sheet_url` — URL Apps Script Web App sheet OB/Security
- `company_name`, nama TTD Finance/GA untuk dokumen, dsb.

> ⏰ **Penting (v2.29.6):** kedua URL overtime **wajib** URL Apps Script `/exec`, bukan tautan
> `docs.google.com/…/edit`. Tautan sheet mentah hanya menghasilkan HTML yang tidak bisa dibaca
> server. Template script: `scripts/apps_script_overtime_driver_v2.gs` dan
> `scripts/apps_script_overtime_ob_security.gs` (lihat USER_GUIDE §11.6 cara deploy).

---

## 6. Memperbarui ke Versi Terbaru

```bash
cd bpf-workhub

# 1. Backup dulu (lihat §7)
# 2. Tarik kode terbaru
git pull origin main

# 3. Rebuild & restart (SPA Vue ikut ter-build ke dalam image — tidak perlu langkah terpisah)
docker compose build web
docker compose up -d web

# 4. Cek kesehatan
docker compose ps
docker logs bbm_web --tail 50 | grep -iE 'error|traceback' || echo 'bersih'

# 5. Smoke test (pakai CSRF token — lihat DEPLOY_FRESH.md §5)
curl -s -o /dev/null -w 'health: %{http_code}\n' https://<host>:5000/api/health
```

> 💡 **SPA di dalam image:** sejak v2.29.1 SPA Vue di-build di Dockerfile (stage
> `frontend-build`) — **tidak ada** bind-mount `./static` lagi, jadi `build-spa.sh` tidak
> diperlukan untuk deploy. Hasil build selalu sinkron dengan source `frontend/`.

> 💡 **Cache browser/PWA:** saat ada perubahan antarmuka, bump versi cache di
> `frontend/public/sw.js` (`CACHE = 'bpf-spa-…'`) lalu rebuild — pengguna otomatis membuang
> shell lama saat service worker berikutnya.

---

## 7. Cadangkan & Pulihkan Data (Backup & Restore)

### 7.1 Backup Otomatis (direkomendasikan)

Service `bbm_backup` di docker-compose: **mysqldump semua database (master + 9 cabang) tiap
03:00 WIB** ke volume `bbm_backups`, retensi 30 hari.

```bash
# Cek status & file backup
docker exec bbm_backup cat /backups/last-backup.txt
docker exec bbm_backup ls -lh /backups/

# Backup manual
docker exec bbm_backup /bin/sh /usr/local/bin/backup-db.sh
```

### 7.2 Foto Overtime Auto-Cleanup

Foto overtime di `uploads/overtime/` dibatasi **maksimal 6 bulan (180 hari)** — otomatis
dibersihkan tiap 30 menit (cron container + background thread Flask), bisa juga manual:

```bash
docker exec bbm_web cat /var/log/overtime-cleanup.log        # log cleanup
docker exec bbm_web sh /app/scripts/overtime-cleanup.sh      # cleanup manual
# atau via API: POST /api/overtime/cleanup-photos (auth admin)
```

### 7.3 Backup Manual & Restore

```bash
# Backup DB master
docker exec bbm_web sh -c 'mysqldump -h db -u bpf_user -pbpf_pass bpf_asset_system \
  --single-transaction --routines --triggers' > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup uploads (foto & bukti)
tar czf uploads_$(date +%Y%m%d).tar.gz uploads/

# Restore (hentikan web dulu)
docker compose stop web
docker exec -i bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system < backup.sql
docker compose start web
```

---

## 8. Mengawasi Kondisi Aplikasi (Monitoring & Log)

### 8.1 Kesehatan Container

```bash
docker compose ps                                        # status + healthcheck
docker inspect --format='{{.State.Health.Status}}' bbm_web
curl -s https://<host>:5000/api/health | python3 -m json.tool   # DB + Redis + pool
```

### 8.2 Log Aplikasi

```bash
docker logs -f bbm_web            # live tail
docker logs bbm_web --since 1h    # 1 jam terakhir (format JSON per request)
```

Sejak v2.29.1 log akses JSON dicetak via handler eksplisit (`INFO`). Log rotation semua
service: `json-file`, max 20 MB × 3 file.

### 8.3 Contoh Query Monitoring (langsung ke DB)

```bash
docker exec bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system \
  -e "SELECT status, COUNT(*) FROM transactions GROUP BY status;"

# Sinkronisasi overtime (meta refresh terakhir)
docker exec bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system \
  -e "SELECT * FROM system_config WHERE config_key LIKE 'overtime_%_last_refresh';"
```

### 8.4 Uptime Kuma (sejak v2.29.2)

Server NAS memakai **Uptime Kuma** (`/home/it-ef/uptime-kuma`, port `127.0.0.1:3001`) untuk
memantau 5 layanan tiap 60 detik — termasuk BPF WorkHub (`/api/health`). Akses via SSH tunnel:
`ssh -L 3001:127.0.0.1:3001 it-ef@<server>` → `http://localhost:3001`.

### 8.5 CI (GitHub Actions)

Setiap push ke `main` menjalankan dua job di GitHub Actions:
- **Backend:** pytest dengan service `mariadb` + `redis` (env DB/SECRET_KEY) — 323 tes.
- **Frontend:** unit test (83 vitest) + build SPA.

Cek status: `gh run list` / `gh run view <id>` (gh CLI terpasang di `~/.local/bin` server).

---

## 9. Akses Lewat Internet dengan Keamanan (HTTPS)

Produksi diakses via **`https://nasbpfsby.duckdns.org:5000`** — reverse proxy nginx
(`nextcloud_nginx`) dengan sertifikat Let's Encrypt. Potongan konfigurasi penting:

```nginx
server {
    listen 5000 ssl;
    server_name nasbpfsby.duckdns.org;
    # ssl_certificate / ssl_certificate_key → Let's Encrypt

    location / {
        set $upstream_bbm http://bbm_web:5000;
        proxy_pass $upstream_bbm;

        # ★ PENTING untuk WebSocket / Socket.IO
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 86400;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 🛡️ Host-check anti-scan: vhost mengembalikan **444** untuk Host header yang bukan domain
> resmi. Port host `5001`/`3307` sudah localhost-only — tidak perlu dibuka ke publik.

---

## 10. Kalau Ada Masalah? (Troubleshooting)

| Masalah | Kemungkinan Penyebab | Solusi |
|---------|---------------------|--------|
| `bbm_web` restart loop | `db` belum healthy / kredensial salah | Cek `docker compose ps`; tunggu healthcheck |
| Semua halaman 500 | `SECRET_KEY` berubah / session korup | Hapus cookie session, login ulang. Jangan regenerate SECRET_KEY saat re-deploy |
| Notifikasi tidak real-time | Proxy tidak meneruskan header WebSocket | Tambahkan `proxy_set_header Upgrade` (lihat §9) |
| Login selalu gagal | User nonaktif / PIN salah / CSRF stale | Cek `SELECT username,is_active FROM users`; hard-refresh (Ctrl+Shift+R) |
| Halaman tampak lama / error aneh | Service worker cache versi lama | Hard-refresh; pastikan `sw.js` versi cache di-bump saat deploy UI |
| **Refresh overtime melaporkan 0 baris** | URL sheet mentah (HTML) atau bukan `/exec` | Pastikan `overtime_*_sheet_url` = URL Apps Script Web App (bukan tautan `/edit`) |
| **Data overtime dobel saat refresh** | `display_id`/uid tidak stabil (versi lama) | Pakai kode ≥ v2.29.6 (`OTL-SH-` deterministik) lalu Refresh sekali |
| Tanggal overtime jadi tahun 1926/0026 | Sel di Google Sheet sumber memang salah ketik | Perbaiki sel di sheet (kolom Tanggal) lalu Refresh |
| Port 5001/3307 bentrok | Aplikasi lain memakai port | Ubah mapping di `docker-compose.yml` |
| Data "hilang" | Volume terhapus | Jangan hapus `bbm_db_data`; pulihkan dari `bbm_backups` |

---

## 11. Daftar Alamat Halaman & Layanan (Endpoint)

### Halaman SPA (Vue 3)

| Path | Fungsi |
|------|--------|
| `/app/login` | Halaman login |
| `/app/dashboard` | Dashboard Admin |
| `/app/ga` | Dashboard GA |
| `/app/finance` | Dashboard Finance |
| `/app/ga-hr` | Data overtime (Driver & OB/Security) + PDF |
| `/app/water` | Air minum (OB) / verifikasi (Finance) |
| `/app/marketing` · `/app/chief-driver` · `/app/driver` | Marketing / Chief Driver / PWA Driver |
| `/app/receptionist` · `/app/traineer` · `/app/assets` | Pelamar kerja / Traineer / Aset |
| `/app/it` | News Scraper & WordPress |
| `/app/overtime-form` | Form publik overtime OB/Security (tanpa login) |
| `/app/apply` | Form publik pelamar kerja (tanpa login) |

### API Penting

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/auth/me` | Status sesi + role + CSRF token (wajib diambil dulu) |
| POST | `/api/auth/login` | Login JSON `{username, pin}` + header `X-CSRF-Token` |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/health` | Healthcheck (DB + Redis + pool) |
| GET | `/api/stats` | Statistik dashboard |
| GET | `/api/overtime/list?module=driver\|ob` | Daftar overtime (terkini di atas) |
| POST | `/api/overtime/refresh?module=…` | Refresh dari Google Sheet (manual, tombol GA HR) |
| GET | `/api/overtime/detail-report?…` | Laporan detail per nama (PDF/Excel, terkini di atas) |
| GET | `/api/overtime/form/<id>` | Formulir Permohonan PDF per baris |
| GET | `/api/water/purchases` · `POST /api/water/purchases` | Pengajuan air minum OB |
| POST | `/api/water/purchases/<id>/verify` | Verifikasi Finance (→ PDF Tanda Terima) |
| POST | `/api/users/sync` · `/api/users/reset-pin` | Manajemen user (admin) |

> Daftar endpoint lengkap & audit kandidat tak terpakai: `scripts/audit_endpoints.py`
> (read-only). Banyak endpoint legacy/internal sah — jangan hapus tanpa cek log runtime.

---

## 12. Akses Alternatif via Cloudflare Tunnel

> ⚠️ **Nonaktif** — produksi memakai DuckDNS + nginx (`https://nasbpfsby.duckdns.org:5000`).
> Bagian ini hanya referensi bila suatu saat port publik perlu dihindari.

Quick tunnel uji coba: `cloudflared tunnel --url http://bbm_web:5000` (jalankan di network
yang sama). Untuk URL permanen: buat tunnel di dashboard Cloudflare → Zero Trust → Tunnels,
lalu arahkan Public Hostname ke `http://bbm_web:5000`.

---

## 13. Antarmuka Admin Vue 3 — Build & Deploy

Antarmuka back-office adalah **SPA Vue 3 + Vite** di `frontend/`. Sejak v2.29.1, SPA di-build
**di dalam Dockerfile** (multi-stage: `node:20-alpine` → build → hasil disalin ke image Flask),
jadi:

```bash
# Deploy biasa sudah cukup — SPA ikut ter-build:
docker compose build web && docker compose up -d web
```

Build lokal (untuk development):

```bash
cd frontend
npm install
npm run dev        # dev server :5173, proxy /api → localhost:5001
npm run build      # hasil di frontend/dist
npm test           # 83 unit test (Vitest)
```

---

## 14. Checklist Akhir Sebelum Go-Live

- [ ] `SECRET_KEY` ada di `.env` lokal (gitignored) — dan **tidak** diubah saat re-deploy
- [ ] PIN bawaan semua akun sudah diganti
- [ ] Reverse proxy meneruskan header WebSocket (Upgrade/Connection)
- [ ] Port host `5001` & `3307` hanya bind `127.0.0.1` (v2.29.1+)
- [ ] URL overtime di `system_config` memakai Apps Script `/exec` (Driver & OB/Security)
- [ ] Backup otomatis terkonfigurasi (DB + uploads)
- [ ] HTTPS aktif (PWA wajib secure origin)
- [ ] Smoke test: `/api/health` 200, `/app/login` 200
- [ ] Test suite backend: `docker exec bbm_web python3 -m pytest tests/ -q` → 323 PASS
- [ ] Test suite frontend: `cd frontend && npm test` → 83 PASS

---

## 📞 Kontak

**PT. Bestprofit Futures — Surabaya**  
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271  
Telp: 031-5349888

---

*BPF WorkHub v2.29.6 · Panduan Deployment · Diperbarui 4 September 2026*
