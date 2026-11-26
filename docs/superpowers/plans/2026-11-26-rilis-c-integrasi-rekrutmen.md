# Rilis C — Integrasi Rekrutmen Berbasis NIK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Satukan intake resepsionis, portal publik, CV Online, Training, TKD, dan FirstWork menjadi satu kasus per NIK dengan linimasa kejadian, portal cek NIK sekali, FirstWork cukup KTP, dan menu rekrutmen 3 tab.

**Architecture:** `applicants` (DB cabang) mendapat kolom NIK dan menjadi sumber aksi per cabang; `recruitment_cases`/`recruitment_steps`/`recruitment_events` (DB master) menjadi sumber identitas dan riwayat lintas cabang. Event ditulis best-effort setelah transaksi sumber commit dan dapat dibangun ulang dari tabel sumber. Portal memakai token sesi bertanda tangan berisi NIK + cabang, bukan NIK di URL.

**Tech Stack:** Flask 3, MySQL/MariaDB, Vue 3 + Pinia + Vitest, FPDF, itsdangerous (bawaan Flask).

**Spec:** `docs/superpowers/specs/2026-11-26-rekrutmen-master-karyawan-design.md`

## Global Constraints

- NIK lengkap **tidak pernah** muncul di URL, respons publik, log, PDF, atau nama berkas. Publik hanya menerima NIK termasker (`****1234`).
- Portal publik **tidak meminta tanggal lahir**; pengecekan identitas hanya sekali di halaman utama portal.
- Satu tautan portal per cabang; cabang selalu berasal dari token cabang, bukan input pengguna.
- CV adalah gerbang tingkat kasus: CV `SELESAI` di cabang mana pun membuka tahap lain.
- Training Hari 2 tetap terkunci sampai Hari 1 tercatat (409).
- Semua perubahan skema **aditif** dan idempoten; aman diulang saat startup.
- Semua impor/backfill idempoten; putaran kedua 0 insert.
- Non-HO selalu terkurung cabang sesi; HO admin melihat semua.
- Setiap rilis: `pytest` hijau, `npm test` + `npm run build` hijau, 7 titik stamp + DB konsisten, `docs/internal/PROGRESS.md` dan `CHANGELOG.md` diperbarui.
- Jangan menyimpan kredensial unitedw di repo, log, atau dokumen.

## Review Focus

- **Dua cabang menyentuh NIK yang sama hampir bersamaan** → tetap satu `recruitment_cases`; tidak ada dua kasus, dan event tidak saling menimpa. Test di Task C3/C2.
- **Baris pelamar lama tanpa NIK ditautkan belakangan** → baris bergabung ke kasus yang sama; tidak ada karyawan ganda. Test di Task C3/C12.
- **DB master mati saat aksi cabang** → verifikasi/absensi/status tetap berhasil; event hilang tetapi `rebuild_recruitment_events.py` memulihkannya. Test di Task C2/C3.
- **Token kedaluwarsa atau dipakai untuk purpose lain** (portal vs kartu) → ditolak tanpa membocorkan data. Test di Task C4/C8.
- **FirstWork dikirim dua kali setelah kartu terbit** → mengembalikan registrasi + kartu yang sama, bukan baris baru. Test di Task C7.

---

### Task C1: Skema NIK pelamar dan tabel event

**Files:**
- Create: `modules/applicant_nik_schema.py`
- Create: `modules/recruitment_events_schema.py`
- Modify: `app.py` (setelah `ensure_recruitment_schema`)
- Modify: `init.sql` (DDL `applicants`, tabel `recruitment_events`)
- Test: `tests/test_applicant_nik_schema.py`
- Test: `tests/test_recruitment_events_schema.py`

**Interfaces:**
- Consumes: koneksi DB cabang dari `modules.config.get_db_connection`.
- Produces: `ensure_applicant_nik_schema(conn) -> bool` (menerima koneksi DB cabang); `ensure_applicant_nik_schema_all(branch_codes=None) -> dict` (loop semua cabang aktif); `ensure_recruitment_events_schema(conn=None) -> bool`.

- [ ] **Step 1: Tulis tes skema kolom NIK**

```python
def test_menambah_kolom_nik_dan_index():
    cur = _FakeCursor()
    assert ensure_applicant_nik_schema(cur_conn(cur)) is True
    sql = ' '.join(cur.statements)
    assert 'ADD COLUMN nik CHAR(16) NULL' in sql
    assert 'ADD COLUMN nik_source VARCHAR(20)' in sql
    assert 'ADD COLUMN linked_at DATETIME NULL' in sql
    assert 'ADD COLUMN link_status ENUM' in sql
    assert 'UNIQUE KEY uq_applicants_nik (nik)' in sql
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `pytest tests/test_applicant_nik_schema.py -v`
Expected: FAIL `ModuleNotFoundError: modules.applicant_nik_schema`.

- [ ] **Step 3: Implementasikan `ensure_applicant_nik_schema`**

Gunakan pola `_column_exists`/`_index_exists` seperti `modules/routes_receptionist.py:99-181`. DDL minimum:

```sql
ALTER TABLE applicants ADD COLUMN nik CHAR(16) NULL;
ALTER TABLE applicants ADD COLUMN nik_source VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE applicants ADD COLUMN linked_at DATETIME NULL;
ALTER TABLE applicants ADD COLUMN link_status ENUM('linked','unlinked','ambiguous') NOT NULL DEFAULT 'unlinked';
ALTER TABLE applicants ADD UNIQUE KEY uq_applicants_nik (nik);
ALTER TABLE applicants ADD KEY idx_applicants_link_status (link_status);
```

Fungsi harus mengembalikan `True` bila semua kolom/index ada setelah pemanggilan, dan `False` bila koneksi `None`.

- [ ] **Step 4: Tulis tes skema `recruitment_events`**

```python
def test_membuat_tabel_event_dengan_kunci_idempoten():
    cur = _FakeCursor()
    assert ensure_recruitment_events_schema(cur_conn(cur)) is True
    sql = ' '.join(cur.statements)
    assert 'CREATE TABLE IF NOT EXISTS recruitment_events' in sql
    assert 'UNIQUE KEY uq_re_event (source_module, branch_code, source_id, event_type)' in sql
```

- [ ] **Step 5: Implementasikan `ensure_recruitment_events_schema`**

DDL mengikuti spec bagian B. Kolom: `case_id`, `nik`, `event_type`, `event_at`, `branch_code`, `actor_role`, `actor_name`, `source_module`, `source_id`, `note`, `metadata_json`, `created_at`; index `(case_id, event_at)`, `(nik, event_at)`, `(branch_code, event_at)`.

- [ ] **Step 6: Daftarkan startup dan `init.sql`**

Di `app.py`, setelah blok `ensure_recruitment_schema()` tambahkan pemanggilan `ensure_recruitment_events_schema()` dengan retry 5x. Untuk `applicants` (DB cabang), panggil `ensure_applicant_nik_schema_all()` setelah master siap: ambil daftar cabang aktif dari `branches` (master), lalu untuk setiap cabang `get_db_connection(branch_code=code)` dan jalankan helper. Kegagalan satu cabang dicatat ke stdout dan tidak menghentikan startup; jalankan ulang saat startup berikutnya (idempoten). Di `init.sql`, tambahkan 4 kolom NIK + unique/index ke `CREATE TABLE applicants` dan DDL `recruitment_events` (definisi sama dengan helper). Tambahkan tes `ensure_applicant_nik_schema_all` memakai dua koneksi cabang palsu: kedua koneksi dipanggil dan hasilnya `{'SBY': True, 'JKT': True}`.

- [ ] **Step 7: Jalankan tes dan commit**

Run: `pytest tests/test_applicant_nik_schema.py tests/test_recruitment_events_schema.py tests/test_recruitment_schema.py -v`
Expected: PASS.

```bash
git add modules/applicant_nik_schema.py modules/recruitment_events_schema.py app.py init.sql tests/test_applicant_nik_schema.py tests/test_recruitment_events_schema.py
git commit -m "feat(schema): NIK pelamar dan linimasa event rekrutmen"
```

---

### Task C1b: Util NIK untuk tanggal lahir dan jenis kelamin

**Files:**
- Create: `modules/nik_utils.py`
- Test: `tests/test_nik_utils.py`

**Interfaces:**
- `normalize_nik(value) -> str` → 16 digit atau `''`.
- `parse_nik(nik) -> dict` → `{valid, tanggal_lahir: 'YYYY-MM-DD'|None, jenis_kelamin: 'L'|'P'|None, kode_wilayah, urut}`.
- `birth_date_from_nik(nik) -> 'YYYY-MM-DD'|None`, `gender_from_nik(nik) -> 'L'|'P'|None`.

- [ ] **Step 1: Tulis tes**

```python
def test_parse_nik_laki_laki():
    data = parse_nik('3573010101900001')
    assert data['tanggal_lahir'] == '1990-01-01'
    assert data['jenis_kelamin'] == 'L'

def test_parse_nik_perempuan_tanggal_plus_40():
    data = parse_nik('3573014101900001')
    assert data['tanggal_lahir'] == '1990-01-01'
    assert data['jenis_kelamin'] == 'P'

def test_parse_nik_tidak_valid():
    assert parse_nik('123')['valid'] is False
    assert birth_date_from_nik('3573019999990001') is None
```

Validasi tanggal harus menolak tanggal mustahil (mis. `99`), dan tahun 2 digit dipetakan dengan ambang 30: `yy <= 30` → 2000+yy, selain itu 1900+yy.

- [ ] **Step 2: Implementasikan**

Tanpa dependensi baru. `parse_nik` tidak mengakses DB dan tidak mencatat NIK ke log. Semua pemakaian DOB di CV Online memanggil `birth_date_from_nik`.

- [ ] **Step 3: Jalankan tes dan commit**

Run: `pytest tests/test_nik_utils.py -v`
Expected: PASS.

```bash
git add modules/nik_utils.py tests/test_nik_utils.py
git commit -m "feat(nik): turunkan tanggal lahir dan jenis kelamin dari NIK"
```

---

### Task C2: Penulis event, timeline, dan rebuild

**Files:**
- Create: `modules/recruitment_events.py`
- Create: `scripts/rebuild_recruitment_events.py`
- Test: `tests/test_recruitment_events.py`

**Interfaces:**
- Produces:
  - `record_event(case_id, nik, event_type, branch_code='', actor_role='', actor_name='', source_module='manual', source_id='', event_at=None, note='', metadata=None, conn=None) -> bool`
  - `fetch_timeline(cursor, case_id, limit=200) -> list[dict]`
  - `EVENT_TYPES` (frozenset)
  - `rebuild_events(conn=None, branch_rows=None) -> dict` (`{'inserted': int, 'skipped': int}`)
- `record_event` **tidak pernah melempar exception**; kegagalan mengembalikan `False` dan dicetak ke stdout.

- [ ] **Step 1: Tulis tes kontrak event**

```python
def test_event_idempoten_dan_nik_tidak_masuk_log(capsys):
    conn = _FakeConn()
    assert record_event('RC-1', NIK, 'VERIFIED', branch_code='SBY',
                        source_module='applicants', source_id='PLM-SBY-1',
                        conn=conn) is True
    assert record_event('RC-1', NIK, 'VERIFIED', branch_code='SBY',
                        source_module='applicants', source_id='PLM-SBY-1',
                        conn=conn) is True
    assert conn.event_rows == 1
    assert NIK not in capsys.readouterr().out

def test_kegagalan_master_tidak_melempar():
    conn = _BrokenConn()
    assert record_event('RC-1', NIK, 'VERIFIED', conn=conn) is False
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `pytest tests/test_recruitment_events.py -v`
Expected: FAIL modul belum ada.

- [ ] **Step 3: Implementasikan `record_event` dan `fetch_timeline`**

`record_event` membuka `get_master_connection()` bila `conn is None`, memakai `INSERT IGNORE INTO recruitment_events ...`, commit bila membuka sendiri, dan menelan semua exception. `metadata` disimpan sebagai JSON (`json.dumps`, `ensure_ascii=False`). `note` dipotong 500 karakter; `source_id` 64; `branch_code` 10.

`fetch_timeline` mengembalikan dict siap-JSON: `id, event_type, event_at, branch_code, actor_role, actor_name, source_module, note, metadata` (metadata di-parse dari JSON; nilai rusak menjadi `{}`).

- [ ] **Step 4: Tulis tes rebuild**

```python
def test_rebuild_membangun_event_dari_sumber(monkeypatch):
    # sumber: satu applicant terverifikasi, satu CV, satu FirstWork
    result = rebuild_events(conn=fake_master, branch_rows=fake_branch_rows)
    assert result['inserted'] >= 3
    assert rebuild_events(conn=fake_master, branch_rows=fake_branch_rows)['inserted'] == 0
```

- [ ] **Step 5: Implementasikan rebuild dan skrip**

`rebuild_events` membaca: `recruitment_cases`, `recruitment_steps` (`completed_at` → event `CV_SUBMITTED`/`FIRSTWORK_SUBMITTED`/`TRAINING_PORTAL_D2`/`TKD_SCORED`), `first_work_submissions`, `cv_online_submissions`, dan baris pelamar yang diberikan pemanggil. Skrip `scripts/rebuild_recruitment_events.py` mengumpulkan baris `applicants` dari semua cabang lewat `get_db_connection(branch_code=...)`, mendukung `--dry-run` (default) dan `--commit`, serta mencetak jumlah tanpa NIK lengkap.

- [ ] **Step 6: Jalankan tes dan commit**

Run: `pytest tests/test_recruitment_events.py -v`
Expected: PASS.

```bash
git add modules/recruitment_events.py scripts/rebuild_recruitment_events.py tests/test_recruitment_events.py
git commit -m "feat(recruitment): penulis event idempoten dan rebuild linimasa"
```

---

### Task C3: `ensure_case` dan intake wajib NIK

**Files:**
- Modify: `modules/recruitment_service.py`
- Modify: `modules/routes_applicants.py:620-840`
- Modify: `modules/routes_receptionist.py:919-1014`
- Test: `tests/test_recruitment_service.py`
- Test: `tests/test_applicants_nik.py`

**Interfaces:**
- Produces: `ensure_case(nik, nama=None, branch_code='', dob=None, source='manual', conn=None) -> str`
- `upsert_case_step(nik, nama, dob, branch_code, step_type, evidence_id, evidence_type=None, conn=None)` tetap ada dan sekarang memanggil `ensure_case` di dalam transaksi yang sama (parameter lama tidak berubah).
- Intake manual: body wajib `nik`; 400 bila bukan 16 digit; 409 bila NIK sudah ada di DB cabang. Intake manual **tidak** menulis `verified_by/verified_at` kecuali petugas mengirim `verify: true`.
- Tautan NIK: `POST /api/applicants/<id>/link-nik` body `{nik}` untuk `receptionist|ga_hr|admin`; 409 bila NIK sudah dipakai baris lain di cabang yang sama.
- Alasan `resigned` **selalu wajib**, bukan hanya bila sudah pernah hadir.

- [ ] **Step 1: Tulis tes `ensure_case` tidak menduplikasi dan tidak menimpa nama**

```python
def test_ensure_case_memakai_kasus_yang_sama_untuk_nik_sama(fake_master):
    first = ensure_case(NIK, 'Budi', 'SBY', conn=fake_master)
    second = ensure_case(NIK, 'Budi Lain', 'JKT', conn=fake_master)
    assert first == second
    assert fake_master.case_rows[0]['nama'] == 'Budi'

def test_ensure_case_menolak_nik_kurang_dari_16_digit(fake_master):
    with pytest.raises(ValueError):
        ensure_case('123', 'Budi', 'SBY', conn=fake_master)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `pytest tests/test_recruitment_service.py -v`
Expected: FAIL `ImportError: cannot import name 'ensure_case'`.

- [ ] **Step 3: Implementasikan `ensure_case` dan refaktor `upsert_case_step`**

Pindahkan blok SELECT/INSERT `recruitment_cases` + `case_branch_history` dari `upsert_case_step` ke `ensure_case`. `upsert_case_step` memanggil `ensure_case(...)` lalu menulis `recruitment_steps` seperti sekarang. Jangan mengubah perilaku commit/rollback saat `conn` diberikan.

- [ ] **Step 4: Tulis tes intake manual**

```python
def test_manual_wajib_nik_16_digit(client_receptionist, fake_branch):
    r = client_receptionist.post('/api/applicants/manual', json={'nama_lengkap': 'Budi'})
    assert r.status_code == 400
    assert 'NIK' in r.get_json()['msg']

def test_manual_nik_ganda_ditolak_409(client_receptionist, fake_branch):
    fake_branch.applicants.append({'id': 1, 'nik': NIK, 'display_id': 'PLM-SBY-1'})
    r = client_receptionist.post('/api/applicants/manual', json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert r.status_code == 409
    assert 'PLM-SBY-1' in r.get_json()['msg']

def test_manual_membuat_kasus_dan_event(client_receptionist, fake_branch, fake_master):
    r = client_receptionist.post('/api/applicants/manual', json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert r.status_code == 200
    assert fake_master.case_rows[0]['nik'] == NIK
    assert any(e['event_type'] == 'RECEPTIONIST_CREATED' for e in fake_master.events)

def test_manual_tidak_otomatis_verifikasi(client_receptionist, fake_branch):
    client_receptionist.post('/api/applicants/manual', json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert fake_branch.applicants[-1]['verified_at'] is None

def test_nik_sama_di_cabang_lain_memakai_kasus_sama(client_receptionist_sby,
                                                     client_receptionist_jkt,
                                                     fake_master):
    client_receptionist_sby.post('/api/applicants/manual',
                                 json={'nama_lengkap': 'Budi', 'nik': NIK})
    client_receptionist_jkt.post('/api/applicants/manual',
                                 json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert len(fake_master.case_rows) == 1
    assert {r['branch_code'] for r in fake_master.branch_history} == {'SBY', 'JKT'}

def test_link_nik_menautkan_baris_lama(client_receptionist, fake_branch, fake_master):
    fake_branch.applicants.append({'id': 7, 'nik': None, 'display_id': 'PLM-SBY-7',
                                   'nama_lengkap': 'Budi', 'no_hp': '0812'})
    r = client_receptionist.post('/api/applicants/7/link-nik', json={'nik': NIK})
    assert r.status_code == 200
    assert fake_branch.applicants[-1]['nik'] == NIK
    assert fake_branch.applicants[-1]['link_status'] == 'linked'
    assert fake_master.events[-1]['event_type'] == 'NIK_LINKED'

def test_resigned_selalu_wajib_alasan(client_receptionist, fake_branch):
    r = client_receptionist.post('/api/applicants/1/status', json={'status': 'resigned'})
    assert r.status_code == 400
    assert 'alasan' in r.get_json()['msg'].lower()
```

- [ ] **Step 5: Implementasikan intake manual**

Di `api_applicants_manual_add`: normalisasi `nik`; wajib 16 digit; cek `SELECT id, display_id FROM applicants WHERE nik=%s`; panggil `ensure_case(nik, nama, session['branch_code'], source='manual')` sebelum INSERT; simpan `nik`, `nik_source='manual'`, `linked_at=NOW()`, `link_status='linked'`. Jangan menulis `verified_by/verified_at` kecuali body `verify` truthy. Setelah commit panggil `record_event(..., 'RECEPTIONIST_CREATED', source_module='applicants', source_id=display_id)` dan `VERIFIED` hanya bila `verify` truthy. Pertahankan perilaku `jabatan` (langsung lulus) tetapi jangan menulis `employee_inout` baru bila `employee_service` Rilis D tersedia — pada Rilis C tetap seperti sekarang.

- [ ] **Step 6: Tautkan NIK pada endpoint khusus dan sync sheet**

Tambahkan `POST /api/applicants/<id>/link-nik` (role `receptionist|ga_hr|admin`): validasi 16 digit, cek baris lain dengan NIK sama di cabang itu (409 + `display_id`), `ensure_case`, update `nik/nik_source='manual'/linked_at/link_status='linked'`, commit, lalu `record_event(..., 'NIK_LINKED')`. Jangan menambah `nik` ke PATCH umum agar field identitas tidak bisa diubah lewat jalur edit biasa.

Sync sheet: bila sheet membawa NIK valid, isi `nik` hanya bila baris belum punya NIK; bila sheet tanpa NIK, cocokkan `nama + no_hp` ke `cv_online_submissions` terbaru (pola `_resolve_applicant` di `training_service.py`, dibalik). Hasil tunggal → link + `ensure_case`; hasil >1 → `link_status='ambiguous'`; tidak ada → `unlinked`. Bila NIK dari sheet sudah dipakai baris lain di cabang yang sama, jangan menimpa: lewati baris itu dan laporkan sebagai duplikat (sync tetap sukses). Sync tidak boleh menimpa NIK yang sudah ada dan tidak membuat kasus untuk baris tanpa NIK.

- [ ] **Step 7: Catat event dari verifikasi, kehadiran, dan status**

Di `verify` → `VERIFIED`; di `attendance` → `INTERVIEW`/`TRAINING_H1`..`TRAINING_H4`; di `status` → `RESIGNED`/`PASSED`/`REJECTED`. Semua memakai `source_id=display_id`, `event_at` dari waktu aksi, `actor_name` dari sesi, `note` alasan bila ada. Panggil setelah commit; kegagalan event tidak boleh mengubah respons sukses. Ubah validasi `resigned` agar alasan wajib untuk semua pelamar (bukan hanya yang sudah hadir); simpan ke `resign_reason` dan kirim ke event.

- [ ] **Step 8: Jalankan tes dan commit**

Run: `pytest tests/test_recruitment_service.py tests/test_applicants_nik.py tests/test_applicants.py -v`
Expected: PASS.

```bash
git add modules/recruitment_service.py modules/routes_applicants.py modules/routes_receptionist.py tests/test_recruitment_service.py tests/test_applicants_nik.py
git commit -m "feat(recruitment): intake NIK wajib dan event pelamar"
```

---

### Task C3b: Event dari CV, training, dan TKD

**Files:**
- Modify: `modules/routes_cv_online.py:414-535`
- Modify: `modules/training_service.py` (kembalikan `attendance_id`)
- Modify: `modules/routes_training.py:122-190`
- Modify: `modules/routes_tkd.py` (start/submit/score)
- Test: `tests/test_recruitment_events_sources.py`

**Interfaces:**
- `record_attendance(...)` menambah `attendance_id` pada hasil sukses (id baris `training_attendance`).
- Event yang ditulis: `CV_SUBMITTED`, `TRAINING_PORTAL_D1`, `TRAINING_PORTAL_D2`, `TKD_STARTED`, `TKD_SUBMITTED`, `TKD_SCORED`.

- [ ] **Step 1: Tulis tes sumber event**

```python
def test_cv_submit_menulis_event_cv_submitted(client_public, fake_master, cv_payload):
    client_public.post('/api/cv-online/public', data=cv_payload,
                       content_type='multipart/form-data')
    assert [e['event_type'] for e in fake_master.events] == ['CV_SUBMITTED']

def test_training_hari1_dan_hari2_menulis_event_berbeda(client_public, fake_master, app):
    s = issue_session_token(NIK, 'SBY')
    for day in (1, 2):
        client_public.post('/api/recruitment/training/attendance',
                           json={'token': BRANCH_TOKEN, 's': s, 'day': day,
                                 'consent': True})
    assert {e['event_type'] for e in fake_master.events} == {
        'TRAINING_PORTAL_D1', 'TRAINING_PORTAL_D2'}

def test_tkd_start_submit_score_menulis_tiga_event(client_public, fake_master, app):
    ...
    assert {'TKD_STARTED', 'TKD_SUBMITTED', 'TKD_SCORED'} <= {
        e['event_type'] for e in fake_master.events}

def test_event_sumber_gagal_tidak_menggagalkan_aksi(client_public, fake_master):
    fake_master.fail_events = True
    r = client_public.post('/api/cv-online/public', data=cv_payload,
                           content_type='multipart/form-data')
    assert r.status_code == 200
```

- [ ] **Step 2: Implementasikan penulisan event**

Panggil `record_event` **setelah** commit transaksi sumber, dengan `case_id` dari `upsert_case_step`/kasus yang sudah ada:
- CV: `source_module='cv'`, `source_id=registration_no`, `event_at=submitted_at`, `metadata={'branch_code': ...}`.
- Training: `source_module='training'`, `source_id=str(attendance_id)`, `metadata={'day': day}`; `branch_code` dari token.
- TKD: `source_module='tkd'`, `source_id=attempt_id`, `metadata={'attempt_no': ..., 'score': ...}` untuk submit/score; `event_at` dari waktu server.

Jangan menulis event di dalam transaksi sumber. Kegagalan `record_event` harus ditelan dan tidak mengubah respons (sudah dijamin Task C2).

- [ ] **Step 3: Jalankan tes dan commit**

Run: `pytest tests/test_recruitment_events_sources.py tests/test_cv_online_nik.py tests/test_training_routes.py tests/test_tkd_public_attempt.py -v`
Expected: PASS.

```bash
git add modules/routes_cv_online.py modules/training_service.py modules/routes_training.py modules/routes_tkd.py tests/test_recruitment_events_sources.py
git commit -m "feat(recruitment): event dari CV, training, dan TKD"
```

---

### Task C4: Token sesi portal, lookup NIK-only, dan ringkasan

**Files:**
- Create: `modules/portal_token.py`
- Modify: `modules/routes_recruitment.py:202-248`
- Test: `tests/test_portal_token.py`
- Modify: `tests/test_recruitment_lookup.py`
- Create: `tests/test_recruitment_summary.py`

**Interfaces:**
- Produces:
  - `issue_session_token(nik, branch_code, purpose='portal', ttl_seconds=1800) -> str`
  - `verify_session_token(token, purpose='portal', max_age=1800) -> dict | None`
  - `issue_card_token(submission_id, ttl_seconds=604800) -> str`
  - `GET /api/recruitment/lookup?nik=&token=<branch_token>` → `{status, known, can_continue, session_token}`
  - `GET /api/recruitment/portal/summary?token=<session_token>` → `{status, data:{known, nama_masked, branch_code, branch_name, stages, next_action, card_token}}`

- [ ] **Step 1: Tulis tes token**

```python
def test_token_bolak_balik_dan_purpose_terkunci(app):
    with app.test_request_context('/'):
        token = issue_session_token(NIK, 'SBY')
        data = verify_session_token(token)
        assert data == {'nik': NIK, 'branch': 'SBY', 'purpose': 'portal'}
        assert verify_session_token(token, purpose='card') is None

def test_token_kedaluwarsa_ditolak(app, monkeypatch):
    with app.test_request_context('/'):
        token = issue_session_token(NIK, 'SBY', ttl_seconds=1)
        monkeypatch.setattr('modules.portal_token._now', lambda: 10**12)
        assert verify_session_token(token, max_age=1) is None
```

- [ ] **Step 2: Implementasikan `portal_token.py`**

Gunakan `itsdangerous.URLSafeTimedSerializer(current_app.secret_key, salt='recruitment-session')`. `verify_session_token` membungkus `loads` dengan `max_age`; semua `BadSignature`/`SignatureExpired`/payload rusak → `None`. Token tidak boleh berisi nama, HP, atau DOB.

- [ ] **Step 3: Ubah lookup**

Hapus `dob` dari validasi dan respons. `token` query adalah token cabang (`cv_online_branch_forms.form_token`); cabang selalu berasal dari token itu. Token cabang hilang/tidak aktif → 403 tanpa membuka DB. Rate limit menjadi 10 percobaan / 600 detik per IP. NIK valid (16 digit) selalu mendapat `session_token` berisi `{nik, branch: <cabang token>, purpose: 'portal'}`; `known` tetap dicek dari tiga tabel. `Cache-Control: no-store` dipertahankan. NIK invalid → `known=false`, `can_continue=false`, tanpa token. Tambahkan tes: token cabang salah → 403; token cabang benar + NIK baru → `known=false` tetap dapat `session_token` dengan `branch` dari token.

- [ ] **Step 4: Tulis tes summary**

```python
def test_summary_memakai_token_dan_tidak_mengirim_nik(client, fake_master, app):
    token = issue_session_token(NIK, 'SBY')
    data = client.get('/api/recruitment/portal/summary', query_string={'token': token}).get_json()['data']
    assert NIK not in str(data)
    assert data['nama_masked'] == 'Budi S.'
    assert [s['type'] for s in data['stages']] == ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']

def test_summary_rate_limit(client, fake_master, app, monkeypatch):
    token = issue_session_token(NIK, 'SBY')
    for _ in range(11):
        last = client.get('/api/recruitment/portal/summary', query_string={'token': token})
    assert last.status_code == 429

def test_summary_cv_gate_dan_next_action(client, fake_master):
    # CV SELESAI di cabang lain membuka semua tahap
    ...
    assert data['stages'][1]['can_start'] is True

def test_summary_menolak_token_purpose_lain(client, fake_master):
    token = issue_card_token(1)
    assert client.get('/api/recruitment/portal/summary', query_string={'token': token}).status_code == 403
```

- [ ] **Step 5: Implementasikan summary**

Verifikasi token (purpose `portal`); terapkan rate limit 20 percobaan / 600 detik per IP dan `Cache-Control: no-store`. Baca kasus berdasarkan NIK; ambil langkah semua cabang untuk kasus; agregasi status per step (SELESAI > DIKECUALIKAN > PENDING > BELUM). CV gate: `cv_done = any(step CV SELESAI)`. `next_action`: CV bila belum selesai, lalu tahap pertama yang belum selesai (TRAINING/TKD/FIRSTWORK), selain itu `DONE`. `nama_masked`: kata pertama + inisial kata berikutnya. `branch_code`/`branch_name` dari token (bukan dari kasus), sehingga NIK baru tetap tampil di cabang tautan. `card_token` diisi bila `first_work_submissions` terbaru untuk NIK ada.

- [ ] **Step 6: Jalankan tes dan commit**

Run: `pytest tests/test_portal_token.py tests/test_recruitment_lookup.py tests/test_recruitment_summary.py -v`
Expected: PASS.

```bash
git add modules/portal_token.py modules/routes_recruitment.py tests/test_portal_token.py tests/test_recruitment_lookup.py tests/test_recruitment_summary.py
git commit -m "feat(portal): token sesi, lookup NIK-only, dan ringkasan tahap"
```

---

### Task C5: Portal publik satu kolom NIK

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue`
- Modify: `frontend/src/views/RecruitmentPortalView.test.js`
- Modify: `frontend/src/views/CvOnlineFormView.vue` + test
- Modify: `modules/routes_cv_online.py:378-535`
- Modify: `frontend/src/components/RecruitmentTkdPanel.vue`
- Test: `frontend/src/components/RecruitmentTkdPanel.test.js` (jika belum ada, buat)
- Test: `tests/test_cv_online_session_token.py`

**Interfaces:**
- Consumes: `GET /api/recruitment/lookup`, `GET /api/recruitment/portal/summary`.
- Produces: query `?token=<branch>&s=<session>` diteruskan ke form CV/Training/FirstWork/TKD.
- `GET /api/cv-online/form-meta?s=` → `{nama, nik_masked, branch_code}` (tanpa NIK lengkap).
- `POST /api/cv-online/public` menerima `s`; bila sah, NIK diambil dari token (bukan dari form) dan cabang token harus sama dengan token cabang.

- [ ] **Step 1: Tulis tes UI**

```js
it('hanya meminta NIK dan tidak menampilkan input tanggal lahir', () => {
  const wrapper = mount(RecruitmentPortalView)
  expect(wrapper.find('input[type="date"]').exists()).toBe(false)
  expect(wrapper.find('#rp-nik').exists()).toBe(true)
})

it('setelah cek memanggil summary dan menampilkan langkah berikutnya', async () => {
  api.mockResolvedValueOnce({ known: true, session_token: 'sess' })
  api.mockResolvedValueOnce({ data: { nama_masked: 'Budi S.', next_action: 'FIRSTWORK', stages: [...] } })
  await wrapper.find('form').trigger('submit')
  expect(api).toHaveBeenCalledWith('/api/recruitment/lookup',
    { params: { nik: '3573010101990001', token: 'branch-tok' } })
  expect(api).toHaveBeenLastCalledWith('/api/recruitment/portal/summary', { params: { token: 'sess' } })
  expect(wrapper.text()).toContain('Langkah berikutnya')
})
```

- [ ] **Step 2: Implementasikan UI**

Satu kolom NIK + tombol **Cek**. Setelah sukses: kartu sapaan (`Halo, {nama_masked}` + cabang), stepper 4 tahap tenang (Selesai/Berikutnya/Belum), dan kartu aksi. Kartu selesai tampil redup tetapi tetap bisa dibuka. Semua tautan form memakai `?token=<branchToken>&s=<sessionToken>`. NIK tak dikenal → CTA "Mulai dari CV Online" dengan tautan yang sama.

- [ ] **Step 2b: CV Online menerima token sesi**

```python
def test_cv_meta_dengan_sesi_tidak_mengirim_nik_lengkap(client, app, fake_master):
    s = issue_session_token(NIK, 'SBY')
    data = client.get('/api/cv-online/form-meta', query_string={'s': s}).get_json()
    assert data['nik_masked'] == '****0001'
    assert NIK not in str(data)

def test_cv_submit_memakai_nik_dari_token(client, app, fake_master, cv_payload):
    s = issue_session_token(NIK, 'SBY')
    cv_payload.pop('nik')
    r = client.post('/api/cv-online/public', data={**cv_payload, 's': s, 'token': BRANCH_TOKEN},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    assert fake_master.cv_rows[-1]['nik'] == NIK

def test_cv_submit_menurunkan_dob_dari_nik(client, app, fake_master, cv_payload):
    s = issue_session_token('3573014101900001', 'SBY')
    cv_payload.pop('nik')
    cv_payload.pop('tanggal_lahir')
    r = client.post('/api/cv-online/public',
                    data={**cv_payload, 's': s, 'token': BRANCH_TOKEN},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    row = fake_master.cv_rows[-1]
    assert row['tanggal_lahir'] == '1990-01-01'
    assert row['jenis_kelamin'] == 'P'

def test_cv_submit_menolak_dob_manual_yang_bertentangan(client, app, fake_master, cv_payload):
    s = issue_session_token('3573010101900001', 'SBY')
    r = client.post('/api/cv-online/public',
                    data={**cv_payload, 's': s, 'token': BRANCH_TOKEN,
                          'tanggal_lahir': '1985-05-05'},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    assert fake_master.cv_rows[-1]['tanggal_lahir'] == '1990-01-01'
```

Di `api_cv_online_form_meta`: bila `s` sah, kembalikan `nama` dari kasus + `nik_masked` + `branch_code`. Di `api_cv_online_public_submit`: bila `s` sah, pakai NIK dari token, tolak bila cabang token beda dengan token cabang, dan jangan pernah menulis NIK dari form. **`tanggal_lahir` dan `jenis_kelamin` selalu diturunkan dari NIK** lewat `modules/nik_utils.py`; nilai dari form diabaikan, dan bila NIK tidak dapat diurai, kolom dibiarkan `NULL` tanpa menggagalkan submit. Di `CvOnlineFormView`, hapus input tanggal lahir dan jenis kelamin; sembunyikan input NIK bila `s` ada (tampilkan NIK termasker) dan kirim `s` saat submit; tanpa `s`, pertahankan fallback input NIK. Hapus `tanggal_lahir` dari payload wajib dan dari validasi backend; pertahankan kolom DB agar data lama tetap terbaca.

- [ ] **Step 3: Sesuaikan panel TKD**

`RecruitmentTkdPanel` menerima prop `session` (string) dan `nik`/`dob` dihapus. Semua panggilan `/api/recruitment/tkd/*` mengirim `{token: branchToken, s: session}`. Bila `session` kosong, panel tidak dirender.

- [ ] **Step 4: Jalankan tes dan build**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js src/views/CvOnlineFormView.test.js`
Expected: PASS.

Run: `pytest tests/test_cv_online_session_token.py -v`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: build sukses.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentPortalView.vue frontend/src/views/RecruitmentPortalView.test.js frontend/src/views/CvOnlineFormView.vue frontend/src/views/CvOnlineFormView.test.js modules/routes_cv_online.py frontend/src/components/RecruitmentTkdPanel.vue frontend/src/components/RecruitmentTkdPanel.test.js tests/test_cv_online_session_token.py
git commit -m "feat(portal): cek NIK sekali, token sesi CV, dan ringkasan langkah berikutnya"
```

---

### Task C6: Training dan TKD memakai token sesi, bukan tanggal lahir

**Files:**
- Modify: `modules/training_service.py`
- Modify: `modules/routes_training.py`
- Modify: `modules/tkd_service.py:124-153`
- Modify: `modules/routes_tkd.py:120-135,198-213`
- Modify: `frontend/src/views/TrainingFormView.vue` + test
- Test: `tests/test_training_token.py`
- Test: `tests/test_tkd_token.py`

**Interfaces:**
- `attendance_status(nik, branch_code, conn=None)` (parameter `dob` dihapus)
- `record_attendance(nik, branch_code, day, ...)` (parameter `dob` dihapus)
- `verify_identity(cursor, nik) -> dict | None` (tanpa DOB)
- Endpoint training menerima `s` (session token) **atau** `nik`; TKD menerima `s` **atau** `nik` + `token`.

- [ ] **Step 1: Tulis tes training tanpa DOB**

```python
def test_status_training_memakai_session_token(client, fake_master, app):
    token = issue_session_token(NIK, 'SBY')
    r = client.get('/api/recruitment/training/status',
                   query_string={'token': BRANCH_TOKEN, 's': token})
    assert r.status_code == 200
    assert r.get_json()['data']['days'].keys() == {'1', '2'}

def test_tanpa_dob_tetap_bisa_absen(client, fake_master, app):
    token = issue_session_token(NIK, 'SBY')
    r = client.post('/api/recruitment/training/attendance',
                    json={'token': BRANCH_TOKEN, 's': token, 'day': 1, 'consent': True})
    assert r.status_code == 200
```

- [ ] **Step 2: Implementasikan perubahan backend training**

`_case_for(cursor, nik)` hanya mencari berdasarkan NIK. `routes_training` membaca `s`; bila valid, `nik` diambil dari token dan `branch` dari token cabang (tolak bila beda dengan token cabang). Bila `s` tidak ada, terima `nik` saja (fallback tautan langsung); `dob` tidak pernah dibaca. Perbarui `tests/test_training_service.py`: semua panggilan `attendance_status`/`record_attendance` menghapus argumen DOB dan harapan `not_found` karena DOB salah diubah menjadi kasus yang tetap ditemukan.

- [ ] **Step 3: Tulis tes TKD tanpa DOB**

```python
def test_tkd_status_memakai_session_token(client, fake_master, app):
    token = issue_session_token(NIK, 'SBY')
    r = client.post('/api/recruitment/tkd/status',
                    json={'token': BRANCH_TOKEN, 's': token})
    assert r.status_code == 200
```

- [ ] **Step 4: Implementasikan perubahan TKD**

`_verify_body` menerima `s`; bila valid, isi `nik`/`branch` dari token. `verify_identity(cursor, nik)` tidak membandingkan DOB. `resolve_branch_token` tetap memeriksa token cabang. Jangan mengubah aturan attempt/penilaian. Perbarui `tests/test_tkd_service_read.py` agar panggilan `verify_identity` memakai dua argumen dan kasus DOB salah tidak lagi dianggap identitas gagal.

- [ ] **Step 5: Sesuaikan form training**

Hapus input NIK dan tanggal lahir. Baca `s` dari query; kirim `{token, s}`. Bila `s` kosong, tampilkan satu input NIK (fallback) dan kirim `{token, nik}`. Hari 2 tetap disabled bila Hari 1 belum ada.

- [ ] **Step 6: Jalankan tes dan commit**

Run: `pytest tests/test_training_token.py tests/test_training_service.py tests/test_training_routes.py tests/test_tkd_token.py tests/test_tkd_public_status_start.py -v`
Expected: PASS.

Run: `cd frontend && npm test -- --run src/views/TrainingFormView.test.js`
Expected: PASS.

```bash
git add modules/training_service.py modules/routes_training.py modules/tkd_service.py modules/routes_tkd.py frontend/src/views/TrainingFormView.vue frontend/src/views/TrainingFormView.test.js tests/test_training_token.py tests/test_tkd_token.py
git commit -m "feat(rekrutmen): training dan TKD memakai token sesi tanpa tanggal lahir"
```

---

### Task C7: FirstWork cukup KTP dan data dari CV

**Files:**
- Modify: `modules/routes_first_work.py:1556-1775`
- Modify: `frontend/src/views/FirstWorkFormView.vue` + test
- Test: `tests/test_first_work_ktp_only.py`

**Interfaces:**
- `POST /api/first-work/public` menerima `s`, `token`, `ktp`, `consent`, dan field OCR opsional. Nama/NIK/pendidikan/HP diambil dari CV terbaru; field OCR hanya mengisi yang kosong.
- Respons sukses menambah `card_token` dan `card_url`.

- [ ] **Step 1: Tulis tes gate CV**

```python
def test_firstwork_ditolak_bila_cv_belum_selesai(client_public, master):
    r = client_public.post('/api/first-work/public', data={
        's': issue_session_token(NIK, 'SBY'), 'token': BRANCH_TOKEN,
        'consent': 'on'}, content_type='multipart/form-data')
    assert r.status_code == 409
    assert 'CV' in r.get_json()['msg']
```

- [ ] **Step 2: Tulis tes data dari CV dan KTP saja**

```python
def test_nama_dan_pendidikan_diambil_dari_cv(client_public, master, cv_row, ktp_file):
    r = client_public.post('/api/first-work/public', data={
        's': issue_session_token(NIK, 'SBY'), 'token': BRANCH_TOKEN,
        'consent': 'on', 'ktp': (ktp_file, 'ktp.jpg')},
        content_type='multipart/form-data')
    assert r.status_code == 200
    row = master.first_work_rows[-1]
    assert row['nama'] == cv_row['nama']
    assert row['pendidikan_raw'] == cv_row['pendidikan_terakhir']
```

- [ ] **Step 3: Implementasikan pengambilan profil CV dan gate**

Tambahkan `_cv_profile(cursor, nik)` yang mengambil `cv_online_submissions` terbaru berdasarkan NIK. Sebelum menulis, cek `recruitment_steps` untuk kasus NIK tersebut: `step_type='CV' AND status='SELESAI'` (cabang mana pun). Bila belum → 409. Isi `nama`, `pendidikan`, `no_hp`, `tempat_lahir`, `jenis_kelamin`, `alamat`, `domisili` dari CV; `tanggal_lahir`/`jenis_kelamin` dari CV bila ada, selain itu turunkan dari NIK lewat `modules/nik_utils.py`; field OCR/demografi hanya mengisi nilai kosong. Form FirstWork tidak meminta tanggal lahir. Bila `s` berasal dari cabang berbeda dengan token cabang → 403. Simpan ringkasan OCR (field + confidence bila tersedia) di `first_work_events.note`/metadata agar dapat diaudit; NIK lengkap tidak masuk log.

- [ ] **Step 4: Buat submit idempoten**

Bila `first_work_submissions` dengan NIK sama sudah ada, kembalikan 200 dengan `registration_no`, `card_token` baru, dan `already_exists: true`; jangan INSERT baru dan jangan menimpa data. Bila belum ada, lanjutkan alur INSERT yang sekarang + `upsert_case_step` + `record_event('FIRSTWORK_SUBMITTED', metadata={'registration_no': ..., 'ocr_confidence': ...})` + `record_event('CARD_ISSUED')`.

- [ ] **Step 5: Ubah form frontend**

Form hanya menampilkan: identitas terkunci (nama + NIK termasker dari summary), unggah KTP, ringkasan OCR collapsible, dan consent. Tombol kirim. Setelah sukses tampilkan nomor registrasi + tombol **Unduh Kartu** memakai `card_url`.

- [ ] **Step 6: Jalankan tes dan commit**

Run: `pytest tests/test_first_work_ktp_only.py tests/test_first_work_pdp.py tests/test_first_work_demographics.py -v`
Expected: PASS.

Run: `cd frontend && npm test -- --run src/views/FirstWorkFormView.test.js`
Expected: PASS.

```bash
git add modules/routes_first_work.py frontend/src/views/FirstWorkFormView.vue frontend/src/views/FirstWorkFormView.test.js tests/test_first_work_ktp_only.py
git commit -m "feat(firstwork): cukup KTP, data standar dari CV, submit idempoten"
```

---

### Task C8: Kartu Business Consultant dan unduhan publik bertoken

**Files:**
- Modify: `modules/pdf_generator.py` (setelah `FirstWorkCardPDF`)
- Modify: `modules/routes_first_work.py:2866-2925`
- Test: `tests/test_first_work_card_pdf.py`

**Interfaces:**
- `class BusinessConsultantCardPDF(BPFBasePDF)` dengan `generate(row)`.
- `GET /api/first-work/card/<int:submission_id>.pdf?t=<card_token>` publik bila token sah; staff tetap bisa tanpa token.

- [ ] **Step 1: Tulis tes PDF**

```python
def test_kartu_business_consultant_a6_tanpa_nik_lengkap():
    pdf = BusinessConsultantCardPDF()
    pdf.generate({'nama': 'Budi Santoso', 'nik': NIK, 'branch_code': 'SBY',
                  'registration_no': 'FW-SBY-1'})
    text = extract_pdf_text(pdf)
    assert 'Business Consultant' in text
    assert NIK not in text
    assert pdf.w > pdf.h  # A6 landscape (148 × 105 mm)
```

- [ ] **Step 2: Implementasikan kelas kartu**

A6 landscape (148 × 105 mm), satu kartu per halaman. Isi: kop/logo, nama, **Business Consultant**, cabang, nomor registrasi, NIK 4 digit terakhir, QR `BPF-FW:<registration_no>`. Tidak ada NIK lengkap di teks atau metadata.

- [ ] **Step 3: Tulis tes endpoint token**

```python
def test_kartu_publik_dengan_token_sah(client, row):
    t = issue_card_token(row['id'])
    r = client.get(f"/api/first-work/card/{row['id']}.pdf?t={t}")
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'no-store'

def test_kartu_token_untuk_id_lain_ditolak(client, row):
    t = issue_card_token(row['id'] + 1)
    assert client.get(f"/api/first-work/card/{row['id']}.pdf?t={t}").status_code == 403
```

- [ ] **Step 4: Implementasikan endpoint**

Hapus dekorator `@role_required`. Bila `t` ada: verifikasi token purpose `card` dan `submission_id` harus cocok; bila tidak sah → 403. Bila `t` tidak ada: periksa sesi dengan role `VIEW_ROLES` dan scope cabang; bila tidak berhak → 401/403. Selalu `Cache-Control: no-store` dan audit tanpa NIK.

- [ ] **Step 5: Jalankan tes dan commit**

Run: `pytest tests/test_first_work_card_pdf.py tests/test_first_work_isolation.py -v`
Expected: PASS.

```bash
git add modules/pdf_generator.py modules/routes_first_work.py tests/test_first_work_card_pdf.py
git commit -m "feat(firstwork): kartu Business Consultant dan unduhan publik bertoken"
```

---

### Task C9: Menu 3 tab, daftar orang, dan detail linimasa

**Files:**
- Modify: `modules/routes_recruitment.py` (setelah `/api/recruitment/cases`)
- Modify: `frontend/src/views/RecruitmentHubView.vue` + test
- Create: `frontend/src/views/RecruitmentPeopleView.vue`
- Create: `frontend/src/views/RecruitmentPersonDetail.vue`
- Create: `frontend/src/views/RecruitmentPeopleView.test.js`
- Test: `tests/test_recruitment_people.py`

**Interfaces:**
- `GET /api/recruitment/people?q=&branch_code=&stage=&status=&link=&view=`
- `GET /api/recruitment/people/<case_id>`
- `GET /api/recruitment/people/<case_id>/timeline`
- `GET /api/recruitment/cases/<case_id>/timeline` (alias kompatibilitas spec Rilis A)
- Hub tab: `pelamar` → PeopleView, `tkd`, `tautan`; query lama `kasus|cv|firstwork` dipetakan ke `pelamar`.

- [ ] **Step 1: Tulis tes API people**

```python
def test_people_menggabungkan_kasus_dan_pelamar_belum_tertaut(client_staff, master, branch):
    data = client_staff.get('/api/recruitment/people').get_json()['data']
    assert {row['case_id'] for row in data} >= {'RC-1', None}
    assert next(r for r in data if r['case_id'] is None)['link_status'] == 'unlinked'

def test_people_masking_nik_untuk_resepsionis(client_receptionist, master):
    row = client_receptionist.get('/api/recruitment/people').get_json()['data'][0]
    assert row['nik_masked'].startswith('****')
    assert len(row['nik_masked']) == 8

def test_people_ga_hr_mendapat_nik_lengkap(client_ga_hr, master):
    assert client_ga_hr.get('/api/recruitment/people').get_json()['data'][0]['nik'] == NIK

def test_people_ga_hr_melihat_semua_cabang(client_ga_hr, master):
    data = client_ga_hr.get('/api/recruitment/people').get_json()['data']
    assert {r['branch_code'] for r in data} == {'SBY', 'JKT'}

def test_people_finance_read_only_tanpa_aksi_tulis(client_finance, master):
    resp = client_finance.get('/api/recruitment/people', query_string={'view': 'firstwork'})
    assert resp.status_code == 200
    assert client_finance.post('/api/applicants/1/verify').status_code == 403
```

- [ ] **Step 2: Implementasikan `/people`**

Kasus master + langkah + event terakhir; baris pelamar `nik IS NULL OR link_status<>'linked'` dari DB cabang dalam scope. Scope: `ga_hr`/`admin` = semua cabang; `receptionist`/`traineer` = cabang sesi; `finance` = semua cabang tetapi hanya `view=firstwork` (ringkasan FirstWork + ekspor, tanpa aksi tulis). Filter `q` mencari nama (LIKE) dan NIK exact (server-side); NIK respons dimasker kecuali `ga_hr`/`admin`. Tahap sekarang = tahap terjauh dari langkah/event. Batasi 200 baris. NIK lengkap tidak pernah masuk log; audit memakai NIK termasker.

- [ ] **Step 3: Implementasikan detail + timeline**

Detail mengembalikan kasus, langkah, riwayat cabang, 50 event terakhir, CV terbaru, FirstWork terbaru, training H1/H2, dan `card_token` bila ada. Masking sama dengan `/people`. `GET /api/recruitment/cases/<case_id>/timeline` memakai fungsi yang sama dengan `/people/<case_id>/timeline` agar kontrak spec Rilis A tetap hidup.

- [ ] **Step 4: Ubah hub menjadi 3 tab**

`TABS` hanya `pelamar` (`RecruitmentPeopleView`), `tkd` (`TkdView`), `tautan` (`RecruitmentLinksView`). Peran: pelamar `receptionist|traineer|finance|ga_hr|admin` (finance read-only, `view=firstwork`), tkd `traineer|ga_hr|admin`, tautan `receptionist|traineer|ga_hr|admin`. `watchEffect` memetakan `kasus|cv|firstwork` → `pelamar`. Perbarui `RecruitmentHubView.test.js`: tepat tiga tombol tab untuk admin, label `Data Rekrutment`/`Soal TKD`/`Tautan Portal`, dan `?tab=kasus` mendarat di `pelamar`.

- [ ] **Step 5: Buat daftar orang**

Tabel: nama, NIK termasker, cabang, tahap, status, kejadian terakhir, aksi cepat. Filter cari/cabang/tahap/status/belum tertaut. Tombol toolbar: Sync Sheet (resepsionis), Ekspor CV/FirstWork (sesuai peran), Pengaturan user-options (admin). Baris tanpa NIK menampilkan aksi **Tautkan NIK**. Untuk `finance`, sembunyikan semua aksi tulis dan tampilkan tombol Ekspor FirstWork saja.

- [ ] **Step 6: Buat detail orang**

Drawer/modal dengan linimasa vertikal (waktu, aktor, cabang, catatan), bagian identitas/CV/training/TKD/FirstWork, dan aksi sesuai peran: verifikasi, interview, H1–H4, pulang (alasan wajib), lulus, tautkan NIK. Panggil endpoint yang sudah ada di Task C3.

- [ ] **Step 7: Jalankan tes dan build**

Run: `pytest tests/test_recruitment_people.py tests/test_recruitment_cases_api.py -v`
Expected: PASS.

Run: `cd frontend && npm test -- --run src/views/RecruitmentHubView.test.js src/views/RecruitmentPeopleView.test.js`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: build sukses.

- [ ] **Step 8: Commit**

```bash
git add modules/routes_recruitment.py frontend/src/views/RecruitmentHubView.vue frontend/src/views/RecruitmentHubView.test.js frontend/src/views/RecruitmentPeopleView.vue frontend/src/views/RecruitmentPersonDetail.vue frontend/src/views/RecruitmentPeopleView.test.js tests/test_recruitment_people.py
git commit -m "feat(rekrutmen): menu tiga tab, daftar orang, dan linimasa"
```

---

### Task C10: Pensiunkan `/apply` dan intake publik tanpa NIK

**Files:**
- Modify: `frontend/src/router/index.js`
- Delete/replace: `frontend/src/views/ApplyView.vue` (atau jadikan halaman pengalihan)
- Modify: `modules/routes_applicants.py:292-344`
- Test: `tests/test_apply_retired.py`
- Test: `frontend/src/router/routes.test.js` (assert redirect `/apply`)

**Interfaces:**
- `GET /apply` → redirect ke `/recruitment-portal`; tanpa token cabang, portal menampilkan pesan minta tautan cabang (bukan form).
- `POST /api/applicants` → `410 Gone` `{status:'error', msg:'Pendaftaran publik dipindahkan ke portal rekrutmen cabang.'}`; tidak menyentuh DB.

- [ ] **Step 1: Tulis tes**

```python
def test_apply_publik_dimatikan_tanpa_menulis_db(client, fake_branch):
    before = len(fake_branch.applicants)
    r = client.post('/api/applicants', json={'nama_lengkap': 'Budi', 'no_hp': '0812'})
    assert r.status_code == 410
    assert len(fake_branch.applicants) == before
```

```js
it('rute /apply dialihkan ke portal', async () => {
  await router.push('/apply')
  expect(router.currentRoute.value.name).toBe('recruitment-portal')
})
```

- [ ] **Step 2: Implementasikan pengalihan**

Ubah rute `/apply` menjadi redirect permanen ke `/recruitment-portal` (pertahankan `meta.public`). Hapus `ApplyView.vue` dari bundel bila tidak dipakai lagi. Di `api_apply_submit`, kembalikan 410 sebelum rate limit/DB; pertahankan endpoint baca `/api/applicants` untuk staff. Catat audit `apply_retired_hit` tanpa data pribadi.

- [ ] **Step 3: Jalankan tes dan commit**

Run: `pytest tests/test_apply_retired.py -v`
Expected: PASS.

Run: `cd frontend && npm test -- --run src/router/routes.test.js`
Expected: PASS.

```bash
git add frontend/src/router/index.js frontend/src/views/ApplyView.vue modules/routes_applicants.py tests/test_apply_retired.py frontend/src/router/routes.test.js
git commit -m "feat(rekrutmen): pensiunkan /apply dan intake publik tanpa NIK"
```

---

### Task C11: E2E alur rekrutmen

**Files:**
- Create: `frontend/e2e/recruitment-flow.spec.ts`
- Modify: `scripts/ci_e2e.sh` (seed data uji rekrutmen)
- Test: `frontend/e2e/recruitment-flow.spec.ts`

**Interfaces:**
- Memakai `E2E_BASE_URL` (Flask lokal + MariaDB uji), bukan produksi.
- Data uji memakai NIK khusus (`3573019900000001`–`...0004`) dan dibersihkan di `afterAll`.

- [ ] **Step 1: Tulis tiga alur spec (alur karyawan menyusul di Rilis D)**

```ts
test('resepsionis input NIK → verifikasi → interview → H1', async ({ page }) => { ... })
test('portal cek NIK → CV → FirstWork KTP → unduh kartu → training → TKD', async ({ page }) => { ... })
test('pelamar lama tanpa NIK → tautkan NIK → muncul di kasus yang sama', async ({ page }) => { ... })
```

Gunakan `page.request` untuk menyiapkan data (bukan klik UI untuk seed), lalu UI untuk alur yang diuji. Unduhan kartu diverifikasi sebagai PDF nyata (`%PDF`). Semua NIK dicari lewat API sebelum/sesudah untuk memastikan satu kasus.

- [ ] **Step 2: Bersihkan data uji**

`afterAll` menghapus `applicants`, `recruitment_cases/steps/events`, `training_attendance`, `cv_online_submissions`, `first_work_submissions`, dan `employees` untuk NIK uji. Jangan menyentuh data lain.

- [ ] **Step 3: Jalankan**

Run: `cd frontend && npm run e2e -- e2e/recruitment-flow.spec.ts`
Expected: PASS (3 alur Rilis C; alur karyawan dijalankan di Rilis D).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/recruitment-flow.spec.ts scripts/ci_e2e.sh
git commit -m "test(e2e): alur rekrutmen berbasis NIK dan master karyawan"
```

---

### Task C12: Penautan NIK lama, impor unitedw, rilis v2.136.0

**Files:**
- Create: `scripts/link_applicants_nik.py`
- Modify: `scripts/import_unitedw_firstwork.py` (bila perlu dukungan CSV 44 baris)
- Modify: `CHANGELOG.md`, `docs/internal/PROGRESS.md`, 7 titik stamp
- Test: `tests/test_link_applicants_nik.py`

**Interfaces:**
- `link_applicants_nik(conn_master, branch_rows, commit=False) -> dict` → `{linked, ambiguous, unlinked}`.

- [ ] **Step 1: Tulis tes penautan**

```python
def test_menautkan_hanya_bila_nama_dan_hp_cocok_tunggal():
    result = link_applicants_nik(master, rows, commit=False)
    assert result == {'linked': 1, 'ambiguous': 1, 'unlinked': 1}
    assert rows[0]['nik'] == NIK

def test_putaran_kedua_tidak_menulis_ulang():
    link_applicants_nik(master, rows, commit=True)
    assert link_applicants_nik(master, rows, commit=True)['linked'] == 0
```

- [ ] **Step 2: Implementasikan skrip**

Dry-run default; `--commit` menulis. Untuk setiap pelamar tanpa NIK: cari CV terbaru dengan nama + HP sama persis (pola `_resolve_applicant` di `training_service.py`). Hasil tunggal → isi NIK + `ensure_case` + event `NIK_LINKED`; hasil >1 → `link_status='ambiguous'`; tidak ada → biarkan. Laporkan jumlah, NIK termasker.

- [ ] **Step 3: Impor 44 pengajuan unitedw**

Jalankan importer yang ada dalam mode dry-run, cocokkan kolom 24 field, lalu commit setelah laporan bersih. Jangan menyimpan CSV mentah ke repo; hapus dari host setelah impor. Verifikasi putaran kedua `skipped`.

- [ ] **Step 4: Backfill event**

Jalankan `python3 scripts/rebuild_recruitment_events.py --dry-run`, cocokkan jumlah dengan tabel sumber, lalu `--commit`; ulangi untuk memastikan 0 insert.

- [ ] **Step 5: Bump v2.136.0 dan dokumentasi**

Perbarui 7 titik: `modules/company_identity.py`, `modules/pdf_generator.py`, `frontend/src/stores/identity.js`, `frontend/public/sw.js`, `CHANGELOG.md`, `docs/internal/USER_LIST.md`, `guides/USER_GUIDE.md`. Tambah entri PROGRESS berisi: portal NIK-only, token sesi, event, FirstWork KTP-only, kartu BC, 3 tab.

- [ ] **Step 6: Verifikasi penuh**

Run: `pytest -q`
Expected: hijau (skip yang memang lingkungan diperbolehkan).

Run: `cd frontend && npm test && npm run build`
Expected: hijau.

Run: `cd frontend && npm run e2e -- e2e/recruitment-flow.spec.ts`
Expected: hijau (3 alur rekrutmen).

Run: `python3 scripts/check_version_stamps.py`
Expected: exit 0.

- [ ] **Step 7: Deploy NAS**

1. Commit + push.
2. Di NAS: `git pull`, `docker compose build web`, `docker compose up -d web`.
3. Jalankan `python3 scripts/link_applicants_nik.py` (dry-run → commit).
4. Jalankan `python3 scripts/rebuild_recruitment_events.py` (dry-run → commit).
5. Jalankan `python3 scripts/sync_version_stamp.py`, lalu `python3 scripts/check_version_stamps.py --with-db` → exit 0.
6. Smoke: portal cek NIK → CV → FirstWork → unduh kartu; resepsionis input NIK; training H1/H2; TKD.
7. Bersihkan semua data uji yang dibuat saat smoke.

- [ ] **Step 8: Commit dokumentasi akhir**

```bash
git add CHANGELOG.md docs/internal/PROGRESS.md modules/company_identity.py modules/pdf_generator.py frontend/src/stores/identity.js frontend/public/sw.js docs/internal/USER_LIST.md guides/USER_GUIDE.md scripts/link_applicants_nik.py tests/test_link_applicants_nik.py
git commit -m "release: v2.136.0 integrasi rekrutmen berbasis NIK"
```

---

## Catatan implementasi

- `applicants` tetap di DB cabang. Jangan memindahkannya ke master pada rilis ini.
- `record_event` dipanggil **setelah** commit sumber. Jangan membungkusnya dalam transaksi yang sama.
- Endpoint lama `/api/recruitment/cases` dipertahankan sampai PeopleView stabil; UI baru tidak memakainya.
- Untuk `finance`: PeopleView menampilkan kolom baca-saja terkait FirstWork dan tombol ekspor; backend `/people` mengizinkan `finance` hanya bila parameter `view=firstwork` disertakan (tanpa aksi tulis).
- Semua data uji yang dibuat saat verifikasi wajib dihapus sebelum rilis ditutup.
