"""Ringkasan portal per sesi (Rilis C — Task C4).

`GET /api/recruitment/portal/summary?token=<session_token>` mengembalikan
tahap dan langkah berikutnya tanpa NIK lengkap, tanggal lahir, atau alamat.
Cabang berasal dari token, bukan dari kasus.
"""
import pytest
from flask import Flask

from modules import helpers as hp
from modules import routes_recruitment as rr
from modules.portal_token import issue_card_token, issue_session_token

NIK = '3573010101900001'


@pytest.fixture(autouse=True)
def _tanpa_rate_limit(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        p = tuple(params or ())
        if 'RECRUITMENT_CASES' in upper:
            self.rows = [r for r in self.conn.cases if str(r.get('nik')) == str(p[0])]
        elif 'RECRUITMENT_STEPS' in upper:
            self.rows = [r for r in self.conn.steps if str(r.get('case_id')) == str(p[0])]
        elif 'FIRST_WORK_SUBMISSIONS' in upper:
            self.rows = [r for r in self.conn.first_work
                         if str(r.get('nik')) == str(p[0])]
        elif 'BRANCHES' in upper:
            self.rows = [r for r in self.conn.branches if str(r.get('code')) == str(p[0])]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.cases = []
        self.steps = []
        self.first_work = []
        self.branches = [{'code': 'SBY', 'name': 'Surabaya'},
                         {'code': 'JKT', 'name': 'Jakarta'}]
        self.closed = False

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def close(self):
        self.closed = True


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = 'summary-test'
    rr.register_recruitment_routes(app)
    return app


@pytest.fixture
def master(app, monkeypatch):
    db = _Conn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: db)
    return db


def _summary(app, token, ip='203.0.113.20'):
    with app.test_request_context('/'):
        pass
    return app.test_client().get('/api/recruitment/portal/summary',
                                 query_string={'token': token},
                                 headers={'X-Real-IP': ip})


def _token(app, nik=NIK, branch='SBY'):
    with app.test_request_context('/'):
        return issue_session_token(nik, branch)


def test_summary_memakai_token_dan_tidak_mengirim_nik(app, master):
    master.cases.append({'case_id': 'RC-1', 'nik': NIK, 'nama': 'Budi Santoso'})
    resp = _summary(app, _token(app))
    data = resp.get_json()['data']
    assert resp.status_code == 200
    assert resp.headers['Cache-Control'] == 'no-store'
    assert NIK not in str(data)
    assert data['nama_masked'] == 'Budi S.'
    assert data['branch_code'] == 'SBY'
    assert data['branch_name'] == 'Surabaya'
    assert [s['type'] for s in data['stages']] == [
        'CV', 'TRAINING', 'TKD', 'FIRSTWORK']
    assert data['next_action'] == 'CV'


def test_summary_cv_gate_dan_next_action(app, master):
    master.cases.append({'case_id': 'RC-1', 'nik': NIK, 'nama': 'Budi Santoso'})
    # CV selesai di cabang lain membuka tahap lain.
    master.steps.append({'case_id': 'RC-1', 'step_type': 'CV',
                         'status': 'SELESAI', 'branch_code': 'JKT',
                         'completed_at': '2026-11-25 09:00:00'})
    data = _summary(app, _token(app)).get_json()['data']
    assert data['stages'][1]['can_start'] is True
    assert data['next_action'] == 'TRAINING'


def test_summary_card_token_tersedia(app, master):
    master.cases.append({'case_id': 'RC-1', 'nik': NIK, 'nama': 'Budi Santoso'})
    master.first_work.append({'id': 9, 'nik': NIK,
                              'submitted_at': '2026-11-25 10:00:00'})
    data = _summary(app, _token(app)).get_json()['data']
    assert data['card_token']
    assert 'first_work_submissions' not in data


def test_summary_menolak_token_kartu_dan_token_rusak(app, master):
    with app.test_request_context('/'):
        card = issue_card_token(1)
    assert _summary(app, card).status_code == 403
    assert _summary(app, 'token-rusak').status_code == 403


def test_summary_rate_limit(app, master):
    token = _token(app)
    for _ in range(21):
        last = _summary(app, token, ip='203.0.113.99')
    assert last.status_code == 429
