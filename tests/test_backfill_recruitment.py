"""Rilis B Task 5 — backfill kasus FirstWork lama tanpa mengubah sumber.

Regresi yang dijaga:
1. Dua baris `first_work_submissions` lama -> dua kasus + dua langkah
   FIRSTWORK SELESAI ber-source `sheet_legacy` (evidence_id = id submission).
2. Dijalankan ulang -> nol baris baru dan evidence/completed_at tidak berubah.
3. Hash ringkasan `first_work_submissions` + `cv_online_submissions`
   identik sebelum/sesudah backfill (sumber benar-benar read-only).
4. Dry-run default tidak menulis; `--commit` yang menulis.
5. Satu NIK = satu kasus walaupun dua cabang; langkah yang sudah ada dari
   form/CV Online tidak ditimpa; NIK invalid tidak dibuatkan kasus.
6. Transaksi per NIK: kegagalan satu NIK di-rollback, NIK lain tetap masuk.
7. Log/report hanya menampilkan 4 digit terakhir NIK.

Koneksi/cursor palsu meniru SQL produksi (tanpa MySQL), mengikuti pola
tests/test_import_unitedw.py dan tests/test_recruitment_service.py.
"""
import copy
import hashlib
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import backfill_recruitment_cases as bf  # noqa: E402

NIK_A = '3579013103950005'
NIK_B = '3507253006060003'
NIK_C = '3171011504991001'
NIK_INVALID = '123456789012345'


def _legacy(row_id, nik, branch='SBY', name='BUDI SANTOSO', source='sheet',
            registration_no=None, dob=None):
    return {
        'id': row_id,
        'nik': nik,
        'nik_raw': nik,
        'nama': name,
        'tanggal_lahir': dob,
        'branch_code': branch,
        'registration_no': registration_no or f'FW-20251007-{row_id:04d}',
        'source': source,
    }


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    @property
    def lastrowid(self):
        return self.conn.lastrowid

    def execute(self, sql, params=None):
        q = ' '.join(str(sql).upper().split())
        params = tuple(params or ())
        self.conn.statements.append(q)
        if self.conn.fail_on and self.conn.fail_on in q:
            raise RuntimeError(f'gagal sengaja: {self.conn.fail_on}')

        if q.startswith('SELECT'):
            self.rows = self._select(q, params)
            return
        if q.startswith('INSERT INTO'):
            self._insert(q, params)
            return
        if q.startswith('UPDATE'):
            self._update(q, params)
            return
        self.rows = []

    def _select(self, q, params):
        match = re.search(r'FROM\s+(\w+)', q)
        table = match.group(1).lower() if match else ''
        rows = self.conn.tables.get(table, [])
        if (table == 'first_work_submissions'
                and ('SOURCE<>%S' in q or 'SOURCE <> %S' in q) and params):
            rows = [r for r in rows if r.get('source') != params[0]]
        elif 'NIK=%S' in q and params:
            rows = [r for r in rows if str(r.get('nik')) == str(params[0])]
        elif 'CASE_ID=%S' in q and params:
            rows = [r for r in rows if str(r.get('case_id')) == str(params[0])]
        elif 'STEP_TYPE=%S' in q and params:
            rows = [r for r in rows if r.get('step_type') == params[0]]
        return [dict(r) for r in rows]

    def _insert(self, q, params):
        match = re.match(r'INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES', q)
        assert match, q
        table = match.group(1).lower()
        columns = [c.strip().lower() for c in match.group(2).split(',')]
        values = dict(zip(columns, params[:len(columns)]))
        unique = {
            'recruitment_cases': ('nik',),
            'recruitment_steps': ('case_id', 'step_type', 'branch_code'),
            'case_branch_history': ('case_id', 'branch_code'),
        }.get(table)
        rows = self.conn.tables[table]
        existing = next((r for r in rows if unique and all(
            r.get(k) == values.get(k) for k in unique)), None)
        if existing and 'ON DUPLICATE KEY UPDATE' in q:
            existing.update(values)
        else:
            rows.append(values)
            self.conn.lastrowid = len(rows)

    def _update(self, q, params):
        match = re.match(r'UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(\w+)=%S', q)
        assert match, q
        table, sets, key = match.groups()
        table, key = table.lower(), key.lower()
        assignments = [s.strip().split('=')[0].lower() for s in sets.split(',')]
        changes = dict(zip(assignments, params[:-1]))
        for row in self.conn.tables[table]:
            if str(row.get(key)) == str(params[-1]):
                row.update(changes)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.tables = {
            'first_work_submissions': [], 'cv_online_submissions': [],
            'recruitment_cases': [], 'recruitment_steps': [],
            'case_branch_history': [],
        }
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.lastrowid = 0
        self.fail_on = ''
        self._saved = copy.deepcopy(self.tables)

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1
        self._saved = copy.deepcopy(self.tables)

    def rollback(self):
        self.rollbacks += 1
        self.tables = copy.deepcopy(self._saved)

    def close(self):
        pass


def _db(*legacy_rows, cv_rows=()):
    db = _FakeConn()
    db.tables['first_work_submissions'] = list(legacy_rows)
    db.tables['cv_online_submissions'] = list(cv_rows)
    db._saved = copy.deepcopy(db.tables)
    return db


def _step(db, nik, branch='SBY'):
    case = next(c for c in db.tables['recruitment_cases'] if c['nik'] == nik)
    return next(s for s in db.tables['recruitment_steps']
                if s['case_id'] == case['case_id']
                and s['step_type'] == 'FIRSTWORK'
                and s['branch_code'] == branch)


def _digest(db):
    """Hash deterministik dari seluruh isi dua tabel sumber."""
    payload = {name: db.tables[name] for name in
               ('first_work_submissions', 'cv_online_submissions')}
    blob = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()


EXPECTED_KEYS = {'scanned', 'cases_created', 'steps_created',
                 'skipped', 'invalid', 'failed'}


# --------------------------------------------------------------------------
# Task 5 Step 1 — failing tests (RED sebelum implementasi)
# --------------------------------------------------------------------------
def test_dua_baris_sumber_jadi_dua_kasus_dan_langkah():
    db = _db(_legacy(11, NIK_A, branch='SBY'),
             _legacy(12, NIK_B, branch='BDG', name='JIMMY OVIANT'))

    report = bf.backfill(conn=db, commit=True)

    assert set(report) == EXPECTED_KEYS
    assert report['scanned'] == 2
    assert report['cases_created'] == 2
    assert report['steps_created'] == 2
    assert report['skipped'] == report['invalid'] == report['failed'] == 0
    assert len(db.tables['recruitment_cases']) == 2
    assert len(db.tables['recruitment_steps']) == 2
    step_a = _step(db, NIK_A, 'SBY')
    assert step_a['evidence_type'] == 'sheet_legacy'
    assert step_a['evidence_id'] == '11', 'evidence_id harus id submission'
    assert step_a['status'] == 'SELESAI'
    assert step_a['branch_code'] == 'SBY'
    step_b = _step(db, NIK_B, 'BDG')
    assert step_b['evidence_id'] == '12'
    assert step_b['branch_code'] == 'BDG'
    assert report['steps_created'] == db.commits == 2, 'transaksi per NIK'


def test_jalan_ulang_tidak_menambah_baris_atau_menimpa_evidence():
    db = _db(_legacy(11, NIK_A), _legacy(12, NIK_B))
    bf.backfill(conn=db, commit=True)
    before = copy.deepcopy(db.tables['recruitment_steps'])

    second = bf.backfill(conn=db, commit=True)

    assert second['scanned'] == 2
    assert second['cases_created'] == second['steps_created'] == 0
    assert second['skipped'] == 2
    assert db.tables['recruitment_steps'] == before
    assert len(db.tables['recruitment_cases']) == 2
    assert db.commits == 2, 'run kedua tidak boleh commit'


def test_hash_ringkasan_sumber_identik_sebelum_sesudah():
    db = _db(_legacy(11, NIK_A),
             _legacy(12, NIK_B, source='form'),
             cv_rows=[{'id': 7, 'nik': NIK_C, 'nama': 'CV USER',
                       'branch_code': 'JKT'}])
    before = _digest(db)

    bf.backfill(conn=db, commit=True)

    assert _digest(db) == before
    writes = [s for s in db.statements
              if s.startswith(('INSERT', 'UPDATE', 'DELETE'))
              and ('FIRST_WORK_SUBMISSIONS' in s
                   or 'CV_ONLINE_SUBMISSIONS' in s)]
    assert writes == [], 'tabel sumber tidak boleh ditulis'


def test_dry_run_tidak_menulis():
    db = _db(_legacy(11, NIK_A), _legacy(12, NIK_B))
    before = _digest(db)

    report = bf.backfill(conn=db, commit=False)

    assert report['scanned'] == 2
    assert report['cases_created'] == 2
    assert report['steps_created'] == 2
    assert db.tables['recruitment_cases'] == []
    assert db.tables['recruitment_steps'] == []
    assert db.commits == 0
    assert _digest(db) == before


def test_satu_nik_dua_cabang_satu_kasus_dua_langkah():
    db = _db(_legacy(11, NIK_A, branch='SBY'),
             _legacy(12, NIK_A, branch='BDG'),
             _legacy(13, NIK_A, branch='SBY'))

    report = bf.backfill(conn=db, commit=True)

    assert report['cases_created'] == 1
    assert report['steps_created'] == 2
    assert report['skipped'] == 1, 'baris ke-3 cabang SBY duplikat'
    assert len(db.tables['recruitment_cases']) == 1
    assert len(db.tables['recruitment_steps']) == 2
    assert {s['branch_code'] for s in db.tables['recruitment_steps']} == {'SBY', 'BDG'}


def test_nik_invalid_dihitung_invalid():
    db = _db(_legacy(11, NIK_INVALID), _legacy(12, NIK_A))

    report = bf.backfill(conn=db, commit=True)

    assert report['invalid'] == 1
    assert report['cases_created'] == 1
    assert [c['nik'] for c in db.tables['recruitment_cases']] == [NIK_A]
    assert len(db.tables['recruitment_steps']) == 1


def test_baris_unitedw_tidak_di_backfill():
    db = _db(_legacy(11, NIK_A),
             _legacy(12, NIK_B, source='unitedw'))

    report = bf.backfill(conn=db, commit=True)

    assert report['scanned'] == 1
    assert [c['nik'] for c in db.tables['recruitment_cases']] == [NIK_A]


def test_langkah_form_yang_sudah_ada_tidak_ditimpa():
    db = _db(_legacy(11, NIK_A, branch='SBY'))
    db.tables['recruitment_cases'].append({
        'case_id': 'RC-FORM1', 'nik': NIK_A, 'nama': 'NAMA DARI FORM',
        'tanggal_lahir': '1990-01-01', 'first_branch': 'SBY'})
    db.tables['recruitment_steps'].append({
        'case_id': 'RC-FORM1', 'step_type': 'FIRSTWORK',
        'status': 'SELESAI', 'branch_code': 'SBY',
        'evidence_type': 'first_work_submission',
        'evidence_id': 'FW-FORM-1', 'completed_at': '2026-11-01 09:00:00'})
    db._saved = copy.deepcopy(db.tables)

    report = bf.backfill(conn=db, commit=True)

    assert report['skipped'] == 1
    assert report['steps_created'] == 0
    step = _step(db, NIK_A)
    assert step['evidence_type'] == 'first_work_submission'
    assert step['evidence_id'] == 'FW-FORM-1'
    assert step['completed_at'] == '2026-11-01 09:00:00'
    assert len(db.tables['recruitment_cases']) == 1


def test_kasus_dari_cv_online_dipakai_ulang_tanpa_menimpa_identitas():
    db = _db(_legacy(11, NIK_A, branch='BDG'),
             cv_rows=[{'id': 7, 'nik': NIK_A, 'nama': 'CV USER',
                       'branch_code': 'JKT'}])
    db.tables['recruitment_cases'].append({
        'case_id': 'RC-CV1', 'nik': NIK_A, 'nama': 'CV USER',
        'tanggal_lahir': None, 'first_branch': 'JKT'})
    db.tables['recruitment_steps'].append({
        'case_id': 'RC-CV1', 'step_type': 'CV', 'status': 'SELESAI',
        'branch_code': 'JKT', 'evidence_type': 'cv_online_submission',
        'evidence_id': 'CV-7', 'completed_at': '2026-10-01 09:00:00'})
    db._saved = copy.deepcopy(db.tables)

    report = bf.backfill(conn=db, commit=True)

    assert report['cases_created'] == 0
    assert report['steps_created'] == 1
    assert len(db.tables['recruitment_cases']) == 1
    case = db.tables['recruitment_cases'][0]
    assert case['case_id'] == 'RC-CV1'
    assert case['nama'] == 'CV USER'
    step = _step(db, NIK_A, 'BDG')
    assert step['evidence_type'] == 'sheet_legacy'
    assert step['evidence_id'] == '11'
    assert len(db.tables['recruitment_steps']) == 2


def test_gagal_satu_nik_di_rollback_nik_lain_tetap_masuk(monkeypatch):
    db = _db(_legacy(11, NIK_A), _legacy(12, NIK_B))
    real_upsert = bf.upsert_case_step

    def gagal_nik_b(nik, *args, **kwargs):
        if nik == NIK_B:
            raise RuntimeError('boom')
        return real_upsert(nik, *args, **kwargs)

    monkeypatch.setattr(bf, 'upsert_case_step', gagal_nik_b)

    report = bf.backfill(conn=db, commit=True)

    assert report['failed'] == 1
    assert report['cases_created'] == 1
    assert report['steps_created'] == 1
    assert [c['nik'] for c in db.tables['recruitment_cases']] == [NIK_A]
    assert db.rollbacks == 1
    assert db.commits == 1


def test_log_hanya_empat_digit_terakhir(capsys):
    db = _db(_legacy(11, NIK_A), _legacy(12, NIK_INVALID))

    bf.backfill(conn=db, commit=True)

    out = capsys.readouterr().out
    assert NIK_A not in out and NIK_INVALID not in out
    assert NIK_A[-4:] in out


def test_cli_default_dry_run_dan_commit_eksplisit(monkeypatch, capsys):
    db = _db(_legacy(11, NIK_A))
    monkeypatch.setattr(bf, 'get_master_connection', lambda: db)

    assert bf.main([]) == 0
    out = capsys.readouterr().out
    assert '"scanned"' in out and 'Dry-run' in out
    assert db.tables['recruitment_cases'] == []

    assert bf.main(['--commit']) == 0
    assert len(db.tables['recruitment_cases']) == 1
    assert db.commits >= 1


def test_cli_commit_tanpa_db_gagal(monkeypatch, capsys):
    monkeypatch.setattr(bf, 'get_master_connection', lambda: None)

    assert bf.main(['--commit']) == 1
    assert 'DB master' in capsys.readouterr().err


def test_backfill_commit_tanpa_koneksi_ditolak():
    with pytest.raises(RuntimeError, match='DB master'):
        bf.backfill(commit=True)
