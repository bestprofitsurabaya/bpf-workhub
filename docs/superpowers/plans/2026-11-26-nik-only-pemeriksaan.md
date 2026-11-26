# Pemeriksaan Identitas NIK-only — Rencana Implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portal rekrutmen, absensi training, dan TKD cukup memakai NIK 16 digit, dengan copy bahasa Indonesia yang lebih humanis.

**Architecture:** NIK tetap menjadi kunci tunggal di `recruitment_cases`. Tanggal lahir berhenti menjadi parameter verifikasi di service, route, dan UI; field tanggal lahir di CV Online/FirstWork tidak disentuh karena merupakan data diri. Perubahan mengikuti pola yang sudah ada: service menerima `nik`, route memvalidasi 16 digit, UI hanya merender satu input.

**Tech Stack:** Python/Flask, MySQL, Vue 3 (`<script setup>`), Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-nik-only-pemeriksaan-design.md`

## Global Constraints

- NIK penuh tidak boleh dikembalikan ke browser atau ditulis ke log; hanya `****1234`.
- Token cabang tetap wajib dan tidak boleh berasal dari input pengguna.
- Kunci jawaban TKD tidak boleh dikirim ke browser.
- Tanggal lahir tetap ada di form CV Online dan FirstWork sebagai data diri.
- Tidak mengubah skema database, logo, atau aset merek.
- Semua teks baru memakai bahasa Indonesia yang ramah dan tidak menyalahkan pengguna.
- Tidak push/merge/deploy ke NAS tanpa persetujuan.

## Review Focus

- NIK 16 digit yang tidak terdaftar: pesan jelas, bukan error 500, dan tidak membocorkan data.
- NIK berisi spasi/titik: dinormalisasi sebelum dicek, bukan ditolak mentah.
- Hari 2 tanpa Hari 1: tetap ditolak 409, termasuk setelah `dob` dihapus.
- Token salah/nonaktif: tetap 403 sebelum menyentuh identitas.
- Rate limit: percobaan berulang tetap 429 dan tidak menghabiskan kuota DB.

---

### Task 1: Absensi training cukup NIK

**Files:**
- Modify: `modules/training_service.py`
- Modify: `modules/routes_training.py`
- Test: `tests/test_training_service.py`, `tests/test_training_routes.py`

**Interfaces:**
- Produces: `_case_for(cursor, nik)`, `attendance_status(nik, branch_code, conn=None)`, `record_attendance(nik, branch_code, day, ip='', user_agent='', conn=None, app_conn=None)`.
- Consumes: `normalize_nik`, `_days_for`, `_resolve_applicant` (tidak berubah).

- [ ] **Step 1: Ubah tes service agar memanggil tanpa `dob`**

Di `tests/test_training_service.py`, ganti setiap `ts.attendance_status(NIK, DOB, 'SBY')` menjadi `ts.attendance_status(NIK, 'SBY')` dan `ts.record_attendance(NIK, DOB, 'SBY', ...)` menjadi `ts.record_attendance(NIK, 'SBY', ...)`. Tambah satu tes: kasus dengan `tanggal_lahir=None` tetap ditemukan lewat NIK.

- [ ] **Step 2: Jalankan tes dan pastikan gagal**

Run: `python3 -m pytest tests/test_training_service.py -q`
Expected: FAIL karena signature lama masih menuntut `dob`.

- [ ] **Step 3: Implementasi service NIK-only**

`_case_for` hanya `WHERE nik=%s`; hapus perbandingan `_dob_text`. `attendance_status` dan `record_attendance` menghapus parameter `dob` dan meneruskannya ke `_case_for`.

- [ ] **Step 4: Ubah route dan tes route**

`routes_training.py`: hapus pembacaan `dob`, validasi cukup `if not nik`. `_NOT_FOUND` menjadi `'Data peserta belum kami temukan. Mohon periksa kembali NIK Anda.'` Tes route menghapus `dob` dari query/body dan menyesuaikan assertion pesan.

- [ ] **Step 5: Jalankan tes**

Run: `python3 -m pytest tests/test_training_service.py tests/test_training_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/training_service.py modules/routes_training.py tests/test_training_service.py tests/test_training_routes.py
git commit -m "feat(training): absensi portal cukup NIK"
```

---

### Task 2: TKD cukup NIK

**Files:**
- Modify: `modules/tkd_service.py`
- Modify: `modules/routes_tkd.py`
- Test: `tests/test_tkd_service_read.py`, `tests/test_tkd_public_status_start.py`

**Interfaces:**
- Produces: `verify_identity(cursor, nik) -> dict | None`.
- Consumes: `fetch_case_by_nik`, `_as_iso`, `_as_float`.

- [ ] **Step 1: Ubah tes service TKD**

`tests/test_tkd_service_read.py`: `svc.verify_identity(cur, '3573010101990001')` mengembalikan kasus; NIK tidak dikenal dan NIK bukan 16 digit mengembalikan `None`. Hapus tes tanggal lahir salah.

- [ ] **Step 2: Jalankan tes dan pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_service_read.py -q`
Expected: FAIL (TypeError signature).

- [ ] **Step 3: Implementasi `verify_identity(cursor, nik)`**

Ambil kasus lewat `fetch_case_by_nik`; tidak ada cabang tanggal lahir. Hapus impor `derive_dob_from_nik` bila tidak terpakai lagi.

- [ ] **Step 4: Ubah route TKD**

`_verify_body` hanya mewajibkan `nik` 16 digit + `token`. `_verified_context` memanggil `svc.verify_identity(cursor, verified['nik'])`. Ubah `_MSG_IDENTITY` menjadi `'Data belum cocok. Periksa kembali NIK Anda atau hubungi Traineer cabang.'` Perbarui docstring modul.

- [ ] **Step 5: Ubah tes route TKD**

Hapus `dob` dari semua body. Ganti `monkeypatch.setattr(svc, 'verify_identity', lambda cur, nik: ...)`. Hapus tes "dob salah"; tambah tes "NIK tidak dikenal" tetap 403 generik.

- [ ] **Step 6: Jalankan tes**

Run: `python3 -m pytest tests/test_tkd_service_read.py tests/test_tkd_public_status_start.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add modules/tkd_service.py modules/routes_tkd.py tests/test_tkd_service_read.py tests/test_tkd_public_status_start.py
git commit -m "feat(tkd): verifikasi identitas cukup NIK"
```

---

### Task 3: Lookup portal cukup NIK

**Files:**
- Modify: `modules/routes_recruitment.py`
- Test: `tests/test_recruitment_lookup.py`

**Interfaces:**
- Produces: `GET /api/recruitment/lookup?nik=<16 digit>`.
- Consumes: `_nik_known`, `portal_summary`, `_response`, `_lookup_ok`.

- [ ] **Step 1: Ubah tes lookup**

`_lookup(client, nik=NIK, **extra)` tidak lagi mengirim `dob`. Hapus parametrized `dob` invalid. Tambah tes: NIK 16 digit tanpa `dob` tetap mengembalikan `known`. Pertahankan tes NIK pendek → `known=False` tanpa menyentuh DB.

- [ ] **Step 2: Jalankan tes dan pastikan gagal**

Run: `python3 -m pytest tests/test_recruitment_lookup.py -q`
Expected: FAIL pada tes yang mengharapkan lookup tanpa `dob` berhasil.

- [ ] **Step 3: Implementasi**

Hapus `_valid_dob(request.args.get('dob'))` dari kondisi lookup. `_valid_dob` tetap dipakai untuk `evidence_date`. Perbarui docstring kontrak.

- [ ] **Step 4: Jalankan tes**

Run: `python3 -m pytest tests/test_recruitment_lookup.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/routes_recruitment.py tests/test_recruitment_lookup.py
git commit -m "feat(portal): lookup rekrutmen cukup NIK"
```

---

### Task 4: UI portal, training, dan TKD cukup NIK

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue`
- Modify: `frontend/src/views/TrainingFormView.vue`
- Modify: `frontend/src/components/RecruitmentTkdPanel.vue`
- Test: `frontend/src/views/RecruitmentPortalView.test.js`, `frontend/src/components/RecruitmentTkdPanel.test.js`

**Interfaces:**
- Produces: `RecruitmentTkdPanel` props `{ token, nik }`; lookup `params: { nik }`.
- Consumes: endpoint Task 1–3.

- [ ] **Step 1: Ubah tes frontend**

Portal: `cek(w, nik)` hanya mengisi NIK; assertion lookup `{ params: { nik: NIK } }`; panel `{ token: TOKEN, nik: NIK }`; hapus tes tanggal lahir invalid, ganti dengan "NIK kurang dari 16 digit tidak memanggil lookup". Training: tambah tes bahwa input `aria-label="Tanggal lahir"` tidak ada. Panel: `PROPS` tanpa `dob`, body status/start tanpa `dob`.

- [ ] **Step 2: Jalankan tes dan pastikan gagal**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js src/components/RecruitmentTkdPanel.test.js`
Expected: FAIL karena input tanggal lahir masih ada.

- [ ] **Step 3: Implementasi UI**

Hapus `dob`, `tkdDob`, `validDate`, dan input tanggal lahir dari portal serta training. `identity()` panel menjadi `{ nik: props.nik, token: props.token }`. Perbarui teks: portal "Masukkan NIK untuk melihat rangkuman dan melanjutkan proses rekrutmen.", tombol "Cek Status"; training "Masukkan NIK untuk melihat dan mencatat kehadiran."

- [ ] **Step 4: Jalankan tes**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js src/components/RecruitmentTkdPanel.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentPortalView.vue frontend/src/views/TrainingFormView.vue frontend/src/components/RecruitmentTkdPanel.vue frontend/src/views/RecruitmentPortalView.test.js frontend/src/components/RecruitmentTkdPanel.test.js
git commit -m "feat(portal): form publik cukup NIK"
```

---

### Task 5: Copy humanis, hitungan soal, dan rilis

**Files:**
- Modify: `frontend/src/components/RecruitmentTkdPanel.vue`
- Modify: `modules/company_identity.py`
- Modify: `CHANGELOG.md`
- Test: `frontend/src/components/RecruitmentTkdPanel.test.js`

**Interfaces:**
- Produces: versi `v2.135.5`; label "21 soal (20 dinilai)".

- [ ] **Step 1: Tambah tes label soal**

Tes panel memuat teks `21 soal (20 dinilai)` pada intro, dan `Soal 1 dari 21` pada ujian.

- [ ] **Step 2: Implementasi label**

Di intro, tampilkan `{{ fmt(rules.question_count) }} soal dinilai + 1 soal profil` atau `21 soal (20 dinilai)`. Pilih satu dan pakai konsisten.

- [ ] **Step 3: Naikkan versi dan changelog**

`modules/company_identity.py` → `v2.135.5`; `frontend/src/stores/identity.js` bila menyimpan versi; `CHANGELOG.md` mencatat NIK-only dan copy.

- [ ] **Step 4: Verifikasi penuh**

Run: `python3 -m pytest tests/test_training_service.py tests/test_training_routes.py tests/test_tkd_service_read.py tests/test_tkd_public_status_start.py tests/test_recruitment_lookup.py -q`
Run: `cd frontend && npm test -- --run`
Run: `cd frontend && npm run build`
Expected: semua PASS, build sukses.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "release: v2.135.5 pemeriksaan cukup NIK dan copy humanis"
```
