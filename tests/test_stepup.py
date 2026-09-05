"""Unit Tests — Step-up Authentication (v2.31, ISO/IEC 27001 A.8.2/A.8.3/A.8.5).

Aksi berisiko (approve/pay kasbon, payout klaim BBM, verifikasi air minum)
wajib didahului verifikasi PIN ulang user yang sedang login:
- tanpa grant step-up → 428 `STEPUP_REQUIRED`;
- grant diterbitkan hanya setelah PIN SENDIRI valid (username dari sesi,
  bukan dari body) dan rate-limited anti brute-force;
- grant berumur pendek & hilang saat logout.

Jalankan:
    python3 -m pytest tests/test_stepup.py -v
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask, jsonify, session

import modules.stepup as stepup_mod
from modules.stepup import (register_stepup_routes, grant_stepup,
                            stepup_required, STEPUP_REQUIRED_CODE)


@pytest.fixture
def app():
    """App minimal: endpoint step-up + satu endpoint dummy ber-decorator."""
    a = Flask(__name__)
    a.secret_key = 'test-secret'
    register_stepup_routes(a)

    @a.route('/api/dummy-sensitive', methods=['POST'])
    @stepup_required
    def dummy_sensitive():
        return jsonify({'status': 'success', 'user': session.get('user_name')})

    return a


@pytest.fixture
def client(app):
    return app.test_client()


# ------------------------------------------------------------------
# Fake DB: hanya menyimpan satu user dengan PIN yang diketahui
# ------------------------------------------------------------------
class FakeCursor:
    def __init__(self, user):
        self._user = user
        self.calls = []  # (query, params) — untuk memeriksa username sesi

    def execute(self, query, params=None):
        self.calls.append((query, params))
        self._row = None
        if self._user and params and params[0] == self._user['username'] \
                and params[1] == self._user['pin'] and self._user['is_active']:
            self._row = {'id': self._user['id']}

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, user):
        self.cursor_obj = FakeCursor(user)

    def cursor(self, dictionary=True):
        return self.cursor_obj

    def close(self):
        pass


def _patch_db(monkeypatch, user):
    conn = FakeConn(user)
    monkeypatch.setattr(stepup_mod, 'get_master_connection', lambda: conn)
    return conn.cursor_obj


def _login(client, username='ga_sby', role='ga'):
    with client.session_transaction() as s:
        s.clear()
        s['user_role'] = role
        s['user_name'] = username
        s['full_name'] = 'GA Surabaya'


# ================================================================
# Endpoint POST /api/step-up
# ================================================================
class TestStepUpEndpoint:
    def test_wajib_login(self, client):
        """Tanpa sesi → 401 (tidak ada user yang bisa diverifikasi)."""
        r = client.post('/api/step-up', json={'pin': '123456'})
        assert r.status_code == 401
        assert r.get_json()['status'] == 'error'

    def test_pin_wajib_diisi(self, client):
        _login(client)
        r = client.post('/api/step-up', json={})
        assert r.status_code == 400
        assert 'PIN wajib diisi' in r.get_json()['msg']

    def test_pin_salah_ditolak_dan_rate_limit_dicatat(self, app, client, monkeypatch):
        """PIN salah → 401 + pin_fail dipanggil (penghitung brute-force naik)."""
        user = {'id': 1, 'username': 'ga_sby', 'pin': '111111', 'is_active': True}
        cur = _patch_db(monkeypatch, user)
        _login(client)

        fails = []
        monkeypatch.setattr(stepup_mod, 'pin_fail',
                            lambda ip: fails.append(ip) or (False, 0))
        monkeypatch.setattr(stepup_mod, 'pin_success',
                            lambda ip: pytest.fail('pin_success tidak boleh dipanggil utk PIN salah'))

        r = client.post('/api/step-up', json={'pin': '999999'})
        assert r.status_code == 401
        assert 'PIN salah' in r.get_json()['msg']
        assert len(fails) == 1
        # Query memakai username SESI, bukan dari body
        query, params = cur.calls[-1]
        assert params[0] == 'ga_sby'
        assert params[1] == '999999'

    def test_pin_benar_menerbitkan_grant(self, app, client, monkeypatch):
        """PIN benar → 200, grant tersimpan di sesi, aksi berisiko lolos."""
        user = {'id': 7, 'username': 'ga_sby', 'pin': '123456', 'is_active': True}
        _patch_db(monkeypatch, user)
        _login(client)

        ok = []
        monkeypatch.setattr(stepup_mod, 'pin_success', lambda ip: ok.append(ip))

        r = client.post('/api/step-up', json={'pin': '123456'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['status'] == 'success'
        assert body['expires_in'] == stepup_mod.STEPUP_TTL
        assert len(ok) == 1
        with client.session_transaction() as s:
            assert s.get('stepup_until', 0) > 0

        # Aksi berisiko sekarang boleh dijalankan
        r2 = client.post('/api/dummy-sensitive')
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'success'

    def test_username_selalu_dari_sesi_bukan_body(self, app, client, monkeypatch):
        """Body tidak bisa memilih username lain — PIN diverifikasi utk user sesi."""
        user = {'id': 1, 'username': 'ga_sby', 'pin': '123456', 'is_active': True}
        cur = _patch_db(monkeypatch, user)
        _login(client)

        # Body membawa 'admin' + pin admin — tetap harus diverifikasi utk ga_sby
        r = client.post('/api/step-up', json={'username': 'admin', 'pin': '123456'})
        assert r.status_code == 200
        query, params = cur.calls[-1]
        assert params[0] == 'ga_sby'  # username sesi, bukan 'admin'

    def test_user_nonaktif_ditolak(self, app, client, monkeypatch):
        """Akun nonaktif → PIN ditolak (is_active=FALSE)."""
        user = {'id': 1, 'username': 'ga_sby', 'pin': '123456', 'is_active': False}
        _patch_db(monkeypatch, user)
        _login(client)
        r = client.post('/api/step-up', json={'pin': '123456'})
        assert r.status_code == 401

    def test_rate_limit_lockout(self, app, client, monkeypatch):
        """Rate-limit aktif → 429 tanpa memeriksa PIN."""
        user = {'id': 1, 'username': 'ga_sby', 'pin': '123456', 'is_active': True}
        _patch_db(monkeypatch, user)
        _login(client)
        monkeypatch.setattr(stepup_mod, 'pin_rate_check',
                            lambda ip: (False, 300))
        r = client.post('/api/step-up', json={'pin': '123456'})
        assert r.status_code == 429
        assert '5 menit' in r.get_json()['msg']


# ================================================================
# Decorator @stepup_required
# ================================================================
class TestStepUpDecorator:
    def test_tanpa_login_401(self, client):
        r = client.post('/api/dummy-sensitive')
        assert r.status_code == 401

    def test_tanpa_grant_428(self, client):
        _login(client)
        r = client.post('/api/dummy-sensitive')
        assert r.status_code == 428
        body = r.get_json()
        assert body['code'] == STEPUP_REQUIRED_CODE
        assert body['status'] == 'error'

    def test_grant_aktif_lolos(self, client):
        """Grant aktif (via alur nyata: POST /api/step-up) → aksi lolos."""
        _login(client)
        # Set grant langsung di sesi test client (setara grant_stepup())
        with client.session_transaction() as s:
            s['stepup_until'] = time.time() + stepup_mod.STEPUP_TTL
        r = client.post('/api/dummy-sensitive')
        assert r.status_code == 200

    def test_grant_kedaluwarsa_428(self, client):
        _login(client)
        with client.session_transaction() as s:
            s['stepup_until'] = 0  # sudah lewat
        r = client.post('/api/dummy-sensitive')
        assert r.status_code == 428

    def test_grant_stepup_dan_clear_stepup(self, app):
        """grant_stepup/clear_stepup bekerja lewat proxy sesi (request context)."""
        with app.test_request_context():
            session.clear()
            assert stepup_mod.stepup_expiry() == 0
            grant_stepup()
            assert stepup_mod.stepup_expiry() > 0
            stepup_mod.clear_stepup()
            assert stepup_mod.stepup_expiry() == 0

    def test_logout_menghapus_grant(self, client):
        """session.clear() (logout) otomatis mencabut grant step-up."""
        _login(client)
        with client.session_transaction() as s:
            s['stepup_until'] = time.time() + stepup_mod.STEPUP_TTL
        with client.session_transaction() as s:
            s.clear()
        r = client.post('/api/dummy-sensitive')
        assert r.status_code == 401

    def test_stepup_expiry_menghitung_sisa(self, app):
        """stepup_expiry menghitung sisa detik grant (0 bila kosong/lewat)."""
        with app.test_request_context():
            session.clear()
            assert stepup_mod.stepup_expiry() == 0
            session['stepup_until'] = time.time() + 120
            assert stepup_mod.stepup_expiry() > 0
            assert stepup_mod.stepup_expiry() <= 120
            session['stepup_until'] = 0
            assert stepup_mod.stepup_expiry() == 0
            del session['stepup_until']
            assert stepup_mod.stepup_expiry() == 0


# ================================================================
# Anti-regresi: ENDPOINT NYATA berisiko wajib 428 tanpa grant
# ================================================================
# Dekorator step-up dipasang di rute produksi (routes_cash / routes_spa /
# routes_water). Tes ini memanggil rute asli dengan sesi role yang benar —
# bila @stepup_required dicabut, permintaan lolos ke body (butuh DB) dan
# tidak lagi menjawab 428 → tes gagal cepat, tanpa perlu DB (428 dicek
# SEBELUM body dijalankan).
class TestRealEndpointsProtected:

    @pytest.fixture
    def app_real(self):
        a = Flask(__name__)
        a.secret_key = 'test-secret'
        from modules.routes_cash import register_cash_routes
        from modules.routes_spa import register_spa_routes
        from modules.routes_water import register_water_routes
        register_cash_routes(a)
        register_spa_routes(a)
        register_water_routes(a)
        return a

    def _login(self, client, role, username=None):
        with client.session_transaction() as s:
            s.clear()
            s['user_role'] = role
            s['user_name'] = username or role
            s['full_name'] = 'Test User'

    def _expect_428(self, client, method, path):
        r = client.open(path, method=method, json={})
        assert r.status_code == 428, (
            f'{method} {path} harus menjawab 428 STEPUP_REQUIRED tanpa grant '
            f'(status aktual: {r.status_code})')
        body = r.get_json()
        assert body['code'] == STEPUP_REQUIRED_CODE

    def test_cash_approve_ga(self, app_real):
        c = app_real.test_client()
        self._login(c, 'ga')
        self._expect_428(c, 'POST', '/api/cash/approve-ga/1')

    def test_cash_approve_finance(self, app_real):
        c = app_real.test_client()
        self._login(c, 'finance')
        self._expect_428(c, 'POST', '/api/cash/approve-finance/1')

    def test_cash_handover(self, app_real):
        c = app_real.test_client()
        self._login(c, 'ga')
        self._expect_428(c, 'POST', '/api/cash/handover/1')

    def test_cash_approve_lpj(self, app_real):
        c = app_real.test_client()
        self._login(c, 'ga')
        self._expect_428(c, 'POST', '/api/cash/approve-lpj/1')

    def test_queue_approve_ga(self, app_real):
        c = app_real.test_client()
        self._login(c, 'ga')
        self._expect_428(c, 'POST', '/api/queue/approve-ga/1')

    def test_queue_payout(self, app_real):
        c = app_real.test_client()
        self._login(c, 'finance')
        self._expect_428(c, 'POST', '/api/queue/payout/1')

    def test_queue_verify(self, app_real):
        c = app_real.test_client()
        self._login(c, 'ga')
        self._expect_428(c, 'POST', '/api/queue/verify/1')

    def test_water_verify(self, app_real):
        c = app_real.test_client()
        self._login(c, 'finance')
        self._expect_428(c, 'POST', '/api/water/purchases/1/verify')

    def test_grant_aktif_lolos_hanya_role_sesuai(self, app_real):
        """Grant aktif → aksi kasbon GA bisa jalan (bukan 428 lagi).

        Memakai /api/cash/approve-ga: role ga + grant → lolos step-up.
        (Body rute tidak dieksekusi penuh — DB di-mock agar test tetap unit.)
        """
        client = app_real.test_client()
        self._login(client, 'ga')
        with client.session_transaction() as s:
            s['stepup_until'] = time.time() + stepup_mod.STEPUP_TTL

        # Role tidak sesuai harus tetap 403 (role_required) walau ada grant
        client_fin = app_real.test_client()
        self._login(client_fin, 'finance')
        with client_fin.session_transaction() as s:
            s['stepup_until'] = time.time() + stepup_mod.STEPUP_TTL
        r = client_fin.post('/api/cash/approve-ga/1', json={})
        assert r.status_code == 403, 'finance tidak boleh approve-ga walau punya grant'

    def test_tanpa_login_401_bukan_428(self, app_real):
        """Tanpa sesi → 401 (role_required menolak dulu), bukan 428."""
        r = app_real.test_client().post('/api/cash/approve-ga/1', json={})
        assert r.status_code == 401