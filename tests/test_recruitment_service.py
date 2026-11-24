"""Regresi upsert kasus & langkah rekrutmen saat submit (Rilis A — Task 4).

Yang diuji:
1. Satu NIK di dua cabang = satu kasus, dua langkah, dua riwayat cabang.
2. Kasus lama tidak ditimpa nama/tanggal lahirnya; cabang yang sama tidak
   menambah baris riwayat; evidence terakhir yang dipakai.
3. Upsert dipanggil di DALAM transaksi submit CV Online & FirstWork, memakai
   branch_code dari token form (bukan body klien).
4. Bila upsert gagal, seluruh submit ikut rollback — tidak ada kasus yatim.

Koneksi dan cursor palsu meniru SQL yang dipakai service/route (tanpa MySQL),
mengikuti pola `tests/test_cv_online_nik.py` dan `tests/test_recruitment_lookup.py`.
Rollback pada koneksi palsu mengembalikan tabel ke snapshot commit terakhir,
sehingga atomicitas benar-benar teramati, bukan hanya dihitung dari flag.
"""
import copy
import io
import os
import re
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers as hp  # noqa: E402
from modules import routes_cv_online as cv  # noqa: E402
from modules import routes_first_work as fw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NIK = '3573010101990001'
NAMA = 'Budi Santoso'
DOB = '1995-01-19'
JKT = [{'code': 'JKT', 'name': 'Jakarta', 'city': 'Jakarta'}]
TOKEN = 'tok-jkt-4'

CV_BASE = {
    'sumber_informasi': 'Instagram',
    'diundang_oleh': 'EF 1',
    'user_ef': 'EF 1',
    'kontak_serumah': 'Ibu Siti, 081211112222, IRT, Jl. Contoh 1',
    'kontak_tidak_serumah': 'Budi, 081233334444, Karyawan, Jl. Contoh 2',
    'nama': NAMA,
    'tempat_lahir': 'Surabaya',
    'tanggal_lahir': DOB,
    'jenis_kelamin': 'Pria',
    'domisili': 'JAWA TIMUR',
    'alamat': 'Jl. Contoh No. 1, Surabaya',
    'no_hp': '081234567890',
    'pendidikan_terakhir': 'S1',
    'nik': NIK,
}
FW_BASE = {
    'nik': NIK,
    'nama': NAMA,
    'pendidikan': 'SMA',
    'no_hp': '081234567890',
    'referensi_text': 'Uji rekrutmen',
    'branch_code': 'SBY',  # decoy: cabang asli berasal dari token
}


@pytest.fixture(autouse=True)
def _tanpa_rate_limit(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = None

    @property
    def lastrowid(self):
        return self.conn.lastrowid

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append(upper)
        if self.conn.fail_on and self.conn.fail_on in upper:
            raise RuntimeError(f'gagal sengaja: {self.conn.fail_on}')
        params = tuple(params or ())

        if upper.startswith('SELECT'):
            self.rows = self._select(upper, params)
            return
        if upper.startswith('INSERT INTO'):
            table, columns = self._insert_shape(upper)
            table = table.lower()
            values = dict(zip(columns, params[:len(columns)]))
            unique = {
                'recruitment_cases': ('nik',),
                'recruitment_steps': ('case_id', 'step_type', 'branch_code'),
                'case_branch_history': ('case_id', 'branch_code'),
            }.get(table)
            rows = self.conn.tables[table]
            existing = next((r for r in rows
                             if unique and all(r.get(k) == values.get(k) for k in unique)),
                            None)
            if existing and 'ON DUPLICATE KEY UPDATE' in upper:
                existing.update(values)
            else:
                rows.append(values)
                self.conn.lastrowid = len(rows)
            return
        if upper.startswith('UPDATE'):
            match = re.match(r'UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(\w+)=%S', upper)
            if not match:
                return
            table, sets, key = match.groups()
            table = table.lower()
            assignments = [s.strip().split('=')[0].lower() for s in sets.split(',')]
            changes = dict(zip(assignments, params[:-1]))
            for row in self.conn.tables[table]:
                if str(row.get(key.lower())) == str(params[-1]):
                    row.update(changes)
            return
        self.rows = None

    def _select(self, upper, params):
        table_match = re.search(r'FROM\s+(\w+)', upper)
        table = table_match.group(1).lower() if table_match else ''
        if table == 'branches':
            return self.conn.tables['branches']
        if table in ('cv_online_branch_forms', 'first_work_branch_forms'):
            return self.conn.tables[table]
        rows = self.conn.tables.get(table, [])
        if 'nik=%s' in upper and params:
            rows = [r for r in rows if str(r.get('nik')) == str(params[0])]
        elif 'case_id=%s' in upper and params:
            rows = [r for r in rows if str(r.get('case_id')) == str(params[0])]
        if 'COUNT(*)' in upper:
            return {'n': len(rows)}
        return rows

    @staticmethod
    def _insert_shape(upper):
        match = re.match(r'INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES', upper)
        assert match, upper
        return match.group(1), [c.strip().lower() for c in match.group(2).split(',')]

    def fetchone(self):
        if isinstance(self.rows, list):
            return self.rows[0] if self.rows else None
        return self.rows

    def fetchall(self):
        return self.rows if isinstance(self.rows, list) else []

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.tables = {
            'recruitment_cases': [],
            'recruitment_steps': [],
            'case_branch_history': [],
            'cv_online_submissions': [],
            'cv_online_events': [],
            'first_work_submissions': [],
            'first_work_events': [],
            'branches': [],
            'cv_online_branch_forms': [],
            'first_work_branch_forms': [],
        }
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
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
        self.closed = True


@pytest.fixture
def db():
    return _FakeConn()


@pytest.fixture
def cv_app():
    app = Flask(__name__)
    app.secret_key = 'test-recruitment-service-cv'
    cv.register_cv_online_routes(app)
    return app


@pytest.fixture
def fw_app():
    app = Flask(__name__)
    app.secret_key = 'test-recruitment-service-fw'
    fw.register_first_work_routes(app)
    return app


def _upsert(nik=NIK, nama=NAMA, dob=DOB, branch='SBY', step='CV',
            evidence='EV-1', conn=None, **kw):
    from modules.recruitment_service import upsert_case_step
    return upsert_case_step(nik, nama, dob, branch, step, evidence, conn=conn, **kw)


class TestUpsertCaseStep:
    def test_dua_cabang_satu_kasus_dua_step_dua_riwayat(self, db):
        first = _upsert(branch='SBY', step='CV', evidence='CV-SBY-001', conn=db)
        second = _upsert(branch='JKT', step='FIRSTWORK',
                         evidence='FW-JKT-001', conn=db)

        assert first == second
        assert len(db.tables['recruitment_cases']) == 1
        assert len(db.tables['recruitment_steps']) == 2
        assert {r['step_type'] for r in db.tables['recruitment_steps']} == {'CV', 'FIRSTWORK'}
        assert {r['branch_code'] for r in db.tables['recruitment_steps']} == {'SBY', 'JKT'}
        assert len(db.tables['case_branch_history']) == 2
        assert db.commits == 0  # transaksi tetap milik pemanggil
        assert db.closed is False

    def test_cabang_sama_tidak_menambah_riwayat_dan_bukti_diperbarui(self, db):
        _upsert(branch='SBY', step='CV', evidence='CV-1', conn=db)
        case_id = _upsert(branch='SBY', step='CV', evidence='CV-2', conn=db)

        assert case_id == db.tables['recruitment_cases'][0]['case_id']
        assert len(db.tables['recruitment_steps']) == 1
        assert db.tables['recruitment_steps'][0]['evidence_id'] == 'CV-2'
        assert len(db.tables['case_branch_history']) == 1

    def test_nama_dan_tanggal_lahir_diisi_saat_kasus_baru(self, db):
        _upsert(nama=NAMA, dob=DOB, conn=db)

        case = db.tables['recruitment_cases'][0]
        assert case['nama'] == NAMA
        assert case['tanggal_lahir'] == DOB
        assert case['first_branch'] == 'SBY'

    def test_nama_dan_tanggal_lahir_lama_tidak_timpa(self, db):
        db.tables['recruitment_cases'].append({
            'case_id': 'RC-1', 'nik': NIK, 'nama': NAMA,
            'tanggal_lahir': DOB, 'first_branch': 'SBY',
        })

        _upsert(nama='Nama Berbeda', dob='1990-01-01',
                branch='JKT', step='FIRSTWORK', conn=db)

        case = db.tables['recruitment_cases'][0]
        assert len(db.tables['recruitment_cases']) == 1
        assert case['nama'] == NAMA
        assert case['tanggal_lahir'] == DOB

    def test_field_kosong_pada_kasus_lama_diisi_tanpa_menimpa_yang_ada(self, db):
        db.tables['recruitment_cases'].append({
            'case_id': 'RC-LAMA', 'nik': NIK, 'nama': '',
            'tanggal_lahir': '1990-01-01', 'first_branch': 'SBY',
        })

        _upsert(nama=NAMA, dob=DOB, branch='JKT', step='FIRSTWORK', conn=db)

        case = db.tables['recruitment_cases'][0]
        assert case['nama'] == NAMA
        assert case['tanggal_lahir'] == '1990-01-01'
        assert len(db.tables['recruitment_cases']) == 1

    def test_step_type_di_luar_cv_dan_firstwork_ditolak(self, db):
        with pytest.raises(ValueError, match='step_type'):
            _upsert(step='TRAINING', conn=db)

        assert db.tables['recruitment_cases'] == []
        assert db.tables['recruitment_steps'] == []

    def test_nik_tidak_valid_ditolak(self, db):
        with pytest.raises(ValueError, match='NIK'):
            _upsert(nik='12345', conn=db)

        assert db.tables['recruitment_cases'] == []

    def test_standalone_commit_dan_tutup_koneksi_sendiri(self, db, monkeypatch):
        import modules.recruitment_service as rs
        monkeypatch.setattr(rs, 'get_master_connection', lambda: db)

        case_id = _upsert()

        assert case_id == db.tables['recruitment_cases'][0]['case_id']
        assert db.commits == 1
        assert db.closed is True

    def test_standalone_gagal_rollback(self, db, monkeypatch):
        import modules.recruitment_service as rs
        monkeypatch.setattr(rs, 'get_master_connection', lambda: db)
        db.fail_on = 'INSERT INTO RECRUITMENT_STEPS'

        with pytest.raises(RuntimeError, match='gagal sengaja'):
            _upsert()

        assert db.rollbacks == 1
        assert db.commits == 0
        assert db.tables['recruitment_cases'] == []
        assert db.tables['case_branch_history'] == []


class TestIntegrasiCVOnline:
    def test_submit_menulis_step_dengan_cabang_dari_token(self, db, cv_app, monkeypatch):
        db.tables['branches'] = JKT
        db.tables['cv_online_branch_forms'] = [
            {'branch_code': 'JKT', 'form_token': TOKEN, 'active': 1}]
        monkeypatch.setattr(cv, 'get_master_connection', lambda: db)

        with cv_app.test_client() as client:
            response = client.post(f'/api/cv-online/public?cabang=JKT&t={TOKEN}',
                                   data={**CV_BASE, 'branch_code': 'SBY', 'consent': '1'})

        assert response.status_code == 200, response.get_json()
        case = db.tables['recruitment_cases'][0]
        step = db.tables['recruitment_steps'][0]
        assert case['nik'] == NIK
        assert step['step_type'] == 'CV'
        assert step['branch_code'] == 'JKT'
        assert step['evidence_type'] == 'cv_online_submission'
        assert step['evidence_id'] == response.get_json()['registration_no']
        assert [r['branch_code'] for r in db.tables['case_branch_history']] == ['JKT']
        assert db.commits == 1

    def test_gagal_upsert_membatalkan_submit(self, db, cv_app, monkeypatch):
        db.fail_on = 'INSERT INTO RECRUITMENT_STEPS'
        monkeypatch.setattr(cv, 'get_master_connection', lambda: db)

        with cv_app.test_client() as client:
            response = client.post('/api/cv-online/public',
                                   data={**CV_BASE, 'consent': '1'})

        assert response.status_code == 500
        assert any(s.startswith('INSERT INTO RECRUITMENT_STEPS')
                   for s in db.statements)  # upsert benar-benar dipanggil
        assert db.rollbacks >= 1
        assert db.commits == 0
        assert db.tables['cv_online_submissions'] == []
        assert db.tables['cv_online_events'] == []
        assert db.tables['recruitment_cases'] == []
        assert db.tables['recruitment_steps'] == []
        assert db.tables['case_branch_history'] == []


class TestIntegrasiFirstWork:
    def _submit(self, db, fw_app, monkeypatch, query=''):
        monkeypatch.setattr(fw, 'get_master_connection', lambda: db)
        monkeypatch.setattr(fw, 'save_file', lambda *a, **k: 'ktp-dummy.png')
        monkeypatch.setattr(fw, '_assign_id_numbers',
                            lambda *a, **k: ('B-1', 'C-1'))
        monkeypatch.setattr(fw, '_next_reg_no',
                            lambda conn, submitted_at, branch_code='SBY':
                            f'FW-{branch_code}-0001')
        monkeypatch.setattr(fw, '_ensure_ktp_scan', lambda *a, **k: None)
        monkeypatch.setattr(fw, '_flag_reuse_signals', lambda *a, **k: None)
        ktp = (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'x' * 32), 'ktp.png')
        with fw_app.test_client() as client:
            # Flask/Werkzeug versi repo: file cukup masuk lewat `data`
            # (otomatis multipart), bukan kwarg `files`.
            return client.post(f'/api/first-work/public{query}',
                               data={**FW_BASE, 'consent': '1', 'ktp': ktp})

    def test_submit_menulis_step_dengan_cabang_dari_token(self, db, fw_app, monkeypatch):
        db.tables['branches'] = JKT
        db.tables['first_work_branch_forms'] = [
            {'branch_code': 'JKT', 'form_token': TOKEN, 'active': 1}]

        response = self._submit(db, fw_app, monkeypatch, f'?cabang=JKT&t={TOKEN}')

        assert response.status_code == 200, response.get_json()
        case = db.tables['recruitment_cases'][0]
        step = db.tables['recruitment_steps'][0]
        assert case['nik'] == NIK
        assert step['step_type'] == 'FIRSTWORK'
        assert step['branch_code'] == 'JKT'
        assert step['evidence_type'] == 'first_work_submission'
        assert step['evidence_id'] == response.get_json()['registration_no']
        assert [r['branch_code'] for r in db.tables['case_branch_history']] == ['JKT']
        assert db.commits == 1

    def test_gagal_upsert_membatalkan_submit(self, db, fw_app, monkeypatch):
        db.fail_on = 'INSERT INTO RECRUITMENT_STEPS'

        response = self._submit(db, fw_app, monkeypatch)

        assert response.status_code == 500
        assert any(s.startswith('INSERT INTO RECRUITMENT_STEPS')
                   for s in db.statements)  # upsert benar-benar dipanggil
        assert db.rollbacks >= 1
        assert db.commits == 0
        assert db.tables['first_work_submissions'] == []
        assert db.tables['first_work_events'] == []
        assert db.tables['recruitment_cases'] == []
        assert db.tables['recruitment_steps'] == []
        assert db.tables['case_branch_history'] == []


def test_service_memakai_helper_normalisasi_nik_yang_sama():
    source = (ROOT / 'modules' / 'recruitment_service.py').read_text(encoding='utf-8')
    assert 'from modules.helpers import normalize_nik' in source
    assert re.search(r'def\s+normalize_nik', source) is None
