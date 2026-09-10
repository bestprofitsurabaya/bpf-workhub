# 🏢 BPF WorkHub

**Sistem Manajemen Armada untuk PT. Bestprofit Futures — Kantor Pusat Jakarta**

> 📅 Versi 2.37.0 · September 2026 — Edit/hapus transaksi air minum (fitur opsional per cabang) · Admin per-cabang (`admin_<kode>`) · Approval Berjenjang · Program 6 tahap ISO 27001 selesai · Kantor Pusat Jakarta (Equity Tower)

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
- **Approval berjenjang (v2.36.0)**: kasbon & klaim BBM wajib ACC Chief Driver dulu sebelum diproses GA (gate 409 + antrean "ACC Atasan")

### ✅ ACC Berjenjang
- Semua pengajuan melewati atasan dulu: kasbon/klaim BBM → Chief Driver lalu GA; overtime → GA HR lalu Admin
- Atasan override per user (`manager_username` di Manajemen User); Admin melihat seluruh antrean ACC
- Tolak harus menyertakan alasan — tercatat di jurnal ACC + audit log

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
- **Dua sumber data**: Driver & OB/Security, masing-masing disinkronkan dari Google Sheet private lewat **Apps Script Web App** (tanpa membuka akses sheet)
- **Waktu sesuai sheet (v2.39.0)**: bridge Apps Script mengirim tanggal/jam sesuai tampilan sheet (zona spreadsheet) — jam di aplikasi = jam di sheet, di zona apa pun; feed script lama (ISO UTC → WIB) tetap didukung
- **Form publik** untuk OB/Security (tanpa login) + **form dalam aplikasi** untuk user OB & Security (`/app/overtime-me`, identitas terkunci dari sesi login)
- **Auto-refresh** di background saat GA HR/Admin login/logout (debounce 30 dtk) + tombol Refresh manual
- Riwayat **8.675 sesi Driver** (2020–2026) & **599 sesi OB/Security** tersimpan; tanggal terbaru selalu di posisi teratas
- 3 format PDF resmi berlogo BPF: laporan rekap, detail per karyawan (PDF/Excel), & Formulir Permohonan (foto tersemat, blok TTD 5 kolom)

### 💧 Air Minum
- OB mengajukan pengiriman air minum (galon/botol/gelas) + **foto bukti sebelum & sesudah diisi**
- Finance memverifikasi → **PDF Tanda Terima** (Informasi Pengiriman → Rincian Barang → Lampiran Foto → Tanda Tangan Finance & GA) — foto bukti ditampilkan besar (mengikuti ruang kosong di bawah blok TTD)
- **Edit & hapus transaksi (v2.37.0, fitur opsional)**: Admin mengaktifkan per cabang di Pengaturan → Finance bisa mengoreksi tanggal/item/remark pengajuan Menunggu/Terverifikasi dan menghapus permanen (selalu step-up PIN + snapshot lengkap di audit log)

### 🛡️ Admin per-cabang (v2.37.0)
- Konvensi `{divisi}_{cabang}` berlaku untuk admin: `admin` = Admin Pusat (semua cabang), `admin_sby`/`admin_bdg`/… = Admin cabang (terkunci ke cabangnya)
- Aksi lintas cabang (ganti cabang, reset nomor dokumen, arsip audit, access review) khusus Admin Pusat
- 1 admin untuk 2 cabang? isi `users.managed_branches` (mis. `SBY,BDG`); promosi ke pusat via `users.admin_all_branches = 1`

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
| **OB/Security** | Submit lembur (form dalam aplikasi + form publik) | OB, Security |

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

Akun seed yang dibuat otomatis saat inisialisasi database (terverifikasi login):

| Login | PIN | Role |
|-------|-----|------|
| `admin` | `123456` | Admin |
| `ga_sby` | `123456` | GA Officer |
| `finance_sby` | `123456` | Finance Officer |

> ⚠️ User per-cabang (`ga_sby`, `finance_sby`, `ob_faisol_sby`, `it_sby`, dst.)
> **bukan akun demo publik** — dibuat oleh Admin saat onboarding dan PIN-nya
> dikelola Admin (ganti setelah login pertama). Jangan andalkan PIN `123456`
> untuk akun tersebut.

### ✍️ Konvensi Username (sejak v2.29.7)

Username dibuat agar **langsung terbaca divisi & cabang pemiliknya**:

- Satu orang per divisi di cabang → `{divisi}_{cabang}` — contoh: `finance_sby`,
  `ga_sby`, `gahr_sby`, `receptionist_sby`, `it_bdg`, `security_sby`.
- Lebih dari satu orang per divisi di cabang yang sama → `{divisi}_{nama}_{cabang}`
  — contoh: `ob_faisol_sby`, `ob_febri_sby` (bukan `ob1`/`ob2`), `security_budi_sby`, `marketing_yusie_sby`.
- Khusus **Driver** username tetap nama orang (`akhad`, `wicak`, …) karena
  dipakai login PWA di HP (form pendek) & dibuat otomatis dari tabel `drivers`.
- Divisi `it` memakai cabang sebagai role (`it_sby` … `it_lpg`) — pola lama yang
  dipertahankan; divisi lain cukup 1 role + kolom `branch_code`.
- **Divalidasi backend sejak v2.29.9**: role back-office WAJIB diawali divisi
  (`finance_`, `ob_`, `security_`, …) — username `uang` utk Finance ditolak sistem.
  Pengecualian: Driver (nama orang), Admin, `it_*`; akun lama yang sudah ada
  tetap bisa disimpan tanpa rename.
>
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
- 🧬 **Step-up auth (v2.31, Tahap 2/6 ISO 27001)** — aksi approve/pay berisiko
  (approve kasbon, serah terima dana, payout klaim BBM, verifikasi air minum)
  wajib konfirmasi PIN ulang user yang sedang login (modal PIN, grant 10 menit,
  hilang saat logout)
- 🛂 **Access Review (v2.32, Tahap 3/6 ISO 27001)** — halaman admin untuk
  review hak akses triwulanan: klasifikasi akun otomatis (OK / Basi >90 hari /
  Belum Login / Nonaktif), export CSV arsip, dan pencatatan review selesai
  (A.5.15 · A.8.2 · A.8.3)
- 🛡️ **Vulnerability Management (v2.33, Tahap 4/6 ISO 27001)** — audit
  kerentanan dependensi otomatis di CI (`pip-audit` + `npm audit` + Trivy
  scan image, A.8.8) + Dependabot mingguan + **Runbook Tanggap Insiden**
  (A.5.24–28, lihat `docs/internal/INCIDENT_RUNBOOK.md`); semua dependensi di-patch ke
  versi aman, image runtime dibersihkan dari tooling build
- 🗄️ **Retensi & Arsip (v2.34, Tahap 5/6 ISO 27001)** — kebijakan retensi
  per kelas dokumen (lihat `docs/internal/RETENTION_POLICY.md`), inventaris live lintas
  cabang, dan arsip audit trail ke tabel arsip (ISO 15489 · UU PDP)
- 🔏 **Integritas Dokumen (v2.35, Tahap 6/6 ISO 27001)** — setiap PDF resmi
  dicatat hash SHA-256 + penandatangan + waktu terbit; verifikasi keaslian
  dengan mengunggah PDF (A.8.2 · keaslian dokumen)

---

## 🧪 Pengujian

```bash
# Backend tests
python -m pytest tests/ -v

# Frontend tests
cd frontend && npm test
```

**Status:** 578 pytest (pass) + 8 skip + 141 vitest · Semua ✅ PASS + audit dependensi bersih (v2.39.2 — CI GitHub Actions: Backend pytest + pip-audit, Frontend unit test/build + npm audit, Image scan Trivy; hijau di tiap push)

---

## 🗺️ Peta Dokumentasi

Dokumentasi BPF WorkHub tersusun seperti rak buku — pilih lorong sesuai kebutuhanmu.

> **Baru di sini?** Mulai dari [Ringkasan Satu Halaman](docs/public/ONEPAGER.md) untuk gambaran
> besarnya, lalu buka [Panduan Pengguna](guides/USER_GUIDE.md) langsung ke bagian peranmu.

### 📖 Untuk Pengguna — belajar memakai sistem

| Dokumen | Isinya |
|---------|--------|
| [📖 Panduan Pengguna](guides/USER_GUIDE.md) | Langkah demi langkah tiap peran — ditulis tanpa istilah teknis |
| [🎯 Lembar Latihan per Peran](docs/public/PELATIHAN.md) | Latihan mandiri 5–10 menit per peran, cocok sebelum demo |
| [📋 Daftar User & Role](docs/internal/USER_LIST.md) | Semua role yang didukung + konvensi nama akun per cabang |

### 🎤 Untuk Presenter — memperkenalkan sistem

| Dokumen | Isinya |
|---------|--------|
| [🎤 Materi Presentasi](docs/public/PRESENTASI.md) | Skenario demo lengkap: poin bicara, tampilan layar, kalimat kunci |
| [📄 Ringkasan Satu Halaman](docs/public/ONEPAGER.md) | Ikhtisar sistem untuk dibagikan — pas di satu halaman |

### 🚀 Untuk IT — menjalankan sistem

| Dokumen | Isinya |
|---------|--------|
| [📘 Panduan Deployment](docs/internal/DEPLOYMENT.md) | Pasang, update, backup, HTTPS, troubleshooting |
| [🌱 Deploy dari Nol](docs/internal/DEPLOY_FRESH.md) | Panduan server kosong → aplikasi jalan |
| [🛡️ Keamanan & Standar](docs/internal/SECURITY.md) | Program ISO 27001 · ISO 9001: klausul & penerapannya |
| [🗄️ Kebijakan Retensi](docs/internal/RETENTION_POLICY.md) | Masa simpan & pemusnahan tiap kelas dokumen |
| [🚨 Runbook Tanggap Insiden](docs/internal/INCIDENT_RUNBOOK.md) | Langkah darurat saat kejadian keamanan |

### 🧭 Untuk Tim Pengembang — melacak perjalanan

| Dokumen | Isinya |
|---------|--------|
| [📋 Changelog](CHANGELOG.md) | Riwayat perubahan per versi — ditulis untuk manusia |
| [📈 Progress Tracker](docs/internal/PROGRESS.md) | Status roadmap, catatan sesi, rekomendasi berikutnya |
| [🤖 Komunikasi Ox Alpha](docs/internal/OXALPHA_COMMUNICATION.md) | Catatan integrasi LLM (OpenRouter) untuk asisten IT |

---

## 📞 Kontak

**PT. Bestprofit Futures — Kantor Pusat Jakarta**
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190
📞 031-5349888

---

*Dikembangkan dengan ❤️ oleh Tim IT BPF*
