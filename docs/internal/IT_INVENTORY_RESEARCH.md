# Riset & Desain — Modul Inventaris IT di BPF WorkHub

Tanggal: 2026-11-10 · Status: riset (belum diimplementasikan)
Penulis: sesi riset IT · Basis kode: `bpf-workhub` v2.77.0 (NAS, `/home/it-ef/bpf-workhub`)

---

## 0. Ringkasan eksekutif

Kebutuhan nyata bukan "scanner jaringan", melainkan **sistem inventaris aset IT**
yang:

1. mencatat **semua** perangkat — termasuk yang tidak pernah/tidak sedang di jaringan
   (monitor, UPS, printer mati, kabel, lisensi, stok cadangan);
2. punya **prosedur pelabelan** yang menghasilkan tag + QR dan tercatat;
3. memungkinkan **update kondisi** dalam hitungan detik (scan QR → ubah kondisi);
4. **menemukan otomatis** perangkat di jaringan sebagai *kandidat*, dengan
   klasifikasi cerdas, tetapi **tidak pernah auto-commit** tanpa persetujuan IT;
5. bisa **ditambah manual** dan **impor massal**.

Kesimpulan riset: **layak dan cocok** dengan arsitektur yang ada. Tidak perlu
aplikasi baru — cukup satu modul di BPF WorkHub yang mengikuti pola
`register_*_routes(app)` + `ensure_*_schema()` + Vue view, memakai ulang
komponen UI, `save_file()` untuk foto, dan `fpdf2` untuk PDF label.

Yang sudah saya buktikan langsung di server:

| Uji | Hasil |
|---|---|
| Login `it_sby` / PIN yang diberikan | **valid** (hash scrypt, verifikasi Python lolos) |
| Peta cabang→DB | `SBY → bpf_asset_system` (master), 11 cabang lain `bpf_branch_*` |
| Sapuan TCP dari NAS ke LAN | **13 host hidup** di `192.168.2.0/24` dalam ±20 detik, tanpa root |
| MAC dari `/proc/net/arp` | terbaca tanpa sudo |
| Lookup vendor OUI | `28:D0:F5 → Ruijie Networks`, `38:68:A4 → Samsung`, `90:2B:34 → Gigabyte` |
| PDF label QR (fpdf2 + segno) | **berhasil** — 24 label A4 (3×8), QR + tag + nama |
| MikroTik API/SSH/SNMP | **tertutup** (hanya 80/443); REST tidak ada (RouterOS 6) |
| Role/nav IT saat ini | `it_sby…it_lpg` → `/app/it` (News Scraper), Transcoder, PDF Kit |

---

## 1. Temuan codebase (yang relevan untuk fitur ini)

### 1.1 Pola modul backend
- Semua modul mendaftar lewat fungsi `register_xxx_routes(app)` di `app.py`
  (bukan Flask Blueprint), route `@app.route('/api/...')` + `@role_required([...])`.
- Koneksi: `get_db_connection()` (DB cabang sesi) dan `get_master_connection()`
  (users/branches). Cabang SBY sengaja memakai DB master.
- Audit: `log_activity_async(user, action, detail)` dipanggil di aksi tulis.
- Skema: tidak ada folder migrasi; cukup `ensure_*_schema()` idempoten yang
  dipanggil saat startup (pola `modules/overtime_schema.py`), plus seed di
  `init.sql` agar fresh deploy tidak 500.
- Upload foto: `save_file(request.files.get(...), prefix, name, app.config['UPLOAD_FOLDER'])`
  → volume `/srv/bpf-workhub/uploads` (1,7 TB).
- Ekspor/PDF: `modules/pdf_generator.py` (fpdf2), `excel_generator.py` (openpyxl).

### 1.2 Frontend
- Vue 3 + Vite, router dengan `meta.roles`, guard di `router/index.js`.
- Menu sidebar didefinisikan manual di `layouts/AppLayout.vue` (grup
  **"Perkakas IT"**), badge angka lewat `/api/nav/badges`.
- Komponen siap pakai: `PageHeader`, `StatCard`, `Modal`, `ConfirmDialog`,
  `StepUpModal`, `EmptyState`, `ErrorState`, `LoadingState`, `ToastStack`,
  `OnboardingTour`, `HelpCenter`.
- Gaya: CSS variable di `styles/main.css` (`--primary`, `--surface`, `--radius`,
  dark mode), kelas `.card`, `.btn`, `.input`, `.field`.
- `api()` helper menangani CSRF, retry, dan normalisasi error.
- Halaman `ItEfView.vue` (News Scraper) adalah contoh "app dalam app": header,
  tab-nav, stat cards, progress. Pola ini bisa ditiru untuk halaman inventaris.

### 1.3 Otorisasi & cabang
- Role IT per cabang: `it_sby`, `it_hu`, `it_jkt2`, `it_bdg`, `it_smg`, `it_mlg`,
  `it_mdn`, `it_bjm`, `it_plm`, `it_lpg`; plus `admin`.
- `ROLE_META` (`stores/auth.js`) menentukan halaman muka tiap role — saat ini
  semua IT diarahkan ke `/it` (News Scraper).
- Scoping cabang memakai `session['branch_code']`; admin pusat bisa lintas
  cabang (`admin_scope.py`). Modul baru **wajib** memfilter `branch_code` agar
  IT Surabaya tidak melihat/mengubah aset cabang lain.

### 1.4 Modul aset yang sudah ada — dan mengapa belum cocok
`modules/routes_assets.py` (role `ga`, `admin`) hanya mencakup:
- 15 unit AC kantor + log servis (parameter teknikal, health score),
- 8 kendaraan + komponen + rekomendasi servis berbasis aturan.

Tidak ada: aset IT, nomor inventaris/tag, QR, lokasi ruangan, PIC, garansi,
riwayat kondisi, penemuan jaringan. **Jangan memperluas modul GA** — buat modul
IT terpisah agar hak akses dan UI tidak tercampur.

---

## 2. Kebutuhan (jobs to be done)

| # | Siapa | Kebutuhan | Ukuran sukses |
|---|---|---|---|
| 1 | IT cabang | Mendata perangkat baru (beli, pindahan, hibah) | < 60 detik per aset |
| 2 | IT cabang | Menemukan perangkat yang belum tercatat | daftar kandidat harian |
| 3 | IT cabang | Menempel label resmi | 1 lembar A4 = 24 label, QR teruji |
| 4 | IT cabang | Update kondisi setelah servis/kerusakan | scan → 3 tap → tersimpan |
| 5 | IT cabang | Stok opname per ruangan | scan sesi, laporan found/missing |
| 6 | IT Head Office | Melihat rekap semua cabang | dashboard lintas cabang |
| 7 | Auditor | Riwayat perubahan (siapa, kapan, apa) | timeline immutable |
| 8 | IT cabang | Pindah lokasi/PIC perangkat | tercatat di riwayat |
| 9 | IT cabang | Garansi hampir habis | pengingat 30/7 hari |
| 10 | IT cabang | Perangkat mati/punah | status `disposed` + alasan |

Non-fungsional: tetap jalan saat jaringan ribut (PWA/offline queue),
tidak butuh kredensial Domain Admin untuk fungsi inti, semua aksi tercatat.

---

## 3. Riset sumber penemuan perangkat (discovery)

### 3.1 Perbandingan sumber

| Sumber | Yang didapat | Cakupan | Biaya | Catatan |
|---|---|---|---|---|
| **Sapuan TCP + ARP dari NAS (host)** | IP, MAC, port terbuka, PTR | Semua yang hidup di subnet | Nol (tanpa root, sudah terbukti) | Butuh skrip di host/agent; Docker bridge tidak melihat ARP LAN |
| **MikroTik DHCP lease + ARP (API/SNMP)** | IP, MAC, **hostname**, lease aktif, WiFi client | Semua klien DHCP | Perlu aktifkan API 8728/SNMP 161 (sekarang tertutup) | Kualitas nama terbaik; RouterOS 6 tanpa REST |
| **Agen Windows (WMI)** | Hardware, OS, software, serial | Hanya PC yang RPC-nya terbuka | Kredensial + buka WMI | Terbukti hanya 4/16 PC bisa dibaca |
| **AD LDAP** | Nama, OS, lastLogon, status disabled | PC domain-join | Kredensial baca AD | 218 komputer, tanpa metadata cabang |
| **DNS/PTR** | Nama host | Semua yang punya PTR | Nol | Sering stale (3 record salah di Surabaya) |

**Rekomendasi:** rantai bertingkat — *ARP/sweep* (selalu jalan) → *MikroTik*
(bila API diaktifkan) → *AD/DNS* (pengayaan nama) → *agen WMI* (opsional, data
dalam). Setiap sumber menyumbang bukti; klasifikasi memakai gabungannya.

### 3.2 Klasifikasi cerdas (rule engine, bukan ML)

Alasan memilih aturan: bisa dijelaskan ke auditor, deterministik, tidak butuh
data latih, dan mudah diperbaiki IT sendiri.

Contoh aturan (bukti → kategori → bobot):

| Bukti | Kategori | Bobot |
|---|---|---|
| port 135 + 445 + OUI motherboard | PC/Workstation | 0.55 |
| hostname cocok `-(EF|EI|EJ|…)` + OS Windows di AD | PC cabang | +0.25 |
| port 9100 atau 631 | Printer | 0.90 |
| OUI Ruijie/Huawei/Ubiquiti/Cisco/Tp-Link + 80/443 | AP/Switch | 0.75 |
| port 53 + IP = default gateway | Router | 0.95 |
| port 554/8000 + OUI Hikvision/Dahua | CCTV | 0.85 |
| OUI Apple/Samsung/Xiaomi + MAC acak | *bukan aset* (kandidat diabaikan) | — |
| port 22 + hostname `nas` | Server/NAS | 0.80 |

Skor ≥ 0.75 → kategori disarankan; 0.5–0.75 → "perlu verifikasi"; < 0.5 →
"tidak dikenal". Setiap kandidat menyimpan **daftar alasan** (mis.
`["port 445", "OUI Gigabyte", "hostname FTP-EF"]`) agar IT bisa menilai.
Keputusan IT (`adopt` / `ignore`) disimpan dan dipakai menaikkan bobot aturan
yang terbukti benar (umpan balik sederhana, tanpa ML).

Deduplikasi: **MAC** sebagai kunci utama, fallback `IP+hostname`. Perangkat
yang sudah di-*adopt* tidak muncul lagi sebagai kandidat.

### 3.3 Tool yang dipakai

| Kebutuhan | Pilihan | Alasan |
|---|---|---|
| Sapuan port | Python stdlib (`socket.connect_ex` + ThreadPool) | tanpa dependensi, tanpa root, sudah diuji |
| MAC lokal | `/proc/net/arp` | terbaca tanpa sudo |
| Vendor OUI | `netaddr` (bundled IEEE) **atau** CSV `manuf` Wireshark | offline, tidak butuh API pihak ketiga |
| MikroTik (opsional) | `librouteros` (API 8728) | DHCP lease + ARP + nama |
| Agen dalam (opsional) | `inventory-surabaya.ps1` yang sudah ada → POST JSON | sudah terbukti, tanpa tool baru |
| QR | `segno` (≈50 KB, murni Python) | spike PDF berhasil bersama fpdf2 |
| Label PDF | `fpdf2` (sudah dipakai) | konsisten dengan PDF resmi BPF |
| Scanner QR di HP | `BarcodeDetector` (Chrome Android) + fallback `jsQR` (di-vendor) | tanpa app tambahan, jalan di PWA |
| Foto kondisi | `save_file()` + volume uploads | pola yang sudah ada |

> Catatan: `nmap`/`arp-scan`/`snmpwalk` **tidak terpasang** di NAS dan tidak
> perlu — pendekatan Python murni cukup untuk kebutuhan ini.

---

## 4. Desain solusi

### 4.1 Skema data (usulan)

```sql
-- Master aset IT (satu tabel, branch-scoped)
CREATE TABLE it_assets (
  id INT AUTO_INCREMENT PRIMARY KEY,
  asset_tag VARCHAR(40) NOT NULL UNIQUE,      -- SBY-IT-PC-0001
  branch_code VARCHAR(10) NOT NULL,
  category VARCHAR(30) NOT NULL,              -- pc/laptop/monitor/printer/...
  brand VARCHAR(60) DEFAULT '',
  model VARCHAR(80) DEFAULT '',
  serial_number VARCHAR(80) DEFAULT '',
  status ENUM('stok','aktif','dipinjam','service','rusak','hilang','disposed')
         DEFAULT 'aktif',
  cond ENUM('baik','rusak_ringan','rusak_berat') DEFAULT 'baik',
  location_room VARCHAR(80) DEFAULT '',       -- "Lantai 2 - Trading"
  location_detail VARCHAR(120) DEFAULT '',    -- "Meja TRD02"
  assigned_to VARCHAR(100) DEFAULT '',        -- PIC/pemakai
  purchase_date DATE NULL,
  purchase_price DECIMAL(14,2) NULL,
  vendor VARCHAR(100) DEFAULT '',
  warranty_until DATE NULL,
  hostname VARCHAR(80) DEFAULT '',
  ip_address VARCHAR(45) DEFAULT '',
  mac_address VARCHAR(20) DEFAULT '',
  os_name VARCHAR(80) DEFAULT '',
  specs JSON NULL,                            -- CPU/RAM/disk dsb.
  notes TEXT NULL,
  source ENUM('manual','import','discovery') DEFAULT 'manual',
  discovery_id INT NULL,
  label_printed_at DATETIME NULL,
  last_seen_at DATETIME NULL,
  created_by VARCHAR(50) DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_it_branch (branch_code, status),
  KEY idx_it_cat (category),
  KEY idx_it_mac (mac_address),
  KEY idx_it_warranty (warranty_until)
);

-- Riwayat (append-only) — sumber timeline & audit
CREATE TABLE it_asset_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id INT NOT NULL,
  kind VARCHAR(30) NOT NULL,   -- created|condition|status|location|pic|label|scan|import|dispose
  before_json JSON NULL,
  after_json JSON NULL,
  note VARCHAR(500) DEFAULT '',
  photo_path VARCHAR(255) DEFAULT '',
  actor VARCHAR(50) DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  KEY idx_ev_asset (asset_id, created_at)
);

-- Kandidat hasil penemuan (staging, tidak pernah langsung jadi aset)
CREATE TABLE it_discovery_runs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  branch_code VARCHAR(10) NOT NULL,
  method VARCHAR(30) NOT NULL,      -- sweep|mikrotik|agent|mixed
  subnet VARCHAR(40) DEFAULT '',
  started_at DATETIME NULL, finished_at DATETIME NULL,
  found INT DEFAULT 0, new_count INT DEFAULT 0,
  status ENUM('running','ok','error') DEFAULT 'running',
  error VARCHAR(500) DEFAULT ''
);

CREATE TABLE it_discovered_devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  run_id INT NOT NULL,
  branch_code VARCHAR(10) NOT NULL,
  ip VARCHAR(45) DEFAULT '', mac VARCHAR(20) DEFAULT '',
  hostname VARCHAR(120) DEFAULT '', vendor VARCHAR(80) DEFAULT '',
  open_ports VARCHAR(120) DEFAULT '',
  category_suggest VARCHAR(30) DEFAULT '',
  confidence DECIMAL(4,2) DEFAULT 0,
  reasons JSON NULL,
  state ENUM('new','ignored','adopted') DEFAULT 'new',
  asset_id INT NULL,
  first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_mac (branch_code, mac),
  KEY idx_state (state)
);

-- Sesi stok opname (fase lanjut)
CREATE TABLE it_stocktake_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  branch_code VARCHAR(10) NOT NULL,
  location_room VARCHAR(80) DEFAULT '',
  started_by VARCHAR(50) DEFAULT '',
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME NULL,
  total_expected INT DEFAULT 0, total_found INT DEFAULT 0
);
CREATE TABLE it_stocktake_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_id INT NOT NULL, asset_id INT NOT NULL,
  scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  result ENUM('found','missing','moved') DEFAULT 'found',
  UNIQUE KEY uniq_scan (session_id, asset_id)
);
```

`specs JSON` dipakai untuk data hasil agen (CPU, RAM, disk) tanpa membanjiri
kolom. Semua tabel `utf8mb4`, pola timestamp mengikuti `asset_ac`.

### 4.2 API (usulan)

```
GET    /api/it/summary                       kartu dashboard
GET    /api/it/assets                        daftar + filter + paging
POST   /api/it/assets                         tambah manual
GET    /api/it/assets/<tag>                   detail + riwayat
PATCH  /api/it/assets/<tag>                   ubah data
POST   /api/it/assets/<tag>/condition         ubah kondisi (+foto/catatan)
POST   /api/it/assets/<tag>/events            catatan/servis/penugasan
POST   /api/it/assets/import                  CSV/XLSX (dry-run & commit)
GET    /api/it/assets/export.csv              ekspor
POST   /api/it/assets/labels.pdf              PDF label (tag[], layout)
GET    /api/it/assets/lookup?tag=...          untuk scan
GET    /api/it/discovery/candidates           kandidat + filter
POST   /api/it/discovery/scan                 trigger (async, 1 run)
POST   /api/it/discovery/candidates/<id>/adopt
POST   /api/it/discovery/candidates/<id>/ignore
POST   /api/it/discovery/agent                push dari host agent (token)
GET    /api/it/reports/warranty                garansi < 30 hari
```

Semua route `@role_required(IT_ROLES + ['admin'])` dan memfilter
`branch_code` dari sesi (kecuali admin pusat).

### 4.3 UI/UX untuk user IT

Menu baru di grup **"Perkakas IT"**: `📦 Inventaris IT` → `/it/inventory`.
Halaman satu aplikasi dengan tab (mengikuti pola `ItEfView.vue`):

1. **Dashboard** — kartu: total aset, aktif, rusak/service, belum berlabel,
   kandidat baru, garansi < 30 hari. Aksi cepat: `+ Tambah`, `Cetak Label`,
   `Scan`, `Pindai Jaringan`.
2. **Aset** — tabel dengan filter kategori/status/kondisi/ruangan/cabang,
   pencarian, pilih massal → cetak label / ekspor / ubah kondisi.
3. **Detail** — identitas, QR, tombol kondisi besar (Baik / Rusak Ringan /
   Rusak Berat), lokasi & PIC, timeline riwayat, foto, cetak ulang label.
4. **Tambah** — wizard 3 langkah (Kategori → Identitas → Penempatan/garansi),
   tag otomatis, opsi "hubungkan ke perangkat terdeteksi".
5. **Jaringan** — daftar kandidat dengan badge keyakinan + alasan
   (`port 445`, `OUI Gigabyte`, `hostname FTP-EF`), tombol **Jadikan Aset** /
   **Abaikan**; filter "baru hari ini".
6. **Label** — pilih aset → pilih layout (A4 3×8, A4 2×8, mini 30×15 mm) →
   pratinjau → unduh PDF. Riwayat cetak tercatat.
7. **Scan** (mobile-first, `/it/scan`) — kamera QR → buka detail → ubah kondisi
   dalam 3 tap; fallback input tag manual; antrean offline.
8. **Stok Opname** — mulai sesi per ruangan → scan → ringkasan ditemukan/hilang.

Detail kecil yang penting:
- Bahasa Indonesia, label tombol kerja ("Jadikan Aset", bukan "Adopt").
- Kondisi memakai warna: hijau / kuning / merah, plus ikon (aksesibilitas).
- Setiap aksi destruktif pakai `ConfirmDialog`; aksi sensitif (hapus/dispose)
  pakai `StepUpModal` (PIN ulang) mengikuti kebiasaan aplikasi.
- Empty state mengajari: "Belum ada aset. Tambah manual atau pindai jaringan."
- Halaman scan didesain untuk satu tangan: tombol besar, kamera penuh layar.

### 4.4 Prosedur pelabelan

**Skema tag:** `<CABANG>-IT-<KATEGORI>-<URUT>` → `SBY-IT-PC-0001`.
Urut per cabang+kategori, tidak pernah dipakai ulang (aset disposed tetap
memegang tag-nya).

**Isi QR:** URL aplikasi `https://nasbpfsby.duckdns.org:5000/app/it/assets/SBY-IT-PC-0001`
(`:5000` wajib — port 443 dilayani Nextcloud; ±67 karakter, QR versi 5, masih
nyaman dicetak 22–25 mm). Untuk perangkat
tanpa akses internet, sisi aplikasi tetap bisa membuka lewat input tag manual.

**Langkah baku:**
1. Data minimum wajib: kategori, merek/model, nomor seri, ruangan, PIC.
2. Sistem membuat tag + QR; cetak pada **stiker vinyl A4** (3×8 = 24 label
   ukuran 63×35 mm) atau layout mini untuk kabel/adaptor.
3. **Uji scan 1 label** sebelum mencetak banyak (prosedur kontrol kualitas).
4. Tempel sesuai kategori:

   | Perangkat | Posisi label |
   |---|---|
   | PC desktop | panel depan kanan atas casing (bukan menutup tombol) |
   | Laptop | alas bawah dekat nomor seri; jangan menutup baut/garansi |
   | Monitor | pangkal belakang, menghadap ke bawah |
   | Printer | panel depan kanan |
   | Switch/router/AP | panel depan kanan; untuk rack pakai label gantung |
   | UPS | panel depan atas |
   | Proyektor/TV | sisi belakang, tidak menutup ventilasi |
   | Kabel/adaptor | label mini pada konektor |

5. Foto perangkat berlabel → unggah → status "berlabel" tercatat (audit).
6. Cetak ulang wajib mengisi alasan; label lama dicabut agar tidak ganda.

**Bahan & alat:** stiker vinyl tahan air, laminasi dingin, pembersih permukaan
(alkohol), gunting/cutter. Untuk volume besar, pertimbangkan label printer
(Brother QL / Zebra) — layout PDF tinggal ditambah ukuran gulungan.

### 4.5 Prosedur update kondisi (target < 15 detik)

1. Scan QR (kamera HP atau halaman `/it/scan`).
2. Halaman detail terbuka; tiga tombol kondisi besar.
3. Pilih kondisi → opsional foto + catatan → **Simpan**.
4. Sistem menulis `it_asset_events` (sebelum→sesudah, aktor, waktu) dan
   memperbarui `updated_at`.
5. Untuk `rusak_berat`, tawarkan status `service` + catatan vendor.

Tanpa HP? Dashboard → cari tag/nama → klik chip kondisi. Tetap 2–3 klik.

### 4.6 Alur penemuan otomatis

```
[cron host 30 mnt]  python3 scripts/it_discovery_agent.py
        │  sapuan TCP 192.168.2.0/23 + /proc/net/arp
        │  (opsional) MikroTik DHCP lease via API
        ▼
POST /api/it/discovery/agent   (token, bukan sesi)
        ▼
dedupe by MAC → klasifikasi aturan → simpan kandidat state=new
        ▼
UI "Jaringan": IT meninjau → Jadikan Aset (prefill form) / Abaikan (7 hari)
```

Mengapa agent di host, bukan di container: ARP tabel LAN hanya terlihat di
namespace host; container bridge tidak bisa membaca MAC tetangga. Ini juga
mengikuti pola yang sudah ada (agen SubsidiTepat di host). Tanpa sudo —
TCP connect + `/proc/net/arp` cukup (sudah diuji).

Frekuensi: manual (tombol) + otomatis 2×/hari. Satu run sekaligus (lock),
timeout per host 0,5–1 dtk, batas 1.024 target.

### 4.7 Impor massal & migrasi data lama

- Template CSV/XLSX: `asset_tag,kategori,merek,model,serial,status,kondisi,ruangan,pic,tanggal_beli,garansi,harga,catatan`.
- Alur: unggah → **pratinjau validasi** (baris error ditandai) → commit.
- Tag kosong → dibuat otomatis; tag bentrok → ditolak dengan saran.
- Sumber data lama yang mungkin: file Excel/Sheets IT, atau tabel
  `bpf_asset_system` lama. Ekspor dulu ke template ini.

---

## 5. Rencana implementasi (bertahap)

| Fase | Isi | Est. | Nilai |
|---|---|---|---|
| **1. Inti inventaris** | schema + CRUD + tambah manual + daftar/detail + dashboard + audit + ekspor CSV | 1–2 hari | Aset non-jaringan mulai tercatat |
| **2. Label & QR** | generator tag, PDF label, layout, status berlabel, prosedur tercetak | 1 hari | Label resmi + prosedur baku |
| **3. Scan & kondisi** | halaman scan mobile, update kondisi 3 tap, foto, timeline | 1–2 hari | Update kondisi cepat & berjejak |
| **4. Discovery** | agent host, endpoint kandidat, klasifikasi aturan, adopt/ignore | 2 hari | Perangkat jaringan masuk otomatis |
| **5. Operasional** | impor Excel, stok opname, garansi, laporan PDF | 1–2 hari | Siklus inventaris lengkap |

File yang akan disentuh:

```
modules/routes_it_assets.py        (baru)  API + logika
modules/it_inventory_schema.py     (baru)  ensure_*_schema()
modules/it_classifier.py           (baru)  aturan + OUI
scripts/it_discovery_agent.py      (baru)  agent host
app.py                             daftar register + ensure
init.sql                           seed tabel
requirements.txt                   + segno (+ netaddr opsional)
frontend/src/views/ItInventoryView.vue     (baru)  tab utama
frontend/src/views/ItAssetDetailView.vue   (baru)
frontend/src/views/ItScanView.vue          (baru, mobile)
frontend/src/router/index.js       route /it/inventory, /it/assets/:tag, /it/scan
frontend/src/layouts/AppLayout.vue menu "Inventaris IT"
frontend/src/stores/auth.js        home role IT → /it/inventory
tests/test_it_assets.py            (baru)  CRUD, scoping cabang, klasifikasi
```

---

## 6. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Sapuan jaringan dianggap "menyerang" | hanya TCP connect + ICMP; jadwal tetap, log run, izin tertulis dari IT Head |
| False positive (HP/tamu masuk kandidat) | kandidat tidak pernah auto-jadi aset; aturan OUI acak → abaikan; tombol Abaikan 7 hari |
| MAC berubah (WiFi private address) | utamakan MAC kabel/OUI; hostname + IP sebagai bukti tambahan |
| Data pribadi (PIC/pemakai) | akses per cabang, audit log, retensi mengikuti kebijakan yang ada |
| Beban server saat scan | thread terbatas, 1 run, di luar jam sibuk, timeout ketat |
| Tag ganda saat impor | `UNIQUE(asset_tag)` + validasi pratinjau |
| PIN lemah (`123456`) | wajib ganti PIN acak 6 digit; rate-limit login sudah ada |

---

## 7. Keputusan yang perlu dikonfirmasi

1. **Domain QR**: pakai URL publik `nasbpfsby.duckdns.org:5000` (bisa discan siapa pun,
   tapi butuh login) atau kode ringkas `BPFIT:...` (hanya dikenal aplikasi)?
2. **Cakupan discovery**: hanya `192.168.2.0/23` atau juga pool VPN
   `172.60.199.0/24`?
3. **MikroTik**: boleh mengaktifkan API 8728 / SNMP 161? (kualitas hostname
   naik drastis; tanpa itu tetap jalan dengan sweep+ARP).
4. **Agen WMI**: perlu data hardware/software otomatis, atau cukup manual?
5. **Printer label**: stiker A4 atau label printer khusus (Brother/Zebra)?
6. **Auto-adopt**: apakah kandidat dengan keyakinan ≥ 0.9 boleh langsung menjadi
   aset, atau selalu manual?
7. **Kategori awal** yang wajib ada (usulan: PC, laptop, monitor, printer,
   scanner, switch, router, AP, UPS, proyektor, TV, CCTV, server/NAS, telepon,
   lisensi, consumable, lainnya).

---

## 8. Bukti teknis (log ringkas)

- Sapuan NAS → `192.168.2.0/24`: 13 hidup — `.1` (router), `.12/.14/.16/.62`
  (Windows: 135+445), `.20/.22/.39/.40/.43/.45` (80/443), `.31` (NAS), `.106` (22).
- `/proc/net/arp` memberi MAC untuk 192.168.2.x dan 172.60.199.x.
- PDF label: 24 label A4 (3×8, 63×35 mm) berisi QR + `SBY-IT-PC-xxxx` +
  footer "PT Bestprofit Futures - Surabaya"; file uji `/tmp/qr-label-spike.pdf`.
- `it_sby` PIN terverifikasi cocok dengan hash scrypt di DB master.


---

## 8. Status implementasi (produksi, 11 Nov 2026)

Keputusan yang diambil pada bagian 7 — semua sudah diterapkan kecuali yang
ditandai *menunggu*:

| Butir | Keputusan |
|---|---|
| Domain QR | URL publik `https://nasbpfsby.duckdns.org:5000/app/it/assets/<TAG>` (butuh login) |
| Cakupan discovery | `192.168.2.0/23` (VNAT `172.60.199.0/24` *menunggu persetujuan*) |
| MikroTik | API 8728 masih tertutup — sweep + ARP jalan; *menunggu* bila ingin hostname akurat |
| Agen WMI | dipakai (PowerShell, manual/Task Scheduler) |
| Printer label | stiker A4 (3×8 default, opsi 2×8 dan 2×6) |
| Auto-adopt | **tidak** — kandidat selalu ditinjau IT |

Konfigurasi produksi yang terpasang:

- `.env`: `IT_DISCOVERY_TOKEN` (48 karakter acak), `IT_ASSET_PUBLIC_BASE`,
  `IT_DISCOVERY_SUBNETS=192.168.2.0/23`.
- Cron host `it-ef`: `0 12,20 * * *` menjalankan
  `scripts/it_discovery_agent.py --branch SBY --subnets 192.168.2.0/23`
  (log `/home/it-ef/it-discovery.log`). Hasil hanya menjadi kandidat.
- Tabel `it_*` dibuat otomatis saat container start di DB master + 11 DB cabang.
- Akses: role IT (per cabang) dan `admin`; role lain ditolak 403. Data ter-scope
  `branch_code` — aset cabang lain tidak terlihat (404 pada lookup lintas cabang).
- MikroTik via API: `pip install librouteros` di host bila API 8728 dibuka.

Catatan operasional:

- Label batch default hanya mencetak aset yang `label_printed_at` masih kosong
  (maks 120); mencetak label menandai aset "tercetak" dan menulis event riwayat.
- Hapus permanen tidak disediakan; gunakan status `disposed` agar tag tidak
  dipakai ulang.
- QR kamera memerlukan `BarcodeDetector` (Chrome Android); input tag manual
  tersedia sebagai fallback di `/it/scan`.

## 9. Rollout agen terkontrol + cakupan (v2.79, 11 Nov 2026)

Keputusan: **deployment terkontrol berbasis allowlist**, bukan agen yang
menyebar sendiri. Tujuannya bukan "menjangkau sebanyak mungkin host", tetapi
mengetahui *host mana yang sudah terpantau* dan *mana yang belum* — dengan
jejak audit per host.

### 9.1 Komponen

| Komponen | Peran |
|---|---|
| `scripts/it_inventory_agent.ps1` v1.1.0 | Agen di PC: baca WMI/CIM, kirim kandidat, lapor registry, self-update harian |
| `scripts/deploy_it_agent.ps1` | Deployer dari PC operator: allowlist CSV, WinRM, laporan hasil |
| `it_agent_hosts` | Satu baris per PC: versi agen, status deploy, laporan terakhir, metode |
| `GET /api/it/agents/coverage` | Angka cakupan + daftar target yang belum tercakup |
| `GET /api/it/agents/targets.csv` | Allowlist siap pakai (hanya PC yang belum tercakup) |
| `GET /api/it/agents/version` + `/package` | Self-update agen (token-gated) |

Status registry: `pending` → `installed` → (`failed` / `unreachable`).
Host dianggap **tercakup** bila `installed` dan laporan terakhir ≤ 7 hari
(`IT_AGENT_STALE_DAYS`). Angka cakupan dihitung dari aset kategori PC/laptop
dibandingkan registry, bukan dari jumlah kandidat.

### 9.2 Dua jalur pemasangan

| Lingkungan | Jalur | Kredensial | Catatan |
|---|---|---|---|
| Active Directory | GPO startup script / Intune / SCCM | tidak perlu per-PC | paling bersih; jalankan `-Install -ApiUrl ... -TokenFile ...` dari share baca-saja |
| Workgroup / standalone | `deploy_it_agent.ps1` via WinRM (5985/5986) | admin lokal per PC / akun seragam | allowlist wajib, maks 25 host per eksekusi |

WinRM harus aktif di PC target (`Enable-PSRemoting -Force`, atau GPO). Untuk
workgroup dengan WinRM HTTP, mesin operator perlu `-SetupTrustedHosts` atau
lebih baik WinRM HTTPS. Deployer **tidak** memakai PsExec, tidak menulis ke
share admin, dan tidak punya parameter subnet/CIDR.

### 9.3 Penjaga keamanan

- `-Targets <csv>` wajib; baris CIDR, rentang IP, dan wildcard ditolak.
- `-MaxHosts` default 25; melebihi hanya dengan `-Force` (keputusan sadar).
- Token tidak ditampilkan di command line remote: dikirim sebagai berkas
  sementara ber-ACL, dihapus setelah config tersimpan (`-DeleteTokenFile`).
- Config agen (`C:\ProgramData\BPFWorkHub\agent-config.json`) di-ACL ke
  SYSTEM + Administrators.
- Agen tidak memindai jaringan, tidak membuka port, tidak membuat aset, dan
  tidak menyentuh host di luar allowlist; self-update hanya menarik dari
  `/api/it/agents/package` dengan token.
- `-DryRun` menampilkan rencana tanpa membuka koneksi; konfirmasi `ya`
  diminta sebelum push.

### 9.4 Runbook singkat

```powershell
# di PC operator Windows (folder berisi kedua skrip)
.\deploy_it_agent.ps1 -Targets .\target_agen_it_SBY.csv `
    -ApiUrl https://nasbpfsby.duckdns.org:5000 -Branch SBY -DryRun
.\deploy_it_agent.ps1 -Targets .\target_agen_it_SBY.csv `
    -ApiUrl https://nasbpfsby.duckdns.org:5000 -Branch SBY `
    -Credential (Get-Credential)
```

Hasil per host: log CSV di `.\logs\deploy_it_agent_<branch>_<stamp>.csv` dan
baris registry di dashboard (tab Jaringan → panel **Cakupan Agen**). Host yang
gagal tercatat `failed`/`unreachable` beserta pesan penyebab, sehingga bisa
diulang tanpa menebak.

### 9.5 Verifikasi

- `tests/test_it_agent_rollout.py` (41 test): host key, versi, status, cakupan,
  allowlist CSV, keselarasan versi Python↔PowerShell, dan penjaga deployer.
- Build SPA + vitest (270 test) lulus; endpoint agen terdaftar di url_map.
- Uji produksi: `GET /api/it/agents/version` tanpa token → 401; dengan
  `X-IT-TOKEN` → `{"version":"1.1.0"}`; `targets.csv` hanya berisi PC yang
  belum tercakup.
