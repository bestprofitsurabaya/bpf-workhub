"""Unit tests — break-glass Admin Pusat (v2.117.0)."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.break_glass as bg  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.rowcount = 0
        self.lastrowid = 0
        self._one = None

    def execute(self, sql, params=None):
        s = ' '.join(str(sql).split())
        params = list(params or [])
        if s.startswith('INSERT INTO break_glass_grants'):
            self.lastrowid = 1
            self.conn.inserted = params
        elif s.startswith('SELECT * FROM break_glass_grants'):
            self._one = self.conn.row
        elif s.startswith('UPDATE break_glass_grants'):
            if self.conn.row and not self.conn.row.get('used_at'):
                self.conn.row['used_at'] = '2026-11-18 12:00:00'
                self.rowcount = 1
            else:
                self.rowcount = 0

    def fetchone(self):
        return self._one

    def close(self):
        pass


class FakeConn:
    def __init__(self, row=None):
        self.row = row
        self.inserted = None

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        pass

    def close(self):
        pass


def _route_client(monkeypatch, role='admin', username='admin', stepup=True):
    monkeypatch.setattr(bg.bm, 'get_branch',
                        lambda code, conn=None: {'code': 'SBY', 'is_active': 1})
    app = Flask(__name__)
    app.secret_key = 'uji-break-glass'
    bg.register_break_glass_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = 'SBY'
        s['full_name'] = 'Uji BG'
        if stepup:
            s['stepup_until'] = (datetime.now() + timedelta(minutes=5)).timestamp()
    return client


def test_issue_wajib_stepup(monkeypatch):
    client = _route_client(monkeypatch, stepup=False)
    r = client.post('/api/admin/break-glass',
                    json={'action': 'delete_tx', 'target': '9',
                          'reason': 'transaksi uji ganda di cabang'})
    assert r.status_code == 428
    assert r.get_json()['code'] == 'STEPUP_REQUIRED'


def test_admin_cabang_tidak_boleh_break_glass(monkeypatch):
    client = _route_client(monkeypatch, username='admin_sby')
    r = client.post('/api/admin/break-glass',
                    json={'action': 'delete_tx', 'target': '9',
                          'reason': 'transaksi uji ganda di cabang'})
    assert r.status_code == 403


def test_alasan_terlalu_pendek_ditolak(monkeypatch):
    client = _route_client(monkeypatch)
    r = client.post('/api/admin/break-glass',
                    json={'action': 'delete_tx', 'target': '9', 'reason': 'salah'})
    assert r.status_code == 400
    assert 'minimal' in r.get_json()['msg']


def test_aksi_di_luar_allowlist_ditolak(monkeypatch):
    client = _route_client(monkeypatch)
    r = client.post('/api/admin/break-glass',
                    json={'action': 'payout', 'target': '9',
                          'reason': 'transaksi uji ganda di cabang'})
    assert r.status_code == 400


def test_issue_sukses_menerbitkan_token_dan_audit(monkeypatch):
    client = _route_client(monkeypatch)
    called = {}

    def fake_issue(branch, action, target, reason, username, ip=None):
        called.update(branch=branch, action=action, target=target,
                      reason=reason, username=username)
        return 'tok-rahasia', 7, '2026-11-18 12:05:00'

    monkeypatch.setattr(bg, 'issue', fake_issue)
    monkeypatch.setattr(bg, 'log_activity_async', lambda *a, **k: None)
    r = client.post('/api/admin/break-glass',
                    json={'action': 'delete_tx', 'target': '9',
                          'reason': 'transaksi uji ganda di cabang'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['token'] == 'tok-rahasia'
    assert data['grant_id'] == 7
    assert called == {'branch': 'SBY', 'action': 'delete_tx', 'target': '9',
                      'reason': 'transaksi uji ganda di cabang',
                      'username': 'Uji BG'}


def _row(**over):
    row = {
        'id': 3, 'branch_code': 'SBY', 'action': 'delete_tx', 'target_ref': '9',
        'reason': 'transaksi uji ganda di cabang', 'issued_by': 'Admin',
        'used_at': None, 'expires_at': (datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'),
    }
    row.update(over)
    return row


def test_consume_sekali_pakai(monkeypatch):
    conn = FakeConn(_row())
    monkeypatch.setattr(bg, 'get_master_connection', lambda: conn)
    ok, info = bg.consume('tok', 'SBY', 'delete_tx', '9', 'Admin')
    assert ok is True
    assert info['reason'].startswith('transaksi uji')
    ok2, err = bg.consume('tok', 'SBY', 'delete_tx', '9', 'Admin')
    assert ok2 is False
    assert 'sudah dipakai' in err


def test_consume_menolak_kedaluwarsa_dan_target_lain(monkeypatch):
    expired = FakeConn(_row(expires_at='2020-01-01 00:00:00'))
    monkeypatch.setattr(bg, 'get_master_connection', lambda: expired)
    ok, err = bg.consume('tok', 'SBY', 'delete_tx', '9', 'Admin')
    assert ok is False and 'kedaluwarsa' in err

    mismatch = FakeConn(_row())
    monkeypatch.setattr(bg, 'get_master_connection', lambda: mismatch)
    ok, err = bg.consume('tok', 'MLG', 'delete_tx', '9', 'Admin')
    assert ok is False and 'tidak cocok' in err


def test_consume_token_kosong(monkeypatch):
    ok, err = bg.consume('', 'SBY', 'delete_tx', '9', 'Admin')
    assert ok is False and 'wajib' in err
