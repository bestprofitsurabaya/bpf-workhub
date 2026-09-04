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
import mysql.connector
from mysql.connector import Error, pooling
from mysql.connector.connection import MySQLConnection

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'db'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER', 'bpf_user'),
    'password': os.environ.get('DB_PASSWORD', 'bpf_pass'),
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
    global db_pool
    try:
        db_pool = pooling.MySQLConnectionPool(**DB_CONFIG)
        print("✔ MySQLConnectionPool initialized")
    except Error as e:
        print(f"❌ Pool init failed: {e}")
        db_pool = None


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


def get_db_connection(branch_code=None, master=False):
    import time
    db_name = DB_CONFIG['database'] if master else resolve_db_name(branch_code)
    pool = db_pool if db_name == DB_CONFIG['database'] else _pool_for(db_name)
    if pool:
        # Retry singkat sebelum menyerah: pool mysql.connector memakai
        # block=False (langsung PoolError saat semua koneksi dipakai sesaat).
        # Retry ber-backoff menghindari pembukaan koneksi non-pool baru yang
        # justru membebani MariaDB (batas max_connections).
        retries = int(os.environ.get('DB_POOL_RETRIES', '3'))
        for attempt in range(retries + 1):
            try:
                return pool.get_connection()
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
            return MySQLConnection(**fallback_config)
        except Error as e:
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
