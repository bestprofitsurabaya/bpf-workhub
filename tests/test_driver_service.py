"""Unit Tests — Catatan Service Driver → GA (v2.131.0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

from modules.routes_driver_service import register_driver_service_routes


class FakeCursor:
    def __init__(self, api):
        self.api = api
        self.rowcount = 0
        self.lastrowid = 11
        self.sql = ''

    def execute(self, sql, params=None):
        self.sql = str(sql).lower()
        self.params = params or ()
        if 'insert into driver_service_reports' in self.sql:
            self.api.inserted = self.params
            self.rowcount = 1
        elif 'update driver_service_reports' in self.sql:
            self.rowcount = 1 if self.params and self.params[-1] == 11 else 0
        elif 'from drivers' in self.sql:
            pass

    def fetchone(self):
        if 'from drivers' in self.sql:
            return {'display_name': 'Rivan', 'nopol': 'B 1126 DFC', 'vehicle_type': 'AVANZA'}
        if 'from driver_service_reports' in self.sql:
            return dict(self.api.inserted or {})
        return None

    def fetchall(self):
        return [dict(self.api.inserted or {})] if self.api.inserted else []

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.inserted = None

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr('modules.routes_driver_service.get_db_connection', lambda: conn)
    monkeypatch.setattr('modules.routes_driver_service.generate_display_id',
                        lambda prefix, conn=None: 'SRV-SBY-20261123-0001')
    monkeypatch.setattr('modules.routes_driver_service.log_activity_async',
                        lambda *a, **k: None)
    app = Flask(__name__)
    app.secret_key = 'test'
    register_driver_service_routes(app)
    app.config['TESTING'] = True
    return app.test_client(), conn


def login(c, role):
    with c.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'DRIVERSBY_RIVAN' if role == 'driver' else 'GA_SBY'
        s['branch_code'] = 'SBY'


def test_driver_submit_membutuhkan_keluhan(client):
    c, _ = client
    login(c, 'driver')
    rv = c.post('/api/driver/service', json={})
    assert rv.status_code == 400


def test_driver_submit_tersimpan(client):
    c, conn = client
    login(c, 'driver')
    rv = c.post('/api/driver/service', json={
        'keluhan': 'Rem depan berbunyi keras', 'km_kendaraan': 131900})
    assert rv.status_code == 200
    d = rv.get_json()
    assert d['status'] == 'success'
    assert d['display_id'] == 'SRV-SBY-20261123-0001'
    assert conn.inserted[1] == 'DRIVERSBY_RIVAN'
    assert conn.inserted[3] == 'B 1126 DFC'


def test_ga_bisa_melihat_dan_memproses(client):
    c, conn = client
    login(c, 'ga')
    rv = c.get('/api/ga/service-reports')
    assert rv.status_code == 200
    assert 'data' in rv.get_json()
    rv = c.post('/api/ga/service-reports/11/review', json={'status': 'REVIEWED'})
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'


def test_driver_tidak_bisa_buka_endpoint_ga(client):
    c, _ = client
    login(c, 'driver')
    assert c.get('/api/ga/service-reports').status_code in (301, 302, 401, 403)


def test_pdf_resmi_terbuat():
    from modules.driver_service_pdf import DriverServicePDF
    pdf = DriverServicePDF()
    pdf.generate({
        'display_id': 'SRV-SBY-20261123-0001', 'driver_display_name': 'Rivan',
        'driver_name': 'DRIVERSBY_RIVAN', 'nopol': 'B 1126 DFC',
        'vehicle_type': 'AVANZA', 'km_kendaraan': 131900,
        'keluhan': 'Rem depan berbunyi keras', 'created_at': '2026-11-23 08:00:00',
        'ga_note': '',
    })
    import io
    buf = io.BytesIO()
    pdf.output(buf)
    assert buf.getvalue()[:4] == b'%PDF'
