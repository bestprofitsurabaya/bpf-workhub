# 📋 Daftar User & Role — BPF WorkHub v2.40.0

Dokumen ini menjelaskan semua role yang didukung sistem, siapa yang memakainya, dan apa yang bisa dilakukan masing-masing.

> 🔒 **Catatan keamanan:** dokumen ini hanya memuat konvensi nama akun. PIN dan kredensial asli
> **tidak** dicantumkan di sini — tersimpan di password manager tim IT dan wajib diganti
> saat login pertama.

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

## 📋 Daftar Isi

1. [Akun Default (Seed Data)](#1-akun-default-seed-data)
2. [10 Role yang Didukung](#2-10-role-yang-didukung)
3. [Detail Akses per Role](#3-detail-akses-per-role)
4. [Ringkasan Akses](#4-ringkasan-akses)
5. [Keamanan Akun](#5-keamanan-akun)
6. [Catatan Penting](#6-catatan-penting)

---

## 1. Akun Default (Seed Data)

Akun berikut dibuat otomatis saat inisialisasi database:

| # | Username | Nama Lengkap | Role | PIN | Keterangan |
|---|----------|--------------|------|-----|------------|
| 1 | `admin_master` | Administrator Pusat | `admin` | `••••••` | Admin Pusat (semua cabang; flag `admin_all_branches=1`). Rename dari `admin`, 7 Sep 2026 |
| 2 | `ga_sby` | GA Officer | `ga` | `••••••` | General Affairs Officer (Surabaya) |
| 3 | `finance_sby` | Finance Officer | `finance` | `••••••` | Finance Officer (Surabaya) |

> ⚠️ **Segera ganti PIN bawaan** setelah login pertama kali. PIN bawaan tidak dicantumkan
> di dokumen ini — minta ke Admin IT / lihat password manager tim.

### 🏷️ Konvensi Username Per-Cabang

Setiap divisi back-office punya user unik per cabang dengan format `{divisi}_{kode_cabang}`:

| Divisi | SBY | HU (JKT) | JKT2 | BDG | SMG | MLG | MDN | BJM | PLM | LPG |
|--------|-----|----------|------|-----|-----|-----|-----|-----|-----|-----|
| GA | `ga_sby` | `ga_hu` | `ga_jkt2` | `ga_bdg` | `ga_smg` | `ga_mlg` | `ga_mdn` | `ga_bjm` | `ga_plm` | `ga_lpg` |
| Finance | `finance_sby` | `finance_hu` | `finance_jkt2` | `finance_bdg` | `finance_smg` | `finance_mlg` | `finance_mdn` | `finance_bjm` | `finance_plm` | `finance_lpg` |
| GA HR | `gahr_sby` | `gahr_hu` | `gahr_jkt2` | `gahr_bdg` | `gahr_smg` | `gahr_mlg` | `gahr_mdn` | `gahr_bjm` | `gahr_plm` | `gahr_lpg` |
| Marketing | `marketing_sby` | `marketing_hu` | `marketing_jkt2` | `marketing_bdg` | `marketing_smg` | `marketing_mlg` | `marketing_mdn` | `marketing_bjm` | `marketing_plm` | `marketing_lpg` |
| Security | `security_sby` | `security_hu` | `security_jkt2` | `security_bdg` | `security_smg` | `security_mlg` | `security_mdn` | `security_bjm` | `security_plm` | `security_lpg` |
| IT | `it_sby` | `it_hu` | `it_jkt2` | `it_bdg` | `it_smg` | `it_mlg` | `it_mdn` | `it_bjm` | `it_plm` | `it_lpg` |

> PIN default semua user: diatur saat pembuatan akun (tidak dicantumkan di dokumen ini). Role di DB tetap sama (misal `finance_sby` → role `finance`),
> hanya username yang unik. Label di UI otomatis menyesuaikan (Finance Surabaya, GA Bandung, dst).
>
### 🔑 Akun Admin per-Cabang (aktif sejak 7 Sep 2026)

| Username | Cabang | Role | PIN awal | DB |
|----------|--------|------|----------|-----|
| `admin_master` | Semua (Admin Pusat) | `admin` | `123456` | bpf_asset_system |
| `admin_jkt` | JKT | `admin` | `123456` | bpf_branch_jkt |
| `admin_sby` | SBY | `admin` | `123456` | bpf_asset_system |
| `admin_bdg` | BDG | `admin` | `123456` | bpf_branch_bdg |
| `admin_smg` | SMG | `admin` | `123456` | bpf_branch_smg |
| `admin_mlg` | MLG | `admin` | `123456` | bpf_branch_malang |
| `admin_mdn` | MDN | `admin` | `123456` | bpf_branch_mdn |
| `admin_bjm` | BJM | `admin` | `123456` | bpf_branch_bjm |
| `admin_plm` | PLM | `admin` | `123456` | bpf_branch_plm |
| `admin_lpg` | LPG | `admin` | `123456` | bpf_branch_lpg |
| `admin_jkt2` | JKT2 | `admin` | `123456` | bpf_branch_jkt2 |

> ⚠️ PIN awal `123456` sesuai konvensi akun IT cabang — wajib diganti saat login pertama.
> Akun test `e2e_admin_tmp` dinonaktifkan (7 Sep 2026).

> Bila **lebih dari satu orang** di divisi & cabang yang sama (mis. 3 OB Surabaya),
> username memakai nama: `ob_faisol_sby`, `ob_febri_sby`, `ob_edwin_sby` — bukan `ob1/ob2/ob3`.
> Khusus Driver: username = nama orang (`akhad`) — dipakai login PWA pendek di HP.

---

## 2. 11 Role yang Didukung

Sistem mendukung **11 peran inti** (peran `it` dipecah per cabang pada daftar di bawah):

| # | Role | Label | Halaman Utama | Keterangan |
|---|------|-------|---------------|------------|
| 1 | `admin` | 🔑 Admin | `/app/dashboard` | Akses penuh: manajemen user, settings, audit log, multi-cabang |
| 2 | `ga` | 🧾 GA Officer | `/app/ga` | Antrean klaim BBM, kasbon, trip, verifikasi anomali |
| 3 | `finance` | 💰 Finance | `/app/finance` | Rekap kasbon, cairkan dana, arsip transaksi |
| 4 | `marketing` | 📣 Marketing | `/app/marketing` | Buat & kelola appointment kunjungan nasabah |
| 5 | `chief_driver` | 🚛 Chief Driver | `/app/chief-driver` | Atur rute perjalanan driver (auto & manual) |
| 6 | `driver` | 🚗 Driver | `/app/driver` | PWA: submit trip, foto ODO/struk, GPS, notifikasi |
| 7 | `ob` | 🧹 OB | `/app/water` | Pengajuan pembelian air minum + **Overtime Saya** (v2.39) |
| 8 | `security` | 🛡️ Security | `/app/overtime-me` | **Overtime Saya** — pengajuan lembur Security (v2.39) |
| 9 | `receptionist` | 🪪 Receptionist | `/app/receptionist` | Verifikasi pelamar kerja & kehadiran |
| 10 | `traineer` | 🎯 Traineer | `/app/traineer` | Pantau rekrutan (read-only) |
| 11 | `ga_hr` | ⏰ GA HR | `/app/ga-hr` | Data overtime Driver & OB/Security |
| 11 | `it_sby` | 📰 IT Surabaya | `/app/it` | News Scraper (SBY) |
| 12 | `it_hu` | 📰 IT Jakarta HO | `/app/it` | News Scraper (JKT) — lihat semua site |
| 13 | `it_jkt2` | 📰 IT Jakarta 2 | `/app/it` | News Scraper (JKT2) |
| 14 | `it_bdg` | 📰 IT Bandung | `/app/it` | News Scraper (BDG) |
| 15 | `it_smg` | 📰 IT Semarang | `/app/it` | News Scraper (SMG) |
| 16 | `it_mlg` | 📰 IT Malang | `/app/it` | News Scraper (MLG) |
| 17 | `it_mdn` | 📰 IT Medan | `/app/it` | News Scraper (MDN) |
| 18 | `it_bjm` | 📰 IT Banjarmasin | `/app/it` | News Scraper (BJM) |
| 19 | `it_plm` | 📰 IT Palembang | `/app/it` | News Scraper (PLM) |
| 20 | `it_lpg` | 📰 IT Lampung | `/app/it` | News Scraper (LPG) |

---

## 3. Detail Akses per Role

### 🔑 Admin (`admin_master` / `admin_<cabang>`)

**Akses:** Semua halaman & API

**Dua tingkat (v2.37.0):**
- `admin_master` = **Admin Pusat** — semua cabang (flag `admin_all_branches=1`),
  bisa ganti cabang kerja, kelola cabang/user global, reset nomor dokumen,
  arsip audit, Access Review. Akun ini rename dari `admin` (7 Sep 2026) dan
  jadi backup bila admin cabang ada kendala.
- `admin_<kode>` (mis. `admin_sby`) = **Admin Cabang** — semua halaman admin
  tampil, tapi operasional terkunci ke cabangnya: tidak bisa ganti cabang,
  tidak bisa aksi lintas cabang (menu Access Review & Audit Log disembunyikan
  dari sidebar-nya).

**Fitur Khusus:**
- Manajemen User (`/app/users`) — CRUD, sync, bulk create, reset PIN
- Pengaturan (`/app/settings`) — identitas perusahaan, reset PIN massal driver,
  toggle edit/hapus transaksi air minum per cabang (v2.37.0)
- Audit Log (`/app/logs`) — semua aktivitas user tercatat (admin cabang:
  cabangnya saja)
- Multi-cabang (`/app/branches`)
- Seed & clean data demo

**Halaman Sidebar:**
- 📊 Dashboard Admin
- 🧾 Dashboard GA
- 💰 Dashboard Finance
- 🗺️ Log Perjalanan
- 🚗 Assignments
- 📋 Rekap
- 💵 Kasbon / BBM
- 📈 Analytics
- 🚛 Chief Driver
- 👥 Manajemen User
- ⚙️ Pengaturan
- 📝 Audit Log
- 🚰 Air Minum
- 🪪 Pelamar Kerja
- 🔧 Aset & Pemeliharaan
- ⏰ GA HR

---

### 🧾 GA Officer (`ga`)

**Akses:** Back-office penuh (hampir sama dengan Admin, kecuali User Management & Settings)

**Dashboard GA** (`/app/ga`):
- 🕐 Antrean klaim BBM — approve, verifikasi anomali ML, tolak
- 💵 Kasbon menunggu approve
- 🗺️ Laporan perjalanan menunggu review
- 🚰 Pengajuan air minum (ringkasan)
- ⚡ Quick links ke Assignments, Kasbon, Air Minum, Analytics

**Dashboard Admin** (`/app/dashboard`) — juga bisa diakses GA:
- 📊 Stat cards: Antrean GA (pending), Verified GA, Terarsip, Transaksi Hari Ini
- 🕐 Antrean Kerja tab GA — approve, verifikasi, tolak, detail
- 🔎 Verifikasi Mendalam — foto bukti, cross-check (health score, flag, budget)
- ✏️ Edit data transaksi (kendaraan/BBM/nominal/ODO/SPBU)
- ↩️ Unverify transaksi
- 🗑 Hapus transaksi (hanya admin)
- ⚡ Aksi Cepat: Log Perjalanan, Assignments, Kasbon, Analytics

**Halaman Sidebar:**
- 🧾 Dashboard GA
- 🗺️ Log Perjalanan
- 🚗 Assignments
- 💵 Kasbon / BBM
- 📈 Analytics
- 🚛 Chief Driver
- 🔧 Aset & Pemeliharaan

**API Endpoint:**
- `POST /api/queue/approve-ga/<id>` — approve klaim BBM
- `POST /api/queue/verify/<id>` — verifikasi anomali ML
- `POST /api/queue/reject/<id>` — tolak klaim
- `POST /api/queue/modify/<id>` — edit data transaksi
- `POST /api/queue/unverify/<id>` — kembalikan ke antrean GA
- `GET /api/queue?tab=ga` — ambil antrean GA
- `POST /api/drivers/sync` — sinkronisasi driver
- `POST /api/vehicles/add` — tambah kendaraan
- `POST /api/assignments/*` — manajemen assignment kendaraan
- `GET /api/assets/*` — aset & pemeliharaan
- `GET /api/cross-check/<id>` — cross-check transaksi
- `GET /api/stats` — statistik dashboard

---

### 💰 Finance (`finance`)

**Akses:** Finance penuh + water (air minum) + kasbon + rekap

**Dashboard Finance** (`/app/finance`):
- 🚰 Rekap air minum — statistik total, menunggu verifikasi, terverifikasi, ditolak
- 💵 Kasbon menunggu approve
- 🧾 LPJ menunggu approve
- 👥 Ringkasan per OB (total, pending, verified, rejected)
- 🥤 Per Jenis & 🏷️ Per Merk air minum
- ⬇️ Export CSV

**Dashboard Admin** (`/app/dashboard`) — juga bisa diakses Finance:
- 📊 Stat cards: Menunggu Finance (os_finance), Terarsip, Transaksi Hari Ini, Nominal Hari Ini
- 💵 Antrean Kerja tab Finance — payout (💰)
- 🤝 Antrean Kerja tab Konfirmasi Driver — arsipkan (📦)
- 🔎 Verifikasi Mendalam — foto bukti, cross-check
- ⚡ Aksi Cepat: Log Perjalanan, Rekap, Analytics

**Halaman Sidebar:**
- 💰 Dashboard Finance
- 🗺️ Log Perjalanan
- 📋 Rekap
- 💵 Kasbon / BBM
- 📈 Analytics
- 🚰 Air Minum

**API Endpoint:**
- `POST /api/queue/payout/<id>` — cairkan dana
- `POST /api/queue/archive/<id>` — arsipkan transaksi
- `GET /api/queue?tab=finance` — ambil antrean finance
- `GET /api/queue?tab=driver_confirm` — ambil konfirmasi driver
- `GET /api/water/recap` — rekap air minum
- `POST /api/water/verify/<id>` — verifikasi air minum
- `GET /api/rekap/*` — rekap transaksi
- `GET /api/cash/history` — riwayat kasbon
- `GET /api/stats` — statistik dashboard

---

### 📣 Marketing (`marketing`)

**Akses:** Appointment & kunjungan nasabah

**Fitur Khusus:**
- Buat appointment kunjungan
- Lihat status kunjungan
- Kelola data nasabah

**Halaman:** Marketing Hub (`/app/marketing`)

---

### 🚛 Chief Driver (`chief_driver`)

**Akses:** Rute perjalanan driver

**Fitur Khusus:**
- Optimasi rute otomatis
- Atur rute manual (tentukan driver + urutan kunjungan)
- Assign driver ke appointment

**Halaman:** Chief Driver Dashboard (`/app/chief-driver`)

---

### 🚗 Driver (`driver`)

**Akses:** PWA driver (mobile-first)

**Fitur Khusus:**
- Submit trip (foto ODO, foto struk, GPS)
- Lihat profil kendaraan & BBM
- Notifikasi real-time
- Multi-rute array
- Enqueue & sync data offline

**Halaman:** Driver PWA (`/app/driver`)

**Tab:**
- ⛽ BBM — klaim pembelian BBM
- 💰 Kasbon — ajukan uang muka
- 🗺️ Trip — log perjalanan
- 📊 Rapor — performa kendaraan

---

### 🧹 OB (`ob`)

**Akses:** Pengajuan air minum + overtime sendiri

**Fitur Khusus:**
- Buat pengajuan pembelian air minum
- Upload foto before/after
- Lihat status pengajuan
- **Overtime Saya (v2.39)** — isi lembur dari dalam aplikasi; Nama & Posisi
  otomatis dari akun (tidak bisa dipilih), riwayat pribadi di halaman yang sama

**Halaman:** Air Minum (`/app/water`) · Overtime Saya (`/app/overtime-me`)

---

### 🛡️ Security (`security`) — v2.39

**Akses:** Overtime sendiri

**Fitur Khusus:**
- **Overtime Saya** (`/app/overtime-me`) — form pengajuan lembur Security:
  Tanggal, Waktu Mulai, Waktu Selesai, Keterangan + foto bukti (watermark) &
  GPS — kolom sama dengan sheet sumber overtime OB/Security
- Nama & Posisi (`Security`) terkunci dari sesi login — tidak bisa dipalsukan
- Riwayat overtime pribadi (terbaru di atas)
- Pengajuan mengikuti ACC berjenjang: GA HR → Admin

**Konvensi username:** `security_<cabang>` (satu orang) /
`security_<nama>_<cabang>` (bila >1 orang per cabang) — contoh:
`security_sby`, `security_budi_sby`. Wajib mengisi kolom **Cabang** saat
membuat akun.

**Halaman:** Overtime Saya (`/app/overtime-me`)

---

### 🪪 Receptionist (`receptionist`)

**Akses:** Sistem pelamar kerja

**Fitur Khusus:**
- Verifikasi pelamar
- Update status tahapan interview/training
- Kelola kehadiran
- Kelola dropdown User

**Halaman:** Receptionist Dashboard (`/app/receptionist`)

---

### 🎯 Traineer (`traineer`)

**Akses:** Pantau rekrutan (read-only)

**Fitur Khusus:**
- Lihat orang yang direkrut (scope: upline sendiri)
- Filter tanggal, search, chip kehadiran
- Tanpa akses edit/PDF

**Halaman:** Traineer Dashboard (`/app/traineer`)

---

### ⏰ GA HR (`ga_hr`)

**Akses:** Data overtime

**Fitur Khusus:**
- Dashboard statistik overtime
- Data Driver (±8.675 sesi dari Google Sheet via Apps Script) & OB/Security (599 sesi dari sheet)
- Auto-refresh saat login/logout
- Refresh dari Google Sheet (Driver & OB/Security)
- Detail Report per nama (PDF/Excel) — Driver & OB/Security
- Config sumber data terpisah (Driver + OB/Security)
- CRUD overtime (edit, delete)
- PDF laporan overtime
- Foto OT auto-cleanup > 6 bulan (cron + manual API)

**Halaman:** GA HR Dashboard (`/app/ga-hr`)

---

### 📰 IT (Semua Cabang) — News Scraper

**Roles:** `it_sby`, `it_hu`, `it_jkt2`, `it_bdg`, `it_smg`, `it_mlg`, `it_mdn`, `it_bjm`, `it_plm`, `it_lpg`

**Akses:** News Scraper & Content Management (`/app/it`)

**Fitur Khusus:**
- Scrape artikel dari newsmaker.id (commodity page, ~16/halaman) + Detik Finance (~48/halaman)
- Multi-WordPress site management (10 cabang, CRUD, test connection)
- Upload artikel ke WordPress dengan SEO optimization
- Upload gambar (featured image + inline)
- Financial Authority Backlinks otomatis (24+ situs otoritas)
- SEO Backlinks ke situs BPF (5 target sites + CTA widget)
- 7 Algoritma SEO (content uniqueness, multi-source, internal linking, schema, sitemap ping, scheduling, analytics)
- Duplicate prevention (500 posts + fuzzy title match)
- Progress tracking + upload history
- Duplicate article checker + delete
- Activity log
- **Access filtering**: user hanya lihat site cabang sendiri
- **it_hu** (HO) bisa lihat semua site
- **Tab Report**: detail per-artikel + filter + export CSV
- **Configurable daily limit** (1-100/hari dari UI)
- **Password toggle** 👁/🙈 di site card & form
- **User-friendly error messages** (DNS/SSL/Timeout)

**Halaman:** News Scraper (`/app/it`)

**API Endpoint:**
- `GET /api/scraper/sites` — list WordPress sites (filtered by branch)
- `POST /api/scraper/sites` — tambah/edit site
- `DELETE /api/scraper/sites/<name>` — hapus site
- `POST /api/scraper/test-connection` — test koneksi WP
- `POST /api/scraper/check` — scrape artikel
- `POST /api/scraper/upload` — upload ke WordPress
- `POST /api/scraper/duplicates` — cek duplikat
- `POST /api/scraper/duplicates/delete` — hapus duplikat
- `GET /api/scraper/backlinks` — config backlinks
- `POST /api/scraper/backlinks` — simpan config
- `POST /api/scraper/backlinks/add-keyword` — tambah keyword mapping
- `GET /api/scraper/hyperlinks` — list hyperlinks
- `POST /api/scraper/hyperlinks` — simpan hyperlinks
- `GET /api/scraper/log` — activity log
- `GET /api/scraper/schedule` — optimal publish schedule
- `GET /api/scraper/analytics` — performance analytics
- `GET /api/scraper/report` — upload report per-article
- `GET /api/scraper/report/export` — export CSV
- `GET /api/scraper/settings` — ambil settings
- `POST /api/scraper/settings` — simpan settings

---

## 4. Ringkasan Akses

| Menu | Admin | GA | Finance | Marketing | Chief Driver | Driver | OB | Security | Receptionist | Traineer | GA HR | IT |
|------|:-----:|:--:|:-------:|:---------:|:------------:|:------:|:--:|:--------:|:------------:|:--------:|:----:|:--:|
| Dashboard Admin | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dashboard GA | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dashboard Finance | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Log Perjalanan | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Assignments | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Rekap | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Kasbon / BBM | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Analytics | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Marketing Hub | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Chief Driver | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manajemen User | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Pengaturan | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Audit Log | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Air Minum | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Overtime Saya (v2.39) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Pelamar Kerja | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Aset & Pemeliharaan | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| GA HR (Overtime) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| News Scraper | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 5. Keamanan Akun

| Aspek | Keterangan |
|-------|------------|
| Metode Login | Username + PIN 6 digit |
| Rate Limiting | Anti brute-force (terlalu banyak percobaan → blokir sementara) |
| CSRF Protection | Aktif untuk semua POST/PUT/DELETE/PATCH |
| Session | HTTP-only cookie, SameSite=Lax, Secure (HTTPS) |
| Step-up Auth | Aksi uang wajib konfirmasi PIN ulang (grant 10 menit, hilang saat logout) |
| PIN Default | Diatur Admin saat pembuatan akun — tidak dicantumkan di dokumen |
| Reset PIN | Hanya admin yang bisa reset PIN user lain |
| Audit Trail | Semua aktivitas login, sync, delete tercatat di `activity_logs` |
| Branch Code | Multi-cabang: user dikaitkan dengan cabang tertentu |
| Access Review | Review hak akses triwulanan (Jan/Apr/Jul/Okt) — akun tanpa login > 90 hari diklasifikasi "basi" & bisa dinonaktifkan Admin |
| ACC Berjenjang (v2.36.0) | Pengajuan wajib ACC atasan dulu: kasbon & klaim BBM → Chief Driver lalu GA; overtime → GA HR lalu Admin. Admin bisa mengatur atasan khusus per user (kolom "Atasan" di Manajemen User); pengaju tidak bisa memutus pengajuannya sendiri; penolakan wajib alasan & tercatat di audit log |
| Admin per-cabang (v2.37.0) | `admin_master` = Admin Pusat (flag `admin_all_branches=1`); `admin_<kode>` = Admin cabang (terkunci ke cabangnya). 1 admin utk 2 cabang: `users.managed_branches` = `SBY,BDG`. Promosi ke pusat: `users.admin_all_branches = 1`. Aksi lintas cabang (switch, docseq cabang lain, arsip audit, access review) ditolak 403 bagi admin cabang |
| Edit/hapus air minum (v2.37.0) | Fitur opsional per cabang (`system_config.water_edit_enabled`, default nonaktif). Aktif → Finance edit (pending/verified) & hapus permanen pengajuan; keduanya wajib step-up PIN + snapshot data lama tersimpan di audit log |

---

## 6. Catatan Penting

1. **PIN Default**: Semua user baru (termasuk bulk create driver/marketing) memakai PIN default yang ditetapkan Admin saat pembuatan akun.
2. **Bulk Create**: Admin bisa membuat akun massal untuk driver aktif dan anggota marketing via `/api/users/bulk-create`.
3. **Bulk Reset PIN**: Admin bisa reset PIN massal semua driver via tombol di Settings.
4. **Role Hierarchy**: Admin > GA/Finance > Marketing/Chief Driver > Driver/OB/Security > Receptionist/Traineer/GA HR.
5. **Data Tersimpan di DB Master**: Seluruh data user tersimpan di database master (bukan DB cabang).

---

## 🔄 Endpoint Klasik yang Dipensiunkan (v2.5)

Pada migrasi v2.5, seluruh antarmuka klasik (Jinja/HTML) dihapus dari repo dan digantikan SPA Vue 3. Endpoint klasik hanya tersisa untuk redirect kompatibilitas.

### Endpoint yang MASIH ADA (hanya redirect)

| Endpoint | Fungsi |
|----------|--------|
| `GET /admin` | Redirect ke `/app/dashboard` |
| `GET /admin/trips` | Redirect ke `/app/trips` |
| `GET /ga/assignments` | Redirect ke `/app/assignments` |
| `GET /marketing` | Redirect ke `/app/marketing` |
| `GET /chief-driver` | Redirect ke `/app/chief-driver` |
| `GET /login` | Redirect ke `/app/login` |
| `GET /logout` | Clear session → redirect `/app/login` |

### Fitur yang TIDAK BERUBAR (tetap tersedia di SPA)

- ✅ Approve/Reject klaim BBM (GA/Admin)
- ✅ Payout/Archive transaksi (Finance/Admin)
- ✅ Verifikasi anomali ML (GA/Admin)
- ✅ Edit data transaksi (GA/Admin)
- ✅ Unverify transaksi (GA/Admin)
- ✅ Hapus transaksi (Admin only)
- ✅ Rekap transaksi (Finance/Admin)
- ✅ Analytics (GA/Finance/Admin)
- ✅ Kasbon/Cash (GA/Finance/Admin)
- ✅ Log Perjalanan/Trips (GA/Finance/Admin)
- ✅ Assignments kendaraan (GA/Admin)
- ✅ Export logsheet Excel/PDF (GA/Finance/Admin)

### Fitur BARU di SPA (tidak ada di klasik)

- 🆕 Cross-check transaksi (health score, flag, budget, selisih ODO)
- 🆕 Modal detail transaksi dengan foto bukti inline
- 🆕 Realtime refresh antrean (event `new_claim`)
- 🆕 Export antrean ke Excel
- 🆕 Dark mode & high contrast mode
- 🆕 Accessibility (focus trap, aria, keyboard navigation)
- 🆕 Verifikasi anomali dengan foto MyPertamina opsional
- 🆕 Multi-cabang: ringkasan cabang, PDF konsolidasi, Excel konsolidasi

---

## 📞 Kontak

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

*BPF WorkHub v1.0 · Daftar User & Role*
