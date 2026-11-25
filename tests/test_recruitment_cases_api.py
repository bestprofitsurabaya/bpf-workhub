"""Regresi endpoint daftar kasus rekrutmen staff (Task 5 — fix round 1/2).

`GET /api/recruitment/cases` dipakai dashboard Task 6. Kontraknya: hanya staff
(traineer/ga_hr/admin), NIK pada respons dan audit HANYA 4 digit terakhir,
filter opsional (nik/branch_code/status) aman untuk nilai yang tidak dikenal,
serta riwayat cabang + langkah ikut tersirat per kasus.

Memakai DB master palsu dan logger audit palsu — tidak ada MySQL/thread pool.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from flask import Flask  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import routes_recruitment as rr  # noqa: E402

NIK_A = '3573010101990001'
NIK_B = '3573010101990002'
# Fix round 2: case_id bersifat opaque (bukan RC-<NIK>) dan tidak dimasker.
CASE_A = 'RC-a1b2c3d4e5f6'
CASE_B = 'RC-f6e5d4c3b2a1'


class _FakeCursor:
    """Cursor baca saja untuk tiga query yang dipakai endpoint cases."""

    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        params = list(params or ())
        self.conn.statements.append((upper, tuple(params)))

        if 'FROM RECRUITMENT_CASES' in upper:
            idx = 0
            nik = branch = status = None
            if 'C.NIK=%S' in upper:
                nik = params[idx]
                idx += 1
            if 'C.FIRST_BRANCH=%S' in upper or 'BRANCH_CODE=%S' in upper:
                branch = params[idx]
                idx += 1 + upper.count('BRANCH_CODE=%S')
            if 'C.STATUS=%S' in upper:
                status = params[idx]

            rows = []
            for case in self.conn.cases:
                if nik is not None and case.get('nik') != nik:
                    continue
                if status is not None and (case.get('status') or '') != status:
                    continue
                if branch is not None:
                    history = any(b['case_id'] == case['case_id']
                                  and b['branch_code'] == branch
                                  for b in self.conn.branches)
                    steps = any(s['case_id'] == case['case_id']
                                and s['branch_code'] == branch
                                for s in self.conn.steps)
                    if not (case.get('first_branch') == branch
                            or history or steps):
                        continue
                rows.append(case)
            rows.sort(key=lambda r: str(r.get('first_seen_at') or ''),
                      reverse=True)
            self._rows = rows[:100]
            return

        if 'FROM CASE_BRANCH_HISTORY' in upper:
            ids = set(params)
            self._rows = [b for b in self.conn.branches
                          if b['case_id'] in ids]
            return

        if 'FROM RECRUITMENT_STEPS' in upper:
            ids = set(params)
            self._rows = [s for s in self.conn.steps
                          if s['case_id'] in ids]
            return

        self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.cases = [
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
        ]
        self.branches = [
            {'case_id': CASE_A, 'branch_code': 'SBY',
             'first_seen_at': datetime(2026, 11, 20, 10, 0),
             'last_seen_at': datetime(2026, 11, 21, 11, 0)},
            {'case_id': CASE_A, 'branch_code': 'JKT',
             'first_seen_at': datetime(2026, 11, 21, 11, 0),
             'last_seen_at': datetime(2026, 11, 21, 11, 0)},
        ]
        self.steps = [
            {'id': 11, 'case_id': CASE_A, 'step_type': 'CV', 'status': 'SELESAI',
             'branch_code': 'SBY', 'exception_reason': None,
             'completed_at': datetime(2026, 11, 20, 10, 5)},
            {'id': 14, 'case_id': CASE_A, 'step_type': 'FIRSTWORK',
             'status': 'DIKECUALIKAN', 'branch_code': 'JKT',
             'exception_reason': 'Tidak hadir',
             'completed_at': datetime(2026, 11, 21, 11, 0)},
        ]
        self.statements = []
        self.closed = False

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.secret_key = 'test-recruitment-cases'
    rr.register_recruitment_routes(flask_app)
    return flask_app


@pytest.fixture
def db(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)
    return conn


@pytest.fixture
def logs(monkeypatch):
    captured = []
    monkeypatch.setattr(rr, 'log_activity_async',
                        lambda *args, **kwargs: captured.append((args, kwargs)),
                        raising=False)
    return captured


def _get(app, role='traineer', name='petugas1', **query):
    client = app.test_client()
    if role is not None:
        with client.session_transaction() as sess:
            sess['user_role'] = role
            sess['user_name'] = name
    return client.get('/api/recruitment/cases', query_string=query)


class TestAksesStaff:
    @pytest.mark.parametrize('role', ['traineer', 'ga_hr', 'admin'])
    def test_role_staff_bisa_membaca(self, app, db, logs, role):
        response = _get(app, role=role)

        assert response.status_code == 200
        assert len(response.get_json()['data']) == 2
        assert db.closed is True

    @pytest.mark.parametrize('role', ['driver', 'finance', 'ga'])
    def test_role_lain_ditolak_403(self, app, db, logs, role):
        response = _get(app, role=role)

        assert response.status_code == 403
        assert db.statements == []
        assert logs == []

    def test_tanpa_login_ditolak_401(self, app, db, logs):
        assert _get(app, role=None).status_code == 401
        assert logs == []


class TestKontrakRespons:
    def test_nik_disamarkan_empat_digit_terakhir(self, app, db, logs):
        response = _get(app)

        assert response.status_code == 200
        payload = response.get_json()
        assert set(payload) == {'data'}
        masked = {case['nik_masked'] for case in payload['data']}
        assert masked == {'****0001', '****0002'}
        assert NIK_A not in json.dumps(payload)
        assert NIK_B not in json.dumps(payload)

    def test_field_kasus_lengkap(self, app, db, logs):
        case = _get(app).get_json()['data'][0]  # first_seen_at terbaru = CASE_B

        assert set(case) == {'case_id', 'nik_masked', 'nama', 'first_branch',
                             'status', 'branches', 'steps', 'tkd_score',
                             'tkd_score_source', 'tkd_score_note', 'tkd_passed'}
        assert case['case_id'] == CASE_B
        assert NIK_B not in case['case_id']
        assert case['nama'] == 'Budi'
        assert case['first_branch'] == 'JKT'
        assert case['status'] == 'NONAKTIF'
        assert case['tkd_score'] is None and case['tkd_passed'] is None

    def test_skor_tkd_ikut_di_level_kasus(self, app, db, logs):
        case = next(c for c in _get(app).get_json()['data']
                    if c['case_id'] == CASE_A)

        assert case['tkd_score'] == 86.67
        assert case['tkd_score_source'] == 'AUTO'
        assert case['tkd_passed'] == 1

    def test_riwayat_cabang_dan_langkah_termasuk(self, app, db, logs):
        case = next(c for c in _get(app).get_json()['data']
                    if c['case_id'] == CASE_A)

        assert len(case['branches']) == 2
        assert set(case['branches'][0]) == {'branch_code', 'first_seen_at',
                                            'last_seen_at'}
        assert {b['branch_code'] for b in case['branches']} == {'SBY', 'JKT'}
        sby = next(b for b in case['branches'] if b['branch_code'] == 'SBY')
        assert sby['last_seen_at'] == '2026-11-21 11:00:00'

        assert len(case['steps']) == 2
        # Task 6: id langkah dibutuhkan tombol exception di dashboard staff.
        assert set(case['steps'][0]) == {'id', 'step_type', 'status',
                                         'branch_code', 'exception_reason',
                                         'completed_at'}
        assert {s['id'] for s in case['steps']} == {11, 14}
        excluded = next(s for s in case['steps']
                        if s['status'] == 'DIKECUALIKAN')
        assert excluded['exception_reason'] == 'Tidak hadir'
        assert excluded['completed_at'] == '2026-11-21 11:00:00'
        assert case['steps'][0]['completed_at'] == '2026-11-20 10:05:00'

    def test_case_id_sama_persis_dengan_yang_tersimpan(self, app, db, logs):
        cases = _get(app).get_json()['data']
        tersimpan = {row['case_id'] for row in db.cases}

        assert {case['case_id'] for case in cases} == tersimpan
        assert CASE_A in tersimpan and CASE_B in tersimpan

    def test_case_id_tidak_berasal_dari_nik(self, app, db, logs):
        cases = _get(app).get_json()['data']

        for case in cases:
            assert case['case_id'].startswith('RC-')
            assert NIK_A not in case['case_id']
            assert NIK_B not in case['case_id']


def test_route_tidak_memasker_case_id():
    source = (Path(__file__).resolve().parents[1] / 'modules'
              / 'routes_recruitment.py').read_text(encoding='utf-8')
    assert '_mask_case_id' not in source


class TestFilter:
    def test_filter_nik_dinormalisasi(self, app, db, logs):
        response = _get(app, nik='3573 0101 0199 0002')

        assert [c['case_id'] for c in response.get_json()['data']] == [CASE_B]

    def test_filter_nik_tidak_ada_mengembalikan_kosong(self, app, db, logs):
        response = _get(app, nik='3573010101999999')

        assert response.get_json() == {'data': []}

    def test_nik_invalid_tidak_menyentuh_db(self, app, db, logs, monkeypatch):
        def _tidak_boleh_db():
            raise AssertionError('DB tidak boleh disentuh untuk NIK invalid')

        monkeypatch.setattr(rr, 'get_master_connection', _tidak_boleh_db)

        response = _get(app, nik='12345')

        assert response.status_code == 200
        assert response.get_json() == {'data': []}

    def test_filter_branch_code_lewat_riwayat_atau_langkah(self, app, db, logs):
        assert {c['case_id'] for c in _get(app, branch_code='JKT')
                .get_json()['data']} == {CASE_A, CASE_B}
        assert [c['case_id'] for c in _get(app, branch_code='SBY')
                .get_json()['data']] == [CASE_A]

    def test_filter_branch_code_tidak_dikenal_kosong(self, app, db, logs):
        assert _get(app, branch_code='XXX').get_json() == {'data': []}

    def test_filter_status_kasus(self, app, db, logs):
        assert [c['case_id'] for c in _get(app, status='AKTIF')
                .get_json()['data']] == [CASE_A]
        assert _get(app, status='SELESAI').get_json() == {'data': []}

    def test_filter_gabungan(self, app, db, logs):
        response = _get(app, nik=NIK_A, branch_code='SBY', status='AKTIF')

        assert [c['case_id'] for c in response.get_json()['data']] == [CASE_A]
        assert _get(app, nik=NIK_A, status='NONAKTIF').get_json() == {'data': []}

    def test_urutan_terbaru_dulu_dan_maks_100(self, app, db, logs):
        for n in range(100):
            db.cases.append({
                'case_id': f'RC-EXTRA-{n:03d}', 'nik': f'900000000000{n:04d}'[:16],
                'nama': 'X', 'first_branch': 'SBY', 'status': 'AKTIF',
                'first_seen_at': datetime(2026, 11, 23, 0, n // 60, n % 60),
            })

        data = _get(app).get_json()['data']

        assert len(data) == 100
        first = [c['case_id'] for c in data[:3]]
        assert first == ['RC-EXTRA-099', 'RC-EXTRA-098', 'RC-EXTRA-097']


class TestAuditView:
    def test_audit_mencatat_nik_termasker_dan_jumlah(self, app, db, logs):
        response = _get(app, nik=NIK_B)

        assert response.status_code == 200
        assert len(logs) == 1
        args, kwargs = logs[0]
        assert args == (None, 'recruitment_cases_view', 'traineer', 'petugas1')
        assert kwargs['new_data'] == {'nik_masked': '****0002', 'count': 1}

    def test_audit_tanpa_filter_tidak_membocorkan_nik(self, app, db, logs):
        _get(app)

        assert logs[0][1]['new_data'] == {'nik_masked': '****', 'count': 2}

    def test_audit_gagal_tidak_mengganggu_pembacaan(self, app, db, monkeypatch):
        def _audit_error(*args, **kwargs):
            raise RuntimeError('audit down')

        monkeypatch.setattr(rr, 'log_activity_async', _audit_error)

        response = _get(app)

        assert response.status_code == 200
        assert len(response.get_json()['data']) == 2
