"""v2.132.0 — /api/driver/me memakai assignment aktif sebagai sumber kendaraan.

Insiden: cache `drivers.nopol` bisa basi (contoh DRIVERSBY_ABIEM masih
`L 1415 CBI` padahal assignment aktifnya `B 1126 DFC`). Header driver dan panel
Profil harus menampilkan kendaraan yang sama, jadi endpoint ini membaca
`vehicle_assignments.is_current = 1` lebih dulu.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_driver as rd  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary

    def execute(self, sql, params=()):
        self.conn.sql_log.append((sql, params))

    def fetchone(self):
        return self.conn.one

    def close(self):
        pass


class FakeConn:
    def __init__(self, one=None):
        self.one = one
        self.sql_log = []
        self.closes = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def close(self):
        self.closes += 1


def make_client(monkeypatch):
    """Daftarkan route driver tanpa menyentuh DB saat registrasi."""
    monkeypatch.setattr(rd, 'ensure_anti_fraud_schema', lambda *a, **k: True)
    monkeypatch.setattr(rd, 'ensure_vehicle_bbm_schema', lambda *a, **k: None)
    monkeypatch.setattr(rd, 'ensure_fuel_prices_schema', lambda *a, **k: None)
    monkeypatch.setattr(rd, 'ensure_voucher_schema', lambda *a, **k: None)
    import modules.branch_manager as bm
    monkeypatch.setattr(bm, 'list_branches', lambda *a, **k: [])

    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['UPLOAD_FOLDER'] = '/tmp'
    rd.register_driver_routes(app, object())
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_role'] = 'driver'
        sess['user_name'] = 'driversby_abiem'
        sess['branch_code'] = 'SBY'
    return client


class TestDriverMeVehicleSource:
    def test_query_mendahulukan_assignment_aktif(self):
        import inspect
        src = inspect.getsource(rd.register_driver_routes)
        assert 'COALESCE(a.nopol, d.nopol) AS nopol' in src
        assert 'LEFT JOIN vehicle_assignments a' in src
        assert 'a.is_current = 1' in src

    def test_profil_mengembalikan_kendaraan_dari_assignment(self, monkeypatch):
        conn = FakeConn(one={
            'name': 'DRIVERSBY_ABIEM',
            'display_name': 'Abiem',
            'nopol': 'B 1126 DFC',
            'vehicle_type': 'INNOVA',
            'bbm_type': 'PERTALITE',
            'is_active': 1,
            'initial_odo_km': 0,
            'last_odo_km': 120000,
        })
        monkeypatch.setattr(rd, 'get_db_connection', lambda *a, **k: conn)
        monkeypatch.setattr(rd, 'session_driver_name', lambda: 'DRIVERSBY_ABIEM')
        client = make_client(monkeypatch)

        r = client.get('/api/driver/me')

        assert r.status_code == 200
        body = r.get_json()
        assert body['nopol'] == 'B 1126 DFC'
        assert body['vehicle_type'] == 'INNOVA'
        sql, params = conn.sql_log[0]
        assert 'vehicle_assignments' in sql
        assert params == ('DRIVERSBY_ABIEM',)
        assert conn.closes == 1

    def test_driver_nonaktif_tetap_404(self, monkeypatch):
        conn = FakeConn(one={
            'name': 'DRIVERSBY_ABIEM', 'display_name': 'Abiem',
            'nopol': 'B 1126 DFC', 'vehicle_type': 'INNOVA',
            'bbm_type': 'PERTALITE', 'is_active': 0,
            'initial_odo_km': 0, 'last_odo_km': 0,
        })
        monkeypatch.setattr(rd, 'get_db_connection', lambda *a, **k: conn)
        monkeypatch.setattr(rd, 'session_driver_name', lambda: 'DRIVERSBY_ABIEM')
        client = make_client(monkeypatch)

        r = client.get('/api/driver/me')

        assert r.status_code == 404
