#!/usr/bin/env python3
"""
BPF WorkHub - Main Application
PT. Bestprofit Futures (Kantor Pusat: Jakarta)
"""
import warnings, os
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
# v2.38.0: migrasi worker eventlet → gevent (eventlet deprecated; gunicorn 26
# menghapus worker bawaannya — insiden 8 Sep 2026).
# v2.39.2: JANGAN mem-patch gevent/eventlet di modul ini. Patching di dalam
# modul aplikasi (jalan saat `import app`, termasuk saat pytest meng-import)
# merusak lock importlib yang sudah di-acquire interpreter →
# "RuntimeError: cannot release un-acquired lock" (CI merah, run 34425989650). Pemetaan patch yang benar
# ditentukan WORKER gunicorn via --worker-class (lihat Dockerfile):
#   gunicorn --worker-class gevent → gevent.patch_all() otomatis sebelum app load
#   gunicorn (worker sinkron)     → tidak ada patch, threading murni
#   python app.py (dev)           → threading murni
# async_mode SocketIO mengikuti: 'gevent' saat worker gevent, 'threading' selain itu.
# ⚠️ Jalankan server HANYA via CMD Dockerfile (worker-class tercatat di sana);
# menjalankan `python app.py` dgn asumsi mode gevent tidak didukung.
# v2.39.3: deteksi via ARGV (sys.argv), bukan env — GUNICORN_CMD_ARGS &
# SERVER_SOFTWARE TIDAK pernah ada di os.environ proses produksi (diverifikasi
# di PID 1 bbm_web, 10 Sep 2026): SERVER_SOFTWARE itu kunci WSGI per-request,
# GUNICORN_CMD_ARGS hanya env INPUT gunicorn. Worker gunicorn mewarisi argv
# master lewat fork, jadi sys.argv memuat persis CMD Dockerfile
# (gunicorn --worker-class gevent ...) — sinyal yang pasti benar.
import sys as _sys_w
_argv_w = ' '.join(_sys_w.argv)
socketio_async_mode = 'gevent' if (
    _sys_w.argv[0].endswith('gunicorn')
    and ('--worker-class=gevent' in _argv_w or '--worker-class gevent' in _argv_w
         or '-k=gevent' in _argv_w or '-k gevent' in _argv_w)
) else 'threading'

from flask_socketio import SocketIO
from flask import Flask, request, session, jsonify, redirect, url_for, flash
from datetime import timedelta
import os
import warnings
import secrets
import json
import time
import hmac
warnings.filterwarnings('ignore')

# Init Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# v2.29: pastikan access log JSON (after_request, INFO) benar-benar tercetak
# ke stdout/docker logs. Default Flask: app.logger level WARNING di production
# → info access log diam-diam dibuang. Handler eksplisit + level INFO + no
# propagate (log akses tidak dobel via root logger gunicorn).
import logging as _logging
if not app.logger.handlers:
    _h = _logging.StreamHandler()
    _h.setFormatter(_logging.Formatter('%(message)s'))
    app.logger.addHandler(_h)
app.logger.setLevel(_logging.INFO)
app.logger.propagate = False
_secret = os.environ.get('SECRET_KEY')
if not _secret:
    _env = os.environ.get('FLASK_ENV', 'production')
    if _env != 'development':
        raise RuntimeError(
            'SECRET_KEY environment variable is required in production. '
            'Set it before starting the app.')
    _secret = 'dev-only-insecure-key-not-for-production'
    print('[SECURITY] WARNING: Using fallback SECRET_KEY — set SECRET_KEY env var for production!')
app.secret_key = _secret
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs('uploads', exist_ok=True)

# Session cookie hardening (ISO/IEC 27001 A.8.5 manajemen sesi)
app.config['SESSION_COOKIE_HTTPONLY'] = True
# Nama cookie unik — cookie browser per-domain dan MENGABAIKAN port. Nextcloud
# (atau layanan lain) di domain yang sama memakai nama default 'session' juga;
# tanpa nama unik kedua app saling menimpa cookie -> sesi acak ter-logout.
app.config['SESSION_COOKIE_NAME'] = os.environ.get('SESSION_COOKIE_NAME', 'bpf_session')
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
# Secure cookie: aktif saat HTTPS (produksi duckdns). Matikan hanya untuk dev http lokal.
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() in ('1', 'true', 'yes')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=int(os.environ.get('SESSION_HOURS', '12')))

# Init SocketIO — batasi CORS ke origin aplikasi (bukan "*").
# Override via env SOCKETIO_ALLOWED_ORIGINS (dipisah koma) bila domain berubah.
_socketio_origins = [
    o.strip() for o in os.environ.get(
        'SOCKETIO_ALLOWED_ORIGINS',
        'https://nasbpfsby.duckdns.org:5000,'
        'https://192.168.2.31:5000,http://192.168.2.31:5000,'
        'http://localhost:5000,http://127.0.0.1:5000',
    ).split(',') if o.strip()
]
socketio = SocketIO(app, cors_allowed_origins=_socketio_origins, async_mode=socketio_async_mode, logger=False, engineio_logger=False)

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

# First Work / Absensi FirstWork (v2.80.0): tabel first_work_* — form publik
# trainee, verifikasi Traineer, read-only Finance. Aman diulang saat startup.
from modules.first_work_schema import ensure_first_work_schema
for _attempt in range(5):
    if ensure_first_work_schema():
        break
    _time.sleep(3)

# Receptionist sheet sync (v2.41.0): tabel employee_inout + kolom sync di
# applicants (safe on every startup, paritas schema ensure lainnya).
from modules.routes_receptionist import ensure_receptionist_schema
ensure_receptionist_schema()

# v2.41.1: auto-sync sheet pelamar & in-out karyawan tiap 30 menit
# (background daemon thread, paritas auto-cleanup foto overtime).
from modules.routes_receptionist import start_receptionist_auto_sync
start_receptionist_auto_sync()

# Multi-cabang (v2.19.2): tabel branches + kolom users.branch_code + cabang utama,
# lalu sinkronkan skema untuk setiap cabang aktif yang punya database sendiri.
from modules import branch_manager as bm
bm.ensure_branches_table()
bm.ensure_users_branch_column()
bm.seed_main_branch()

# Penomoran dokumen v2.29.10: tabel doc_sequences (master + tiap cabang)
from modules.helpers import ensure_doc_sequences
for _attempt in range(5):
    if ensure_doc_sequences():
        break
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _ok, _msg = bm.ensure_branch_database(_b['code'])
            print(f'[branches] {_b["code"]}: {_msg}')
except Exception as _be:
    print(f'[branches] startup sync error: {_be}')

# Integritas dokumen v2.35.0 (Tahap 6/6): registri hash di DB master.
from modules.doc_integrity import ensure_document_registry
ensure_document_registry()

# Approval berjenjang v2.36.0: tabel jurnal ACC (approval_requests) di DB
# master + tiap DB cabang, dan kolom users.manager_username (override atasan).
from modules.approvals import ensure_approval_tables, ensure_manager_column
from modules.config import get_master_connection as _ret_master, _pool_for as _ret_pool
for _attempt in range(5):
    _aconn = _ret_master()
    if _aconn:
        try:
            if ensure_manager_column(_aconn) and ensure_approval_tables(_aconn):
                break
        except Exception as _ae:
            print(f'[approvals] master ensure error: {_ae}')
        finally:
            try:
                _aconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _bp = _ret_pool(_b['db_name'])
            if _bp:
                try:
                    _bc = _bp.get_connection()
                    try:
                        ensure_manager_column(_bc)
                        ensure_approval_tables(_bc)
                    finally:
                        try:
                            _bc.close()
                        except Exception:
                            pass
                except Exception as _ae:
                    print(f'[approvals] {_b["code"]} ensure error: {_ae}')
except Exception as _be:
    print(f'[approvals] branch ensure error: {_be}')

# Penugasan v2.73.0: tabel riwayat tukar driver (assignment_swaps) ikut
# dijamin di master + tiap DB cabang (idempoten) — pola blok approvals di atas.
from modules.routes_api_assignments import ensure_assignment_tables
for _attempt in range(5):
    _aconn = _ret_master()
    if _aconn:
        try:
            if ensure_assignment_tables(_aconn):
                break
        except Exception as _ae:
            print(f'[assignments] master ensure error: {_ae}')
        finally:
            try:
                _aconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _bp = _ret_pool(_b['db_name'])
            if _bp:
                try:
                    _bc = _bp.get_connection()
                    try:
                        ensure_assignment_tables(_bc)
                    finally:
                        try:
                            _bc.close()
                        except Exception:
                            pass
                except Exception as _ae:
                    print(f'[assignments] {_b["code"]} ensure error: {_ae}')
except Exception as _be:
    print(f'[assignments] branch ensure error: {_be}')

# Identitas driver v2.78.0: tautkan `drivers.user_id` ke `users.id` di tiap DB
# cabang (idempoten + backfill dari nama lama). Satu akun = satu profil driver.
from modules.driver_identity import (
    ensure_driver_user_schema as _ensure_driver_link,
    backfill_driver_links as _backfill_driver_links,
)
from modules.config import get_master_connection as _di_master, _pool_for as _di_pool
for _attempt in range(5):
    _dconn = _di_master()
    if _dconn:
        try:
            if _ensure_driver_link(_dconn):
                break
        except Exception as _de:
            print(f'[driver-identity] master ensure error: {_de}')
        finally:
            try:
                _dconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    _drv_users = []
    _duconn = _di_master()
    if _duconn:
        try:
            _duc = _duconn.cursor(dictionary=True)
            _duc.execute("SELECT id, username, full_name, role, branch_code, is_active FROM users")
            _drv_users = _duc.fetchall()
            _duc.close()
        finally:
            try:
                _duconn.close()
            except Exception:
                pass
    for _b in bm.list_branches():
        if not (_b.get('is_active') and _b.get('db_name')):
            continue
        _dp = _di_pool(_b['db_name']) if _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system') else None
        _dbc = None
        try:
            _dbc = _dp.get_connection() if _dp else _di_master()
            if _dbc:
                _ensure_driver_link(_dbc)
                # Hanya user cabang ini — jangan tautkan driver clone cabang
                # lain ke akun SBY (nama sama, orang/DB berbeda).
                _bcode = (_b.get('code') or '').strip().upper()
                _busers = [u for u in _drv_users
                           if ((u.get('branch_code') or '').strip().upper() or bm.DEFAULT_BRANCH_CODE.upper()) == _bcode]
                _backfill_driver_links(_dbc, _busers)
        except Exception as _de:
            print(f'[driver-identity] {_b["code"]} ensure error: {_de}')
        finally:
            try:
                if _dbc:
                    _dbc.close()
            except Exception:
                pass
except Exception as _be:
    print(f'[driver-identity] branch ensure error: {_be}')

# Retensi v2.34.0 (Tahap 5/6): tabel arsip audit + register tindakan retensi
# dibuat di master & setiap DB cabang (activity_logs tersebar per-cabang).
from modules.routes_retention import ensure_retention_tables
from modules.config import get_master_connection as _ret_master, _pool_for as _ret_pool
for _attempt in range(5):
    _rconn = _ret_master()
    if _rconn:
        try:
            if ensure_retention_tables(_rconn):
                break
        except Exception as _re:
            print(f'[retention] master ensure error: {_re}')
        finally:
            try:
                _rconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _bp = _ret_pool(_b['db_name'])
            if _bp:
                try:
                    _bc = _bp.get_connection()
                    try:
                        ensure_retention_tables(_bc)
                    finally:
                        try:
                            _bc.close()
                        except Exception:
                            pass
                except Exception as _re:
                    print(f'[retention] {_b["code"]} ensure error: {_re}')
except Exception as _be:
    print(f'[retention] branch ensure error: {_be}')

# v2.37.0: kolom jejak edit air minum (water_purchases.edited_by/edited_at/
# edit_count) + kolom admin per-cabang (users.admin_all_branches/
# managed_branches) di master + tiap DB cabang.
from modules.routes_water import ensure_water_edit_columns
from modules.admin_scope import ensure_branch_admin_columns
for _attempt in range(5):
    _wconn = _ret_master()
    if _wconn:
        try:
            _ok_w = ensure_water_edit_columns(_wconn)
            _ok_a = ensure_branch_admin_columns(_wconn)
            if _ok_w and _ok_a:
                break
        except Exception as _we:
            print(f'[water-admin] master ensure error: {_we}')
        finally:
            try:
                _wconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _bp = _ret_pool(_b['db_name'])
            if _bp:
                try:
                    _bc = _bp.get_connection()
                    try:
                        ensure_water_edit_columns(_bc)
                        ensure_branch_admin_columns(_bc)
                    finally:
                        try:
                            _bc.close()
                        except Exception:
                            pass
                except Exception as _we:
                    print(f'[water-admin] {_b["code"]} ensure error: {_we}')
except Exception as _be:
    print(f'[water-admin] branch ensure error: {_be}')

# Pengadaan v2.70.0: tabel suppliers/purchase_orders/po_items/po_receipts
# di DB master + tiap DB cabang (idempoten, pola ensure lainnya).
from modules.routes_procurement import ensure_procurement_schema
for _attempt in range(5):
    _pconn = _ret_master()
    if _pconn:
        try:
            if ensure_procurement_schema(_pconn):
                break
        except Exception as _pe:
            print(f'[procurement] master ensure error: {_pe}')
        finally:
            try:
                _pconn.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _bp = _ret_pool(_b['db_name'])
            if _bp:
                try:
                    _bc = _bp.get_connection()
                    try:
                        ensure_procurement_schema(_bc)
                    finally:
                        try:
                            _bc.close()
                        except Exception:
                            pass
                except Exception as _pe:
                    print(f'[procurement] {_b["code"]} ensure error: {_pe}')
except Exception as _be:
    print(f'[procurement] branch ensure error: {_be}')

# Inventaris IT v2.78.0: tabel it_assets/it_asset_events/it_discovery_*/
# it_stocktake_* di DB master + tiap DB cabang (idempoten, pola ensure lain).
from modules.it_inventory_schema import ensure_it_inventory_schema
for _attempt in range(5):
    _ic = _ret_master()
    if _ic:
        try:
            if ensure_it_inventory_schema(_ic):
                break
        except Exception as _ie:
            print(f'[it-inventory] master ensure error: {_ie}')
        finally:
            try:
                _ic.close()
            except Exception:
                pass
    _time.sleep(3)
try:
    for _b in bm.list_branches():
        if _b.get('is_active') and _b.get('db_name') and _b['db_name'] != os.environ.get('DB_NAME', 'bpf_asset_system'):
            _ib = _ret_pool(_b['db_name'])
            if _ib:
                try:
                    _icn = _ib.get_connection()
                    try:
                        ensure_it_inventory_schema(_icn)
                    finally:
                        try:
                            _icn.close()
                        except Exception:
                            pass
                except Exception as _ie:
                    print(f'[it-inventory] {_b["code"]} ensure error: {_ie}')
except Exception as _be:
    print(f'[it-inventory] branch ensure error: {_be}')

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
from modules.routes_nav import register_nav_routes
from modules.routes_docseq import register_docseq_routes
from modules.routes_overtime import register_overtime_routes
from modules.routes_receptionist import register_receptionist_routes
from modules.routes_spa import register_spa_routes
from modules.news_scraper import register_news_scraper_routes
from modules.security import register_health_routes
from modules.stepup import register_stepup_routes
from modules.routes_accessreview import register_access_review_routes
from modules.routes_retention import register_retention_routes
from modules.routes_documents import register_document_routes
from modules.routes_subsidy import register_subsidy_routes  # v2.50.0
from modules.routes_procurement import register_procurement_routes          # v2.70.0
from modules.routes_expense import register_expense_routes                    # v2.71.0
from modules.routes_it_assets import register_it_asset_routes                # v2.78.0
from modules.routes_first_work import register_first_work_routes             # v2.80.0
from modules.routes_profile import register_profile_routes                   # v2.81.0
from modules.approvals import register_approval_routes
from modules.transcoder import register_transcoder_routes
from modules.pdfkit import register_pdfkit_routes

register_driver_routes(app, socketio)
register_auth_routes(app)
register_procurement_routes(app)
register_expense_routes(app)
register_it_asset_routes(app)
register_first_work_routes(app)   # v2.80.0 — Absensi FirstWork (trainee)
register_profile_routes(app)      # v2.81.0 — Profil Saya (ganti nama & PIN)
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
register_nav_routes(app)
register_docseq_routes(app)
register_overtime_routes(app)
register_receptionist_routes(app)
register_spa_routes(app)
register_news_scraper_routes(app)
register_health_routes(app)
register_stepup_routes(app)
register_access_review_routes(app)
register_retention_routes(app)
register_document_routes(app)
register_approval_routes(app)
register_transcoder_routes(app)
register_pdfkit_routes(app)
register_subsidy_routes(app)  # v2.50.0 — integrasi Subsidi Tepat

# ================================================================
# AUTO-CLEANUP: Hapus foto overtime > 6 bulan (180 hari)
# Dijalankan di background thread saat startup & periodik tiap 30 menit.
# ================================================================
def _periodic_photo_cleanup():
    """Hapus foto overtime yang lebih lama dari 180 hari. Dijalankan periodik."""
    import threading
    while True:
        try:
            from modules.routes_overtime import _cleanup_old_photos
            result = _cleanup_old_photos(max_age_days=180)
            if result.get('deleted', 0) > 0:
                print(f'[overtime-cleanup] Auto-cleanup: {result["deleted"]} foto dihapus')
        except Exception as e:
            print(f'[overtime-cleanup] Error: {e}')
        # Tidur 30 menit (1800 detik)
        threading.Event().wait(1800)

try:
    import threading as _threading
    _cleanup_thread = _threading.Thread(target=_periodic_photo_cleanup, daemon=True)
    _cleanup_thread.start()
    print('[overtime-cleanup] Background cleanup thread started (setiap 30 menit)')
except Exception as _tc_err:
    print(f'[overtime-cleanup] Gagal start thread: {_tc_err}')

# ================================================================
# CSRF PROTECTION (berlaku untuk sesi admin yang login)
# Endpoint PWA driver (tanpa session) & socket.io dikecualikan.
# ================================================================
# v2.5: endpoint driver (submit-trip, cash request/submit-lpj/delete, driver-complete)
# kini WAJIB sesi login PIN — SPA driver mengirim X-CSRF-Token (api()/fetch), jadi
# tidak perlu lagi dikecualikan dari proteksi CSRF (defense-in-depth).
# v2.47.1: /api/assignments/confirm ikut dilepas dari daftar pengecualian —
# endpointnya kini wajib sesi driver (lihat modules/routes_api_assignments.py).
# v2.83.0: /api/first-work/public dikecualikan — form publik dikunjungi orang
# tanpa login, tapi traineer/admin yang kebetulan masih bersesi login bisa
# membawa token CSRF basi dari SPA lama dan terlantung 400 tanpa alasan jelas.
# Endpoint tetap aman: rate limit per IP + validasi isi file + tanpa akses data.
CSRF_EXEMPT_PREFIXES = (
    '/socket.io', '/api/get-feedback',
    '/api/vehicle-allowed-bbm', '/uploads/',
    '/api/first-work/public',
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
    session_token = session.get('csrf_token')
    # v2.74.0 (pentest hardening): perbandingan konstan-waktu (anti timing attack)
    if not token or not session_token or not hmac.compare_digest(str(token), str(session_token)):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'msg': 'CSRF token tidak valid. Muat ulang halaman dan coba lagi.'}), 400
        flash('Sesi tidak valid. Silakan muat ulang halaman dan coba lagi.', 'error')
        ref = request.referrer or ''
        return redirect(ref if ref.startswith('/') else url_for('admin_dashboard'))
    return None

# v2.47.1: jaring pengaman koneksi DB — route yang lupa close() di jalur error
# tidak lagi membocorkan koneksi pool (lihat modules/config.py).
@app.teardown_request
def release_db_connections(exc):
    from modules.config import release_request_connections
    release_request_connections()


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
    # HSTS: paksa HTTPS di browser (aktif saat HTTPS — langsung maupun via
    # proxy reverse yang meneruskan X-Forwarded-Proto, v2.74.0).
    forwarded_proto = (request.headers.get('X-Forwarded-Proto') or '').lower()
    if request.is_secure or forwarded_proto == 'https':
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

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


@app.before_request
def session_binding_check():
    """Anti session hijacking: bind session ke IP + User-Agent.
    Bila IP atau UA berubah signifikan setelah login, session dianggap
    tidak valid (potensi hijacking). Skip untuk endpoint publik & socket.io.
    ISO/IEC 27001 A.8.5 — manajemen sesi.
    """
    p = request.path
    if p.startswith(('/socket.io', '/uploads/', '/api/overtime/form')):
        return None
    if not session.get('user_role'):
        return None
    # Skip binding check untuk mobile driver (IP bisa berubah saat pindah jaringan)
    if session.get('user_role') == 'driver':
        return None
    # Simpan IP & UA saat login
    if '_bind_ip' not in session:
        session['_bind_ip'] = request.remote_addr
        session['_bind_ua'] = request.user_agent.string[:200]
    # Cek binding — hanya flag, tidak block (production-safe)
    current_ip = request.remote_addr
    saved_ip = session.get('_bind_ip', '')
    if saved_ip and current_ip != saved_ip:
        # IP berbeda → log warning (bukan blocker karena NAT/proxy)
        print(f'[SESSION] IP binding mismatch: {session.get("user_name", "?")} '
              f'({saved_ip} → {current_ip})')

if __name__ == '__main__':
    # Werkzeug dev runner HANYA untuk development lokal.
    # Produksi selalu via gunicorn (CMD Dockerfile), tidak melewati blok ini.
    # Guard: di production jalur python app.py langsung ditolak — menghindari
    # server dev tanpa TLS/proxy secara tak sengaja (v2.49.2 audit fix).
    if os.environ.get('FLASK_ENV', 'production').lower() == 'production':
        raise SystemExit(
            '[SECURITY] Refused to run Werkzeug dev server in production.\n'
            '           Gunakan: gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:5000 app:app'
        )
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
