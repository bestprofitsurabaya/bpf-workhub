# 🏢 BPF WorkHub v2.27.0

**Sistem Manajemen Armada, Klaim BBM, Kasbon, Log Perjalanan, Appointment & Air Minum**  
**PT. Bestprofit Futures — Surabaya**

---

Sistem end-to-end untuk pencatatan, verifikasi, persetujuan, dan pengarsipan klaim BBM, pengajuan kasbon dengan kode unik, log perjalanan harian, serta manajemen aset, oxygen, dan content management (News Scraper). Dilengkapi dengan sistem appointment, deteksi anomali Machine Learning, GPS tracking, watermark foto, PIN security, session-based login, role-based access, CSRF protection, notifikasi real-time, import Excel, audit trail, Chart.js visualization, PWA offline-first, dan WebSocket real-time.

---

## 🧭 Apa Isi Sistem Ini?

BPF WorkHub dirancang untuk menggantikan cara kerja manual (catat di kertas, rekap di Excel) dengan satu aplikasi digital yang dipakai semua orang di perusahaan — dari sopir, OB, GA, Finance, Marketing, Chief Driver, hingga Admin.

**Inti masalah yang diselesaikan:**
- Sopir harus bayar BBM dari uang sendiri, lalu menunggu berhari-hari uangnya diganti.
- OB membeli galon tanpa bukti resmi.
- Finance harus mengecek struk satu per satu secara manual.
- Tidak ada audit trail yang jelas.

**Solusinya:**
Semua tercatat, terverifikasi, dan bisa dipertanggungjawabkan — dengan satu aplikasi yang dipakai semua orang, sesuai porsinya masing-masing.

---

## ✨ Fitur Utama

### 📱 Driver (PWA Offline-First)
- 5 tab: ⛽ BBM, 💰 Kasbon, 🗺️ Trip, ⏰ OT, 📊 Rapor
- Offline-first: data tersimpan di HP dan terkirim otomatis saat online
- Notifikasi real-time via WebSocket
- Watermark otomatis: GPS + waktu + nama perusahaan
- PWA: bisa dipasang di layar utama HP

### 👨‍💼 GA (General Affairs)
- Dashboard GA: antrean klaim BBM, kasbon, trip review
- Verifikasi anomali ML dengan foto bukti
- Aset & Pemeliharaan: 15 unit AC + 8 kendaraan + 12 komponen
- Health score otomatis 0–100

### 💰 Finance
- Rekap air minum per OB, per jenis, per merk
- Verifikasi pengajuan air minum → PDF tanda terima
- Kasbon: approve, cairkan, arsipkan
- Export CSV/Excel

### 📣 Marketing
- Input appointment kunjungan nasabah
- Jam kunjungan spesifik untuk rute otomatis
- Pantau status real-time

### 🚛 Chief Driver
- Board penugasan per sesi & per driver
- ⚡ Atur Rute Otomatis: kunjungan dibagi per area & urut jam
- Estimasi jarak/BBM + angka penghematan
- Atur Rute Manual (tentukan driver + urutan sendiri)

### 🪪 Receptionist
- Form publik pelamar kerja (tanpa login)
- Verifikasi data, catat kehadiran interview & 4 hari training
- Laporan PDF resmi berlogo BPF
- Kelola dropdown User untuk form pelamar

### 🎯 Traineer / Upline
- Pantau kehadiran rekrutan (read-only)
- Scope otomatis: hanya rekrutan dengan UPLINE milik sendiri

### ⏰ GA HR (Overtime)
- Data overtime Driver dari Google Sheet (8.665 baris)
- Form publik OB/Security tanpa login
- Auto-refresh saat login/logout
- Edit & hapus data overtime

### 📰 IT (News Scraper — Multi-Cabang)
- Scrape artikel dari newsmaker.id + Detik Finance (64 artikel/scrape)
- Multi-WordPress site management (10 cabang, CRUD, test connection)
- Upload artikel ke WordPress dengan SEO optimization
- Financial Authority Backlinks otomatis (24+ situs)
- Duplicate article checker
- Tab Report: detail per-artikel + filter + export CSV
- Configurable daily limit (1-100/hari)
- Password toggle 👁/🙈 di site card & form

### ⚙️ Admin
- Manajemen user: buat akun, reset PIN, aktifkan/nonaktifkan
- Multi-cabang: isolasi data penuh per cabang
- Audit log: semua aktivitas tercatat
- Backup DB otomatis
- Seed & bersihkan data demo

---

## 🔄 Alur Kerja

### Alur Klaim BBM
```
Driver → GA Approve → Finance Payout → Driver TTD → Archive ZIP
```

### Alur Kasbon
```
Driver → GA Approve → Finance Cairkan → GA Serahkan → Driver Isi LPJ → GA Verifikasi → Selesai
```

### Alur Appointment
```
Marketing Input → Chief Driver Bagi → Driver Kunjungi → GA Review Trip
```

### Alur Air Minum
```
OB Ajukan → Finance Verifikasi → PDF Tanda Terima
```

### Alur Pelamar Kerja
```
Pelamar Isi Form → Receptionist Verifikasi → Kehadiran Interview + Training → Lulus/ Mundur
```

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + Flask |
| Frontend | Vue 3 + Vite (SPA penuh) |
| Database | MariaDB 10.11 |
| Cache | Redis 7 |
| Realtime | Flask-SocketIO + eventlet |
| ML | Scikit-learn (Isolation Forest) |
| PDF | FPDF2 + DejaVu Sans |
| Excel | openpyxl |
| Charts | Chart.js 4.4 |
| Container | Docker + Docker Compose |
| PWA | Service Worker + IndexedDB |

---

## 📦 Quick Start

```bash
git clone https://github.com/bestprofitsurabaya/bpf-workhub.git
cd bpf-workhub
docker compose up -d
```

Aplikasi tersedia di `http://localhost:5001`

---

## 🔐 Akun Default

| Role | Username | PIN |
|------|----------|-----|
| Admin | `admin` | `123456` |
| GA | `ga_officer` | `123456` |
| Finance | `finance_officer` | `123456` |
| OB | `ob1` | `123456` |
| Marketing | `Yusie` | `123456` |
| Chief Driver | `driver` | `123456` |
| Driver | `wicak` | `123456` |
| Receptionist | `receptionis` | `123456` |
| Traineer | `traineer_a` | `123456` |
| GA HR | `ga_hr_officer` | `123456` |
| IT Surabaya | `it_sby` | `123456` |

---

## 📁 Struktur Project

```
bpf-workhub/
├── app.py                    # Entry point Flask + SocketIO
├── init.sql                  # Schema database
├── modules/                  # Backend modular (32 file)
│   ├── routes_*.py           # 16 route modules
│   ├── config.py             # DB connection pool
│   ├── helpers.py            # Utils + role_required
│   ├── engine.py             # ML insights
│   ├── pdf_generator.py      # PDF enterprise
│   └── realtime.py           # SocketIO bus
├── frontend/                 # SPA Vue 3
│   └── src/
│       ├── views/            # 20+ view components
│       ├── stores/           # Pinia stores
│       ├── router/           # Vue Router + role guards
│       └── components/       # Modal, Toast, Notification
├── tests/                    # 20 test files (pytest)
├── scripts/                  # Utility scripts
├── docker-compose.yml        # 4 services (db, web, redis, backup)
└── Dockerfile
```

---

## 🧪 Testing

- **243 pytest** (backend)
- **82 Vitest** (frontend)
- **Browser verification** via Puppeteer
- **CI/CD** via GitHub Actions

---

## 🚀 Deployment

### Online
- **URL**: `https://nasbpfsby.duckdns.org:5000`
- **Reverse Proxy**: nginx + DuckDNS + Let's Encrypt

### Local Development
- **URL**: `http://localhost:5001`
- **Port**: 5001 (web) → 5000 (Flask inside container)

### Docker Services
| Service | Port | Fungsi |
|---------|------|--------|
| `bbm_web` | 5001 → 5000 | Flask + SocketIO |
| `bbm_mariadb` | 3307 → 3306 | MariaDB 10.11 |
| `bbm_redis` | internal | Cache + rate limit |
| `bbm_backup` | cron 03:00 | Backup DB otomatis |
| `bbm_nginx` | 80, 443, 5000 | HTTPS reverse proxy |

---

## 🔒 Keamanan

| Fitur | Deskripsi |
|-------|-----------|
| Login PIN | Username + 6 digit PIN |
| Session | HTTP-only cookie, SameSite=Lax |
| CSRF | Token di semua POST/PUT/DELETE/PATCH |
| Role-Based Access | 11 role, least privilege |
| Audit Trail | 30+ action types |
| Rate Limit | Anti brute-force login |
| Watermark | GPS + timestamp di foto |
| Security Headers | CSP, X-Frame-Options, Referrer-Policy |

---

## 👥 11 Role Pengguna

| Role | Fungsi Utama |
|------|-------------|
| Admin | Full access: settings, users, audit log, semua dashboard |
| GA Officer | Approve/reject klaim, trip review, aset & pemeliharaan |
| Finance | Payout, archive, rekap, verifikasi air minum |
| Marketing | Input appointment kunjungan nasabah |
| Chief Driver | Command center penugasan driver |
| Driver | Submit BBM, trip log, kasbon, overtime (PWA offline-first, auto-save) |
| OB | Pengajuan air minum |
| Receptionist | Verifikasi pelamar kerja |
| Traineer | Pantau kehadiran rekrutan |
| GA HR | Kelola overtime Driver & OB/Security + cetak form PDF |
| IT Surabaya | News Scraper & Content Management (WordPress + SEO, 10 cabang) |

---

## 📄 Dokumen Pendukung

| Dokumen | Deskripsi |
|---------|-----------|
| `DEPLOYMENT.md` | Panduan deployment lengkap |
| `SECURITY.md` | Pemetaan ISO/IEC 27001, ISO 9241-11, ISO 9001 |
| `USER_GUIDE.md` | Panduan pengguna per peran |
| `USER_LIST.md` | Daftar user & role lengkap |
| `CHANGELOG.md` | Riwayat perubahan versi |
| `PRESENTASI.md` | Materi presentasi & demo |
| `PELATIHAN.md` | Lembar latihan per peran |
| `ONEPAGER.md` | Ringkasan satu halaman |

---

## 📞 Kontak

**PT. Bestprofit Futures — Surabaya**  
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271  
Telp: 031-5349888

---

*BPF WorkHub v2.27.0 · Dikembangkan oleh Tim IT BPF Surabaya*
