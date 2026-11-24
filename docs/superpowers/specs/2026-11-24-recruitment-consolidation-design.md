# Design — Konsolidasi Rekrutmen WorkHub & unitedw (24 November 2026)

## Intent
Manajemen ingin WorkHub menjadi satu-satunya platform rekrutmen. unitedw
memiliki portal 4 aplikasi (Register Online CV → Training Absensi → Test
Kemampuan Dasar → Firstwork Absensi), tetapi hanya Firstwork yang aktif.
WorkHub sudah punya CV Online dan FirstWork produksi, namun **tanpa NIK di CV
Online** dan **tanpa 13 field demografi yang dipakai unitedw di FirstWork**.

Tujuan desain ini: membuat data rekrutmen **saling berkelanjutan**, bukan empat
form terpisah, dengan NIK sebagai kunci identitas dan pengecualian urutan
dicatat per orang oleh petugas.

## Goals
- Satu kasus per NIK, dapat dilihat lintas cabang oleh Traineer/GA HR.
- NIK baru wajib mengisi CV Online; NIK yang sudah ada boleh langsung ke
  langkah mana pun (termasuk FirstWork).
- Kesetaraan isian: 13 field demografi unitedw tersedia di FirstWork WorkHub,
  termasuk cetak kartu.
- 226 pengajuan unitedw (13–24 Nov 2026) terimpor dengan jejak sumber; 1.738
  data lama WorkHub ter-backfill sebagai kasus tanpa mengubah record asli.
- Deteksi cabang bersifat informasi/audit, bukan gerbang persetujuan.

## Non-goals
- Tidak memindahkan mesin OCR atau MFA dari/ke unitedw (keduanya sudah ada
  atau setara di WorkHub).
- Tidak membangun aplikasi Training dan TKD penuh pada tahap ini — keduanya
  mulai sebagai langkah generik dengan evidence.
- Tidak mengubah status data lama atau menghapus data unitedw.
- Tidak membuat model divisi di dokumen ini (direncanakan terpisah).
- Tidak membuka detail pribadi ke endpoint publik.

## Anti-goals
- Form FirstWork yang menolak peserta karena Training/TKD belum selesai.
- Kasus ganda untuk NIK yang sama di cabang berbeda.
- Portal publik yang bisa dipakai untuk enumerasi "siapa daftar di cabang mana".

## Constraints
- `cv_online_submissions` dan `first_work_submissions` berada di **DB master**;
  deteksi lintas cabang tidak perlu read model.
- `cv_online_submissions` belum punya kolom NIK; `first_work_submissions`
  sudah punya `nik` (16 digit) + `nik_raw`.
- Peranexisting: CV Online `VIEW_ROLES = traineer, ga_hr, admin`; FirstWork
  `VIEW_ROLES = traineer, finance, ga_hr, admin`.
- Endpoint `/api/first-work/check-nik` sudah global (master, tanpa filter
  cabang) dan sengaja mengembalikan boolean saja + `Cache-Control: no-store`.
- Data unitedw: 226 baris, 3 NIK ganda, 9 email ganda, semua status Baru.
- Data WorkHub: 1.738 baris, 7 Okt 2025–10 Nov 2026, **0 iris NIK** dengan
  unitedw — keduanya berurutan secara kronologis, bukan duplikat.
- NIK dan KTP adalah data pribadi; consent sudah ada di dua form publik.

## Approaches yang dipertimbangkan

1. **Data dulu** — rekonsiliasi & impor tanpa ubah UI. Bukti kuat, tapi tidak
   menjawab keluhan "form kurang lengkap".
2. **Paritas dulu** — tambah field + cetak kartu, lalu impor. Langsung terasa,
   tapi menyentuh banyak file; risiko regresi form produksi.
3. **Tata kelola dulu** — model divisi & audit. Penting, tapi tidak terlihat
   sebagai peningkatan rekrutmen.

**Dipilih: 1 + 2 dalam satu paket "Paritas & Rekonsiliasi"**, dengan urutan
implementasi data → paritas → impor → dashboard. Paket divisi menyusul.

## Design

### A. Identitas & portal
- Tambah kolom `nik` (16 digit, normalisasi sama seperti FirstWork) ke
  `cv_online_submissions`, plus consent saat input pertama.
- **Portal tetap satu tautan per cabang** (memakai token cabang yang sudah ada
  di `cv_online_branch_forms` / `first_work_branch_forms`). Token menentukan
  cabang tempat peserta mengisi; NIK tidak menggantikan token.
- Portal cabang menampilkan 4 kartu langkah. Sebelum mengisi langkah apa pun,
  peserta memasukkan NIK + tanggal lahir sekali. Endpoint baru
  `/api/recruitment/lookup` (publik) mengembalikan **hanya**:
  `{"known": bool, "can_continue": bool}` — tidak mengembalikan cabang/tahap.
- Deteksi NIK tetap global ke master, jadi peserta yang membuka tautan cabang B
  dengan NIK yang pernah mendaftar di cabang A tetap dikenali, tetapi ia
  mengisi langkah berikutnya **di cabang B** sesuai token yang dipakainya.
- Endpoint staff `/api/recruitment/cases?nik=` (role traineer/ga_hr/admin)
  mengembalikan cabang asal, cabang pengisian tiap langkah, dan riwayat pindah
  cabang, serta mencatat akses.

### B. Model data (DB master)
- `recruitment_cases`: `case_id`, `nik` UNIQUE, `nama`, `tanggal_lahir`,
  `first_seen_at`, `first_branch`, `status`, `merged_from`.
- `recruitment_steps`: `case_id`, `step_type` ENUM('CV','TRAINING','TKD','FIRSTWORK'),
  `status` ENUM('BELUM','PENDING','SELESAI','DIKECUALIKAN'), `branch_code`,
  `evidence_type`, `evidence_id`, `completed_at`, `actor`, `exception_reason`.
- `case_branch_history`: `case_id`, `branch_code`, `first_seen_at`, `last_seen_at`.
- `step_evidence` tidak menyalin data module; cukup `{type, id, ringkasan}`.

### C. Aturan langkah & pengecualian
- NIK baru → langkah `CV` wajib sebelum langkah lain tersedia.
- NIK dikenal → semua langkah tersedia; pilihan di tangan peserta.
- Petugas (Traineer/GA HR/Admin) dapat menandai `DIKECUALIKAN` per langkah,
  wajib mengisi alasan; tanpa alur persetujuan lain.
- Pindah cabang **hanya tercatat**, tidak memblokir proses. Peserta memakai
  tautan cabang mana pun; langkah yang diisi tetap dicatat dengan `branch_code`
  dari token yang dipakainya, sementara `case_branch_history` menyimpan jejak
  cabang sebelumnya untuk Traineer/GA HR.

### D. Paritas isian FirstWork
Tambahkan ke `first_work_submissions` + form publik + review + ekspor:
`tempat_lahir`, `tanggal_lahir`, `jenis_kelamin`, `golongan_darah`, `alamat`,
`rt_rw`, `kel_desa`, `kecamatan`, `agama`, `status_perkawinan`, `pekerjaan`,
`kewarganegaraan`, `berlaku_hingga`. Field OCR yang sudah ada tetap dipertahankan.
**Keputusan implementasi (call saya):** cetak kartu BPF ikut dibangun karena
merupakan kemampuan unitedw yang dipakai petugas; tanpanya paritas tidak penuh.

### E. Kode cabang pada ID FP / ID BPF
unitedw memakai prefix dua huruf di `ID FP` dan `ID BPF`, misalnya `EF_30031`
(Surabaya), `EA_68922` (Jakarta Pacific Place), `EI_60849` (Equity Tower).
WorkHub hanya menyimpan seri `B`/`C` global (`first_work_id_counters`) dan
sudah memiliki tabel `first_work_branch_counters` yang belum dipakai.

- Tambah pemetaan `branch_code → prefix` (12 cabang):
  `JKT→EI, JKT2→EA, JMB→EB, MLG→EC, PTK→ED, SBY→EF, BDG→EG, MDN→EH,
  BJM→EJ, PKU→EK, LPG→EL, SMG→EM`.
- Generator ID memakai `(branch_code, series)` di `first_work_branch_counters`;
  format akhir `<prefix>_<nomor>`, seri `B` untuk ID FP, `C` untuk ID BPF.
- Data lama tidak dinomori ulang — hanya baris baru yang memakai prefix.

### E. Training & TKD
Langkah generik dengan evidence: tanggal, cabang, file/absensi, catatan, nilai.
Belum ada aplikasi kuis tersendiri di tahap ini.

### G. Import & backfill
- CSV unitedw (226 baris) dipetakan kolom per kolom; 3 NIK ganda dan 9 email
  ganda → `merged_from` + catatan, bukan dibuang.
- 1.738 baris WorkHub lama di-backfill sebagai kasus + langkah FIRSTWORK
  `SELESAI`, source `sheet_legacy`.
- Semua impor idempoten (kunci alami `source + source_uid`) dan bisa di-rollback.

### H. Dashboard Traineer / GA HR
Satu halaman kasus: filter NIK/nama/cabang/status, matriks 4 langkah,
penanda cabang asal vs cabang saat ini, log pengecualian, dan ekspor.

## Risks & mitigasi
- NIK salah/OCR keliru → validasi 16 digit + tanggal lahir; koreksi petugas.
- Enumeration data pribadi → endpoint publik boolean-only, rate limit, no-store.
- Regresi form produksi → flag fitur baru, uji dua cabang pilot, rollback.
- Duplikat NIK → merge ke satu kasus dengan audit `merged_from`.
- Data lama berubah makna → backfill read-only, field baru nullable.

## Builder check
Dokumen ini ditinjau builder sebelum implementasi. Pertanyaan minor diselesaikan
di dokumen; yang mengubah arsitektur dikembalikan ke user sebelum kode ditulis.
