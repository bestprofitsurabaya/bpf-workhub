"""Regresi exception langkah rekrutmen per orang (Rilis A — Task 5).

Kontrak: `POST /api/recruitment/steps/<id>/exception` dengan body
`{'reason': str}` hanya untuk staff (traineer/ga_hr/admin). Langkah boleh
dikecualikan hanya dari status `BELUM`/`PENDING`, alasan wajib dan maksimal
500 karakter. Sukses menulis `DIKECUALIKAN` + alasan + actor + `NOW()` di
DB master dan mencatat audit `recruitment_step_exception`.

Semua pengujian memakai DB master palsu dan logger audit palsu (tanpa MySQL,
Redis, atau thread pool), mengikuti pola `tests/test_recruitment_lookup.py`.
"""
import os
import sys

import pytest
from flask import Flask  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import routes_recruitment as rr  # noqa: E402

STAFF_ROLES = ('traineer', 'ga_hr', 'admin')
ALLOWED_FROM = ('BELUM', 'PENDING')
DIALLOWED_FROM = ('SELESAI', 'DIKECUALIKAN')


class _FakeCursor:
    """Cursor minimal: baca baris langkah dan terapkan UPDATE generik."""

    def __init__(self, conn):
        self.conn = conn
        self._rows = None

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append(upper)
        params = list(params or ())
        if upper.startswith('SELECT') and 'FROM RECRUITMENT_STEPS' in upper:
            self._rows = self.conn.steps.get(params[0])
            return
        if upper.startswith('UPDATE') and 'RECRUITMENT_STEPS' in upper:
            set_part = upper.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
            changes = {}
            i = 0
            for chunk in set_part.split(','):
                col, _, rhs = chunk.strip().partition('=')
                col = col.strip().lower()
                rhs = rhs.strip()
                if rhs == '%S':
                    changes[col] = params[i]
                    i += 1
                elif 'NOW()' in rhs:
                    changes[col] = 'NOW()'
                elif len(rhs) >= 2 and rhs[0] == rhs[-1] == "'":
                    changes[col] = rhs[1:-1]
            step_id = params[-1]
            row = self.conn.steps.get(step_id)
            if row is not None:
                row.update(changes)
            self.conn.updates.append((step_id, changes))

    def fetchone(self):
        return self._rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, step_id=7, status='BELUM'):
        self.steps = {step_id: {
            'id': step_id, 'case_id': 'RC-3573010101990001',
            'step_type': 'CV', 'status': status,
            'exception_reason': None, 'actor': '', 'completed_at': None,
        }} if step_id is not None else {}
        self.statements = []
        self.updates = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.secret_key = 'test-recruitment-exception'
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


@pytest.fixture(autouse=True)
def _scope_allowed(monkeypatch):
    """Default tes lama: langkah dianggap dalam cabang petugas."""
    monkeypatch.setattr(rr, '_case_scope_ok',
                        lambda cursor, case_id, scope: True)


def _post(app, reason='Tidak hadir', step_id=7, role='traineer', name='petugas1'):
    client = app.test_client()
    if role is not None:
        with client.session_transaction() as sess:
            sess['user_role'] = role
            sess['user_name'] = name
    return client.post(f'/api/recruitment/steps/{step_id}/exception',
                       json={'reason': reason})


class TestValidasiAlasan:
    @pytest.mark.parametrize('reason', ['', '   ', '\t\n ', None])
    def test_alasan_kosong_ditolak_400(self, app, db, logs, reason):
        response = _post(app, reason=reason)

        assert response.status_code == 400
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    @pytest.mark.parametrize('reason', [123, ['alasan'], {'teks': 'alasan'}])
    def test_alasan_bukan_string_ditolak_400(self, app, db, logs, reason):
        response = _post(app, reason=reason)

        assert response.status_code == 400
        assert db.updates == []
        assert logs == []

    def test_alasan_lebih_500_karakter_ditolak_400(self, app, db, logs):
        response = _post(app, reason='x' * 501)

        assert response.status_code == 400
        assert db.updates == []
        assert logs == []

    def test_tanpa_body_json_ditolak_400(self, app, db, logs):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_role'] = 'traineer'
            sess['user_name'] = 'petugas1'

        response = client.post('/api/recruitment/steps/7/exception')

        assert response.status_code == 400
        assert db.updates == []


class TestTransisiStatus:
    @pytest.mark.parametrize('status', ALLOWED_FROM)
    def test_status_boleh_dikecualikan(self, app, db, logs, status):
        db.steps[7]['status'] = status

        response = _post(app, reason='  Pelamar mengundurkan diri  ')

        assert response.status_code == 200
        step = db.steps[7]
        assert step['status'] == 'DIKECUALIKAN'
        assert step['exception_reason'] == 'Pelamar mengundurkan diri'
        assert step['actor'] == 'petugas1'
        assert step['completed_at'] == 'NOW()'
        assert db.commits == 1
        assert db.closed is True
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'DIKECUALIKAN'

    @pytest.mark.parametrize('status', DIALLOWED_FROM)
    def test_status_terkunci_ditolak_409(self, app, db, logs, status):
        db.steps[7]['status'] = status

        response = _post(app, reason='Alasan apa pun')

        assert response.status_code == 409
        assert db.steps[7]['status'] == status
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_step_tidak_ditemukan_404(self, app, db, logs):
        response = _post(app, step_id=999)

        assert response.status_code == 404
        assert db.updates == []
        assert logs == []


class TestAudit:
    def test_audit_mencatat_step_dan_alasan(self, app, db, logs):
        response = _post(app, reason='Tidak lulus')

        assert response.status_code == 200
        assert len(logs) == 1
        args, kwargs = logs[0]
        assert args == (None, 'recruitment_step_exception', 'traineer', 'petugas1')
        assert kwargs['new_data'] == {'step_id': 7, 'reason': 'Tidak lulus'}

    def test_audit_gagal_tidak_menggagalkan_respons(self, app, db, monkeypatch):
        def _audit_error(*args, **kwargs):
            raise RuntimeError('audit down')

        monkeypatch.setattr(rr, 'log_activity_async', _audit_error, raising=False)

        response = _post(app, reason='Tidak lulus')

        assert response.status_code == 200
        assert db.steps[7]['status'] == 'DIKECUALIKAN'


class TestRoleGate:
    @pytest.mark.parametrize('role', STAFF_ROLES)
    def test_role_staff_diizinkan(self, app, db, logs, role):
        response = _post(app, role=role)

        assert response.status_code == 200
        assert db.steps[7]['status'] == 'DIKECUALIKAN'

    @pytest.mark.parametrize('role', ['finance', 'driver', 'ga', 'receptionist'])
    def test_role_lain_ditolak_403(self, app, db, logs, role):
        response = _post(app, role=role)

        assert response.status_code == 403
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_tanpa_login_ditolak_401(self, app, db, logs):
        response = _post(app, role=None)

        assert response.status_code == 401
        assert db.updates == []
        assert logs == []


class TestScopeCabang:
    def test_langkah_cabang_lain_ditolak_403(self, app, db, logs, monkeypatch):
        monkeypatch.setattr(rr, '_case_scope_ok',
                            lambda cursor, case_id, scope: False)

        response = _post(app, reason='Alasan apa pun')

        assert response.status_code == 403
        assert db.steps[7]['status'] == 'BELUM'
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_scope_diperiksa_sebelum_status_tidak_membocorkan_409(
            self, app, db, logs, monkeypatch):
        monkeypatch.setattr(rr, '_case_scope_ok',
                            lambda cursor, case_id, scope: False)
        db.steps[7]['status'] = 'SELESAI'

        response = _post(app, reason='Alasan apa pun')

        # Status langkah cabang lain tidak boleh terbaca lewat kode 409.
        assert response.status_code == 403
        assert db.steps[7]['status'] == 'SELESAI'
