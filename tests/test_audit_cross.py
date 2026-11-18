"""Unit tests — audit log lintas cabang untuk Admin Pusat (v2.116.0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_audit_cross as ac  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._one = None
        self._rows = []

    def execute(self, sql, params=None):
        s = ' '.join(str(sql).split())
        self.conn.queries.append((s, list(params or [])))
        if self.conn.name == 'BROKEN':
            raise RuntimeError('Table activity_logs tidak ada')
        if 'FROM activity_logs WHERE id=' in s:
            self._one = self.conn.detail
            self._rows = []
        else:
            self._rows = self.conn.rows
            self._one = None

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, name, rows=None, detail=None):
        self.name = name
        self.rows = rows or []
        self.detail = detail
        self.queries = []
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def close(self):
        self.closed = True


BRANCHES = [
    {'code': 'SBY', 'name': 'Surabaya', 'db_name': 'db_sby', 'is_active': 1},
    {'code': 'MLG', 'name': 'Malang', 'db_name': 'db_mlg', 'is_active': 1},
    {'code': 'OFF', 'name': 'Nonaktif', 'db_name': 'db_off', 'is_active': 0},
]

LOG_SBY = [{'id': 3, 'transaction_id': 'BPF-3', 'action': 'approve',
            'user_type': 'ga', 'user_name': 'ga_sby', 'created_at':
            '2026-11-18 10:00:00', 'ip_address': '10.0.0.1', 'branch_code': None}]
LOG_MLG = [{'id': 9, 'transaction_id': 'BPF-9', 'action': 'delete_tx',
            'user_type': 'admin', 'user_name': 'admin_mlg',
            'created_at': '2026-11-18 11:00:00', 'ip_address': '10.0.0.2',
            'branch_code': 'MLG'}]


def _client(monkeypatch, role='admin', username='admin', broken=False):
    conns = {
        'db_sby': FakeConn('db_sby', LOG_SBY),
        'db_mlg': FakeConn('db_mlg', LOG_MLG),
        'db_off': FakeConn('db_off', []),
        'BROKEN': FakeConn('BROKEN'),
    }
    monkeypatch.setattr(ac, 'get_master_connection', lambda: FakeConn('master'))
    monkeypatch.setattr(ac.bm, 'list_branches',
                        lambda conn=None: list(BRANCHES))
    monkeypatch.setattr(ac.bm, 'get_branch',
                        lambda code, conn=None: next(
                            (b for b in BRANCHES if b['code'] == code), None))
    monkeypatch.setattr(ac, '_connect_db',
                        lambda db: conns['BROKEN'] if broken else conns.get(db))
    app = Flask(__name__)
    app.secret_key = 'uji-audit-cross'
    ac.register_audit_cross_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = 'SBY'
        s['full_name'] = 'Uji Audit'
    return client, conns


def test_ho_menggabungkan_log_dan_menandai_cabang(monkeypatch):
    client, conns = _client(monkeypatch)
    r = client.get('/api/admin/audit-logs/all')
    assert r.status_code == 200
    data = r.get_json()
    # Urut terbaru dulu & cabang kosong diisi kode cabangnya.
    assert [x['id'] for x in data['logs']] == [9, 3]
    assert data['logs'][0]['branch'] == 'MLG'
    assert data['logs'][1]['branch'] == 'SBY'
    assert data['logs'][1]['branch_code'] == 'SBY'
    # Cabang nonaktif tidak ikut fan-out "semua".
    assert data['summary']['branches'] == 2
    assert data['summary']['returned'] == 2
    assert conns['db_off'].queries == []


def test_db_satu_cabang_mati_tidak_mengosongkan_hasil(monkeypatch):
    # db_sby rusak, db_mlg tetap terbaca.
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(ac, '_connect_db',
                        lambda db: FakeConn('BROKEN') if db == 'db_sby'
                        else FakeConn('db_mlg', LOG_MLG))
    r = client.get('/api/admin/audit-logs/all')
    assert r.status_code == 200
    data = r.get_json()
    assert [x['id'] for x in data['logs']] == [9]
    assert data['summary']['errors'] == 1
    assert data['errors'][0]['branch'] == 'SBY'


def test_filter_cabang_aksi_dan_pencarian(monkeypatch):
    client, conns = _client(monkeypatch)
    client.get('/api/admin/audit-logs/all?branch=MLG&action=delete_tx&q=admin')
    sql, params = conns['db_mlg'].queries[0]
    assert 'action=%s' in sql
    assert 'user_name LIKE %s' in sql
    assert ['delete_tx', '%admin%', '%admin%', '%admin%', '%admin%', 50] == params[1:]


def test_admin_cabang_ditolak(monkeypatch):
    client, _ = _client(monkeypatch, username='admin_sby')
    r = client.get('/api/admin/audit-logs/all')
    assert r.status_code == 403


def test_detail_lintas_cabang_memakai_db_cabangnya(monkeypatch):
    client, conns = _client(monkeypatch)
    conns['db_mlg'].detail = {
        'id': 9, 'transaction_id': 'BPF-9', 'action': 'delete_tx',
        'user_type': 'admin', 'user_name': 'admin_mlg',
        'old_data': '{"status": "verified_ga"}', 'new_data': None,
        'ip_address': '10.0.0.2', 'user_agent': 'uji', 'branch_code': 'MLG',
        'created_at': '2026-11-18 11:00:00',
    }
    r = client.get('/api/admin/audit-logs/all/MLG/9')
    assert r.status_code == 200
    data = r.get_json()
    assert data['branch'] == 'MLG'
    # Snapshot string JSON diubah jadi objek untuk UI.
    assert data['old_data'] == {'status': 'verified_ga'}


def test_detail_cabang_tak_dikenal_400(monkeypatch):
    client, _ = _client(monkeypatch)
    r = client.get('/api/admin/audit-logs/all/XXX/1')
    assert r.status_code == 400
