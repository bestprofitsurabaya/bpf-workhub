"""Uji ekspor lintas cabang CV Online & FirstWork (v2.115.0 — Fase 2).

Admin Pusat boleh memilih satu cabang atau semua cabang; role cabang tidak
boleh dibelokkan ke cabang lain lewat query string.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_cv_online as cv  # noqa: E402
import modules.routes_first_work as fw  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.calls.append((' '.join(str(sql).split()), list(params or [])))

    def fetchone(self):
        return {'total': 0, 'n': 0}

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.calls = []
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def _app(module):
    app = Flask(__name__)
    app.secret_key = 'uji-ekspor'
    if module is cv:
        module.register_cv_online_routes(app)
    else:
        module.register_first_work_routes(app)
    return app


def _client(module, monkeypatch, role='admin', username='admin', branch='SBY'):
    conn = FakeConn()
    monkeypatch.setattr(module, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(module, 'log_activity_async', lambda *a, **k: None)
    app = _app(module)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = branch
        s['full_name'] = 'Uji Ekspor'
    return client, conn


def _where(calls, table):
    """Ambil (sql, params) query pertama yang menyentuh tabel tertentu."""
    for sql, params in calls:
        if table in sql:
            return sql, params
    return '', []


def test_cv_export_admin_pusat_bisa_pilih_cabang(monkeypatch):
    client, conn = _client(cv, monkeypatch)
    r = client.get('/api/cv-online/export?branch=MLG&status=submitted')
    assert r.status_code == 200
    sql, params = _where(conn.calls, 'cv_online_submissions')
    assert 'branch_code=%s' in sql
    assert 'MLG' in params
    assert 'submitted' in params


def test_cv_export_admin_pusat_semua_cabang_tanpa_filter(monkeypatch):
    client, conn = _client(cv, monkeypatch)
    r = client.get('/api/cv-online/export')
    assert r.status_code == 200
    sql, _params = _where(conn.calls, 'cv_online_submissions')
    assert 'branch_code' not in sql


def test_cv_export_role_cabang_tidak_bisa_dibelokkan(monkeypatch):
    client, conn = _client(cv, monkeypatch, role='traineer',
                           username='traineer_mlg', branch='MLG')
    r = client.get('/api/cv-online/export?branch=SBY')
    assert r.status_code == 200
    sql, params = _where(conn.calls, 'cv_online_submissions')
    assert 'branch_code=%s' in sql
    assert params[0] == 'MLG'
    assert 'SBY' not in params


def test_fw_export_admin_pusat_bisa_pilih_cabang_dan_pencarian(monkeypatch):
    client, conn = _client(fw, monkeypatch)
    r = client.get('/api/first-work/export?branch=BDG&q=Budi')
    assert r.status_code == 200
    sql, params = _where(conn.calls, 'first_work_submissions')
    assert 's.branch_code=%s' in sql
    assert 'BDG' in params
    assert any('%Budi%' == p for p in params)


def test_fw_export_role_cabang_terkunci_ke_cabangnya(monkeypatch):
    client, conn = _client(fw, monkeypatch, role='traineer',
                           username='traineer_mlg', branch='MLG')
    r = client.get('/api/first-work/export?branch=BDG')
    assert r.status_code == 200
    _sql, params = _where(conn.calls, 'first_work_submissions')
    assert 'MLG' in params
    assert 'BDG' not in params


def test_cv_list_statistik_mengikuti_filter_cabang(monkeypatch):
    client, conn = _client(cv, monkeypatch)
    r = client.get('/api/cv-online?branch=MLG')
    assert r.status_code == 200
    stat_calls = [params for sql, params in conn.calls
                  if 'GROUP BY status' in sql]
    assert stat_calls and stat_calls[0] == ['MLG']
