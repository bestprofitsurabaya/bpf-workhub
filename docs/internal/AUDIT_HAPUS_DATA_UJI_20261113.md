# Audit — Hapus Data Uji & Cakupan Admin Pusat

**Tanggal:** 13 November 2026
**Versi:** v2.108.2
**Pemicu:** laporan "admin atau traineer tidak bisa menghapus data uji" dan
"mestinya master admin juga bisa manage semua cabang".

---

## Ringkasan

Keluhan bukan soal izin yang salah setel, melainkan **fitur yang tidak ada**
dan **asimetri antarcabang**:

1. Modul FirstWork sama sekali tidak punya jalur hapus.
2. Data demo bisa ditanam per cabang tetapi hanya bisa dibersihkan untuk
   cabang yang sedang aktif.
3. Penanaman transaksi dummy tidak benar-benar idempoten.

Hak Admin Pusat sendiri **sudah benar** dan tidak diubah — justru diverifikasi
ulang lewat tes dan uji langsung.

---

## Temuan

| # | Tingkat | Temuan | Status |
|---|---------|--------|--------|
| A-01 | Kritis | `modules/routes_first_work.py` tidak punya endpoint DELETE. Data uji `first_work_submissions.id=1849` ("UJI COBA", HP 081234567890, status `submitted`, cabang SBY) tidak bisa dibuang dari aplikasi — hanya lewat SQL manual. | **Diperbaiki** |
| A-02 | Tinggi | `POST /api/branches/<code>/seed-demo` (`@ho_only`) bisa menanam demo ke cabang mana pun, tetapi `POST /api/demo/clean` memakai `get_db_connection()` = **cabang sesi saja**. Admin Pusat bisa menanam ke MLG lalu tidak bisa membersihkannya tanpa mengganti cabang aktif. | **Diperbaiki** |
| A-03 | Sedang | `INSERT IGNORE` untuk transaksi dummy dipakai tanpa kunci unik, sehingga setiap klik "Buat Data Demo" menambah 2 baris lagi (MLG berisi 4 baris, seharusnya 2). Klaim "idempoten" di komentar tidak benar. | **Diperbaiki** |
| A-04 | Info | `admin_master` **sudah** dikenali sebagai Admin Pusat: `admin_scope.is_ho_admin()` menerima nama legacy `admin`/`admin_master` **dan** flag `users.admin_all_branches=1`; `routes_first_work._scope_branch()` memakai jalur yang sama. Tidak ada bug di sini. | Terverifikasi |
| A-05 | Rendah | `scripts/smoke_expenses.py` masih mengunci rumus lama `grand_total = PO + LPJ`, padahal `total` sudah memasukkan voucher rekanan sejak v2.107.0 → smoke selalu merah di cabang yang punya baris SPBU rekanan. | **Diperbaiki** |
| A-06 | Catatan | Traineer tidak punya akses ke `/settings` (memang by design: `meta.roles = ['admin']`), sehingga tombol Data Demo tidak pernah terlihat oleh mereka. Karena itu jalur hapus harus ada di layar yang traineer pakai (`/first-work`). | Sesuai desain |
| A-07 | Risiko diterima | Penghapusan FirstWork bersifat **permanen** (hard delete, `first_work_events` ikut CASCADE). Mitigasi berlapis: konfirmasi `{"confirm":"HAPUS"}`, kunci cabang, traineer hanya status belum final, audit PII tersamar, file KTP ikut dihapus. | Diterima |
| A-08 | Catatan | Data demo MLG (4 transaksi dummy + 20 rute) **dibiarkan** — kemungkinan dipakai gladi resik. Sekarang bisa dibersihkan sendiri lewat tombol 🧹 Demo di Pengaturan tanpa mengganti cabang. | Diterima |

---

## Perbaikan yang dikerjakan

### A-01 — `DELETE /api/first-work/<id>`
- Role: `EDIT_ROLES` (`traineer`, `admin`).
- Wajib body `{"confirm": "HAPUS"}` → 400 bila tidak ada/salah.
- Scope: `_row_allowed()` — traineer & admin cabang hanya data cabangnya;
  Admin Pusat semua cabang. Sesi tanpa cabang → fail-closed.
- Traineer hanya boleh menghapus `submitted`/`rejected`; `verified` adalah
  arsip resmi → 403 (admin tetap boleh).
- File `ktp_file`/`ktp_scan_file` dihapus dari disk, dibatasi
  `os.path.abspath(...).startswith(UPLOAD_DIR + os.sep)`.
- Audit `activity_logs` (`action='first_work_delete'`) ditulis **sebelum**
  baris hilang, NIK/HP disamarkan (`_mask()` → 4 digit terakhir).
- UI: tombol 🗑️ Hapus Data di modal detail `FirstWorkView.vue`, tampil sesuai
  `canDelete()`.

### A-02 — `POST /api/branches/<code>/clean-demo`
- `@ho_only` (Admin Pusat), `@rate_limit(10/menit)`.
- Hanya menyentuh `appointments.display_id LIKE 'DEMO-%'` dan
  `transactions.is_dummy=1`; mengeset `system_config.dummy_data_enabled=false`.
- UI: tombol 🧹 Demo di baris cabang `SettingsView.vue`.

### A-03 — Seed idempoten
- `routes_branches._DUMMY_TX_SQL` dan `routes_api_master.DEMO_TX_SQL` diganti
  menjadi `INSERT ... SELECT ... FROM DUAL WHERE NOT EXISTS (...)` dengan
  kunci `(is_dummy, driver_name, nopol)`.

### A-05 — Smoke rekap
- Assertion diperbarui menjadi `grand_total = PO + LPJ + voucher`.

---

## Bukti verifikasi

**Unit test (container):**
- `tests/test_first_work_delete.py` — 15 lulus.
- `tests/test_branch_clean_demo.py` — 10 lulus.
- `tests/test_branches.py` — 21 lulus (assertion `INSERT IGNORE` diperbarui).
- Pytest penuh: 1292 lulus, 6 dilewati, 0 gagal.
- Vitest penuh: 317 lulus (44 berkas).

**Uji live (v2.108.2, `https://127.0.0.1:5000`):**

| Skenario | Hasil |
|----------|-------|
| Admin cabang MLG menghapus data SBY (1849) | `403 Data di luar cabang Anda` |
| Admin cabang MLG memanggil clean-demo BDG | `403 hanya untuk Admin Pusat (HO)` |
| Admin Pusat (flag `admin_all_branches=1`) seed-demo BDG #1 | `200 — 20 rute baru, 2 transaksi dummy` |
| Seed-demo BDG #2 | `200 — 0 rute baru, 0 transaksi dummy` (DB tetap 2/20) |
| clean-demo BDG | `200 — 20 rute, 2 transaksi dummy` (DB kembali 0/0) |
| Hapus 1849 sebagai Admin Pusat | `200 — "Data UJI COBA dihapus", 2 file KTP dihapus` |
| Baris & event 1849 setelah hapus | `0` dan `0` |
| Audit `first_work_delete` | Ada; NIK/HP tersamar (••••9999) |
| Flag `admin_mlg` setelah uji | kembali `0` |

`scripts/overall_check.sh` → **9/9 SEHAT**.

---

## Sisa risiko / rekomendasi

1. **Hard delete tidak bisa dibatalkan.** Bila kelak dibutuhkan pemulihan,
   pertimbangkan soft-delete (`deleted_at`) + job pembersih. Untuk data uji
   dan PII, hard delete justru lebih aman.
2. **Penghapusan tidak memakai step-up PIN.** Operasi destruktif lain
   (aksi uang) memakai step-up. Bila traineer kelak diberi wewenang lebih
   luas, pertimbangkan step-up untuk hapus data `verified`.
3. **Counter ID tidak di-rewind** saat data dihapus — nomor urut yang sudah
   terpakai tetap dianggap terpakai (perilaku yang diinginkan).
4. **Data demo MLG** masih 4 transaksi (sisa bug duplikasi lama). Bersihkan
   sekali lewat 🧹 Demo bila tidak dipakai.
