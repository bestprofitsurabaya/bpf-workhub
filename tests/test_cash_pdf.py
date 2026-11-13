"""Regression v2.106.0 — dokumen PDF per kasbon.

Finance sebelumnya tidak punya dokumen per transaksi untuk kasbon: modal
detail hanya menampilkan field, tanpa tombol PDF dan tanpa generator di
backend. Test ini mengunci route baru (`GET /api/cash/<id>/pdf`) agar
selalu mengembalikan PDF untuk role yang berwenang.
"""
import pytest
from flask import Flask

from modules.routes_cash import register_cash_routes

CASH = {
    'id': 13,
    'display_id': 'KSB-013',
    'driver_name': 'BUDI',
    'nopol': 'L 1234 AB',
    'vehicle_type': 'MOTOR',
    'bbm_type': 'PERTALITE',
    'base_amount': 500000,
    'unique_cents': 300,
    'total_amount': 500300,
    'daily_code': 700,
    'status': 'COMPLETED',
    'ga_approved_by': 'GA SBY',
    'ga_approved_at': '2026-11-01 09:00:00',
    'finance_approved_by': 'FINANCE SBY',
    'finance_approved_at': '2026-11-01 10:00:00',
    'handover_by': 'GA SBY',
    'handover_at': '2026-11-01 11:00:00',
    'notes': 'Kasbon harian driver.',
    'created_at': '2026-11-01 08:00:00',
    'lpj_transaction_id': None,
}


class FakeCursor:
    row = CASH

    def __init__(self):
        self._row = None

    def execute(self, sql, params=None):
        self._row = self.row if 'fuel_cash_requests' in sql else None

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def cursor(self, dictionary=False):
        return FakeCursor()

    def close(self):
        pass


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'test'
    register_cash_routes(app)
    return app.test_client()


def _patch_dependencies(monkeypatch):
    import modules.routes_cash as rc
    import modules.pdf_generator as pg
    import modules.doc_integrity as di
    from modules.company_identity import IDENTITY_DEFAULTS

    monkeypatch.setattr(rc, 'get_db_connection', lambda: FakeConn())
    monkeypatch.setattr(rc, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(pg, 'get_company_identity', lambda *a, **k: dict(IDENTITY_DEFAULTS))
    monkeypatch.setattr(di, 'register_pdf', lambda *a, **k: None)


def test_finance_mendapat_pdf_kasbon(client, monkeypatch):
    _patch_dependencies(monkeypatch)
    with client.session_transaction() as s:
        s['user_role'] = 'finance'
        s['user_name'] = 'finance_sby'
        s['branch_code'] = 'SBY'

    r = client.get('/api/cash/13/pdf')

    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    assert r.data.startswith(b'%PDF')
    assert 'Kasbon_KSB-013.pdf' in r.headers['Content-Disposition']


def test_kasbon_tidak_ditemukan(client, monkeypatch):
    _patch_dependencies(monkeypatch)
    monkeypatch.setattr(FakeCursor, 'row', None)
    with client.session_transaction() as s:
        s['user_role'] = 'finance'
        s['user_name'] = 'finance_sby'

    r = client.get('/api/cash/999/pdf')

    assert r.status_code == 404


def test_tanpa_sesi_ditolak(client, monkeypatch):
    _patch_dependencies(monkeypatch)
    r = client.get('/api/cash/13/pdf')
    assert r.status_code == 401


def test_role_driver_ditolak(client, monkeypatch):
    _patch_dependencies(monkeypatch)
    with client.session_transaction() as s:
        s['user_role'] = 'driver'
        s['driver_name'] = 'BUDI'

    r = client.get('/api/cash/13/pdf')
    assert r.status_code == 403
