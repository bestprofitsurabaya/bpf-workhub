"""Database & App Configuration (v2.19.2 — multi-cabang).

Satu instalasi, banyak cabang: setiap cabang punya DATABASE MySQL sendiri
(isolasi data penuh). DB default (DB_NAME) adalah DB *master* — menyimpan
`users`, `branches`, dan data operasional cabang utama sekaligus.

Routing:
- get_db_connection(master=True)  → selalu DB master (users/branches).
- get_db_connection()             → DB cabang aktif dari session['branch_code']
  (bila ada), selain itu DB master/default (pra-login & cabang utama).
"""
import os
import threading
import time
from mysql.connector import Error, pooling
from mysql.connector.connection import MySQLConnection

# v2.30 (ISO/IEC 27001 A.8.2/A.8.13): kredensial DB HANYA dari environment
# (docker-compose membacanya dari .env) — TIDAK ada fallback password default
# yang dikenal publik di kode/repo. Bila env hilang di luar mode development,
# app gagal start (fail-fast) alih-alih diam-diam memakai kredensial lama.
def _resolve_db_password():
    pw = os.environ.get('DB_PASSWORD')
    if pw:
        return pw
    env = os.environ.get('FLASK_ENV', '')
    if env == 'production':
        raise RuntimeError(
            'DB_PASSWORD environment variable is required in production. '
            'Set it before starting the app (lihat .env.example).')
    # Dev/test tanpa env: pakai dummy agar jelas GAGAL connect (bukan diam-diam
    # memakai kredensial default yang dikenal publik).
    print('[SECURITY] WARNING: DB_PASSWORD tidak diset — memakai nilai dev-only '
          '(tidak akan connect ke DB).')
    return 'dev-only-insecure-db-password-not-for-production'

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'db'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER', 'bpf_user'),
    'password': _resolve_db_password(),
    'database': os.environ.get('DB_NAME', 'bpf_asset_system'),
    'pool_name': 'bbm_pool',
    'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
    'pool_reset_session': True,
    'autocommit': False,
    'connect_timeout': 60,
    'use_pure': True
}

db_pool = None
_branch_pools = {}
_pool_lock = threading.Lock()
_pool_last_attempt = 0.0


def _base_config(db_name=None):
    """Konfigurasi koneksi NON-pool untuk satu database tertentu."""
    cfg = {k: v for k, v in DB_CONFIG.items()
           if k not in ('pool_name', 'pool_size', 'pool_reset_session')}
    if db_name:
        cfg['database'] = db_name
    return cfg


def _pool_for(db_name):
    """Pool khusus per database cabang (lazy, di-cache)."""
    if db_name in _branch_pools:
        return _branch_pools[db_name]
    cfg = dict(DB_CONFIG)
    cfg['database'] = db_name
    cfg['pool_name'] = 'pool_' + db_name.replace('.', '_')
    # DB cabang jauh lebih sepi dari master (data 1-2MB vs ratusan MB) — pakai
    # pool kecil (default 5) agar total koneksi idle tidak menggerus RAM host.
    # mysql.connector membuka SEMUA koneksi pool saat init (eager), jadi
    # DB_POOL_SIZE besar × 10 DB = ratusan koneksi menganggur.
    cfg['pool_size'] = int(os.environ.get('BRANCH_POOL_SIZE', 5))
    try:
        pool = pooling.MySQLConnectionPool(**cfg)
        _branch_pools[db_name] = pool
        return pool
    except Error as e:
        print(f"❌ Branch pool init failed ({db_name}): {e}")
        return None


def init_pool():
    global db_pool, _pool_last_attempt
    try:
        db_pool = pooling.MySQLConnectionPool(**DB_CONFIG)
        print("✔ MySQLConnectionPool initialized")
    except Error as e:
        print(f"❌ Pool init failed: {e}")
        db_pool = None
    finally:
        _pool_last_attempt = time.time()


def _ensure_pool():
    """Lazy (re)init pool master (v2.47.1).

    Dulu pool hanya dibuat sekali saat `import app`. Bila DB belum siap/DNS
    gagal saat itu (kejadian nyata: "❌ Pool init failed ... Temporary failure
    in name resolution"), pool TIDAK PERNAH dibuat lagi → seluruh request
    memakai koneksi non-pool baru (mahal & berisiko menembus max_connections)
    sampai worker di-restart. Sekarang pool dicoba ulang saat ada request,
    dengan jeda minimal DB_POOL_REINIT_SECONDS agar DB yang mati tidak
    dihujani percobaan koneksi tiap request.
    """
    global db_pool, _pool_last_attempt
    if db_pool is not None:
        return db_pool
    cooldown = int(os.environ.get('DB_POOL_REINIT_SECONDS', '30'))
    with _pool_lock:
        if db_pool is not None:
            return db_pool
        if time.time() - _pool_last_attempt < cooldown:
            return None
        try:
            db_pool = pooling.MySQLConnectionPool(**DB_CONFIG)
            print("✔ MySQLConnectionPool re-initialized (lazy)")
        except Error as e:
            print(f"❌ Pool re-init failed: {e}")
            db_pool = None
        finally:
            _pool_last_attempt = time.time()
    return db_pool


def resolve_db_name(branch_code=None):
    """Tentukan nama database efektif: cabang sesi (bila ada) atau master."""
    if branch_code is None:
        try:
            from flask import has_request_context, session
            if has_request_context():
                branch_code = session.get('branch_code')
        except Exception:
            pass
    if branch_code:
        try:
            from modules.branch_manager import get_branch_db_name
            db = get_branch_db_name(branch_code)
            if db and db != DB_CONFIG['database']:
                return db
        except Exception:
            pass
    return DB_CONFIG['database']


# ---------------------------------------------------------------------------
# Request-scoped connection tracking (v2.47.1)
# ---------------------------------------------------------------------------
# Latar: banyak route mengambil koneksi lalu `return jsonify(error), 500` di
# blok `except` TANPA close(). mysql.connector tidak mengembalikan koneksi ke
# pool sebelum close() → tiap error path membocorkan satu koneksi sampai pool
# habis (gejala produksi: "⚠ Pool exhausted" berulang, lalu request sehat pun
# gagal 500). Daripada menyisir ratusan route satu per satu, setiap koneksi
# yang diambil DI DALAM request context dicatat dan dikembalikan otomatis di
# teardown_request (close() kedua pada koneksi yang sudah ditutup di-skip).
def _track_connection(conn):
    if conn is None:
        return
    try:
        from flask import has_request_context, g
        if not has_request_context():
            return
        conns = getattr(g, '_db_conns', None)
        if conns is None:
            conns = []
            g._db_conns = conns
        conns.append(conn)
    except Exception:
        pass


def _is_pooled_open(conn):
    """True bila koneksi masih memegang koneksi fisik (belum di-close)."""
    # PooledMySQLConnection: close() mengosongkan ._cnx. Koneksi non-pool
    # (fallback) tidak punya atribut ._cnx → selalu aman di-close ulang.
    if hasattr(conn, '_cnx'):
        return getattr(conn, '_cnx') is not None
    return True


def release_request_connections():
    """Kembalikan ke pool semua koneksi request yang belum ditutup route."""
    try:
        from flask import has_request_context, g
        if not has_request_context():
            return
        conns = g.pop('_db_conns', None) or []
    except Exception:
        return
    for conn in conns:
        try:
            if _is_pooled_open(conn):
                conn.close()
        except Exception as e:
            print(f'⚠ Gagal mengembalikan koneksi ke pool: {e}')


def get_db_connection(branch_code=None, master=False):
    db_name = DB_CONFIG['database'] if master else resolve_db_name(branch_code)
    pool = _ensure_pool() if db_name == DB_CONFIG['database'] else _pool_for(db_name)
    if pool:
        # Retry singkat sebelum menyerah: pool mysql.connector memakai
        # block=False (langsung PoolError saat semua koneksi dipakai sesaat).
        # Retry ber-backoff menghindari pembukaan koneksi non-pool baru yang
        # justru membebani MariaDB (batas max_connections).
        retries = int(os.environ.get('DB_POOL_RETRIES', '3'))
        for attempt in range(retries + 1):
            try:
                conn = pool.get_connection()
                _track_connection(conn)
                return conn
            except Error as pool_err:
                if attempt == retries:
                    print(f"⚠ Pool exhausted ({db_name}): {pool_err}")
                else:
                    time.sleep(0.15 * (attempt + 1))

    # Fallback: koneksi langsung NON-POOL (sama seperti sebelumnya).
    max_retries = 5
    fallback_config = _base_config(db_name)
    for attempt in range(max_retries):
        try:
            conn = MySQLConnection(**fallback_config)
            _track_connection(conn)
            return conn
        except Error:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)
    return None


# Alias eksplisit untuk koneksi master (users/branches) — lebih terbaca di route.
def get_master_connection():
    return get_db_connection(master=True)


def get_db_pool_info():
    """Info ringkas pool DB (untuk /api/health). Aman bila pool belum init."""
    info = {'master_pool': 'not_initialized'}
    try:
        if db_pool is not None:
            size = DB_CONFIG.get('pool_size', 10)
            info['master_pool'] = f'ready/{size}'
        info['branch_pools'] = {name: 'ready' for name in _branch_pools}
    except Exception:
        pass
    return info
