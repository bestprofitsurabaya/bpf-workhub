"""Unit test — MFA TOTP (v2.112.0).

Mencakup:
- vektor uji RFC 6238 (SHA1, 6 digit) → kompatibel Microsoft/Google Authenticator
- enkripsi rahasia (encrypt-then-MAC) & deteksi tamper
- anti-replay (`mfa_last_step`)
- kode pemulihan sekali pakai
- logika kebijakan: off / optional / required_roles + masa tenggang
- endpoint login dua langkah (verify, enroll) & validasi admin

Jalankan:
    python3 -m pytest tests/test_mfa.py -v
"""
import sys
import os
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

import modules.mfa as core
import modules.routes_mfa as routes_mfa
from modules.routes_mfa import register_mfa_routes

# RFC 6238 lampiran B — rahasia ASCII "12345678901234567890" dalam base32.
RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


# ---------------------------------------------------------------------------
# TOTP inti
# ---------------------------------------------------------------------------
def test_totp_rfc6238_vectors_6_digit():
    # Nilai RFC 8 digit dipotong 6 digit terakhir (DIGITS=6).
    vectors = {
        59: '287082',
        1111111109: '081804',
        1111111111: '050471',
        1234567890: '005924',
        2000000000: '279037',
        20000000000: '353130',
    }
    for at, expected in vectors.items():
        assert core.totp_now(RFC_SECRET, at=at) == expected


def test_generate_secret_base32_dan_unik():
    a, b = core.generate_secret(), core.generate_secret()
    assert a != b
    assert len(a) >= 32
    assert '=' not in a
    assert core.totp_now(a).isdigit()


def test_match_step_window_dan_replay():
    now = 1111111111
    step = now // 30
    assert core.match_step(RFC_SECRET, '050471', at=now) == step
    # Kode sama tidak boleh dipakai dua kali.
    assert core.match_step(RFC_SECRET, '050471', at=now, last_step=step) is None
    # Window ±1: kode step sebelumnya masih diterima bila belum dipakai.
    prev_code = core.totp_now(RFC_SECRET, at=now - 30)
    assert core.match_step(RFC_SECRET, prev_code, at=now) == step - 1
    # Format salah ditolak.
    assert core.match_step(RFC_SECRET, 'abcdef', at=now) is None
    assert core.match_step(RFC_SECRET, '12345', at=now) is None
    assert core.match_step('', '123456', at=now) is None


def test_otpauth_uri_kompatibel_authenticator():
    uri = core.otpauth_uri('JBSWY3DPEHPK3PXP', 'finance_smg')
    assert uri.startswith('otpauth://totp/')
    assert 'secret=JBSWY3DPEHPK3PXP' in uri
    assert 'algorithm=SHA1' in uri
    assert 'digits=6' in uri
    assert 'period=30' in uri
    assert 'issuer=BPF%20WorkHub' in uri


# ---------------------------------------------------------------------------
# Enkripsi rahasia
# ---------------------------------------------------------------------------
def test_encrypt_decrypt_roundtrip():
    secret = core.generate_secret()
    blob = core.encrypt_secret(secret)
    assert blob and secret not in blob
    assert core.decrypt_secret(blob) == secret


def test_decrypt_menolak_tamper_dan_sampah():
    blob = core.encrypt_secret('JBSWY3DPEHPK3PXP')
    tampered = blob[:-4] + ('AAAA' if not blob.endswith('AAAA') else 'BBBB')
    assert core.decrypt_secret(tampered) == ''
    assert core.decrypt_secret('bukan-base64!!') == ''
    assert core.decrypt_secret('') == ''


# ---------------------------------------------------------------------------
# Kode pemulihan
# ---------------------------------------------------------------------------
def test_recovery_code_format_dan_hash():
    codes = core.generate_recovery_codes(10)
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11 and code[5] == '-'
    # Hash peka normalisasi (huruf kecil/spasi tetap sama).
    assert core.hash_recovery(codes[0]) == core.hash_recovery(codes[0].lower().replace('-', ' '))
    assert core.hash_recovery(codes[0]) != core.hash_recovery(codes[1])
    assert len(core.hash_recovery(codes[0])) == 64


# ---------------------------------------------------------------------------
# Kebijakan
# ---------------------------------------------------------------------------
def _policy(policy='required_roles', roles=None, grace=0, enforced_at=None):
    return {
        'policy': policy,
        'required_roles': roles if roles is not None else ['admin'],
        'grace_days': grace,
        'enforced_at': enforced_at,
    }


def _user(role='admin', enrolled=False):
    return {
        'role': role,
        'mfa_enabled': 1 if enrolled else 0,
        'mfa_secret': 'x' if enrolled else None,
    }


def test_default_required_roles_kecuali_marketing_ob_driver():
    for role in ('marketing', 'ob', 'driver'):
        assert role not in core.DEFAULT_REQUIRED_ROLES
    for role in ('admin', 'finance', 'security', 'traineer', 'chief_driver', 'it_sby'):
        assert role in core.DEFAULT_REQUIRED_ROLES


def test_policy_off_adalah_kill_switch():
    assert core.requirement_for_user(_user('admin', enrolled=True), _policy('off'))['required'] is False
    assert core.requirement_for_user(_user('admin'), _policy('off'))['required'] is False


def test_policy_optional():
    enrolled = core.requirement_for_user(_user('admin', enrolled=True), _policy('optional'))
    assert enrolled['required'] is True and enrolled['mode'] == 'verify'
    fresh = core.requirement_for_user(_user('admin'), _policy('optional'))
    assert fresh['required'] is False and fresh['optional'] is True


def test_policy_required_roles():
    must = core.requirement_for_user(_user('admin'), _policy('required_roles', ['admin']))
    assert must['required'] is True and must['mode'] == 'enroll'
    other = core.requirement_for_user(_user('marketing'), _policy('required_roles', ['admin']))
    assert other['required'] is False
    # User yang sudah mendaftar selalu verifikasi (bukan enroll).
    enrolled = core.requirement_for_user(_user('admin', enrolled=True), _policy('required_roles', ['admin']))
    assert enrolled['required'] is True and enrolled['mode'] == 'verify'


def test_masa_tenggang_menunda_pendaftaran():
    pol = _policy('required_roles', ['admin'], grace=7, enforced_at=datetime.now())
    req = core.requirement_for_user(_user('admin'), pol)
    assert req['required'] is False
    assert req['nudge'] is True
    assert 6.5 < req['grace_days_left'] <= 7

    expired = _policy('required_roles', ['admin'], grace=7,
                      enforced_at=datetime.now() - timedelta(days=8))
    assert core.requirement_for_user(_user('admin'), expired)['required'] is True


def test_grace_days_left_nol_bila_tidak_berlaku():
    assert core.grace_days_left(_policy('optional', grace=7, enforced_at=datetime.now())) == 0
    assert core.grace_days_left(_policy('required_roles', grace=0, enforced_at=datetime.now())) == 0
    assert core.grace_days_left(_policy('required_roles', grace=7, enforced_at=None)) == 0


# ---------------------------------------------------------------------------
# Endpoint — fake DB
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        s = ' '.join(str(sql).split())
        if s.startswith('SELECT') and 'FROM users' in s:
            if 'WHERE id=%s' in s:
                self.rows = [dict(self.conn.user)] if self.conn.user else []
            elif 'WHERE username=%s' in s:
                self.rows = [dict(self.conn.user)] if self.conn.user else []
            else:
                self.rows = []
        elif 'FROM mfa_recovery_codes' in s and 'COUNT(*)' in s:
            self.rows = [{'n': sum(1 for r in self.conn.recovery if not r.get('used_at'))}]
        elif 'FROM mfa_recovery_codes' in s:
            self.rows = [dict(r) for r in self.conn.recovery if not r.get('used_at')]
        elif 'FROM system_config' in s:
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, user=None, recovery=None):
        self.user = user
        self.recovery = recovery or []
        self.executed = []
        self.committed = False
        self.rolled = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__)
    a.secret_key = 'test-secret'
    register_mfa_routes(a)
    monkeypatch.setattr(routes_mfa, 'log_activity_async', lambda *args, **kwargs: None)
    monkeypatch.setattr(routes_mfa, '_post_login_sync', lambda user: None)
    monkeypatch.setattr(routes_mfa, 'mfa_rate_check', lambda ip, username='': (True, 0))
    monkeypatch.setattr(routes_mfa, 'mfa_fail', lambda ip, username='': (False, 0))
    monkeypatch.setattr(routes_mfa, 'mfa_success', lambda ip, username='': None)
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def _pending(client, uid=1, username='admin', at=None, mode='verify'):
    with client.session_transaction() as s:
        s['mfa_pending_user'] = username
        s['mfa_pending_uid'] = uid
        s['mfa_pending_role'] = 'admin'
        s['mfa_pending_branch'] = 'SBY'
        s['mfa_pending_branch_name'] = 'Surabaya'
        s['mfa_pending_at'] = time.time() if at is None else at
        s['mfa_pending_mode'] = mode


def _enrolled_user(secret):
    return {
        'id': 1, 'username': 'admin', 'full_name': 'Admin Pusat', 'role': 'admin',
        'branch_code': 'SBY', 'is_active': 1, 'mfa_enabled': 1,
        'mfa_secret': core.encrypt_secret(secret), 'mfa_enrolled_at': None,
        'mfa_last_step': None,
    }


def test_verify_tanpa_sesi_pending_ditolak(client):
    r = client.post('/api/auth/mfa/verify', json={'code': '123456'})
    assert r.status_code == 401


def test_verify_sesi_kedaluwarsa(client):
    _pending(client, at=time.time() - 601)
    r = client.post('/api/auth/mfa/verify', json={'code': '123456'})
    assert r.status_code == 401
    assert r.get_json()['code'] == 'MFA_EXPIRED'


def test_verify_kode_salah(client, monkeypatch):
    secret = core.generate_secret()
    conn = FakeConn(user=_enrolled_user(secret))
    monkeypatch.setattr(routes_mfa, 'get_master_connection', lambda: conn)
    _pending(client)
    r = client.post('/api/auth/mfa/verify', json={'code': '000000'})
    assert r.status_code == 401
    assert r.get_json()['code'] == 'MFA_INVALID'


def test_verify_kode_benar_membuat_sesi_penuh(client, monkeypatch):
    secret = core.generate_secret()
    conn = FakeConn(user=_enrolled_user(secret))
    monkeypatch.setattr(routes_mfa, 'get_master_connection', lambda: conn)
    _pending(client)
    r = client.post('/api/auth/mfa/verify', json={'code': core.totp_now(secret)})
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] == 'success'
    assert data['user']['role'] == 'admin'
    assert data['mfa'] is True
    with client.session_transaction() as s:
        assert s.get('user_role') == 'admin'
        assert s.get('mfa_pending_user') is None
        assert s.get('mfa_pending_uid') is None
    # mfa_last_step disimpan (anti-replay).
    assert any('UPDATE users SET mfa_last_step' in sql for sql, _ in conn.executed)


def test_verify_kode_pemulihan_sekali_pakai(client, monkeypatch):
    secret = core.generate_secret()
    code = 'ABCDE-12345'
    user = _enrolled_user(secret)
    conn = FakeConn(user=user, recovery=[{'id': 7, 'code_hash': core.hash_recovery(code), 'used_at': None}])
    monkeypatch.setattr(routes_mfa, 'get_master_connection', lambda: conn)
    _pending(client)
    r = client.post('/api/auth/mfa/verify', json={'recovery_code': code})
    assert r.status_code == 200
    assert r.get_json()['recovery_used'] is True
    assert any('UPDATE mfa_recovery_codes SET used_at=NOW()' in sql for sql, _ in conn.executed)
    assert conn.committed is True


def test_enroll_start_mengembalikan_qr_dan_secret(client):
    _pending(client, mode='enroll')
    r = client.post('/api/auth/mfa/enroll/start')
    assert r.status_code == 200
    d = r.get_json()
    assert d['secret']
    assert d['otpauth_uri'].startswith('otpauth://totp/')
    # segno terpasang di image produksi; di host dev bisa tidak ada.
    assert d['qr'] == '' or d['qr'].startswith('data:image/svg+xml;base64,')
    with client.session_transaction() as s:
        assert s.get('mfa_pending_secret')


def test_enroll_confirm_menyimpan_dan_memberi_10_kode_pemulihan(client, monkeypatch):
    _pending(client, mode='enroll')
    start = client.post('/api/auth/mfa/enroll/start').get_json()
    user = {
        'id': 1, 'username': 'admin', 'full_name': 'Admin Pusat', 'role': 'admin',
        'branch_code': 'SBY', 'is_active': 1, 'mfa_enabled': 0,
        'mfa_secret': None, 'mfa_enrolled_at': None, 'mfa_last_step': None,
    }
    conn = FakeConn(user=user)
    monkeypatch.setattr(routes_mfa, 'get_master_connection', lambda: conn)
    r = client.post('/api/auth/mfa/enroll/confirm', json={'code': core.totp_now(start['secret'])})
    assert r.status_code == 200
    d = r.get_json()
    assert d['enrolled'] is True
    assert len(d['recovery_codes']) == 10
    assert any('UPDATE users SET mfa_enabled=1' in sql for sql, _ in conn.executed)
    with client.session_transaction() as s:
        assert s.get('user_role') == 'admin'


def test_admin_settings_menolak_kebijakan_tidak_dikenal(client):
    with client.session_transaction() as s:
        s['user_role'] = 'admin'
        s['user_name'] = 'admin'
        s['stepup_until'] = time.time() + 60
    r = client.put('/api/security/mfa/settings', json={'policy': 'ngawur', 'grace_days': 7})
    assert r.status_code == 400


def test_admin_settings_wajib_role_admin(client):
    with client.session_transaction() as s:
        s['user_role'] = 'finance'
        s['stepup_until'] = time.time() + 60
    r = client.put('/api/security/mfa/settings', json={'policy': 'off', 'grace_days': 7})
    assert r.status_code == 403


def test_admin_settings_wajib_stepup(client):
    with client.session_transaction() as s:
        s['user_role'] = 'admin'
    r = client.put('/api/security/mfa/settings', json={'policy': 'off', 'grace_days': 7})
    assert r.status_code == 428
    assert r.get_json()['code'] == 'STEPUP_REQUIRED'


def test_kebijakan_gagal_dibaca_fail_open_kecuali_akun_ber_mfa():
    """DB tidak terbaca → jangan paksa pendaftaran (login tetap jalan).

    Akun yang sudah punya rahasia TOTP tetap wajib verifikasi (fail-closed),
    karena verifikasi tidak bergantung pada pembacaan kebijakan.
    """
    broken = dict(_policy('required_roles', ['admin']), ok=False)
    assert core.requirement_for_user(_user('admin'), broken)['required'] is False
    enrolled = core.requirement_for_user(_user('admin', enrolled=True), broken)
    assert enrolled['required'] is True and enrolled['mode'] == 'verify'
