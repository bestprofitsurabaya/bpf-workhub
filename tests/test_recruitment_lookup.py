"""Regresi endpoint lookup publik rekrutmen (Rilis A — Task 3).

Kontrak: `GET /api/recruitment/lookup?nik=<16 digit>&dob=YYYY-MM-DD`
hanya mengembalikan boolean (`known`, `can_continue`) — tidak ada cabang,
tahap, nama, atau data pribadi lain. Lookup adalah operasi baca murni:
tidak boleh ada INSERT/UPDATE, walaupun NIK belum dikenal.

Semua pengujian memakai DB master palsu dan rate limit memori (tanpa Redis
atau MySQL), mengikuti pola `tests/test_cv_online_nik.py`.
"""
import os
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers as hp  # noqa: E402
from modules import routes_recruitment as rr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NIK = '3573010101990001'
NIK_LAIN = '3573010101990002'
DOB = '1999-01-01'
TABLES = ('recruitment_cases', 'cv_online_submissions', 'first_work_submissions')


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
        table = next((t for t in TABLES if t.upper() in upper), None)
        if not upper.startswith('SELECT') or not table or 'NIK=%S' not in upper:
            self._rows = None
            return
        nik = params[0] if params else ''
        matches = [row for row in self.conn.tables.get(table, [])
                   if str(row.get('nik') or '') == str(nik)]
        if 'COUNT(*)' in upper:
            self._rows = {'n': len(matches)}
        else:
            self._rows = matches[0] if matches else None

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


def _lookup(client, nik=NIK, dob=DOB, ip=None, **extra):
    headers = {'X-Real-IP': ip} if ip else {}
    return client.get('/api/recruitment/lookup',
                      query_string={'nik': nik, 'dob': dob, **extra},
                      headers=headers)


class TestLookupBooleanOnly:
    def test_nik_baru_mengembalikan_known_false(self, client, db):
        response = _lookup(client)

        assert response.status_code == 200
        assert response.get_json() == {
            'status': 'success', 'known': False, 'can_continue': False,
        }
        assert response.headers['Cache-Control'] == 'no-store'
        assert db.closed is True

    def test_tidak_ada_branch_step_atau_detail_pribadi(self, client, db):
        db.tables['recruitment_cases'].append(db.baris(NIK, 'SBY'))

        data = _lookup(client).get_json()

        assert data['known'] is True
        for key in ('branch', 'branch_code', 'step', 'nama', 'name'):
            assert key not in data

    def test_nik_di_first_work_cabang_lain_dikenali(self, client, db):
        db.tables['first_work_submissions'].append(db.baris(NIK, 'SBY'))

        data = _lookup(client, cabang='JKT').get_json()

        assert data['known'] is True
        assert data['can_continue'] is True

    def test_nik_di_cv_online_dikenali(self, client, db):
        db.tables['cv_online_submissions'].append(db.baris(NIK, 'MLG'))

        data = _lookup(client).get_json()

        assert data == {'status': 'success', 'known': True, 'can_continue': True}

    def test_nik_di_recruitment_cases_dikenali(self, client, db):
        db.tables['recruitment_cases'].append(db.baris(NIK, 'JKT'))

        data = _lookup(client).get_json()

        assert data['known'] is True

    def test_nik_dinormalisasi_seperti_first_work(self, client, db):
        db.tables['first_work_submissions'].append(db.baris(NIK, 'SBY'))

        data = _lookup(client, nik='3573 0101 0199 0001').get_json()

        assert data['known'] is True

    def test_nik_tidak_ditemukan_tetap_false(self, client, db):
        db.tables['first_work_submissions'].append(db.baris(NIK_LAIN, 'SBY'))

        data = _lookup(client).get_json()

        assert data['known'] is False
        assert data['can_continue'] is False

    @pytest.mark.parametrize('nik, dalam_db, expected_known', [
        (NIK, False, False),   # NIK valid, belum terdaftar
        (NIK, True, True),     # NIK valid, terdaftar
        ('12345', False, False),  # NIK invalid — tanpa menyentuh DB
    ])
    def test_kontrak_tiga_kunci_sama_untuk_input_valid_dan_invalid(
            self, client, db, nik, dalam_db, expected_known):
        if dalam_db:
            db.tables['first_work_submissions'].append(db.baris(NIK, 'SBY'))

        data = _lookup(client, nik=nik).get_json()

        assert set(data) == {'status', 'known', 'can_continue'}
        assert data == {'status': 'success', 'known': expected_known,
                        'can_continue': expected_known}


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
        assert response.get_json() == {
            'status': 'success', 'known': False, 'can_continue': False,
        }
        assert response.headers['Cache-Control'] == 'no-store'

    @pytest.mark.parametrize('dob', ['', '01-01-1999', '1999-02-30', '1999/01/01'])
    def test_dob_invalid_sukses_tanpa_menyentuh_db(self, client, monkeypatch, dob):
        def _tidak_boleh_db():
            raise AssertionError('DB tidak boleh disentuh untuk DOB invalid')

        monkeypatch.setattr(rr, 'get_master_connection', _tidak_boleh_db)

        response = _lookup(client, dob=dob)

        assert response.status_code == 200
        assert response.get_json() == {
            'status': 'success', 'known': False, 'can_continue': False,
        }


class TestRateLimit:
    def test_10_permintaan_per_menit_per_ip(self, client, db):
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
