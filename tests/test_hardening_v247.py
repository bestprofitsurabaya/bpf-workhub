"""Hardening v2.47.1 — endpoint legacy yang dulu terbuka kini butuh sesi.

- POST /api/assignments/confirm : dulu tanpa autentikasi (siapa pun bisa
  menandai konfirmasi assignment atas nama driver mana pun) & dikecualikan
  CSRF. Kini identitas diambil dari sesi (resolve_driver_scope).
- POST /api/verify-pin          : dulu publik -> brute-force PIN 6 digit +
  enumerasi user; v2.47.1 wajib login; v2.73.0 DIHAPUS (cleanup fitur
  terbenam — penggantinya /api/step-up). Uji memastikan 404.
- GET  /api/vehicle_bbm/<t>     : duplikat /api/vehicle-allowed-bbm/<t>
  tanpa pemanggil — v2.73.0 DIHAPUS; uji memastikan 404 & penggantinya hidup.
- GET  /admin/backup            : mysqldump hilang/gagal -> 503 + log stderr
  (bukan 500 tanpa keterangan).
"""
import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_api_assignments as raa  # noqa: E402
import modules.routes_api_master as ram  # noqa: E402
import modules.routes_reports as rr  # noqa: E402


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        self.conn.sql_log.append((sql, params or ()))
        self._rows = self.conn.rows_for(sql)
        return self

    def fetchone(self):
        return (self._rows or [None])[0]

    def fetchall(self):
        return self._rows

    @property
    def rowcount(self):
        return self.conn.rowcount

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows_for=None, rowcount=1):
        self.sql_log = []
        self.rowcount = rowcount
        self._rows_for = rows_for or (lambda sql: [])
        self.closes = 0

    def rows_for(self, sql):
        return self._rows_for(sql)

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        pass

    def close(self):
        self.closes += 1


def _make_assignment_app():
    app = Flask(__name__)
    app.secret_key = 'test'
    raa.register_assignment_api(app)
    return app.test_client()


def _login(client, role, name):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = name
        s['full_name'] = name
        s['csrf_token'] = 'tok'


# ---------------------------------------------------------------------------
# /api/assignments/confirm
# ---------------------------------------------------------------------------
class TestAssignmentConfirmAuth:
    def test_tanpa_sesi_ditolak_401(self, monkeypatch):
        c = _make_assignment_app()
        r = c.post('/api/assignments/confirm',
                   data=json.dumps({'driver_name': 'BUDI', 'nopol': 'L 1 ABC'}),
                   content_type='application/json')
        assert r.status_code == 401

    def test_nopol_wajib_ada(self, monkeypatch):
        c = _make_assignment_app()
        _login(c, 'driver', 'BUDI')
        r = c.post('/api/assignments/confirm',
                   data=json.dumps({'nopol': ''}),
                   content_type='application/json')
        assert r.status_code == 400

    def test_identitas_dari_sesi_bukan_body(self, monkeypatch):
        """Body bisa menyebut driver lain — sesi tetap jadi identitas."""
        conn = FakeConn(rowcount=1)
        monkeypatch.setattr(raa, 'get_db_connection', lambda *a, **k: conn)
        c = _make_assignment_app()
        _login(c, 'driver', 'BUDI')
        r = c.post('/api/assignments/confirm',
                   data=json.dumps({'driver_name': 'PENYUSUP', 'nopol': 'L 1 ABC'}),
                   content_type='application/json')
        assert r.status_code == 200
        sql, params = conn.sql_log[0]
        assert params[0] == 'BUDI', 'identitas harus dari sesi'
        assert 'confirmed_by_driver' in sql

    def test_back_office_boleh_mewakili_driver(self, monkeypatch):
        conn = FakeConn(rowcount=1)
        monkeypatch.setattr(raa, 'get_db_connection', lambda *a, **k: conn)
        c = _make_assignment_app()
        _login(c, 'ga', 'ga_sby')
        r = c.post('/api/assignments/confirm',
                   data=json.dumps({'driver_name': 'BUDI', 'nopol': 'L 1 ABC'}),
                   content_type='application/json')
        assert r.status_code == 200
        assert conn.sql_log[0][1][0] == 'BUDI'


# ---------------------------------------------------------------------------
# /api/verify-pin & /api/vehicle_bbm — DIHAPUS v2.73.0 (cleanup fitur terbenam)
# ---------------------------------------------------------------------------
class TestLegacyEndpointsRemoved:
    def test_verify_pin_dihapus_404(self):
        """Endpoint legacy v1.0 tinggal 404; jalurnya kini /api/step-up."""
        app = Flask(__name__)
        app.secret_key = 'test'
        ram.register_master_api(app)
        c = app.test_client()
        r = c.post('/api/verify-pin',
                   data=json.dumps({'username': 'admin', 'pin': '123456'}),
                   content_type='application/json')
        assert r.status_code == 404

    def test_vehicle_bbm_alias_dihapus_404(self):
        """Duplikat alias tanpa pemanggil tinggal 404."""
        app = Flask(__name__)
        app.secret_key = 'test'
        ram.register_master_api(app)
        c = app.test_client()
        assert c.get('/api/vehicle_bbm/AVANZA').status_code == 404

    def test_step_up_masih_terdaftar(self):
        """Pengganti verify-pin tetap hidup & tetap butuh sesi."""
        app = Flask(__name__)
        app.secret_key = 'test'
        from modules.stepup import register_stepup_routes
        register_stepup_routes(app)
        c = app.test_client()
        r = c.post('/api/step-up',
                   data=json.dumps({'pin': '123456'}),
                   content_type='application/json')
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# /admin/backup
# ---------------------------------------------------------------------------
def _make_report_app():
    app = Flask(__name__)
    app.secret_key = 'test'
    rr.register_report_routes(app)
    return app.test_client()


class TestBackupEndpoint:
    def test_mysqldump_hilang_503(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError('mysqldump')
        monkeypatch.setattr(rr.subprocess, 'run', boom)
        c = _make_report_app()
        with c.session_transaction() as s:
            s['user_role'] = 'admin'; s['user_name'] = 'admin'
        r = c.get('/admin/backup')
        assert r.status_code == 503
        assert 'mysqldump' in r.get_data(as_text=True)

    def test_mysqldump_gagal_503(self, monkeypatch):
        res = subprocess.CompletedProcess(args=['mysqldump'], returncode=2,
                                          stdout='', stderr='Access denied')
        monkeypatch.setattr(rr.subprocess, 'run', lambda *a, **k: res)
        c = _make_report_app()
        with c.session_transaction() as s:
            s['user_role'] = 'admin'; s['user_name'] = 'admin'
        r = c.get('/admin/backup')
        assert r.status_code == 503

    def test_sukses_kirim_dump(self, monkeypatch):
        res = subprocess.CompletedProcess(args=['mysqldump'], returncode=0,
                                          stdout='-- dump isi', stderr='')
        monkeypatch.setattr(rr.subprocess, 'run', lambda *a, **k: res)
        c = _make_report_app()
        with c.session_transaction() as s:
            s['user_role'] = 'admin'; s['user_name'] = 'admin'
        r = c.get('/admin/backup')
        assert r.status_code == 200
        assert r.headers['Content-Type'] == 'application/sql'
        assert '-- dump isi' in r.get_data(as_text=True)

    def test_tanpa_role_admin_ditolak(self):
        c = _make_report_app()
        with c.session_transaction() as s:
            s['user_role'] = 'driver'; s['user_name'] = 'budi'
        # role_required: klien HTML diarahkan (302), klien JSON/AJAX ditolak 403
        r = c.get('/admin/backup')
        assert r.status_code in (302, 403)
        assert r.headers.get('Content-Type', '').startswith('application/sql') is False
