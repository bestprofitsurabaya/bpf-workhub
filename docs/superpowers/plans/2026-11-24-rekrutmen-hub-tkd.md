# Hub Rekrutmen & TKD Online Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menyatukan alur rekrutmen WorkHub menjadi satu menu bertab, satu tautan portal per cabang, dan ujian TKD online yang dinilai otomatis dengan maksimal dua percobaan.

**Architecture:** TKD memakai bank soal global di DB master, percobaan dengan snapshot soal/kunci/poin, penilaian murni di server, dan satu skor resmi per kasus (`recruitment_cases.tkd_score`). Logika murni (identitas, sampling, penilaian, validasi, CSV) dipisah dari orkestrasi DB dan route HTTP. Frontend menambah satu hub route `/recruitment?tab=...`, satu komponen ujian publik di portal, dan tiga panel staff TKD.

**Tech Stack:** Python 3 / Flask / MariaDB 10.11 / pytest; Vue 3 / Vue Router / Vitest / `qrcode` (sudah ada); tanpa dependency baru.

**Spec:** `docs/superpowers/specs/2026-11-24-rekrutmen-hub-tkd-design.md`

## Global Constraints

- Maksimal **2 percobaan** per kasus; percobaan ke-2 hanya terbuka bila percobaan pertama **< 70**; tidak ada percobaan ke-3 lewat portal.
- Ujian default **20 soal bernilai + 1 soal motivasi**, **25 menit**, lulus **70**; kuota `REGULASI 7 · PERUSAHAAN 4 · PRODUK 6 · HITUNG 3`.
- Skor resmi = **tertinggi** dari attempt otomatis; koreksi `MANUAL` staff menang sampai staff mengedit lagi.
- Kunci jawaban, poin, dan `is_correct` **tidak pernah** masuk response publik.
- NIK selalu dimasker di UI/log/audit; NIK lengkap tidak masuk tabel baru, URL, atau nama Redis key (pakai hash).
- Token cabang memakai `cv_online_branch_forms` yang sudah ada; tidak membuat token baru.
- Role staff rekrutmen: `traineer`, `ga_hr`, `admin`; `finance` hanya FirstWork; `receptionist` hanya Pelamar + Tautan.
- Ubah pengaturan TKD global hanya `admin`; `traineer`/`ga_hr` hanya membaca.
- UI berbahasa Indonesia; halaman publik mobile-first.
- Tanpa dependency baru: CSV memakai `csv` Python, QR memakai `qrcode` yang sudah terpasang.
- Skema idempoten saat startup dan `init.sql` wajib memuat DDL yang sama untuk drift check.
- Versi rilis: bump 7 titik + stamp DB, CHANGELOG, PROGRESS, satu commit rilis.

## Review Focus

1. **NIK benar + tanggal lahir salah** → harus ditolak dengan pesan generik, tanpa skor, attempt, nama, atau cabang di response, dan tanpa sesi TKD.
2. **Attempt ditinggalkan melewati `expires_at`** → difinalisasi lazy saat status/start/resume/hasil diakses, tetap menghabiskan satu kesempatan, dan skornya ikut menjadi kandidat skor terbaik.
3. **Koreksi manual lebih rendah dari attempt terbaik** → pelamar melihat skor koreksi (bukan skor terbaik), dan attempt baru tidak menimpa skor `MANUAL`.
4. **Soal diedit/dinonaktifkan saat attempt berjalan** → snapshot attempt tidak berubah dan skor dihitung dari snapshot, bukan bank soal hidup.
5. **Impor CSV / seed dijalankan ulang** → kode yang sudah ada (terutama yang aktif) dilewati, tidak menimpa editan staff; hanya mode "perbarui draft" yang boleh mengubah `active=0`.

---

## File Structure

**Backend — baru**
- `modules/tkd_schema.py` — DDL 4 tabel TKD, seed baris `tkd_settings`, ALTER 7 kolom skor di `recruitment_cases`.
- `modules/tkd_core.py` — fungsi murni: turunan tanggal dari NIK, parse angka, penilaian, sampling, kesiapan bank, validasi pengaturan/soal, state publik, CSV.
- `modules/tkd_service.py` — orkestrasi DB: token cabang, verifikasi identitas, attempt start/resume/finalize, sinkronisasi skor kasus, koreksi manual.
- `modules/routes_tkd.py` — endpoint publik dan staff TKD.
- `scripts/seed_tkd_bank.py` — seed insert-if-absent dari CSV.
- `docs/seed/tkd_bank_v1.csv` — 30 soal bernilai + 1 soal profil.

**Backend — diubah**
- `app.py` — panggil `ensure_tkd_schema()` setelah `ensure_recruitment_schema()`; daftarkan `register_tkd_routes(app)`; tambah prefix CSRF publik TKD.
- `init.sql` — DDL 4 tabel TKD + 7 kolom skor pada `recruitment_cases`.
- `modules/routes_recruitment.py` — field skor di `/api/recruitment/cases`, endpoint `/api/recruitment/portal-links`, perilaku skor pada bukti manual TKD.

**Frontend — baru**
- `frontend/src/views/RecruitmentHubView.vue` — shell tab `/recruitment`.
- `frontend/src/views/RecruitmentLinksView.vue` — tab Tautan (satu link portal + QR per cabang).
- `frontend/src/views/TkdView.vue` — shell sub-tab Bank Soal / Hasil / Pengaturan.
- `frontend/src/views/TkdBankPanel.vue`
- `frontend/src/views/TkdResultsPanel.vue`
- `frontend/src/views/TkdSettingsPanel.vue`
- `frontend/src/components/RecruitmentTkdPanel.vue` — alur ujian publik (intro, ujian, hasil).

**Frontend — diubah**
- `frontend/src/router/index.js` — route hub + redirect rute lama + guard `/first-work`.
- `frontend/src/layouts/AppLayout.vue` — satu item menu "Rekrutmen".
- `frontend/src/views/RecruitmentPortalView.vue` — kartu TKD aktif + panel ujian.
- `frontend/src/views/RecruitmentCasesView.vue` — kolom skor TKD + prop `embedded`.
- `frontend/src/views/dashboard/ReceptionistView.vue`, `CvOnlineView.vue`, `FirstWorkView.vue` — prop `embedded`.

---

### Task 1: Skema TKD & kolom skor kasus

**Files:**
- Create: `modules/tkd_schema.py`
- Modify: `app.py` (setelah blok `ensure_recruitment_schema`)
- Modify: `init.sql` (tabel `recruitment_cases` + DDL TKD setelah `case_branch_history`)
- Test: `tests/test_tkd_schema.py`

**Interfaces:**
- Produces: `ensure_tkd_schema(conn=None) -> bool` — membuat `tkd_questions`, `tkd_settings`, `tkd_attempts`, `tkd_attempt_items`, menyisipkan `tkd_settings(id=1)` bila belum ada, dan menambah 7 kolom skor ke `recruitment_cases`. Idempoten; `conn` yang diberikan tidak ditutup.
- Produces: konstanta `TKD_TABLES` (4 nama tabel) dan `CASE_SCORE_COLUMNS` (7 pasang nama kolom + DDL).

- [ ] **Step 1: Tulis tes skema yang gagal**

```python
# tests/test_tkd_schema.py
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split())
        m = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', text, re.I)
        if m:
            self.conn.created.append(m.group(1).lower())
        if text.upper().startswith('SELECT COLUMN_NAME'):
            self.conn.queried_columns = True
        if text.upper().startswith('ALTER TABLE RECRUITMENT_CASES'):
            self.conn.alters.append(text)
        if 'INSERT IGNORE INTO TKD_SETTINGS' in text.upper():
            self.conn.seeded_settings = True
    def fetchall(self):
        return [{'COLUMN_NAME': c} for c in self.conn.existing_columns]
    def fetchone(self):
        return None
    def close(self):
        pass

class _FakeConn:
    def __init__(self, existing_columns=()):
        self.created, self.alters = [], []
        self.existing_columns = set(existing_columns)
        self.seeded_settings = False
        self.queried_columns = False
        self.commits = 0
    def cursor(self, dictionary=False):
        return _FakeCursor(self)
    def commit(self):
        self.commits += 1
    def close(self):
        pass

def test_membuat_empat_tabel_dan_seed_settings():
    from modules.tkd_schema import ensure_tkd_schema, TKD_TABLES
    conn = _FakeConn()
    assert ensure_tkd_schema(conn) is True
    assert set(TKD_TABLES) <= set(conn.created)
    assert conn.seeded_settings is True

def test_menambah_tujuh_kolom_skor_bila_belum_ada():
    from modules.tkd_schema import ensure_tkd_schema
    conn = _FakeConn()
    assert ensure_tkd_schema(conn) is True
    assert len(conn.alters) == 7

def test_idempoten_tidak_alter_kolom_yang_sudah_ada():
    from modules.tkd_schema import ensure_tkd_schema, CASE_SCORE_COLUMNS
    conn = _FakeConn(existing_columns=[c for c, _ in CASE_SCORE_COLUMNS])
    assert ensure_tkd_schema(conn) is True
    assert conn.alters == []

def test_init_sql_memuat_tabel_dan_kolom_untuk_drift_check():
    from scripts.check_schema_drift import parse_init_sql
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    parsed = parse_init_sql(sql)
    for table in ('tkd_questions', 'tkd_settings', 'tkd_attempts', 'tkd_attempt_items'):
        assert table in parsed
    assert {'tkd_score', 'tkd_score_source', 'tkd_score_note',
            'tkd_score_updated_by', 'tkd_score_updated_at',
            'tkd_best_attempt_id', 'tkd_passed'} <= set(parsed['recruitment_cases'])

def test_startup_memanggil_setelah_recruitment():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'from modules.tkd_schema import ensure_tkd_schema' in app
    assert app.index('ensure_tkd_schema()') > app.index('ensure_recruitment_schema()')
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_schema.py -q`
Expected: FAIL karena `modules.tkd_schema` belum ada.

- [ ] **Step 3: Implementasi `modules/tkd_schema.py`**

Struktur: `_DDL` (4 CREATE TABLE persis seperti spec §3.1–3.4), `CASE_SCORE_COLUMNS` (7 tuple), `ensure_tkd_schema(conn=None)`.
Alur: koneksi master → jalankan CREATE (catat label yang gagal) → `INSERT IGNORE INTO tkd_settings (id, quota) VALUES (1, %s)` dengan `json.dumps(DEFAULT_QUOTA)` → baca `information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recruitment_cases' AND COLUMN_NAME IN (...)` → jalankan ALTER hanya untuk kolom yang belum ada; error `1060`/`duplicate column` dianggap sukses → `commit()` → `all(results)`.
`conn` yang diberikan tidak ditutup. Cetak `[tkd-schema] <label>: <e>` untuk kegagalan non-fatal.

- [ ] **Step 4: Daftarkan di `app.py` dan `init.sql`**

`app.py`, tepat setelah loop `ensure_recruitment_schema()`:

```python
# TKD online (Rilis C): tabel tkd_* + kolom skor di recruitment_cases.
from modules.tkd_schema import ensure_tkd_schema
for _attempt in range(5):
    if ensure_tkd_schema():
        break
    _time.sleep(3)
```

`init.sql`: tambahkan 7 kolom ke `CREATE TABLE recruitment_cases` (setelah `merged_from`) dan 4 `CREATE TABLE` TKD setelah `case_branch_history`. DDL harus sama persis dengan `modules/tkd_schema.py` (tipe, default, unique key, index).

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_schema.py tests/test_init_sql.py tests/test_recruitment_schema.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/tkd_schema.py app.py init.sql tests/test_tkd_schema.py
git commit -m "feat(tkd): skema bank soal, attempt, dan skor kasus"
```

---

### Task 2: Core identitas, angka, dan penilaian

**Files:**
- Create: `modules/tkd_core.py`
- Test: `tests/test_tkd_core_grading.py`

**Interfaces:**
- Produces: `derive_dob_from_nik(nik, today=None) -> date | None`
- Produces: `parse_numeric(value) -> float | None`
- Produces: `normalize_short_text(value) -> str`
- Produces: `grade_answer(question: dict, answer) -> tuple[bool | None, float]` — `None` untuk soal `PROFILE_TEXT`.
- Produces: `compute_score(items: list[dict], pass_score: float) -> dict` dengan kunci `score`, `total_points`, `awarded`, `correct_count`, `passed`.
- Produces: `as_json(value, default=None)` — menerima `str` JSON, `dict`, `list`, atau `None`.
- Produces: `DEFAULT_QUOTA`, `MAX_ATTEMPTS = 2`, `MODAL_TIERS = ('30k','50k','100k')`, `CATEGORIES`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_core_grading.py
from datetime import date
import pytest
from modules.tkd_core import (derive_dob_from_nik, parse_numeric,
                              normalize_short_text, grade_answer, compute_score)

def test_tanggal_lahir_dari_nik_laki_laki():
    assert derive_dob_from_nik('3573010101990001') == date(1999, 1, 1)

def test_tanggal_lahir_dari_nik_perempuan_dan_pivot_abad():
    assert derive_dob_from_nik('3573014101990001') == date(1999, 1, 1)
    assert derive_dob_from_nik('3573010101270001', today=date(2026, 11, 24)) == date(1927, 1, 1)
    assert derive_dob_from_nik('3573010101260001', today=date(2026, 11, 24)) == date(2026, 1, 1)

@pytest.mark.parametrize('nik', ['', '123', '357301010199000X', '3573013201990001', '3573010113990001'])
def test_tanggal_lahir_tidak_valid_mengembalikan_none(nik):
    assert derive_dob_from_nik(nik) is None

@pytest.mark.parametrize('raw,expected', [
    ('1.866,8', 1866.8), ('$1866,8', 1866.8), ('1866.8', 1866.8),
    (' 1 866,8 ', 1866.8), ('159.501', 159501.0), (60, 60.0),
])
def test_parse_numeric_menerima_format_indonesia(raw, expected):
    assert parse_numeric(raw) == pytest.approx(expected)

@pytest.mark.parametrize('raw', ['', 'abc', '1,2,3', None, float('nan')])
def test_parse_numeric_menolak_sampah(raw):
    assert parse_numeric(raw) is None

def test_normalize_short_text_mengabaikan_huruf_besar_dan_tanda_baca():
    assert normalize_short_text(' 499/BAPPEBTI/SI/X/2004 ') == normalize_short_text('499 bappebti si x 2004')

def test_mcq_dinilai_dari_kunci_snapshot():
    q = {'type': 'MCQ', 'answer': {'option': 'b'}, 'points': 1}
    assert grade_answer(q, {'option': 'b'}) == (True, 1.0)
    assert grade_answer(q, {'option': 'a'}) == (False, 0.0)

def test_numeric_memakai_toleransi():
    q = {'type': 'NUMERIC', 'answer': {'value': 1866.8, 'tolerance': 0.5}, 'points': 1}
    assert grade_answer(q, 1866.4) == (True, 1.0)
    assert grade_answer(q, 1867.5) == (False, 0.0)

def test_short_text_menerima_alias():
    q = {'type': 'SHORT_TEXT', 'answer': {'aliases': ['499/BAPPEBTI/SI/X/2004']}, 'points': 1}
    assert grade_answer(q, {'text': '499 Bappebti SI X 2004'}) == (True, 1.0)

def test_profile_tidak_dinilai():
    q = {'type': 'PROFILE_TEXT', 'answer': None, 'points': 0}
    assert grade_answer(q, {'text': 'apa saja'}) == (None, 0.0)

def test_skor_14_dari_20_lulus_70():
    items = [{'is_correct': True, 'points_awarded': 1, 'points': 1}] * 14
    items += [{'is_correct': False, 'points_awarded': 0, 'points': 1}] * 6
    assert compute_score(items, 70) == {
        'score': 70.0, 'total_points': 20.0, 'awarded': 14.0,
        'correct_count': 14, 'passed': True}
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_core_grading.py -q`
Expected: FAIL karena `modules.tkd_core` belum ada.

- [ ] **Step 3: Implementasi fungsi murni**

Aturan:
- `derive_dob_from_nik`: hanya 16 digit; ambil `nik[6:12]` = `DDMMYY`; `DD > 40` → perempuan (`DD -= 40`); pivot `YY > today.year % 100` → `1900+YY`, selain itu `2000+YY`; `date(...)`; `ValueError` → `None`.
- `parse_numeric`: `bool` ditolak; angka langsung; string dibersihkan dari `$`, `US$`, `Rp`, spasi; bila ada `,` dan `.` → buang `.`, ganti `,` jadi `.`; bila hanya `,` → ganti jadi `.`; bila hanya `.`: pola `^\d{1,3}(\.\d{3})+$` dianggap pemisah ribuan (buang titik, mis. `159.501` → `159501`), selain itu desimal (mis. `1866.8`); `float`; tolak `NaN`/`inf`.
- `normalize_short_text`: `str(value or '').upper()` lalu buang semua non-`A-Z0-9`.
- `grade_answer`: baca `question['type']`; `MCQ` bandingkan `answer['option']`; `NUMERIC` pakai `parse_numeric` pada `answer['value']` atau angka langsung; `SHORT_TEXT` bandingkan alias ternormalisasi; `PROFILE_TEXT` → `(None, 0.0)`.
- `compute_score`: hanya item dengan `points` > 0; bila `total_points == 0` → `score = 0.0`, `passed = False`; selain itu `score = round(awarded/total*100, 2)`; `passed = score >= pass_score`.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_core_grading.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/tkd_core.py tests/test_tkd_core_grading.py
git commit -m "feat(tkd): identitas, parsing angka, dan penilaian jawaban"
```

---

### Task 3: Core sampling, kesiapan bank, validasi pengaturan, dan state publik

**Files:**
- Modify: `modules/tkd_core.py`
- Test: `tests/test_tkd_core_sampling.py`

**Interfaces:**
- Consumes: `DEFAULT_QUOTA`, `MAX_ATTEMPTS`, `MODAL_TIERS`, `as_json` dari Task 2.
- Produces: `select_questions(questions: list[dict], settings: dict, modal_tier: str, rng=None) -> list[dict] | None` — 20 soal bernilai + 1 `PROFILE_TEXT` terakhir; `None` bila bank tidak cukup.
- Produces: `readiness(questions: list[dict], settings: dict) -> dict` dengan kunci `ready`, `active_valued`, `quota_ok`, `tier_ok`, `reasons`.
- Produces: `validate_settings(payload: dict) -> tuple[dict | None, list[str]]`.
- Produces: `public_state(case: dict, attempts: list[dict], steps: list[dict], settings: dict) -> dict` dengan kunci `state`, `official_score`, `score_source`, `attempts_used`, `max_attempts`, `active_attempt`, `can_start`, `pass_score`, `question_count`, `duration_minutes`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_core_sampling.py
import random
from modules.tkd_core import (DEFAULT_QUOTA, select_questions, readiness,
                              validate_settings, public_state)

def _q(code, category, tier=None, active=1, type_='MCQ', points=1):
    return {'id': hash(code) % 10000, 'code': code, 'category': category,
            'type': type_, 'prompt': code, 'options': [{'id': 'a', 'text': 'A'},
            {'id': 'b', 'text': 'B'}], 'answer': {'option': 'a'},
            'points': points, 'modal_tier': tier, 'active': active,
            'sort_order': 0}

def _bank():
    rows = []
    for i in range(8): rows.append(_q(f'REG-{i}', 'REGULASI'))
    for i in range(5): rows.append(_q(f'PER-{i}', 'PERUSAHAAN'))
    for i in range(7): rows.append(_q(f'PRO-{i}', 'PRODUK'))
    for i in range(4): rows.append(_q(f'HIT-G-{i}', 'HITUNG'))
    for tier in ('30k', '50k', '100k'):
        for i in range(2): rows.append(_q(f'HIT-{tier}-{i}', 'HITUNG', tier))
    rows.append(_q('PROF-1', 'PROFIL', type_='PROFILE_TEXT', points=0))
    return rows

SETTINGS = {'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
            'max_attempts': 2, 'quota': dict(DEFAULT_QUOTA), 'active': 1}

def test_sampling_memenuhi_kuota_dan_menambah_satu_profil():
    picked = select_questions(_bank(), SETTINGS, '30k', rng=random.Random(1))
    assert len(picked) == 21
    valued = [q for q in picked if q['type'] != 'PROFILE_TEXT']
    assert len(valued) == 20
    assert {c: sum(1 for q in valued if q['category'] == c) for c in DEFAULT_QUOTA} == DEFAULT_QUOTA
    assert picked[-1]['category'] == 'PROFIL'

def test_hanya_tier_terpilih_yang_muncul():
    picked = select_questions(_bank(), SETTINGS, '100k', rng=random.Random(2))
    tiers = {q['modal_tier'] for q in picked if q['category'] == 'HITUNG'}
    assert '100k' in tiers
    assert not ({'30k', '50k'} & tiers)

def test_bank_kurang_mengembalikan_none():
    rows = [q for q in _bank() if not q['code'].startswith('REG')]
    assert select_questions(rows, SETTINGS, '30k') is None

def test_kesiapan_butuh_kuota_tiap_kategori_dan_tier():
    ok = readiness(_bank(), SETTINGS)
    assert ok['ready'] is True
    assert all(ok['tier_ok'].values())

    short = [q for q in _bank() if q['code'] != 'PRO-0']
    bad = readiness(short, SETTINGS)
    assert bad['ready'] is False
    assert 'PRODUK' in ' '.join(bad['reasons'])

def test_validate_settings_menolak_kuota_tidak_sama_dan_attempt_bukan_2():
    payload = dict(SETTINGS, quota={'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 2})
    data, errors = validate_settings(payload)
    assert data is None and any('kuota' in e.lower() for e in errors)

    data, errors = validate_settings(dict(SETTINGS, max_attempts=3))
    assert data is None and any('2' in e for e in errors)

def test_state_publik_lulus_habis_dan_dikecualikan():
    case = {'tkd_score': 85, 'tkd_score_source': 'AUTO', 'tkd_passed': 1}
    state = public_state(case, [], [], SETTINGS)
    assert state['state'] == 'LULUS' and state['can_start'] is False

    case = {'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0}
    attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 60},
                {'id': 'TKD-2', 'status': 'SELESAI', 'score': 55}]
    assert public_state(case, attempts, [], SETTINGS)['state'] == 'HABIS'

    steps = [{'step_type': 'TKD', 'status': 'DIKECUALIKAN'}]
    assert public_state(case, [], steps, SETTINGS)['state'] == 'DIKECUALIKAN'

def test_state_publik_belum_berlangsung_dan_bisa_coba():
    empty = {'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
    assert public_state(empty, [], [], SETTINGS)['state'] == 'BELUM'
    active = [{'id': 'TKD-1', 'status': 'BERLANGSUNG', 'score': None,
               'expires_at': '2099-01-01 00:00:00'}]
    st = public_state(empty, active, [], SETTINGS)
    assert st['state'] == 'BERLANGSUNG' and st['active_attempt']['id'] == 'TKD-1'
    done = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 60}]
    assert public_state({'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0},
                        done, [], SETTINGS)['state'] == 'BISA_COBA'

def test_state_skor_belum_tercatat_untuk_kasus_lama():
    case = {'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
    steps = [{'step_type': 'TKD', 'status': 'SELESAI'}]
    assert public_state(case, [], steps, SETTINGS)['state'] == 'SKOR_BELUM_TERCATAT'
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_core_sampling.py -q`
Expected: FAIL karena fungsi belum ada.

- [ ] **Step 3: Implementasi**

`select_questions`:
1. `valued = [q for q in questions if q['active'] and q['category'] != 'PROFIL' and q['type'] != 'PROFILE_TEXT']`.
2. Untuk setiap kategori di `settings['quota']`: pool = kategori tersebut; khusus `HITUNG`, pool = `modal_tier in (None, '', modal_tier)`. Ambil `rng.sample(pool, min(quota, len(pool)))`; catat kekurangan.
3. Bila total < `question_count`, isi dari sisa pool kategori lain (tetap mengecualikan HITUNG tier lain). Bila masih kurang → `None`.
4. Ambil satu `PROFILE_TEXT` aktif pertama; bila tidak ada → `None`.
5. Acak urutan soal bernilai dengan `rng.shuffle`, lalu tempel profil di akhir.

`readiness`: hitung soal bernilai aktif; periksa `>= question_count`, setiap kategori memenuhi kuota, `HITUNG` per tier `umum + tier >= quota HITUNG`, dan ada `PROFILE_TEXT`. `reasons` berisi kalimat Indonesia yang menyebut kategori/tier kurang.

`validate_settings`: normalisasi `question_count` 1–100, `duration_minutes` 5–180, `pass_score` 0–100, `quota` tepat 4 kategori bernilai dengan jumlah = `question_count`, `shuffle_options`/`active` boolean, `max_attempts` **wajib 2**. Kembalikan `(data, [])` atau `(None, errors)`.

`public_state` urutan keputusan:
1. `settings['active']` false atau `settings.get('bank_ready') is False` → `SEGERA`.
2. ada langkah TKD `DIKECUALIKAN` → `DIKECUALIKAN`.
3. ada attempt `BERLANGSUNG` → `BERLANGSUNG` (`active_attempt` = id, expires_at, remaining_seconds).
4. `tkd_score` NULL tetapi ada langkah TKD `SELESAI` → `SKOR_BELUM_TERCATAT`.
5. `tkd_passed == 1` atau (`tkd_score` bukan NULL dan `tkd_score >= pass_score`) → `LULUS`.
6. `attempts_used >= max_attempts` → `HABIS`.
7. `attempts_used >= 1` → `BISA_COBA`.
8. selain itu → `BELUM`.

`attempts_used` menghitung attempt `BERLANGSUNG`, `SELESAI`, dan `KEDALUWARSA`.
`can_start = state in ('BELUM', 'BISA_COBA')`; `official_score`/`score_source` dari kasus; `pass_score`, `question_count`, `duration_minutes`, `max_attempts` dari settings.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_core_sampling.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/tkd_core.py tests/test_tkd_core_sampling.py
git commit -m "feat(tkd): sampling stratifikasi, kesiapan bank, dan state publik"
```

---

### Task 4: Core validasi soal dan CSV

**Files:**
- Modify: `modules/tkd_core.py`
- Test: `tests/test_tkd_core_csv.py`

**Interfaces:**
- Produces: `validate_question(data: dict) -> list[str]`.
- Produces: `normalize_question(data: dict) -> dict` — bentuk siap INSERT (`options`/`answer` JSON string).
- Produces: `csv_to_question_rows(text: str) -> tuple[list[dict], list[str]]` — baris tervalidasi dengan `active=0`; error menyebut nomor baris.
- Produces: `import_rows(existing: dict[str, dict], rows: list[dict], update_drafts: bool) -> dict` dengan kunci `insert`, `update`, `skip`, `errors`.
- Produces: `question_row_to_csv(row: dict) -> list[str]` dan `CSV_COLUMNS`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_core_csv.py
from pathlib import Path
import pytest
from modules.tkd_core import (CSV_COLUMNS, validate_question, csv_to_question_rows,
                              import_rows, question_row_to_csv)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'docs' / 'seed' / 'tkd_bank_v1.csv'

def test_csv_seed_berisi_31_soal_dan_valid():
    rows, errors = csv_to_question_rows(SEED.read_text(encoding='utf-8'))
    assert errors == []
    assert len(rows) == 31
    assert sum(1 for r in rows if r['category'] == 'REGULASI') == 8
    assert sum(1 for r in rows if r['category'] == 'PERUSAHAAN') == 5
    assert sum(1 for r in rows if r['category'] == 'PRODUK') == 7
    assert sum(1 for r in rows if r['category'] == 'HITUNG') == 10
    assert sum(1 for r in rows if r['category'] == 'PROFIL') == 1
    assert all(r['active'] == 0 for r in rows)

def test_kunci_hitung_penting_terbaca():
    rows, _ = csv_to_question_rows(SEED.read_text(encoding='utf-8'))
    by_code = {r['code']: r for r in rows}
    assert by_code['HIT-01']['answer']['value'] == pytest.approx(1866.8)
    assert by_code['HIT-30-01']['answer']['value'] == pytest.approx(56400.3)
    assert by_code['HIT-50-01']['answer']['value'] == pytest.approx(97000.5)
    assert by_code['HIT-100-01']['answer']['value'] == pytest.approx(159501.0)

def test_validasi_soal_mcq_dan_profile():
    mcq = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
           'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
           'answer': {'option': 'a'}, 'points': 1, 'active': 0}
    assert validate_question(mcq) == []
    assert validate_question(dict(mcq, answer={'option': 'z'}))
    profile = {'code': 'P-1', 'category': 'PROFIL', 'type': 'PROFILE_TEXT',
               'prompt': 'Motivasi?', 'answer': None, 'points': 0, 'active': 0}
    assert validate_question(profile) == []

def test_import_melewati_kode_aktif_dan_hanya_update_draft():
    existing = {'A': {'id': 1, 'active': 1}, 'B': {'id': 2, 'active': 0}}
    rows = [{'code': 'A'}, {'code': 'B'}, {'code': 'C'}]
    plan = import_rows(existing, rows, update_drafts=False)
    assert plan['insert'] == ['C'] and plan['skip'] == ['A', 'B'] and plan['update'] == []

    plan = import_rows(existing, rows, update_drafts=True)
    assert plan['insert'] == ['C'] and plan['skip'] == ['A'] and plan['update'] == ['B']

def test_round_trip_baris_csv():
    row = {'code': 'REG-01', 'category': 'REGULASI', 'type': 'MCQ',
           'prompt': 'Pertanyaan, dengan koma', 'options': [{'id': 'a', 'text': 'A'}],
           'answer': {'option': 'a'}, 'points': 1, 'modal_tier': None,
           'active': 1, 'sort_order': 1}
    values = question_row_to_csv(row)
    assert len(values) == len(CSV_COLUMNS)
    assert values[CSV_COLUMNS.index('prompt')] == 'Pertanyaan, dengan koma'
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_core_csv.py -q`
Expected: FAIL karena fungsi/seed belum ada.

- [ ] **Step 3: Implementasi validasi & CSV**

`CSV_COLUMNS = ('code','category','type','prompt','option_a','option_b','option_c','option_d','option_e','correct','tolerance','points','modal_tier','active')`.

Aturan `validate_question`:
- `code` wajib `^[A-Z0-9][A-Z0-9_-]{2,39}$`.
- `category` ∈ `CATEGORIES`; `type` ∈ `MCQ/NUMERIC/SHORT_TEXT/PROFILE_TEXT`.
- `prompt` 1–2000 karakter.
- `MCQ`: 2–6 opsi, id unik `a`–`f`, teks tidak kosong; `answer['option']` harus ada di opsi; `points > 0`.
- `NUMERIC`: `answer['value']` angka; `tolerance >= 0` (default 0.5); `points > 0`.
- `SHORT_TEXT`: `answer['aliases']` 1–10 string tidak kosong; `points > 0`.
- `PROFILE_TEXT`: hanya kategori `PROFIL`, `answer is None`, `points == 0`.
- `modal_tier` `None`/`''` atau ∈ `MODAL_TIERS`; hanya boleh untuk `HITUNG`.
- `active` 0/1.

`csv_to_question_rows`: `csv.DictReader(io.StringIO(text.lstrip('\ufeff')))`; wajib semua `CSV_COLUMNS`; maksimal 500 baris; bangun `options` dari `option_a..e` (abaikan kosong), `answer` sesuai tipe, `active=0`, `sort_order` = urutan baris. Kumpulkan error `'baris N: ...'`; baris invalid tidak masuk hasil.

`import_rows`: bandingkan `code`; `existing[code]['active'] == 1` → `skip`; `active == 0` dan `update_drafts` → `update`; `active == 0` tanpa flag → `skip`; tidak ada → `insert`. `errors` kosong (validasi sudah di lapisan CSV).

`question_row_to_csv`: kebalikan pemetaan; `options` → `option_a..e`; `answer` → `correct` (MCQ huruf, NUMERIC angka, SHORT_TEXT alias `|`); `active` tetap diekspor. Semua akses field memakai `row.get(...)` agar baris parsial dari SELECT ringkas tidak melempar `KeyError`.

- [ ] **Step 4: Tulis seed CSV**

Buat `docs/seed/tkd_bank_v1.csv` dengan header `CSV_COLUMNS` dan 31 baris. Isi wajib (kunci tidak boleh diubah):

| Kode | Kategori | Tipe | Inti | Kunci |
|---|---|---|---|---|
| REG-01 | REGULASI | MCQ | Pengawas PBK | Bappebti |
| REG-02 | REGULASI | MCQ | Dasar hukum | UU 32/1997 jo. UU 10/2011 |
| REG-03 | REGULASI | MCQ | Fungsi KBI | kliring/penjaminan penyelesaian |
| REG-04 | REGULASI | MCQ | LPS vs KBI | LPS simpanan bank; KBI kliring PBK |
| REG-05 | REGULASI | SHORT_TEXT | Izin pialang | `499/BAPPEBTI/SI/X/2004` |
| REG-06 | REGULASI | SHORT_TEXT | Izin SPA | `1157/BAPPEBTI/SP/3/2007` |
| REG-07 | REGULASI | MCQ | Anggota bursa | `SPAB-071/BBJ/05/04` |
| REG-08 | REGULASI | MCQ | Dana nasabah | rekening terpisah (segregated) |
| PER-01 | PERUSAHAAN | MCQ | Profil BPF | pialang berizin Bappebti, anggota BBJ & KBI |
| PER-02 | PERUSAHAAN | MCQ | Keuntungan BBJ | teratur/transparan, price discovery, hedging, kliring |
| PER-03 | PERUSAHAAN | MCQ | Keamanan BPF | izin resmi, dana terpisah, anggota KBI |
| PER-04 | PERUSAHAAN | MCQ | Peran KBI bagi nasabah | jaminan penyelesaian via kliring |
| PER-05 | PERUSAHAAN | MCQ | Arti anggota bursa | meneruskan order ke bursa |
| PRO-01 | PRODUK | MCQ | Produk multilateral BBJ | GOL, GOL250, OLE |
| PRO-02 | PRODUK | MCQ | Produk SPA | XUL, XAG, BCO, HKK, JPK, forex |
| PRO-03 | PRODUK | MCQ | Contract size emas | 100 troy ounce |
| PRO-04 | PRODUK | MCQ | Rollover emas | US$5/lot/malam/sisi + VAT |
| PRO-05 | PRODUK | MCQ | Multilateral vs SPA | bursa vs luar bursa |
| PRO-06 | PRODUK | MCQ | Kuotasi emas | USD/troy ounce |
| PRO-07 | PRODUK | MCQ | Bukan produk multilateral | forex |
| HIT-01 | HITUNG | NUMERIC | Laba bersih Pak Budi | 1866.8 |
| HIT-02 | HITUNG | NUMERIC | Biaya Pak Budi | 133.2 |
| HIT-03 | HITUNG | NUMERIC | Short sell 2 lot | 3933.4 |
| HIT-04 | HITUNG | NUMERIC | Rollover 3 lot 2 malam | 60 |
| HIT-30-01 | HITUNG | NUMERIC | Ibu Dian $30k bersih | 56400.3 |
| HIT-30-02 | HITUNG | NUMERIC | Ibu Dian $30k biaya | 299.7 |
| HIT-50-01 | HITUNG | NUMERIC | Ibu Dian $50k bersih | 97000.5 |
| HIT-50-02 | HITUNG | NUMERIC | Ibu Dian $50k biaya | 499.5 |
| HIT-100-01 | HITUNG | NUMERIC | Ibu Dian $100k bersih | 159501 |
| HIT-100-02 | HITUNG | NUMERIC | Ibu Dian $100k biaya | 999 |
| PROF-01 | PROFIL | PROFILE_TEXT | Target karier di BPF | (tidak dinilai) |

Setiap soal HITUNG menyebut eksplisit contract size 100 troy ounce, facility fee US$15/lot/sisi + VAT 11% (total US$33,3/lot), dan asumsi lot. Soal tier menyebut modal, margin US$1.000/lot, dan 30% modal sebagai margin (9/15/30 lot). Toleransi 0,5 untuk nilai kecil dan 1 untuk nilai besar. Khusus `HIT-04` (rollover 3 lot × 2 malam × 2 sisi × US$5 = US$60) prompt menyebut "sebelum VAT" agar kunci 60 konsisten; soal lain memakai total setelah VAT.

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_core_csv.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/tkd_core.py docs/seed/tkd_bank_v1.csv tests/test_tkd_core_csv.py
git commit -m "feat(tkd): validasi soal, CSV, dan bank soal awal 31 baris"
```

---

### Task 5: Service DB — token, identitas, pengaturan, dan pembacaan attempt

**Files:**
- Create: `modules/tkd_service.py`
- Test: `tests/test_tkd_service_read.py`

**Interfaces:**
- Consumes: `derive_dob_from_nik`, `as_json`, `public_state` dari `tkd_core`.
- Produces: `resolve_branch_token(cursor, token: str) -> str` — `branch_code` untuk token aktif, `''` bila tidak sah.
- Produces: `load_settings(cursor) -> dict` — baris `tkd_settings` dengan `quota` sudah di-parse; default dari `tkd_core` bila baris hilang.
- Produces: `fetch_case_by_nik(cursor, nik: str, for_update: bool = False) -> dict | None` — menambahkan `FOR UPDATE` bila `for_update`.
- Produces: `verify_identity(cursor, nik: str, dob: str) -> dict | None` — cocokkan `tanggal_lahir` atau turunan NIK; `None` bila gagal.
- Produces: `fetch_attempts(cursor, case_id: str) -> list[dict]`, `fetch_tkd_steps(cursor, case_id: str) -> list[dict]`, `fetch_active_questions(cursor) -> list[dict]`, `fetch_attempt(cursor, attempt_id: str, for_update=False) -> dict | None`, `fetch_attempt_items(cursor, attempt_id: str) -> list[dict]`.
- Produces: `_as_iso(value)` dan `_as_float(value)` helper modul.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_service_read.py
import json
from datetime import date, datetime
import pytest
from modules import tkd_service as svc

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if 'FROM CV_ONLINE_BRANCH_FORMS' in upper:
            self._rows = [r for r in self.conn.tokens
                          if r['form_token'] == params[0] and r['active']]
        elif 'FROM RECRUITMENT_CASES' in upper and 'WHERE NIK=%S' in upper:
            self._rows = [r for r in self.conn.cases if r['nik'] == params[0]]
        elif 'FROM TKD_SETTINGS' in upper:
            self._rows = [self.conn.settings] if self.conn.settings else []
        elif 'FROM TKD_ATTEMPTS' in upper:
            self._rows = list(self.conn.attempts)
        elif 'FROM RECRUITMENT_STEPS' in upper:
            self._rows = list(self.conn.steps)
        elif 'FROM TKD_QUESTIONS' in upper:
            self._rows = list(self.conn.questions)
        elif 'FROM TKD_ATTEMPT_ITEMS' in upper:
            self._rows = list(self.conn.items)
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []
        self.tokens = [{'form_token': 'tok-sby', 'branch_code': 'SBY', 'active': 1}]
        self.cases = [
            {'case_id': 'RC-1', 'nik': '3573010101990001', 'nama': 'Andi',
             'tanggal_lahir': date(1999, 1, 1), 'first_branch': 'SBY',
             'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None},
            {'case_id': 'RC-2', 'nik': '3573014101990002', 'nama': 'Dian',
             'tanggal_lahir': None, 'first_branch': 'MLG',
             'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None},
        ]
        self.settings = {'id': 1, 'question_count': 20, 'duration_minutes': 25,
                         'pass_score': 70, 'max_attempts': 2, 'active': 0,
                         'quota': json.dumps({'REGULASI': 7, 'PERUSAHAAN': 4,
                                              'PRODUK': 6, 'HITUNG': 3})}
        self.attempts, self.steps, self.questions, self.items = [], [], [], []
    def cursor(self, dictionary=False): return _Cursor(self)

def test_token_aktif_dan_tidak_aktif():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.resolve_branch_token(cur, 'tok-sby') == 'SBY'
    assert svc.resolve_branch_token(cur, 'tok-salah') == ''
    conn.tokens[0]['active'] = 0
    assert svc.resolve_branch_token(cur, 'tok-sby') == ''

def test_load_settings_parse_kuota_dan_default():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    s = svc.load_settings(cur)
    assert s['quota'] == {'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 3}
    conn.settings = None
    s = svc.load_settings(cur)
    assert s['question_count'] == 20 and s['pass_score'] == 70

def test_identitas_tanggal_eksplisit_harus_sama():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.verify_identity(cur, '3573010101990001', '1999-01-01')['case_id'] == 'RC-1'
    assert svc.verify_identity(cur, '3573010101990001', '2000-01-01') is None

def test_identitas_null_memakai_turunan_nik():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    # NIK perempuan: 41 -> 01, YY 99 -> 1999
    assert svc.verify_identity(cur, '3573014101990002', '1999-01-01')['case_id'] == 'RC-2'
    assert svc.verify_identity(cur, '3573014101990002', '1999-01-02') is None

def test_identitas_nik_tidak_dikenal_atau_nik_invalid():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.verify_identity(cur, '3573010101999999', '1999-01-01') is None
    assert svc.verify_identity(cur, '123', '1999-01-01') is None
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_service_read.py -q`
Expected: FAIL karena modul belum ada.

- [ ] **Step 3: Implementasi pembacaan**

SQL yang dipakai:
- Token: `SELECT branch_code FROM cv_online_branch_forms WHERE form_token=%s AND active=1 LIMIT 1`.
- Kasus: `SELECT case_id, nik, nama, tanggal_lahir, first_branch, tkd_score, tkd_score_source, tkd_score_note, tkd_passed FROM recruitment_cases WHERE nik=%s LIMIT 1`.
- Pengaturan: `SELECT * FROM tkd_settings WHERE id=1`.
- Attempt: `SELECT * FROM tkd_attempts WHERE case_id=%s ORDER BY attempt_no`; `fetch_attempt` memakai `WHERE id=%s` dan menambahkan `FOR UPDATE` bila diminta.
- Langkah: `SELECT id, step_type, status, branch_code, evidence_type, evidence_id, completed_at FROM recruitment_steps WHERE case_id=%s AND step_type='TKD'`.
- Soal aktif: `SELECT * FROM tkd_questions WHERE active=1 ORDER BY category, sort_order, id`.
- Item: `SELECT * FROM tkd_attempt_items WHERE attempt_id=%s ORDER BY position`.

`verify_identity`: normalisasi NIK dengan `normalize_nik`; bila bukan 16 digit → `None`. Ambil kasus; bila tidak ada → `None`. Bila `tanggal_lahir` ada, bandingkan `_as_iso` dengan `dob`; bila NULL, bandingkan `derive_dob_from_nik(nik)` dengan `date.fromisoformat(dob)` (tanggal invalid → `None`). Kembalikan dict kasus dengan `_as_float` untuk skor dan `_as_iso` untuk tanggal.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_service_read.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/tkd_service.py tests/test_tkd_service_read.py
git commit -m "feat(tkd): token cabang, verifikasi identitas, dan pembacaan attempt"
```

---

### Task 6: Service DB — mulai, finalisasi lazy, dan sinkronisasi skor kasus

**Files:**
- Modify: `modules/tkd_service.py`
- Test: `tests/test_tkd_service_attempts.py`

**Interfaces:**
- Consumes: `select_questions`, `compute_score`, `grade_answer`, `MAX_ATTEMPTS` dari `tkd_core`; helper Task 5.
- Produces: `create_attempt(cursor, case, branch_code, modal_tier, settings, questions, now=None, rng=None) -> dict` — `{'attempt': dict, 'items': list[dict]}`; `ValueError('Bank soal belum siap')` bila sampling gagal.
- Produces: `finalize_attempt(cursor, attempt, status='KEDALUWARSA', now=None) -> dict` — menilai item, update attempt, sinkron skor kasus; idempoten untuk attempt yang sudah selesai.
- Produces: `finalize_expired(cursor, case_id, now=None) -> list[dict]`.
- Produces: `sync_case_score(cursor, case_id, pass_score, attempt_branch='') -> dict` — `{'score','source','passed','best_attempt_id'}`.
- Produces: `attempt_result(cursor, attempt, settings) -> dict` — payload hasil publik.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_service_attempts.py
import json
from datetime import datetime, timedelta
import pytest
from modules import tkd_service as svc
from modules.tkd_core import DEFAULT_QUOTA

class _Cursor:
    def __init__(self, conn):
        self.conn = conn; self._rows = []; self.lastrowid = 0
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if upper.startswith('INSERT INTO TKD_ATTEMPTS'):
            self.conn.inserted_attempt = params
        elif upper.startswith('INSERT INTO TKD_ATTEMPT_ITEMS'):
            self.conn.items.append({'attempt_id': params[0], 'question_id': params[1],
                                    'position': params[2], 'snapshot': params[3],
                                    'answer': None, 'is_correct': None,
                                    'points_awarded': None})
        elif 'FROM TKD_ATTEMPT_ITEMS' in upper:
            self._rows = list(self.conn.items)
        elif 'FROM TKD_ATTEMPTS' in upper and 'CASE_ID=%S' in upper:
            self._rows = list(self.conn.attempts)
        elif 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [self.conn.case]
        elif 'FROM TKD_SETTINGS' in upper:
            self._rows = [self.conn.settings]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []; self.inserted_attempt = None
        self.case = {'case_id': 'RC-1', 'first_branch': 'SBY', 'tkd_score': None,
                     'tkd_score_source': None, 'tkd_passed': None,
                     'tkd_score_note': None, 'tkd_best_attempt_id': None}
        self.settings = {'question_count': 20, 'duration_minutes': 25,
                         'pass_score': 70, 'max_attempts': 2, 'active': 1,
                         'shuffle_options': 0,
                         'quota': dict(DEFAULT_QUOTA)}
        self.attempts, self.items = [], []
    def cursor(self, dictionary=False): return _Cursor(self)

def _questions():
    rows = []
    for cat, n in (('REGULASI', 8), ('PERUSAHAAN', 5), ('PRODUK', 7)):
        for i in range(n):
            rows.append({'id': len(rows) + 1, 'code': f'{cat}-{i}', 'category': cat,
                         'type': 'MCQ', 'prompt': f'{cat} {i}',
                         'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
                         'answer': {'option': 'a'}, 'points': 1,
                         'modal_tier': None, 'active': 1, 'sort_order': i})
    for i in range(4):
        rows.append({'id': len(rows) + 1, 'code': f'HIT-G-{i}', 'category': 'HITUNG',
                     'type': 'NUMERIC', 'prompt': 'H', 'options': [],
                     'answer': {'value': 10, 'tolerance': 0.5}, 'points': 1,
                     'modal_tier': None, 'active': 1, 'sort_order': i})
    for tier in ('30k', '50k', '100k'):
        for i in range(2):
            rows.append({'id': len(rows) + 1, 'code': f'HIT-{tier}-{i}',
                         'category': 'HITUNG', 'type': 'NUMERIC', 'prompt': 'H',
                         'options': [], 'answer': {'value': 10, 'tolerance': 0.5},
                         'points': 1, 'modal_tier': tier, 'active': 1, 'sort_order': i})
    rows.append({'id': len(rows) + 1, 'code': 'PROF-1', 'category': 'PROFIL',
                 'type': 'PROFILE_TEXT', 'prompt': 'Motivasi?', 'options': [],
                 'answer': None, 'points': 0, 'modal_tier': None,
                 'active': 1, 'sort_order': 0})
    return rows

def test_create_attempt_membuat_21_item_dan_snapshot_berkunci():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings,
                             _questions(), now=datetime(2026, 11, 24, 10, 0))
    assert out['attempt']['attempt_no'] == 1
    assert out['attempt']['expires_at'] == datetime(2026, 11, 24, 10, 25)
    assert len(out['items']) == 21
    mcq = [i for i in out['items']
           if json.loads(i['snapshot'])['type'] == 'MCQ']
    assert json.loads(mcq[0]['snapshot'])['answer'] == {'option': 'a'}

def test_finalize_menilai_dan_menyinkronkan_skor_kasus():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings, _questions())
    for item in out['items'][:14]:
        snap = json.loads(item['snapshot'])
        if snap['type'] == 'MCQ':
            item['answer'] = json.dumps({'option': snap['answer']['option']})
        else:
            item['answer'] = json.dumps({'value': snap['answer']['value']})
    attempt = {'id': out['attempt']['id'], 'case_id': 'RC-1', 'status': 'BERLANGSUNG',
               'pass_score_snapshot': 70, 'branch_code': 'SBY',
               'started_at': datetime(2026, 11, 24, 10, 0),
               'expires_at': datetime(2026, 11, 24, 10, 25), 'submitted_at': None,
               'score': None, 'passed': None, 'attempt_no': 1}
    conn.attempts = [attempt]
    result = svc.finalize_attempt(cur, attempt, 'SELESAI')
    assert result['score'] == 70.0 and result['passed'] is True

def test_edit_bank_setelah_attempt_tidak_mengubah_snapshot():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    questions = _questions()
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings, questions)
    idx = next(i for i, item in enumerate(out['items'])
               if json.loads(item['snapshot'])['type'] == 'MCQ')
    snapshot_before = out['items'][idx]['snapshot']
    # Edit bank soal setelah attempt dibuat: snapshot attempt harus beku.
    questions[0]['prompt'] = 'DIUBAH'
    questions[0]['answer'] = {'option': 'b'}
    assert out['items'][idx]['snapshot'] == snapshot_before
    assert json.loads(out['items'][idx]['snapshot'])['answer'] == {'option': 'a'}

def test_attempt_kedaluwarsa_tetap_menghabiskan_kesempatan():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    old = {'id': 'TKD-old', 'case_id': 'RC-1', 'status': 'BERLANGSUNG',
           'expires_at': datetime(2026, 11, 24, 9, 0), 'pass_score_snapshot': 70,
           'branch_code': 'SBY', 'attempt_no': 1, 'score': None, 'passed': None}
    conn.attempts = [old]
    done = svc.finalize_expired(cur, 'RC-1', now=datetime(2026, 11, 24, 10, 0))
    assert done and done[0]['status'] == 'KEDALUWARSA'

def test_sync_tidak_menimpa_manual():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.case.update(tkd_score=75, tkd_score_source='MANUAL', tkd_passed=1)
    conn.attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 90,
                      'passed': 1, 'submitted_at': datetime(2026, 11, 24, 10, 0)}]
    out = svc.sync_case_score(cur, 'RC-1', 70)
    assert out['score'] == 75 and out['source'] == 'MANUAL'
    assert not any(s[0].startswith('UPDATE RECRUITMENT_CASES') for s in conn.statements)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_service_attempts.py -q`
Expected: FAIL karena fungsi belum ada.

- [ ] **Step 3: Implementasi**

`create_attempt`:
1. `selected = select_questions(questions, settings, modal_tier, rng)`; `None` → `ValueError`.
2. Hitung `attempt_no` dari `MAX(attempt_no)` attempt kasus + 1.
3. `id = 'TKD-' + uuid.uuid4().hex[:16]`; `expires_at = now + duration_minutes`.
4. `settings_snapshot = json.dumps({question_count, duration_minutes, quota, max_attempts, shuffle_options})`.
5. INSERT `tkd_attempts` dengan kolom lengkap: `id`, `case_id`, `attempt_no`, `branch_code`, `modal_tier`, `status='BERLANGSUNG'`, `settings_snapshot`, `pass_score_snapshot=settings['pass_score']`, `started_at=now`, `expires_at`, `total_points=0`, `correct_count=0`.
6. Untuk setiap soal: bila `shuffle_options` dan MCQ, acak urutan `options` dengan `rng`; snapshot = `{code,prompt,type,category,options,answer,points,tolerance,modal_tier}`; INSERT item dengan `position` 1..N.
7. Return attempt dict + items.

`finalize_attempt`:
- Bila `attempt['status']` sudah `SELESAI`/`KEDALUWARSA`, kembalikan attempt apa adanya.
- Ambil item; untuk tiap item `grade_answer(as_json(snapshot), as_json(answer))`; simpan hasil ke dict item (`is_correct`, `points_awarded`) lalu UPDATE `is_correct`, `points_awarded`.
- `compute_score(items, attempt['pass_score_snapshot'])`.
- UPDATE attempt: `status`, `submitted_at = now`, `score`, `total_points`, `correct_count`, `passed`.
- `sync_case_score(cursor, case_id, pass_score_snapshot, attempt.branch_code)`.
- **Mutasi dict `attempt` yang diberikan secara in-place** (`attempt.update(...)`) lalu kembalikan dict itu, agar pemanggil dan fake DB pada tes melihat nilai baru.
- Return attempt dengan nilai baru.

`finalize_expired`: `SELECT * FROM tkd_attempts WHERE case_id=%s AND status='BERLANGSUNG' AND expires_at < %s FOR UPDATE`; finalisasi tiap baris dengan status `KEDALUWARSA`.

`sync_case_score`:
1. `SELECT score, passed, id, submitted_at FROM tkd_attempts WHERE case_id=%s AND status IN ('SELESAI','KEDALUWARSA') AND score IS NOT NULL ORDER BY score DESC, submitted_at ASC LIMIT 1`.
2. Bila tidak ada attempt → kembalikan skor kasus saat ini (`SELECT tkd_score, tkd_score_source, tkd_passed FROM recruitment_cases WHERE case_id=%s`).
3. Bila `tkd_score_source='MANUAL'` → kembalikan tanpa UPDATE.
4. UPDATE `recruitment_cases SET tkd_score=%s, tkd_score_source='AUTO', tkd_best_attempt_id=%s, tkd_passed=%s, tkd_score_updated_by='system:tkd', tkd_score_updated_at=NOW() WHERE case_id=%s`.
5. `INSERT IGNORE INTO recruitment_steps (case_id, step_type, status, branch_code) VALUES (%s,'TKD','PENDING',%s)` dengan branch = `attempt_branch` atau `first_branch`.
6. UPDATE semua baris TKD non-`DIKECUALIKAN`: `SELESAI` + `completed_at=submitted_at` + `evidence_type='tkd_attempt'` + `evidence_id=attempt.id` + `actor='system:tkd'` bila lulus; `PENDING` + `completed_at=NULL` + evidence kosong bila belum.

`attempt_result`: hitung `attempts_used`, `best_score`, dan state dari `public_state`; sertakan `official_score`/`official_passed` dari kasus yang sudah disinkronkan.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_service_attempts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/tkd_service.py tests/test_tkd_service_attempts.py
git commit -m "feat(tkd): mulai attempt, finalisasi lazy, dan skor resmi kasus"
```

---

### Task 7: Service DB — koreksi skor manual

**Files:**
- Modify: `modules/tkd_service.py`
- Test: `tests/test_tkd_service_manual.py`

**Interfaces:**
- Consumes: helper Task 5–6.
- Produces: `set_manual_score(cursor, case_id: str, score: float, reason: str, actor: str, pass_score: float, branch_code: str = '') -> dict` dengan kunci `old_score`, `score`, `passed`, `source='MANUAL'`, `branch_code`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_service_manual.py
from datetime import datetime
from modules import tkd_service as svc

class _Cursor:
    def __init__(self, conn):
        self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [self.conn.case]
        elif 'FROM CASE_BRANCH_HISTORY' in upper:
            self._rows = [{'branch_code': 'MLG'}]
        else:
            self._rows = []
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []
        self.case = {'case_id': 'RC-1', 'first_branch': 'SBY',
                     'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0}
    def cursor(self, dictionary=False): return _Cursor(self)

def test_koreksi_manual_menulis_skor_alasan_dan_status_lulus():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 75, 'Koreksi hasil', 'traineer1', 70)
    assert out['old_score'] == 60 and out['score'] == 75 and out['passed'] is True
    sql = ' '.join(s[0] for s in conn.statements)
    assert "TKD_SCORE_SOURCE='MANUAL'" in sql
    assert 'TKD_SCORE_NOTE=%S' in sql
    assert 'TKD_PASSED=%S' in sql

def test_koreksi_tanpa_baris_tkd_memakai_cabang_terakhir():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 80, 'Tes manual', 'ga_hr1', 70)
    assert out['branch_code'] == 'MLG'
    assert any('INSERT IGNORE INTO RECRUITMENT_STEPS' in s[0] for s in conn.statements)

def test_koreksi_manual_lebih_rendah_tetap_menang():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 50, 'Koreksi turun', 'traineer1', 70)
    assert out['score'] == 50 and out['passed'] is False and out['source'] == 'MANUAL'

def test_koreksi_tidak_mengubah_attempt():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    svc.set_manual_score(cur, 'RC-1', 50, 'Salah input', 'admin1', 70)
    assert not any('UPDATE TKD_ATTEMPTS' in s[0] for s in conn.statements)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_service_manual.py -q`
Expected: FAIL karena fungsi belum ada.

- [ ] **Step 3: Implementasi**

Alur:
1. Ambil kasus (`case_id`, `first_branch`, `tkd_score`); tidak ada → `ValueError('Kasus tidak ditemukan')`.
2. `branch = branch_code or _latest_branch_code(cursor, case_id, first_branch)`; query `case_branch_history ORDER BY last_seen_at DESC, first_seen_at DESC LIMIT 1`.
3. `passed = score >= pass_score`.
4. UPDATE `recruitment_cases SET tkd_score=%s, tkd_score_source='MANUAL', tkd_score_note=%s, tkd_score_updated_by=%s, tkd_score_updated_at=NOW(), tkd_passed=%s, tkd_best_attempt_id=NULL WHERE case_id=%s`.
5. `INSERT IGNORE` baris TKD untuk `branch` bila belum ada.
6. UPDATE semua baris TKD non-`DIKECUALIKAN` menjadi `SELESAI`/`PENDING`; `completed_at=NOW()` bila lulus; `evidence_type='manual_score'`, `evidence_id=''`, `actor=actor`.
7. Return dict.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_service_manual.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/tkd_service.py tests/test_tkd_service_manual.py
git commit -m "feat(tkd): koreksi skor manual yang menang atas skor otomatis"
```

---

### Task 8: Route publik — status & start

**Files:**
- Create: `modules/routes_tkd.py`
- Modify: `app.py` (import + `register_tkd_routes(app)` + prefix CSRF)
- Test: `tests/test_tkd_public_status_start.py`

**Interfaces:**
- Consumes: `from modules import tkd_service as svc` (semua panggilan lewat `svc.<fn>` agar mudah di-monkeypatch), `tkd_core.public_state`, `tkd_core.readiness`, `tkd_core.as_json`, `tkd_core.MODAL_TIERS`, `normalize_nik`, `client_ip`, `redis_rate_hit`, `log_activity_async`.
- Produces: `register_tkd_routes(app)` yang mendaftarkan seluruh endpoint publik/staff TKD (task berikut menambah endpoint ke modul yang sama).
- Produces: helper `_public(payload, status=200)`, `_rate(ip, nik, action)`, `_nik_key(nik)`, `_valid_date(value)`, `_verify_body(body)`, `_attempt_payload(attempt, items)`.
- Produces: `POST /api/recruitment/tkd/status` → `{'status':'success','data': <public_state>}`, `Cache-Control: no-store`.
- Produces: `POST /api/recruitment/tkd/start` → `{'status':'success','data': {'attempt_id','attempt_no','modal_tier','expires_at','remaining_seconds','duration_minutes','questions','answers'}}`.
- Produces: sesi Flask `tkd_case_id`, `tkd_verified_at` (epoch int), `tkd_branch`; berlaku 2 jam.
- Audit: `tkd_attempt_start` dengan `attempt_id`, `case_id`, `branch_code` (tanpa NIK).

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_public_status_start.py
from datetime import datetime, timedelta
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules import tkd_service as svc

CASE = {'case_id': 'RC-1', 'nik': '3573010101990001', 'nama': 'Andi',
        'tanggal_lahir': '1999-01-01', 'first_branch': 'SBY',
        'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
SETTINGS = {'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
            'max_attempts': 2, 'active': 1, 'shuffle_options': 0,
            'quota': {'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 3}}

class _NoopConn:
    def cursor(self, dictionary=False): return _NoopCursor()
    def commit(self): pass
    def close(self): pass

class _NoopCursor:
    def execute(self, sql, params=None): pass
    def fetchone(self): return None
    def fetchall(self): return []
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'tkd-test'
    rt.register_tkd_routes(a)
    monkeypatch.setattr(rt, 'get_master_connection', lambda: _NoopConn())
    monkeypatch.setattr(svc, 'resolve_branch_token', lambda cur, tok: 'SBY' if tok == 'tok' else '')
    monkeypatch.setattr(svc, 'load_settings', lambda cur: dict(SETTINGS))
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [{'id': 1}] * 31)
    monkeypatch.setattr(rt, 'readiness', lambda q, s: {'ready': True, 'reasons': []})
    monkeypatch.setattr(svc, 'verify_identity', lambda cur, nik, dob: dict(CASE) if (nik, dob) == (CASE['nik'], CASE['tanggal_lahir']) else None)
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik, for_update=False: dict(CASE))
    monkeypatch.setattr(svc, 'finalize_expired', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'fetch_tkd_steps', lambda cur, cid: [])
    monkeypatch.setattr(rt, 'redis_rate_hit', lambda *a, **k: True)
    return a

def _post(app, path, body):
    return app.test_client().post(path, json=body)

def test_status_sukses_menyimpan_sesi_tanpa_nik(app):
    client = app.test_client()
    r = client.post('/api/recruitment/tkd/status',
                    json={'nik': CASE['nik'], 'dob': CASE['tanggal_lahir'], 'token': 'tok'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['state'] == 'BELUM' and data['can_start'] is True
    assert r.headers['Cache-Control'] == 'no-store'
    with client.session_transaction() as s:
        assert s['tkd_case_id'] == 'RC-1' and 'nik' not in s and 'tkd_branch' == 'SBY'

def test_status_dob_salah_ditolak_generik_tanpa_data(app):
    r = _post(app, '/api/recruitment/tkd/status',
              {'nik': CASE['nik'], 'dob': '2000-01-01', 'token': 'tok'})
    assert r.status_code == 403
    body = r.get_json()
    assert body['status'] == 'error'
    assert 'Andi' not in r.get_data(as_text=True)
    assert 'tkd_score' not in r.get_data(as_text=True)

def test_token_salah_dan_input_invalid(app):
    assert _post(app, '/api/recruitment/tkd/status',
                 {'nik': CASE['nik'], 'dob': '1999-01-01', 'token': 'x'}).status_code == 400
    assert _post(app, '/api/recruitment/tkd/status',
                 {'nik': '123', 'dob': '1999-01-01', 'token': 'tok'}).status_code == 400

def test_start_menolak_tier_tidak_dikenal_dan_bank_belum_aktif(app, monkeypatch):
    bad = _post(app, '/api/recruitment/tkd/start',
                {'nik': CASE['nik'], 'dob': '1999-01-01', 'token': 'tok', 'modal_tier': '20k'})
    assert bad.status_code == 400

    monkeypatch.setattr(svc, 'load_settings', lambda cur: dict(SETTINGS, active=0))
    off = _post(app, '/api/recruitment/tkd/start',
                {'nik': CASE['nik'], 'dob': '1999-01-01', 'token': 'tok', 'modal_tier': '30k'})
    assert off.status_code == 409

def test_start_mengembalikan_soal_tanpa_kunci(app, monkeypatch):
    monkeypatch.setattr(svc, 'create_attempt', lambda *a, **k: {
        'attempt': {'id': 'TKD-1', 'attempt_no': 1, 'expires_at': datetime(2026, 11, 24, 10, 25)},
        'items': [{'position': 1, 'snapshot': {'type': 'MCQ', 'prompt': 'P',
                    'options': [{'id': 'a', 'text': 'A'}], 'answer': {'option': 'a'},
                    'points': 1, 'category': 'REGULASI'}, 'answer': None}]})
    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'dob': '1999-01-01', 'token': 'tok', 'modal_tier': '30k'})
    assert r.status_code == 200
    body = r.get_json()['data']
    q = body['questions'][0]
    assert 'answer' not in q and 'points' not in q
    assert body['attempt_id'] == 'TKD-1'
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_public_status_start.py -q`
Expected: FAIL karena route belum ada.

- [ ] **Step 3: Implementasi route publik**

Helper modul:
```python
_PUBLIC_ROLES = ('traineer', 'ga_hr', 'admin')
_SESSION_HOURS = 2

def _public(payload, status=200):
    resp = jsonify(payload); resp.headers['Cache-Control'] = 'no-store'; return resp, status

def _nik_key(nik): return hashlib.sha256(nik.encode()).hexdigest()[:32]

def _rate(ip, nik, action):
    return (redis_rate_hit(f'{action}|ip|{ip}', 10, 60, prefix='tkd')
            and redis_rate_hit(f'{action}|nik|{_nik_key(nik)}', 5, 60, prefix='tkd'))

def _verify_body(body):
    nik, _ = normalize_nik(body.get('nik'))
    dob = str(body.get('dob') or '').strip()
    token = str(body.get('token') or '').strip()
    if len(nik) != 16 or not _valid_date(dob) or not token:
        return None, ('error', 400, 'Data belum lengkap.')
    return {'nik': nik, 'dob': dob, 'token': token}, None
```

`status`:
1. Body JSON; `_verify_body`; bila error → `_public({'status':'error','msg':err[2]}, err[1])`. Rate limit per IP+NIK → 429.
2. Buka koneksi master; `cursor(dictionary=True)`; `branch = svc.resolve_branch_token(cursor, token)`; kosong → 400 `'Tautan tidak valid atau sudah dirotasi.'`.
3. `case = svc.verify_identity(cursor, nik, dob)`; `None` → 403 `'Data belum lengkap, hubungi Traineer.'` (tanpa detail).
4. Set sesi (`tkd_case_id`, `tkd_verified_at=int(time.time())`, `tkd_branch=branch`).
5. `settings = svc.load_settings(cursor)`; `questions = svc.fetch_active_questions(cursor)`; `ready = readiness(questions, settings)`; `settings['bank_ready'] = ready['ready']`.
6. `svc.finalize_expired(cursor, case_id)`; `attempts = svc.fetch_attempts(...)`; `steps = svc.fetch_tkd_steps(...)`; `data = public_state(case, attempts, steps, settings)`; tambahkan `bank_ready`.
7. Return `_public({'status':'success','data':data})`.

`start`:
1. Sama seperti status + `modal_tier` wajib ∈ `MODAL_TIERS` → 400.
2. Setelah verifikasi, kunci baris kasus dengan `svc.fetch_case_by_nik(cursor, nik, for_update=True)`.
3. `settings`/`ready`; tidak aktif/tidak siap → 409 `'TKD belum dibuka. Hubungi Traineer cabang.'`.
4. `svc.finalize_expired`; `attempts`/`steps`; `state = public_state(...)`.
5. Bila `state['state'] == 'BERLANGSUNG'` → ambil attempt aktif + item, kembalikan payload resume.
6. Bila `state['can_start']` false → 409 dengan pesan sesuai state (`DIKECUALIKAN`, `LULUS`, `HABIS`, `SKOR_BELUM_TERCATAT`).
7. `create_attempt(...)`; `commit`; return payload.

Payload attempt publik:
```python
def _attempt_payload(attempt, items):
    questions = []
    answers = {}
    for item in items:
        snap = as_json(item['snapshot'], {})
        q = {'position': item['position'], 'type': snap.get('type'),
             'category': snap.get('category'), 'prompt': snap.get('prompt'),
             'options': snap.get('options') or []}
        questions.append(q)
        ans = as_json(item.get('answer'))
        if ans is not None:
            answers[str(item['position'])] = ans
    remaining = max(0, int((attempt['expires_at'] - datetime.now()).total_seconds()))
    return {'attempt_id': attempt['id'], 'attempt_no': attempt['attempt_no'],
            'modal_tier': attempt.get('modal_tier'), 'expires_at': _as_iso(attempt['expires_at']),
            'remaining_seconds': remaining,
            'duration_minutes': as_json(attempt.get('settings_snapshot'), {}).get('duration_minutes', 25),
            'questions': questions, 'answers': answers}
```

- [ ] **Step 4: Daftarkan di `app.py` dan CSRF**

Setelah `register_recruitment_routes(app)`:
```python
from modules.routes_tkd import register_tkd_routes
register_tkd_routes(app)
```
Tambahkan ke `CSRF_EXEMPT_PREFIXES` **hanya** path publik:
```python
'/api/recruitment/tkd/status',
'/api/recruitment/tkd/start',
'/api/recruitment/tkd/attempts/',
```
Jangan mengecualikan `/api/recruitment/tkd/questions`, `/score`, `/settings`, `/attempts` (daftar staff), atau `/review/`.

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_public_status_start.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_tkd.py app.py tests/test_tkd_public_status_start.py
git commit -m "feat(tkd): status dan mulai ujian publik dengan sesi terverifikasi"
```

---

### Task 9: Route publik — resume, simpan jawaban, submit, hasil

**Files:**
- Modify: `modules/routes_tkd.py`
- Test: `tests/test_tkd_public_attempt.py`

**Interfaces:**
- Consumes: sesi + helper Task 8; `from modules import tkd_service as svc`, `tkd_service.fetch_attempt`, `fetch_attempt_items`, `finalize_attempt`, `attempt_result`, `fetch_attempts`, `fetch_tkd_steps`.
- Produces: `GET /api/recruitment/tkd/attempts/<id>`, `PUT .../answers/<position>`, `POST .../submit`, `GET .../result`.
- Produces: `_require_session(attempt)` helper (403 bila sesi kosong/kedaluwarsa, 404 bila attempt bukan milik sesi), `_save_answer(cursor, item, answer)` helper, `_valid_answer(snapshot, answer)` helper.
- Attempt hanya boleh diakses bila `attempt.case_id == session['tkd_case_id']`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_public_attempt.py
from datetime import datetime, timedelta
import json
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules import tkd_service as svc

ATTEMPT = {'id': 'TKD-1', 'case_id': 'RC-1', 'attempt_no': 1, 'status': 'BERLANGSUNG',
           'expires_at': datetime.now() + timedelta(minutes=20), 'modal_tier': '30k',
           'settings_snapshot': json.dumps({'duration_minutes': 25}),
           'pass_score_snapshot': 70, 'branch_code': 'SBY'}
ITEM = {'position': 1, 'snapshot': json.dumps({'type': 'MCQ', 'category': 'REGULASI',
        'prompt': 'P', 'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
        'answer': {'option': 'a'}, 'points': 1}), 'answer': None}

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'tkd-test'
    rt.register_tkd_routes(a)
    class _Conn:
        def cursor(self, dictionary=False): return object()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(rt, 'get_master_connection', _Conn)
    monkeypatch.setattr(rt, 'redis_rate_hit', lambda *a, **k: True)
    monkeypatch.setattr(svc, 'fetch_attempt', lambda cur, aid, for_update=False: dict(ATTEMPT) if aid == 'TKD-1' else None)
    monkeypatch.setattr(svc, 'fetch_attempt_items', lambda cur, aid: [dict(ITEM)])
    monkeypatch.setattr(svc, 'load_settings', lambda cur: {'pass_score': 70, 'max_attempts': 2, 'question_count': 20, 'duration_minutes': 25, 'active': 1, 'quota': {}})
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik: {'case_id': 'RC-1', 'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0})
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [dict(ATTEMPT)])
    monkeypatch.setattr(svc, 'fetch_tkd_steps', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'finalize_expired', lambda cur, cid: [])
    return a

def _client(app, case_id='RC-1'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['tkd_case_id'] = case_id
        s['tkd_verified_at'] = int(datetime.now().timestamp())
    return c

def test_attempt_tanpa_sesi_atau_kasus_lain_ditolak(app):
    assert app.test_client().get('/api/recruitment/tkd/attempts/TKD-1').status_code == 403
    assert _client(app, 'RC-lain').get('/api/recruitment/tkd/attempts/TKD-1').status_code == 404

def test_resume_mengembalikan_soal_tanpa_kunci(app):
    r = _client(app).get('/api/recruitment/tkd/attempts/TKD-1')
    assert r.status_code == 200
    body = r.get_json()['data']
    q = body['questions'][0]
    assert 'answer' not in q and 'points' not in q
    assert q['position'] == 1

def test_simpan_jawaban_mcq_valid_dan_opsi_asing_ditolak(app, monkeypatch):
    saved = {}
    monkeypatch.setattr(rt, '_save_answer', lambda cur, item, answer: saved.update(answer=answer))
    c = _client(app)
    ok = c.put('/api/recruitment/tkd/attempts/TKD-1/answers/1', json={'answer': {'option': 'b'}})
    assert ok.status_code == 200 and saved['answer'] == {'option': 'b'}
    bad = c.put('/api/recruitment/tkd/attempts/TKD-1/answers/1', json={'answer': {'option': 'z'}})
    assert bad.status_code == 400
    missing = c.put('/api/recruitment/tkd/attempts/TKD-1/answers/99', json={'answer': {'option': 'a'}})
    assert missing.status_code == 404

def test_submit_idempoten_dan_tanpa_kunci(app, monkeypatch):
    done = dict(ATTEMPT, status='SELESAI', score=85.0, passed=1, submitted_at=datetime.now())
    monkeypatch.setattr(svc, 'finalize_attempt', lambda cur, att, status='SELESAI': dict(done))
    monkeypatch.setattr(svc, 'attempt_result', lambda cur, att, settings: {'score': 85.0, 'passed': True,
                        'official_score': 85.0, 'best_score': 85.0, 'attempts_used': 1,
                        'max_attempts': 2, 'state': 'LULUS'})
    c = _client(app)
    first = c.post('/api/recruitment/tkd/attempts/TKD-1/submit')
    second = c.post('/api/recruitment/tkd/attempts/TKD-1/submit')
    assert first.status_code == 200 and second.status_code == 200
    assert 'answer' not in first.get_data(as_text=True)

def test_hasil_attempt_masih_berjalan_ditolak(app):
    assert _client(app).get('/api/recruitment/tkd/attempts/TKD-1/result').status_code == 409
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_public_attempt.py -q`
Expected: FAIL karena endpoint belum ada.

- [ ] **Step 3: Implementasi**

`_require_session(attempt)`:
- `case_id = session.get('tkd_case_id')`; `verified = int(session.get('tkd_verified_at') or 0)`; bila kosong atau `time.time()-verified > 7200` → 403.
- `attempt is None or attempt['case_id'] != case_id` → 404.
- Semua response memakai `_public(...)` dari Task 8 (`Cache-Control: no-store`).

`GET attempt`:
- Ambil attempt (`svc.fetch_attempt`); bila `expires_at < now` dan status `BERLANGSUNG` → `svc.finalize_attempt(cur, attempt, 'KEDALUWARSA')`; return `{'finished': True, 'result': svc.attempt_result(cur, attempt, settings)}`.
- Bila status bukan `BERLANGSUNG` → `{'finished': True, 'result': svc.attempt_result(cur, attempt, settings)}`.
- Selain itu → `_attempt_payload`.

`PUT answer`:
- Rate limit: `redis_rate_hit(f'tkd-answer|{attempt_id}', 60, 60, prefix='tkd')` → 429 bila lewat.
- Position int; item = item dengan `position` tersebut; tidak ada → 404.
- Attempt harus `BERLANGSUNG` dan belum lewat `expires_at` (bila lewat → finalisasi dan 409 dengan hasil).
- Validasi bentuk: MCQ `{'option': id}` dan id ada di snapshot; NUMERIC `parse_numeric` bukan None → simpan `{'value': x}`; SHORT_TEXT/PROFILE `{'text': str}` dipotong 500/1000.
- Setelah valid, panggil `_save_answer(cursor, item, answer)`; helper itu yang menjalankan `UPDATE tkd_attempt_items SET answer=%s, answered_at=NOW() WHERE attempt_id=%s AND position=%s`, lalu commit; return `{'position','saved':True}`.

`POST submit`:
- Rate limit: `redis_rate_hit(f'tkd-submit|{attempt_id}', 5, 60, prefix='tkd')` → 429 bila lewat.
- Attempt; bila sudah selesai → `svc.attempt_result` (idempoten).
- `status = 'KEDALUWARSA' if now > expires_at + 60s else 'SELESAI'`.
- `svc.finalize_attempt`; commit; audit `tkd_attempt_submit` (`attempt_id`, `case_id`, `status`, `score`; tanpa NIK); return `svc.attempt_result`.

`GET result`:
- Attempt; bila `BERLANGSUNG` dan sudah lewat → finalisasi; bila masih `BERLANGSUNG` → 409 `'Ujian belum selesai.'`.
- Return `svc.attempt_result`.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_public_attempt.py tests/test_tkd_public_status_start.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/routes_tkd.py tests/test_tkd_public_attempt.py
git commit -m "feat(tkd): resume, autosave jawaban, submit, dan hasil publik"
```

---

### Task 10: Route staff — bank soal

**Files:**
- Modify: `modules/routes_tkd.py`
- Test: `tests/test_tkd_staff_bank.py`

**Interfaces:**
- Consumes: `validate_question`, `normalize_question` dari `tkd_core`; `log_activity_async`, `role_required`.
- Produces: `GET /api/recruitment/tkd/questions`, `POST /api/recruitment/tkd/questions`, `PUT /api/recruitment/tkd/questions/<id>`, `POST /api/recruitment/tkd/questions/<id>/toggle`.
- Produces: response staff memuat `answer` dan `points`; response publik tidak pernah memakai endpoint ini.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_staff_bank.py
import json
import pytest
from flask import Flask
from modules import routes_tkd as rt

QUESTION = {'id': 1, 'code': 'REG-01', 'category': 'REGULASI', 'type': 'MCQ',
            'prompt': 'P', 'options': json.dumps([{'id': 'a', 'text': 'A'}]),
            'answer': json.dumps({'option': 'a'}), 'points': 1,
            'modal_tier': None, 'active': 0, 'sort_order': 0}

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split()); self.conn.statements.append((u, params))
        if u.startswith('SELECT') and 'FROM TKD_QUESTIONS' in u:
            self._rows = [dict(QUESTION)]
        elif u.startswith('INSERT INTO TKD_QUESTIONS'):
            self.conn.inserted = params; self.lastrowid = 7
        elif u.startswith('UPDATE TKD_QUESTIONS'):
            self.conn.updated = params
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []; self.inserted = None; self.updated = None
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    conn = _Conn()
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    a.conn = conn
    return a

def _client(app, role='traineer'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = role; s['user_name'] = 'petugas'
    return c

def test_daftar_soal_staff_memuat_kunci(app):
    r = _client(app).get('/api/recruitment/tkd/questions')
    assert r.status_code == 200
    row = r.get_json()['data'][0]
    assert row['answer'] == {'option': 'a'} and row['options'] == [{'id': 'a', 'text': 'A'}]

def test_role_lain_ditolak(app):
    assert _client(app, 'finance').get('/api/recruitment/tkd/questions').status_code == 403

def test_tambah_soal_valid_dan_invalid(app):
    body = {'code': 'NEW-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer': {'option': 'a'}, 'points': 1}
    ok = _client(app).post('/api/recruitment/tkd/questions', json=body)
    assert ok.status_code == 201 and ok.get_json()['data']['id'] == 7
    bad = _client(app).post('/api/recruitment/tkd/questions', json=dict(body, answer={'option': 'z'}))
    assert bad.status_code == 400

def test_toggle_membalik_status(app):
    r = _client(app).post('/api/recruitment/tkd/questions/1/toggle')
    assert r.status_code == 200
    assert any('UPDATE TKD_QUESTIONS SET ACTIVE' in s[0] for s in app.conn.statements)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_staff_bank.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementasi**

Semua endpoint memakai `@role_required(['traineer','ga_hr','admin'])`.
- GET: filter opsional `category`, `active` (`''` = semua), `q` (LIKE prompt/code); `ORDER BY category, sort_order, id`; parse `options`/`answer` JSON sebelum dikirim; tambahkan `updated_at` ISO.
- POST: `body = request.get_json(silent=True) or {}`; `validate_question`; error → 400 `{'status':'error','msg': '; '.join(errors)}`; `normalize_question`; INSERT semua kolom; `active` default 0; `created_by`/`updated_by` = session user; audit `tkd_question_create` dengan `code`, tanpa NIK; return 201 `{'status':'success','data':{'id': cursor.lastrowid}}`.
- PUT: id int; validasi; pastikan baris ada (SELECT) → 404; UPDATE; audit `tkd_question_update`; return 200.
- POST toggle: SELECT `active`; tidak ada → 404; UPDATE `active = 1 - active`; audit `tkd_question_toggle`; return status baru.
- Tidak ada DELETE fisik.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_staff_bank.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/routes_tkd.py tests/test_tkd_staff_bank.py
git commit -m "feat(tkd): CRUD bank soal staff"
```

---

### Task 11: Route staff — impor/ekspor CSV dan seed script

**Files:**
- Modify: `modules/routes_tkd.py`
- Create: `scripts/seed_tkd_bank.py`
- Test: `tests/test_tkd_staff_csv.py`, `tests/test_tkd_seed.py`

**Interfaces:**
- Consumes: `csv_to_question_rows`, `import_rows`, `question_row_to_csv`, `CSV_COLUMNS`.
- Produces: `POST /api/recruitment/tkd/questions/import` body JSON `{'csv': str, 'update_drafts': bool}` → `{'inserted','updated','skipped','errors'}`.
- Produces: `GET /api/recruitment/tkd/questions/export.csv` → `text/csv` dengan `Content-Disposition: attachment`.
- Produces: `seed_bank(cursor, csv_text) -> dict` di `scripts/seed_tkd_bank.py` — insert-if-absent berdasarkan `code`, semua baris baru `active=0`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_staff_csv.py
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules.tkd_core import CSV_COLUMNS

CSV_TEXT = ('code,category,type,prompt,option_a,option_b,option_c,option_d,option_e,'
            'correct,tolerance,points,modal_tier,active\n'
            'NEW-1,PRODUK,MCQ,Pertanyaan,A,B,,, ,a,,1,,1\n')

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split()); self.conn.statements.append((u, params))
        if 'FROM TKD_QUESTIONS' in u and u.startswith('SELECT'):
            self._rows = [{'code': 'OLD-1', 'active': 1}]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    monkeypatch.setattr(rt, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    return a

def _client(app, role='traineer'):
    c = app.test_client()
    with c.session_transaction() as s: s['user_role'] = role; s['user_name'] = 'petugas'
    return c

def test_impor_menyisipkan_draft_dan_melewati_kode_aktif(app):
    r = _client(app).post('/api/recruitment/tkd/questions/import',
                          json={'csv': CSV_TEXT, 'update_drafts': False})
    assert r.status_code == 200
    body = r.get_json()
    assert body['inserted'] == 1 and body['skipped'] == 0

def test_impor_menolak_csv_kosong_dan_baris_berlebih(app):
    assert _client(app).post('/api/recruitment/tkd/questions/import', json={}).status_code == 400
    too_many = CSV_TEXT + ''.join(
        f'X-{i},PRODUK,MCQ,P,A,B,,,,a,,1,,0\n' for i in range(500))
    r = _client(app).post('/api/recruitment/tkd/questions/import', json={'csv': too_many})
    assert r.status_code == 400

def test_ekspor_csv_memakai_header_lengkap(app):
    r = _client(app).get('/api/recruitment/tkd/questions/export.csv')
    assert r.status_code == 200
    assert r.mimetype == 'text/csv'
    assert r.get_data(as_text=True).splitlines()[0] == ','.join(CSV_COLUMNS)
    assert 'attachment' in r.headers['Content-Disposition']

def test_role_finance_tidak_boleh_impor(app):
    assert _client(app, 'finance').post('/api/recruitment/tkd/questions/import',
                                        json={'csv': CSV_TEXT}).status_code == 403
```

```python
# tests/test_tkd_seed.py
from pathlib import Path
from scripts.seed_tkd_bank import seed_bank

ROOT = Path(__file__).resolve().parents[1]
CSV = (ROOT / 'docs' / 'seed' / 'tkd_bank_v1.csv').read_text(encoding='utf-8')

class _Cursor:
    def __init__(self, existing): self.existing = existing; self.inserted = []
    def execute(self, sql, params=None):
        if 'FROM TKD_QUESTIONS' in ' '.join(str(sql).upper().split()):
            self._rows = [{'code': c} for c in self.existing]
        elif 'INSERT INTO TKD_QUESTIONS' in ' '.join(str(sql).upper().split()):
            self.inserted.append(params)
        else:
            self._rows = []
    def fetchall(self): return getattr(self, '_rows', [])
    def fetchone(self): return None
    def close(self): pass

class _Conn:
    def __init__(self, existing): self.c = _Cursor(existing)
    def cursor(self, dictionary=False): return self.c
    def commit(self): pass

def test_seed_insert_if_absent_tidak_menyentuh_kode_yang_ada():
    conn = _Conn(existing={'REG-01'})
    out = seed_bank(conn.c, CSV)
    assert out['inserted'] == 30 and out['skipped'] == 1
    assert all(p[-1] == 0 for p in conn.c.inserted)  # active=0

def test_seed_idempoten_saat_semua_kode_sudah_ada():
    codes = {line.split(',')[0] for line in CSV.splitlines()[1:] if line.strip()}
    conn = _Conn(existing=codes)
    out = seed_bank(conn.c, CSV)
    assert out['inserted'] == 0 and out['skipped'] == 31
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_staff_csv.py tests/test_tkd_seed.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementasi route impor/ekspor**

Impor:
1. `body = request.get_json(silent=True) or {}`; `text = body.get('csv')`; bukan string atau kosong → 400; `len(text) > 300_000` → 400.
2. `rows, errors = csv_to_question_rows(text)`; `errors` → 400 `{'status':'error','msg':'; '.join(errors[:10])}`.
3. `SELECT code, active FROM tkd_questions` → `existing = {code: {'active': ...}}`.
4. `plan = import_rows(existing, rows, bool(body.get('update_drafts')))`.
5. INSERT baris `plan['insert']` dengan `active=0`; UPDATE baris `plan['update']` hanya `WHERE code=%s AND active=0`.
6. Audit `tkd_questions_import` dengan hitungan; return `{'inserted': n, 'updated': n, 'skipped': n, 'errors': []}`.

Ekspor: SELECT semua; `io.StringIO`; `csv.writer`; header `CSV_COLUMNS`; baris `question_row_to_csv`; return `Response(text, mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=tkd_bank.csv'})`.

- [ ] **Step 4: Implementasi `scripts/seed_tkd_bank.py`**

```python
def seed_bank(cursor, csv_text):
    rows, errors = csv_to_question_rows(csv_text)
    if errors:
        raise ValueError('; '.join(errors[:10]))
    cursor.execute('SELECT code FROM tkd_questions')
    existing = {str(r['code']) for r in (cursor.fetchall() or [])}
    inserted = skipped = 0
    for row in rows:
        if row['code'] in existing:
            skipped += 1
            continue
        _insert_question(cursor, row, active=0)
        inserted += 1
    return {'inserted': inserted, 'skipped': skipped, 'errors': []}
```

`main()`: argumen `--csv` default `docs/seed/tkd_bank_v1.csv`, `--dry-run`; `ensure_tkd_schema()`; koneksi master; `seed_bank`; commit; print ringkasan. Script **tidak** dipanggil saat startup.

Catatan: `_insert_question(cursor, row, active=0)` dipakai bersama oleh route impor dan seed; letakkan `active` sebagai **parameter terakhir** pada `INSERT INTO tkd_questions (...)` agar tes seed dapat memeriksa `params[-1] == 0`.

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_staff_csv.py tests/test_tkd_seed.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_tkd.py scripts/seed_tkd_bank.py tests/test_tkd_staff_csv.py tests/test_tkd_seed.py
git commit -m "feat(tkd): impor/ekspor CSV dan seed bank insert-if-absent"
```

---

### Task 12: Route staff — hasil, review, koreksi skor, pengaturan

**Files:**
- Modify: `modules/routes_tkd.py`
- Test: `tests/test_tkd_staff_results.py`

**Interfaces:**
- Consumes: `set_manual_score`, `finalize_expired`, `attempt_result`, `readiness`, `validate_settings`, `fetch_active_questions`, `load_settings`, `fetch_attempt`, `fetch_attempt_items`.
- Produces: `GET /api/recruitment/tkd/attempts`, `GET /api/recruitment/tkd/review/<id>`, `POST /api/recruitment/tkd/score`, `GET /api/recruitment/tkd/settings`, `PUT /api/recruitment/tkd/settings`.
- Produces: `_scope_branch(conn) -> str | None` — `None` hanya untuk Admin Pusat (`is_ho_admin`); role lain memakai `session['branch_code']`.
- Produces: `_fetch_attempt_rows(cursor, scope, params) -> list[dict]`, `_fetch_review(cursor, attempt_id, scope) -> dict | None`, `_case_in_scope(cursor, case_id, scope) -> bool`, `_mask_nik(nik) -> str`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_tkd_staff_results.py
import json
from datetime import datetime
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules import tkd_service as svc

CASE = {'case_id': 'RC-1', 'nama': 'Andi', 'nik': '3573010101990001',
        'first_branch': 'SBY', 'tkd_score': 60, 'tkd_score_source': 'AUTO',
        'tkd_passed': 0, 'tkd_score_note': None}

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    class _Conn:
        def cursor(self, dictionary=False): return object()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(rt, 'get_master_connection', _Conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rt, '_scope_branch', lambda conn: 'SBY')
    monkeypatch.setattr(rt, '_fetch_attempt_rows', lambda cur, scope, q: [{
        'id': 'TKD-1', 'case_id': 'RC-1', 'nama': 'Andi',
        'nik': '3573010101990001', 'branch_code': 'SBY', 'attempt_no': 1,
        'status': 'SELESAI', 'score': 60, 'passed': 0,
        'started_at': datetime(2026, 11, 24, 10, 0),
        'submitted_at': datetime(2026, 11, 24, 10, 20),
        'score_source': 'AUTO'}])
    monkeypatch.setattr(svc, 'set_manual_score', lambda *a, **k: {
        'old_score': 60, 'score': 75, 'passed': True, 'source': 'MANUAL', 'branch_code': 'SBY'})
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik: dict(CASE))
    monkeypatch.setattr(svc, 'load_settings', lambda cur: {
        'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
        'max_attempts': 2, 'quota': {'REGULASI': 7, 'PERUSAHAAN': 4,
                                     'PRODUK': 6, 'HITUNG': 3},
        'shuffle_options': 0, 'active': 1})
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [{'id': i} for i in range(30)])
    monkeypatch.setattr(rt, 'readiness', lambda q, s: {
        'ready': True, 'active_valued': 30, 'quota_ok': {}, 'tier_ok': {},
        'reasons': []})
    monkeypatch.setattr(rt, '_case_in_scope', lambda cur, cid, scope: True)
    monkeypatch.setattr(rt, 'finalize_expired_all', lambda cur, scope: [])
    return a

def _client(app, role='traineer', branch='SBY'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = role; s['user_name'] = 'petugas'; s['branch_code'] = branch
    return c

def test_daftar_hasil_memasker_nik(app):
    r = _client(app).get('/api/recruitment/tkd/attempts')
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert '****0001' in text and '3573010101990001' not in text

def test_review_hanya_staff_dan_memuat_kunci(app, monkeypatch):
    monkeypatch.setattr(rt, '_fetch_review', lambda cur, aid, scope: {
        'attempt': {'id': 'TKD-1'}, 'case': {'nama': 'Andi'},
        'items': [{'position': 1, 'answer': {'option': 'a'}, 'is_correct': 1, 'points_awarded': 1,
                   'snapshot': {'prompt': 'P', 'answer': {'option': 'a'}, 'points': 1}}]})
    r = _client(app).get('/api/recruitment/tkd/review/TKD-1')
    assert r.status_code == 200
    assert r.get_json()['data']['items'][0]['snapshot']['answer'] == {'option': 'a'}
    assert _client(app, 'finance').get('/api/recruitment/tkd/review/TKD-1').status_code == 403

def test_koreksi_skor_wajib_alasan_dan_rentang_0_100(app):
    c = _client(app)
    assert c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 75}).status_code == 400
    assert c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 101, 'reason': 'x'}).status_code == 400
    ok = c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 75, 'reason': 'Koreksi'})
    assert ok.status_code == 200 and ok.get_json()['data']['score'] == 75

def test_pengaturan_hanya_admin_boleh_ubah(app):
    assert _client(app, 'traineer').put('/api/recruitment/tkd/settings', json={}).status_code == 403
    assert _client(app, 'admin').get('/api/recruitment/tkd/settings').status_code == 200
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_tkd_staff_results.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementasi daftar hasil & review**

`GET /attempts`:
- `scope = _scope_branch(conn)`.
- `finalize_expired_all(cursor, scope)` — pilih attempt `BERLANGSUNG` yang `expires_at < NOW()`, batasi 200, finalisasi.
- Query join `tkd_attempts a JOIN recruitment_cases c ON c.case_id=a.case_id`; filter `branch_code` (default scope), `status`, `from`, `to`, `q` (nama LIKE atau `c.nik` bila 16 digit).
- Respons per baris: `id`, `case_id`, `nama`, `nik_masked`, `branch_code`, `attempt_no`, `status`, `score`, `passed`, `started_at`, `submitted_at`, `score_source` (dari `c.tkd_score_source`).
- Jangan meneruskan `nik` mentah: bentuk dict baru dengan `nik_masked = _mask_nik(row.get('nik'))` dan tanpa kunci `nik`.
- `nik_masked` memakai `_mask_nik` (import dari `routes_recruitment` atau duplikat 3 baris).

`GET /review/<id>`:
- Attempt + case; `scope` dan attempt.branch_code harus cocok (kecuali `scope is None`) → 403/404.
- Items: `position`, `snapshot` (prompt/type/category/options/answer/points), `answer`, `is_correct`, `points_awarded`.
- Sertakan jawaban `PROFILE_TEXT` terakhir dan `modal_tier`, `settings_snapshot`, `score`, `passed`.

- [ ] **Step 4: Implementasi koreksi skor & pengaturan**

`POST /score`:
- Body `case_id`, `score` (float 0–100), `reason` (wajib, maks 500).
- Scope: `_case_in_scope(cursor, case_id, scope)` — cek `first_branch`, `case_branch_history`, atau `recruitment_steps`; gagal → 403.
- `settings = svc.load_settings(cursor)`; `svc.set_manual_score(...)`; commit; audit `recruitment_tkd_score_edit` (`case_id`, `old_score`, `score`, `reason`, aktor; tanpa NIK).
- Return data.

`GET /settings`: `settings = svc.load_settings(cursor)` lalu `readiness(svc.fetch_active_questions(cursor), settings)`; kembalikan `question_count`, `duration_minutes`, `pass_score`, `max_attempts`, `quota`, `shuffle_options`, `active`, `readiness`.

`PUT /settings`:
- `@role_required(['admin'])` **hanya** untuk method ini; daftarkan route terpisah atau cek `session['user_role'] == 'admin'` di dalam handler (lebih sederhana: dua route dengan method berbeda tidak bisa decorator berbeda, jadi cek manual dan return 403).
- `validate_settings`; error → 400.
- Bila `active=1`, `readiness` harus `ready` → 409 dengan `reasons`.
- UPDATE `tkd_settings`; audit `tkd_settings_update`; return settings baru.

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_tkd_staff_results.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_tkd.py tests/test_tkd_staff_results.py
git commit -m "feat(tkd): hasil, review, koreksi skor, dan pengaturan staff"
```

---

### Task 13: Integrasi rekrutmen — link portal, skor di daftar kasus, bukti TKD

**Files:**
- Modify: `modules/routes_recruitment.py`
- Test: `tests/test_recruitment_portal_links.py`, `tests/test_recruitment_cases_score.py`

**Interfaces:**
- Consumes: `cv_online_branch_forms`, `branches`, `is_ho_admin`, `set_manual_score`.
- Produces: `GET /api/recruitment/portal-links` (role `receptionist`, `traineer`, `ga_hr`, `admin`) → `{'data':[{'branch_code','branch_name','portal_path','active'}], 'scope_branch': str|None}`; `portal_path` = `/app/recruitment-portal?token=<form_token>`.
- Produces: `GET /api/recruitment/cases` menambahkan `tkd_score`, `tkd_score_source`, `tkd_score_note`, `tkd_passed` di level kasus.
- Produces: `POST /api/recruitment/steps/<id>/evidence` untuk TKD dengan `score` → memanggil `set_manual_score` dan menghitung status; tanpa `score` perilaku lama.

- [ ] **Step 1: Tulis tes link portal**

```python
# tests/test_recruitment_portal_links.py
import pytest
from flask import Flask
from modules import routes_recruitment as rr

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split())
        if 'FROM BRANCHES' in u:
            self._rows = [{'code': 'SBY', 'name': 'Surabaya'},
                          {'code': 'MLG', 'name': 'Malang'}]
        elif 'FROM CV_ONLINE_BRANCH_FORMS' in u:
            self._rows = [{'branch_code': 'SBY', 'form_token': 'tok-sby', 'active': 1},
                          {'branch_code': 'MLG', 'form_token': 'tok-mlg', 'active': 1}]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rr.register_recruitment_routes(a)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(rr, '_portal_scope_branch', lambda conn: 'SBY')
    return a

def _client(app, role='receptionist'):
    c = app.test_client()
    with c.session_transaction() as s: s['user_role'] = role; s['user_name'] = 'resepsionis'
    return c

def test_satu_link_portal_per_cabang_dalam_scope(app):
    r = _client(app).get('/api/recruitment/portal-links')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data == [{'branch_code': 'SBY', 'branch_name': 'Surabaya',
                     'portal_path': '/app/recruitment-portal?token=tok-sby',
                     'active': True}]

def test_tidak_ada_link_cv_atau_firstwork(app):
    text = _client(app).get('/api/recruitment/portal-links').get_data(as_text=True)
    assert 'cv-online-form' not in text and 'first-work-form' not in text

def test_role_finance_ditolak(app):
    assert _client(app, 'finance').get('/api/recruitment/portal-links').status_code == 403
```

- [ ] **Step 2: Tulis tes skor kasus & bukti TKD**

Perluas `tests/test_recruitment_cases_api.py`: tambahkan empat field skor ke setiap dict `_FakeConn.cases`, lalu sesuaikan `test_field_kasus_lengkap`.

```python
# pada tests/test_recruitment_cases_api.py — _FakeConn.cases
{'case_id': CASE_A, 'nik': NIK_A, 'nama': 'Andi',
 'first_branch': 'SBY', 'status': 'AKTIF',
 'first_seen_at': datetime(2026, 11, 20, 10, 0),
 'tkd_score': 86.67, 'tkd_score_source': 'AUTO',
 'tkd_score_note': None, 'tkd_passed': 1},
{'case_id': CASE_B, 'nik': NIK_B, 'nama': 'Budi',
 'first_branch': 'JKT', 'status': 'NONAKTIF',
 'first_seen_at': datetime(2026, 11, 22, 9, 30),
 'tkd_score': None, 'tkd_score_source': None,
 'tkd_score_note': None, 'tkd_passed': None},

# test_field_kasus_lengkap — ekspektasi baru
assert set(case) == {'case_id', 'nik_masked', 'nama', 'first_branch',
                     'status', 'branches', 'steps', 'tkd_score',
                     'tkd_score_source', 'tkd_score_note', 'tkd_passed'}
assert case['tkd_score'] is None and case['tkd_passed'] is None

def test_skor_tkd_ikut_di_level_kasus(app, db, logs):
    case = next(c for c in _get(app).get_json()['data']
                if c['case_id'] == CASE_A)
    assert case['tkd_score'] == 86.67
    assert case['tkd_score_source'] == 'AUTO'
    assert case['tkd_passed'] == 1
```

```python
# tests/test_recruitment_cases_score.py
import pytest
from flask import Flask
from modules import routes_recruitment as rr

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split())
        self.conn.statements.append((u, params))
        if u.startswith('SELECT ID, CASE_ID, STEP_TYPE, STATUS') and 'RECRUITMENT_STEPS' in u:
            self._rows = [{'id': 13, 'case_id': 'RC-1', 'step_type': 'TKD',
                           'status': 'PENDING', 'branch_code': 'SBY'}]
        elif 'FROM RECRUITMENT_CASES' in u:
            self._rows = [{'case_id': 'RC-1', 'first_branch': 'SBY'}]
        else:
            self._rows = []
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []; self.commits = 0
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): self.commits += 1
    def rollback(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'
    rr.register_recruitment_routes(a)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(rr, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rr, 'load_settings', lambda cur: {'pass_score': 70})
    return a

def _client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = 'traineer'; s['user_name'] = 'petugas'
    return c

def test_bukti_tkd_dengan_skor_menulis_manual(app, monkeypatch):
    called = {}
    def _fake(cur, cid, score, reason, actor, pass_score, branch_code=''):
        called.update(case_id=cid, score=score, reason=reason, actor=actor,
                      pass_score=pass_score, branch_code=branch_code)
        return {'score': score, 'passed': True, 'source': 'MANUAL',
                'branch_code': branch_code}
    monkeypatch.setattr(rr, 'set_manual_score', _fake)
    r = _client(app).post('/api/recruitment/steps/13/evidence',
                          json={'date': '2026-11-24', 'note': 'Tes manual',
                                'score': '80'})
    assert r.status_code == 200
    assert called == {'case_id': 'RC-1', 'score': 80.0, 'reason': 'Tes manual',
                      'actor': 'petugas', 'pass_score': 70,
                      'branch_code': 'SBY'}

@pytest.mark.parametrize('bad', ['101', 'abc', '-1'])
def test_bukti_tkd_skor_invalid_ditolak(app, monkeypatch, bad):
    called = []
    monkeypatch.setattr(rr, 'set_manual_score', lambda *a, **k: called.append(1))
    r = _client(app).post('/api/recruitment/steps/13/evidence',
                          json={'date': '2026-11-24', 'note': 'x', 'score': bad})
    assert r.status_code == 400
    assert called == []
```

- [ ] **Step 3: Jalankan tes, pastikan gagal**

Run: `python3 -m pytest tests/test_recruitment_portal_links.py tests/test_recruitment_cases_score.py -q`
Expected: FAIL.

- [ ] **Step 4: Implementasi**

`_portal_scope_branch(conn)`: salin pola `routes_cv_online._scope_branch` — admin + `is_ho_admin(conn)` → `None`; selain itu `session['branch_code']` uppercase atau `''`.

`portal-links`:
- `@role_required(['receptionist', 'traineer', 'ga_hr', 'admin'])` (jangan pakai `_STAFF_ROLES` yang tidak memuat receptionist).
- Query `branches` (`is_active=1 ORDER BY code`) dan `cv_online_branch_forms`.
- Untuk tiap cabang dalam scope: token aktif dan tidak kosong → `portal_path`; tanpa token → `portal_path=''`, `active=False`.
- Jangan sertakan field `form_token` terpisah; token hanya ada di `portal_path` (dibutuhkan QR).
- Audit `recruitment_portal_links_view` tanpa NIK.

`cases`:
- Tambahkan kolom ke SELECT (`c.tkd_score, c.tkd_score_source, c.tkd_score_note, c.tkd_passed`) dan ke dict respons.
- Tambahkan helper `_as_float(value)` di modul (`None` → `None`; `Decimal`/`int`/`str` → `float`); pakai untuk `tkd_score`; `tkd_passed` jadi `int`/`None`.
- Update `tests/test_recruitment_cases_api.py` `test_field_kasus_lengkap` agar memuat 4 kunci baru (sudah ditulis di Step 2).

`evidence`:
- Import di `modules/routes_recruitment.py`: `from modules.tkd_service import load_settings as tkd_load_settings, set_manual_score as tkd_set_manual_score` (nama unik agar mudah di-monkeypatch sebagai `rr.load_settings`/`rr.set_manual_score` — gunakan alias `load_settings` dan `set_manual_score` bila tidak bentrok).
- Ubah SELECT langkah menjadi `SELECT id, case_id, step_type, status, branch_code FROM recruitment_steps WHERE id=%s`.
- Setelah validasi `score`, bila `row['step_type'] == 'TKD'` dan `score` tidak kosong:
  - `value = float(score)` di dalam `try`; `ValueError` atau di luar 0–100 → 400 `'Skor TKD harus angka 0–100.'`.
  - `pass_score = tkd_load_settings(cursor)['pass_score']`.
  - `tkd_set_manual_score(cursor, row['case_id'], value, note or 'Bukti manual TKD', actor, pass_score, row.get('branch_code') or '')`.
  - Jangan menulis `status='SELESAI'` manual setelahnya; `set_manual_score` yang menentukan status dan menulis evidence TKD.
- Bila `score` kosong → perilaku lama (UPDATE status SELESAI + evidence manual).
- Audit `recruitment_step_evidence` tetap; tambahkan `score` numerik (`None` bila kosong).

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `python3 -m pytest tests/test_recruitment_portal_links.py tests/test_recruitment_cases_score.py tests/test_recruitment_cases_api.py tests/test_recruitment_evidence.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_recruitment.py tests/test_recruitment_portal_links.py tests/test_recruitment_cases_score.py tests/test_recruitment_cases_api.py
git commit -m "feat(recruitment): link portal per cabang dan skor TKD di kasus"
```

---

### Task 14: Frontend — route hub, menu tunggal, redirect lama, dan prop `embedded`

**Files:**
- Create: `frontend/src/views/RecruitmentHubView.vue`
- Create: `frontend/src/views/TkdView.vue` (stub sementara; Task 16 menggantinya)
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Modify: `frontend/src/views/dashboard/ReceptionistView.vue`
- Modify: `frontend/src/views/RecruitmentCasesView.vue`
- Modify: `frontend/src/views/CvOnlineView.vue`
- Modify: `frontend/src/views/FirstWorkView.vue`
- Test: `frontend/src/views/RecruitmentHubView.test.js`, `frontend/src/router/routes.test.js`, `frontend/src/layouts/AppLayout.test.js`

**Interfaces:**
- Consumes: `useAuthStore`, `useRealtimeStore` (`/api/nav/badges`), `api`.
- Produces: route `/recruitment` (name `recruitment`) dengan meta roles `['receptionist','traineer','finance','ga_hr','admin']`.
- Produces: tab `pelamar|kasus|cv|firstwork|tkd|tautan`; tab yang tidak diizinkan tidak dirender dan `?tab=` terlarang diarahkan ke tab pertama yang diizinkan.
- Produces: keempat view lama menerima prop `embedded: Boolean` (default `false`) dan menyembunyikan `PageHeader` bila `true`.

- [ ] **Step 1: Tulis tes hub & route yang gagal**

```js
// frontend/src/views/RecruitmentHubView.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import RecruitmentHubView from './RecruitmentHubView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer', user: { branch_code: 'SBY' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const STUBS = {
  ReceptionistView: true, RecruitmentCasesView: true, CvOnlineView: true,
  FirstWorkView: true, TkdView: true, RecruitmentLinksView: true,
}

async function mountAt(path, role = 'traineer', badges = {}) {
  authMock.role = role
  apiMock.mockResolvedValue({ badges })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/recruitment', name: 'recruitment',
               component: RecruitmentHubView }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(RecruitmentHubView, {
    global: { plugins: [router], stubs: STUBS },
  })
  await flushPromises()
  return w
}

describe('RecruitmentHubView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('traineer melihat enam tab dan tab terlarang diarahkan ke pelamar', async () => {
    const w = await mountAt('/recruitment?tab=tautan', 'traineer')
    const labels = w.findAll('[data-tab]').map((b) => b.text())
    expect(labels).toEqual(expect.arrayContaining(
      ['Pelamar', 'Kasus', 'CV Online', 'FirstWork', 'TKD', 'Tautan']))
    expect(w.find('[data-tab="tautan"]').attributes('data-active')).toBe('true')
  })

  it('receptionist hanya melihat Pelamar dan Tautan', async () => {
    const w = await mountAt('/recruitment?tab=tkd', 'receptionist')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['pelamar', 'tautan'])
    expect(w.find('[data-tab="pelamar"]').attributes('data-active')).toBe('true')
  })

  it('finance hanya melihat FirstWork', async () => {
    const w = await mountAt('/recruitment', 'finance')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['firstwork'])
  })

  it('badge antrean tampil di tab CV dan FirstWork', async () => {
    const w = await mountAt('/recruitment?tab=cv', 'admin',
      { cv_online_pending: 3, first_work_pending: 2 })
    expect(w.find('[data-tab="cv"]').text()).toContain('3')
    expect(w.find('[data-tab="firstwork"]').text()).toContain('2')
  })
})
```

```js
// tambahan frontend/src/router/routes.test.js
describe('hub rekrutmen', () => {
  it('/recruitment memakai gabungan peran staff rekrutmen', () => {
    const route = router.resolve('/recruitment')
    expect(route.name).toBe('recruitment')
    expect(route.meta.roles).toEqual(expect.arrayContaining(
      ['receptionist', 'traineer', 'finance', 'ga_hr', 'admin']))
  })

  it('rute lama tetap terdaftar dan mengarah ke tab yang tepat', () => {
    for (const [path, tab] of [['/receptionist', 'pelamar'],
      ['/recruitment-cases', 'kasus'], ['/cv-online', 'cv']]) {
      const r = router.resolve(path)
      expect(r.matched.length).toBeGreaterThan(0)
      const redirects = r.matched.map((m) => JSON.stringify(m.redirect || ''))
      expect(redirects.some((s) => s.includes(tab))).toBe(true)
    }
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/RecruitmentHubView.test.js src/router/routes.test.js`
Expected: FAIL karena route/view belum ada.

- [ ] **Step 3: Implementasi router**

- Tambah route di dalam layout: `{ path: 'recruitment', name: 'recruitment', component: () => import('../views/RecruitmentHubView.vue'), meta: { roles: ['receptionist','traineer','finance','ga_hr','admin'], title: 'Rekrutmen' } }`.
- Ganti `receptionist` menjadi redirect: `{ path: 'receptionist', redirect: { path: '/recruitment', query: { tab: 'pelamar' } }, meta: { roles: [...] } }`; `traineer` → `/recruitment?tab=pelamar`; `recruitment-cases` → `tab: 'kasus'`; `cv-online` → `tab: 'cv'`.
- `first-work` **tetap** route komponen (jangan redirect murni). Tambah di guard setelah blok `!auth.isAuthenticated`:
```js
if (to.name === 'first-work') {
  return { path: '/recruitment', query: { ...to.query, tab: 'firstwork' } }
}
```
- Guard `/first-work` tanpa login tetap ke `first-work-form` (perilaku lama).

- [ ] **Step 4: Implementasi `RecruitmentHubView.vue`**

- `TABS` berisi `{id,label,roles,component}`; komponen: `pelamar` → `ReceptionistView`, `kasus` → `RecruitmentCasesView`, `cv` → `CvOnlineView`, `firstwork` → `FirstWorkView`, `tkd` → `TkdView`, `tautan` → `RecruitmentLinksView`.
- `TkdView.vue` dibuat sebagai stub dulu:
```vue
<template>
  <div class="card" data-tkd-stub>Bank soal TKD segera tersedia.</div>
</template>
```
Task 16 mengganti stub ini dengan shell sub-tab.
- `availableTabs = TABS.filter(t => t.roles.includes(auth.role))`.
- `currentTab`: baca `route.query.tab`; bila tidak ada/tidak diizinkan → `availableTabs[0].id`. `watchEffect` memanggil `router.replace({ query: { ...route.query, tab: current } })` hanya bila berbeda.
- Render header "🪪 Rekrutmen", tab bar `<button data-tab="..." :data-active="currentTab === t.id ? 'true' : 'false'">`, dan `<component :is="activeComponent" embedded />`.
- Badge: `api('/api/nav/badges')` saat mount; tampilkan angka di tab `cv` (`cv_online_pending`) dan `firstwork` (`first_work_pending`).
- Gaya mengikuti `PageHeader`/`card`/`btn` yang ada; mobile: tab bar bisa di-scroll horizontal.

- [ ] **Step 5: Menu tunggal di `AppLayout.vue`**

Ganti tiga item grup "Rekrutmen & Trainee" menjadi satu:
```js
{ label: 'Rekrutmen', path: '/recruitment', icon: '🪪',
  roles: ['receptionist', 'traineer', 'finance', 'ga_hr', 'admin'],
  keywords: 'rekrutmen pelamar cv firstwork tkd trainee recruitment' }
```
Hapus `badge` dari item menu (badge pindah ke tab hub). Perbarui `frontend/src/layouts/AppLayout.test.js`:
- Baris yang mengharapkan `'Absensi FirstWork'` (dua tempat: admin & traineer) diganti menjadi tetap `'Rekrutmen'` dan tambahkan `expect(nav).not.toContain('Absensi FirstWork')`.
- Tes badge: hapus assertion `Absensi FirstWork` (badge FirstWork/CV pindah ke tab hub); pertahankan assertion badge `Dashboard GA`.
- Tambahkan `{ path: '/recruitment', component: Blank }` ke `makeRouter()` agar `router-link` aktif tidak memicu warning.
- `'Registrasi CV Online'` tidak boleh lagi muncul sebagai item menu terpisah.

- [ ] **Step 6: Tambah prop `embedded` ke empat view lama**

Di setiap file (`ReceptionistView.vue`, `RecruitmentCasesView.vue`, `CvOnlineView.vue`, `FirstWorkView.vue`):
```js
defineProps({ embedded: { type: Boolean, default: false } })
```
Bungkus `PageHeader` dengan `v-if="!embedded"` (termasuk slot aksi). Jangan mengubah root class/padding agar route lama tetap sama.

- [ ] **Step 7: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/views/RecruitmentHubView.test.js src/router/routes.test.js src/layouts/AppLayout.test.js src/views/RecruitmentCasesView.test.js`
Expected: PASS (setelah menyesuaikan ekspektasi menu lama).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/RecruitmentHubView.vue frontend/src/views/RecruitmentHubView.test.js \
  frontend/src/router/index.js frontend/src/router/routes.test.js \
  frontend/src/layouts/AppLayout.vue frontend/src/layouts/AppLayout.test.js \
  frontend/src/views/dashboard/ReceptionistView.vue frontend/src/views/RecruitmentCasesView.vue \
  frontend/src/views/CvOnlineView.vue frontend/src/views/FirstWorkView.vue
git commit -m "feat(recruitment): satu menu dan route hub bertab"
```

---

### Task 15: Portal publik — kartu TKD dan alur ujian

**Files:**
- Create: `frontend/src/components/RecruitmentTkdPanel.vue`
- Modify: `frontend/src/views/RecruitmentPortalView.vue`
- Test: `frontend/src/components/RecruitmentTkdPanel.test.js`, `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: `api`; `POST /api/recruitment/tkd/status`, `/start`, `GET /attempts/<id>`, `PUT /attempts/<id>/answers/<pos>`, `POST /attempts/<id>/submit`, `GET /attempts/<id>/result`.
- Produces: `RecruitmentTkdPanel` props `{ token: String, nik: String, dob: String }`, emits `close`.
- Produces: kartu TKD di portal menjadi tombol yang membuka panel; kartu `TRAINING` tetap "Segera tersedia".

- [ ] **Step 1: Tulis tes panel yang gagal**

```js
// frontend/src/components/RecruitmentTkdPanel.test.js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentTkdPanel from './RecruitmentTkdPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const PROPS = { token: 'tok', nik: '3573010101990001', dob: '1999-01-01' }
const BELUM = { status: 'success', data: {
  state: 'BELUM', official_score: null, score_source: null, attempts_used: 0,
  max_attempts: 2, active_attempt: null, can_start: true, pass_score: 70,
  question_count: 20, duration_minutes: 25, bank_ready: true } }

async function mountPanel(status = BELUM) {
  apiMock.mockResolvedValueOnce(status)
  const w = mount(RecruitmentTkdPanel, { props: PROPS })
  await flushPromises()
  return w
}

describe('RecruitmentTkdPanel', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('status BELUM menampilkan aturan dan pilihan modal', async () => {
    const w = await mountPanel()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/status', {
      method: 'POST', body: { nik: PROPS.nik, dob: PROPS.dob, token: PROPS.token } })
    const text = w.text()
    expect(text).toContain('20 soal')
    expect(text).toContain('25 menit')
    expect(text).toContain('lulus 70')
    expect(text).toContain('2 kesempatan')
    for (const tier of ['30.000', '50.000', '100.000']) expect(text).toContain(tier)
  })

  it('LULUS menampilkan skor resmi dan tidak menawarkan mulai', async () => {
    const w = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'LULUS', official_score: 86.67, can_start: false } })
    expect(w.text()).toContain('86,67')
    expect(w.text()).toContain('Lulus')
    expect(w.find('[data-action="start"]').exists()).toBe(false)
  })

  it('HABIS dan DIKECUALIKAN menampilkan pesan tanpa tombol mulai', async () => {
    const habis = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'HABIS', official_score: 60, can_start: false } })
    expect(habis.text()).toContain('Kesempatan habis')

    const exc = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'DIKECUALIKAN', can_start: false } })
    expect(exc.text()).toContain('Dikecualikan')
    expect(exc.find('[data-action="start"]').exists()).toBe(false)
  })

  it('mulai mengirim tier dan menampilkan soal tanpa kunci', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', attempt_no: 1, modal_tier: '30k',
      expires_at: new Date(Date.now() + 1500000).toISOString(),
      remaining_seconds: 1500, duration_minutes: 25,
      questions: [{ position: 1, type: 'MCQ', category: 'REGULASI', prompt: 'Pertanyaan 1',
                    options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }],
      answers: {} } })
    await w.find('select[data-tier]').setValue('30k')
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/start', {
      method: 'POST', body: { nik: PROPS.nik, dob: PROPS.dob, token: PROPS.token, modal_tier: '30k' } })
    expect(w.text()).toContain('Pertanyaan 1')
    expect(w.text()).not.toContain('kunci')
  })

  it('memilih jawaban menyimpan otomatis dan submit menampilkan skor', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', attempt_no: 1, modal_tier: '30k',
      expires_at: new Date(Date.now() + 1500000).toISOString(), remaining_seconds: 1500,
      duration_minutes: 25,
      questions: [{ position: 1, type: 'MCQ', category: 'REGULASI', prompt: 'P',
                    options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }], answers: {} } })
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()
    apiMock.mockResolvedValueOnce({ status: 'success' })
    await w.find('input[value="b"]').setValue(true)
    vi.advanceTimersByTime(600)
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/attempts/TKD-1/answers/1', {
      method: 'PUT', body: { answer: { option: 'b' } } })

    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', score: 85, passed: true, official_score: 85,
      best_score: 85, attempts_used: 1, max_attempts: 2, state: 'LULUS' } })
    await w.find('[data-action="submit"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('85')
    expect(w.text()).toContain('Lulus')
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/components/RecruitmentTkdPanel.test.js`
Expected: FAIL karena komponen belum ada.

- [ ] **Step 3: Implementasi `RecruitmentTkdPanel.vue`**

State mesin: `loading`, `error`, `status` (data status), `mode` (`intro|exam|result`), `attempt`, `questions`, `index`, `answers` (reactive object), `tier` (`30k`), `saving`, `submitting`, `result`, `now`.

Alur:
1. `onMounted` → `loadStatus()`: POST status; isi `status`; bila `state === 'BERLANGSUNG'` siapkan tombol "Lanjutkan".
2. `start()`: POST start dengan `modal_tier: tier`; bila sukses → `enterExam(data)`; bila 409 → `loadStatus()` dan tampilkan `msg`.
3. `resume()`: GET attempt id dari `status.active_attempt.id`; bila `finished` → tampilkan hasil; selain itu `enterExam`.
4. `enterExam(data)`: simpan `attempt`, `questions`, `answers` (dari `data.answers`), `index=0`, `mode='exam'`; mulai interval 1 detik untuk `now`; hitung `remaining` dari `expires_at`; bila 0 → `submit()`.
5. `answerOf(q)` / `setAnswer(q, value)`: MCQ `{option}`; NUMERIC angka/string; SHORT/PROFILE `{text}`; simpan ke `answers`; debounce 500 ms → PUT; tampilkan "Menyimpan…"/"Tersimpan".
6. Navigasi `prev`/`next`; soal terakhir menampilkan tombol "Selesai".
7. `submit()`: POST submit; `mode='result'`; `result` = data; hentikan timer.
8. `retry()`: `mode='intro'`; `loadStatus()`.
9. Tombol tutup memanggil `emit('close')`.
10. Semua teks Indonesia; angka skor diformat `toLocaleString('id-ID', {maximumFractionDigits:2})`.

Tampilan:
- `intro`: kartu aturan (jumlah soal, durasi, ambang, kesempatan, "tidak ada kunci/pembahasan"), `select[data-tier]` dengan label `$30.000/$50.000/$100.000`, tombol `data-action="start"` atau "Lanjutkan".
- `exam`: header "Soal X dari N" + timer `mm:ss`, progress bar, prompt, opsi (radio untuk MCQ, input number untuk NUMERIC, input/textarea untuk teks), tombol Sebelumnya/Berikutnya/Selesai.
- `result`: skor percobaan, skor resmi, lulus/tidak, sisa kesempatan, tombol "Coba lagi" bila `status.can_start` (setelah reload status) atau pesan "Hubungi Traineer cabang."

- [ ] **Step 4: Sambungkan ke `RecruitmentPortalView.vue`**

- Ubah `STEPS` TKD: `future: false`, `action: 'tkd'`; teks "Buka tes →" saat terbuka.
- State `tkdOpen = ref(false)`, `tkdNik = ref('')`, `tkdDob = ref('')`.
- Saat `check()` sukses `known=true`, simpan NIK/DOB ke `tkdNik`/`tkdDob`.
- Kartu TKD dirender sebagai `<button>` (bukan `<a>`) saat `known`; `@click="tkdOpen = true"`.
- Di bawah form/kartu: `<RecruitmentTkdPanel v-if="tkdOpen" :token="branchToken" :nik="tkdNik" :dob="tkdDob" @close="tkdOpen = false" />`.
- Kartu TKD yang belum dikenal tetap terkunci dengan hint "lengkapi CV Online dulu".
- Perbarui tes portal: TKD tidak lagi "Segera tersedia"; klik kartu TKD memanggil status; `TRAINING` tetap "Segera tersedia".

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/components/RecruitmentTkdPanel.test.js src/views/RecruitmentPortalView.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RecruitmentTkdPanel.vue frontend/src/components/RecruitmentTkdPanel.test.js \
  frontend/src/views/RecruitmentPortalView.vue frontend/src/views/RecruitmentPortalView.test.js
git commit -m "feat(tkd): ujian online di portal pelamar"
```

---

### Task 16: Staff UI — shell TKD dan Bank Soal

**Files:**
- Create: `frontend/src/views/TkdView.vue`
- Create: `frontend/src/views/TkdBankPanel.vue`
- Test: `frontend/src/views/TkdBankPanel.test.js`

**Interfaces:**
- Consumes: `api`; endpoint Task 10–11.
- Produces: `TkdView` sub-tab `bank|hasil|pengaturan` (default `bank`), menerima prop `embedded`.
- Produces: `TkdBankPanel` tanpa prop; mengelola daftar soal, form tambah/edit, preview, toggle, impor, ekspor.

- [ ] **Step 1: Tulis tes bank panel yang gagal**

```js
// frontend/src/views/TkdBankPanel.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdBankPanel from './TkdBankPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const QUESTIONS = [
  { id: 1, code: 'REG-01', category: 'REGULASI', type: 'MCQ',
    prompt: 'Pengawas PBK', options: [{ id: 'a', text: 'Bappebti' }],
    answer: { option: 'a' }, points: 1, modal_tier: null, active: 1 },
  { id: 2, code: 'HIT-30-01', category: 'HITUNG', type: 'NUMERIC',
    prompt: 'Laba Ibu Dian', options: [], answer: { value: 56400.3, tolerance: 1 },
    points: 1, modal_tier: '30k', active: 0 },
]

async function mountPanel() {
  apiMock.mockResolvedValue({ data: QUESTIONS })
  const w = mount(TkdBankPanel)
  await flushPromises()
  return w
}

describe('TkdBankPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('memuat dan menampilkan soal beserta status', async () => {
    const w = await mountPanel()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/questions', { params: {} })
    const text = w.text()
    expect(text).toContain('REG-01')
    expect(text).toContain('HIT-30-01')
    expect(text).toContain('Aktif')
  })

  it('filter kategori dikirim ke API', async () => {
    const w = await mountPanel()
    await w.find('select[data-filter="category"]').setValue('HITUNG')
    await w.find('button[data-action="apply"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/questions',
      { params: { category: 'HITUNG' } })
  })

  it('form tambah memvalidasi kunci MCQ sebelum POST', async () => {
    const w = await mountPanel()
    await w.find('button[data-action="new"]').trigger('click')
    await w.find('input[data-field="code"]').setValue('NEW-1')
    await w.find('select[data-field="category"]').setValue('PRODUK')
    await w.find('select[data-field="type"]').setValue('MCQ')
    await w.find('textarea[data-field="prompt"]').setValue('Pertanyaan')
    await w.find('input[data-field="option_a"]').setValue('A')
    await w.find('input[data-field="option_b"]').setValue('B')
    await w.find('button[data-action="save"]').trigger('click')
    expect(w.text()).toContain('Kunci jawaban wajib dipilih')
    expect(apiMock).not.toHaveBeenCalledWith('/api/recruitment/tkd/questions',
      expect.objectContaining({ method: 'POST' }))
  })

  it('toggle memanggil endpoint dan memuat ulang', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success' })
    apiMock.mockResolvedValueOnce({ data: QUESTIONS })
    await w.find('button[data-toggle="1"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/questions/1/toggle', { method: 'POST' })
  })

  it('preview menampilkan kunci khusus staff', async () => {
    const w = await mountPanel()
    await w.find('button[data-preview="1"]').trigger('click')
    expect(w.text()).toContain('Kunci')
    expect(w.text()).toContain('Bappebti')
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/TkdBankPanel.test.js`
Expected: FAIL.

- [ ] **Step 3: Implementasi `TkdBankPanel.vue`**

- Filter bar: kategori (`''`, REGULASI, PERUSAHAAN, PRODUK, HITUNG, PROFIL), status (`''`, aktif, draft), cari; tombol Terapkan/Reset.
- Tabel: kode, kategori, tipe, cuplikan prompt, tier, poin, status badge, aksi (Preview, Edit, Aktifkan/Nonaktifkan).
- Modal form: kategori, tipe, prompt, opsi A–E (hanya MCQ), kunci (radio/select untuk MCQ; input angka + toleransi untuk NUMERIC; input alias `|` untuk SHORT_TEXT), poin, modal tier (hanya HITUNG), aktif.
- Validasi klien: kode/prompt wajib; MCQ minimal 2 opsi dan kunci dipilih; NUMERIC kunci angka; SHORT_TEXT minimal satu alias; PROFILE_TEXT poin 0. Tampilkan error di form, jangan POST.
- Simpan: POST/PUT; sukses → tutup modal, muat ulang, pesan.
- Preview: modal menampilkan prompt/opsi seperti pelamar + blok "Kunci (khusus staff)" berisi `answer` dan poin.
- Impor: input file `.csv`; baca `file.text()`; POST JSON `{csv, update_drafts}`; tampilkan `inserted/updated/skipped/errors`.
- Ekspor: `<a href="/api/recruitment/tkd/questions/export.csv">⬇️ Ekspor CSV</a>`.

- [ ] **Step 4: Implementasi `TkdView.vue`**

- Ganti stub dari Task 14 dengan sub-tab `bank`, `hasil`, `pengaturan`; label Indonesia.
- `<component :is="activePanel" />`: `bank` → `TkdBankPanel`; `hasil` dan `pengaturan` sementara merender `<p>Segera tersedia.</p>` (Task 17/18 menggantinya dengan panel asli).
- `embedded` prop hanya untuk konsistensi; tidak merender `PageHeader` karena hub sudah punya header.

- [ ] **Step 5: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/views/TkdBankPanel.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/TkdView.vue frontend/src/views/TkdBankPanel.vue \
  frontend/src/views/TkdBankPanel.test.js
git commit -m "feat(tkd): tab bank soal staff"
```

---

### Task 17: Staff UI — Hasil dan koreksi skor

**Files:**
- Create: `frontend/src/views/TkdResultsPanel.vue`
- Test: `frontend/src/views/TkdResultsPanel.test.js`

**Interfaces:**
- Consumes: `GET /api/recruitment/tkd/attempts`, `GET /review/<id>`, `POST /score`, `GET /api/recruitment/cases?nik=`.
- Produces: tabel hasil, modal detail, modal koreksi, dan pencarian kasus untuk skor manual.

- [ ] **Step 1: Tulis tes yang gagal**

```js
// frontend/src/views/TkdResultsPanel.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdResultsPanel from './TkdResultsPanel.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const ROWS = [{ id: 'TKD-1', case_id: 'RC-1', nama: 'Andi', nik_masked: '****0001',
  branch_code: 'SBY', attempt_no: 1, status: 'SELESAI', score: 60, passed: 0,
  started_at: '2026-11-24 10:00:00', submitted_at: '2026-11-24 10:20:00',
  score_source: 'AUTO' }]

async function mountPanel() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/recruitment/tkd/attempts') return Promise.resolve({ data: ROWS })
    if (path === '/api/recruitment/tkd/review/TKD-1') return Promise.resolve({ data: {
      attempt: { id: 'TKD-1', modal_tier: '30k', score: 60 },
      case: { nama: 'Andi', tkd_score: 60, tkd_score_source: 'AUTO' },
      items: [{ position: 1, snapshot: { prompt: 'P', answer: { option: 'a' }, points: 1 },
                answer: { option: 'b' }, is_correct: 0, points_awarded: 0 }] } })
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(TkdResultsPanel)
  await flushPromises()
  return w
}

describe('TkdResultsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan NIK termasker dan skor', async () => {
    const w = await mountPanel()
    expect(w.text()).toContain('****0001')
    expect(w.text()).toContain('60')
    expect(w.text()).not.toContain('3573010101990001')
  })

  it('detail menampilkan jawaban, kunci, dan poin', async () => {
    const w = await mountPanel()
    await w.find('button[data-review="TKD-1"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Kunci')
    expect(w.text()).toContain('Poin')
  })

  it('koreksi mewajibkan alasan dan mengirim skor', async () => {
    const w = await mountPanel()
    await w.find('button[data-score="RC-1"]').trigger('click')
    await w.find('input[data-field="score"]').setValue('75')
    await w.find('button[data-action="save-score"]').trigger('click')
    expect(w.text()).toContain('Alasan wajib')
    expect(apiMock).not.toHaveBeenCalledWith('/api/recruitment/tkd/score',
      expect.objectContaining({ method: 'POST' }))

    await w.find('textarea[data-field="reason"]').setValue('Koreksi hasil')
    await w.find('button[data-action="save-score"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/score', {
      method: 'POST', body: { case_id: 'RC-1', score: 75, reason: 'Koreksi hasil' } })
  })

  it('koreksi tanpa attempt mencari kasus lewat NIK', async () => {
    const w = await mountPanel()
    await w.find('button[data-action="manual-search"]').trigger('click')
    await w.find('input[data-field="nik"]').setValue('3573010101990001')
    apiMock.mockResolvedValueOnce({ data: [{ case_id: 'RC-9', nama: 'Budi', nik_masked: '****0009' }] })
    await w.find('button[data-action="do-search"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Budi')
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/TkdResultsPanel.test.js`
Expected: FAIL.

- [ ] **Step 3: Implementasi**

- Filter: cabang (isi dari `auth.user.branch_code`; admin bisa kosong), status, dari/sampai tanggal, cari nama/NIK; tombol Terapkan.
- Tabel: nama, NIK termasker, cabang, attempt ke-, status, skor, lulus, mulai/selesai, sumber (`AUTO`/`MANUAL`), aksi Detail + Koreksi.
- Detail: modal `Modal.vue`; daftar item dengan prompt, jawaban pelamar, kunci, benar/salah, poin; tampilkan jawaban `PROFILE_TEXT` terakhir; tier modal.
- Koreksi: modal skor + alasan; validasi 0–100 dan alasan wajib; POST `/api/recruitment/tkd/score`; sukses → tutup, muat ulang.
- "Koreksi tanpa attempt": modal cari NIK (16 digit) → `GET /api/recruitment/cases?nik=` → pilih kasus → isi skor + alasan → POST.
- Jangan pernah merender NIK penuh dari respons; input NIK hanya untuk query dan tidak disimpan setelah pencarian.
- Ubah `TkdView.vue`: sub-tab `hasil` memakai `TkdResultsPanel` (ganti placeholder `Segera tersedia`).

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/views/TkdResultsPanel.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TkdResultsPanel.vue frontend/src/views/TkdResultsPanel.test.js frontend/src/views/TkdView.vue
git commit -m "feat(tkd): tab hasil, detail, dan koreksi skor"
```

---

### Task 18: Staff UI — Pengaturan dan indikator kesiapan

**Files:**
- Create: `frontend/src/views/TkdSettingsPanel.vue`
- Test: `frontend/src/views/TkdSettingsPanel.test.js`

**Interfaces:**
- Consumes: `GET/PUT /api/recruitment/tkd/settings`; `useAuthStore`.
- Produces: form pengaturan; `max_attempts` selalu 2 dan tidak bisa diubah; non-admin read-only.

- [ ] **Step 1: Tulis tes yang gagal**

```js
// frontend/src/views/TkdSettingsPanel.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdSettingsPanel from './TkdSettingsPanel.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const SETTINGS = { question_count: 20, duration_minutes: 25, pass_score: 70,
  max_attempts: 2, quota: { REGULASI: 7, PERUSAHAAN: 4, PRODUK: 6, HITUNG: 3 },
  shuffle_options: 1, active: 0,
  readiness: { ready: true, active_valued: 30, quota_ok: {}, tier_ok: {}, reasons: [] } }

async function mountPanel(role = 'traineer') {
  authMock.role = role
  apiMock.mockResolvedValue({ data: SETTINGS })
  const w = mount(TkdSettingsPanel)
  await flushPromises()
  return w
}

describe('TkdSettingsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan angka dan kesiapan bank', async () => {
    const w = await mountPanel('admin')
    expect(w.text()).toContain('30')
    expect(w.find('input[data-field="max_attempts"]').element.disabled).toBe(true)
  })

  it('traineer tidak bisa menyimpan pengaturan', async () => {
    const w = await mountPanel('traineer')
    expect(w.find('button[data-action="save"]').element.disabled).toBe(true)
    expect(w.text()).toContain('Hanya admin')
  })

  it('admin menyimpan kuota dan status aktif', async () => {
    const w = await mountPanel('admin')
    await w.find('input[data-field="question_count"]').setValue('20')
    await w.find('button[data-action="save"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/settings', {
      method: 'PUT',
      body: expect.objectContaining({ question_count: 20, max_attempts: 2 }),
    })
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/TkdSettingsPanel.test.js`
Expected: FAIL.

- [ ] **Step 3: Implementasi**

- Muat settings; tampilkan jumlah soal, durasi, ambang lulus, kuota 4 kategori, acak opsi, aktif.
- `max_attempts` input `disabled` dengan nilai 2 dan catatan "Tetap 2 pada rilis ini".
- Indikator kesiapan: `Soal aktif: 30/20 · REGULASI 8/7 · PERUSAHAAN 5/4 · PRODUK 7/6 · HITUNG 10/3 · tiap tier ≥3`; bila `ready=false`, tampilkan `reasons`.
- Tombol Simpan hanya aktif untuk `auth.role === 'admin'`; selain itu disabled + teks "Hanya admin dapat mengubah pengaturan."
- Simpan: PUT body berisi semua field; sukses → muat ulang + pesan.
- Ubah `TkdView.vue`: sub-tab `pengaturan` memakai `TkdSettingsPanel` (ganti placeholder `Segera tersedia`).
- Perbarui commit Task ini untuk menyertakan `frontend/src/views/TkdView.vue`.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/views/TkdSettingsPanel.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TkdSettingsPanel.vue frontend/src/views/TkdSettingsPanel.test.js frontend/src/views/TkdView.vue
git commit -m "feat(tkd): pengaturan dan kesiapan bank soal"
```

---

### Task 19: Staff UI — Tab Tautan (satu link portal + QR)

**Files:**
- Create: `frontend/src/views/RecruitmentLinksView.vue`
- Test: `frontend/src/views/RecruitmentLinksView.test.js`

**Interfaces:**
- Consumes: `GET /api/recruitment/portal-links`; `qrcode` (sudah ada); `Modal.vue`.
- Produces: satu kartu per cabang berisi URL portal, tombol Salin tautan, QR, Cetak QR.

- [ ] **Step 1: Tulis tes yang gagal**

```js
// frontend/src/views/RecruitmentLinksView.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentLinksView from './RecruitmentLinksView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,x')) } }))

const LINKS = { data: [
  { branch_code: 'SBY', branch_name: 'Surabaya',
    portal_path: '/app/recruitment-portal?token=tok-sby', active: true },
  { branch_code: 'MLG', branch_name: 'Malang',
    portal_path: '/app/recruitment-portal?token=tok-mlg', active: true },
] }

async function mountView() {
  apiMock.mockResolvedValue(LINKS)
  const w = mount(RecruitmentLinksView)
  await flushPromises()
  return w
}

describe('RecruitmentLinksView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan satu link portal per cabang', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Surabaya')
    expect(w.text()).toContain('Malang')
    expect(w.findAll('[data-portal-link]')).toHaveLength(2)
    expect(w.text()).toContain('/app/recruitment-portal?token=tok-sby')
  })

  it('tidak menampilkan tombol salin link CV atau FirstWork', async () => {
    const w = await mountView()
    const text = w.text()
    expect(text).not.toContain('cv-online-form')
    expect(text).not.toContain('first-work-form')
    expect(text).not.toContain('Salin Link CV')
    expect(text).not.toContain('Salin Link FirstWork')
  })

  it('menyalin URL absolut ke clipboard', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const w = await mountView()
    await w.find('button[data-copy="SBY"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(
      window.location.origin + '/app/recruitment-portal?token=tok-sby')
  })

  it('QR dibuat lokal dan modal menampilkan URL', async () => {
    const w = await mountView()
    await w.find('button[data-qr="SBY"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('QR Portal Rekrutmen SBY')
  })
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/RecruitmentLinksView.test.js`
Expected: FAIL.

- [ ] **Step 3: Implementasi**

- Muat `/api/recruitment/portal-links`; kartu per cabang dengan nama/kode, `portal_path` (absolut = `window.location.origin + portal_path`), status aktif.
- Tombol "🔗 Salin tautan" (`navigator.clipboard.writeText`), "▦ QR", "🖨️ Cetak QR".
- QR memakai `QRCode.toDataURL(url, { width: 420, margin: 2 })`; modal `Modal.vue`; cetak memakai `window.open` + HTML sederhana seperti `FirstWorkView.showQr`.
- Teks penjelas: "Bagikan satu tautan ini; pelamar memilih CV, FirstWork, atau TKD dari portal."
- Cabang tanpa token → tampilkan "Belum ada token; hubungi Admin." dan nonaktifkan tombol.
- Tidak ada tombol/link ke `cv-online-form` atau `first-work-form`.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `cd frontend && npx vitest run src/views/RecruitmentLinksView.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentLinksView.vue frontend/src/views/RecruitmentLinksView.test.js
git commit -m "feat(recruitment): tab tautan dengan satu portal dan QR per cabang"
```

---

### Task 20: Rilis — versi, dokumentasi, dan verifikasi penuh

**Files:**
- Modify: `modules/company_identity.py`, `modules/pdf_generator.py`, `frontend/src/stores/identity.js`, `frontend/public/sw.js`, `CHANGELOG.md`, `docs/internal/USER_LIST.md`, `guides/USER_GUIDE.md`
- Modify: `docs/internal/PROGRESS.md`
- Test: seluruh suite

**Interfaces:**
- Consumes: `scripts/sync_version_stamp.py`, `scripts/check_version_stamps.py --with-db`.
- Produces: versi rilis baru (naik dari `v2.133.1`, mis. `v2.134.0`) konsisten di 7 titik + DB.

- [ ] **Step 1: Jalankan seluruh tes backend**

Run: `python3 -m pytest -q`
Expected: PASS. Bila ada kegagalan yang tidak terkait TKD, catat dan perbaiki hanya yang disebabkan perubahan ini.

- [ ] **Step 2: Jalankan seluruh tes frontend**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 3: Bump versi 7 titik + DB**

- Ubah `IDENTITY_DEFAULTS['system_version']` di `modules/company_identity.py` ke versi baru.
- Ikuti `scripts/check_version_stamps.py` untuk 6 titik lain (PDF, identity.js, sw.js CACHE, CHANGELOG heading, USER_LIST, USER_GUIDE).
- Jalankan `python3 scripts/sync_version_stamp.py` di container/host untuk DB master + branches.
- Verifikasi: `python3 scripts/check_version_stamps.py --with-db` → exit 0.

- [ ] **Step 4: Dokumentasi rilis**

- `CHANGELOG.md`: entri teratas `## vX.Y.Z` berisi hub rekrutmen, TKD online, 2 percobaan, skor resmi, seed draft.
- `docs/internal/PROGRESS.md`: perbarui header versi + bagian rilis baru (tanggal 24 Nov 2026) berisi langkah deploy: build, migrasi otomatis, `seed_tkd_bank.py`, aktifkan soal, aktifkan settings, pilot 1 cabang.
- Catat bahwa `tkd_settings.active=0` saat deploy dan bank harus di-review sebelum diaktifkan.

- [ ] **Step 5: Build & smoke test**

Run: `cd frontend && npm run build` lalu `docker compose build web` (di NAS).
Smoke test manual viewport 375px:
1. Buka portal dengan token SBY → NIK+DOB → kartu TKD → mulai → jawab → tutup → buka lagi → lanjut → submit → skor tampil.
2. Buka portal lagi dengan NIK+DOB → skor resmi terlihat.
3. Dua percobaan → skor resmi = tertinggi.
4. Koreksi skor oleh Traineer → pelamar melihat skor koreksi.
5. Tab Tautan menampilkan satu link per cabang; QR terbaca.

- [ ] **Step 6: Commit rilis**

```bash
git add -A
git commit -m "release: vX.Y.Z hub rekrutmen dan TKD online"
```

---

## Catatan Implementasi

- **Ambigu spesifikasi yang diselesaikan di plan ini:** kesiapan "tiap tier ≥3 soal HITUNG" dihitung sebagai pool per tier = soal umum (`modal_tier NULL`) + soal tier tersebut, sehingga 4 umum + 2 tier = 6 ≥ 3. Ini konsisten dengan §4.2 (3 tier × 2 soal) dan sampling yang hanya memunculkan tier terpilih.
- **`max_attempts`** disimpan di DB tetapi divalidasi harus 2; UI menampilkannya read-only.
- **Bukti manual TKD** tanpa skor tetap `SELESAI` seperti perilaku lama; dengan skor menjadi `MANUAL` dan status mengikuti ambang lulus.
- **Attempt kedaluwarsa** difinalisasi lazy; tidak ada cron/worker baru.
- **CSRF** hanya dikecualikan untuk path publik TKD; endpoint staff tetap terlindungi.
