# Rilis A — Fondasi Kasus & Deteksi Rekrutmen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun fondasi kasus rekrutmen berbasis NIK di WorkHub, dengan portal satu tautan per cabang, deteksi NIK lintas cabang, dan dashboard Traineer/GA HR — tanpa mengubah form FirstWork atau mengimpor data unitedw.

**Architecture:** Modul baru `modules/recruitment.py` + route `modules/routes_recruitment.py` di DB master. Tabel kasus/langkah/riwayat cabang menjadi sumber kebenaran alur; modul CV Online dan FirstWork tetap menjadi sumber data langkah. Endpoint publik hanya boolean; detail hanya untuk staff.

**Tech Stack:** Python 3.11 / Flask / mysql.connector / pytest, Vue 3 / Vitest, MariaDB master.

**Spec:** `docs/superpowers/specs/2026-11-24-recruitment-consolidation-design.md`

## Global Constraints

- Versi rilis **v2.133.0** (bump oleh controller setelah semua task).
- Tidak menyentuh 12 field demografi FirstWork, cetak kartu, atau impor 226 data unitedw — itu Rilis B.
- NIK = 16 digit hasil `normalize_nik` dari `modules.routes_first_work`; gunakan helper yang sama, jangan duplikasi.
- Data kasus di **DB master** (`get_master_connection`), bukan DB cabang.
- Token cabang tetap menentukan `branch_code` tiap langkah; NIK hanya identitas.
- Endpoint publik: boolean-only, `Cache-Control: no-store`, rate limit.
- Peran staff: `traineer`, `ga_hr`, `admin`.
- Setiap task: failing test → implement → passing test → commit.

## Review Focus

- NIK yang sama di dua cabang tidak boleh membuat dua kasus.
- Endpoint publik tidak boleh membocorkan cabang/tahap/status selain `known`/`can_continue`.
- Lookup untuk NIK yang belum ada tidak boleh membuat baris kasus (PII minimization).
- Submit CV/FirstWork gagal harus tetap rollback kasus/langkah (atomic).
- Petugas tanpa alasan tidak boleh menandai `DIKECUALIKAN`.

---

### Task 1: Skema kasus rekrutmen

**Files:**
- Create: `modules/recruitment_schema.py`
- Modify: `init.sql`
- Modify: `app.py` (panggil ensure setelah `ensure_appointments_schema`)
- Test: `tests/test_recruitment_schema.py`

**Interfaces:**
- Consumes: `get_master_connection()` dari `modules.config`.
- Produces: `ensure_recruitment_schema(conn=None) -> bool`; tabel `recruitment_cases`, `recruitment_steps`, `case_branch_history`.

- [ ] **Step 1: Write failing test**

```python
def test_ensure_membuat_tiga_tabel(fake_conn):
    from modules.recruitment_schema import ensure_recruitment_schema
    assert ensure_recruitment_schema(fake_conn) is True
    assert {'recruitment_cases','recruitment_steps','case_branch_history'} <= set(fake_conn.created)
```

- [ ] **Step 2: Run test — FAIL** (`pytest tests/test_recruitment_schema.py -q`)

- [ ] **Step 3: Implement schema**

DDL: `recruitment_cases(id, case_id UNIQUE, nik UNIQUE, nama, tanggal_lahir, first_seen_at, first_branch, status, merged_from, created_at, updated_at)`; `recruitment_steps(id, case_id, step_type ENUM('CV','TRAINING','TKD','FIRSTWORK'), status ENUM('BELUM','PENDING','SELESAI','DIKECUALIKAN'), branch_code, evidence_type, evidence_id, exception_reason, completed_at, actor, UNIQUE(case_id, step_type, branch_code))`; `case_branch_history(id, case_id, branch_code, first_seen_at, last_seen_at, UNIQUE(case_id, branch_code))`. Semua `CREATE TABLE IF NOT EXISTS`.

- [ ] **Step 4: Run test — PASS**; commit.

```bash
git add modules/recruitment_schema.py init.sql app.py tests/test_recruitment_schema.py
git commit -m "feat: skema kasus rekrutmen lintas cabang"
```

---

### Task 2: NIK pada form CV Online

**Files:**
- Modify: `modules/routes_cv_online.py`
- Modify: `frontend/src/views/CvOnlineFormView.vue`
- Test: `tests/test_cv_online_nik.py`, `frontend/src/views/CvOnlineFormView.test.js`

**Interfaces:**
- Consumes: `normalize_nik` dari `modules.routes_first_work` (atau pindahkan ke helper bersama bila import cycle — putuskan di task ini, catat di report).
- Produces: kolom `nik`, `nik_raw`, `consent_at` sudah ada; field baru `nik` di payload submit CV.

- [ ] **Step 1: failing test** — submit CV tanpa NIK ditolak 400; NIK 16 digit diterima dan tersimpan.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** validasi + UI field NIK dengan pesan consent; data lama NULL tetap bisa dibaca.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 3: Endpoint lookup publik boolean-only

**Files:**
- Modify: `modules/routes_recruitment.py` (buat file jika belum ada)
- Test: `tests/test_recruitment_lookup.py`

**Interfaces:**
- Consumes: tabel Task 1; `first_work_submissions.nik`, `cv_online_submissions.nik`.
- Produces: `GET /api/recruitment/lookup?nik=&dob=` → `{'status':'success','known':bool,'can_continue':bool}`.

- [ ] **Step 1: failing test** — NIK belum ada → `known False`; NIK ada di FirstWork cabang lain → `known True`; response tidak mengandung `branch`/`step`; header `no-store`; 10x request → 429.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** `known = exists in cases OR cv_online OR first_work`; `can_continue = known` (NIK baru mendapat `known=false`, kartu CV tetap tersedia di portal); jangan insert apa pun; pakai rate limiter Redis yang sudah ada.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 4: Upsert kasus & langkah saat submit

**Files:**
- Create: `modules/recruitment_service.py`
- Modify: `modules/routes_cv_online.py`, `modules/routes_first_work.py`
- Test: `tests/test_recruitment_service.py`

**Interfaces:**
- Consumes: `upsert_case_step(nik, nama, dob, branch_code, step_type, evidence_id) -> case_id`.
- Produces: kasus dibuat sekali per NIK; `recruitment_steps` berisi evidence; `case_branch_history` bertambah bila cabang baru.

- [ ] **Step 1: failing test** — dua submit NIK sama di cabang beda → satu kasus, dua baris step, dua baris branch history.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** helper dipanggil di dalam transaksi submit yang sudah ada; bila gagal, submit ikut rollback.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 5: Exception langkah per orang

**Files:**
- Modify: `modules/routes_recruitment.py`
- Test: `tests/test_recruitment_exception.py`

**Interfaces:**
- Consumes: `recruitment_steps`.
- Produces: `POST /api/recruitment/steps/<id>/exception` body `{'reason':str}`; hanya status `BELUM`/`PENDING` yang boleh; alasan wajib; audit via `log_activity_async(..., new_data={'step_id':..., 'reason':...})`.

- [ ] **Step 1: failing test** — alasan kosong → 400; alasan ada → 200 + status `DIKECUALIKAN`; audit tercatat.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement**; role `traineer/ga_hr/admin`.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 6: Dashboard kasus staff

**Files:**
- Create: `frontend/src/views/RecruitmentCasesView.vue`
- Modify: `frontend/src/router/index.js`
- Test: `frontend/src/views/RecruitmentCasesView.test.js`

**Interfaces:**
- Consumes: `GET /api/recruitment/cases?nik=&branch=&status=`.
- Produces: tabel kasus + matriks 4 langkah + penanda cabang asal/saat ini + tombol exception.

- [ ] **Step 1: failing test** — render NIK termask, 4 kolom langkah, tombol exception hanya untuk staff.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement** mengikuti pola `FirstWorkView.vue`; NIK ditampilkan 4 digit terakhir.
- [ ] **Step 4: run — PASS**; commit.

---

### Task 7: Portal per cabang 4 kartu

**Files:**
- Create: `frontend/src/views/RecruitmentPortalView.vue`
- Modify: `frontend/src/router/index.js` (route publik `/recruitment-portal`)
- Test: `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: `/api/recruitment/lookup`, token cabang dari query.
- Produces: halaman dengan input NIK+tanggal lahir; sebelum dikenal hanya kartu CV aktif; setelah dikenal 4 kartu aktif; tautan ke form CV/FirstWork dengan token cabang.

- [ ] **Step 1: failing test** — kartu CV tampil, 3 kartu lain terkunci sebelum lookup; setelah `known true` semua aktif; tidak menampilkan nama cabang lama.
- [ ] **Step 2: run — FAIL**
- [ ] **Step 3: implement**; tidak menulis data kasus saat lookup.
- [ ] **Step 4: run — PASS**; commit.
