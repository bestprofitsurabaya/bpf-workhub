# Rilis D — Master Karyawan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bangun master karyawan lengkap dari data rekrutmen + FirstWork + In-Out lama, dengan pencarian oleh resepsionis, pencatatan keluar/masuk satu klik, dan tampilan penuh untuk GA HR.

**Architecture:** Tabel `employees` dan `employee_attendance_events` di DB master; NIK sebagai kunci global. Pelamar yang lulus dipromosikan otomatis dari kasus + CV + FirstWork. Baris historis diisi lewat skrip seed idempoten. Halaman `/employees` menjadi satu pintu untuk resepsionis dan GA HR; menu In-Out lama menjadi arsip.

**Tech Stack:** Flask 3, MySQL/MariaDB, Vue 3 + Pinia + Vitest, FPDF (tidak berubah).

**Spec:** `docs/superpowers/specs/2026-11-26-rekrutmen-master-karyawan-design.md`

**Prasyarat:** Rilis C selesai dan ter-deploy (v2.136.0): NIK wajib, kasus, event, portal, FirstWork KTP-only.

## Global Constraints

- NIK lengkap hanya untuk `ga_hr` dan `admin`; resepsionis dan peran lain melihat `****1234`.
- NIK NULL sah selama `needs_nik=1`; NIK non-NULL unik.
- Seed tidak boleh mengaktifkan ulang karyawan yang sudah dinonaktifkan GA HR dan tidak menimpa field yang sudah diedit.
- Resepsionis hanya melihat/mencatat cabangnya sendiri; HO admin melihat semua.
- Satu klik = satu event keluar/masuk; arah yang sama dua kali ditolak 409.
- Koreksi memakai void + event baru, bukan menghapus riwayat.
- Semua skema aditif dan idempoten.
- Setiap rilis: pytest, Vitest, build, 7 titik stamp + DB, PROGRESS, CHANGELOG.

## Review Focus

- **NIK yang sudah punya karyawan dipromosikan lagi** → tidak membuat baris kedua; mengisi field kosong dan mengaktifkan kembali bila perlu. Test di Task D2.
- **Seed dijalankan ulang setelah GA HR menonaktifkan karyawan** → status aktif dan field HR tidak berubah. Test di Task D6.
- **Dua resepsionis menekan Keluar hampir bersamaan** → hanya satu event OUT; yang kedua 409. Test di Task D2/D3.
- **Karyawan pindah cabang** → tetap satu baris; riwayat absensi lama tidak hilang. Test di Task D3.
- **Baris legacy tanpa NIK** → tetap tampil dengan `needs_nik=1`; tidak memblokir pencarian nama. Test di Task D6.

---

### Task D1: Skema karyawan, absensi, dan penomoran

**Files:**
- Create: `modules/employee_schema.py`
- Modify: `app.py` (setelah `ensure_recruitment_events_schema`)
- Modify: `init.sql`
- Test: `tests/test_employee_schema.py`

**Interfaces:**
- Produces: `ensure_employee_schema(conn=None) -> bool`.

- [ ] **Step 1: Tulis tes skema**

```python
def test_membuat_tabel_employees_dan_event_absensi():
    cur = _FakeCursor()
    assert ensure_employee_schema(cur_conn(cur)) is True
    sql = ' '.join(cur.statements)
    assert 'CREATE TABLE IF NOT EXISTS employees' in sql
    assert 'UNIQUE KEY uq_emp_nik (nik)' in sql
    assert 'UNIQUE KEY uq_emp_source (source, source_uid)' in sql
    assert 'CREATE TABLE IF NOT EXISTS employee_attendance_events' in sql
    assert "ENUM('OUT','IN')" in sql
    assert 'CREATE TABLE IF NOT EXISTS employee_counters' in sql
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `pytest tests/test_employee_schema.py -v`
Expected: FAIL modul belum ada.

- [ ] **Step 3: Implementasikan DDL**

`employees` mengikuti spec bagian F: identitas, kontak, pekerjaan, pendidikan, asal-usul (`source`, `source_uid`, `case_id`, `needs_nik`), status (`is_active`, `deactivated_at/by/reason`), audit. `jabatan` default `'Business Consultant'`. `source` ENUM teks bebas (`VARCHAR(20)`), bukan ENUM ketat, agar impor baru tidak gagal.

`employee_attendance_events`: `employee_id`, `nik`, `branch_code`, `direction ENUM('OUT','IN')`, `event_at`, `actor_username`, `actor_name`, `note`, `voided_at`, `voided_by`, `void_reason`, `source`, `created_at`; index `(employee_id, event_at)`, `(branch_code, event_at)`.

`employee_counters`: `branch_code`, `series`, `last_value`, primary key `(branch_code, series)`.

- [ ] **Step 4: Daftarkan startup dan `init.sql`**

Tambahkan pemanggilan `ensure_employee_schema()` di `app.py` dengan retry 5x. Salin DDL ke `init.sql` agar fresh install dan CI drift check sinkron.

- [ ] **Step 5: Jalankan tes dan commit**

Run: `pytest tests/test_employee_schema.py tests/test_schema_drift.py -v`
Expected: PASS (drift check boleh SKIP bila DB tidak tersedia).

```bash
git add modules/employee_schema.py app.py init.sql tests/test_employee_schema.py
git commit -m "feat(employees): skema master karyawan dan absensi"
```

---

### Task D2: Layanan promosi, toggle absensi, dan nonaktif

**Files:**
- Create: `modules/employee_service.py`
- Test: `tests/test_employee_service.py`

**Interfaces:**
- `promote_to_employee(case_id, jabatan='Business Consultant', branch_code='', actor='', actor_role='', conn=None) -> dict`
  → `{'employee_id', 'employee_no', 'created', 'reactivated'}`
- `toggle_attendance(employee_id, direction, actor_username, actor_name, branch_code, note='', conn=None) -> dict`
  → `{'event_id', 'direction', 'event_at', 'status': 'OUT'|'IN'}`
- `deactivate_employee(employee_id, reason, actor, conn=None) -> dict`
- `reactivate_employee(employee_id, actor, conn=None) -> dict`
- `void_attendance(employee_id, event_id, reason, actor, conn=None) -> dict`
- `current_status(cursor, employee_id) -> 'OUT'|'IN'`
- `next_employee_no(cursor, branch_code) -> str` → `KRY-<CABANG>-<5 digit>`

- [ ] **Step 1: Tulis tes promosi**

```python
def test_promosi_mengisi_dari_kasus_cv_dan_firstwork(fake_master):
    result = promote_to_employee('RC-1', conn=fake_master)
    assert result['created'] is True
    row = fake_master.employees[0]
    assert row['nik'] == NIK
    assert row['nama'] == 'Budi Santoso'
    assert row['jabatan'] == 'Business Consultant'
    assert row['no_hp'] == '08123456789'

def test_promosi_nik_sama_tidak_menduplikasi(fake_master):
    promote_to_employee('RC-1', conn=fake_master)
    result = promote_to_employee('RC-1', conn=fake_master)
    assert result['created'] is False
    assert len(fake_master.employees) == 1
```

- [ ] **Step 2: Implementasikan `promote_to_employee`**

Baca kasus + CV terbaru + FirstWork terbaru. NIK wajib; bila kosong raise `ValueError('NIK wajib dilengkapi')`. Cari `employees WHERE nik=%s`; bila ada, isi hanya field kosong, set `is_active=1`, `deactivated_* = NULL`, catat event `EMPLOYEE_REACTIVATED` bila sebelumnya nonaktif. Bila belum ada, buat `employee_no` dari counter, `source='recruitment'`, `case_id`, `tanggal_masuk=hari ini`, lalu event `EMPLOYEE_CREATED`. Semua dalam satu transaksi koneksi yang diberikan.

- [ ] **Step 3: Tulis tes toggle**

```python
def test_toggle_out_lalu_out_lagi_ditolak(fake_master):
    toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=fake_master)
    with pytest.raises(ValueError, match='already_out'):
        toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=fake_master)

def test_toggle_mencatat_aktor_dan_waktu(fake_master):
    result = toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', note='ke bank', conn=fake_master)
    event = fake_master.attendance_events[0]
    assert event['direction'] == 'OUT'
    assert event['actor_name'] == 'Rina'
    assert event['note'] == 'ke bank'
    assert result['status'] == 'OUT'

def test_void_koreksi_lalu_arah_baru_diterima(fake_master):
    first = toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=fake_master)
    void_attendance(1, first['event_id'], 'salah tekan', 'ga_hr', conn=fake_master)
    assert current_status(fake_master.cursor(), 1) == 'IN'
    assert toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY',
                             conn=fake_master)['status'] == 'OUT'
```

- [ ] **Step 4: Implementasikan toggle**

Ambil event terakhir yang belum di-void. Arah sama → `ValueError('already_out'/'already_in')`. Cabang karyawan harus sama dengan `branch_code` (kecuali pemanggil mengirim `'*'` untuk HO). Insert event, update `updated_at`. `current_status` mengembalikan arah event terakhir atau `'IN'` bila belum ada.

- [ ] **Step 5: Implementasikan nonaktif/aktif**

`deactivate_employee` wajib alasan; set `is_active=0`, `deactivated_at=NOW()`, `deactivated_by=actor`, `deactivation_reason`; event `EMPLOYEE_DEACTIVATED`. `reactivate_employee` set aktif kembali dan event `EMPLOYEE_REACTIVATED`.

- [ ] **Step 6: Implementasikan void/koreksi absensi**

`void_attendance` hanya untuk GA HR/admin (penegakan di route): wajib alasan, set `voided_at=NOW()`, `voided_by=actor`, `void_reason`; tidak menghapus baris. Event koreksi dicatat di audit log, bukan menghapus riwayat. Tolak 409 bila event sudah di-void atau bukan milik karyawan tersebut. Setelah void, arah yang sama boleh dicatat lagi.

- [ ] **Step 7: Jalankan tes dan commit**

Run: `pytest tests/test_employee_service.py -v`
Expected: PASS.

```bash
git add modules/employee_service.py tests/test_employee_service.py
git commit -m "feat(employees): promosi, toggle absensi, dan nonaktif"
```

---

### Task D3: API karyawan dan batas peran

**Files:**
- Create: `modules/routes_employees.py`
- Modify: `app.py` (registrasi route)
- Test: `tests/test_employees_api.py`

**Interfaces:**
- `GET /api/employees?q=&branch_code=&active=&needs_nik=&limit=`
- `GET /api/employees/<int:employee_id>`
- `GET /api/employees/export.csv?active=&branch_code=` (GA HR/admin; NIK lengkap)
- `POST /api/employees/<int:employee_id>/attendance` body `{direction, note}`
- `POST /api/employees/<int:employee_id>/attendance/<int:event_id>/void` body `{reason}` (GA HR/admin)
- `POST /api/employees/<int:employee_id>/deactivate` body `{reason}` (GA HR/admin)
- `POST /api/employees/<int:employee_id>/reactivate` (GA HR/admin)
- `PATCH /api/employees/<int:employee_id>` (field HR; `nik` hanya GA HR/admin)
- Semua memakai `role_required(['receptionist','ga_hr','admin'])`; aksi tulis nonaktif/edit/void hanya `ga_hr|admin`.

- [ ] **Step 1: Tulis tes daftar dan masking**

```python
def test_resepsionis_hanya_melihat_cabangnya(client_receptionist, master):
    data = client_receptionist.get('/api/employees').get_json()['data']
    assert all(row['branch_code'] == 'SBY' for row in data)
    assert data[0]['nik_masked'] == '****0001'
    assert 'nik' not in data[0]

def test_ga_hr_melihat_nik_lengkap(client_ga_hr, master):
    assert client_ga_hr.get('/api/employees').get_json()['data'][0]['nik'] == NIK

def test_ekspor_hanya_ga_hr(client_receptionist, client_ga_hr, master):
    assert client_receptionist.get('/api/employees/export.csv').status_code == 403
    resp = client_ga_hr.get('/api/employees/export.csv')
    assert resp.status_code == 200
    assert 'text/csv' in resp.headers['Content-Type']

def test_void_absensi_hanya_ga_hr(client_receptionist, client_ga_hr, master):
    event_id = master.attendance_events[0]['id']
    r = client_receptionist.post(f'/api/employees/1/attendance/{event_id}/void',
                                 json={'reason': 'salah'})
    assert r.status_code == 403
    r = client_ga_hr.post(f'/api/employees/1/attendance/{event_id}/void',
                          json={'reason': 'salah'})
    assert r.status_code == 200
```

- [ ] **Step 2: Implementasikan daftar dan detail**

Filter `q` mencari `nama` (LIKE) dan NIK exact; `active=1/0`; `needs_nik=1`; `branch_code` hanya dihormati untuk GA HR/admin HO. Sertakan status sekarang (`OUT`/`IN`), event terakhir, dan jumlah event. Detail menambah riwayat 100 event dan profil lengkap; resepsionis hanya menerima subset kontak (tanpa NIK lengkap, tanpa field HR sensitif).

- [ ] **Step 3: Tulis tes toggle dan konflik**

```python
def test_toggle_keluar_lalu_kedua_409(client_receptionist, master):
    r1 = client_receptionist.post('/api/employees/1/attendance', json={'direction': 'OUT'})
    r2 = client_receptionist.post('/api/employees/1/attendance', json={'direction': 'OUT'})
    assert r1.status_code == 200
    assert r2.status_code == 409

def test_cabang_lain_ditolak(client_receptionist, master):
    master.employees[0]['branch_code'] = 'JKT'
    assert client_receptionist.post('/api/employees/1/attendance',
                                    json={'direction': 'OUT'}).status_code == 403
```

- [ ] **Step 4: Implementasikan endpoint tulis**

Waktu dari server, aktor dari sesi, audit `log_activity_async`. Nonaktif wajib alasan (400 bila kosong). PATCH hanya field yang diizinkan: `nama`, `jabatan`, `tanggal_masuk`, `status_kepegawaian`, `atasan`, `no_hp`, `alamat`, `pendidikan_terakhir`, `branch_code` (GA HR/admin). `nik` hanya bisa diisi GA HR/admin dan harus unik (409 bila sudah dipakai); setelah NIK terisi, set `needs_nik=0`. Void absensi wajib alasan, tolak 409 bila event sudah di-void, dan catat aktor/waktu. Ekspor CSV memakai `send_file`/`Response` dengan `Content-Disposition: attachment`, NIK lengkap hanya untuk GA HR/admin, dan audit tanpa NIK.

- [ ] **Step 5: Daftarkan route dan jalankan tes**

Di `app.py`, impor dan panggil `register_employee_routes(app)`.

Run: `pytest tests/test_employees_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_employees.py app.py tests/test_employees_api.py
git commit -m "feat(employees): API daftar, detail, toggle, dan nonaktif"
```

---

### Task D4: Promosi otomatis saat pelamar lulus

**Files:**
- Modify: `modules/routes_applicants.py:789-840`
- Modify: `modules/routes_receptionist.py:1020-1086` (alias lama)
- Test: `tests/test_applicants_promote.py`

**Interfaces:**
- `POST /api/applicants/<id>/status` dengan `status='lulus'` mengembalikan `{status:'success', employee_created: true, employee_no: 'KRY-SBY-00001'}`.
- Bila NIK kosong → 409 `'Lengkapi NIK sebelum menjadikan karyawan.'`
- `POST /api/applicants/<id>/register-employee` (lama) tetap ada sebagai alias: memanggil `promote_to_employee` dan **tidak** menulis `employee_inout` baru; tanpa NIK → 409.

- [ ] **Step 1: Tulis tes**

```python
def test_lulus_membuat_karyawan(client_receptionist, fake_branch, fake_master):
    fake_branch.applicants[0].update({'nik': NIK, 'status': 'training_4'})
    r = client_receptionist.post('/api/applicants/1/status', json={'status': 'lulus'})
    assert r.get_json()['employee_created'] is True
    assert fake_master.employees[0]['nik'] == NIK

def test_lulus_tanpa_nik_ditolak(client_receptionist, fake_branch):
    fake_branch.applicants[0].update({'nik': None, 'status': 'training_4'})
    r = client_receptionist.post('/api/applicants/1/status', json={'status': 'lulus'})
    assert r.status_code == 409
    assert 'NIK' in r.get_json()['msg']

def test_register_employee_lama_tidak_menulis_inout(client_receptionist,
                                                     fake_branch, fake_master):
    fake_branch.applicants[0].update({'nik': NIK, 'status': 'training_4'})
    client_receptionist.post('/api/applicants/1/register-employee', json={})
    assert fake_branch.employee_inout == []
    assert fake_master.employees[0]['nik'] == NIK
```

- [ ] **Step 2: Implementasikan hook**

Sebelum update status, bila `status == 'lulus'` dan `row['nik']` kosong → 409. Setelah commit status pelamar, panggil `promote_to_employee(case_id, branch_code=session['branch_code'], actor=...)`; bila berhasil, catat juga event `PASSED` (sudah ada di Task C3) dan event karyawan dari service. Bila promosi gagal, kembalikan sukses dengan `employee_created: false` dan `warning` agar UI dapat menampilkan tindakan ulang; jangan menggulung status lulus. Ubah `api_applicant_register_employee` menjadi alias: cari `case_id` dari NIK pelamar, panggil `promote_to_employee`, dan hapus penulisan `employee_inout` baru (baris lama tetap arsip).

- [ ] **Step 3: Jalankan tes dan commit**

Run: `pytest tests/test_applicants_promote.py tests/test_applicants.py -v`
Expected: PASS.

```bash
git add modules/routes_applicants.py tests/test_applicants_promote.py
git commit -m "feat(rekrutmen): promosi otomatis pelamar lulus ke master karyawan"
```

---

### Task D5: Halaman karyawan, menu, dan arsip In-Out

**Files:**
- Create: `frontend/src/views/EmployeesView.vue`
- Create: `frontend/src/views/EmployeesView.test.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Modify: `frontend/src/views/dashboard/EmployeeInOutView.vue` (mode arsip)
- Test: `frontend/src/views/dashboard/EmployeeInOutView.test.js` (bila ada)

**Interfaces:**
- Route `/employees`, roles `receptionist|ga_hr|admin`.
- Sidebar item **Karyawan** di grup SDM & Armada; item In-Out dihapus; `/inout` redirect ke `/employees?archive=1` dengan roles `receptionist|ga_hr|admin`.

- [ ] **Step 1: Tulis tes daftar dan toggle**

```js
it('menampilkan status Di Kantor dan tombol Keluar', async () => {
  api.mockResolvedValueOnce({ data: [{ id: 1, nama: 'Budi', status: 'IN', branch_code: 'SBY' }] })
  const wrapper = mount(EmployeesView)
  await flushPromises()
  expect(wrapper.text()).toContain('Di Kantor')
  expect(wrapper.text()).toContain('Keluar')
})

it('mengirim arah OUT saat tombol Keluar ditekan', async () => {
  ...
  await wrapper.find('[data-action="out"]').trigger('click')
  expect(api).toHaveBeenCalledWith('/api/employees/1/attendance', {
    method: 'POST', body: { direction: 'OUT', note: '' } })
})
```

- [ ] **Step 2: Implementasikan `EmployeesView.vue`**

Pencarian nama/NIK, filter cabang (GA HR/admin), filter aktif, `needs_nik`. Tabel: nama, NIK (termasker untuk resepsionis), jabatan, cabang, status Di Kantor/Di Luar, kejadian terakhir, tombol **Keluar**/**Kembali**. Modal detail: profil + riwayat; GA HR dapat edit, nonaktifkan (alasan wajib), aktifkan, koreksi/void event absensi (alasan wajib), ekspor CSV. Tampilkan banner `needs_nik` untuk baris legacy.

- [ ] **Step 3: Ubah router dan menu**

Tambah route `/employees`; ubah `/inout` menjadi redirect `{ path: '/employees', query: { archive: '1' } }`. Hapus item **In-Out Karyawan** dari sidebar dan tambah **Karyawan**. Route `/ga-hr` tetap untuk Overtime.

- [ ] **Step 4: Pertahankan arsip In-Out**

`EmployeeInOutView` hanya dirender bila `archive=1`; tampilkan banner "Arsip In-Out lama — data read-only" dan sembunyikan tombol catat. Backend lama tetap ada sampai GA HR selesai memverifikasi arsip.

- [ ] **Step 5: Jalankan tes dan build**

Run: `cd frontend && npm test -- --run src/views/EmployeesView.test.js src/views/dashboard/EmployeeInOutView.test.js`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: build sukses.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/EmployeesView.vue frontend/src/views/EmployeesView.test.js frontend/src/router/index.js frontend/src/layouts/AppLayout.vue frontend/src/views/dashboard/EmployeeInOutView.vue frontend/src/views/dashboard/EmployeeInOutView.test.js
git commit -m "feat(employees): halaman karyawan, toggle keluar/masuk, arsip in-out"
```

---

### Task D6: Seed karyawan dari FirstWork, unitedw, dan In-Out lama

**Files:**
- Create: `scripts/seed_employees.py`
- Test: `tests/test_seed_employees.py`

**Interfaces:**
- `seed_employees(conn, first_work_rows, inout_names, commit=False) -> dict`
  → `{'inserted', 'updated', 'skipped', 'needs_nik'}`.

- [ ] **Step 1: Tulis tes seed**

```python
def test_seed_mengisi_business_consultant_dari_firstwork(fake_master):
    result = seed_employees(fake_master, [FW_ROW], [], commit=True)
    assert result['inserted'] == 1
    row = fake_master.employees[0]
    assert row['jabatan'] == 'Business Consultant'
    assert row['source'] == 'firstwork'
    assert row['is_active'] == 1

def test_seed_mempertahankan_sumber_unitedw(fake_master):
    seed_employees(fake_master, [dict(FW_ROW, id=9, source='unitedw',
                                      source_uid='FP-9')], [], commit=True)
    assert fake_master.employees[0]['source'] == 'unitedw'

def test_seed_ulang_tidak_mengaktifkan_kembali(fake_master):
    seed_employees(fake_master, [FW_ROW], [], commit=True)
    fake_master.employees[0].update({'is_active': 0, 'deactivation_reason': 'keluar'})
    seed_employees(fake_master, [FW_ROW], [], commit=True)
    assert fake_master.employees[0]['is_active'] == 0
    assert len(fake_master.employees) == 1

def test_nik_invalid_tetap_impor_dengan_needs_nik(fake_master):
    result = seed_employees(fake_master, [dict(FW_ROW, nik='123')], [], commit=True)
    assert result['needs_nik'] == 1
    assert fake_master.employees[0]['nik'] is None
```

- [ ] **Step 2: Implementasikan seed**

Sumber: `first_work_submissions` (semua baris, NIK valid atau tidak), lalu nama unik `employee_inout` per cabang. `source` karyawan mengikuti `first_work_submissions.source` bila nilainya `unitedw`, selain itu `firstwork`. NIK valid → cari berdasarkan NIK; NIK invalid/kosong → `source_uid` stabil (`fw:<id>` / `io:<branch>:<nama_norm>`). Insert pertama: `is_active=1`, `jabatan='Business Consultant'` untuk FirstWork/unitedw dan `'Staf'` untuk In-Out, `tanggal_masuk` dari `submitted_at` (FirstWork) atau `created_at`/hari ini (In-Out). Baris yang sudah ada: hanya isi field kosong; **jangan** ubah `is_active`, `deactivated_*`, atau field yang sudah terisi.

- [ ] **Step 3: Skrip CLI**

`--dry-run` default, `--commit` untuk menulis. Kumpulkan `employee_inout` dari semua cabang lewat `get_db_connection(branch_code=...)`; nama dinormalisasi (uppercase, spasi tunggal). Laporkan jumlah per sumber dan NIK termasker.

- [ ] **Step 4: Jalankan tes dan commit**

Run: `pytest tests/test_seed_employees.py -v`
Expected: PASS.

```bash
git add scripts/seed_employees.py tests/test_seed_employees.py
git commit -m "feat(employees): seed idempoten dari firstwork, unitedw, dan in-out lama"
```

---

### Task D7: Rilis v2.137.0 dan deploy

**Files:**
- Modify: `CHANGELOG.md`, `docs/internal/PROGRESS.md`, 7 titik stamp
- Modify: `frontend/e2e/recruitment-flow.spec.ts` (tambah alur karyawan)
- Test: seluruh suite

- [ ] **Step 1: Bump v2.137.0**

Perbarui 7 titik stamp. Tambah entri CHANGELOG + PROGRESS: master karyawan, promosi otomatis, toggle keluar/masuk, seed 1.737 NIK + 76 nama In-Out, arsip In-Out, NIK masking.

- [ ] **Step 2: Verifikasi penuh**

Run: `pytest -q`
Expected: hijau.

Run: `cd frontend && npm test && npm run build`
Expected: hijau.

Run: `cd frontend && npm run e2e -- e2e/recruitment-flow.spec.ts`
Expected: hijau (4 alur, termasuk lulus → karyawan → keluar → kembali → nonaktif).

Run: `python3 scripts/check_version_stamps.py`
Expected: exit 0.

- [ ] **Step 3: Deploy NAS**

1. Commit + push.
2. NAS: `git pull`, `docker compose build web`, `docker compose up -d web`.
3. `python3 scripts/sync_version_stamp.py`; `python3 scripts/check_version_stamps.py --with-db` → exit 0.
4. Jalankan `python3 scripts/seed_employees.py --dry-run`, cocokkan jumlah, lalu `--commit`; ulangi untuk memastikan 0 insert.
5. Smoke: GA HR cari karyawan, resepsionis catat keluar → kembali, nonaktifkan dengan alasan, cek riwayat; pelamar lulus otomatis muncul sebagai karyawan.
6. Bersihkan semua data uji yang dibuat saat smoke (karyawan uji, event absensi, pelamar uji) dan pastikan seed ulang tetap 0 insert.

- [ ] **Step 4: Commit dokumentasi akhir**

```bash
git add CHANGELOG.md docs/internal/PROGRESS.md modules/company_identity.py modules/pdf_generator.py frontend/src/stores/identity.js frontend/public/sw.js docs/internal/USER_LIST.md guides/USER_GUIDE.md
git commit -m "release: v2.137.0 master karyawan lengkap"
```

---

## Catatan implementasi

- Jangan menghapus tabel `employee_inout`; itu arsip. Hanya UI dan penulisan baru yang dialihkan.
- Promosi otomatis memakai kasus + CV + FirstWork; tidak ada input ulang identitas.
- Bila NIK belum ada pada baris legacy, resepsionis/GA HR melengkapi lewat detail karyawan; setelah NIK terisi, baris bisa digabung dengan karyawan lain yang NIK-nya sama (manual, dengan konfirmasi).
- Ekspor karyawan GA HR memakai CSV; NIK lengkap hanya untuk `ga_hr|admin`.
- Data uji wajib dibersihkan; jangan meninggalkan karyawan fiktif di master.
