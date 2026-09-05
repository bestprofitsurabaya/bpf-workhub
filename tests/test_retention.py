"""
Unit Tests — Retensi & Arsip Dokumen v2.34.0 (Tahap 5/6 ISO).

- `_cutoff_datetime` / `_env_days` / `_class_meta` — logika kebijakan murni
- `ensure_retention_tables` — DDL idempoten (archive + register)
- `archive_audit_db` — INSERT...SELECT lalu DELETE (transaksi)
- `GET  /api/admin/retention/overview`       → kebijakan + inventaris (admin)
- `POST /api/admin/retention/archive-audit`  → arsip lintas DB (admin only)

Pola: DB di-fake via monkeypatch fungsi modul (sama dgn test_docseq_admin).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta  # noqa: E402

from flask import Flask  # noqa: E402

import modules.routes_retention as rr  # noqa: E402
from modules import branch_manager  # noqa: E402


class FakeCursor:
    def __init__(self, rows=None, rowcount=0, dictionary=True):
        self.rows = rows or []
        self.rowcount = rowcount
        self.dictionary = dictionary
        self.log = []

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))
        return None

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None, rowcount=0, name='bpf_asset_system'):
        self.cur = FakeCursor(rows, rowcount)
        self.commits = 0
        self.name = name

    def cursor(self, dictionary=True):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _client(monkeypatch, role='admin', master=None):
    monkeypatch.setattr(rr, 'log_activity_async', lambda *a, **k: None)
    if master is not None:
        monkeypatch.setattr(rr, 'get_master_connection', lambda: master)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rr.register_retention_routes(app)
    client = app.test_client()
    if role:
        with client.session_transaction() as s:
            s['user_role'] = role
            s['full_name'] = 'Admin Test'
    return client


# ================================================================
# Logika murni
# ================================================================
class TestKebijakan:
    def test_cutoff_hari(self):
        c = rr._cutoff_datetime(90)
        diff = (datetime.now() - c).days
        assert diff == 90

    def test_cutoff_angka_negatif_aman(self):
        c = rr._cutoff_datetime(-5)
        assert (datetime.now() - c).days == 0

    def test_env_days_override(self, monkeypatch):
        monkeypatch.setenv('RETENTION_DAYS_AUDIT_LOGS', '365')
        cls = {'key': 'audit_logs', 'default_days': 1825}
        assert rr._env_days(cls) == 365

    def test_env_days_invalid_fallback(self, monkeypatch):
        monkeypatch.setenv('RETENTION_DAYS_AUDIT_LOGS', 'abc')
        cls = {'key': 'audit_logs', 'default_days': 1825}
        assert rr._env_days(cls) == 1825

    def test_class_meta_permanen(self):
        cls = {'key': 'transactions', 'label': 'T', 'table': 't', 'date_col': 'c',
               'scope': 'all', 'action': 'none', 'default_days': None, 'note': ''}
        m = rr._class_meta(cls, {'total': 5})
        assert m['retention_days'] is None and m['permanent'] is True
        assert m['total'] == 5

    def test_kelas_berisi_audit_logs(self):
        keys = [c['key'] for c in rr.RETENTION_CLASSES]
        assert 'audit_logs' in keys and 'transactions' in keys


class TestEnsureTables:
    def test_ddl_idempoten(self):
        conn = FakeConn()
        assert rr.ensure_retention_tables(conn) is True
        assert rr.ensure_retention_tables(conn) is True
        creates = [sql for sql, _ in conn.cur.log if 'CREATE TABLE' in sql]
        assert len(creates) == 4  # 2 tabel × 2 panggilan
        assert any('activity_logs_archive' in s for s in creates)
        assert any('retention_actions' in s for s in creates)


class TestArchiveAuditDb:
    def test_arsip_insert_delete_dan_commit(self):
        conn = FakeConn(rowcount=7)
        rows, cutoff = rr.archive_audit_db(conn, datetime(2021, 1, 1))
        assert rows == 7
        assert cutoff == '2021-01-01 00:00:00'
        stmts = [sql for sql, _ in conn.cur.log]
        assert any('INSERT INTO activity_logs_archive' in s for s in stmts)
        assert any('DELETE FROM activity_logs' in s for s in stmts)
        assert conn.commits == 1

    def test_tanpa_baris_tidak_delete(self):
        conn = FakeConn(rowcount=0)
        rows, _ = rr.archive_audit_db(conn, datetime(2021, 1, 1))
        assert rows == 0
        stmts = [sql for sql, _ in conn.cur.log]
        assert not any('DELETE FROM activity_logs' in s for s in stmts)
        assert conn.commits == 0


# ================================================================
# Routes
# ================================================================
class TestOverviewRoute:
    def test_admin_melihat_kelas(self, monkeypatch):
        master = FakeConn(rows=[{'id': 1, 'class_key': 'audit_logs', 'action': 'archive',
                                 'db_name': 'bpf_asset_system', 'cutoff_date': 'x',
                                 'rows_affected': 3, 'actor': 'Admin',
                                 'created_at': '2026-09-05 21:00:00', 'note': ''}])
        monkeypatch.setattr(rr, '_all_dbs', lambda: [('bpf_asset_system', True)])
        monkeypatch.setattr(rr, '_open_db', lambda db, m: FakeConn())
        monkeypatch.setattr(rr, '_db_inventory',
                            lambda conn, cls: {'count': 3, 'oldest': '2020-01-01',
                                               'newest': '2026-09-01', 'expired': 1})
        c = _client(monkeypatch, role='admin', master=master)
        r = c.get('/api/admin/retention/overview')
        assert r.status_code == 200
        d = r.get_json()
        assert d['status'] == 'success'
        keys = [k['key'] for k in d['classes']]
        assert 'audit_logs' in keys and 'transactions' in keys
        audit = next(k for k in d['classes'] if k['key'] == 'audit_logs')
        assert audit['action'] == 'archive'
        assert audit['total'] == 3
        assert len(d['actions']) == 1

    def test_inventory_error_tidak_gagalkan(self, monkeypatch):
        monkeypatch.setattr(rr, '_all_dbs', lambda: [('bpf_asset_system', True)])
        monkeypatch.setattr(rr, '_open_db', lambda db, m: FakeConn())
        monkeypatch.setattr(rr, '_db_inventory', lambda conn, cls: None)
        c = _client(monkeypatch, role='admin', master=FakeConn())
        r = c.get('/api/admin/retention/overview')
        assert r.status_code == 200
        assert all(k['total'] == 0 for k in r.get_json()['classes'])

    def test_non_admin_ditolak(self, monkeypatch):
        c = _client(monkeypatch, role='ga', master=FakeConn())
        assert c.get('/api/admin/retention/overview').status_code == 403


class TestArchiveAuditRoute:
    def test_arsip_berhasil(self, monkeypatch):
        master = FakeConn()
        monkeypatch.setattr(rr, '_all_dbs', lambda: [('bpf_asset_system', True)])
        monkeypatch.setattr(rr, '_open_db', lambda db, m: FakeConn(rowcount=11))
        monkeypatch.setattr(rr, '_record_action', lambda *a, **k: None)
        c = _client(monkeypatch, role='admin', master=master)
        r = c.post('/api/admin/retention/archive-audit', json={'days': 365})
        assert r.status_code == 200
        d = r.get_json()
        assert d['total_rows'] == 11
        assert d['days'] == 365
        assert d['results'][0]['rows'] == 11

    def test_days_minimal_30(self, monkeypatch):
        master = FakeConn()
        monkeypatch.setattr(rr, '_all_dbs', lambda: [('bpf_asset_system', True)])
        captured = {}

        class Conn:
            def cursor(self, dictionary=True):
                return FakeCursor(rowcount=2)

            def commit(self):
                pass

            def close(self):
                pass

            def rollback(self):
                pass

        monkeypatch.setattr(rr, '_open_db', lambda db, m: Conn())
        monkeypatch.setattr(rr, '_record_action', lambda *a, **k: None)
        c = _client(monkeypatch, role='admin', master=master)
        r = c.post('/api/admin/retention/archive-audit', json={'days': 5})
        assert r.status_code == 200
        assert r.get_json()['days'] == 30  # dikunci ke minimal 30 hari

    def test_days_tidak_valid(self, monkeypatch):
        c = _client(monkeypatch, role='admin', master=FakeConn())
        assert c.post('/api/admin/retention/archive-audit',
                      json={'days': 'abc'}).status_code == 400

    def test_non_admin_ditolak(self, monkeypatch):
        c = _client(monkeypatch, role='finance', master=FakeConn())
        assert c.post('/api/admin/retention/archive-audit',
                      json={}).status_code == 403
