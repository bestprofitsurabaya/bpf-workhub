"""Promosi otomatis pelamar lulus ke master karyawan (Rilis D — D4)."""
import pytest
from types import SimpleNamespace

import modules.routes_applicants as ap
import modules.routes_receptionist as rr
from tests.test_applicants_nik import _FakeConn, _add_row, NIK


@pytest.fixture
def setup(monkeypatch):
    branch = _FakeConn()
    branch.employee_inout = []
    master = SimpleNamespace(events=[], case_rows=[], branch_history=[],
                             employees=[])

    def _fake_app():
        from flask import Flask
        app = Flask(__name__)
        app.secret_key = 'promote-test'
        rr.register_receptionist_routes(app)
        ap.register_applicant_routes(app)
        for module in (rr, ap):
            monkeypatch.setattr(module, 'get_db_connection', lambda: branch)
            monkeypatch.setattr(module, 'log_activity_async', lambda *a, **k: None)
            monkeypatch.setattr(module, 'ensure_case',
                                lambda nik, *a, **k: 'RC-1', raising=False)
            monkeypatch.setattr(module, 'record_event',
                                lambda *a, **k: True, raising=False)
            monkeypatch.setattr(module, 'promote_to_employee',
                                _promote, raising=False)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = 'receptionist'
            s['user_name'] = 'resepsionis'
            s['full_name'] = 'Rina'
            s['branch_code'] = 'SBY'
            s['stepup_until'] = 9_999_999_999
        return client

    def _promote(case_id, **kwargs):
        master.employees.append({'nik': NIK, 'case_id': case_id,
                                 'employee_no': 'KRY-SBY-00001'})
        return {'employee_id': 1, 'employee_no': 'KRY-SBY-00001',
                'created': True, 'reactivated': False}

    return _fake_app(), branch, master


def test_lulus_membuat_karyawan(setup):
    client, branch, master = setup
    row = _add_row(branch, nik=NIK, status='training_4')
    res = client.post(f'/api/applicants/{row["id"]}/status',
                      json={'status': 'lulus'})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body['employee_created'] is True
    assert body['employee_no'] == 'KRY-SBY-00001'
    assert master.employees[0]['nik'] == NIK


def test_lulus_tanpa_nik_ditolak(setup):
    client, branch, master = setup
    row = _add_row(branch, nik=None, status='training_4')
    res = client.post(f'/api/applicants/{row["id"]}/status',
                      json={'status': 'lulus'})
    assert res.status_code == 409
    assert 'NIK' in res.get_json()['msg']
    assert master.employees == []


def test_register_employee_lama_tidak_menulis_inout(setup):
    client, branch, master = setup
    row = _add_row(branch, nik=NIK, status='training_4')
    res = client.post(f'/api/applicants/{row["id"]}/register-employee', json={})
    assert res.status_code == 200, res.get_json()
    assert branch.employee_inout == []
    assert master.employees[0]['nik'] == NIK
