"""Header CORS untuk bridge APK (v2.126.0).

Aplikasi Cordova berjalan di origin `https://localhost` (WebView Android),
sedangkan API dilayani `https://nasbpfsby.duckdns.org:8444`. Tanpa
`Access-Control-Allow-Origin`, `fetch()` dan `EventSource` di WebView diblokir
meskipun server membalas 200 — inilah penyebab layar menampilkan OFFLINE.

Isi bridge memang publik dan read-only, jadi `*` aman dipakai (tanpa cookie).
"""
from flask import request

BRIDGE_PATHS = ('/api/state', '/api/month', '/api/stream')
BRIDGE_PREFIXES = ('/api/app/',)


def is_bridge_path(path):
    p = path or ''
    return p in BRIDGE_PATHS or p.startswith(BRIDGE_PREFIXES)


def _apply(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Range'
    response.headers['Access-Control-Expose-Headers'] = (
        'Content-Length, Content-Range, X-Checksum-SHA256')
    response.headers['Access-Control-Max-Age'] = '86400'
    return response


def install_bridge_cors(app):
    """Pasang preflight + header CORS untuk path bridge pada `app`."""

    @app.before_request
    def _bridge_preflight():
        if request.method == 'OPTIONS' and is_bridge_path(request.path):
            return _apply(app.make_response(('', 204)))

    @app.after_request
    def _bridge_cors(response):
        if is_bridge_path(request.path):
            _apply(response)
        return response
