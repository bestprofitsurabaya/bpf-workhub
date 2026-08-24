# 🚀 Panduan Deployment — BPF WorkHub v2.28.2

Dokumen ini menjelaskan cara menginstal, mengkonfigurasi, dan menjaga aplikasi BPF WorkHub tetap berjalan.

**PT. Bestprofit Futures — Surabaya**

---

## Daftar Isi

1. [Arsitektur & Port](#1-arsitektur--port)
2. [Prasyarat](#2-prasyarat)
3. [Instalasi Pertama](#3-instalasi-pertama)
4. [Variabel Lingkungan](#4-variabel-lingkungan)
5. [Update ke Versi Baru](#5-update-ke-versi-baru)
6. [Backup & Restore + Foto Cleanup](#6-backup--restore--foto-cleanup)
7. [Monitoring & Log](#7-monitoring--log)
8. [Reverse Proxy & HTTPS](#8-reverse-proxy--https)
9. [Troubleshooting](#9-troubleshooting)
10. [Daftar Endpoint](#10-daftar-endpoint)
11. [Cloudflare Tunnel](#11-cloudflare-tunnel)
12. [SPA Vue 3 — Build & Deploy](#12-spa-vue-3--build--deploy)
13. [Checklist Sebelum Go-Live](#13-checklist-sebelum-go-live)

---

## 1. Arsitektur & Port

```
Internet / VPN
      │
      ▼
  Reverse Proxy (nginx / duckdns:5000)     ← HTTPS public
      │
      ▼
┌──────────────┐        ┌──────────────────┐
│  bbm_web     │◄──────►│  bbm_mariadb     │
│  Flask :5000 │  DB    │  MariaDB :3306   │
│  :5001 (dev) │        │  :3307 (host)    │
└──────────────┘        └──────────────────┘
   │  ┌───────────────┐
   └──│  bbm_db_data  │  ← volume persist DB
      │  uploads/     │  ← volume foto & bukti
      └───────────────┘
```

| Container | Nama | Port Host | Port Kontainer | Fungsi |
|-----------|------|-----------|----------------|--------|
| Web (Flask + SocketIO) | `bbm_web` | `5001` (dev) / `5000` (prod) | `5000` | Aplikasi + Cron (foto cleanup tiap 30 menit) |
| Database | `bbm_mariadb` | `3307` | `3306` | MariaDB 10.11 |
| Cache | `bbm_redis` | internal | `6379` | Rate limit + cache |
| Backup | `bbm_backup` | cron 03:00 | — | Backup DB otomatis |

> **Catatan SocketIO:** WebSocket membutuhkan koneksi *long-lived*. Jika memakai reverse proxy, wajib aktifkan header **Upgrade/Connection**. Tanpa itu, notifikasi real-time driver tidak akan jalan.

---

## 2. Prasyarat

- Docker Engine 20.10+ dan Docker Compose v2 (`docker compose`)
- Ruang disk cukup untuk volume DB + `uploads/`
- Zona waktu server: `Asia/Jakarta`
- Git untuk menarik kode terbaru

```bash
docker --version && docker compose version
```

---

## 3. Instalasi Pertama

```bash
# 1. Clone repo
git clone https://github.com/bestprofitsurabaya/bpf-workhub.git
cd bpf-workhub

# 2. Build & jalankan
docker compose up -d --build

# 3. Verifikasi
docker compose ps                 # kedua container "Up" dan "healthy"
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/login   # → 200
```

Database **dibuat otomatis** pada first run dari `init.sql`. Kredensial awal:

| Role | Username | PIN |
|------|----------|-----|
| Admin | `admin` | `123456` |
| GA | `ga_officer` | `123456` |
| Finance | `finance_officer` | `123456` |

> ⚠️ **Segera ganti PIN bawaan** setelah login pertama.

---

## 4. Variabel Lingkungan

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `DB_HOST` | `db` | Host MariaDB (nama service compose) |
| `DB_USER` | `bpf_user` | User DB |
| `DB_PASSWORD` | `bpf_pass` | Password DB |
| `DB_NAME` | `bpf_asset_system` | Nama database |
| `DB_POOL_SIZE` | `15` | Ukuran pool koneksi |
| `REDIS_URL` | `redis://redis:6379/0` | Backing store rate limit. Jika Redis mati, fallback ke memori |
| `SECRET_KEY` | wajib ganti | **WAJIB GANTI di produksi** — dipakai untuk session & CSRF |
| `FLASK_DEBUG` | `0` | Jangan aktifkan di produksi |
| `TZ` | `Asia/Jakarta` | Zona waktu |
| `SESSION_HOURS` | `12` | Masa berlaku sesi login (jam) |
| `SESSION_COOKIE_SECURE` | `true` | Cookie hanya lewat HTTPS. Set `false` untuk dev lokal |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Proteksi CSRF tingkat cookie |

**Cara generate SECRET_KEY aman:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> 🔴 Jika `SECRET_KEY` diubah setelah produksi berjalan, semua session login akan ter-logout (aman, hanya perlu login ulang).

---

## 5. Update ke Versi Baru

```bash
cd bpf-workhub

# 1. Backup dulu (lihat bagian 6)
# 2. Tarik kode terbaru
git pull origin main

# 3. Rebuild & restart
docker compose up -d --build

# 4. Cek kesehatan
docker compose ps
docker logs bbm_web --tail 50 | grep -iE 'error|traceback' || echo 'bersih'

# 5. Smoke test
curl -s -o /dev/null -w 'login: %{http_code}\n'  http://localhost:5001/login
curl -s -o /dev/null -w 'driver: %{http_code}\n'  http://localhost:5001/driver
```

> 💡 **Migrasi schema:** tabel `notifications` dibuat otomatis saat startup. Untuk perubahan schema lain, Tim IT akan menyertakan file SQL di release note.

**Update frontend / PWA:** service worker memakai `CACHE_NAME` ber-version; saat update, versi asset di-bump sehingga perangkat driver otomatis mengambil versi baru.

---

## 6. Backup & Restore + Foto Cleanup

### 6.1 Backup Otomatis (v2.21, Direkomendasikan)

Service `backup` di docker-compose: **mysqldump semua database setiap 03:00 WIB** ke volume `bbm_backups`, retensi 30 hari.

### 6.2 Foto Overtime Cleanup (v2.28.2)

Foto overtime yang tersimpan di `uploads/overtime/` dibatasi **maksimal 6 bulan (180 hari)**. Tiga mekanisme cleanup:

| Mekanisme | Interval | Keterangan |
|-----------|----------|------------|
| **Cron di container** | Tiap 30 menit | Shell script `scripts/overtime-cleanup.sh`, dijalankan cron di `bbm_web` — bekerja langsung saat fresh deploy |
| **Background thread Flask** | Tiap 30 menit | Fungsi `_periodic_photo_cleanup()` di `app.py`, daemon thread |
| **Manual trigger** | On-demand | Admin bisa panggil `POST /api/overtime/cleanup-photos` dari dashboard atau API |

**Log cleanup:**
```bash
# Lihat log cleanup terakhir
docker exec bbm_web cat /var/log/overtime-cleanup.log

# Cleanup manual via API
curl -X POST http://localhost:5001/api/overtime/cleanup-photos \
  -H "Cookie: session=..."

# Cleanup manual via shell
docker exec bbm_web sh /app/scripts/overtime-cleanup.sh
```

**Konfigurasi:**
- Default: 180 hari (6 bulan)
- Bisa diubah via environment variable `MAX_AGE_DAYS` di `docker-compose.yml` atau `Dockerfile`

```bash
# Cek status backup terakhir
docker exec bbm_backup cat /backups/last-backup.txt

# Lihat file backup
docker exec bbm_backup ls -lh /backups/

# Jalankan backup manual
docker exec bbm_backup /bin/sh /usr/local/bin/backup-db.sh
```

### 6.3 Backup Manual

```bash
# Backup DB
docker exec bbm_web sh -c 'mysqldump -h db -u bpf_user -pbpf_pass bpf_asset_system \
  --single-transaction --routines --triggers' > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup uploads
tar czf uploads_$(date +%Y%m%d).tar.gz uploads/
```

### 6.4 Restore

```bash
# Stop web dulu
docker compose stop web

# Restore DB
zcat backup.sql.gz | docker exec -i bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system

# Restore uploads
tar xzf uploads_YYYYMMDD.tar.gz -C .

# Start lagi
docker compose start web
```

---

## 7. Monitoring & Log

### 7.1 Kesehatan Container

```bash
docker compose ps                      # status container
docker inspect --format='{{.State.Health.Status}}' bbm_mariadb
```

### 7.2 Log Aplikasi

```bash
docker logs -f bbm_web                # live tail
docker logs bbm_web --since 1h        # 1 jam terakhir
```

### 7.3 Query Monitoring

```bash
# Status transaksi
docker exec bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system \
  -e "SELECT status, COUNT(*) FROM transactions GROUP BY status;"

# Kasbon berjalan
docker exec bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system \
  -e "SELECT display_id, driver_name, total_amount, status FROM fuel_cash_requests ORDER BY id DESC LIMIT 20;"

# Audit trail
docker exec bbm_mariadb mysql -uroot -ppassword_db bpf_asset_system \
  -e "SELECT created_at, user_name, action FROM activity_logs ORDER BY id DESC LIMIT 20;"
```

### 7.4 Healthcheck Endpoint

```bash
# Status layanan (DB, Redis, pool)
docker exec bbm_web curl -s localhost:5000/api/health | python3 -m json.tool
```

---

## 8. Reverse Proxy & HTTPS

Produksi saat ini diakses via **`https://nasbpfsby.duckdns.org:5000`** — nginx reverse proxy.

```nginx
server {
    listen 5000 ssl;
    server_name nasbpfsby.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/nasbpfsby.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nasbpfsby.duckdns.org/privkey.pem;

    location / {
        set $upstream_bbm http://bbm_web:5000;
        proxy_pass $upstream_bbm;

        # ★ PENTING untuk WebSocket / Socket.IO
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 9. Troubleshooting

| Masalah | Kemungkinan Penyebab | Solusi |
|---------|---------------------|--------|
| `bbm_web` restart loop | `db` belum healthy / kredensial salah | Cek `docker compose ps`; tunggu healthcheck |
| 500 pada semua halaman | `SECRET_KEY` berubah / session korup | Hapus cookie session, login ulang |
| Notifikasi tidak real-time | Proxy tidak meneruskan header WebSocket | Tambahkan `proxy_set_header Upgrade` (lihat §8) |
| Login selalu gagal | User nonaktif / PIN salah | Cek `SELECT username,is_active FROM users` |
| Halaman lambat | Service worker versi lama | Hard refresh |
| Port 5001 bentrok | Aplikasi lain memakai port | Ubah `ports: "XXXX:5000"` di compose |
| Data tidak tersimpan | Volume hilang | Jangan hapus `bbm_db_data` |

---

## 10. Daftar Endpoint

### Halaman (Web)

| Method | Path | Auth | Fungsi |
|--------|------|------|--------|
| GET | `/login` | Publik | Login admin |
| GET | `/logout` | Session | Logout |
| GET | `/driver` | Publik | PWA Driver |
| GET | `/admin` | admin/ga/finance | Dashboard admin |
| GET | `/ga/assignments` | admin/ga | Penugasan kendaraan |
| GET | `/admin/rekap` | admin/finance | Rekapitulasi |
| GET | `/admin/analytics` | admin/ga/finance | Analytics |
| GET | `/admin/trips` | admin/ga | Trip review |
| GET | `/admin/users` | **admin** | Manajemen pengguna |
| GET | `/admin/settings` | admin/ga/finance | Pengaturan |
| GET | `/admin/logs` | admin | Audit log |

### API Penting

| Method | Path | Auth | Fungsi |
|--------|------|------|--------|
| GET | `/api/stats` | Session | Statistik dashboard |
| GET | `/api/notifications?driver=...` | Publik | Notifikasi driver |
| POST | `/api/notifications/read` | Publik | Tandai notifikasi dibaca |
| POST | `/api/cash/request` | Publik (driver) | Ajukan kasbon |
| POST | `/api/cash/submit-lpj/<id>` | Publik (driver) | Kirim LPJ |
| GET | `/api/cash/history` | Publik (driver) | Riwayat kasbon |
| POST | `/api/cash/approve-ga/<id>` | ga/admin | Approve kasbon GA |
| POST | `/api/cash/approve-finance/<id>` | finance/admin | Cairkan kasbon |
| POST | `/api/users/sync` | **admin** | Tambah/update user |
| POST | `/api/users/reset-pin` | **admin** | Reset PIN user |
| POST | `/api/verify-pin` | Publik | Verifikasi PIN |
| POST | `/api/assignments/create` | ga/admin | Assign kendaraan |
| POST | `/api/drivers/sync` | admin | Tambah driver |

---

## 11. Cloudflare Tunnel (Akses Cadangan Opsional)

> ⚠️ **Nonaktif sejak v1.2.3** — produksi memakai DuckDNS + nginx.

Aplikasi bisa diakses publik tanpa membuka port di router/gateway, memakai Cloudflare Tunnel.

### Quick Tunnel (Uji Coba)

```yaml
# di docker-compose.yml
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: bbm_cloudflared
  command: tunnel --no-autoupdate --url http://web:5000
  depends_on:
    - web
  restart: unless-stopped
```

Jalankan: `docker compose up -d cloudflared`  
Lihat URL: `bash scripts/tunnel-url.sh`

### Named Tunnel (URL Permanen)

1. Dashboard Cloudflare → Zero Trust → Networks → Tunnels → Create
2. Salin Tunnel Token
3. Ubah command: `tunnel --no-autoupdate run --token <TOKEN>`
4. Tambahkan Public Hostname → Service: `http://web:5000`

---

## 12. SPA Vue 3 — Build & Deploy

Mulai v2.0, antarmuka admin/back-office adalah **Single Page App Vue 3**.

### Alur Build

```
Stage 1 (node:20-alpine): cd frontend && npm install && npm run build → dist/
Stage 2 (python:3.11-slim): Flask + dependensi; dist disalin ke /app/static/app/
```

> 🔴 **PENTING:** `docker-compose.yml` me-mount `./static:/app/static`. Setelah pull kode baru:
> ```bash
> bash scripts/build-spa.sh     # build SPA + salin ke static/app/
> docker compose up -d --build
> ```

### Build Lokal

```bash
cd frontend
npm install
npm run dev        # dev server :5173, proxy /api → localhost:5001
npm run build      # hasil di frontend/dist
```

### Endpoint Auth & Trips

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/auth/me` | Status sesi + role + CSRF token |
| POST | `/api/auth/login` | Login JSON (username + PIN) |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/trips` | List log perjalanan |
| POST | `/api/trips/verify/<id>` | Verify trip |
| POST | `/api/trips/reject/<id>` | Reject trip + alasan |
| GET | `/app/*` | SPA (fallback index.html) |

### Endpoint News Scraper (v2.23)

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/scraper/sites` | List WordPress sites |
| POST | `/api/scraper/sites` | Tambah/edit WordPress site |
| DELETE | `/api/scraper/sites/<name>` | Hapus WordPress site |
| POST | `/api/scraper/test-connection` | Test koneksi WP API |
| POST | `/api/scraper/check` | Scrape artikel dari newsmaker.id |
| POST | `/api/scraper/upload` | Upload artikel ke WordPress + SEO |
| POST | `/api/scraper/duplicates` | Cek artikel duplikat |
| POST | `/api/scraper/duplicates/delete` | Hapus artikel duplikat |
| GET | `/api/scraper/backlinks` | Lihat config backlinks |
| POST | `/api/scraper/backlinks` | Simpan config backlinks |
| POST | `/api/scraper/backlinks/add-keyword` | Tambah keyword mapping |
| GET | `/api/scraper/hyperlinks` | List hyperlinks |
| POST | `/api/scraper/hyperlinks` | Simpan hyperlinks |
| GET | `/api/scraper/log` | Activity log |
| DELETE | `/api/scraper/log` | Clear log |

---

## 13. Checklist Sebelum Go-Live

- [ ] `SECRET_KEY` ada di `.env` lokal (gitignored)
- [ ] PIN bawaan semua akun sudah diganti
- [ ] Reverse proxy meneruskan header WebSocket
- [ ] Backup otomatis terkonfigurasi (DB + uploads)
- [ ] HTTPS aktif (PWA wajib secure origin)
- [ ] Smoke test: `/login` 200, `/driver` 200, `/app/` 200
- [ ] SPA: `bash scripts/build-spa.sh` sudah dijalankan
- [ ] Test suite: `docker exec bbm_web python3 -m pytest tests/ -q` → semua PASS
- [ ] Frontend: `cd frontend && npm test` → semua PASS

---

## 📞 Kontak

**PT. Bestprofit Futures — Surabaya**  
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271  
Telp: 031-5349888

---

*BPF WorkHub v2.28.2 · Panduan Deployment*
