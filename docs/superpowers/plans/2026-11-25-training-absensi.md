# Absensi Training Portal (2 Hari) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Peserta bisa mencatat kehadiran training Hari 1 & Hari 2 dari portal rekrutmen, tersimpan sebagai bukti, menggerakkan status TRAINING, dan mengisi kolom H1/H2 di dashboard Pelamar bila identitas cocok.

**Architecture:** Satu tabel bukti `training_attendance` (unik per kasus+cabang+hari) di DB master, satu service identitas/absensi, dua endpoint publik ber-token cabang, satu halaman form Vue, dan kartu portal yang diaktifkan. Pencocokan ke `applicants` memakai nama + HP yang sama persis dari CV Online, hanya bila hasilnya tunggal.

**Tech Stack:** Python 3.11 / Flask + MySQL (master), Vue 3 + Vite + Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-training-absensi-design.md`

## Global Constraints

- Cabang selalu dari token `cv_online_branch_forms` (`active=1`), tidak pernah dari input pengguna.
- Hari 2 ditolak server (409) sampai Hari 1 tercatat untuk kasus+cabang yang sama.
- Tanpa PIN, tanpa OCR/foto, tanpa membuat baris `applicants` otomatis, tanpa mengubah skema `applicants`.
- Pencocokan Pelamar: nama ternormalisasi sama DAN HP ternormalisasi sama; hanya bila tepat satu kandidat.
- NIK tidak boleh muncul penuh di log; pakai mask 4 digit terakhir (pola `_mask_nik`).
- Semua DDL idempoten (`CREATE TABLE IF NOT EXISTS`) dan dipanggil saat startup.
- Bahasa UI: Indonesia, nada tenang, tanpa istilah teknis.

## Review Focus

- NIK valid tapi tanggal lahir beda → harus 404 generik, bukan membocorkan bahwa NIK terdaftar.
- Token cabang salah/nonaktif → 403 dan tidak ada penulisan apa pun.
- Submit Hari 2 dua kali / Hari 1 dua kali → idempoten, tidak menggandakan bukti dan tidak menurunkan status pelamar.
- Pelamar dengan nama sama tapi HP berbeda (atau sebaliknya) → tidak boleh tertaut (`unlinked`), bukan menebak.
- Pelamar sudah `lulus`/`resigned`/`rejected` → absensi tetap tercatat di hub, status pelamar tidak diubah.

---

### Task 1: Skema `training_attendance`

**Files:**
- Create: `modules/training_schema.py`
- Modify: `app.py` (setelah blok `ensure_recruitment_schema`, sekitar baris 129–133)
- Test: `tests/test_training_schema.py`

**Interfaces:**
- Produces: `ensure_training_attendance_schema(conn=None) -> bool`

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_ddl_idempoten_dan_kolom_kunci():
    # fake cursor mencatat SQL; dua panggilan harus menghasilkan DDL yang sama
    # dan mengandung UNIQUE KEY (case_id, branch_code, day)
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `python -m pytest tests/test_training_schema.py -v`
Expected: FAIL `ModuleNotFoundError: modules.training_schema`

- [ ] **Step 3: Implementasi**

`ensure_training_attendance_schema(conn=None)` membuat tabel:

```sql
CREATE TABLE IF NOT EXISTS training_attendance (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  case_id VARCHAR(40) NOT NULL,
  nik CHAR(16) NOT NULL,
  branch_code VARCHAR(10) NOT NULL,
  day TINYINT NOT NULL,
  nama VARCHAR(150) NOT NULL DEFAULT '',
  attended_at DATETIME NOT NULL,
  applicant_id INT NULL,
  link_status ENUM('linked','unlinked','ambiguous') NOT NULL DEFAULT 'unlinked',
  ip VARCHAR(45) NOT NULL DEFAULT '',
  user_agent VARCHAR(255) NOT NULL DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ta_case_branch_day (case_id, branch_code, day),
  KEY idx_ta_nik (nik),
  KEY idx_ta_applicant (applicant_id),
  KEY idx_ta_branch_date (branch_code, attended_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
```

Pola koneksi/commit/close mengikuti `modules/recruitment_schema.py` (buka sendiri bila `conn` None, jangan tutup koneksi pemanggil). Daftarkan di `app.py` dengan retry 5× pola yang sama.

- [ ] **Step 4: Jalankan tes**

Run: `python -m pytest tests/test_training_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/training_schema.py app.py tests/test_training_schema.py
git commit -m "feat(training): skema bukti absensi training 2 hari"
```

---

### Task 2: Verifikasi identitas & status hari

**Files:**
- Create: `modules/training_service.py`
- Test: `tests/test_training_service.py`

**Interfaces:**
- Consumes: tabel `recruitment_cases` (nik, tanggal_lahir, nama), `training_attendance`.
- Produces:
  - `attendance_status(nik, dob, branch_code, conn=None) -> dict` → `{'ok': True, 'nama': str, 'days': {1: dict|None, 2: dict|None}, 'next_day': 1|2|None}` atau `{'ok': False, 'error': 'not_found'|'db'}`
  - `mask_nik(nik) -> str`

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_nik_unknown_atau_dob_beda_selalu_not_found():
    assert attendance_status(NIK, '1990-01-01', 'SBY', conn=fake)['error'] == 'not_found'

def test_next_day_1_saat_belum_ada_absensi():
    assert attendance_status(NIK, DOB, 'SBY', conn=fake)['next_day'] == 1

def test_next_day_none_setelah_dua_hari():
    ...
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `python -m pytest tests/test_training_service.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: Implementasi**

- Normalisasi NIK dengan `modules.helpers.normalize_nik`.
- `SELECT case_id, nama, tanggal_lahir FROM recruitment_cases WHERE nik=%s`.
- Bandingkan `str(tanggal_lahir)[:10] == dob`; beda/absen → `not_found` (pesan route nanti generik).
- Ambil dua baris `training_attendance` untuk `case_id` + `branch_code`; susun `days` dan `next_day` (1 bila hari 1 kosong, 2 bila hari 1 ada dan hari 2 kosong, None bila lengkap).

- [ ] **Step 4: Jalankan tes**

Run: `python -m pytest tests/test_training_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/training_service.py tests/test_training_service.py
git commit -m "feat(training): verifikasi identitas dan status hari absensi"
```

---

### Task 3: Catat absensi, kunci Hari 2, tautkan Pelamar

**Files:**
- Modify: `modules/training_service.py`
- Test: `tests/test_training_service.py`

**Interfaces:**
- Produces: `record_attendance(nik, dob, branch_code, day, ip='', user_agent='', conn=None) -> dict`
  → `{'ok': True, 'day': int, 'link_status': str, 'applicant_id': int|None, 'days': dict}` atau `{'ok': False, 'error': 'invalid_day'|'not_found'|'day2_locked'|'db'}`
- Produces internal: `_resolve_applicant(cursor, nik) -> tuple[int|None, str]`

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_hari_2_ditolak_sebelum_hari_1():        # error == 'day2_locked', tidak ada INSERT
def test_submit_ganda_idempoten():                # dua kali hari 1 → satu baris, attended_at terbaru
def test_nama_sama_hp_beda_tidak_tertaut():       # link_status == 'unlinked'
def test_dua_kandidat_jadi_ambiguous():           # link_status == 'ambiguous', applicant_id None
def test_tertaut_mengisi_attendance_dan_status(): # applicant_attendance training_1 + status naik
def test_status_terminal_tidak_diubah():          # lulus tetap lulus
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `python -m pytest tests/test_training_service.py -k record -v`
Expected: FAIL

- [ ] **Step 3: Implementasi**

1. Validasi `day in (1, 2)`; status identitas seperti Task 2.
2. Bila `day == 2` dan hari 1 tidak ada → `day2_locked`.
3. Resolusi Pelamar:
   - Ambil CV terbaru: `SELECT nama, no_hp_norm FROM cv_online_submissions WHERE nik=%s ORDER BY submitted_at DESC LIMIT 1` (fallback `no_hp` bila `no_hp_norm` kosong, normalisasi dengan helper baru).
   - Kandidat: `SELECT id, nama_lengkap, no_hp, status FROM applicants WHERE UPPER(TRIM(nama_lengkap))=%s LIMIT 50`.
   - Bandingkan HP ternormalisasi; kandidat dengan status terminal diabaikan.
   - 1 → `linked`; 0 → `unlinked`; >1 → `ambiguous`.
4. `INSERT ... ON DUPLICATE KEY UPDATE attended_at=VALUES(attended_at), ip=..., user_agent=..., link_status=..., applicant_id=...`.
5. `recruitment_steps` TRAINING (case+branch): hari 1 → `PENDING`, hari 2 → `SELESAI`, `evidence_type='training_attendance'`, `evidence_id=<id absensi>`, `completed_at=NOW()`; `case_branch_history` upsert.
6. Bila `linked`: upsert `applicant_attendance` (`training_1`/`training_2`, `marked_by='Portal Training'`, `note='Absensi portal Hari N'`) dan naikkan `applicants.status` hanya bila status sekarang `interview`/`training_1` (tidak pernah menurunkan/terminal).

- [ ] **Step 4: Jalankan tes**

Run: `python -m pytest tests/test_training_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/training_service.py tests/test_training_service.py
git commit -m "feat(training): catat absensi, kunci hari 2, tautkan pelamar"
```

---

### Task 4: Endpoint publik ber-token

**Files:**
- Create: `modules/routes_training.py`
- Modify: `app.py` (registrasi route, dekat `register_recruitment_routes`)
- Test: `tests/test_training_routes.py`

**Interfaces:**
- Consumes: `training_service.attendance_status`, `training_service.record_attendance`, `routes_cv_online._branch_form_tokens` (atau salinan pembacaan tabel yang sama).
- Produces:
  - `GET /api/recruitment/training/status?token=&nik=&dob=`
  - `POST /api/recruitment/training/attendance` body `{token, nik, dob, day, consent}`
  - `register_training_routes(app) -> None`

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_token_salah_403_dan_tanpa_tulis()
def test_status_404_generik_untuk_dob_salah()
def test_submit_tanpa_consent_400()
def test_hari_2_409()
def test_submit_sukses_mengembalikan_status_hari()
def test_rate_limit_429()          # monkeypatch redis None + memori
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `python -m pytest tests/test_training_routes.py -v`
Expected: FAIL 404 untuk semua endpoint

- [ ] **Step 3: Implementasi**

- Validasi token dengan `secrets.compare_digest` terhadap `cv_online_branch_forms`; tidak valid → 403 `{'status':'error','msg':'Tautan form tidak valid...'}`.
- Rate limit: `redis_rate_hit('training|' + ip, 20, 600, fallback=...)` (pola `_lookup_ok` di `routes_recruitment.py`).
- Pesan 404: `'Data peserta tidak ditemukan. Periksa NIK dan tanggal lahir.'` (tidak membedakan NIK vs DOB).
- Sukses submit: audit `log_activity_async(None, 'training_attendance_portal', 'public', 'portal', new_data={'day':…,'branch_code':…,'nik_masked':mask_nik(nik),'link_status':…}, ip=…)`.
- Tidak pernah mengembalikan NIK penuh, case_id, atau applicant_id ke browser.

- [ ] **Step 4: Jalankan tes**

Run: `python -m pytest tests/test_training_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/routes_training.py app.py tests/test_training_routes.py
git commit -m "feat(training): endpoint publik status dan simpan absensi"
```

---

### Task 5: Halaman form training

**Files:**
- Create: `frontend/src/views/TrainingFormView.vue`
- Modify: `frontend/src/router/index.js` (dekat rute publik lain, baris ~32–39)
- Test: `frontend/src/views/TrainingFormView.test.js`

**Interfaces:**
- Consumes: `GET /api/recruitment/training/status`, `POST /api/recruitment/training/attendance`, query `token`.
- Produces: rute `training-form` (`meta.public: true`).

- [ ] **Step 1: Tulis tes yang gagal**

```js
it('mendaftarkan rute publik /training-form')
it('menampilkan Hari 1 dan Hari 2, Hari 2 terkunci bila Hari 1 kosong')
it('setelah simpan menampilkan konfirmasi dan status kedua hari')
it('menampilkan pesan ramah saat NIK/tanggal lahir tidak cocok')
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/TrainingFormView.test.js`
Expected: FAIL (komponen tidak ada)

- [ ] **Step 3: Implementasi**

- Langkah 1: NIK + tanggal lahir + tombol **Cek Status**.
- Langkah 2: kartu status Hari 1/Hari 2; radio Hari 2 `disabled` bila Hari 1 kosong dengan hint "Hari 2 terbuka setelah Hari 1 tercatat"; checkbox pernyataan; tombol **Simpan Absensi**.
- Sukses: panel hijau "Absensi Hari N tercatat" + status kedua hari + tautan kembali ke portal (`/app/recruitment-portal?token=…`).
- Gaya mengikuti `CvOnlineFormView.vue` (kartu putih, sudut 12 px, aksen biru), mobile-first 390 px.
- Simpan token hanya di memori; jangan tampilkan di UI.

- [ ] **Step 4: Jalankan tes**

Run: `cd frontend && npx vitest run src/views/TrainingFormView.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TrainingFormView.vue frontend/src/views/TrainingFormView.test.js frontend/src/router/index.js
git commit -m "feat(training): halaman absensi training 2 hari"
```

---

### Task 6: Aktifkan kartu Training di portal

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue` (objek `STEPS`)
- Test: `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: rute `training-form`.
- Produces: kartu `TRAINING` dengan `href` `/app/training-form?token=…`, tanpa `future`.

- [ ] **Step 1: Ubah tes lebih dulu**

```js
expect(card(w, 'TRAINING').attributes('data-locked')).toBe('true')   // sebelum lookup
expect(card(w, 'TRAINING').attributes('href')).toBe(`/app/training-form?token=${TOKEN}`) // setelah lookup
expect(card(w, 'TRAINING').text()).not.toContain('Segera tersedia')
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/RecruitmentPortalView.test.js`
Expected: FAIL (masih "Segera tersedia")

- [ ] **Step 3: Implementasi**

`STEPS[1]`: `href: formHref('training-form')`, `future: false`, deskripsi "Absensi Hari 1 dan Hari 2 training."

- [ ] **Step 4: Jalankan tes**

Run: `cd frontend && npx vitest run src/views/RecruitmentPortalView.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentPortalView.vue frontend/src/views/RecruitmentPortalView.test.js
git commit -m "feat(training): aktifkan kartu Training di portal"
```

---

### Task 7: Tampilkan Hari 1/Hari 2 di hub

**Files:**
- Modify: `modules/routes_recruitment.py` (payload `/api/recruitment/cases`)
- Modify: `frontend/src/views/RecruitmentCasesView.vue` (detail kasus)
- Test: `tests/test_recruitment_cases_training.py`, `frontend/src/views/RecruitmentCasesView.test.js`

**Interfaces:**
- Produces: field `training: [{day, attended_at, link_status}]` pada setiap baris kasus.

- [ ] **Step 1: Tulis tes yang gagal (backend + frontend)**

```python
def test_cases_memuat_training_dua_hari_dan_tidak_membocorkan_nik()
```

```js
it('menampilkan Training Hari 1 dan Hari 2 di detail kasus')
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `python -m pytest tests/test_recruitment_cases_training.py -v`
Run: `cd frontend && npx vitest run src/views/RecruitmentCasesView.test.js`

- [ ] **Step 3: Implementasi**

- Query massal `training_attendance` dengan `IN (...)` seperti pola `steps_by_case`; kirim `training` per kasus.
- Di detail kasus, di bawah langkah TRAINING: "Hari 1 — 25/11/2026 09:12 · terhubung ke Pelamar" / "belum terhubung ke Pelamar".

- [ ] **Step 4: Jalankan tes**

Run: `python -m pytest tests/test_recruitment_cases_training.py -v`
Run: `cd frontend && npx vitest run src/views/RecruitmentCasesView.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/routes_recruitment.py frontend/src/views/RecruitmentCasesView.vue tests/test_recruitment_cases_training.py frontend/src/views/RecruitmentCasesView.test.js
git commit -m "feat(training): tampilkan status hari training di hub"
```

---

### Task 8: Rilis, changelog, dan verifikasi penuh

**Files:**
- Modify: `CHANGELOG.md`, `docs/internal/PROGRESS.md`, `modules/version.py` (atau sumber versi repo)

- [ ] **Step 1: Naikkan versi minor + entri changelog**

Catat: form absensi training 2 hari, kunci Hari 2, pencocokan Pelamar, kartu portal aktif.

- [ ] **Step 2: Jalankan seluruh tes**

Run: `python -m pytest tests -q`
Run: `cd frontend && npm test`
Expected: semua lulus (kegagalan lingkungan DB yang sudah ada dicatat terpisah, bukan regresi).

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: build sukses, tidak ada peringatan baru.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/internal/PROGRESS.md modules/version.py
git commit -m "chore(release): absensi training portal 2 hari"
```

- [ ] **Step 5: Berhenti sebelum deploy**

Jangan merge/push/deploy tanpa persetujuan. Laporkan hasil tes + bukti screenshot lokal.
