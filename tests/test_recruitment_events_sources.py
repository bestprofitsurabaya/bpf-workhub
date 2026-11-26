"""Event linimasa dari sumber CV, training portal, dan TKD (Rilis C — C3b).

Event ditulis SETELAH commit transaksi sumber, best-effort: kegagalan master
tidak mengubah respons publik. Fixture DB/cursor tiruan dipakai ulang dari
modul tes yang sudah ada agar kontrak endpoint tetap sama.
"""
import pytest

from modules import routes_cv_online as cv
from modules import routes_tkd as tkd
from modules import routes_training as tr
from modules import tkd_service as svc

from tests.test_recruitment_service import (  # noqa: F401
    CV_BASE, NIK, _tanpa_rate_limit, cv_app, db,
)
from tests.test_training_routes import (  # noqa: F401
    TOKEN as TRAINING_TOKEN, _bersih, client as training_client,
)
from tests.test_tkd_public_attempt import (  # noqa: F401
    BASE as TKD_BASE, _waktu_import_yang_basi, ctx,
)


def _capture(monkeypatch, module, events):
    def _record(case_id, nik, event_type, **kwargs):
        events.append({'case_id': case_id, 'nik': nik,
                       'event_type': event_type, **kwargs})
        return True
    monkeypatch.setattr(module, 'record_event', _record)


def test_cv_submit_menulis_event_cv_submitted(monkeypatch, db, cv_app):
    events = []
    _capture(monkeypatch, cv, events)
    monkeypatch.setattr(cv, 'get_master_connection', lambda: db)
    res = cv_app.test_client().post('/api/cv-online/public',
                                    data={**CV_BASE, 'consent': '1'})
    assert res.status_code == 200, res.get_json()
    assert [e['event_type'] for e in events] == ['CV_SUBMITTED']
    assert events[0]['source_module'] == 'cv'
    assert events[0]['source_id'] == res.get_json()['registration_no']


def test_cv_event_gagal_tidak_menggagalkan_submit(monkeypatch, db, cv_app):
    monkeypatch.setattr(cv, 'get_master_connection', lambda: db)
    monkeypatch.setattr(cv, 'record_event',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('master')))
    res = cv_app.test_client().post('/api/cv-online/public',
                                    data={**CV_BASE, 'consent': '1'})
    assert res.status_code == 200, res.get_json()


def test_training_hari1_dan_hari2_menulis_event_berbeda(monkeypatch,
                                                        training_client):
    events = []
    _capture(monkeypatch, tr, events)
    monkeypatch.setattr(
        tr, 'record_attendance',
        lambda nik, branch, day, **k: {
            'ok': True, 'day': day, 'link_status': 'linked', 'days': {},
            'case_id': 'RC-1', 'attendance_id': 42})

    for day in (1, 2):
        res = training_client.post('/api/recruitment/training/attendance',
                                   json={'token': TRAINING_TOKEN, 'nik': NIK,
                                         'day': day, 'consent': True})
        assert res.status_code == 200, res.get_json()
    assert {e['event_type'] for e in events} == {
        'TRAINING_PORTAL_D1', 'TRAINING_PORTAL_D2'}
    assert all(e['source_module'] == 'training' for e in events)


def test_tkd_submit_menulis_submitted_dan_scored(monkeypatch, ctx):
    events = []
    _capture(monkeypatch, tkd, events)
    client = ctx['app'].test_client()
    with client.session_transaction() as s:
        s['tkd_case_id'] = 'RC-1'
        import time
        s['tkd_verified_at'] = int(time.time())
    res = client.post(TKD_BASE + '/submit')
    assert res.status_code == 200, res.get_json()
    types = {e['event_type'] for e in events}
    assert {'TKD_SUBMITTED', 'TKD_SCORED'} <= types
    assert all(e['source_module'] == 'tkd' for e in events)


def test_tkd_start_menulis_event_started(monkeypatch, ctx):
    events = []
    _capture(monkeypatch, tkd, events)
    monkeypatch.setattr(tkd, '_verify_body',
                        lambda body: ({'nik': NIK, 'branch': 'SBY',
                                       'dob': '1990-01-01'}, None))
    monkeypatch.setattr(tkd, '_rate', lambda *a, **k: True)
    monkeypatch.setattr(tkd, '_verified_context',
                        lambda cur, v: ({'branch': 'SBY', 'nik': NIK}, None))
    monkeypatch.setattr(svc, 'fetch_case_by_nik',
                        lambda cur, nik, for_update=False: {'case_id': 'RC-1'})
    monkeypatch.setattr(svc, 'load_settings',
                        lambda cur: {'active': 1, 'pass_score': 70,
                                     'max_attempts': 2, 'question_count': 20,
                                     'duration_minutes': 25, 'quota': {}})
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [{'id': 1}])
    monkeypatch.setattr(tkd, 'readiness', lambda q, s: {'ready': True})
    monkeypatch.setattr(tkd, '_state_for',
                        lambda cur, case, settings: ({'state': 'BARU',
                                                      'can_start': True}, []))
    monkeypatch.setattr(svc, 'create_attempt',
                        lambda cur, case, branch, tier, settings, questions: {
                            'attempt': {'id': 'TKD-NEW', 'case_id': 'RC-1',
                                        'attempt_no': 1, 'status': 'BERLANGSUNG'},
                            'items': []})
    res = ctx['app'].test_client().post('/api/recruitment/tkd/start',
                                        json={'modal_tier': '30k'})
    assert res.status_code == 200, res.get_json()
    assert 'TKD_STARTED' in {e['event_type'] for e in events}
