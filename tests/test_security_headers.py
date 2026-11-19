"""Tests — Security headers, rate limit, health, access log (v2.21)."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask


@pytest.fixture
def app():
    """Aplikasi minimal yang memakai middleware keamanan app.py."""
    import app as main_app
    # v2.128.4 — health menurunkan status bila ada kegagalan kritis yang
    # ditelan (modules.integrity) dalam 30 menit terakhir. Tes lain dalam satu
    # proses pytest bisa meninggalkan catatan tersebut, membuat tes health
    # gagal saat suite penuh (lulus saat dijalankan sendiri). Bersihkan dulu.
    from modules.integrity import reset as reset_integrity
    reset_integrity()
    yield main_app.app


@pytest.fixture
def client(app):
    return app.test_client()


# ============================================================
# SECURITY HEADERS
# ============================================================
def test_security_headers_present(client):
    r = client.get('/login')
    assert r.status_code in (200, 302)
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'DENY'
    assert r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'Permissions-Policy' in r.headers


def test_csp_on_html(client):
    r = client.get('/login')
    csp = r.headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp
    assert 'frame-ancestors' in csp
    # script inline/eval TIDAK diizinkan (ketat) — anti-XSS
    assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
    assert "'unsafe-eval'" not in csp.split('script-src')[1].split(';')[0]


# ============================================================
# RATE LIMIT
# ============================================================
def test_rate_limit_blocks_after_threshold():
    from modules.security import rate_limit, clear_rate_limits
    clear_rate_limits()

    app = Flask(__name__)
    app.secret_key = 'test'

    @app.route('/x', methods=['POST'])
    @rate_limit(limit=3, window=60, scope='test-scope')
    def x():
        return 'ok'

    c = app.test_client()
    for _ in range(3):
        assert c.post('/x').status_code == 200
    assert c.post('/x').status_code == 429


def test_rate_limit_allows_after_window():
    from modules.security import rate_limit, clear_rate_limits
    clear_rate_limits()

    app = Flask(__name__)
    app.secret_key = 'test'

    @app.route('/x', methods=['POST'])
    @rate_limit(limit=2, window=1, scope='test-window')
    def x():
        return 'ok'

    c = app.test_client()
    assert c.post('/x').status_code == 200
    assert c.post('/x').status_code == 200
    assert c.post('/x').status_code == 429


# ============================================================
# HEALTH ENDPOINT
# ============================================================
def test_health_endpoint_ok(client, monkeypatch):
    # Stub koneksi DB agar hermetis
    class FakeConn:
        def cursor(self):
            return self
        def execute(self, *a, **k):
            return None
        def fetchone(self):
            return (1,)
        def close(self):
            pass

    import modules.config as cfg
    monkeypatch.setattr(cfg, 'get_master_connection', lambda: FakeConn())
    monkeypatch.setattr(cfg, 'get_db_pool_info', lambda: None)
    import modules.security as sec
    monkeypatch.setattr(sec, '_redis_ping', lambda: True)

    r = client.get('/api/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] == 'ok'
    assert data['checks']['database'] == 'ok'


def test_health_degraded_when_db_down(client, monkeypatch):
    import modules.config as cfg
    monkeypatch.setattr(cfg, 'get_master_connection', lambda: None)
    monkeypatch.setattr(cfg, 'get_db_pool_info', lambda: None)
    import modules.security as sec
    monkeypatch.setattr(sec, '_redis_ping', lambda: False)

    r = client.get('/api/health')
    data = r.get_json()
    assert data['status'] == 'degraded'
    assert data['checks']['database'] == 'error'


# ============================================================
# ACCESS LOG JSON
# ============================================================
def test_access_log_json(client, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        client.get('/api/health')
    # Cari baris log JSON berisi method & path
    found = any('"method": "GET"' in rec.message and '"path": "/api/health"' in rec.message
                for rec in caplog.records)
    assert found, 'access log JSON tidak ditemukan untuk /api/health'
