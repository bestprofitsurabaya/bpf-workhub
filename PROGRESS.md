# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-08-24  
**Branch:** `main`  
**Versi terbaru:** v2.28.1

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | v2.28.1 (OT Form Multi-Modul + H+1 + Nama Filter) |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| App Running | `https://nasbpfsby.duckdns.org:5000` |
| Databases | 10 DB terpisah (1 master + 9 cabang) |
| GPS Detail | ✅ Nominatim reverse geocode + disimpan ke DB |
| Watermark | ✅ 4 baris: perusahaan + tanggal + alamat + koordinat |

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

### Security & Infrastructure
- [x] CSP connect-src — Nominatim diizinkan
- [x] Service Worker — fix redirect error
- [x] Nginx cache-busting
- [x] GPS detail disimpan ke DB

---

## 🔄 Yang Sedang Dikerjakan

- (kosong)

---

## 📋 Yang Belum Dikerjakan

### Fitur Baru
- [ ] Laporan otomatis mingguan via email
- [ ] Approval berjenjang (multi-level)
- [ ] Dashboard mobile khusus admin

---

## 🐛 Bug Terbuka

### Fixed
- ✅ GPS kecamatan kosong — municipality/district fallback
- ✅ GPS ReferenceError — variable addr undefined
- ✅ CSP blokir Nominatim
- ✅ Service Worker redirect error
- ✅ Photo upload 1 tombol → 2 tombol
- ✅ Watermark font terlalu besar

---

## 📝 Catatan untuk Sesi Berikutnya

> "Baca `PROGRESS.md` dan `CHANGELOG.md`, lalu lanjutkan."

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

*BPF WorkHub v2.28.0 · Progres Tracker*
