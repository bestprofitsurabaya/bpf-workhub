"""Regresi endpoint lookup publik rekrutmen (Rilis A — Task 3).

Kontrak dasar: `GET /api/recruitment/lookup?nik=<16 digit>` mengembalikan
`known`/`can_continue` plus ringkasan tahap yang sudah disanitasi. Sejak
v2.135.12, bila tautan membawa token cabang yang sah dan NIK punya riwayat di
cabang lain, respons boleh memuat `branch_history` (nama cabang + tanggal
pertama) sebagai informasi saja — tanpa NIK, case_id, atau kode cabang.
Lookup tetap operasi baca murni: tidak boleh ada INSERT/UPDATE, walaupun NIK
belum dikenal.

Semua pengujian memakai DB master palsu dan rate limit memori (tanpa Redis
atau MySQL), mengikuti pola `tests/test_cv_online_nik.py`.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers as hp  # noqa: E402
from modules import routes_recruitment as rr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NIK = '3573010101990001'
NIK_LAIN = '3573010101990002'
TABLES = ('recruitment_cases', 'cv_online_submissions', 'first_work_submissions',
          'recruitment_steps', 'case_branch_history', 'cv_online_branch_forms',
          'branches')


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
        if not upper.startswith('SELECT') or not table:
            self._rows = None
            return
        if table == 'recruitment_steps' and 'CASE_ID=%S' in upper:
            # SQL sudah memfilter case_id; baris tiruan sengaja tanpa case_id
            # seperti hasil SELECT produksi.
            self._rows = list(self.conn.tables[table])
            return
        if table == 'case_branch_history' and 'CASE_ID=%S' in upper:
            case_id = params[0] if params else ''
            self._rows = [row for row in self.conn.tables[table]
                          if str(row.get('case_id') or '') == str(case_id)]
            return
        if table == 'cv_online_branch_forms' and 'FORM_TOKEN=%S' in upper:
            token = params[0] if params else ''
            self._rows = next(
                (row for row in self.conn.tables[table]
                 if str(row.get('form_token') or '') == str(token)), None)
            return
        if table == 'branches':
            if 'CODE IN' in upper:
                codes = {str(code).upper() for code in params}
                self._rows = [row for row in self.conn.tables[table]
                              if str(row.get('code') or '').upper() in codes]
            else:
                self._rows = list(self.conn.tables[table])
            return
        if 'NIK=%S' not in upper:
            self._rows = None
            return
        nik = params[0] if params else ''
        matches = [row for row in self.conn.tables.get(table, [])
                   if str(row.get('nik') or '') == str(nik)]
        if 'COUNT(*)' in upper:
            self._rows = {'n': len(matches)}
        elif table in ('cv_online_submissions', 'first_work_submissions'):
            # Fallback riwayat butuh SEMUA baris NIK, bukan baris pertama.
            self._rows = matches
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


def _lookup(client, nik=NIK, ip=None, **extra):
    headers = {'X-Real-IP': ip} if ip else {}
    return client.get('/api/recruitment/lookup',
                      query_string={'nik': nik, **extra},
                      headers=headers)


class TestLookupBooleanOnly:
    def test_nik_baru_mengembalikan_known_false(self, client, db):
        response = _lookup(client)

        assert response.status_code == 200
        data = response.get_json()
        assert {key: data[key] for key in ('status', 'known', 'can_continue')} == {
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

        assert {key: data[key] for key in ('status', 'known', 'can_continue')} == {
            'status': 'success', 'known': True, 'can_continue': True}

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

        assert data['status'] == 'success'
        assert data['known'] is expected_known
        assert data['can_continue'] is expected_known
        if nik == '12345':
            assert set(data) == {'status', 'known', 'can_continue'}


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

    def test_nik_valid_tanpa_tanggal_lahir_tetap_dicek(self, client, db):
        db.tables['recruitment_cases'].append(db.baris(NIK, 'SBY'))

        response = _lookup(client)

        assert response.status_code == 200
        data = response.get_json()
        assert data['known'] is True
        assert data['can_continue'] is True


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


def test_lookup_menyertakan_status_tahap(client, db):
    db.tables['recruitment_cases'].append({
        'case_id': 'RC-1', 'nik': NIK, 'nama': 'Bili Darnanto Susilo'})
    db.tables['recruitment_steps'] = [
        {'step_type': 'CV', 'status': 'SELESAI',
         'completed_at': '2026-11-25 19:28:30', 'branch_code': 'SBY'},
        {'step_type': 'TKD', 'status': 'SELESAI',
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
    assert data['nama_masked'] == 'Bili D.'


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
        {'step_type': 'CV', 'status': 'PENDING', 'completed_at': None},
        {'step_type': 'CV', 'status': 'SELESAI',
         'completed_at': '2026-11-25 19:28:30'},
    ]
    data = _lookup(client).get_json()
    assert data['stages'][0]['status'] == 'SELESAI'
    assert data['stages'][0]['completed_at'] == '2026-11-25 19:28:30'


def test_lookup_invalid_tetap_kontrak_lama(client, db):
    data = _lookup(client, nik='12345').get_json()
    assert set(data) == {'status', 'known', 'can_continue'}


class TestRiwayatCabangLain:
    """Info "pernah tercatat di cabang lain" — hanya lewat token cabang sah."""

    TOKEN = 'tok_portal_sby_uji'

    def _token(self, db, code='SBY', token=TOKEN):
        db.tables['cv_online_branch_forms'].append(
            {'branch_code': code, 'form_token': token, 'active': 1})

    def _kasus(self, db, first_branch='SBY', case_id='RC-uji123'):
        db.tables['recruitment_cases'].append({
            'nik': NIK, 'case_id': case_id, 'first_branch': first_branch,
            'first_seen_at': datetime(2026, 10, 1, 8, 30),
        })
        db.tables['branches'] += [
            {'code': 'SBY', 'name': 'Cabang Surabaya'},
            {'code': 'MLG', 'name': 'Cabang Malang'},
            {'code': 'JKT', 'name': 'Cabang Jakarta'},
        ]
        return case_id

    def _jejak(self, db, case_id, code, when):
        db.tables['case_branch_history'].append({
            'case_id': case_id, 'branch_code': code, 'first_seen_at': when,
            'last_seen_at': when,
        })

    def test_cabang_lain_dilaporkan_tanpa_kode_nik_atau_case_id(self, client, db):
        self._token(db)
        case_id = self._kasus(db)
        self._jejak(db, case_id, 'SBY', datetime(2026, 10, 1, 8, 30))
        self._jejak(db, case_id, 'MLG', datetime(2026, 10, 12, 9, 15))

        data = _lookup(client, token=self.TOKEN).get_json()

        assert data['branch_history'] == {
            'other_branch_count': 1,
            'first_seen_at': '2026-10-12',
            'branch_names': ['Cabang Malang'],
        }
        import json
        teks = json.dumps(data)
        for rahasia in (NIK, case_id, 'MLG'):
            assert rahasia not in teks

    def test_beberapa_cabang_lain_dihitung_dengan_tanggal_terawal(self, client, db):
        self._token(db)
        case_id = self._kasus(db)
        self._jejak(db, case_id, 'SBY', datetime(2026, 10, 1, 8, 30))
        self._jejak(db, case_id, 'MLG', datetime(2026, 10, 20, 14, 0))
        self._jejak(db, case_id, 'JKT', datetime(2026, 10, 5, 10, 0))

        data = _lookup(client, token=self.TOKEN).get_json()

        assert data['branch_history'] == {
            'other_branch_count': 2,
            'first_seen_at': '2026-10-05',
            'branch_names': ['Cabang Jakarta', 'Cabang Malang'],
        }

    def test_riwayat_cabang_sendiri_tidak_memicu_info(self, client, db):
        self._token(db)
        case_id = self._kasus(db)
        self._jejak(db, case_id, 'SBY', datetime(2026, 10, 1, 8, 30))

        data = _lookup(client, token=self.TOKEN).get_json()

        assert data['known'] is True
        assert 'branch_history' not in data

    def test_cabang_asal_dipakai_bila_jejak_belum_ada(self, client, db):
        self._token(db)
        self._kasus(db, first_branch='MLG')

        data = _lookup(client, token=self.TOKEN).get_json()

        assert data['branch_history'] == {
            'other_branch_count': 1,
            'first_seen_at': '2026-10-01',
            'branch_names': ['Cabang Malang'],
        }

    def test_data_lama_tanpa_kasus_tetap_terbaca(self, client, db):
        self._token(db)
        db.tables['cv_online_submissions'].append({
            'nik': NIK, 'branch_code': 'MLG',
            'submitted_at': datetime(2026, 9, 3, 11, 0),
        })
        db.tables['branches'].append({'code': 'MLG', 'name': 'Cabang Malang'})

        data = _lookup(client, token=self.TOKEN).get_json()

        assert data['branch_history'] == {
            'other_branch_count': 1,
            'first_seen_at': '2026-09-03',
            'branch_names': ['Cabang Malang'],
        }

    def test_tanpa_token_tidak_membuka_riwayat(self, client, db):
        case_id = self._kasus(db)
        self._jejak(db, case_id, 'MLG', datetime(2026, 10, 12, 9, 15))

        data = _lookup(client).get_json()

        assert data['known'] is True
        assert 'branch_history' not in data

    def test_token_tidak_sah_tidak_membuka_riwayat(self, client, db):
        case_id = self._kasus(db)
        self._jejak(db, case_id, 'MLG', datetime(2026, 10, 12, 9, 15))

        data = _lookup(client, token='token-palsu').get_json()

        assert data['known'] is True
        assert 'branch_history' not in data
