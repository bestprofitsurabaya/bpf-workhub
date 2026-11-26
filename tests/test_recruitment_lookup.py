"""Regresi endpoint lookup publik rekrutmen (Rilis C — NIK-only + token cabang).

`GET /api/recruitment/lookup?nik=<16 digit>&token=<token cabang>` menjawab
keberadaan NIK lintas cabang dan menerbitkan `session_token` untuk satu sesi
portal. Tidak ada DOB, cabang dari input pengguna, nama, atau tahap di respons.
"""
import os
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers as hp  # noqa: E402
from modules import routes_recruitment as rr  # noqa: E402
from modules.portal_token import verify_session_token  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NIK = '3573010101900001'
BRANCH_TOKEN = 'tok-sby-rahasia'
TABLES = ('recruitment_cases', 'cv_online_submissions', 'first_work_submissions',
          'cv_online_branch_forms')


@pytest.fixture(autouse=True)
def _tanpa_rate_limit(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = None

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append(upper)
        params = tuple(params or ())
        if 'CV_ONLINE_BRANCH_FORMS' in upper:
            self._rows = [row for row in self.conn.tables['cv_online_branch_forms']
                          if str(row.get('form_token')) == str(params[0])
                          and int(row.get('active') or 0) == 1]
            return
        table = next((t for t in TABLES[:3] if t.upper() in upper), None)
        if not upper.startswith('SELECT') or not table or 'NIK=%S' not in upper:
            self._rows = None
            return
        nik = params[0] if params else ''
        matches = [row for row in self.conn.tables.get(table, [])
                   if str(row.get('nik') or '') == str(nik)]
        self._rows = {'n': len(matches)} if 'COUNT(*)' in upper else matches

    def fetchone(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows

    def fetchall(self):
        return self._rows if isinstance(self._rows, list) else []

    def close(self):
        pass


class _FakeConn:
    def __init__(self, **tables):
        self.tables = {name: [] for name in TABLES}
        self.tables.update(tables)
        self.tables['cv_online_branch_forms'] = (
            self.tables['cv_online_branch_forms'] or
            [{'branch_code': 'SBY', 'form_token': BRANCH_TOKEN, 'active': 1}])
        self.statements = []
        self.commits = 0
        self.closed = False

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True

    def baris(self, nik, branch_code='SBY'):
        return {'nik': nik, 'branch_code': branch_code}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'test-recruitment-lookup'
    rr.register_recruitment_routes(app)
    return app.test_client()


@pytest.fixture
def db(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)
    return conn


def _lookup(client, nik=NIK, token=BRANCH_TOKEN, ip=None, **extra):
    headers = {'X-Real-IP': ip} if ip else {}
    return client.get('/api/recruitment/lookup',
                      query_string={'nik': nik, 'token': token, **extra},
                      headers=headers)


class TestLookupNikOnly:
    def test_nik_baru_mendapat_session_token_dari_cabang_token(self, client, db):
        response = _lookup(client)
        data = response.get_json()
        assert response.status_code == 200
        assert data['known'] is False
        assert data['can_continue'] is False
        assert response.headers['Cache-Control'] == 'no-store'
        with client.application.test_request_context('/'):
            parsed = verify_session_token(data['session_token'])
        assert parsed == {'nik': NIK, 'branch': 'SBY', 'purpose': 'portal'}
        assert db.closed is True

    def test_tidak_ada_branch_step_atau_detail_pribadi(self, client, db):
        db.tables['recruitment_cases'].append(db.baris(NIK, 'JKT'))
        data = _lookup(client).get_json()
        assert data['known'] is True
        for key in ('branch', 'branch_code', 'step', 'nama', 'name',
                    'tanggal_lahir', 'dob'):
            assert key not in data
        assert NIK not in str(data)

    def test_nik_di_first_work_cabang_lain_dikenali(self, client, db):
        db.tables['first_work_submissions'].append(db.baris(NIK, 'SBY'))
        data = _lookup(client, token=BRANCH_TOKEN).get_json()
        assert data['known'] is True
        assert data['can_continue'] is True

    def test_nik_di_cv_online_dikenali(self, client, db):
        db.tables['cv_online_submissions'].append(db.baris(NIK, 'MLG'))
        assert _lookup(client).get_json()['known'] is True

    def test_nik_di_recruitment_cases_dikenali(self, client, db):
        db.tables['recruitment_cases'].append(db.baris(NIK, 'JKT'))
        assert _lookup(client).get_json()['known'] is True

    def test_nik_dinormalisasi_seperti_first_work(self, client, db):
        db.tables['first_work_submissions'].append(db.baris(NIK, 'SBY'))
        assert _lookup(client, nik='3573 0101 0190 0001').get_json()['known'] is True

    def test_nik_tidak_ditemukan_tetap_false(self, client, db):
        db.tables['first_work_submissions'].append(db.baris('3573010101900002'))
        data = _lookup(client).get_json()
        assert data['known'] is False
        assert data['session_token']

    def test_token_cabang_salah_403(self, client, db):
        response = _lookup(client, token='salah')
        assert response.status_code == 403
        # Token salah tidak boleh memicu pencarian NIK ke tabel mana pun.
        assert not any('WHERE NIK=%S' in s for s in db.statements)

    def test_token_cabang_nonaktif_403(self, client, db):
        db.tables['cv_online_branch_forms'][0]['active'] = 0
        assert _lookup(client).status_code == 403


class TestLookupBacaSaja:
    def test_tidak_menulis_row_walaupun_nik_baru(self, client, db):
        response = _lookup(client)
        assert response.status_code == 200
        tulis = [s for s in db.statements
                 if s.startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))]
        assert tulis == []
        assert db.commits == 0

    @pytest.mark.parametrize('nik', ['', '12345', NIK[:-1], NIK + '1', '1,23E+15'])
    def test_nik_invalid_sukses_tanpa_menyentuh_db(self, client, monkeypatch, nik):
        def _tidak_boleh_db():
            raise AssertionError('DB tidak boleh disentuh untuk NIK invalid')
        monkeypatch.setattr(rr, 'get_master_connection', _tidak_boleh_db)
        response = _lookup(client, nik=nik)
        assert response.status_code == 200
        data = response.get_json()
        assert data['known'] is False
        assert data['can_continue'] is False
        assert 'session_token' not in data
        assert response.headers['Cache-Control'] == 'no-store'

    def test_dob_diabaikan(self, client, db):
        # Parameter lama tetap diterima, tetapi tidak memengaruhi respons.
        data = _lookup(client, dob='1990-02-30').get_json()
        assert data['known'] is False


class TestRateLimit:
    def test_10_permintaan_per_10_menit_per_ip(self, client, db):
        responses = [_lookup(client, ip='203.0.113.7') for _ in range(11)]
        statuses = [response.status_code for response in responses]
        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429
        assert responses[-1].headers['Cache-Control'] == 'no-store'

    def test_ip_lain_tidak_terkunci(self, client, db):
        for _ in range(10):
            assert _lookup(client, ip='203.0.113.8').status_code == 200
        assert _lookup(client, ip='203.0.113.8').status_code == 429
        assert _lookup(client, ip='203.0.113.9').status_code == 200


def test_route_didaftarkan_di_app():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'from modules.routes_recruitment import register_recruitment_routes' in source
    assert 'register_recruitment_routes(app)' in source
