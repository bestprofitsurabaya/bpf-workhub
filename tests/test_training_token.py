"""Training portal memakai token sesi, bukan tanggal lahir (Rilis C — C6)."""
import pytest

from flask import Flask

from modules import helpers as hp
from modules import routes_training as rt
from modules.portal_token import issue_session_token
from tests.test_training_routes import NIK, TOKEN, _bersih  # noqa: F401


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'training-token-test'
    rt.register_training_routes(app)
    return app.test_client()


def _session(client, nik=NIK, branch='SBY'):
    with client.application.test_request_context('/'):
        return issue_session_token(nik, branch)


def test_status_memakai_session_token(client, monkeypatch):
    seen = {}

    def _status(nik, branch, conn=None):
        seen.update(nik=nik, branch=branch)
        return {'ok': True, 'nama': 'Budi', 'days': {1: None, 2: None},
                'next_day': 1}

    monkeypatch.setattr(rt, 'attendance_status', _status)
    s = _session(client)
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 's': s})
    assert res.status_code == 200
    assert set(res.get_json()['data']['days'].keys()) == {'1', '2'}
    assert seen == {'nik': NIK, 'branch': 'SBY'}


def test_absen_tanpa_dob_dengan_session_token(client, monkeypatch):
    seen = {}

    def _record(nik, branch, day, **kwargs):
        seen.update(nik=nik, branch=branch, day=day)
        return {'ok': True, 'day': day, 'link_status': 'linked',
                'days': {}, 'case_id': 'RC-1', 'attendance_id': 5}

    monkeypatch.setattr(rt, 'record_attendance', _record)
    monkeypatch.setattr(rt, 'record_event', lambda *a, **k: True)
    s = _session(client)
    res = client.post('/api/recruitment/training/attendance',
                      json={'token': TOKEN, 's': s, 'day': 1, 'consent': True})
    assert res.status_code == 200, res.get_json()
    assert seen == {'nik': NIK, 'branch': 'SBY', 'day': 1}


def test_session_cabang_berbeda_ditolak(client, monkeypatch):
    monkeypatch.setattr(rt, 'attendance_status',
                        lambda *a, **k: {'ok': True, 'days': {1: None, 2: None}})
    s = _session(client, branch='JKT')
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 's': s})
    assert res.status_code == 403


def test_fallback_tanpa_sesi_menerima_nik_saja(client, monkeypatch):
    seen = {}

    def _status(nik, branch, conn=None):
        seen.update(nik=nik, branch=branch)
        return {'ok': True, 'days': {1: None, 2: None}}

    monkeypatch.setattr(rt, 'attendance_status', _status)
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 'nik': NIK})
    assert res.status_code == 200
    assert seen == {'nik': NIK, 'branch': 'SBY'}
