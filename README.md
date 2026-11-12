# 🏢 BPF WorkHub

Sistem operasional digital untuk **PT Bestprofit Futures** — Kantor Pusat Jakarta, dipakai oleh kantor pusat dan cabang-cabangnya di Indonesia.

> **Versi 2.86.1 · November 2026** — riwayat lengkap: [CHANGELOG.md](CHANGELOG.md)

BPF WorkHub lahir dari masalah yang sudah bertahun-tahun jadi kebiasaan: pengeluaran BBM driver, kasbon, lembur, dan pembelian air minum tercatat di kertas dan Google Sheet — lampiran foto sukar dilacak, rekap sering tidak sinkron, dan dokumen penting terselip di mana-mana. Aplikasi ini menggantikannya dengan satu tempat: yang di lapangan mengirim lewat HP, yang memverifikasi bekerja lewat dashboard, dan semuanya tercatat penuh dengan audit trail.

## 🧭 Cara kerjanya

1. **Yang di lapangan** (driver, OB, security) mengirim pengajuan lewat PWA di HP — foto nota dan odometer, formulir lembur, belanja air minum. Koneksi lemah pun aman karena ada antrean offline.
2. **Yang memverifikasi** (Chief Driver, GA, Finance, GA HR) memeriksa lewat dashboard, memberi ACC berjenjang, lalu mencairkan dana.
3. **Sistem berjaga di tengahnya**: AI mendeteksi anomali konsumsi BBM, klaim dijodohkan otomatis dengan transaksi SPBU resmi MyPertamina, setiap PDF resmi diberi sidik jari SHA-256, dan setiap tindakan tercatat di log audit.

## 👥 Siapa pakai apa

| Peran | Mengerjakan | Masuk ke |
|-------|-------------|-----------|
| **Admin** — pusat: `admin`; cabang: `admin_<kode>` | Akun, cabang, pengaturan, log, Access Review | `/app/dashboard` |
| **Driver** | Klaim BBM, kasbon, log perjalanan, rapor kendaraan | PWA `/m/` |
| **Chief Driver** | ACC pengajuan driver, assign appointment | `/app/chief-driver` |
| **GA Officer** | Verifikasi klaim & kasbon, perjalanan, penugasan, procurement, aset | `/app/ga` |
| **Finance** | Pencairan dana, verifikasi air minum & SubsidiTepat, Berita Acara | `/app/finance` |
| **GA HR** | Kelola data lembur (rekap, PDF resmi, formulir permohonan) | `/app/ga-hr` |
| **Marketing** | Jadwal & pantau appointment nasabah | `/app/marketing` |
| **OB / Security** | Belanja air minum, pencatatan lembur | PWA `/m/` · `/app/overtime-me` |
| **Receptionist** | Rekrutmen (pelamar & in-out karyawan) | `/app/receptionist` |
| **Traineer** | Verifikasi Absensi FirstWork; data pelamar cabang (lihat saja) | `/app/first-work` |
| **IT per cabang** (`it_<kode>`) | Berita perusahaan (scraper), Transcoder, PDF Kit | `/app/it` |

Konvensi akun — **satu orang per divisi di satu cabang** → `{divisi}_{cabang}` (mis. `finance_sby`); lebih dari satu → `{divisi}_{nama}_{cabang}` (mis. `ob_faisol_sby`); Driver memakai nama orang; divisi IT memakai role `it_<kode>` per cabang. Backend memvalidasi pembeda divisi ini, jadi nama seperti `uang` untuk Finance akan ditolak. Semua login memakai **PIN**.

## ✨ Modul-modul

| Modul | Inti kegiatan |
|-------|---------------|
| 💰 **Klaim BBM & Kasbon** | Foto nota + odometer, hitung konsumsi per km otomatis, deteksi anomali AI, kode kasbon harian unik, LPJ |
| ✅ **ACC Berjenjang** | Pengajuan wajib lewat atasan dulu (jurnal ACC + alasan tolak tercatat); penunjukan atasan bisa diatur per user |
| 🗺 **Perjalanan & Appointments** | Trip multi-tujuan dengan GPS, auto-complete appointment saat trip selesai, notifikasi realtime ke marketing |
| ⏰ **Overtime** | Dua sumber data (Driver dan OB/Security) via Apps Script bridge dari Google Sheet private; auto-refresh; tiga format PDF resmi berlogo BPF |
| 💧 **Air Minum** | Pengajuan galon/botol/gelas dengan foto bukti sebelum–sesudah, verifikasi Finance, PDF tanda terima; koreksi/hapus opsional dengan step-up PIN |
| ⛽ **SubsidiTepat** | Riwayat transaksi resmi SPBU dari portal MyPertamina di-import agen → auto-match ke klaim → Berita Acara Rekonsiliasi (PDF + root-hash antar periode) |
| 🔄 **Penugasan driver** | Serah terima, tukar driver, riwayat per trip |
| 📋 **Procurement · Asset · Expense** | Pengadaan, inventaris aset, dan pencatatan pengeluaran |
| 🪪 **Receptionist** | Pipeline pelamar (daftar hadir otomatis) dan in-out karyawan, sinkron otomatis dari aplikasi dan Google Sheet |
| 🎯 **Absensi FirstWork** | Form publik ber-token per cabang (QR statis bisa dicetak) — pendaftar first work mengisi NIK, foto KTP, dan referensi; menerima **ID Fingerprint & ID BPF** otomatis yang angka awalnya diatur Traineer; verifikasi, koreksi, dan ekspor CSV di dashboard |
| 📰 **News Scraper** | Berita tentang BPF dikumpulkan dari portal berita → publish ke WordPress tiap cabang (cron 06/10/14/18 WIB, hanya artikel berumur ≤ 1 hari) |
| 🎬 **Transcoder** | YouTube → audio/video untuk materi internal (ffmpeg + yt-dlp) |
| 📄 **PDF Kit** | Kompres PDF dua mesin: lossy Ghostscript + lossless qpdf — sadar dokumen bertanda tangan |
| 🔐 **Keamanan & tata kelola** | Step-up PIN untuk aksi uang, Access Review triwulanan, retensi & arsip audit, integritas dokumen (hash SHA-256), program ISO 27001 |

## 🏗️ Arsitektur

Semuanya hidup di satu NAS (Debian + Docker Compose); HTTPS dilayani oleh proxy Nextcloud nginx yang berjalan di server yang sama. Data terpisah per cabang: satu DB master + satu DB tiap cabang **lain** — cabang default (Surabaya) sengaja berbagi DB master, dan konvensi ini dijaga guard di CI.

```txt
   Browser (SPA /app/) & PWA driver (/m/)
        │   HTTPS  nasbpfsby.duckdns.org:5000
        ▼
 nextcloud_nginx (SSL termination, cache assets, WebSocket)
        │   proxy_pass → jaringan docker bersama
        ▼
┌──────────────────────────── bpf-workhub (Docker Compose) ─────────────────────┐
│  web     Flask + SocketIO · gunicorn gevent 1 worker · SPA & PWA dalam image   │
│  db      MariaDB 10.11 — 1 DB master (dipakai SBY) + 11 DB cabang              │
│  redis   Redis 7 (cache, rate-limit, realtime bus)                             │
│  backup  dump harian 03:00 + drill restore mingguan + heartbeat Uptime Kuma    │
└────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ file gate (bind mount)
 agen di host: login-OTP SubsidiTepat (Chrome dalam Xvfb) + sinkronisasi 06:15 WIB
```

Teknologi utama: **Python 3.11 / Flask 3 / gevent / Socket.IO**, **Vue 3 + Vite**, **MariaDB**, **Redis**. Dockerfile multi-stage: build SPA di stage Node, runtime Python slim + mysql-client + ffmpeg/poppler/ghostscript/qpdf (untuk PDF Kit, transcoder, kompres foto).

## 📁 Peta repo

```text
bpf-workhub/
├── app.py               # entry Flask: wiring modul, middleware keamanan, ensure-schema startup
├── modules/             # backend: route API tiap modul, DB pool, generator PDF, guard keamanan
├── frontend/            # SPA Vue 3 (views per peran, router + guard, vitest)
├── mobile/              # PWA shell driver/OB/security (bind mount — bedah cepat tanpa rebuild)
├── agent/subsiditepat/  # agen host: login MyPertamina, pull/push riwayat SPBU, OTP supervisor
├── scripts/             # migrasi DB, smoke test, backup/restore, Appscript bridge, cek stamp versi
├── tests/               # pytest backend (75 file)
├── docs/                # dokumentasi — mulai dari INDEX.md
├── guides/              # panduan pengguna per peran
├── init.sql             # seed schema, cabang, akun demo
└── docker-compose.yml   # web · db · redis · backup (dokumen kaya komentar per keputusan desain)
```

Data yang harus bertahan antar restart tersimpan di tiga volume `bpf-workhub_*` (DB, redis, backup) plus bind `/srv/bpf-workhub/` (uploads user, hasil transcoder, arsip Berita Acara — dokumen resmi, jangan pernah dihapus). Kredensial tinggal di `.env` (template: `.env.example`, tidak pernah di-commit).

## 🚦 Mulai cepat (fresh deploy)

```bash
cp .env.example .env && chmod 600 .env   # isi SECRET_KEY + MYSQL_*; generator di header template
docker compose up -d --build             # DB di-seed init.sql saat volume pertama dibuat
curl http://127.0.0.1:5001/api/health    # harap 'database': 'ok'
```

Akun demo khusus **fresh install** (PIN awal `123456` — wajib diganti):

| Login | Peran |
|---|---|
| `admin` | Admin Pusat |
| `ga_sby` | GA Surabaya |
| `finance_sby` | Finance Surabaya |

> Di server produksi, akun seed `admin` sudah di-rename menjadi `admin_master` dan PIN bawaan telah diganti. Daftar akun per cabang: [docs/internal/USER_LIST.md](docs/internal/USER_LIST.md).

## 🧪 Uji & rilis

```bash
./scripts/run-tests.sh          # pytest aman (lewati 2 file butuh DB)
./scripts/run-tests.sh --db     # lengkap; kredensial dari .env, hindari saat produksi sibuk
cd frontend && npx vitest run   # unit SPA
```

CI GitHub Actions menjaga standar tiap push: build SPA + vitest + `npm audit`, pytest + `pip-audit` + cek stamp versi + cek peta cabang→DB, dan scan image **Trivy** (CVE HIGH/CRITICAL membuat build gagal). Rilis baru: bump versi di 7 titik stamp (rinciannya di [docs/DEVELOPER.md](docs/DEVELOPER.md)), isi [CHANGELOG.md](CHANGELOG.md), perbarui panduan, lalu `docker compose build web && docker compose up -d web`.

## 🗺️ Peta dokumentasi

Indeks lengkap semua dokumen + statusnya: **[docs/INDEX.md](docs/INDEX.md)**. Ringkasnya:

- 📖 Belajar pakai: [Panduan Pengguna](guides/USER_GUIDE.md) · [Lembar Latihan](docs/public/PELATIHAN.md) · [Materi Presentasi](docs/public/PRESENTASI.md) · [One-pager](docs/public/ONEPAGER.md)
- 🚀 Menjalankan sistem: [Panduan Deployment](docs/internal/DEPLOYMENT.md) · [Deploy dari Nol](docs/internal/DEPLOY_FRESH.md) · [Keamanan & Standar ISO](docs/internal/SECURITY.md) · [Runbook Insiden](docs/internal/INCIDENT_RUNBOOK.md)
- 🧭 Pengembangan: [DEVELOPER.md](docs/DEVELOPER.md) · [Changelog](CHANGELOG.md) · [Progress Tracker](docs/internal/PROGRESS.md) · [Daftar User & Role](docs/internal/USER_LIST.md)

## 📞 Kontak

**PT. Bestprofit Futures — Kantor Pusat Jakarta**
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190 · 031-5349888

*Dikembangkan oleh tim IT BPF — dengan cinta (dan sedikit pytest).*
