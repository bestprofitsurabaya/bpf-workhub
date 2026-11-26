# Portal Rekrutmen — Status Tahap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portal rekrutmen menampilkan status keempat tahap dari `recruitment_steps`, dengan pembeda `✓ Selesai` + waktu selesai, tampilan redup, dan tahap selesai yang tidak bisa dijalankan ulang.

**Architecture:** Perbesar respons `GET /api/recruitment/lookup` dengan `stages`, `nama_masked`, dan `next_action` agar tetap satu permintaan NIK+DOB+token cabang. Frontend membaca field baru itu untuk merender kartu; tidak ada tabel atau token sesi baru.

**Tech Stack:** Flask + `mysql.connector` (backend), Vue 3 + Vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-11-26-portal-rekrutmen-status-design.md`

## Global Constraints

- NIK divalidasi 16 digit; DOB tetap wajib dan divalidasi `YYYY-MM-DD`.
- Cabang selalu berasal dari `token` tautan (`cv_online_branch_forms`), bukan input pengguna.
- Rate limit 10 percobaan / 600 detik per IP dan `Cache-Control: no-store` dipertahankan.
- Kunci lama `status`, `known`, `can_continue` tidak dihapus; klien lama tetap bekerja.
- NIK lengkap, DOB, alamat, dan nama lengkap tidak pernah masuk respons.
- Tidak ada urutan wajib antar tahap; TKD boleh selesai sebelum CV.
- Tahap yang sudah `SELESAI` tidak boleh dibuka kembali atau diisi ulang dari portal; koreksi lewat petugas.
- Tidak ada skema baru; status diambil dari `recruitment_cases` + `recruitment_steps` yang sudah ada.

## Review Focus

- TKD selesai sebelum CV → status keempat tahap dihitung independen, bukan berurutan. Test: `test_lookup_menyertakan_status_tahap`.
- NIK dikenal hanya lewat `cv_online_submissions`/`first_work_submissions` tanpa `recruitment_cases` → semua stage `BELUM`, `next_action='CV'`. Test: `test_lookup_nik_terkenal_tanpa_kasus`.
- Beberapa baris `recruitment_steps` untuk satu `step_type` → status `SELESAI` menang atas yang lain. Test: `test_agregasi_status_memilih_selesai`.
- NIK invalid / token cabang invalid → tidak ada data tahap sama sekali. Test: `test_lookup_invalid_tetap_kontrak_lama`.
- Tahap selesai tidak bisa dibuka atau diisi ulang. Test: `test_kartu_selesai_menampilkan_centang_waktu_dan_redup` (assert `tagName === 'DIV'`, tanpa `href`).

---

### Task 1: Backend — status tahap di `/lookup`

**Files:**
- Modify: `modules/routes_recruitment.py` (helper + `api_recruitment_lookup`)
- Test: `tests/test_recruitment_lookup.py`

**Interfaces:**
- Consumes: `normalize_nik`, `_valid_dob`, `_lookup_ok`, `_nik_known`, `_response`, `_branch_from_token` (sudah ada di modul).
- Produces: `portal_summary(cursor, nik, known=False) -> dict` dengan kunci `nama_masked`, `stages` (list `{type, status, completed_at, can_open}`), `next_action`. Response `/lookup` menyertakan ketiga kunci itu.

- [ ] **Step 1: Tulis tes status tahap**

Tambahkan ke `tests/test_recruitment_lookup.py` (memakai fixture `client`/`db` yang ada):

```python
def test_lookup_menyertakan_status_tahap(client, db):
    db.tables['recruitment_cases'].append({
        'case_id': 'RC-1', 'nik': NIK, 'nama': 'Bili Darnanto Susilo'})
    db.tables['recruitment_steps'] = [
        {'case_id': 'RC-1', 'step_type': 'CV', 'status': 'SELESAI',
         'completed_at': '2026-11-25 19:28:30', 'branch_code': 'SBY'},
        {'case_id': 'RC-1', 'step_type': 'TKD', 'status': 'SELESAI',
         'completed_at': '2026-11-25 19:24:47', 'branch_code': 'SBY'},
    ]
    data = _lookup(client).get_json()
    assert [s['type'] for s in data['stages']] == ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']
    assert data['stages'][0]['status'] == 'SELESAI'
    assert data['stages'][0]['completed_at'] == '2026-11-25 19:28:30'
    assert data['stages'][2]['completed_at'] == '2026-11-25 19:24:47'
    assert data['stages'][1]['status'] == 'BELUM'
    assert data['stages'][0]['can_open'] is False
    assert data['stages'][2]['can_open'] is False
    assert data['stages'][1]['can_open'] is True
    assert data['next_action'] == 'TRAINING'
    assert data['nama_masked'] == 'Bili S.'
```

- [ ] **Step 2: Tulis tes kasus tepi**

```python
def test_lookup_nik_terkenal_tanpa_kasus(client, db):
    db.tables['cv_online_submissions'].append(db.baris(NIK))
    data = _lookup(client).get_json()
    assert data['known'] is True
    assert {s['status'] for s in data['stages']} == {'BELUM'}
    assert data['next_action'] == 'CV'


def test_agregasi_status_memilih_selesai(client, db):
    db.tables['recruitment_cases'].append({'case_id': 'RC-1', 'nik': NIK,
                                           'nama': 'Budi Santoso'})
    db.tables['recruitment_steps'] = [
        {'case_id': 'RC-1', 'step_type': 'CV', 'status': 'PENDING',
         'completed_at': None},
        {'case_id': 'RC-1', 'step_type': 'CV', 'status': 'SELESAI',
         'completed_at': '2026-11-25 19:28:30'},
    ]
    data = _lookup(client).get_json()
    assert data['stages'][0]['status'] == 'SELESAI'
    assert data['stages'][0]['completed_at'] == '2026-11-25 19:28:30'


def test_lookup_invalid_tetap_kontrak_lama(client, db):
    data = _lookup(client, nik='12345').get_json()
    assert set(data) == {'status', 'known', 'can_continue'}
```

- [ ] **Step 3: Jalankan tes, pastikan gagal**

Run: `pytest tests/test_recruitment_lookup.py -q`
Expected: FAIL (field `stages` belum ada).

- [ ] **Step 4: Implementasikan `portal_summary` dan pasang di lookup**

Di `modules/routes_recruitment.py`, tambahkan konstanta `_STAGE_TYPES = ('CV','TRAINING','TKD','FIRSTWORK')`, `_STATUS_RANK = {'BELUM':1,'PENDING':2,'DIKECUALIKAN':3,'SELESAI':4}`, dan fungsi:

```python
def portal_summary(cursor, nik, known=False):
    """Ringkasan empat tahap untuk satu NIK — tanpa data pribadi lengkap."""
```

Isi: SELECT `case_id, nama` dari `recruitment_cases` WHERE `nik=%s`; bila ada, SELECT `step_type, status, completed_at, branch_code` dari `recruitment_steps` WHERE `case_id=%s` lalu filter di Python berdasarkan `case_id`; agregasi per `step_type` dengan prioritas `_STATUS_RANK`, simpan `completed_at` dari baris `SELESAI` terakhir; `can_open` = `False` bila status `SELESAI`, selain itu `True` untuk CV dan `bool(known)` untuk sisanya; `next_action` = tahap pertama yang belum `SELESAI` dengan urutan `_STAGE_TYPES`, atau `'DONE'`; `nama_masked` = kata pertama + inisial kata kedua. Kembalikan `{'nama_masked','stages','next_action'}`.

Di `api_recruitment_lookup`, setelah `known` dihitung, panggil `portal_summary(cursor, nik, known)` dan gabungkan hasilnya ke payload sukses. Bila helper raises, kembalikan payload lama `{status, known, can_continue}` (best-effort). Jangan mengubah jalur NIK invalid/token invalid.

- [ ] **Step 5: Jalankan tes, pastikan lolos**

Run: `pytest tests/test_recruitment_lookup.py -q`
Expected: PASS (semua tes lama + 3 tes baru).

- [ ] **Step 6: Commit**

```bash
git add modules/routes_recruitment.py tests/test_recruitment_lookup.py
git commit -m "feat(portal): lookup mengembalikan status empat tahap"
```

---

### Task 2: Frontend — kartu dengan pembeda tahap selesai

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue`
- Test: `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: `GET /api/recruitment/lookup` dengan `stages`, `nama_masked`, `next_action` dari Task 1.
- Produces: kelas `rp-card--done`, teks `✓ Selesai · <waktu>`, baris `Langkah berikutnya: <label>`.

- [ ] **Step 1: Tulis tes UI**

Tambahkan ke `frontend/src/views/RecruitmentPortalView.test.js` dengan mock lookup:

```js
const LOOKUP_DONE = { status: 'success', known: true, can_continue: true,
  nama_masked: 'Bili S.', next_action: 'TRAINING',
  stages: [
    { type: 'CV', status: 'SELESAI', completed_at: '2026-11-25 19:28:30' },
    { type: 'TRAINING', status: 'BELUM', completed_at: null },
    { type: 'TKD', status: 'SELESAI', completed_at: '2026-11-25 19:24:47' },
    { type: 'FIRSTWORK', status: 'BELUM', completed_at: null } ] }

it('kartu selesai menampilkan centang, waktu, dan redup tetapi tetap bisa dibuka', async () => {
  const w = await mountPortal('?token=tok', LOOKUP_DONE)
  await cek(w, NIK, '1996-02-01')
  const cv = card(w, 'CV')
  expect(cv.text()).toContain('✓ Selesai')
  expect(cv.text()).toContain('2026-11-25 19:28:30')
  expect(cv.text()).toContain('tidak perlu diulang')
  expect(cv.classes()).toContain('rp-card--done')
  expect(cv.element.tagName).toBe('DIV')
  expect(cv.attributes('href')).toBeUndefined()
  expect(card(w, 'TRAINING').classes()).not.toContain('rp-card--done')
  expect(card(w, 'TRAINING').attributes('href')).toBeTruthy()
})

it('langkah berikutnya tampil dari respons lookup', async () => {
  const w = await mountPortal('?token=tok', LOOKUP_DONE)
  await cek(w, NIK, '1996-02-01')
  expect(w.text()).toContain('Langkah berikutnya: Training Absensi')
})
```

(Gunakan helper `mountPortal`/`cek`/`card` yang sudah ada di file tes; sesuaikan argumen bila helper lama hanya menerima satu argumen.)

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js`
Expected: FAIL (kelas/teks belum ada).

- [ ] **Step 3: Implementasikan UI**

Di `RecruitmentPortalView.vue`: simpan `summary` dari hasil lookup (`nama_masked`, `stages`, `next_action`); buat `stageStatus(type)` dan `stageTime(type)` dari `summary.stages`; pada setiap kartu tampilkan `✓ Selesai · <waktu> · tidak perlu diulang` bila status `SELESAI`, otherwise `Belum`; untuk tahap selesai, `cardTag(step)` harus mengembalikan `'div'` dan `cardAttrs(step)` mengembalikan `{}` sehingga tidak ada tautan/klik; tambahkan `:class="{ 'rp-card--done': isDone(step) }"`; tambahkan satu baris `Langkah berikutnya: <label>` di bawah header/sapaan. Sisa tahap yang belum selesai memakai aturan `isLocked` yang sudah ada. Label: CV → `CV Online`, TRAINING → `Training Absensi`, TKD → `Test Kemampuan Dasar`, FIRSTWORK → `FirstWork Absensi`. CSS `.rp-card--done { opacity: .68; }` — tetap `pointer-events` aktif.

- [ ] **Step 4: Jalankan tes dan build**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js && npm run build`
Expected: PASS dan build sukses.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentPortalView.vue frontend/src/views/RecruitmentPortalView.test.js
git commit -m "feat(portal): pembeda tahap selesai dan langkah berikutnya"
```

---

### Task 3: Rilis v2.135.2 dan deploy

**Files:**
- Modify: `CHANGELOG.md`, `docs/internal/PROGRESS.md`, 7 titik stamp
- Test: seluruh suite fokus

- [ ] **Step 1: Bump v2.135.2**

Perbarui `modules/company_identity.py`, `modules/pdf_generator.py`, `frontend/src/stores/identity.js`, `frontend/public/sw.js`, `CHANGELOG.md`, `docs/internal/USER_LIST.md`, `guides/USER_GUIDE.md`. Tambah catatan PROGRESS: lookup membawa status 4 tahap, kartu selesai ✓ + waktu + redup, langkah berikutnya.

- [ ] **Step 2: Verifikasi**

Run: `pytest tests/test_recruitment_lookup.py -q`
Run: `cd frontend && npm test -- --run && npm run build`
Run: `python3 scripts/check_version_stamps.py`
Expected: hijau, exit 0.

- [ ] **Step 3: Commit, push, deploy NAS**

Commit, push ke `origin/main`, di NAS `docker compose build web && docker compose up -d web`, jalankan `scripts/sync_version_stamp.py` lalu `scripts/check_version_stamps.py --with-db`.

- [ ] **Step 4: Smoke NIK contoh**

Cek produksi dengan NIK `3509190102960003` + DOB `1996-02-01` + token cabang SBY: respons harus memuat CV/TKD `SELESAI` dengan waktu masing-masing, Training/FirstWork `BELUM`, `next_action='TRAINING'`. Pastikan NIK lengkap tidak muncul di respons.

## Catatan implementasi

- Jangan menambah kolom/tabel; `recruitment_steps` sudah punya `status` dan `completed_at`.
- `can_open` untuk tahap non-CV mengikuti `known`, bukan CV selesai — ini disengaja karena TKD bisa selesai lebih dulu.
- Kartu selesai tetap memuat tautan/form yang sama; hanya tampilannya yang redup.
