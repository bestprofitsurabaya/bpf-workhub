"""TKD memakai token sesi portal, bukan tanggal lahir (Rilis C — C6)."""
import pytest

from modules import routes_tkd as rt
from modules import tkd_service as svc
from modules.portal_token import issue_session_token
from tests.test_tkd_public_attempt import ctx  # noqa: F401

NIK = '3573010101900001'


def _session(app, nik=NIK, branch='SBY'):
    with app.test_request_context('/'):
        return issue_session_token(nik, branch)


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setattr(svc, 'resolve_branch_token', lambda cur, token: 'SBY')
    monkeypatch.setattr(svc, 'verify_identity',
                        lambda cur, nik: {'case_id': 'RC-1', 'nik': nik,
                                          'tanggal_lahir': '1990-01-01'})
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [])
    monkeypatch.setattr(svc, 'load_settings',
                        lambda cur: {'active': 1, 'pass_score': 70,
                                     'max_attempts': 2, 'question_count': 20,
                                     'duration_minutes': 25, 'quota': {}})
    monkeypatch.setattr(rt, 'readiness', lambda q, s: {'ready': True})
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'fetch_tkd_steps', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'finalize_expired', lambda cur, cid: [])


def test_tkd_status_memakai_session_token(ctx):
    app = ctx['app']
    s = _session(app)
    res = app.test_client().post('/api/recruitment/tkd/status',
                                 json={'token': 'tok', 's': s})
    assert res.status_code == 200, res.get_json()


def test_tkd_tanpa_dob_dengan_nik_fallback(ctx):
    app = ctx['app']
    res = app.test_client().post('/api/recruitment/tkd/status',
                                 json={'token': 'tok', 'nik': NIK})
    assert res.status_code == 200, res.get_json()


def test_tkd_session_cabang_berbeda_ditolak(ctx):
    app = ctx['app']
    s = _session(app, branch='JKT')
    res = app.test_client().post('/api/recruitment/tkd/status',
                                 json={'token': 'tok', 's': s})
    assert res.status_code == 403


def test_verify_identity_tanpa_dob(ctx, monkeypatch):
    seen = {}

    def _verify(cur, nik):
        seen['nik'] = nik
        return {'case_id': 'RC-1'}

    monkeypatch.setattr(svc, 'verify_identity', _verify)
    app = ctx['app']
    s = _session(app)
    res = app.test_client().post('/api/recruitment/tkd/status',
                                 json={'token': 'tok', 's': s})
    assert res.status_code == 200
    assert seen['nik'] == NIK
