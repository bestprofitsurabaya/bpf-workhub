"""Fitur keamanan & observabilitas terpusat (v2.21).

- Rate limiting sederhana per-IP (in-memory, window geser) untuk endpoint
  publik tanpa sesi — melengkapi rate-limit login yang sudah ada.
- Endpoint `/api/health`: status DB master + Redis + total koneksi pool,
  opsional status per-cabang (`?branches=1`) untuk admin.
"""
import time
from collections import defaultdict, deque
from functools import wraps

from flask import jsonify, request, session

# ============================================================
# RATE LIMIT SEDERHANA (in-memory, per-IP, window geser)
# ============================================================
_RL_STORE = defaultdict(deque)
_RL_LOCK = None  # GIL cukup aman untuk kasus ini (append/popleft atomik)

DEFAULT_LIMIT = 60      # permintaan per menit per IP (endpoint publik)
DEFAULT_WINDOW = 60     # detik


def _client_ip():
    # Konsisten dengan helpers.client_ip (hargai proxy trust)
    return request.remote_addr or 'unknown'


def rate_limit(limit=DEFAULT_LIMIT, window=DEFAULT_WINDOW, scope='public'):
    """Dekorator: batasi request per-IP untuk endpoint yang dilindungi.

    Menolak 429 saat melewati batas. Dipakai untuk endpoint publik yang
    rawan spam/abuse (form pelamar, seed demo, dll).
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f'{scope}:{_client_ip()}'
            now = time.monotonic()
            q = _RL_STORE[key]
            # Buang entri yang sudah lewat window
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return jsonify({'status': 'error', 'msg': 'Terlalu banyak permintaan. Coba lagi nanti.'}), 429
            q.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def clear_rate_limits():
    """Kosongkan seluruh store rate-limit (dipakai tes)."""
    _RL_STORE.clear()


# ============================================================
# HEALTH CHECK
# ============================================================
def health_payload(branches=False):
    """Payload status layanan: DB master, Redis, pool; opsional per cabang."""
    from modules.config import get_master_connection, get_db_pool_info
    from modules.branch_manager import list_branches

    status = {'status': 'ok', 'checks': {}}

    # DB master
    conn = get_master_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('SELECT 1')
            cur.fetchone()
            cur.close()
            status['checks']['database'] = 'ok'
        except Exception:
            status['checks']['database'] = 'error'
            status['status'] = 'degraded'
        finally:
            conn.close()
    else:
        status['checks']['database'] = 'error'
        status['status'] = 'degraded'

    # Redis (jika tersedia) — cek via koneksi ringan
    status['checks']['redis'] = 'ok' if _redis_ping() else 'unavailable'

    # Pool info (jika ada)
    try:
        info = get_db_pool_info()
        if info:
            status['checks']['pool'] = info
    except Exception:
        pass

    # Per cabang (admin)
    if branches and session.get('user_role') == 'admin':
        branch_checks = {}
        for b in (list_branches() or []):
            code = b.get('code')
            db_ok = _branch_db_ok(code)
            branch_checks[code] = 'ok' if db_ok else 'error'
            if not db_ok:
                status['status'] = 'degraded'
        status['checks']['branches'] = branch_checks

    return status


def _redis_ping():
    try:
        import os
        import redis
        url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
        r = redis.from_url(url, socket_timeout=2)
        return bool(r.ping())
    except Exception:
        return False


def _branch_db_ok(code):
    from modules.config import get_db_connection
    conn = get_db_connection(branch_code=code)
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def register_health_routes(app):
    @app.route('/api/health')
    def api_health():
        want_branches = request.args.get('branches') in ('1', 'true')
        return jsonify(health_payload(branches=want_branches))
