# Rilis B — Paritas & Rekonsiliasi Rekrutmen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menyamakan FirstWork WorkHub dengan unitedw (13 field demografi + kode cabang pada ID FP/BPF + cetak kartu), lalu mengimpor 226 pengajuan unitedw dan mem-backfill 1.738 data lama WorkHub sebagai kasus — tanpa mengubah data asli.

**Architecture:** Field baru ditambahkan ke `first_work_submissions` (nullable), form publik, review, dan ekspor. Modul impor baru memetakan CSV unitedw ke `recruitment_cases`/`recruitment_steps` + `first_work_submissions` dengan kunci alami `source + source_uid`. Backfill hanya membaca data lama.

**Tech Stack:** Python 3.11 / Flask / mysql.connector / pytest / fpdf2, Vue 3 / Vitest.

**Spec:** `docs/superpowers/specs/2026-11-24-recruitment-consolidation-design.md`
**Depends on:** Rilis A (`2026-11-24-rilis-a-fondasi-rekrutmen.md`)

## Global Constraints

- Versi rilis **v2.133.1** (bump oleh controller).
- Sumber CSV unitedw: 226 baris, 13–24 Nov 2026, 3 NIK ganda, 9 email ganda; semua status Baru.
- Data WorkHub lama: 1.738 baris, 7 Okt 2025–10 Nov 2026; 0 iris NIK dengan unitedw.
- NIK di laporan cukup 4 digit terakhir; file CSV mentah tidak boleh di-commit.
- Impor/backfill idempoten dan harus bisa di-rollback.
- Tidak mengubah Rilis A, tidak menyentuh modul BBM/Finance.
- Setiap task: failing test → implement → passing test → commit.

## Review Focus

- Field OCR lama tidak boleh tertimpa nilai手动 baru.
- Impor 3 NIK ganda harus menghasilkan satu kasus dengan `merged_from`, bukan 3 kasus.
- Backfill 1.738 baris tidak boleh mengubah `first_work_submissions`.
- Cetak kartu tidak boleh memotong nilai panjang (pelajaran v2.131.4).
- Ekspor review tetap menyamarkan NIK sesuai kebijakan yang ada.

---

### Task 1: Kode cabang pada ID FP & ID BPF

**Files:**
- Modify: `modules/first_work_schema.py`, `modules/routes_first_work.py`
- Test: `tests/test_first_work_branch_id.py`

**Interfaces:**
- Consumes: `first_work_branch_counters` (sudah ada, masih kosong), pemetaan 12 cabang.
- Produces: ID baru `<prefix>_<nomor>`; prefix `EI,EA,EB,EC,ED,EF,EG,EH,EJ,EK,EL,EM`
  untuk `JKT,JKT2,JMB,MLG,PTK,SBY,BDG,MDN,BJM,PKU,LPG,SMG`.

- [ ] **Step 1: failing test** — submit di SBY menghasilkan `EF_` + nomor dari counter cabang; submit di BDG menghasilkan `EG_`; nomor lama `B`/`C` tidak berubah.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** seed pemetaan prefix per cabang; generator pakai `(branch_code, series)`; fallback ke counter global bila cabang belum punya baris; ID lama tidak diubah.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 2: 13 field demografi FirstWork

**Files:**
- Modify: `modules/first_work_schema.py`, `modules/routes_first_work.py`
- Modify: `frontend/src/views/FirstWorkFormView.vue`, `frontend/src/views/FirstWorkView.vue`
- Test: `tests/test_first_work_demographics.py`, `frontend/src/views/FirstWorkFormView.test.js`

**Interfaces:**
- Consumes: kolom baru nullable di `first_work_submissions`.
- Produces: payload public/CV review/export menyertakan 13 field: `tempat_lahir`, `tanggal_lahir`, `jenis_kelamin`, `golongan_darah`, `alamat`, `rt_rw`, `kel_desa`, `kecamatan`, `agama`, `status_perkawinan`, `pekerjaan`, `kewarganegaraan`, `berlaku_hingga`.

- [ ] **Step 1: failing test** — submit tanpa field baru tetap diterima; submit dengan field baru tersimpan; review/export menampilkan field.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** field optional, tidak menimpa hasil OCR; tampil di langkah identitas/kontak yang sesuai.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 3: Cetak kartu BPF dari FirstWork

**Files:**
- Modify: `modules/pdf_generator.py` (class baru `FirstWorkCardPDF`)
- Modify: `modules/routes_first_work.py` (endpoint PDF)
- Test: `tests/test_first_work_card_pdf.py`

**Interfaces:**
- Consumes: baris `first_work_submissions`.
- Produces: `GET /api/first-work/card/<id>.pdf` → PDF A4/portion kartu dengan nama, NIK 4 digit terakhir, cabang, nomor registrasi, QR `BPF-FW:<registration_no>`.

- [ ] **Step 1: failing test** — endpoint 404 → implement; PDF diawali `%PDF`; nilai tidak terkliping (cek posisi x seperti pola `test_driver_service_pdf_qr.py`).
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** memakai `BPFBasePDF`; render dengan `pdftoppm` dan baca hasilnya.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 4: Impor 226 pengajuan unitedw

**Files:**
- Create: `scripts/import_unitedw_firstwork.py`
- Test: `tests/test_import_unitedw.py`

**Interfaces:**
- Consumes: CSV unitedw (di luar repo, argumen path); helper `upsert_case_step` Rilis A.
- Produces: baris `first_work_submissions` + `recruitment_steps` dengan `source='unitedw'`; laporan jumlah `inserted`, `skipped`, `merged`, `invalid`.

- [ ] **Step 1: failing test** — NIK ganda → satu kasus + `merged_from`; email ganda ditandai; dua kali impor → `skipped=226`, tidak ada baris baru.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** dry-run default; `--commit` untuk menulis; log tanpa NIK lengkap; validasi 16 digit.
- [ ] **Step 4: run — PASS dengan dry-run pada CSV nyata**; commit.

---

### Task 5: Backfill 1.738 kasus lama

**Files:**
- Create: `scripts/backfill_recruitment_cases.py`
- Test: `tests/test_backfill_recruitment.py`

**Interfaces:**
- Consumes: `first_work_submissions` + `cv_online_submissions` yang sudah ada.
- Produces: `recruitment_cases` + langkah `SELESAI` dengan `source='sheet_legacy'`; **tidak** mengubah tabel sumber.

- [ ] **Step 1: failing test** — 2 baris sumber → 2 kasus; dijalankan ulang → 0 baris baru; hash ringkasan sumber sebelum/sesudah identik.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** batch, transaksi per NIK, laporkan count.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 6: Evidence Training & TKD generik

**Files:**
- Modify: `modules/routes_recruitment.py`
- Modify: `frontend/src/views/RecruitmentCasesView.vue`
- Test: `tests/test_recruitment_evidence.py`, `frontend/src/views/RecruitmentCasesView.test.js`

**Interfaces:**
- Consumes: `recruitment_steps` langkah `TRAINING`/`TKD`.
- Produces: `POST /api/recruitment/steps/<id>/evidence` `{date, note, file_url?, score?}` → status `SELESAI`; staff dapat membuka/tutup detail evidence.

- [ ] **Step 1: failing test** — evidence tanpa tanggal ditolak; dengan tanggal → status SELESAI; audit tercatat.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** UI ringan di modal kasus (tanpa modul kuis baru).
- [ ] **Step 4: run — PASS**; commit.
