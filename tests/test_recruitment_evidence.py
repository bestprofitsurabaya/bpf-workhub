"""Regresi bukti manual langkah TRAINING/TKD rekrutmen (Rilis B — Task 6).

Kontrak: `POST /api/recruitment/steps/<id>/evidence` dengan body
`{'date': 'YYYY-MM-DD', 'note': str, 'file_url'?: str, 'score'?: str}`
hanya untuk staff (traineer/ga_hr/admin). Tanggal wajib valid; langkah
CV/FIRSTWORK dan langkah `DIKECUALIKAN` ditolak 409. Sukses menulis
`SELESAI` + `manual_evidence` + token + catatan + actor + tanggal selesai
di DB master dan mencatat audit `recruitment_step_evidence`.

Langkah TRAINING/TKD yang belum ada dibuat secara malas (lazy) lewat
`step_id = 0` dengan `case_id`/`step_type` di body; cabang diambil dari
riwayat cabang terakhir kasus.

Memakai DB master palsu dan logger audit palsu — tanpa MySQL/Redis/thread.
"""
import os
import sys

import pytest
from flask import Flask  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import routes_recruitment as rr  # noqa: E402

STAFF_ROLES = ('traineer', 'ga_hr', 'admin')
CASE_A = 'RC-a1b2c3d4e5f6'
VALID_BODY = {'date': '2026-11-24', 'note': 'Lulus pelatihan'}


class _FakeCursor:
    """Cursor minimal untuk SELECT/INSERT/UPDATE langkah bukti."""

    _UPDATE_COLS = ('status', 'evidence_type', 'evidence_id',
                    'exception_reason', 'completed_at', 'actor')

    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        params = list(params or ())
        self.conn.statements.append((upper, tuple(params)))

        if upper.startswith('SELECT') and 'FROM RECRUITMENT_STEPS' in upper:
            if ' WHERE ID=%S' in upper:
                step = self.conn.steps.get(params[0])
                self._rows = [step] if step else []
            else:
                self._rows = [s for s in self.conn.steps.values()
                              if s.get('case_id') == params[0]
                              and s.get('step_type') == params[1]
                              and s.get('branch_code') == params[2]]
            return

        if upper.startswith('SELECT') and 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [c for c in self.conn.cases
                          if c['case_id'] == params[0]]
            return

        if upper.startswith('SELECT') and 'FROM CASE_BRANCH_HISTORY' in upper:
            branches = [b for b in self.conn.branches
                        if b['case_id'] == params[0]]
            branches.sort(key=lambda b: (b.get('last_seen_at') or '',
                                         b.get('first_seen_at') or ''),
                          reverse=True)
            self._rows = branches[:1]
            return

        if upper.startswith('INSERT') and 'RECRUITMENT_STEPS' in upper:
            case_id, step_type, branch = params[0], params[1], params[2]
            if not any(s.get('case_id') == case_id
                       and s.get('step_type') == step_type
                       and s.get('branch_code') == branch
                       for s in self.conn.steps.values()):
                new_id = self.conn.next_id
                self.conn.next_id += 1
                self.conn.steps[new_id] = {
                    'id': new_id, 'case_id': case_id, 'step_type': step_type,
                    'status': 'BELUM', 'branch_code': branch,
                    'evidence_type': '', 'evidence_id': '',
                    'exception_reason': None, 'completed_at': None, 'actor': '',
                }
                self.conn.inserts.append(new_id)
            return

        if upper.startswith('UPDATE') and 'RECRUITMENT_STEPS' in upper:
            set_part = upper.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
            cols = [chunk.strip().partition('=')[0].lower()
                    for chunk in set_part.split(',')]
            changes = dict(zip(cols, params[:len(cols)]))
            step_id = params[-1]
            row = self.conn.steps.get(step_id)
            if row is not None:
                row.update(changes)
            self.conn.updates.append((step_id, changes))
            return

        self._rows = []

    @property
    def lastrowid(self):
        return self.conn.next_id - 1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeConn:
    def __init__(self, step_type='TRAINING', status='BELUM', step_id=7):
        self.steps = {step_id: {
            'id': step_id, 'case_id': CASE_A, 'step_type': step_type,
            'status': status, 'branch_code': 'SBY', 'evidence_type': '',
            'evidence_id': '', 'exception_reason': None,
            'completed_at': None, 'actor': '',
        }} if step_id is not None else {}
        self.cases = [{'case_id': CASE_A, 'first_branch': 'SBY'}]
        self.branches = [
            {'case_id': CASE_A, 'branch_code': 'SBY',
             'first_seen_at': '2026-11-20 10:00:00',
             'last_seen_at': '2026-11-20 10:00:00'},
            {'case_id': CASE_A, 'branch_code': 'JKT',
             'first_seen_at': '2026-11-21 11:00:00',
             'last_seen_at': '2026-11-21 11:00:00'},
        ]
        self.next_id = 100
        self.statements = []
        self.updates = []
        self.inserts = []
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
    flask_app.secret_key = 'test-recruitment-evidence'
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


def _post(app, body=None, step_id=7, role='traineer', name='petugas1', raw=False):
    client = app.test_client()
    if role is not None:
        with client.session_transaction() as sess:
            sess['user_role'] = role
            sess['user_name'] = name
    if raw:
        return client.post(f'/api/recruitment/steps/{step_id}/evidence')
    return client.post(f'/api/recruitment/steps/{step_id}/evidence', json=body)


class TestValidasiTanggal:
    @pytest.mark.parametrize('date_value', [
        None, '', '   ', '2026-13-01', '24-11-2026', 'not-a-date', 12345,
    ])
    def test_tanggal_hilang_atau_invalid_ditolak_400(self, app, db, logs, date_value):
        body = dict(VALID_BODY)
        if date_value is None:
            body.pop('date')
        else:
            body['date'] = date_value

        response = _post(app, body=body)

        assert response.status_code == 400
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_tanpa_body_json_ditolak_400(self, app, db, logs):
        assert _post(app, raw=True).status_code == 400
        assert db.updates == []


class TestTulisBukti:
    def test_dengan_tanggal_valid_status_selesai_dan_tersimpan(self, app, db, logs):
        response = _post(app, body=dict(VALID_BODY, file_url='https://x/bukti.pdf',
                                        score='A'))

        assert response.status_code == 200
        step = db.steps[7]
        assert step['status'] == 'SELESAI'
        assert step['evidence_type'] == 'manual_evidence'
        assert step['evidence_id']
        assert step['exception_reason'] == 'Lulus pelatihan'
        assert step['completed_at'] == '2026-11-24'
        assert step['actor'] == 'petugas1'
        assert db.commits == 1
        assert db.closed is True
        payload = response.get_json()
        assert payload['status'] == 'success'
        assert payload['data']['status'] == 'SELESAI'
        assert payload['data']['id'] == 7

    @pytest.mark.parametrize('step_type', ['CV', 'FIRSTWORK'])
    def test_langkah_cv_firstwork_ditolak_409(self, app, db, logs, step_type):
        db.steps[7]['step_type'] = step_type

        response = _post(app, body=VALID_BODY)

        assert response.status_code == 409
        assert db.steps[7]['status'] == 'BELUM'
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_langkah_dikecualikan_ditolak_409(self, app, db, logs):
        db.steps[7]['status'] = 'DIKECUALIKAN'

        response = _post(app, body=VALID_BODY)

        assert response.status_code == 409
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_langkah_tidak_ditemukan_404(self, app, db, logs):
        assert _post(app, body=VALID_BODY, step_id=999).status_code == 404
        assert db.updates == []
        assert logs == []

    def test_langkah_selesai_boleh_ditulis_ulang(self, app, db, logs):
        db.steps[7]['status'] = 'SELESAI'

        assert _post(app, body=VALID_BODY).status_code == 200
        assert db.steps[7]['exception_reason'] == 'Lulus pelatihan'


class TestAudit:
    def test_audit_mencatat_step_tanggal_dan_metadata(self, app, db, logs):
        response = _post(app, body=dict(VALID_BODY, file_url='https://x/a.pdf',
                                        score='88'))

        assert response.status_code == 200
        assert len(logs) == 1
        args, kwargs = logs[0]
        assert args == (None, 'recruitment_step_evidence', 'traineer', 'petugas1')
        detail = kwargs['new_data']
        assert detail['step_id'] == 7
        assert detail['date'] == '2026-11-24'
        assert detail['note'] == 'Lulus pelatihan'
        assert detail['file_url'] == 'https://x/a.pdf'
        assert detail['score'] == '88'
        assert 'nik' not in detail

    def test_audit_gagal_tidak_menggagalkan_respons(self, app, db, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError('audit down')

        monkeypatch.setattr(rr, 'log_activity_async', _boom, raising=False)

        assert _post(app, body=VALID_BODY).status_code == 200
        assert db.steps[7]['status'] == 'SELESAI'


class TestRoleGate:
    @pytest.mark.parametrize('role', STAFF_ROLES)
    def test_role_staff_diizinkan(self, app, db, logs, role):
        assert _post(app, body=VALID_BODY, role=role).status_code == 200

    @pytest.mark.parametrize('role', ['finance', 'driver', 'ga', 'receptionist'])
    def test_role_lain_ditolak_403(self, app, db, logs, role):
        assert _post(app, body=VALID_BODY, role=role).status_code == 403
        assert db.updates == []
        assert db.commits == 0
        assert logs == []

    def test_tanpa_login_ditolak_401(self, app, db, logs):
        assert _post(app, body=VALID_BODY, role=None).status_code == 401
        assert db.updates == []


class TestLazyStepCreation:
    """TRAINING/TKD belum ada (Task 4 hanya membuat CV/FIRSTWORK)."""

    @pytest.mark.parametrize('step_type', ['TRAINING', 'TKD'])
    def test_langkah_baru_dibuat_dengan_cabang_riwayat_terakhir(self, app, db, logs, step_type):
        db.steps.clear()

        response = _post(app, step_id=0, body=dict(
            VALID_BODY, case_id=CASE_A, step_type=step_type))

        assert response.status_code == 200
        assert len(db.inserts) == 1
        created = db.steps[db.inserts[0]]
        assert created['step_type'] == step_type
        assert created['branch_code'] == 'JKT'  # last_seen_at terbaru
        assert created['status'] == 'SELESAI'
        assert created['evidence_type'] == 'manual_evidence'
        assert created['evidence_id']
        assert created['exception_reason'] == 'Lulus pelatihan'
        assert created['completed_at'] == '2026-11-24'
        assert created['actor'] == 'petugas1'
        assert db.commits == 1
        assert logs[0][1]['new_data']['created'] is True

    def test_langkah_baru_tanpa_case_id_ditolak_400(self, app, db, logs):
        response = _post(app, step_id=0, body=dict(VALID_BODY, step_type='TRAINING'))

        assert response.status_code == 400
        assert db.inserts == []
        assert logs == []

    def test_langkah_baru_jenis_cv_ditolak_409(self, app, db, logs):
        response = _post(app, step_id=0, body=dict(
            VALID_BODY, case_id=CASE_A, step_type='CV'))

        assert response.status_code == 409
        assert db.inserts == []
        assert logs == []

    def test_langkah_baru_kasus_tidak_ditemukan_404(self, app, db, logs):
        response = _post(app, step_id=0, body=dict(
            VALID_BODY, case_id='RC-tidak-ada', step_type='TRAINING'))

        assert response.status_code == 404
        assert db.inserts == []
        assert logs == []
