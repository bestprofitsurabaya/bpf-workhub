#!/usr/bin/env python3
"""
BPF WorkHub - Main Application
PT. Bestprofit Surabaya
"""
import warnings, os
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
try:
    import eventlet
    eventlet.monkey_patch()
    socketio_async_mode = 'eventlet'
except Exception:
    eventlet = None
    socketio_async_mode = 'threading'

from flask_socketio import SocketIO
from flask import Flask, request, session, jsonify, redirect, url_for, flash
from datetime import timedelta
import os
import warnings
import secrets
import json
import time
warnings.filterwarnings('ignore')

# Init Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.environ.get('SECRET_KEY', 'bpf_bbm_secret_key_default_2026')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs('uploads', exist_ok=True)

# Session cookie hardening (ISO/IEC 27001 A.8.5 manajemen sesi)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
# Secure cookie: aktif saat HTTPS (produksi duckdns). Matikan hanya untuk dev http lokal.
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() in ('1', 'true', 'yes')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=int(os.environ.get('SESSION_HOURS', '12')))

# Init SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=socketio_async_mode, logger=False, engineio_logger=False)

# Attach realtime bus (driver notification rooms)
from modules.realtime import init_socketio
init_socketio(socketio)

# Init DB Pool
from modules.config import init_pool
init_pool()

# Ensure notifications table exists (safe on every startup)
from modules.notifications import ensure_notifications_table
ensure_notifications_table()

# Ensure appointment system tables/columns (safe on every startup).
# Retry bila koneksi pertama gagal (DB masih warming up / pool belum siap).
from modules.appointments_schema import ensure_appointments_schema
import time as _time
for _attempt in range(5):
    _ok = ensure_appointments_schema()
    if _ok:
        break
    _time.sleep(3)

# Sistem Overtime (v2.22): tabel overtime_driver & overtime_ob_security
from modules.overtime_schema import ensure_overtime_schema
for _attempt in range(5):
    _ok = ensure_overtime_schema()
    if _ok:
        break
    _time.sleep(3)

# Multi-cabang (v2.19.2): tabel branches + kolom users.branch_code + cabang utama,
# lalu sinkronkan skema untuk setiap cabang aktif yang punya database sendiri.
from modules import branch_manager as bm
bm.ensure_branches_table()
bm.ensure_users_branch_column()
bm.seed_main_branch()
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _ok, _msg = bm.ensure_branch_database(_b['code'])
            print(f'[branches] {_b["code"]}: {_msg}')
except Exception as _be:
    print(f'[branches] startup sync error: {_be}')

# Register all route modules
from modules.routes_driver import register_driver_routes
from modules.routes_api_master import register_master_api
from modules.routes_api_transactions import register_transaction_api
from modules.routes_api_assignments import register_assignment_api
from modules.routes_admin import register_admin_routes
from modules.routes_reports import register_report_routes
from modules.routes_cash import register_cash_routes
from modules.routes_settings import register_settings_routes
from modules.routes_notifications import register_notification_routes
from modules.routes_auth import register_auth_routes
from modules.routes_appointments import register_appointment_routes
from modules.routes_water import register_water_routes
from modules.routes_applicants import register_applicant_routes
from modules.routes_assets import register_asset_routes
from modules.routes_branches import register_branch_routes
from modules.routes_overtime import register_overtime_routes
from modules.routes_spa import register_spa_routes
from modules.routes_news_scraper import register_news_scraper_routes
from modules.security import register_health_routes

register_driver_routes(app, socketio)
register_auth_routes(app)
register_master_api(app)
register_transaction_api(app)
register_assignment_api(app)
register_cash_routes(app)
register_admin_routes(app)
register_report_routes(app)
register_settings_routes(app)
register_notification_routes(app)
register_appointment_routes(app)
register_water_routes(app)
register_applicant_routes(app)
register_asset_routes(app)
register_branch_routes(app)
register_overtime_routes(app)
register_spa_routes(app)
register_news_scraper_routes(app)
register_health_routes(app)

# ================================================================
# CSRF PROTECTION (berlaku untuk sesi admin yang login)
# Endpoint PWA driver (tanpa session) & socket.io dikecualikan.
# ================================================================
# v2.5: endpoint driver (submit-trip, cash request/submit-lpj/delete, driver-complete)
# kini WAJIB sesi login PIN — SPA driver mengirim X-CSRF-Token (api()/fetch), jadi
# tidak perlu lagi dikecualikan dari proteksi CSRF (defense-in-depth).
CSRF_EXEMPT_PREFIXES = (
    '/socket.io', '/api/assignments/confirm', '/api/get-feedback',
    '/api/vehicle-allowed-bbm', '/uploads/',
)

@app.context_processor
def inject_csrf_token():
    """Sediakan fungsi csrf_token() untuk dipakai di template (meta tag & hidden input)."""
    def _csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(16)
        return session['csrf_token']
    return {'csrf_token': _csrf_token}

@app.before_request
def csrf_protect():
    if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
        return None
    # Hanya berlaku untuk sesi admin yang login; halaman login ikut dilindungi
    if not session.get('user_role') and request.path != '/login':
        return None
    for p in CSRF_EXEMPT_PREFIXES:
        if request.path.startswith(p):
            return None
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token or not session.get('csrf_token') or token != session.get('csrf_token'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'msg': 'CSRF token tidak valid. Muat ulang halaman dan coba lagi.'}), 400
        flash('Sesi tidak valid. Silakan muat ulang halaman dan coba lagi.', 'error')
        ref = request.referrer or ''
        return redirect(ref if ref.startswith('/') else url_for('admin_dashboard'))
    return None

# Middleware
@app.after_request
def add_no_cache_header(response):
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.after_request
def add_security_headers(response):
    """Security headers lengkap (ISO/IEC 27001 A.8.2 · A.8.7 · A.8.8).

    - X-Content-Type-Options: nosniff        — cegah MIME sniffing
    - X-Frame-Options: DENY                  — cegah clickjacking
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy                     — batasi fitur browser
    - Content-Security-Policy                — batasi sumber skrip/style (anti-XSS)
      (santai untuk SPA Vue + Socket.IO + map; inline script/styles dibatasi
      ketat, nonce sulit karena SPA statis — pendekatan ini tetap memblokir
      injeksi skrip dari sumber asing)
    """
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy',
                                'camera=(self), geolocation=(self), microphone=(), '
                                'payment=(), usb=(), display-capture=()')
    if response.headers.get('Content-Type', '').startswith('text/html'):
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://a.tile.openstreetmap.org; "
            "connect-src 'self' ws: wss: https://nominatim.openstreetmap.org https://*.tile.openstreetmap.org; "
            "frame-ancestors 'none'")
    return response


@app.after_request
def log_access_json(response):
    """Access log ringkas berformat JSON (observabilitas, v2.21).

    Dicetak via app.logger (INFO) — satu baris per request dengan field
    terstruktur untuk diproses (grep/jq) atau dipipakan ke aggregator.
    Endpoint statis & socket.io dilewati agar tidak membanjiri log.
    """
    p = request.path
    if p.startswith(('/static/', '/uploads/', '/socket.io', '/app/assets/', '/app/dark-init.js')):
        return response
    entries = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'method': request.method,
        'path': p,
        'status': response.status_code,
        'ip': request.remote_addr or '-',
        'user': session.get('user_name') if session else '-',
        'role': session.get('user_role') if session else '-',
        'ms': int((time.perf_counter() - request.environ.get('_req_start', time.perf_counter())) * 1000),
    }
    app.logger.info(json.dumps(entries, ensure_ascii=False))
    return response


@app.before_request
def mark_request_start():
    request.environ['_req_start'] = time.perf_counter()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
