"""Regresi NIK pada form CV Online (Rilis A — Task 2).

 Yang diuji (tanpa DB nyata):
 1. Submit tanpa NIK / NIK bukan 16 digit ditolak 400.
 2. NIK 16 digit dinormalisasi, disimpan ke kolom `nik` + `nik_raw`.
 3. Baris lama dengan `nik` NULL tetap bisa dibaca (serialize/export).
 4. Kolom baru dipasang helper skema idempoten + tercermin di init.sql
    (sumber kebenaran schema drift CI).
 """
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

from modules import helpers as hp  # noqa: E402
from modules import routes_cv_online as cv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = Flask(__name__)
APP.secret_key = 'test-cv-online-nik'
cv.register_cv_online_routes(APP)

NIK = '3573010101990001'
BASE = {
    'sumber_informasi': 'Instagram',
    'diundang_oleh': 'EF 1',
    'user_ef': 'EF 1',
    'kontak_serumah': 'Ibu Siti, 081211112222, IRT, Jl. Contoh 1',
    'kontak_tidak_serumah': 'Budi, 081233334444, Karyawan, Jl. Contoh 2',
    'nama': 'Budi Santoso',
    'tempat_lahir': 'Surabaya',
    'tanggal_lahir': '1995-01-19',
    'jenis_kelamin': 'Pria',
    'domisili': 'JAWA TIMUR',
    'alamat': 'Jl. Contoh No. 1, Surabaya',
    'no_hp': '081234567890',
    'pendidikan_terakhir': 'S1',
    'nik': NIK,
}


@pytest.fixture(autouse=True)
def _tanpa_rate_limit(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last = None

    def execute(self, sql, params=None):
        upper = sql.upper()
        if 'FROM BRANCHES' in upper:
            self.last = [{'code': 'SBY', 'name': 'Surabaya', 'city': 'Surabaya'}]
        elif 'CV_ONLINE_BRANCH_FORMS' in upper:
            self.last = []
        elif 'INSERT INTO CV_ONLINE_SUBMISSIONS' in upper:
            self.conn.inserted.append((sql, params))
            self.conn.lastrowid = 7
        elif 'INSERT INTO CV_ONLINE_EVENTS' in upper:
            self.conn.events.append((sql, params))
        elif 'SELECT * FROM CV_ONLINE_SUBMISSIONS' in upper:
            self.last = self.conn.rows
        elif 'COUNT(*)' in upper:
            self.last = {'n': 0}
        elif 'SELECT ID FROM CV_ONLINE_SUBMISSIONS' in upper:
            self.last = None
        else:
            self.last = None

    def fetchone(self):
        if isinstance(self.last, list):
            return self.last[0] if self.last else None
        return self.last

    def fetchall(self):
        return self.last if isinstance(self.last, list) else []

    @property
    def lastrowid(self):
        return self.conn.lastrowid

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.inserted = []
        self.events = []
        self.rows = []
        self.commits = 0
        self.closed = False
        self.lastrowid = 0

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class TestValidasiNIK:
    def test_payload_tanpa_nik_ditolak(self):
        data, error = cv.validate_payload({k: v for k, v in BASE.items() if k != 'nik'})
        assert data is None
        assert 'NIK' in error

    def test_nik_kurang_dari_16_digit_ditolak(self):
        for value in ('', '12345', NIK[:-1], NIK + '1', '12e3+45678901234'):
            data, error = cv.validate_payload({**BASE, 'nik': value})
            assert data is None, value
            assert 'NIK' in error, value

    def test_nik_16_digit_dinormalisasi(self):
        data, error = cv.validate_payload({**BASE, 'nik': '3573 0101 0199 0001'})
        assert error == ''
        assert data['nik'] == NIK
        assert data['nik_raw'] == '3573 0101 0199 0001'


class TestSubmitPublik:
    def test_submit_tanpa_nik_ditolak_400(self):
        payload = {k: v for k, v in BASE.items() if k != 'nik'}
        with APP.test_client() as client:
            response = client.post('/api/cv-online/public',
                                   data={**payload, 'consent': '1'})
        assert response.status_code == 400
        assert 'NIK' in response.get_json()['msg']

    def test_submit_nik_tidak_valid_ditolak_400(self):
        with APP.test_client() as client:
            response = client.post('/api/cv-online/public',
                                   data={**BASE, 'nik': '12345', 'consent': '1'})
        assert response.status_code == 400
        assert 'NIK' in response.get_json()['msg']

    def test_submit_nik_16_digit_tersimpan(self, monkeypatch):
        conn = _FakeConn()
        monkeypatch.setattr(cv, 'get_master_connection', lambda: conn)
        with APP.test_client() as client:
            response = client.post('/api/cv-online/public',
                                   data={**BASE, 'nik': '3573 0101 0199 0001',
                                         'consent': '1'})
        assert response.status_code == 200, response.get_json()
        assert len(conn.inserted) == 1
        sql, params = conn.inserted[0]
        assert re.search(r'\bnik\b', sql, re.I)
        assert re.search(r'\bnik_raw\b', sql, re.I)
        assert NIK in params
        assert '3573 0101 0199 0001' in params

    def test_baris_lama_nik_null_tetap_terbaca(self):
        data = cv._serialize({'id': 1, 'nama': 'Pendaftar Lama',
                              'nik': None, 'nik_raw': None})
        assert data['nama'] == 'Pendaftar Lama'
        assert data['nik'] is None
        assert data['nik_raw'] is None

    def test_detail_menyertakan_nik_bila_ada(self, monkeypatch):
        conn = _FakeConn()
        conn.rows = [{
            'id': 7, 'registration_no': 'CV-SBY-260102-001', 'nama': 'Budi',
            'nik': NIK, 'nik_raw': NIK, 'status': 'submitted',
            'branch_code': 'SBY',
        }]
        monkeypatch.setattr(cv, 'get_master_connection', lambda: conn)
        with APP.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_role'] = 'traineer'
                sess['user_name'] = 'tr1'
                sess['branch_code'] = 'SBY'
            response = client.get('/api/cv-online/7')
        assert response.status_code == 200
        data = response.get_json()['data']
        assert data['nik'] == NIK
        assert data['nik_raw'] == NIK

    def test_ekspor_csv_menyertakan_nik(self, monkeypatch):
        conn = _FakeConn()
        conn.rows = [{
            'id': 7, 'registration_no': 'CV-SBY-260102-001', 'nama': 'Budi',
            'nik': NIK, 'nik_raw': '', 'status': 'submitted',
            'submitted_at': '2026-11-24 10:00:00',
        }]
        monkeypatch.setattr(cv, 'get_master_connection', lambda: conn)
        with APP.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_role'] = 'traineer'
                sess['user_name'] = 'tr1'
                sess['branch_code'] = 'SBY'
            response = client.get('/api/cv-online/export')
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert 'NIK' in text
        assert NIK in text


class TestHelperBersama:
    def test_normalize_nik_tersedia_di_helpers_dan_first_work(self):
        from modules.helpers import normalize_nik as helper_nik
        from modules.routes_first_work import normalize_nik as first_work_nik
        assert helper_nik('3573 0101 0199 0001') == (NIK, '3573 0101 0199 0001')
        assert first_work_nik('3573 0101 0199 0001') == (NIK, '3573 0101 0199 0001')
        assert helper_nik('1,23E+15') == ('', '1,23E+15')


class _SchemaCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        upper = sql.upper()
        if 'INFORMATION_SCHEMA.COLUMNS' in upper:
            self.conn.queried = True
            return
        if 'ALTER TABLE' in upper:
            self.conn.alters.append(sql)
            match = re.search(r'ADD COLUMN\s+(\w+)', sql, re.I)
            if match:
                self.conn.existing.add(match.group(1).lower())

    def fetchall(self):
        return [(name,) for name in sorted(self.conn.existing)]

    def close(self):
        pass


class _SchemaConn:
    def __init__(self):
        self.existing = set()
        self.alters = []
        self.commits = 0
        self.queried = False
        self.closed = False

    def cursor(self):
        return _SchemaCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class TestSkemaNIK:
    def test_helper_menambah_keduakolom_secara_idempoten(self):
        from modules.cv_online_schema import ensure_cv_online_nik_columns
        conn = _SchemaConn()
        assert ensure_cv_online_nik_columns(conn) is True
        assert len(conn.alters) == 2
        assert any(re.search(r'\bnik\b', sql, re.I) for sql in conn.alters)
        assert any('nik_raw' in sql for sql in conn.alters)
        first = list(conn.alters)
        assert ensure_cv_online_nik_columns(conn) is True
        assert conn.alters == first  # tidak ada ALTER kedua kalinya
        assert conn.commits == 2

    def test_helper_tidak_menutup_koneksi_yang_diberikan(self):
        from modules.cv_online_schema import ensure_cv_online_nik_columns
        conn = _SchemaConn()
        assert ensure_cv_online_nik_columns(conn) is True
        assert conn.closed is False

    def test_ddl_fresh_install_juga_memiliki_kolom(self):
        source = (ROOT / 'modules' / 'cv_online_schema.py').read_text(encoding='utf-8')
        assert re.search(r'\bnik\s+CHAR\(16\)', source, re.I)
        assert re.search(r'\bnik_raw\s+VARCHAR\(32\)', source, re.I)

    def test_init_sql_memiliki_kolom_nik(self):
        from scripts.check_schema_drift import parse_init_sql
        sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
        columns = parse_init_sql(sql)['cv_online_submissions']
        assert 'nik' in columns
        assert 'nik_raw' in columns

    def test_startup_memanggil_helper_setelah_ensure_cv_online_schema(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        assert 'ensure_cv_online_nik_columns()' in app
        assert app.index('ensure_cv_online_nik_columns()') > app.index(
            'ensure_cv_online_schema()')
