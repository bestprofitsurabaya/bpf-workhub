"""Audit UI finance v2.75.0 — lock guard baru di modul kasbon/BBM.

Temuan audit (28 Okt 2026, docs/internal/AUDIT_UI_FINANCE_20261028.md):
GET /api/cash/daily-code dulu bisa dipanggil TANPA sesi sama sekali
(konfigurasi mode baca + tulis get-or-create kode harian dari pihak anonim).
Kini wajib sesi (driver maupun back-office) — semuanya login PIN, aman.
"""
import pytest
from flask import Flask

from modules.routes_cash import register_cash_routes


@pytest.fixture
def cash_app():
    app = Flask(__name__)
    app.secret_key = 'test'
    register_cash_routes(app)
    return app


@pytest.fixture
def client(cash_app):
    return cash_app.test_client()


def test_daily_code_tanpa_sesi_ditolak(client):
    r = client.get('/api/cash/daily-code')
    assert r.status_code == 401
    r = client.post('/api/cash/daily-code', json={'code': 123})
    assert r.status_code == 401


def test_daily_code_finance_melampaui_guard(client, monkeypatch):
    """Sesi finance melewati guard; tanpa DB → 500 rapi, bukan 401."""
    import modules.routes_cash as rc
    monkeypatch.setattr(rc, 'get_db_connection', lambda: None)
    with client.session_transaction() as s:
        s['user_role'] = 'finance'
        s['csrf_token'] = 'x'
    r = client.get('/api/cash/daily-code')
    assert r.status_code == 500  # guard lulus (tidak 401), DB gagal terkontrol


def test_daily_code_driver_melampaui_guard(client, monkeypatch):
    """Sesi driver juga lulus guard (pemakai kode harian utamanya)."""
    import modules.routes_cash as rc
    import modules.helpers as hp

    def fake_scope(q=''):
        return 'WICAK'  # sesi driver dengan identitas terverifikasi

    monkeypatch.setattr(rc, 'session_driver_name', lambda: 'WICAK')
    monkeypatch.setattr(hp, 'session_driver_name', lambda: 'WICAK')
    monkeypatch.setattr(rc, 'get_db_connection', lambda: None)
    with client.session_transaction() as s:
        s['user_role'] = 'driver'
        s['driver_name'] = 'WICAK'
        s['csrf_token'] = 'x'
    r = client.get('/api/cash/daily-code')
    assert r.status_code == 500  # bukan 401 — guard lulus
