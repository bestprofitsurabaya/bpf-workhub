"""API master karyawan (Rilis D — D3): peran, masking, toggle, void."""
import pytest
from flask import Flask

import modules.employee_service as es
import modules.routes_employees as re_mod
from tests.test_employee_service import _Conn

NIK = '3573010101900001'


@pytest.fixture
def master():
    conn = _Conn()
    conn.employees.append({
        'id': 1, 'employee_no': 'KRY-SBY-00001', 'nik': NIK,
        'nama': 'Budi Santoso', 'nama_norm': 'budi santoso',
        'jabatan': 'Business Consultant', 'branch_code': 'SBY',
        'is_active': 1, 'needs_nik': 0, 'no_hp': '081234567890',
        'tanggal_masuk': '2026-11-26', 'deactivation_reason': None,
    })
    return conn


@pytest.fixture
def app(master, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_master_connection', lambda: master)
    monkeypatch.setattr(re_mod, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(es, 'get_master_connection', lambda: master)
    monkeypatch.setattr(es, 'record_event', lambda *a, **k: True)
    app = Flask(__name__)
    app.secret_key = 'employees-api-test'
    re_mod.register_employee_routes(app)
    return app


def _client(app, role='receptionist', branch='SBY'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'staff'
        s['full_name'] = 'Staf'
        s['branch_code'] = branch
    return c


def test_resepsionis_hanya_cabangnya_dan_nik_termasker(app):
    data = _client(app).get('/api/employees').get_json()['data']
    assert all(row['branch_code'] == 'SBY' for row in data)
    assert data[0]['nik_masked'] == '****0001'
    assert 'nik' not in data[0]


def test_ga_hr_melihat_nik_lengkap(app, master):
    master.employees[0]['branch_code'] = 'JKT'
    data = _client(app, role='ga_hr').get('/api/employees').get_json()['data']
    assert data[0]['nik'] == NIK
    assert data[0]['branch_code'] == 'JKT'


def test_ekspor_hanya_ga_hr(app):
    assert _client(app).get('/api/employees/export.csv').status_code == 403
    resp = _client(app, role='ga_hr').get('/api/employees/export.csv')
    assert resp.status_code == 200
    assert 'text/csv' in resp.headers['Content-Type']


def test_toggle_keluar_lalu_kedua_409(app):
    c = _client(app)
    assert c.post('/api/employees/1/attendance',
                  json={'direction': 'OUT'}).status_code == 200
    assert c.post('/api/employees/1/attendance',
                  json={'direction': 'OUT'}).status_code == 409


def test_cabang_lain_ditolak(app, master):
    master.employees[0]['branch_code'] = 'JKT'
    assert _client(app).post('/api/employees/1/attendance',
                             json={'direction': 'OUT'}).status_code == 403


def test_void_khusus_ga_hr(app):
    c = _client(app)
    assert c.post('/api/employees/1/attendance',
                  json={'direction': 'OUT'}).status_code == 200
    event_id = 1
    assert c.post(f'/api/employees/1/attendance/{event_id}/void',
                  json={'reason': 'salah'}).status_code == 403
    assert _client(app, role='ga_hr').post(
        f'/api/employees/1/attendance/{event_id}/void',
        json={'reason': 'salah'}).status_code == 200


def test_nonaktif_wajib_alasan_dan_hanya_ga_hr(app):
    c = _client(app)
    assert c.post('/api/employees/1/deactivate',
                  json={'reason': ''}).status_code == 403
    ga = _client(app, role='ga_hr')
    assert ga.post('/api/employees/1/deactivate',
                   json={'reason': ''}).status_code == 400
    assert ga.post('/api/employees/1/deactivate',
                   json={'reason': 'pindah'}).status_code == 200
    assert ga.post('/api/employees/1/reactivate').status_code == 200


def test_patch_nik_hanya_ga_hr_dan_unik(app, master):
    master.employees.append({'id': 2, 'employee_no': 'KRY-SBY-00002',
                             'nik': '3573010101900002', 'nama': 'Rina',
                             'branch_code': 'SBY', 'is_active': 1})
    ga = _client(app, role='ga_hr')
    assert _client(app).patch('/api/employees/1',
                              json={'nik': '3573010101900003'}).status_code == 403
    assert ga.patch('/api/employees/1',
                    json={'nik': '3573010101900002'}).status_code == 409
    assert ga.patch('/api/employees/1',
                    json={'nik': '3573010101900003'}).status_code == 200
