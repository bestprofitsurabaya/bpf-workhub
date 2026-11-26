"""Endpoint publik absensi training portal (2 hari).

Kontrak:
- `GET  /api/recruitment/training/status?token=&nik=`
- `POST /api/recruitment/training/attendance` body {token, nik, day, consent}

Cabang selalu dari token `cv_online_branch_forms`; NIK penuh tidak pernah
dikirim balik ke browser dan tidak ditulis ke log (hanya 4 digit terakhir).
"""
import secrets

from flask import Flask, request, jsonify

import pytest

from modules import helpers as hp
from modules import routes_training as rt
from modules import training_service as ts

NIK = '3509190102960003'
TOKEN = 'tok_sby_rahasia'


@pytest.fixture(autouse=True)
def _bersih(monkeypatch):
    monkeypatch.setattr(hp, '_get_redis', lambda: None)
    hp._counter_mem.clear()
    monkeypatch.setattr(rt, '_branch_tokens', lambda conn=None: {
        'SBY': {'form_token': TOKEN, 'active': 1},
        'BDG': {'form_token': 'tok_bdg', 'active': 1},
        'MLG': {'form_token': 'tok_mlg', 'active': 0},
    })
    monkeypatch.setattr(rt, '_audit', lambda *a, **k: None)
    yield


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    rt.register_training_routes(app)
    return app.test_client()


def _status_ok(monkeypatch, days=None, next_day=1):
    days = days or {1: None, 2: None}
    monkeypatch.setattr(rt, 'attendance_status',
                        lambda *a, **k: {'ok': True, 'nama': 'Bili',
                                         'days': days, 'next_day': next_day})


def test_status_token_salah_403(client):
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': 'salah', 'nik': NIK})
    assert res.status_code == 403
    assert res.get_json()['status'] == 'error'


def test_status_token_nonaktif_403(client):
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': 'tok_mlg', 'nik': NIK})
    assert res.status_code == 403


def test_status_nik_bukan_16_digit_400(client):
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 'nik': '123'})
    assert res.status_code == 400


def test_status_tidak_ditemukan_404_generik(client, monkeypatch):
    monkeypatch.setattr(rt, 'attendance_status',
                        lambda *a, **k: {'ok': False, 'error': 'not_found'})
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 'nik': NIK})
    body = res.get_json()
    assert res.status_code == 404
    assert 'periksa kembali NIK' in body['msg']
    assert 'NIK' in body['msg'] and NIK not in body['msg']


def test_status_sukses_mengembalikan_hari(client, monkeypatch):
    _status_ok(monkeypatch, days={1: {'attended_at': '2026-11-25 09:00:00',
                                      'link_status': 'linked'}, 2: None},
               next_day=2)
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 'nik': NIK})
    data = res.get_json()['data']
    assert res.status_code == 200
    assert data['next_day'] == 2
    assert data['days']['1']['link_status'] == 'linked'


def test_status_nama_lengkap_tidak_dikirim_ke_browser(client, monkeypatch):
    monkeypatch.setattr(rt, 'attendance_status', lambda *a, **k: {
        'ok': True, 'nama': 'Bili Darnanto Susilo',
        'days': {1: None, 2: None}, 'next_day': 1})
    res = client.get('/api/recruitment/training/status',
                     query_string={'token': TOKEN, 'nik': NIK})
    body = res.get_data(as_text=True)
    assert 'Bili D.' in body
    assert 'Darnanto' not in body


def test_submit_tanpa_consent_400(client):
    res = client.post('/api/recruitment/training/attendance',
                      json={'token': TOKEN, 'nik': NIK, 'day': 1})
    assert res.status_code == 400
    assert 'pernyataan' in res.get_json()['msg'].lower()


def test_submit_hari_2_409(client, monkeypatch):
    monkeypatch.setattr(rt, 'record_attendance',
                        lambda *a, **k: {'ok': False, 'error': 'day2_locked'})
    res = client.post('/api/recruitment/training/attendance',
                      json={'token': TOKEN, 'nik': NIK, 'day': 2,
                            'consent': True})
    assert res.status_code == 409
    assert 'Hari 1' in res.get_json()['msg']


def test_submit_sukses_tanpa_membocorkan_nik(client, monkeypatch):
    monkeypatch.setattr(rt, 'record_attendance', lambda *a, **k: {
        'ok': True, 'day': 1, 'link_status': 'linked', 'applicant_id': 77,
        'days': {1: {'attended_at': '2026-11-25 09:00:00',
                     'link_status': 'linked'}, 2: None}})
    res = client.post('/api/recruitment/training/attendance',
                      json={'token': TOKEN, 'nik': NIK, 'day': 1,
                            'consent': True})
    body = res.get_json()
    assert res.status_code == 200
    assert body['data']['day'] == 1
    assert 'applicant_id' not in body['data']
    assert NIK not in res.get_data(as_text=True)


def test_submit_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(rt, '_rate_ok', lambda ip: False)
    res = client.post('/api/recruitment/training/attendance',
                      json={'token': TOKEN, 'nik': NIK, 'day': 1,
                            'consent': True})
    assert res.status_code == 429
