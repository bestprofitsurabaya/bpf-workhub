"""Rilis B Task 4 — impor 226 pengajuan unitedw ke WorkHub.

Regresi yang dijaga:
1. NIK ganda → satu recruitment_cases + catatan `merged_from` (bukan 3 kasus).
2. Email ganda ditandai di `verification_note` tiap submission.
3. Dua kali impor `--commit` → `skipped=226` (semua), tanpa baris baru.
4. Dry-run default tidak menulis apa pun; `--commit` yang menulis.
5. NIK 16 digit divalidasi; log/report hanya 4 digit terakhir.
6. ID FP/ID BPF dipertahankan apa adanya (tanpa penomoran ulang).
7. Nama cabang unitedw dipetakan ke branch_code WorkHub.

Koneksi/cursor palsu meniru SQL yang dipakai import + upsert_case_step Rilis A
(tanpa MySQL), mengikuti pola tests/test_recruitment_service.py.
"""
import copy
import csv
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import import_unitedw_firstwork as imp  # noqa: E402

NIK_A = '3525161807070002'
NIK_B = '3171011504991001'
HEADERS = [
    'No', 'Waktu kirim', 'ID FP', 'ID BPF', 'Email', 'NIK KTP', 'Nama Lengkap',
    'Cabang', 'Status', 'Tempat Lahir', 'Tanggal Lahir', 'Jenis Kelamin',
    'Gol. Darah', 'Alamat', 'RT/RW', 'Kel/Desa', 'Kecamatan', 'Agama',
    'Status Perkawinan', 'Pekerjaan', 'Kewarganegaraan', 'Berlaku Hingga',
    'Pendidikan', 'Referensi', 'No. Handphone', 'File KTP',
]


def _row(**overrides):
    base = {
        'No': '1', 'Waktu kirim': '24/11/2026 11:00:24',
        'ID FP': 'EF_30031', 'ID BPF': 'EF_8365',
        'Email': 'orang1@example.com', 'NIK KTP': NIK_A,
        'Nama Lengkap': 'MUCHAMMAD FAISAL ARIF', 'Cabang': 'Surabaya',
        'Status': 'Baru', 'Tempat Lahir': 'GRESIK', 'Tanggal Lahir': '2007-07-18',
        'Jenis Kelamin': 'LAKI-LAKI', 'Gol. Darah': 'O',
        'Alamat': 'USMAN SADAR 14/8', 'RT/RW': '007/001', 'Kel/Desa': 'KARANGTURI',
        'Kecamatan': 'GRESIK', 'Agama': 'ISLAM', 'Status Perkawinan': 'BELUM KAWIN',
        'Pekerjaan': 'PELAJAR/MAHASISWA', 'Kewarganegaraan': 'WNI',
        'Berlaku Hingga': 'Seumur Hidup', 'Pendidikan': 'SMA',
        'Referensi': 'INSTAGRAM', 'No. Handphone': '6285806075618',
        'File KTP': 'ktp/EF/EF_KTP_sumber.jpg',
    }
    base.update(overrides)
    return base


def _csv(tmp_path, rows):
    path = tmp_path / 'unitedw.csv'
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(path)


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

        if q.startswith('SELECT LAST_INSERT_ID()'):
            self.rows = [(self.conn.last_insert_id,)]
            return
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
        if 'WHERE NIK=%S' in q and params:
            return [r for r in rows if str(r.get('nik')) == str(params[0])]
        if 'WHERE CASE_ID=%S' in q and params:
            return [r for r in rows if str(r.get('case_id')) == str(params[0])]
        if 'SOURCE=%S' in q and 'SOURCE_UID=%S' in q and len(params) >= 2:
            return [r for r in rows if str(r.get('source')) == str(params[0])
                    and str(r.get('source_uid')) == str(params[1])]
        return list(rows)

    def _insert(self, q, params):
        match = re.match(r'INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES', q)
        assert match, q
        table = match.group(1).lower()
        columns = [c.strip().lower() for c in match.group(2).split(',')]
        values = dict(zip(columns, params[:len(columns)]))
        rows = self.conn.tables[table]
        if table == 'doc_sequences':
            key = values.get('seq_key')
            seq = self.conn.sequences.get(key, 0) + 1
            self.conn.sequences[key] = seq
            self.conn.last_insert_id = seq
            return
        unique = {
            'first_work_submissions': ('source_uid',),
            'recruitment_cases': ('nik',),
            'recruitment_steps': ('case_id', 'step_type', 'branch_code'),
            'case_branch_history': ('case_id', 'branch_code'),
        }.get(table)
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
            'first_work_submissions': [], 'first_work_events': [],
            'recruitment_cases': [], 'recruitment_steps': [],
            'case_branch_history': [], 'doc_sequences': [],
        }
        self.sequences = {}
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.lastrowid = 0
        self.last_insert_id = 0
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


def _subs(db, uid):
    return next(s for s in db.tables['first_work_submissions']
                if s['source_uid'] == uid)


# --------------------------------------------------------------------------
# Task 4 Step 1 — failing tests (RED sebelum implementasi)
# --------------------------------------------------------------------------
def test_nik_ganda_satu_kasus_dengan_merged_from(tmp_path):
    path = _csv(tmp_path, [
        _row(No='1', **{'ID FP': 'EF_30031', 'ID BPF': 'EF_8365'}),
        _row(No='2', **{'ID FP': 'EK_89526', 'ID BPF': 'EK_1234',
                        'NIK KTP': NIK_B, 'Nama Lengkap': 'JIMMY OVIANT',
                        'Cabang': 'Pekanbaru', 'Email': 'jimmy@example.com'}),
        _row(No='3', **{'ID FP': 'EK_89525', 'ID BPF': 'EK_1235',
                        'NIK KTP': NIK_B, 'Nama Lengkap': 'JIMMY OVIANT',
                        'Cabang': 'Pekanbaru', 'Email': 'jimmy2@example.com'}),
    ])
    db = _FakeConn()

    report = imp.import_unitedw(path, conn=db, commit=True)

    assert report == {'inserted': 2, 'skipped': 0, 'merged': 1, 'invalid': 0}
    cases = [c for c in db.tables['recruitment_cases'] if c['nik'] == NIK_B]
    assert len(cases) == 1, 'NIK ganda tidak boleh membuat 2 kasus'
    note = cases[0]['merged_from'] or ''
    assert 'EK_89526' in note and 'EK_89525' in note
    assert len(db.tables['first_work_submissions']) == 3
    # ID sumber tidak dinomori ulang.
    assert _subs(db, 'EK_89525')['fingerprint_no'] == 'EK_89525'
    assert _subs(db, 'EK_89525')['bpf_no'] == 'EK_1235'


def test_email_ganda_ditandai(tmp_path):
    path = _csv(tmp_path, [
        _row(No='1', **{'ID FP': 'EF_30031', 'Email': 'SAMA@example.com'}),
        _row(No='2', **{'ID FP': 'EG_20001', 'NIK KTP': NIK_B,
                        'Cabang': 'Bandung', 'Email': 'sama@example.com'}),
        _row(No='3', **{'ID FP': 'EA_10001', 'NIK KTP': '3214567890123456',
                        'Cabang': 'Jakarta - Pacific Place Mall',
                        'Email': 'unik@example.com'}),
    ])
    db = _FakeConn()

    imp.import_unitedw(path, conn=db, commit=True)

    assert 'EMAIL_DUPLIKAT' in _subs(db, 'EF_30031')['verification_note']
    assert 'EMAIL_DUPLIKAT' in _subs(db, 'EG_20001')['verification_note']
    assert 'EMAIL_DUPLIKAT' not in _subs(db, 'EA_10001')['verification_note']


def test_impor_ulang_skip_semua_tanpa_baris_baru(tmp_path):
    path = _csv(tmp_path, [
        _row(No='1', **{'ID FP': 'EF_30031'}),
        _row(No='2', **{'ID FP': 'EK_89526', 'NIK KTP': NIK_B,
                        'Cabang': 'Pekanbaru'}),
    ])
    db = _FakeConn()

    first = imp.import_unitedw(path, conn=db, commit=True)
    second = imp.import_unitedw(path, conn=db, commit=True)

    assert first == {'inserted': 2, 'skipped': 0, 'merged': 0, 'invalid': 0}
    assert second == {'inserted': 0, 'skipped': 2, 'merged': 0, 'invalid': 0}
    assert len(db.tables['first_work_submissions']) == 2
    assert len(db.tables['recruitment_cases']) == 2
    assert len(db.tables['recruitment_steps']) == 2


def test_dry_run_default_tidak_menulis(tmp_path):
    path = _csv(tmp_path, [_row(No='1')])
    db = _FakeConn()

    report = imp.import_unitedw(path, conn=db, commit=False)

    assert report == {'inserted': 1, 'skipped': 0, 'merged': 0, 'invalid': 0}
    assert db.tables['first_work_submissions'] == []
    assert db.tables['recruitment_cases'] == []
    assert db.commits == 0


def test_gagal_di_tengah_rollback_semua(tmp_path):
    path = _csv(tmp_path, [
        _row(No='1', **{'ID FP': 'EF_30031'}),
        _row(No='2', **{'ID FP': 'EG_20001', 'NIK KTP': NIK_B,
                        'Cabang': 'Bandung'}),
    ])
    db = _FakeConn()
    db.fail_on = 'INSERT INTO RECRUITMENT_CASES'

    with pytest.raises(RuntimeError):
        imp.import_unitedw(path, conn=db, commit=True)

    assert db.rollbacks == 1
    assert db.tables['first_work_submissions'] == []
    assert db.tables['first_work_events'] == []
    assert db.tables['recruitment_cases'] == []
    assert db.tables['recruitment_steps'] == []


def test_nik_invalid_ditandai_invalid_dan_log_tanpa_nik_lengkap(tmp_path, capsys):
    jelek = '123456789012345'  # 15 digit
    path = _csv(tmp_path, [
        _row(No='1', **{'ID FP': 'EF_30031', 'NIK KTP': NIK_A}),
        _row(No='2', **{'ID FP': 'EG_20001', 'NIK KTP': jelek,
                        'Cabang': 'Bandung'}),
    ])
    db = _FakeConn()

    report = imp.import_unitedw(path, conn=db, commit=True)
    out = capsys.readouterr().out

    assert report['invalid'] == 1
    assert report['inserted'] == 1
    assert len(db.tables['first_work_submissions']) == 1
    assert jelek not in out, 'log tidak boleh memuat NIK lengkap'
    assert NIK_A not in out, 'log tidak boleh memuat NIK lengkap'
    assert NIK_A[-4:] in out


def test_pemetaan_nama_cabang_unitedw(tmp_path):
    expected = {
        'Kantor Pusat - Equity Tower, Jakarta': 'JKT',
        'Jakarta - Pacific Place Mall': 'JKT2',
        'Bandung': 'BDG', 'Surabaya': 'SBY', 'Malang': 'MLG',
        'Bandar Lampung': 'LPG', 'Pontianak': 'PTK', 'Pekanbaru': 'PKU',
        'Banjarmasin': 'BJM', 'Jambi': 'JMB', 'Semarang': 'SMG', 'Medan': 'MDN',
    }
    for name, code in expected.items():
        assert imp.map_branch(name) == code, name
    # Fallback bila nama cabang asing: prefix ID FP yang resmi.
    assert imp.map_branch('Cabang Baru', 'EJ_12345') == 'BJM'
    assert imp.map_branch('SBY') == 'SBY'


def test_field_demografi_dan_normalisasi_tersimpan(tmp_path):
    path = _csv(tmp_path, [_row(**{
        'Tempat Lahir': 'GRESIK', 'Tanggal Lahir': '18/07/2007',
        'Gol. Darah': 'O', 'Alamat': 'Jl. Contoh 12', 'RT/RW': '007/001',
        'Kel/Desa': 'KARANGTURI', 'Kecamatan': 'GRESIK', 'Agama': 'ISLAM',
        'Status Perkawinan': 'BELUM KAWIN', 'Pekerjaan': 'MAHASISWA',
        'Kewarganegaraan': 'WNI', 'Berlaku Hingga': 'Seumur Hidup',
        'Pendidikan': 'SMA', 'Referensi': 'INSTAGRAM',
        'No. Handphone': '6285806075618',
    })])
    db = _FakeConn()

    imp.import_unitedw(path, conn=db, commit=True)
    sub = _subs(db, 'EF_30031')

    assert sub['tempat_lahir'] == 'GRESIK'
    assert sub['tanggal_lahir'] == '2007-07-18'
    assert sub['golongan_darah'] == 'O'
    assert sub['alamat'] == 'Jl. Contoh 12'
    assert sub['rt_rw'] == '007/001'
    assert sub['pendidikan_norm'] == 'SMA'
    assert sub['referensi_norm'] == 'instagram'
    assert sub['no_hp_norm'] == '085806075618'
    assert sub['branch_code'] == 'SBY'


def test_cli_default_dry_run_dan_commit_eksplisit(tmp_path, monkeypatch, capsys):
    path = _csv(tmp_path, [_row(No='1', **{'ID FP': 'EF_30031'})])
    db = _FakeConn()
    monkeypatch.setattr(imp, 'get_master_connection', lambda: db)

    assert imp.main(['--csv', path]) == 0
    out = capsys.readouterr().out
    assert '"inserted"' in out and '"skipped"' in out
    assert db.tables['first_work_submissions'] == []

    assert imp.main(['--csv', path, '--commit']) == 0
    assert len(db.tables['first_work_submissions']) == 1
    assert db.commits >= 1
