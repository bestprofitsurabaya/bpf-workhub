"""
Unit Tests — client_ip() anti-spoofing (ISO/IEC 27001 A.12.6 — kontrol teknis).

Menjamin rate limit (login & verify-pin) tidak bisa dibypass dengan memalsukan
header X-Forwarded-For:

- Via Cloudflare Tunnel: CF-Connecting-IP (di-set & ditimpa Cloudflare) dipakai.
- Via nginx container: X-Real-IP dipercaya HANYA bila peer TCP loopback/privat.
- X-Forwarded-For DIABAIKAN sepenuhnya (nilai pertamanya dikontrol klien).
- Akses langsung origin: request.remote_addr (peer TCP nyata) sebagai fallback.

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_client_ip.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask
from modules.helpers import client_ip


def _ctx(headers=None):
    app = Flask(__name__)
    ctx = app.test_request_context(
        '/',
        headers=headers or {},
        environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
    )
    return app, ctx


def test_cf_connecting_ip_dipakai_menang_atas_xff_palsu():
    """CF-Connecting-IP (asli dari Cloudflare) menang walau XFF dipalsukan."""
    app, ctx = _ctx({'CF-Connecting-IP': '203.0.113.9', 'X-Forwarded-For': '1.2.3.4'})
    with ctx:
        assert client_ip() == '203.0.113.9'


def test_xff_diabaikan_tanpa_cf_header():
    """Tanpa CF-Connecting-IP, XFF palsu tidak boleh dipakai — fallback remote_addr."""
    app, ctx = _ctx({'X-Forwarded-For': '1.2.3.4, 10.0.0.1'})
    with ctx:
        ip = client_ip()
        assert ip != '1.2.3.4'
        assert ip == '127.0.0.1'  # remote_addr test client


def test_fallback_remote_addr_ketika_tanpa_header_apapun():
    app, ctx = _ctx({})
    with ctx:
        assert client_ip() == '127.0.0.1'


def test_cf_palsu_diabaikan_saat_origin_diakses_langsung_dari_ip_publik():
    """CF-Connecting-IP palsu TIDAK dipercaya bila remote_addr publik (origin diekspos)."""
    app = Flask(__name__)
    ctx = app.test_request_context(
        '/',
        headers={'CF-Connecting-IP': '203.0.113.9'},
        environ_overrides={'REMOTE_ADDR': '8.8.8.8'},
    )
    with ctx:
        assert client_ip() == '8.8.8.8'


def test_x_real_ip_dipakai_dari_proxy_privat():
    """nginx di container lain (peer 172.x) menimpa X-Real-IP -> dipercaya."""
    app = Flask(__name__)
    ctx = app.test_request_context(
        '/',
        headers={'X-Real-IP': '203.0.113.50'},
        environ_overrides={'REMOTE_ADDR': '172.18.0.5'},
    )
    with ctx:
        assert client_ip() == '203.0.113.50'


def test_x_real_ip_palsu_diabaikan_dari_ip_publik():
    """X-Real-IP palsu tidak dipercaya bila peer TCP publik (origin diekspos)."""
    app = Flask(__name__)
    ctx = app.test_request_context(
        '/',
        headers={'X-Real-IP': '203.0.113.50'},
        environ_overrides={'REMOTE_ADDR': '8.8.8.8'},
    )
    with ctx:
        assert client_ip() == '8.8.8.8'


def test_x_real_ip_sampah_diabaikan():
    app = Flask(__name__)
    ctx = app.test_request_context(
        '/',
        headers={'X-Real-IP': 'not-an-ip'},
        environ_overrides={'REMOTE_ADDR': '172.18.0.5'},
    )
    with ctx:
        assert client_ip() == '172.18.0.5'


def test_selalu_mengembalikan_string_non_kosong():
    app, ctx = _ctx({'CF-Connecting-IP': ''})
    with ctx:
        assert client_ip()
