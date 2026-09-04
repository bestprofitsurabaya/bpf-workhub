# 🏢 BPF WorkHub

**Sistem Manajemen Armada untuk PT. Bestprofit Futures — Surabaya**

> 📅 Versi 2.29.1 · September 2026 — Production hardening (gunicorn, pool DB, keamanan port)

---

## 🎯 Apa itu BPF WorkHub?

BPF WorkHub adalah aplikasi web yang membantu tim operasional PT Bestprofit Futures mengelola aktivitas harian armada — mulai dari pencatatan pengeluaran BBM (bensin), pengajuan kasbon (uang muka), log perjalanan driver, hingga manajemen appointment nasabah.

**Cara kerjanya sederhana:**
1. 🚗 **Driver** mengisi data BBM dan perjalanan lewat HP (PWA)
2. 👤 **GA/Finance** memverifikasi dan mencairkan dana
3. 📊 **Admin** memantau semua aktivitas dari dashboard
4. 📱 Semua data tersinkron real-time via WebSocket

---

## ✨ Fitur Utama

### 💰 Klaim BBM & Kasbon
- Driver submit foto bukti BBM (odomenter, nota, struk)
- Sistem otomatis hitung konsumsi BBM per kilometer
- AI mendeteksi anomali penggunaan BBM
- Kasbon dengan kode unik harian untuk verifikasi cash

### 🗺️ Log Perjalanan
- Multi-destination trip tracking
- Integrasi dengan Google Maps (GPS tracking)
- Auto-complete appointment saat driver submit trip
- Real-time notifikasi ke marketing

### 📅 Appointment
- Marketing buat jadwal kunjungan nasabah
- Chief Driver assign ke driver
- Driver konfirmasi kunjungan via trip
- Status tracking real-time

### ⏰ Overtime (Lembur)
- Form publik untuk OB/Security (tanpa login)
- Driver submit lembur dari PWA
- Sync dari Google Sheet (data existing)
- Export PDF laporan lembur

### 💧 Air Minum
- Pembelian air minum untuk kantor
- Tracking stok dan pengeluaran

---

## 👥 Siapa yang Pakai?

| Role | Kegunaan | Contoh |
|------|----------|--------|
| **Admin** | Kelola semua data dan user | Manajer IT |
| **Driver** | Submit BBM, kasbon, trip | AKHAD, BUDI |
| **GA** | Verifikasi klaim BBM & kasbon | Staff GA |
| **Finance** | Pencairan dana | Staff Keuangan |
| **GA HR** | Kelola data lembur | Staff HRD |
| **Marketing** | Buat & pantau appointment | Marketing |
| **Chief Driver** | Assign driver ke appointment | Supervisor |
| **OB/Security** | Submit lembur lewat form publik | OB, Security |

---

## 🚀 Cara Mulai

### Akses Online
🌐 **https://nasbpfsby.duckdns.org:5000**

### Akses Lokal (Development)
```bash
# Clone repository
git clone https://github.com/bestprofitsurabaya/bpf-workhub.git
cd bpf-workhub

# Jalankan dengan Docker (port host sudah localhost-only sejak v2.29.1)
docker compose up -d --build

# Akses dari mesin yang sama / SSH tunnel:
#   ssh -L 5001:127.0.0.1:5001 user@server
# Buka browser → http://localhost:5001
#
# Catatan: port 5001 (web) & 3307 (DB) sengaja di-bind ke 127.0.0.1 —
# produksi dilayani lewat nextcloud_nginx (HTTPS), bukan port host.
```

### Akun Demo (PIN-based)

| Login | PIN | Role |
|-------|-----|------|
| `admin` | `123456` | Admin |
| `ga_sby` | `123456` | GA Surabaya |
| `finance_sby` | `123456` | Finance Surabaya |
| `it_sby` | `123456` | IT Surabaya |
| `AKHAD` | `123456` | Driver |

> Semua login memakai **PIN**, bukan password. Endpoint login: `POST /api/auth/login`
> (JSON `{username, pin}` + header `X-CSRF-Token` dari `GET /api/auth/me`).

---

## 🛠️ Teknologi yang Dipakai

| Komponen | Teknologi | Fungsi |
|----------|-----------|--------|
| Backend | Python Flask | Server & API |
| Runtime | Gunicorn (eventlet) | WSGI production (sejak v2.29.1) |
| Frontend | Vue 3 + Vite | Tampilan SPA (di-build ke dalam image) |
| Database | MariaDB | Penyimpanan data |
| Cache | Redis | Session & real-time |
| Realtime | Socket.IO | Notifikasi langsung |
| Container | Docker | Deployment |

---

## 📁 Struktur Project

```
bpf-workhub/
├── app.py                  # File utama Flask
├── modules/                # Modul backend
│   ├── routes_driver.py    # Endpoint driver
│   ├── routes_cash.py      # Endpoint kasbon
│   ├── routes_overtime.py  # Endpoint lembur
│   ├── routes_news_scraper.py  # Scraper berita
│   └── ...
├── frontend/               # SPA Vue 3
│   ├── src/views/          # Halaman-halaman
│   └── src/stores/         # State management
├── tests/                  # Unit tests
├── docker-compose.yml      # Konfigurasi Docker
└── .env                    # Environment variables
```

---

## 🔒 Keamanan

- 🔐 Login PIN dengan brute-force protection
- 🛡️ CSRF protection di semua form
- 🔒 HTTPS dengan sertifikat Let's Encrypt
- 📝 Audit log untuk semua aktivitas
- 🚫 Rate limiting untuk mencegah spam
- 🔑 Role-based access control (RBAC)

---

## 🧪 Pengujian

```bash
# Backend tests
python -m pytest tests/ -v

# Frontend tests
cd frontend && npm test
```

**Status:** 313 pytest · Semua ✅ PASS (terakhir diverifikasi di container rebuilt v2.29.1)

---

## 📚 Dokumen Lainnya

- [🛡️ Keamanan & Standar](SECURITY.md)
- [🚀 Panduan Deploy](DEPLOYMENT.md)
- [📖 Panduan User](USER_GUIDE.md)
- [📋 Changelog](CHANGELOG.md)

---

## 📞 Kontak

**PT. Bestprofit Futures — Surabaya**
Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18
📞 031-5349888

---

*Dikembangkan dengan ❤️ oleh Tim IT BPF*
