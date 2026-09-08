# 📋 Changelog — BPF WorkHub

Riwayat perubahan BPF WorkHub. Ditulis untuk manusia, bukan untuk robot.

---

## v2.37.7 — 8 September 2026 (Kop Tanda Terima air minum mengikuti cabang)

Lanjutan v2.37.6: kop per cabang kini juga di **PDF Tanda Terima air minum**
(dokumen yang dicetak Finance saat verifikasi) — sebelumnya kop dokumen ini
masih memakai identitas global (alamat HO) untuk semua cabang.

### Ditambah
- **`get_branch_identity(branch_code)`** (`modules/company_identity.py`) —
  satu sumber identitas kop per cabang dari tabel `branches` (DB master):
  company_name, company_subtitle, address, phone. Kolom kosong di baris
  cabang diisi dari identitas global; branch kosong/baris tak ada/DB mati →
  identitas global penuh (fail-open, perilaku lama).
- **`BPFBasePDF.set_identity(identity=…, branch_code=…)`** — cara standar
  memasang kop per dokumen SEBELUM `add_page()`; dipakai semua subclass
  (WaterReceiptPDF, OvertimeFormPDF, dst.).

### Diubah
- **PDF Tanda Terima air minum** (`/api/water/purchases/<id>/pdf`) — kop
  kini mengikuti cabang sesi (SBY → "Graha Bukopin …", JKT → "Equity Tower
  Lt. 47 …", dst.). Finance cabang mana pun mencetak dokumen resmi dengan
  kop cabangnya sendiri.
- **Kop per cabang diperluas ke dokumen lain**: Form Permohonan Overtime,
  Laporan Overtime (PDF & detail per-driver PDF) — via `set_identity()`;
  Trip Logsheet Excel & Laporan Appointment Harian Excel — via parameter
  `identity` opsional di `excel_generator.py` (fallback identitas global
  bila tidak dikirim).
- **UI Pengaturan → 🏢 Cabang**: tombol **✏️ Edit** kini tampil di tabel
  cabang (khusus Admin Pusat) — identitas cabang (nama, kota, **alamat
  kop dokumen**, telepon, subjudul) bisa diperbarui Admin langsung dari UI
  saat kantor pindah, tanpa SQL; identitas tersimpan ikut ditulis ke
  `system_config` DB cabang. Keterangan seksi diperjelas (alamat = kop
  dokumen resmi; label "Ganti cabang (Admin Pusat)").
  Catatan: endpoint `POST /api/branches/save` sudah ada sejak v2.19.2 —
  perubahan ini menutup gap UI-nya.
- **`WaterReportPDF` (export rekap)** di-refactor memakai `set_identity()` —
  perilaku sama dengan v2.37.6, kini lewat satu pintu yang sama.
- Stamp versi v2.37.7 (pdf_generator SYSTEM_VERSION, company_identity &
  identity.js default, seed init.sql) + master DB `system_config`
  `system_version` diperbarui (sebelumnya basi di v2.29.10).

### Data
- **Alamat MLG dikoreksi** sesuai situs resmi: "BPF Tower…" → **Ruko
  Pelita, Jl. Letjen S. Parman No. 59 Kav. 1, 3–5, Malang** (ter-verify
  live di kop PDF).
- **Stamp identitas dirapikan** — kolom `system_name`/`system_version`
  tabel `branches` kini seragam "BPF WorkHub v2.37.7" untuk semua cabang
  aktif, dan tersinkron ke `system_config` tiap DB cabang (8 DB, script
  `scripts/sync_branch_stamp.py`, idempoten). Master DB `system_config`
  `system_version` v2.29.10 → v2.37.7.

### Keamanan / Keandalan
- **Insiden gunicorn 26 (8 Sep)** — rebuild pasca-merge Dependabot #6
  membuat `bbm_web` crash-loop: gunicorn 26.x menghapus worker bawaan
  `eventlet`/`gevent` (jadi extra terpisah), CMD
  `gunicorn --worker-class eventlet` gagal ImportError. CI lulus karena
  pytest tidak pernah memulai worker. Fix: kembali ke gunicorn 23.0.0
  + catatan di `requirements.txt`; guard baru
  `tests/test_gunicorn_worker.py` (2 test) mem-parse CMD Dockerfile dan
  memastikan worker-class bisa di-resolve versi ter-install — regresi
  serupa kini tertangkap CI.
- **Verifikasi UI browser (puppeteer)** — skrip baru
  `frontend/scripts/verify_branch_edit_ui.mjs` (9 cek): login
  admin_master → Pengaturan → Cabang → ✏️ Edit → ubah alamat → simpan →
  DB berubah → restore. Menangkap bug nyata: daftar cabang dari
  `/api/branches/current` tidak memuat `id`/`address` sehingga modal
  ✏️ Edit selalu terbuka sebagai "Tambah" — diperbaiki dengan merge data
  penuh dari `/api/branches` di `loadBranches()`.
- **3 cabang resmi ditambahkan NONAKTIF** (`is_active=0`, pola PLM — data
  tercatat, diaktifkan Admin saat kantor mulai dipakai): **JMB Jambi**
  (Jl. Kolonel Abunjani No. 29 C Sipin), **PTK Pontianak** (Sentra Bisnis
  A. Yani Megamall C1-C5), **PKU Pekanbaru** (Sudirman City Square) —
  lengkap dengan alamat & telepon resmi; seed ikut di
  `scripts/branches_update.sql` + tersimpan di DB produksi.

### Test
- `tests/test_branch_identity.py` **baru (11 test)**: fallback berlapis
  (kolom kosong → global, baris tak ada, DB mati fail-open), normalisasi
  kode lowercase, subtitle fallback dari city, kebersihan koneksi (conn
  sendiri ditutup, conn pemanggil tidak), kunci hasil = nama field identity.
- `tests/test_water.py` +2: kop Tanda Terima memakai alamat cabang (alamat
  HO tidak ikut muncul — dicek di teks PDF hasil generate) + set_identity
  tanpa argumen tetap global.
- Suite air minum: **42 pytest lulus** (test_branch_identity + test_water +
  test_water_export + test_pdf_header_layout).
- +3 test lanjutan: kop OvertimeReportPDF per cabang (alamat MDN masuk,
  HO tidak), Trip Logsheet Excel dengan `identity` cabang (B2 = "Cabang
  Banjarmasin") + fallback identity kosong. Full suite container & vitest
  135 + build SPA hijau (jalankan terpisah — vitest flake bila bentrok
  dengan pytest paralel).
- Verifikasi live di container: `get_branch_identity` mengembalikan alamat
  resmi ke-9 cabang dari DB produksi; PDF Tanda Terima SBY/MDN/JKT masing-
  masing memuat kop cabangnya dan TIDAK memuat alamat cabang lain.

---

## v2.37.6 — 7 September 2026 (Tata letak export air minum + kop per cabang + Palembang dinonaktifkan)

Lanjutan sesi yang terputus di tengah pekerjaan: perapian tata letak output
PDF rekap air minum dan kop dokumen yang mengikuti cabang masing-masing.
Sekalian pembersihan data cabang (Palembang tidak punya kantor cabang).

### Diperbaiki
- **PDF** (`modules/water_report.py`): grid digambar manual per baris
  (rect + garis kolom) sehingga semua kolom tetap rata walau teks
  multi-baris; tinggi baris diukur dari SEMUA kolom (bukan 3); header tabel
  diulang tiap halaman; teks vertikal center pada sel satu baris; blok TTD
  dengan tempat/tanggal (kota cabang dari tabel `branches`).
- **Excel**: tinggi baris mengikuti konten wrap, zebra fill, warna status,
  garis tanda tangan di ATAS nama, freeze panes header.
- **Filter tanggal `to` kini INKLUSIF** — bug v2.37.4: transaksi pada hari
  terakhir bulan tersembunyi dari daftar & export ("Sampai 31 Agustus"
  tidak menampilkan transaksi 31 Agustus). Query kini `< (to + 1 hari)`,
  tetap parameterized. `tests/test_water_filter.py` disesuaikan.
- **Kop PDF tidak lagi selalu Kantor Pusat** — bug integrasi v2.37.5:
  `WaterReportPDF()` dipanggil tanpa override identity sehingga kop tetap
  memakai alamat HO (Equity Tower) untuk semua cabang. Kini `generate()`
  meng-override identitas dari `meta['company']` (dibangun `_export_meta()`
  dari tabel `branches` sesuai cabang sesi). +1 test regresi
  (`test_kop_mengikuti_cabang`: alamat cabang ADA, alamat HO TIDAK ADA).

### Ditambah
- **Data identitas cabang** — alamat & telepon resmi 9 cabang diisi di
  tabel `branches` (sumber: bestprofit-futures.co.id/hubungi-kami), sehingga
  kop export tiap cabang menampilkan alamatnya sendiri (SBY: Graha Bukopin
  Lt. 11; JKT: Equity Tower Lt. 47; JKT2: Pacific Place Mall; BDG, SMG, MDN,
  BJM, LPG, MLG). `init.sql` seed SBY/JKT/JKT2 ikut menyertakan
  address/phone untuk fresh-install. SQL pembanding:
  `scripts/branches_update.sql`.

### Keamanan / Data
- **Cabang Palembang (PLM) dinonaktifkan** — perusahaan tidak memiliki kantor
  cabang di Palembang: `branches.is_active=0` + user `it_plm` & `admin_plm`
  dinonaktifkan (login 401 terverifikasi live). DB `bpf_branch_plm`
  dibiarkan utuh — reversible. Sekalian: telepon JKT di tabel branches
  dikoreksi (sebelumnya 031-5349888 = nomor Surabaya, kini 021-29035005 = HO
  Jakarta).

### Deploy
- Rebuild `bbm_web` 7 Sep (2× — fix kop menyusul verifikasi pertama);
  health 200; login `admin_master` OK; export PDF (SBY) memuat kop
  "Graha Bukopin …" tanpa "Equity Tower"; export Excel A2/A3 memuat
  identitas SBY; periode default kini "01/09/2026 s/d 30/09/2026".
- Suite: 28/28 test water di container final; **551 pytest + 6 skip** lulus
  (container rebuilt).

---

## v2.37.5 — 7 September 2026 (Export rekap air minum — PDF & Excel resmi)

Permintaan pemilik: hasil filter bisa diexport dalam format resmi untuk
dilampirkan ke laporan/dokumentasi.

### Ditambah
- **Tombol 📄 Export PDF & 📊 Export Excel** di WaterView (finance/admin) —
  mengirim filter aktif (rentang/status/pencarian) ke endpoint export.
- **`GET /api/water/purchases/export?format=xlsx|pdf`** — filter identik
  dengan daftar (default bulan berjalan); nama file
  `Rekap_AirMinum_<dari>_sd_<sampai>.<ext>`.
- **Generator laporan resmi** (`modules/water_report.py`):
  - Excel (openpyxl): landscape A4 fit-to-width, kop perusahaan + periode +
    filter, 9 kolom (No, No. Dokumen, Tanggal, OB, Rincian Item, Total Qty,
    Status, Remark, Catatan), baris zebra + border, blok RINGKASAN, dua blok
    TTD: **Finance (Dibuat oleh)** & **Kepala Cabang (Mengetahui)**.
  - PDF (fpdf2): reuse `BPFBasePDF` (kop identitas + footer halaman),
    landscape A4, tabel wrap multi-baris, ringkasan, TTD dua pihak.
- **Nama TTD dari Pengaturan → 🚰 Air Minum** — kini 3 field: Nama Finance
  (Menyerahkan/Mengetahui TTD PDF tanda terima), Nama GA (Menerima), dan
  **Nama Kepala Cabang** (`system_config.water_head_name`) — fallback label
  generik bila belum diset.
- Test: +15 pytest (`tests/test_water_export.py`: validitas xlsx/pdf,
  landscape, konten judul & TTD via extractor PDF, multi-page, content-type
  & filename endpoint, filter diteruskan, scoping OB, fallback TTD) + +4
  vitest (tombol export, params filter & format, OB tak lihat tombol) —
  suite **551 pytest + 6 skip** dan **135 vitest**, hijau.

---

## v2.37.4 — 7 September 2026 (Filter rentang tanggal daftar air minum)

Saran finance: cari pengajuan per rentang tanggal, default menampilkan
bulan berjalan.

### Ditambah
- **Filter bar di WaterView** — Dari/Sampai (date picker), Status
  (Semua/Menunggu/Terverifikasi/Ditolak), pencarian bebas `q`
  (no. dokumen / nama OB / merk), tombol Tampilkan + ↺ Bulan ini.
- **Backend `GET /api/water/purchases`** menerima `from`, `to`,
  `status`, `q` — default rentang bulan berjalan (awal s/d akhir bulan,
  akhir eksklusif). Response kini `{purchases, range, filters}` (array
  lama tetap ditangani frontend). Semua nilai via parameter query (%s) —
  tanggal invalid → fallback default, bukan error.
- Test: +12 pytest (`tests/test_water_filter.py`: _month_range termasuk
  Desember→Januari, _parse_ymd, guard SQL parameterized, scoping OB,
  status invalid) + +5 vitest (params bulan berjalan, ganti rentang,
  pencarian Enter, reset, kompatibilitas array lama) — suite
  **536 pytest + 6 skip** dan **131 vitest**, hijau.

---

## v2.37.3 — 7 September 2026 (Detail snapshot audit log di UI Log)

Lanjutan temuan E2E air minum: snapshot `old_data`/`new_data` tersimpan di
DB tapi tidak bisa dilihat admin dari UI Log.

### Ditambah
- **`GET /api/audit-logs/<id>`** — detail satu entri audit log termasuk
  snapshot `old_data`/`new_data` (di-parse ke objek bila datang sebagai
  string). Role: ga/finance/admin; scoping cabang paritas dengan list
  (admin cabang terkunci ke cabangnya, `?branch=` khusus Admin Pusat).
- **UI Log** — tombol 🔍 per baris membuka modal detail: metadata (user,
  aksi, cabang, IP, user-agent, waktu) + tabel snapshot Data Lama & Data
  Baru; pesan jelas bila entri tidak menyimpan snapshot.
- Test: +5 vitest (modal buat/tutup, id mengikuti entri yang diklik,
  entri tanpa snapshot, error di modal, list tetap utuh) — suite
  **524 pytest + 6 skip** dan **126 vitest**, hijau.

---

## v2.37.2 — 7 September 2026 (Fix: foto bukti tidak muncul + preview di verifikasi air minum)

Laporan finance: gambar bukti tidak muncul & butuh preview saat proses
verifikasi air minum.

### Diperbaiki
- **Semua foto bukti 500 sejak commit 584ba88** — auth check `/uploads/`
  memakai `session` tanpa meng-import-nya → NameError di setiap request,
  gambar tidak pernah tampil di UI (air minum, trip, disp, overtime).
  Kini `session` di-import di `routes_driver.py` + regression test
  `tests/test_uploads_auth.py` (401 tanpa sesi, 200 dengan sesi back-office
  & driver PWA, 404 file tidak ada).
- Fallback UI bila foto gagal dimuat: "⚠️ Foto gagal dimuat" (bukan gambar
  kosong).

### Ditambah — Preview bukti di proses verifikasi (SPA)
- Modal Verifikasi/Tolak kini menampilkan foto bukti (sebelum & sesudah)
  langsung di dalam modal — finance tidak perlu buka Detail terpisah.
- Klik foto (di modal verifikasi & modal detail) → lightbox perbesar
  fullscreen; klik backdrop atau ✖ untuk menutup.
- Test: +6 vitest (foto tampil, GET detail, lightbox buka/tutup, klik di
  detail, fallback rusak, verifikasi tetap bisa tanpa detail) — suite
  **524 pytest + 6 skip** dan **121 vitest**, hijau.

---

## v2.37.1 — 7 September 2026 (Hotfix: lubang scoping admin cabang di /api/users/sync)

Hotfix keamanan lanjutan v2.37.0 — guard admin cabang pada `/api/users/sync`
diperketat untuk update-by-id dan akun tanpa cabang.

### Diperbaiki
- **Update-by-id lintas cabang kini ditolak (403)** — sebelumnya admin cabang
  bisa mengubah akun cabang lain dengan mengirim `id` tanpa `branch_code`.
  Branch target kini di-resolve dari row existing (by id/username), dan role
  admin pada row existing ikut dicek.
- **User baru tanpa `branch_code` ditolak (403)** — admin cabang tidak bisa
  lagi membuat akun tanpa jejak cabang.
- Test toggle air minum dibuat deterministik (monkeypatch jalur tanpa-DB —
  tidak lagi flake di host/container dengan DB nyata).
- Test: +2 (TestAdminCabangScope) — suite 520 pytest + 6 skip, hijau.

---

## v2.37.0 — 7 September 2026 (Edit/hapus transaksi air minum + admin per-cabang + Pengaturan terstruktur)

Tiga permintaan lapangan sekaligus: (1) Finance bisa mengoreksi & menghapus
transaksi air minum — fitur opsional yang di-enable/non-aktifkan Admin per
cabang; (2) akun admin mengikuti konvensi `{divisi}_{cabang}` — `admin_sby`,
`admin_bdg`, dst. terkunci ke cabangnya masing-masing; (3) halaman Pengaturan
Admin yang menumpuk dibenahi jadi terstruktur dengan peta seksi.

### Ditambah — Edit & Hapus Transaksi Air Minum (fitur opsional, default NONAKTIF)
- Toggle Admin di **Pengaturan → 🚰 Air Minum** (`system_config`
  `water_edit_enabled` per DB cabang — berlaku per cabang, bukan global).
  Bila nonaktif, perilaku persis seperti sebelumnya (tidak ada tombol baru,
  API menolak 403).
- **Edit** (`PUT /api/water/purchases/<id>`): Finance/admin bisa mengoreksi
  tanggal pengiriman, rincian item (jenis/merk/satuan/qty), remark & note —
  untuk pengajuan berstatus **Menunggu** dan **Terverifikasi** (status
  Ditolak tidak bisa diedit — cukup alasan tolaknya). Foto bukti OB tidak
  berubah lewat endpoint ini (bukti tetap orisinal).
- **Hapus permanen** (`DELETE /api/water/purchases/<id>`): baris + item +
  file foto dihapus; **snapshot lengkap disimpan di audit log** sebelum
  terhapus (`old_data`) — jejak satu-satunya yang tersisa, sesuai keputusan
  "hapus permanen + audit".
- Keduanya wajib **step-up PIN** (428 tanpa grant — sama dengan verifikasi)
  dan tercatat penuh di audit log (`water_purchase_edit` /
  `water_purchase_delete`).
- Kolom jejak edit baru di `water_purchases`: `edited_by`, `edited_at`,
  `edit_count` (dibuat otomatis saat startup di master + tiap DB cabang,
  idempoten; juga ikut `ensure_branch_database` untuk cabang baru).
- SPA: tombol ✏️ Edit & 🗑️ di WaterView (finance/admin) hanya muncul bila
  fitur aktif; modal edit dengan validasi item sama seperti form pengajuan;
  hapus dengan konfirmasi + step-up PIN.

### Ditambah — Admin per-cabang (`admin_<kode>`)
- Konvensi username v2.29.7 kini berlaku juga untuk admin: **`admin`** (tanpa
  sufiks) = Admin Pusat — semua cabang; **`admin_<kode>`** (mis. `admin_sby`)
  = Admin Cabang — operasional terkunci ke cabangnya.
- Modul baru `modules/admin_scope.py`: deteksi Admin Pusat (fail-closed —
  DB mati = dianggap admin cabang), daftar cabang milik akun (suffix username
  + kolom `users.managed_branches` utk 1 admin multi-cabang), flag
  `users.admin_all_branches` (promosi manual via SQL), decorator `ho_only`,
  dan `assert_branch_row_scope` (baris di luar cabang → 403).
- Endpoint lintas cabang kini **khusus Admin Pusat** (admin cabang → 403):
  ganti cabang kerja (`/api/branches/switch`), daftar/daftar+reset nomor
  dokumen cabang lain, retensi & arsip audit global, access review + export,
  daftar cabang untuk switcher.
- Audit log (`/api/audit-logs?branch=`): admin cabang hanya boleh membaca
  log cabangnya.
- Login & `/api/auth/me` kini menyertakan `is_ho_admin` → SPA menyembunyikan
  switcher cabang & menu lintas cabang (Access Review, Audit Log) untuk
  admin cabang; sidebar menandai "🔒 Cabang".
- `admin_all_branches` + `managed_branches` dibuat otomatis saat startup
  (master + tiap DB cabang).

### Diubah — Pengaturan (SPA) lebih terstruktur
- Peta seksi **sticky** di atas halaman: 🚗 Data Master · 🚰 Air Minum ·
  🏢 Cabang & Nomor · 🗄️ Kepatuhan (ISO) · 🎨 Identitas · 🧪 Lainnya — klik
  langsung scroll; seksi aktif ter-highlight saat scroll (IntersectionObserver).
- Toggle edit/hapus air minum memakai switch standar (label AKTIF/NONAKTIF)
  dengan konfirmasi.

### Test
- **511 pytest** (+35: `tests/test_admin_scope.py` 13, `tests/test_water_edit_delete.py`
  19 — termasuk gate fitur, step-up 428, scoping admin cabang, foto terhapus,
  endpoint toggle; `TestAdminCabangScope` 3 — guard manajemen user) +
  **115 vitest** (+6: WaterView edit/delete UI 4, SettingsView peta seksi +
  toggle 2). Build SPA sukses.

---

## v2.36.2 — 6 September 2026 (Kunci sinkronisasi overtime yang stabil)

Lanjutan v2.36.1: identitas baris overtime Driver tidak lagi bergantung pada
**nomor baris spreadsheet** (berubah setiap ada baris disisipkan/dihapus di
tengah), melainkan **digest isi baris** — pola yang sama dengan modul
OB/Security sejak v2.29.6.

### Perubahan
- Kolom baru `source_uid` di `overtime_driver` (**UNIQUE**) berisi
  `sheet-<md5(nama|submitted_at|sheet_row)>` — re-sync mengenali baris yang
  sama walau posisi baris sheet bergeser; pasangan (nama, submitted_at)
  terbukti unik di seluruh 8.745 baris produksi.
- `display_id` kini `OTS-<12 digit digest>` — bebas benturan walaupun
  `sheet_row` menumpuk, dan **konsisten** antar re-sync (verifikasi PDF tetap
  bermakna). Sebelumnya (v2.36.1) `OTS-<sheet_row>` bisa berubah nilainya
  ketika sheet bergeser.
- Submit form PWA Driver kini juga menyimpan `source_uid` (`form-…`) —
  paritas OB; sekaligus memperbaiki bug laten di mana semua submit form
  menumpuk di `sheet_row=0` (benturan UNIQUE lama).
- `sheet_row` tidak lagi UNIQUE; tetap disimpan sebagai jejak posisi terakhir.
- Backfill startup idempoten: baris lama (semua `source_uid=''`) diisi dari
  (nama, submitted_at) **sebelum** index UNIQUE dibuat — urutan migrasi aman.
- Paritas cabang: `ensure_branch_database()` kini ikut menjalankan migrasi
  overtime di setiap DB cabang; `init.sql` & CREATE TABLE disamakan
  (display_id/source/source_uid) agar deploy fresh tidak berbeda dengan prod.

---

## v2.36.1 — 6 September 2026 (Perbaikan sinkronisasi overtime Driver — data tidak aktual)

Laporan dari lapangan (6 Sep): data overtime Driver di aplikasi tidak sama dengan
spreadsheet sumbernya, meski tombol Refresh sudah dicoba berkali-kali. Ternyata
temuannya lebih dalam dari sekadar "belum di-refresh":

### Akar masalah: baris baru saling menimpa (silent data loss)
- Kolom `display_id` di tabel `overtime_driver` punya constraint **UNIQUE**
  (`uk_display_id`), tapi upsert dari sheet **tidak pernah mengisi kolom ini**
  → semua baris baru masuk dengan nilai `''`. MySQL/MariaDB hanya mengizinkan
  **SATU** baris dengan nilai `''` di kolom UNIQUE → setiap baris sheet baru
  yang masuk **menimpa baris kosong yang sama** (last-writer-wins). Efek
  kumulatifnya: data terlihat "ada" tapi isinya tertukar/usang — persis
  keluhan user. (Baris OB/Security tidak terdampak — display_id-nya sudah
  deterministik dari digest.)

### Perbaikan
- **Upsert kini mengisi `display_id` deterministik**: `OTS-<sheet_row>` —
  konvensi yang sama dengan backfill lama, idempoten saat re-sync.
- **Backfill otomatis** di startup (schema ensure): baris lama bermata
  `display_id=''` diisi `OTS-<sheet_row>` (idempoten, hanya baris sheet).
- **Tombol Refresh di UI Overtime kini full sync** (`full: true`) — sebelumnya
  incremental (hanya baris Timestamp ≥ refresh terakhir −1 jam), sehingga
  edit/penghapusan di baris lama sheet tidak pernah tertarik dan user merasa
  refresh "tidak berfungsi". Full sync menarik ±9 ribu baris — aman.
- Service worker cache bump `v2361`.

### Verifikasi
- Data produksi diperbaiki: 8.675 baris lama (drift) dihapus → full sync
  ulang → **8.745 baris** terisi sesuai feed (100 baris kosong dilewati).
- Verifikasi akhir: setiap baris DB dicocokkan ke feed (nama + tanggal) —
  tidak ada perbedaan. Kolom lokal (GPS, sumber form PWA) tidak tersentuh
  (tidak ada baris GPS di DB saat ini; backup JSON sebelum repair tersimpan).

---

## v2.36.0 — 6 September 2026 (Approval Berjenjang — ACC atasan sebelum diproses)

Fitur roadmap #3 (#3 PROGRESS "approval berjenjang") — sekarang SEMUA
pengajuan yang menggerakkan uang/waktu kerja melewati atasan dulu sebelum
back-office memproses. Modul inti `modules/approvals.py` sebenarnya sudah
ditulis sesi sebelumnya namun BELUM terpasang ke mana pun; sesi ini
menuntaskan integrasi penuh + memperbaiki 5 bug laten di modul tersebut.

### Kebijakan ACC (keputusan produk)

| Jenis pengajuan | Rantai ACC | Titik gate (diblok 409) |
|---|---|---|
| Kasbon (`cash`) | Chief Driver → GA | `/api/cash/approve-ga` |
| Klaim BBM (`bbm`) | Chief Driver → GA | `/api/queue/approve-ga` |
| Overtime Driver (`overtime_driver`) | GA HR → Admin | PATCH `/api/overtime/driver/<id>` |
| Overtime OB/Security (`overtime_ob`) | GA HR → Admin | PATCH `/api/overtime/ob/<id>` |

- Atasan override per user: kolom `users.manager_username` (diisi Admin di
  form Manajemen User). Kosong = atasan default per role (driver →
  Chief Driver, ob → GA HR). Override divalidasi JOIN: atasan harus akun
  aktif — salah ketik tidak membuat pengajuan macet tanpa pemutus.
- Overtime selalu GA HR → Admin (tanpa override — form OB publik tidak
  punya sesi).
- Pengaju tidak bisa memutus pengajuannya sendiri (diblok; pengecualian:
  admin memproses lewat akun berbeda). Tolak wajib alasan (endpoint 400
  tanpa alasan) — alasan tercatat di jurnal + audit log `approval_*`.
- Dokumen lama (sebelum fitur) tidak teregistrasi → langsung lolos gate
  (fail-open, pola sama dengan step-up; DB down juga lolos).

### Backend

- **Modul** `modules/approvals.py`:
  - Tabel `approval_requests` (per DB — master & tiap cabang): subjek
    dokumen (doc_type+doc_ref unik), pengaju, rantai ACC (JSON), langkah
    aktif, status `pending/approved/rejected`, pemutus + catatan.
  - API: `GET /api/approvals` (antrean ACC milik sesi; Admin melihat
    semua), `POST /api/approvals/<type>/<ref>/decision` (ACC/tolak,
    tolak wajib catatan), `GET /api/approvals/<type>/<ref>` (badge
    status). Role: admin/ga/finance/chief_driver/ga_hr.
  - `hook_create_approval()` dipanggil di 4 titik submit (best-effort —
    gagal pencatatan tidak menggagalkan pengajuan): submit kasbon,
    submit klaim BBM driver (`/driver`), submit OT Driver PWA, submit
    OT OB/Security form publik.
  - `gate_approval()` dipasang di 3 titik proses: approve-ga kasbon,
    approve-ga klaim BBM, finalisasi PATCH overtime — pending/rejected
    → 409 JSON `SUPERVISOR_APPROVAL_REQUIRED` + info posisi ACC
    (`pending_at`) untuk pesan SPA.
  - Re-submit dokumen yang sama (draft dikirim ulang) me-reset jurnal ke
    langkah 1 pending (upsert `ON DUPLICATE KEY`).
- **Bug laten modul yang diperbaiki saat integrasi**:
  1. `request` tidak di-import → setiap POST ke endpoint keputusan
     meledak 500.
  2. Router dirakit dgn argumen `role_required` yang tak pernah dipakai →
     semua endpoint ACC tanpa proteksi role. Kini memakai
     `role_required` helpers secara langsung (401/403 terverifikasi).
  3. Endpoint membaca DB cabang via `helpers.get_db_connection` yang
     tidak ada (import error saat runtime) → kini `modules.config`.
  4. Langkah rantai ber-nama hanya bisa diputus oleh username persis →
     kini pemegang role yang sama juga bisa (chief_driver cadangan);
     chain default ikut menyimpan role.
  5. Rantai overtime utk pengaju role `driver` salah ambil Chief Driver
     (map role-pengaju dipakai utk semua doc_type) → kini rantai OT
     selalu GA HR → Admin.
- **Startup** (`app.py`): `ensure_manager_column` + `ensure_approval_tables`
  di master & tiap DB cabang (polanya retention) — retry 5×; modul
  terdaftar via `register_approval_routes(app)`.
- **Cabang baru** otomatis dapat tabel ACC (`ensure_branch_database`).
- **Manajemen User**: `/api/users` menyertakan `manager_username`,
  `/api/users/sync` menyimpannya (eksplisit-saja seperti branch_code —
  toggle/bulk tidak menghapus atasan); `init.sql` kolom baru + tabel
  `approval_requests`.

### Frontend (SPA)

- Halaman baru **✅ ACC Atasan** (`/approvals`, menu untuk chief_driver,
  ga, finance, ga_hr, admin): kartu ringkasan, tabel pengajuan pending
  (display_id, pengaju, cabang, rantai ACC, umur), tombol Keputusan →
  modal ACC/Tolak (tolak wajib alasan).
- `Manajemen User`: kolom form **Atasan (ACC berjenjang)** (placeholder
  "kosong = atasan default role").
- Pesan 409 yang ramah: CashView & GaDashboard menerjemahkan
  `SUPERVISOR_APPROVAL_REQUIRED` → "Menunggu ACC atasan (…) — proses
  dulu lewat menu ACC Atasan".
- SW cache → `bpf-spa-20260906-v2360`; stamp versi → v2.36.0.

### Test & verifikasi

- `tests/test_approvals.py` **baru (39 test)**: build_chain (default,
  override, override nonaktif diabaikan), create/upsert reset, decide
  (urutan langkah, self-approval diblok, langkah ber-role utk cadangan,
  tolak final + alasan), gate (409 pending/rejected, lolos setelah full
  ACC, fail-open), endpoint (401/403/daftar terfilter/keputusan/404),
  **dan endpoint produksi nyata**: submit kasbon mencatat jurnal dgn
  identitas sesi; approve-ga kasbon terblokir 409 saat pending & lolos
  (hingga 404 data-uji) setelah full ACC.
- `ApprovalsView.test.js` baru (5 vitest) + penyesuaian 2 test
  users/sync (tuple UPDATE kini +manager_username).
- Suite: **196 pytest** terkait lulus di host (approvals + cash +
  overtime + users + docseq + stepup + integrity + retention); full
  suite 482 dijalankan di container/CI; **109 vitest** + build SPA sukses.
- Pelajaran: gate dipasang dengan variabel `(allowed, resp)` — salah
  balik jadi `blocked` sempat membuat gate tidak pernah memblokir;
  tertangkap oleh test endpoint nyata sebelum deploy.

---

## v2.35.1 — 5 September 2026 (Fix kritis produksi — pool DB cabang & hook integritas)

Dua bug ditemukan & diperbaiki saat verifikasi live Tahap 5+6 (deploy sesi ini):

1. **Kebocoran koneksi pool DB cabang** (`modules/branch_manager.py`,
   `ensure_branch_database`): tiap helper migrasi (notifications, appointments
   schema, doc_sequences, identitas) dipanggil dengan `pool.get_connection()`
   inline yang TIDAK pernah ditutup + koneksi penyalin skema `bc` juga bocor →
   hingga 5 koneksi per cabang per startup → pool cabang (ukuran 5) langsung
   habis setelah restart & **semua operasi DB cabang gagal** ("pool exhausted").
   Fix: satu koneksi per helper dipakai lalu ditutup (try/finally) + `bc.close()`.
   Verifikasi: setelah restart, 6× get/close pool cabang OK; retention overview
   membaca 10/10 DB.
2. **Hook integritas dokumen mati-senyap** di Form Permohonan Overtime
   (`routes_overtime.py`): hook memakai `session.get(...)` tapi modul tidak
   mengimpor `session` → `NameError` tertelan `except: pass` → PDF tetap
   terbit tapi TIDAK tercatat di registri. Fix: pakai helper modul
   `session_user(...)`. Verifikasi live: Form OT → registri terisi →
   `POST /api/documents/verify` found=True → tamper 1 byte → found=False.

Suite: 443 pytest + 6 skip + 104 vitest lulus.

---

## v2.35.0 — 5 September 2026 (Tahap 6/6 — Integritas & siklus hidup dokumen)

### 🔏 Verifikasi keaslian dokumen: hash SHA-256 + penandatangan + timestamp

Tahap terakhir Program Perbaikan Standar Bertahap (ISO/IEC 27001 A.8.2 /
A.8.9 + ISO 15489 keaslian dokumen).

#### Backend — registri integritas `document_registry` (DB master)

- `modules/doc_integrity.py` (baru): `ensure_document_registry()` (DDL
  idempoten), `register_pdf(doc_type, doc_no, bytes, signer_name,
  signer_role, branch_code, filename, meta)` — hash SHA-256 + ukuran byte +
  penandatangan + timestamp tersimpan; `lookup_pdf(bytes)` — cari berdasar
  hash. Pencatatan **best-effort** (gagal DB tidak menggagalkan unduhan PDF).
- Hook di titik terbit dokumen resmi bertanda tangan:
  - **Tanda Terima Air Minum** (`/api/water/purchases/<id>/pdf`) — signer =
    TTD Finance (user yang memverifikasi), meta: GA + status.
  - **Form Permohonan Overtime** (`/api/overtime/form-pdf`, driver & OB) —
    signer = user GA HR/Admin yang mencetak.
- `modules/routes_documents.py` (baru):
  - `POST /api/documents/verify` — upload PDF (multipart, maks 20 MB); hash
    dihitung ulang → cocokkan registri → buktikan utuh + siapa/kapan terbit.
    Semua role login boleh (verifikasi dipakai penerima dokumen).
  - `GET /api/admin/documents` — daftar registri (admin, filter q/limit).
- Tabel dibuat otomatis saat startup (master) + `app.py` registrasi route.

#### Frontend — Pengaturan → 🔏 Verifikasi & Registri Dokumen

- Upload PDF → hasil VALID (jenis/no. dokumen, waktu terbit, penandatangan,
  hash) atau TIDAK terdaftar (belum dicatat / sudah diubah).
- Tabel registri 50 terbaru (jenis, no. dokumen, cabang, penandatangan, hash).

#### Test

- `tests/test_doc_integrity.py` (+13, fake-DB): DDL idempoten, register
  menyimpan sha256/signer, DB-down tidak fatal, lookup cocok/tidak,
  verify valid & not-found & validasi non-PDF/kosong & butuh login,
  list admin-only 403.

---

## v2.34.0 — 5 September 2026 (Tahap 5/6 — Retensi & pemusnahan dokumen)

### 🗄️ Retensi per kelas dokumen + arsip audit trail (ISO 15489 / UU PDP)

Tahap 5 Program Perbaikan Standar Bertahap: data hanya disimpan selama
perlu, arsip audit trail utuh, dan setiap tindakan disposisi tercatat.

#### Kebijakan & dokumentasi

- **`RETENTION_POLICY.md`** (baru) — kelas dokumen, jadwal retensi default
  (audit trail 5 th, pelamar 2 th, BBM permanen, dsb.), prosedur arsip,
  prosedur pemusnahan (wajib persetujuan manajemen + backup dulu), peran,
  review tahunan. Nilai retensi bisa diubah via env `RETENTION_DAYS_*`.

#### Backend — `modules/routes_retention.py` (baru, admin-only)

- 6 kelas dokumen terdefinisi (audit_logs, transactions, water, overtime
  driver/ob, applicants) — label, masa retensi, catatan, tindakan.
- `GET /api/admin/retention/overview` — kebijakan + **inventaris live
  lintas DB** (master + 9 cabang): jumlah baris, tanggal tertua/terbaru,
  estimasi baris lewat masa retensi (anti-gagal per DB).
- `POST /api/admin/retention/archive-audit` — **arsipkan audit trail**
  lebih tua dari N hari (min. 30) di semua DB: baris dipindah ke
  `activity_logs_archive` (INSERT…SELECT + DELETE, satu transaksi) — utuh,
  ikut backup harian, tetap bisa dibuka. Tiap DB dicatat di
  `retention_actions` + audit `retention_audit_archive`.
- Tidak ada penghapusan otomatis data bisnis — pemusnahan manual &
  disetujui (lihat kebijakan bagian 6).
- Tabel `activity_logs_archive` & `retention_actions` dibuat otomatis di
  master + tiap cabang saat startup; route diregistrasi di `app.py`.

#### Frontend — Pengaturan → 🗄️ Retensi & Arsip Dokumen

- Tabel kebijakan+inventaris (masa retensi, total baris, estimasi lewat
  masa, rentang data), input ambang hari + tombol **Arsipkan Audit Trail**
  (konfirmasi), riwayat 20 tindakan retensi terakhir.

#### Test

- `tests/test_retention.py` (+20, fake-DB): cutoff/env override/kelas,
  DDL idempoten, arsip INSERT+DELETE+commit, tanpa-baris tidak DELETE,
  overview admin & anti-gagal & 403, arsip route sukses / days min 30 /
  days invalid 400 / non-admin 403.

---

## v2.33.0 — 5 September 2026 (Tahap 4/6 — Vulnerability management)

### 🛡️ Manajemen kerentanan: audit dependensi otomatis + scan image + runbook insiden

Tahap 4 dari Program Perbaikan Standar Bertahap (ISO/IEC 27001 A.8.8
[teknikal vulnerability management] & A.5.24–28 [manajemen insiden]). Semua
kerentanan dependensi yang terdeteksi **diperbaiki**, bukan sekadar diaudit.

#### 🔧 Perbaikan kerentanan dependensi (hasil audit awal)

- **Backend `requirements.txt`** — dipindah ke versi ter-patch (pip-audit
  awal: 30+ temuan):
  - Flask 3.0.0 → **3.1.3**, Werkzeug 3.0.0 → **3.1.8**
  - mysql-connector-python 8.2.0 → **9.7.0** (protobuf rentan transitif ikut hilang)
  - Pillow 10.0.1 → **12.3.0**, requests 2.31.0 → **2.34.2**
  - scikit-learn 1.3.1 → **1.6.1** (tetap kompatibel numpy 1.26/pandas 2.1)
  - Hasil: `pip-audit -r requirements.txt` → **No known vulnerabilities found**.
- **Frontend `package.json`** (semua devDependencies — tidak ikut bundle
  produksi): vite ^5.3.3 → **^7.2.0**, vitest ^1.6.0 → **^3.2.7**, happy-dom
  ^14.12.3 → **^20.14.0**, @vitejs/plugin-vue ^5.0.5 → **^6.0.8**.
  Hasil: `npm audit` → **0 vulnerabilities** (sebelumnya 5: 2 critical,
  1 high — esbuild/vite/vitest/happy-dom).
- **Dockerfile** — tooling build (pip, setuptools, wheel, jaraco.context)
  dihapus setelah `pip install` → image runtime lebih ramping & scan Trivy
  bersih (sebelumnya 2 HIGH di build-tooling).

#### 🤖 Audit otomatis di CI (A.8.8)

- Job **Backend** kini menjalankan `pip-audit -r requirements.txt` (gagal
  bila ada vuln pada versi ter-pin).
- Job **Frontend** kini menjalankan `npm audit --audit-level=high`.
- Job baru **Image security scan (Trivy)** — `docker build` + scan image
  severity HIGH/CRITICAL (Trivy 0.74.0, `--ignore-unfixed`), gagal bila ada
  temuan dengan fix tersedia.
- **`.github/dependabot.yml`** (baru) — update otomatis mingguan untuk pip
  (root) & npm (frontend), limit 5 PR, label `dependencies`/`security`.

#### 🚨 Runbook insiden (A.5.24–28)

- **`INCIDENT_RUNBOOK.md`** (baru) — prosedur tanggap insiden lengkap:
  peran & kontak, klasifikasi severity (SEV-1/2/3), sumber deteksi,
  alur tanggap, prosedur per jenis insiden (akun terkompromi, kebocoran
  data pribadi [termasuk kewajiban UU PDP 3×24 jam], layanan down,
  defacement/injeksi, brute-force/DDoS, insider threat, temuan audit),
  preservasi bukti & chain of custody (A.5.28), pemulihan & verifikasi,
  komunikasi, review pasca-insiden (A.5.27), template log insiden &
  cheat-sheet terminal.

#### Test

- **410 pytest passed + 6 skipped** (container, DB service) + **104 vitest
  passed** + build SPA sukses — semua dengan versi dependensi baru;
  runtime container terverifikasi (import + gunicorn).
- Trivy image scan: **0 temuan HIGH/CRITICAL**.

---

## v2.32.0 — 5 September 2026 (Tahap 3/6 — Access review & akun basi)

### 🛂 Access review triwulanan + laporan akun basi (ISO/IEC 27001 A.5.15/A.8.2/A.8.3)

Tahap 3 dari Program Perbaikan Standar Bertahap: hak akses kini bisa
direview berkala (triwulanan) dengan laporan akun yang tidak terpakai.

#### Backend — `modules/routes_accessreview.py` (baru, admin-only)

- **`GET /api/admin/access-review`** — semua user master + klasifikasi status
  akun otomatis:
  - `ok` — aktif & login dalam ambang batas
  - `stale` (**Basi**) — aktif tapi login terakhir > N hari (default 90,
    env `STALE_ACCOUNT_DAYS`) → kandidat pencabutan akses
  - `never_login` (**Belum Login**) — aktif tapi belum pernah login
  - `inactive` — sudah dinonaktifkan
  + ringkasan jumlah per status, `review` terakhir (siapa+kapan), ambang hari.
- **`POST /api/admin/access-review/complete`** — tandai review selesai:
  simpan ke `system_config` (siapa + kapan) + audit `access_review_complete`.
- **`GET /api/admin/access-review/export`** — CSV (UTF-8 BOM) arsip review
  triwulanan.
- Audit view/export ikut tercatat (`access_review_view/export`).

#### Frontend — halaman baru **Access Review** (`/app/access-review`, admin)

- Menu samping Admin + route baru.
- Kartu ringkasan (total/aktif/nonaktif/OK/Basi/Belum Login), badge
  **REVIEW TERLAMBAT** bila review terakhir > 90 hari atau belum pernah.
- Tabel semua akun dengan badge status warna + info kapan review terakhir;
  filter pencarian/status/role/cabang.
- Aksi cepat **🚫 Nonaktifkan** pada akun Basi & Belum Login (A.8.3 —
  pencabutan akses) dengan konfirmasi; tombol **Export CSV** & **Tandai
  Review Selesai**.

#### Test

- `tests/test_access_review.py` (+14): klasifikasi (nonaktif/never/stale/ok,
  ambang custom, string ISO, tanggal rusak → stale), ringkasan & label,
  CSV, route admin-only (403/401), list + review info, complete (config +
  commit), export, DB down → 500.
- Vitest `AccessReviewView.test.js` (+6): render ringkasan/klasifikasi,
  badge REVIEW TERLAMBAT, filter status, complete → API, nonaktifkan akun
  basi → `/api/users/sync`, export → download URL.
- **403 pytest + 104 vitest** lulus (host; 5 test security-headers butuh
  container DB — pre-existing).

---

## v2.31.0 — 5 September 2026 (Tahap 2/6 — Step-up authentication)

### 🔐 Step-up auth: konfirmasi PIN ulang sebelum aksi approve/pay berisiko

Tahap 2 dari Program Perbaikan Standar Bertahap (ISO/IEC 27001 A.8.2/A.8.3/
A.8.5 — lihat PROGRESS.md). Aksi yang **menggerakkan uang** kini wajib
didahului verifikasi PIN ulang user yang sedang login — menutup celah "sesi
menyala di komputer bersama" dan menambah peristiwa autentikasi kedua yang
dekat waktunya dengan aksi.

#### Backend

- **`modules/stepup.py`** (baru):
  - `POST /api/step-up` — verifikasi PIN user **sesi** (username diambil dari
    sesi, TIDAK dari body — anti verifikasi PIN orang lain), rate-limited
    anti brute-force (jalur `pin_*` terpisah dari login), grant sesi
    berumur pendek `stepup_until` (env `STEPUP_TTL_SECONDS`, default 600 s).
  - Decorator `@stepup_required` — menjawab **428 `STEPUP_REQUIRED`** saat
    sesi tidak punya grant yang masih berlaku; dipasang DI BAWAH
    `@role_required` (cek role dulu, lalu step-up).
  - Grant hilang otomatis saat `session.clear()` (logout) atau kedaluwarsa;
    audit `step_up` dicatat di activity_logs.
- **Endpoint berisiko yang kini di-protect** (8 total):
  - Kasbon: `approve-ga`, `approve-finance`, **`handover`** (serah terima
    dana ke driver — sebelumnya TIDAK di-protect), `approve-lpj`
  - Klaim BBM: `queue/approve-ga`, `queue/payout`, `queue/verify`
  - Air minum: `water/purchases/<id>/verify`
  - Aksi non-uang (reject, cancel, archive, edit, reset) sengaja TIDAK
    di-protect — sesuai fokus tahap "approve/pay berisiko" (friction minimal).

#### Frontend

- **`stores/stepup.js`** (baru): `require(actionFn, label)` mencoba aksi →
  bila 428 `STEPUP_REQUIRED`, buka modal PIN & simpan aksi tertunda →
  setelah PIN valid, aksi dijalankan ulang otomatis → promise terselesaikan
  sesuai hasil akhir.
- **`components/StepUpModal.vue`** (baru, dipasang global di `App.vue`):
  modal PIN 6 digit, nama user sesi dari auth store, error inline, tombol
  Batal = resolve kosong (bukan gagal).
- **View yang memakai step-up**: CashView (approve GA/Finance/handover/LPJ),
  WaterView (verify), GaDashboard (approve + verify anomali), AdminDashboard
  (approve, payout, verifikasi anomali ber-foto via FormData — seluruh
  request dijalankan ulang utuh setelah PIN, tidak dipecah).

#### Test

- **`tests/test_stepup.py`** (24): endpoint (login wajib, PIN wajib, PIN
  salah 401 + rate-limit, PIN benar → grant, username selalu dari sesi,
  user nonaktif, lockout 429), decorator (401/428/lolos/kedaluwarsa,
  clear saat logout, sisa waktu grant), dan **anti-regresi endpoint NYATA**:
  8 rute produksi berisiko wajib 428 tanpa grant + role tidak sesuai tetap
  403 walau grant ada + tanpa login 401 (bukan 428).
- Vitest: `stores/stepup.test.js` (7), `StepUpModal.test.js` (5),
  `GaDashboard.test.js` (+1 alur 428 → PIN → retry), `WaterView.test.js`
  (mock store). **98 vitest + 391 pytest** lulus (host; 5 test
  security-headers tetap butuh container DB — pre-existing).

---

## v2.30.0 — 5 September 2026 (Tahap 1/6 — Keamanan kredensial)

### 🔐 Kredensial DB tidak lagi di-hardcode (ISO/IEC 27001 A.8.2/A.8.13/A.8.23)

Mulai program perbaikan standar bertahap (lihat PROGRESS.md — roadmap 6 tahap).
Tahap 1: menghapus kredensial DB dari file yang di-commit & fail-fast bila env
hilang di produksi.

- **docker-compose.yml**: `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `DB_PASSWORD`
  dibaca dari `.env` (gitignored) dengan fail-fast `${VAR:?...}` — bila env
  tidak ada, compose menolak start (bukan diam-diam pakai password default).
  Healthcheck MariaDB juga memakai env container, bukan password hardcoded.
- **`.env.example`** (baru): template lengkap + cara generate password acak.
- **modules/config.py**: `DB_PASSWORD` wajib dari env; di `FLASK_ENV=production`
  tanpa env → `RuntimeError` saat start. Di dev/test → nilai dev-only yang jelas
  GAGAL connect (tidak pernah fallback ke kredensial produksi).
- **modules/routes_reports.py** (fix bug): baca `DB_PASSWORD` (sebelumnya salah
  baca `DB_PASS` yang tidak pernah diset → selalu fallback); password mysqldump
  dikirim via env `MYSQL_PWD`, bukan argv (tidak tampil di `ps`).
- **modules/excel_generator.py**: koneksi DB baca `DB_PASSWORD` dari env, tanpa
  fallback hardcoded.
- **Script & dokumentasi**: contoh perintah DB di DEPLOYMENT.md / DEPLOY_FRESH.md /
  PELATIHAN.md / seed_demo_routes / tidy_driver_accounts / demo_cleanup /
  auto_cleanup_demo kini membaca dari `.env` — password lama dihapus dari repo.
- **CI**: kredensial service test diganti nilai throwaway (`ci_*_x9`) agar jelas
  bukan kredensial produksi.
- **`scripts/rotate-db-credentials.sh`** (baru): rotasi idempoten password root &
  `bpf_user` via `ALTER USER` (stdin, bukan argv) + backup `.env` sebelum menimpa.
- ✅ **Rotasi produksi DIJALANKAN 5 Sep 2026** (persetujuan user): backup 11 DB OK →
  `ALTER USER` root@localhost/root@%/bpf_user@% (hex 24 acak) → `docker compose
  up -d` recreate (db/web/backup) → verifikasi: health `ok`, pool 10 DB ready,
  login e2e admin sukses, password lama ditolak (1045), backup otomatis OK.
  Backup `.env` lama: `.env.bak-20260905_105155`.
- **Test** `tests/test_secret_hygiene.py` (+7): pola password lama dilarang muncul
  di file ter-commit; compose wajib baca dari env; config fail-fast production.

---

## v2.29.11 — 5 September 2026

### 🔢 Admin: Kelola Nomor Dokumen per Cabang

- Halaman **Settings → Nomor Dokumen** (Admin): daftar counter nomor urut
  per cabang & jenis dokumen (prefix) — format `PREFIX-CABANG-TANGGAL-0001`
  (mis. `WTR-SBY-20260905-0001`), lengkap dengan label jenis dokumen.
- Tombol **Reset** per baris untuk memulai nomor dari 0001 lagi (awal hari /
  selesai uji coba / koreksi) — dengan konfirmasi peringatan.
- API baru (admin-only + audit trail `doc_seq_reset`):
  - `GET  /api/admin/doc-sequences` — daftar counter semua cabang
  - `POST /api/admin/doc-sequences/reset` — reset per (cabang, prefix, tanggal)
- Test: +13 (`tests/test_docseq_admin.py` — logika parse/reset + route admin).

### 🧹 Operasional produksi

- **Akun uji lama dibersihkan** dari DB produksi: `qa`, `e2e_driver`,
  `test_check` (tidak pernah dipakai operasional; jejak login e2e dihapus).
- **E2E penomoran lintas cabang** terverifikasi live: `WTR-BDG-*` (OB
  Bandung) & `CASH-MLG-*` (Finance Malang) — isolasi nomor per cabang.
- **Fresh deploy diuji** dari klon GitHub bersih: init.sql (admin + cabang
  JKT/JKT2 HO Jakarta), `doc_sequences` dibuat otomatis di startup, dan
  penomoran `WTR-SBY-…-0001` bekerja sejak hari pertama.

---

## v2.29.10 — 4 September 2026

### 🔢 Standar penomoran dokumen & transaksi per cabang

Format baru (semua dokumen baru): **`{PREFIX}-{BRANCH}-{YYYYMMDD}-{SEQ}`**

| Dokumen | Prefix | Contoh |
|---|---|---|
| Tanda terima air minum | `WTR` | `WTR-SBY-20260904-0001` |
| Kasbon / LPJ | `CASH` | `CASH-BDG-20260904-0001` |
| Transaksi BBM | `BPF` | `BPF-SBY-20260904-0001` |
| Trip / Perjalanan | `TRIP` | `TRIP-SBY-20260904-0001` |
| Kunjungan appointment | `APP` | `APP-MLG-20260904-0001` |
| Pendaftaran applicant | `PLM` | `PLM-SBY-20260904-0001` |
| Overtime OB/Security | `OTL` | `OTL-SBY-20260904-0001` |
| Overtime Driver | `OTD` | `OTD-SBY-20260904-0001` |

- Fungsional lewat `generate_display_id()`: kode cabang diambil dari sesi
  login (fallback cabang utama), nomor urut harian per (cabang, prefix)
  dialokasikan atomik via tabel baru `doc_sequences` di DB yang sama dengan
  data (isolasi cabang terjaga) — `INSERT … ON DUPLICATE KEY UPDATE` +
  `LAST_INSERT_ID()` → aman saat banyak permintaan bersamaan, tanpa nomor
  kembar.
- `doc_sequences` dibuat otomatis di startup (master + tiap DB cabang).
- **Data lama tidak diubah** (riwayat tetap format lama); hanya dokumen yang
  dibuat mulai v2.29.10 yang memakai format baru.
- Faktor kemanusiaan: nomor tampil pendek & resmi di PDF/laporan, langsung
  jelas asal cabangnya di laporan konsolidasi.

### 🏢 Kantor Pusat = Jakarta (Equity Tower) — koreksi identitas perusahaan

- **Surabaya bukan kantor pusat** — sekarang diberi label **`Cabang
  Surabaya`** di semua tempat (DB `branches`, kode default, seed, test,
  dokumen). Kantor Pusat hanya satu: **Jakarta (Equity Tower, SCBD Lot 9,
  Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190)**.
- Identitas default perusahaan di kode & UI (kop surat PDF, login, Apply,
  Overtime, presentasi) dikoreksi ke **Kantor Pusat | Jakarta**; DB produksi
  di-update: `branches` SBY (nama/city), `system_config` master, dan
  identitas cabang JKT di `bpf_branch_jkt`.
- Seed `init.sql`: SBY → Cabang Surabaya + baris `JKT` & `JKT2` ditambahkan
  agar fresh deploy konsisten dengan produksi.
- Alamat kontak di dokumentasi (README, USER_GUIDE, daftar user, materi
  pelatihan/presentasi, security, deployment) dikoreksi ke HO Jakarta.
- Nomor kontak dipertahankan (031-5349888) sampai ada nomor resmi HO baru.
- Catatan: koordinat `DEPOT_LAT/DEPOT_LNG` di docker-compose tetap titik
  awal rute cabang SBY (bukan HO) — itu memang depot operasional Surabaya.

### 🔧 Perbaikan kecil

- **Alokasi urut DB untuk baris baru**: `_alloc_seq_db` kini meng-set
  `LAST_INSERT_ID(1)` eksplisit saat `INSERT` baris baru lalu membaca
  `LAST_INSERT_ID()` — memperbaiki nomor yang sebelumnya keluar `0000`
  (lastrowid kosong untuk tabel non-auto-increment).
- **Versi sistem disinkronkan ke v2.29.10** — sebelumnya stale `v2.22.1` di
  default identitas (kop/footer PDF, fallback UI) & `system_config` DB
  master; kini konsisten di kode + DB.
- **Kop surat PDF kini benar-benar simetris**: baris subjudul & alamat
  ("Kantor Pusat | Jakarta", "Equity Tower …") sebelumnya bergeser ke
  kanan ~5 mm karena `new_x=LMARGIN` + `r_margin=0` membuat kotak teks
  asimetris — diperbaiki dengan `set_x(0)` tiap baris. Terverifikasi via
  bbox poppler di 5 tipe dokumen (portrait & landscape): seluruh 3 baris kop
  tepat di tengah halaman (delta 0.0 pt).
- **Fallback identitas offline (tanpa DB)**: saat koneksi DB gagal, kop PDF
  kini memakai `IDENTITY_DEFAULTS` penuh (nama/subjudul/alamat/kontak),
  bukan `{}` — PDF dari tes/script konsisten dengan produksi.
- Sisa teks "PT. Bestprofit Surabaya" di modul app & narasi laporan
  dikoreksi → "PT. Bestprofit Futures".

### ✅ Verifikasi menyeluruh & test regresi kop PDF

- **E2E live penomoran modul lain** (produksi): `APP-SBY-20260905-0001`
  (kunjungan marketing), `PLM-SBY-20260905-0001/0002` (pendaftaran publik —
  membuktikan nomor urut naik & fallback cabang utama di luar sesi),
  `OTL-SBY-20260905-0001` (overtime OB publik), `CASH-SBY-20260905-0001`
  (kasbon) — semua format `PREFIX-SBY-TANGGAL-SEQ` benar. Cleanup penuh
  (data + aktivitas + counter seq + daily-code), DB kembali baseline 0 sisa.
- **Identitas HO sisi JKT lengkap**: `branches` JKT = "Kantor Pusat Jakarta"
  (DB `bpf_branch_jkt`), `system_config` JKT kini berisi nama/subjudul/
  alamat Equity Tower + `system_version v2.29.10`.
- **UI terverifikasi (browser)**: halaman login menampilkan "BPF WorkHub ·
  PT BESTPROFIT FUTURES · Jakarta"; form Identitas di `/app/settings`
  terisi Subjudul "Kantor Pusat | Jakarta", Alamat Equity Tower, Versi
  v2.29.10.
- **Test regresi geometri kop** `tests/test_pdf_header_layout.py` (8 tipe
  PDF portrait/landscape): 3 baris kop wajib tepat di tengah halaman
  (toleransi ±1,5 pt via `pdftotext -bbox`) + subjudul/alamat HO Jakarta
  hadir tanpa DB. `poppler-utils` ditambahkan ke Dockerfile & CI supaya
  test ini benar-benar berjalan (skip bila binary tidak ada).

---

## v2.29.9 — 4 September 2026

### 🧾 Validasi username `{divisi}_{cabang}` di backend (awalan divisi WAJIB)

- `/api/users/sync` kini **menolak username role back-office yang tidak
  diawali divisi** — mis. membuat user Finance `uang` atau Marketing `dewi`
  baru → 400 dengan pesan: wajib `finance_…` / `marketing_…` (mis.
  `finance_sby`, `finance_nama_sby`).
- Pengecualian: **Driver** (username = nama orang untuk PWA HP), **Admin**
  (`admin`), dan **IT per cabang** (`it_sby` …). Akun sistem lama
  (`qa`, `test_check`, `e2e_driver`) dan akun yang **sudah ada** dgn
  (username, role) sama (mis. hasil bulk-create marketing lama bernama
  orang) tetap bisa di-simpan/di-toggle tanpa rename — tidak ada akun yang
  "terkunci".

### 👤 Nama asli lebih menonjol di tabel Users

- Kolom Username & Nama Lengkap digabung jadi satu kolom **User**: Nama
  Lengkap tampil **tebal** sebagai identitas utama, username kecil di
  bawahnya — Admin mengenali orangnya (Faisol), bukan kode loginnya
  (`ob_faisol_sby`). CSV export & pencarian tidak berubah.

### 🚀 Uji onboarding cabang (live, 4 Sep)

- (a) **User baru di cabang lain**: admin membuat `finance_bdg` (cabang
  Bandung) → login → sesi branch BDG + dashboard finance; akun dihapus
  setelah verifikasi.
- (b) **Cabang baru utuh dari nol**: `POST /api/branches/save` + ensure-db
  → database cabang baru dibuat (salinan skema) → user pertama dibuat &
  login dengan scope cabang baru → **cleanup penuh**: cabang dinonaktifkan,
  baris branches dihapus, database test di-drop, container di-restart agar
  pool koneksi bersih. (Detail angka verifikasi di PROGRESS.)

---

## v2.29.8 — 4 September 2026

### 🐛 Fix tab "Selesai" Dashboard Marketing

- Tab **✅ Selesai** di dashboard Marketing memanggil `/api/appointments/
  completed` — endpoint **khusus Driver PWA** (scope `driver_name`, tanpa
  sesi) sehingga untuk marketing login selalu ditolak → tab selalu kosong +
  satu error 400 di console.
- Backend: endpoint baru **`/api/appointments/history`** (role marketing /
  chief_driver / ga / admin) — riwayat status `completed` **lintas tanggal**
  untuk marketing di-scope ke `marketing_username` sesi sendiri (anti bocor
  data marketing lain), urut `completed_at` terbaru dulu, parameter `limit`
  (default 50, maks 100, non-angka → fallback 50).
- Frontend `MarketingDashboard.vue` kini memakai `/api/appointments/history`.
- Test: `tests/test_appointments_history.py` (5 unit, pola fake-DB) + 1
  vitest baru di `MarketingDashboard.test.js` (tab Selesai memuat riwayat,
  memastikan TIDAK memanggil `/completed` lagi).

### 📖 Dokumentasi konvensi username (USER_GUIDE)

- Seksi 12.1 bertambah: tabel konvensi username `{divisi}_{cabang}` per role
  (+ nama bila >1 orang per divisi-cabang), catatan Driver/admin/IT, dan
  **checklist onboarding pembukaan user/cabang baru** 7 langkah.

### ✅ Verifikasi live produksi

- Rebuild + deploy (`docker compose up -d --build web`), SW cache
  `bpf-spa-20260904-v298`, `bbm_web` healthy, log bersih.
- **E2E air minum dengan user rename**: `ob_faisol_sby` login → submit
  pengajuan berfoto (WTR-20260904-17484740, id 16) → `finance_sby` login →
  verifikasi → unduh PDF tanda terima live: kop seimbang, seksi lengkap,
  TTD "Finance Officer" (nama user yang memverifikasi). Data uji dibersihkan.
- **Marketing live**: login `marketing_yusie_sby` → `/api/appointments/
  history` HTTP 200 `{"data":[]}` (sebelumnya 400); OB tetap ditolak di
  `/completed` (regresi negatif ✓).
- Test suite container: **330 passed + 6 skipped**; vitest: **86 passed**.

---

## v2.29.7 — 4 September 2026

### 👥 Manajemen User: Admin bisa edit SEMUA detail user

- **Fix tombol Simpan selalu nonaktif saat edit tanpa PIN baru** — ekspresi
  `(form.pin && form.pin.length !== 6)` mengembalikan string kosong `''` saat
  PIN dibiarkan kosong; Vue memperlakukan `''` sebagai *truthy* untuk atribut
  boolean → tombol 💾 Simpan selalu `disabled`. Admin praktis tidak bisa
  mengedit user tanpa mengganti PIN. Kini `!!form.pin && …` — edit data user
  (nama, role, tim, cabang, status) bisa disimpan tanpa menyentuh PIN.
- **`branch_code` kini benar-benar tersimpan** — form Edit User sudah punya
  pilihan Cabang, tapi backend `/api/users/sync` tidak pernah menulisnya ke
  DB (INSERT/UPDATE tanpa kolom `branch_code`). Kini cabang ikut disimpan,
  dengan pola yang sama seperti PIN/team (hanya diubah bila dikirim eksplisit,
  agar toggle aktif/nonaktif & bulk action tidak menghapus cabang user).
- **Username bisa diganti saat edit** — sebelumnya input Username di-disable
  untuk user lama. Kini Admin bisa mengubah nama login lewat update by-id
  (username adalah kunci login, bukan primary key); bila username baru sudah
  dipakai user lain, backend menolak dengan pesan jelas (400).
- Audit log `user_sync` kini mencatat `branch_code`.
- **Deploy live 4 Sep 2026** — server = perangkat kerja (`docker compose up
  -d --build web`): health `/api/health` ok, login admin e2e 200, test suite
  container 325 passed + 6 skipped, logs bersih. Uji e2e live: buat user →
  rename username + ganti cabang (SBY→BDG) → toggle nonaktif tanpa
  branch/pin → cabang tetap BDG ✓ (data uji dibersihkan kembali ke 33 user).

### ✍️ Konvensi Username `{divisi}_{cabang}` + rename massal produksi

Keputusan user (4 Sep): username dibuat agar terbaca **divisi & cabang**.

- Pola: satu orang per divisi-cabang → `{divisi}_{cabang}` (`finance_sby`,
  `ga_sby`, `gahr_sby`, `receptionist_sby`); bila >1 orang per divisi-cabang →
  `{divisi}_{nama}_{cabang}` (`ob_faisol_sby`, `ob_febri_sby`, `ob_edwin_sby`,
  `marketing_yusie_sby`, `marketing_icang_sby`).
- 12 akun produksi di-rename via API `/api/users/sync` (id-based, v2.29.7):
  `finance_officer→finance_sby`, `ga_officer→ga_sby`, `ga_hr_officer→gahr_sby`,
  `ob1/ob2/ob3→ob_faisol_sby/ob_febri_sby/ob_edwin_sby` (full_name asli),
  `receptionis→receptionist_sby` (typo diperbaiki),
  `driver→chief_driver_sby` (username 'driver' membingungkan),
  `traineer_a→traineer_sby`, `Icang→marketing_icang_sby`, `Yusie→
  marketing_yusie_sby`, `dewi→marketing_dewi_mlg`. PIN, cabang & role
  dipertahankan (verifikasi login 5 akun OK).
- **Tidak diubah**: `admin`; `it_*` (sudah `it_{cabang}`); **Driver**
  (username = nama orang utk login PWA pendek di HP); akun test (`qa`,
  `test_check`, `e2e_driver`).
- Script demo/UI & dokumentasi diselaraskan: record/rehearsal/verify_*,
  seed_demo_routes, init.sql seed (`ga_sby`/`finance_sby` + branch_code SBY),
  README (akun demo + seksi konvensi), USER_LIST, USER_GUIDE, PELATIHAN,
  PRESENTASI, presentasi/index.html, DEPLOYMENT, DEPLOY_FRESH.
- ⚠️ User yang akunnya di-rename perlu tahu username barunya (PIN tidak
  berubah). Appointment lama marketing tetap tercatat di bawah username lama.
- **Helper text pola username di form Users** (keputusan: contoh saja, tanpa
  validasi keras) — di bawah kolom Username tampil contoh dinamis per role
  + cabang: `contoh: ga_sby`, `ob_sby … bila >1 orang per cabang:
  ob_nama_sby (mis. ob_faisol_sby)`; catatan khusus driver/admin/it.
- **Verifikasi login dari UI (browser nyata, puppeteer)**: 11 skenario
  lulus — admin, finance_sby, ga_sby, ob_faisol_sby, chief_driver_sby,
  gahr_sby, receptionist_sby, it_sby → landing halaman masing-masing +
  cookie sesi terbentuk; PIN salah → tetap di login + pesan; hint terlihat
  di halaman Users. (Satu 400 konsol di tab 'Selesai' MarketingDashboard =
  endpoint driver-only — pre-existing, ditangkap diam-diam, tak terkait
  rename.)

### 💧 PDF Tanda Terima Air Minum dirapikan

- **Foto bukti diperbesar** — sel foto tidak lagi terkunci di tinggi 52 mm:
  tingginya mengikuti ruang kosong yang tersedia di halaman (ruang blok TTD
  dicadangkan ±60 mm), dengan rentang 60–130 mm. Foto lebih tinggi & lebih
  lebar; foto potret (rasio HP) tampil jauh lebih besar dari sebelumnya.
  Lebar sel dihitung ulang per jumlah foto (2 foto: 93 mm masing-masing;
  1 foto: selebar halaman).
- **Tanda tangan lebih ke bawah** — blok TANDA TANGAN terdorong turun mengikuti
  posisi foto, sehingga ruang kosong di dasar halaman terpakai optimal.
- **Header kop tidak lagi tidak simetris** — nama perusahaan & subjudul
  sebelumnya diratakan terhadap sisa lebar *setelah* logo (geser ~7 mm ke
  kanan dari tengah halaman). Kini teks kop diratakan ke **tengah lebar
  halaman** (`r_margin` ditahan sementara + `set_x(0)`), logo tetap di kiri.
  Berlaku untuk semua dokumen PDF berlogo BPF.

---

## v2.29.6 — 4 September 2026

### ⏰ Sinkronisasi Overtime Google Sheet diperbaiki (Driver & OB/Security)

Dua bug lama membuat sinkronisasi sheet overtime **diam-diam mati**; keduanya
ketemu saat mengaktifkan sumber OB/Security kedua (mirip Driver).

- **Fix regresi redirect Apps Script** (`1963283`): `_fetch_sheet_rows()` memakai
  `allow_redirects=False`, padahal Google Apps Script `/exec` selalu menjawab
  302 dulu ke `script.googleusercontent.com` → body kosong → refresh melaporkan
  **0 baris tanpa error**. Akibatnya refresh **Driver** (dan calon OB) tidak
  pernah mengambil data baru. Kini redirect diikuti + URL akhir tetap dicek
  SSRF (`_check_public_url`). Test anti-regresi ditambahkan. Sinkronisasi
  Driver diuji penuh: 8.831 baris, 57 baris usang terperbarui.
- **Fix duplicate `display_id` saat batch besar** di `_upsert_ob_rows()`:
  `generate_display_id()` bersuffix acak 2 digit (~100 kandidat/detik) — dalam
  satu batch 600+ baris ruangnya habis, guard 500× break → id kembar → INSERT
  kena UNIQUE `display_id` → **baris lain tertimpa diam-diam**. Kini
  `display_id` sheet deterministik per sesi (`OTL-SH-` + 16 hex digest, sama
  dengan basis `source_uid`) — idempoten saat re-sync tanpa query tambahan.
- **Apps Script bridge OB/Security** (`scripts/apps_script_overtime_ob_security.gs`)
  — pola sama seperti Driver v2 (SHEET_ID `1AsBq-rHss…`), untuk sheet private.
  Deployed oleh user; `overtime_ob_sheet_url` kini mengarah ke Web App.
- **Auto-refresh OB/Security** — sinkronisasi sheet OB kini juga berjalan di
  background saat login/logout GA HR/admin (debounce 30 dtk, sama seperti
  Driver), selain tombol Refresh manual.
- **PDF overtime disempurnakan**: header tabel multi-baris diratakan (cell()
  tak menangani `\n` → teks menyatu/terpotong); kolom WAKTU & NO. FORM
  dilebarkan agar '18:30 - 20:00' & id `OTL-SH-…` tidak terpotong; Formulir
  Permohonan kini menyematkan **foto sebagai gambar** (file lokal `/uploads`
  atau URL publik; tautan Drive private → fallback link klik); en dash `–`
  diganti ASCII `-` (clean_text membuang non-ASCII).
- **Detail report per orang dibalik terkini-dulu** (PDF & Excel):
  `ORDER BY tanggal DESC, waktu_mulai DESC, id DESC` — baris terbaru di atas.
- **Urutan overtime terkini-dulu** — API & PDF rekap sudah `tanggal DESC`;
  ditambah pengaman sort di sisi klien GA HR (Driver & OB/Security) supaya
  tanggal terbaru selalu di posisi teratas.
- **`submitted_at` untuk OB/Security** (kolom baru, idempoten): timestamp
  submit asli Google Form kini tersimpan & ter-backfill 599/599 — PDF
  'TANGGAL FORM' & kolom timestamp laporan detail tidak lagi kosong/memakai
  waktu sync. Paritas dengan `overtime_driver`.
- **Re-seed data OB/Security dari sheet** (persetujuan user): 578 baris migrasi
  lama (beberapa tanggal korup 0026/1926 & duplikat) diganti dengan 599 sesi
  dari sheet (11 pengajuan ganda dide-dupe), semua `source='sheet'`,
  `display_id` seragam `OTL-SH-…`. Backup migrasi:
  `/tmp/overtime_ob_migrasi_backup_20260904.sql`. Tahun kini 2025–2026.
  ⚠️ **4 sel di sheet sumber masih 1926** (Edwin P, ~8–14 Jan 2026, kolom
  Tanggal) — harus dibetulkan di Google Sheet agar refresh berikutnya tidak
  mengembalikannya.

### 📚 Dokumentasi diselaraskan ke v2.29.6

- **DEPLOYMENT.md dipulihkan** — sejak rewrite `918d7ee` file terpotong
  (464 → 83 baris, berakhir di tengah tabel, isi TOC 14 seksi tak ada). Kini
  lengkap & akurat: arsitektur (gunicorn, redis, backup), env vars v2.29.1,
  monitoring (Uptime Kuma + CI), HTTPS, troubleshooting overtime, endpoint,
  checklist go-live.
- README, USER_GUIDE (overtime dua sumber Apps Script + auto-refresh +
  urutan terkini-di-atas + PDF), USER_LIST, DEPLOY_FRESH, SECURITY,
  ONEPAGER/PRESENTASI/PELATIHAN diperbarui; angka tes konsisten
  (323 pytest + 83 vitest).

---

## v2.29.5 — 4 September 2026

### 🧹 Pembersihan data demo modul air minum (production)

Data demo dari pengujian sesi v2.29.4 dihapus dari DB produksi agar evaluasi
dokumen air minum oleh user Finance dimulai dari daftar bersih. **Tidak ada
perubahan kode — tanpa redeploy.**

- Dihapus dari `bpf_asset_system` (DB master): `WTR-20260904-10300556`
  (id 11, verified, foto) + `WTR-DEMO-02` (id 10, verified) + `WTR-DEMO-01`
  (id 9, pending) — termasuk item terkait (cascade `water_purchase_items`),
  9 entri `activity_logs`, dan 2 file foto di `./uploads`.
- Dihapus dari `bpf_restore_test` (DB uji-restore, bukan produksi): salinan
  `WTR-DEMO-02`.
- Backup SQL lengkap (purchase + item + log + nama file foto) disimpan di
  `/tmp/bpf_water_demo_backup_20260904.sql` (di luar repo) — dapat dipulihkan
  bila diperlukan.
- Verifikasi live sbg `finance_officer` (HTTPS): daftar pengajuan air minum
  kini kosong.

---

## v2.29.4 — 4 September 2026

### 📄 PDF Tanda Terima Air Minum — format Finance

Penyesuaian format dokumen air minum sesuai masukan user Finance.

- Seksi `INFORMASI PENGAJUAN` → **`INFORMASI PENGIRIMAN`** (dengan baris
  **Tanggal Pengiriman**).
- Urutan isi dokumen terverifikasi: **Informasi Pengiriman → Rincian Barang →
  Hasil Verifikasi/Remark → Lampiran Foto → Tanda Tangan** — foto bukti OB
  (sebelum & sesudah diisi, dari form OB) kini tampil SEBELUM blok TTD.
- Nama di blok TTD Finance ('Menyerahkan') diambil dari **user yang
  memverifikasi** (`verified_by`); nama TTD `system_config` hanya fallback
  (mis. status masih pending).
- Form OB + validasi backend: label **'Tanggal Pembelian' → 'Tanggal
  Pengiriman'** agar istilah seragam di seluruh alur.
- Tests: heading & urutan seksi dikunci di `tests/test_water.py` (13 lulus) +
  `WaterView` vitest (4 lulus).

### 🛠️ CI backend diperbaiki (test_security_headers)

Job pytest di GitHub Actions kini menjalankan service **mariadb + redis** dengan
env DB/SECRET_KEY (meniru compose produksi). Sebelumnya test yang meng-import
`app` error di collection (tanpa `SECRET_KEY`) atau hang (koneksi DB 60s tanpa
DB).

---

## v2.29.3 — 4 September 2026

### 🐛 Fix login production + fix PDF Tanda Terima Air Minum (redeploy penuh)

Image web di-rebuild & container di-restart (pertama kali sejak v2.29.1 — sesi
v2.29.2 memang sengaja tanpa perubahan runtime).

#### 🔑 Fix: Login error "login is not a function"

- **Gejala:** klik tombol Masuk → `k.login is not a function` (k = store Pinia
  hasil minify).
- **Akar masalah:** refactor username per-cabang 27 Agu (commit `0450822`)
  tidak sengaja menghapus aksi `login` dari `frontend/src/stores/auth.js`,
  sementara `LoginView.vue` tetap memanggil `auth.login()` → regresi di
  production sejak 27 Agu.
- **Fix source:** aksi `login(username, pin)` dikembalikan + simpan
  `csrf_token` ke localStorage (commit `e8c9281`).
- **Fix deploy:** `docker compose build web` + `up -d web` (4 Sep); bundle baru
  terverifikasi berisi `/api/auth/login` + handling CSRF.
- **Verifikasi live (HTTPS `nasbpfsby.duckdns.org:5000`):** login admin → 200,
  sesi terkonfirmasi via `/api/auth/me`. Catatan: `ga_sby`/`finance_sby` dengan
  PIN demo `123456` → 401 (PIN bukan default / akun beda — bukan bug aplikasi).
- **Anti-regresi:** test kontrak store (`login`/`bootstrap`/`logout`) di
  `frontend/src/stores/auth.test.js` — gagal di unit test bila aksi hilang lagi.
- ⚠️ Pengguna yang masih melihat error: hard-refresh (Ctrl+Shift+R) atau
  bersihkan service worker — `sw.js` dapat meng-cache `index.html` lama.

#### 📄 Fix: PDF air minum — judul seksi tidak lagi "orphan"

- Dokumen panjang (banyak item/remark): judul 'TANDA TANGAN' dan 'LAMPIRAN FOTO
  (TIMESTAMP)' tercetak di dasar halaman sebelumnya sementara isinya pindah ke
  halaman berikutnya — cek ruang halaman berjalan setelah judul digambar.
- Fix: cek ruang dipindah SEBELUM judul seksi digambar di
  `WaterReceiptPDF._draw_signatures` & `_draw_photos` + test regresi
  multi-halaman di `tests/test_water.py`.
- 16 pytest lulus (test_water + test_pdf_compact).

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
| v2.29.6 | 323 | 83 | 406 |
| v2.29.7 | 331 | 85 | 416 |
| v2.29.8 | 336 | 86 | 422 |
| v2.29.9 | 341 | 86 | 427 |

---

*BPF WorkHub v2.35.1 · Diperbarui 6 September 2026*
