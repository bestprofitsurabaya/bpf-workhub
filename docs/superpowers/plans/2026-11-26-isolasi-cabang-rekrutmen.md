# Isolasi Cabang Rekrutmen — Rencana Implementasi

**Goal:** Token portal satu cabang tidak boleh membaca atau menulis data kasus
cabang lain, dan staff non-HO hanya melihat kasus cabangnya. Admin Pusat tetap
lintas cabang.

**Architecture:** Aturan scope yang sudah dipakai skor TKD (`_case_in_scope`)
diperluas ke jalur tulis/baca portal: absensi training, sesi TKD, daftar kasus,
dan pengecualian langkah. Kecocokan ditentukan dari cabang asal, riwayat
(`case_branch_history`), atau langkah (`recruitment_steps`) kasus. Tanpa
kecocokan, pelamar diperlakukan seperti tidak ditemukan agar identitas cabang
tidak bocor.

**Tech Stack:** Python/Flask, MySQL, pytest, Vue 3, Vitest.

**Status:** Selesai dan ter-deploy sebagai v2.135.6 (26 November 2026).
Terverifikasi: 351 tes backend terdampak, 36 tes frontend fokus, build SPA,
health NAS `state=ok`/`stale=false`, dan smoke test token SBY vs BDG.

## Global Constraints

- Tidak mengubah skema database maupun data historis.
- NIK penuh, nomor HP, dan token cabang tidak boleh muncul di laporan/PDF.
- Pesan penolakan lintas cabang harus generik dan sama dengan NIK tidak
  ditemukan.
- Admin Pusat (`admin` / `admin_all_branches`) tetap melihat semua cabang.

## Temuan Audit

1. Absensi training dan sesi TKD memakai cabang token tanpa memeriksa cabang
   kasus, sehingga token cabang lain bisa menulis bukti.
2. `POST /api/recruitment/steps/<id>/exception` tidak memakai scope cabang.
3. `GET /api/recruitment/cases` menampilkan kasus semua cabang ke staff non-HO.
4. Langkah TKD `RC-4f91d973d9b2` menunjuk attempt yang tidak ada (jejak audit
   putus); data ini tidak diubah otomatis dan menunggu keputusan pemilik data.

## Task 1: Absensi training terikat cabang

- [x] `_case_in_branch()` di `training_service.py`.
- [x] `attendance_status()` dan `record_attendance()` menolak `not_found`.
- [x] Tes: status/absensi cabang lain tidak menemukan dan tidak menulis;
      kasus dengan riwayat cabang tetap boleh.

## Task 2: Sesi TKD terikat cabang

- [x] `_case_matches_branch()` di `routes_tkd.py`.
- [x] `_verified_context()` menolak dengan pesan identitas generik.
- [x] Tes: status/start dengan token cabang lain ditolak 403 tanpa attempt.

## Task 3: Daftar kasus dan pengecualian langkah

- [x] Filter scope pada query `GET /api/recruitment/cases` untuk non-HO.
- [x] `_case_scope_ok()` diperiksa sebelum status langkah pada exception.
- [x] Tes: kasus cabang lain tidak muncul; filter cabang lain tidak menembus
      scope; exception lintas cabang 403 tanpa membocorkan status.

## Task 4: Rilis dan verifikasi

- [x] Versi `v2.135.6`, changelog, panduan, dan service worker cache.
- [x] Build frontend dan image Docker di NAS.
- [x] Health check dan smoke test produksi.
