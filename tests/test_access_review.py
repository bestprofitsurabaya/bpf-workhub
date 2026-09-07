"""
Unit Tests — Access Review & Laporan Akun Basi (v2.32.0, Tahap 3/6 ISO/IEC 27001).

- classify_account   : never_login / stale / ok / inactive
- GET  /api/admin/access-review          → laporan + ringkasan + review info (admin only)
- POST /api/admin/access-review/complete → tandai review selesai (audit + config)
- GET  /api/admin/access-review/export   → CSV arsip triwulanan (admin only)

Pola sama dengan test_docseq_admin (DB di-fake, sesi lewat test client).
"""

import sys
import os
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_accessreview as ra  # noqa: E402


# ================================================================
# Fake conn/cursor
# ================================================================
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.log = []
        self._fetchall = []

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))
        self._fetchall = self.conn._pick(sql)
        return None

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        return (self._fetchall or [None])[0]

    def close(self):
        pass


class FakeConn:
    """Satu cursor per pemanggilan cursor() — rows di-pick sesuai query."""

    def __init__(self, users=None, config=None):
        self.users = users or []
        self.config = config or []
        self.cur = None
        self.commits = 0

    def cursor(self, dictionary=True):
        # Pilih baris sesuai query (dikenali saat execute): users / system_config
        self.cur = FakeCursor(self)
        return self.cur

    def _pick(self, sql):
        if 'FROM users' in sql:
            return self.users
        if 'FROM system_config' in sql:
            return self.config
        return []

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _user(**kw):
    base = {'id': 1, 'username': 'u', 'full_name': 'User', 'role': 'ga',
            'team_name': '', 'branch_code': 'SBY', 'is_active': 1,
            'last_login': None}
    base.update(kw)
    return base


def _patch_db(monkeypatch, users, config=None):
    conn = FakeConn(users=users, config=config or [])
    monkeypatch.setattr(ra, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(ra, 'log_activity_async', lambda *a, **k: None)
    return conn


def _make_client(monkeypatch, users, config=None, role='admin'):
    conn = _patch_db(monkeypatch, users, config)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    ra.register_access_review_routes(app)
    client = app.test_client()
    if role:
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = role
            s['full_name'] = 'Test Admin'
    return client, conn


# ================================================================
# Logika murni: klasifikasi akun
# ================================================================
class TestClassifyAccount:
    def test_nonaktif(self):
        assert ra.classify_account(_user(is_active=0)) == 'inactive'
        assert ra.classify_account(_user(is_active=False)) == 'inactive'

    def test_aktif_belum_pernah_login(self):
        assert ra.classify_account(_user(is_active=1, last_login=None)) == 'never_login'

    def test_aktif_login_baru(self):
        u = _user(is_active=1, last_login=datetime.now() - timedelta(days=5))
        assert ra.classify_account(u) == 'ok'

    def test_aktif_login_lama_stale(self):
        u = _user(is_active=1, last_login=datetime.now() - timedelta(days=200))
        assert ra.classify_account(u) == 'stale'

    def test_stale_days_env_custom(self, monkeypatch):
        monkeypatch.setattr(ra, 'STALE_ACCOUNT_DAYS', 30)
        u = _user(is_active=1, last_login=datetime.now() - timedelta(days=45))
        assert ra.classify_account(u, stale_days=30) == 'stale'
        assert ra.classify_account(u, stale_days=60) == 'ok'

    def test_last_login_string_iso(self):
        u = _user(is_active=1, last_login=datetime.now().isoformat())
        assert ra.classify_account(u) == 'ok'
        u2 = _user(is_active=1, last_login='2020-01-01T00:00:00')
        assert ra.classify_account(u2) == 'stale'

    def test_last_login_rusak_dianggap_stale(self):
        u = _user(is_active=1, last_login='bukan-tanggal')
        assert ra.classify_account(u) == 'stale'


class TestBuildReport:
    def test_ringkasan_dan_label(self):
        rows = [
            _user(id=1, username='ok1', last_login=datetime.now() - timedelta(days=1)),
            _user(id=2, username='stale1', last_login=datetime.now() - timedelta(days=200)),
            _user(id=3, username='never1', last_login=None),
            _user(id=4, username='off1', is_active=0),
        ]
        rep = ra._build_report(rows)
        s = rep['summary']
        assert s['total'] == 4
        assert s['active'] == 3
        assert s['inactive'] == 1
        assert s['ok'] == 1
        assert s['stale'] == 1
        assert s['never_login'] == 1
        by = {u['username']: u for u in rep['users']}
        assert by['ok1']['account_status'] == 'ok'
        assert by['stale1']['account_status'] == 'stale'
        assert by['never1']['account_status'] == 'never_login'
        assert by['off1']['account_status'] == 'inactive'
        assert by['ok1']['account_status_label'] == 'OK'

    def test_csv_lengkap(self):
        rows = [_user(id=1, username='ga_sby', full_name='GA Surabaya',
                      role='ga', branch_code='SBY',
                      last_login=datetime.now() - timedelta(days=300))]
        rep = ra._build_report(rows)
        csv_text = ra._build_csv(rep)
        assert csv_text.startswith('\ufeff')
        lines = csv_text.strip('\ufeff').strip().split('\n')
        assert lines[0].startswith('Username,Nama Lengkap,Role,Tim,Cabang,Status Akun')
        assert 'ga_sby' in lines[1]
        assert 'GA' in lines[1]
        assert 'Basi' in lines[1]


# ================================================================
# Route API
# ================================================================
class TestAccessReviewAPI:
    def test_wajib_admin(self, monkeypatch):
        c, _ = _make_client(monkeypatch, users=[], role='ga')
        assert c.get('/api/admin/access-review').status_code == 403
        assert c.post('/api/admin/access-review/complete').status_code == 403
        assert c.get('/api/admin/access-review/export').status_code == 403
        c2, _ = _make_client(monkeypatch, users=[], role=None)
        assert c2.get('/api/admin/access-review').status_code == 401

    def test_list_ok(self, monkeypatch):
        users = [
            _user(id=1, username='ga_sby', last_login=datetime.now() - timedelta(days=2)),
            _user(id=2, username='ob_old', last_login=datetime.now() - timedelta(days=400)),
            _user(id=3, username='never', last_login=None),
            _user(id=4, username='off', is_active=0),
        ]
        c, _ = _make_client(monkeypatch, users=users,
                            config=[{'config_key': ra.REVIEW_AT_KEY, 'config_value': '2026-06-01 09:00:00'},
                                    {'config_key': ra.REVIEW_BY_KEY, 'config_value': 'Administrator'}])
        r = c.get('/api/admin/access-review')
        assert r.status_code == 200
        d = r.get_json()
        assert d['summary']['total'] == 4
        assert d['summary']['stale'] == 1
        assert d['stale_days'] == ra.STALE_ACCOUNT_DAYS
        assert d['review']['last_at'] == '2026-06-01 09:00:00'
        assert d['review']['last_by'] == 'Administrator'

    def test_complete_menyimpan_config_dan_audit(self, monkeypatch):
        c, conn = _make_client(monkeypatch, users=[], role='admin')
        r = c.post('/api/admin/access-review/complete')
        assert r.status_code == 200
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['last_by'] == 'Test Admin'
        assert conn.commits >= 1
        # Query INSERT ... ON DUPLICATE untuk kedua key config
        inserts = [q for q, _ in conn.cur.log if 'ON DUPLICATE' in q] if conn.cur else []
        assert len(inserts) >= 1

    def test_export_csv(self, monkeypatch):
        users = [_user(id=1, username='ga_sby', last_login=datetime.now() - timedelta(days=2))]
        c, _ = _make_client(monkeypatch, users=users)
        r = c.get('/api/admin/access-review/export')
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        text = r.get_data(as_text=True)
        assert text.startswith('\ufeff')
        assert 'ga_sby' in text

    def test_db_tidak_tersedia(self, monkeypatch):
        monkeypatch.setattr(ra, 'get_master_connection', lambda: None)
        monkeypatch.setattr(ra, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ra.register_access_review_routes(app)
        c = app.test_client()
        with c.session_transaction() as s:
            s['user_role'] = 'admin'
            s['user_name'] = 'admin'  # v2.37.0: scoping admin membaca username sesi
        assert c.get('/api/admin/access-review').status_code == 500
        assert c.post('/api/admin/access-review/complete').status_code == 500