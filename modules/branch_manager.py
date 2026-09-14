"""Manajemen cabang (v2.19.2 — multi-cabang).

Setiap cabang = satu database MySQL terpisah (isolasi data penuh).
Tabel `branches` + `users` tinggal di DB master; data operasional
di database masing-masing cabang.

Alur:
- Admin mendaftarkan cabang (code, name, db_name, identitas).
- `ensure_branch_database()` membuat DB cabang + menyalin skema dari master
  (CREATE TABLE ... LIKE) lalu menjalankan migrasi aplikasi (appointments,
  notifications) dan menanam identitas ke system_config cabang.
- Setelah login, session['branch_code'] mengarahkan seluruh query
  operasional ke DB cabang via modules.config.get_db_connection().
"""
import os
from datetime import datetime

from modules.config import DB_CONFIG, get_db_connection, get_master_connection

DEFAULT_BRANCH_CODE = os.environ.get('BRANCH_MAIN_CODE', 'SBY')
DEFAULT_BRANCH_NAME = os.environ.get('BRANCH_MAIN_NAME', 'Cabang Surabaya')

BRANCH_COLUMNS = (
    'code', 'name', 'db_name', 'city', 'address', 'phone',
    'company_name', 'company_subtitle', 'system_name', 'system_version',
    'is_active',
)

_branch_db_cache = {}  # code -> (db_name, ts)


def _cache_get(code):
    hit = _branch_db_cache.get(code)
    if hit and (datetime.now() - hit[1]).total_seconds() < 60:
        return hit[0]
    return None


def _cache_set(code, db_name):
    _branch_db_cache[code] = (db_name, datetime.now())


def invalidate_branch_cache(code=None):
    if code:
        _branch_db_cache.pop(code, None)
    else:
        _branch_db_cache.clear()


def ensure_branches_table(conn=None):
    """CREATE TABLE branches (master DB) — idempoten."""
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                db_name VARCHAR(64) NOT NULL,
                city VARCHAR(100) DEFAULT '',
                address VARCHAR(255) DEFAULT '',
                phone VARCHAR(30) DEFAULT '',
                company_name VARCHAR(150) DEFAULT '',
                company_subtitle VARCHAR(150) DEFAULT '',
                system_name VARCHAR(100) DEFAULT '',
                system_version VARCHAR(30) DEFAULT '',
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def ensure_users_branch_column(conn=None):
    """ALTER users ADD branch_code (master DB) — idempoten."""
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN branch_code VARCHAR(20) DEFAULT NULL")
        except Exception:
            pass  # sudah ada
        conn.commit()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def seed_main_branch(conn=None):
    """Pastikan cabang utama (DB master) terdaftar — idempoten."""
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO branches (code, name, db_name, is_active) VALUES (%s,%s,%s,1) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name), db_name=VALUES(db_name), is_active=1",
            (DEFAULT_BRANCH_CODE, DEFAULT_BRANCH_NAME, DB_CONFIG['database']))
        conn.commit()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def get_branch(code, conn=None):
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM branches WHERE code=%s", (code,))
        return cursor.fetchone()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def get_branch_db_name(code):
    """db_name cabang (cache 60 detik). None bila tidak ada/nonaktif."""
    cached = _cache_get(code)
    if cached:
        return cached
    branch = get_branch(code)
    if not branch or not branch.get('is_active'):
        return None
    db = branch.get('db_name')
    _cache_set(code, db)
    return db


def list_branches(conn=None):
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM branches ORDER BY is_active DESC, name")
        return cursor.fetchall()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def save_branch(data, conn=None):
    """Upsert cabang (master). Bila db_name berubah & DB baru bisa dihubungi,
    identitas cabang ikut ditulis ke system_config DB cabang.

    Returns (branch_dict, error).
    """
    own = conn is None
    conn = conn or get_master_connection()
    code = str(data.get('code', '') or '').strip().upper()
    name = str(data.get('name', '') or '').strip()
    db_name = str(data.get('db_name', '') or '').strip()
    if not code or not name or not db_name:
        return None, 'code, name, dan db_name wajib diisi'
    if not db_name.replace('_', '').isalnum():
        return None, 'db_name hanya boleh huruf/angka/underscore'
    if conn is None:
        return None, 'DB tidak tersedia'
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, db_name FROM branches WHERE code=%s", (code,))
        existing = cursor.fetchone()
        vals = {
            'code': code, 'name': name, 'db_name': db_name,
            'city': str(data.get('city', '') or '').strip(),
            'address': str(data.get('address', '') or '').strip(),
            'phone': str(data.get('phone', '') or '').strip(),
            'company_name': str(data.get('company_name', '') or '').strip(),
            'company_subtitle': str(data.get('company_subtitle', '') or '').strip(),
            'system_name': str(data.get('system_name', '') or '').strip(),
            'system_version': str(data.get('system_version', '') or '').strip(),
            'is_active': 1 if data.get('is_active', True) in (True, 1, '1', 'true') else 0,
        }
        if existing:
            set_clause = ', '.join(f'{k}=%s' for k in vals)
            cursor.execute(f"UPDATE branches SET {set_clause} WHERE code=%s",
                           (*vals.values(), code))
        else:
            cols = ', '.join(vals)
            ph = ', '.join(['%s'] * len(vals))
            cursor.execute(f"INSERT INTO branches ({cols}) VALUES ({ph})", tuple(vals.values()))
        conn.commit()
        inv = {k: vals[k] for k in vals}
        branch = {**inv, 'id': existing['id'] if existing else cursor.lastrowid}
        # Tulis identitas ke DB cabang (bila sudah dibuat / bisa dihubungi)
        try:
            write_branch_identity(branch)
        except Exception:
            pass  # DB cabang belum ada — identitas di-copy saat ensure_branch_database
        invalidate_branch_cache(code)
        return branch, None
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def write_branch_identity(branch, conn=None):
    """Tulis identitas cabang ke system_config DB cabang (idempoten)."""
    from modules.company_identity import IDENTITY_DEFAULTS, IDENTITY_KEYS
    db_name = branch.get('db_name')
    if not db_name or db_name == DB_CONFIG['database']:
        # Cabang utama memakai master — identitas dibiarkan di system_config master.
        return
    own = conn is None
    if conn is None:
        from modules.config import _pool_for
        pool = _pool_for(db_name)
        if not pool:
            return
        conn = pool.get_connection()
    cursor = conn.cursor()
    try:
        mapping = {
            'company_name': branch.get('company_name'),
            'company_subtitle': branch.get('company_subtitle'),
            'system_name': branch.get('system_name'),
            'system_version': branch.get('system_version'),
            'company_address': branch.get('address'),
            'company_phone': branch.get('phone'),
        }
        # v2.40.3: system_version selalu mengikuti versi kode — bump versi yang
        # lupa meng-update tabel branches tidak lagi membuat startup menimpa
        # stamp system_config cabang dgn versi lama (insiden revert stamp v2.40.2).
        mapping['system_version'] = IDENTITY_DEFAULTS['system_version']
        for key in IDENTITY_KEYS:
            val = str(mapping.get(key, '') or '').strip()
            cursor.execute(
                "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                (key, val))
        conn.commit()
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def set_branch_active(code, active, conn=None):
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE branches SET is_active=%s WHERE code=%s",
                       (1 if active else 0, code))
        conn.commit()
        invalidate_branch_cache(code)
        return cursor.rowcount > 0
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def _escape_ident(name):
    return '`' + str(name).replace('`', '``') + '`'


def ensure_branch_database(code, conn=None):
    """Buat database cabang + salin skema dari master + migrasi aplikasi.

    Idempoten (CREATE DATABASE IF NOT EXISTS / CREATE TABLE IF NOT EXISTS /
    LIKE — aman dijalankan ulang). Returns (ok, msg).
    """
    branch = get_branch(code, conn=conn)
    if not branch:
        return False, 'Cabang tidak ditemukan'
    db_name = branch.get('db_name')
    if not db_name:
        return False, 'db_name cabang kosong'
    if db_name == DB_CONFIG['database']:
        return True, 'Cabang utama memakai DB master — tidak perlu database baru'

    master = conn or get_master_connection()
    if not master:
        return False, 'DB master tidak tersedia'
    mc = master.cursor(dictionary=True)
    try:
        mc.execute("CREATE DATABASE IF NOT EXISTS " + _escape_ident(db_name))
        mc.execute("SHOW TABLES")
        tables = [list(r.values())[0] for r in mc.fetchall()]
    finally:
        mc.close()

    # Salin struktur semua tabel (LIKE menjaga kolom/index/FK)
    from modules.config import _pool_for
    pool = _pool_for(db_name)
    if not pool:
        return False, f'Gagal membuat pool untuk database {db_name}'
    bc = pool.get_connection()
    bcursor = bc.cursor()
    try:
        for t in tables:
            bcursor.execute(
                f"CREATE TABLE IF NOT EXISTS {_escape_ident(db_name)}.{_escape_ident(t)} "
                f"LIKE {_escape_ident(DB_CONFIG['database'])}.{_escape_ident(t)}")
        bc.commit()
    finally:
        bcursor.close()
        # v2.35.1: koneksi ini TIDAK pernah ditutup → bocor 1/panggilan.
        try:
            bc.close()
        except Exception:
            pass

    # Migrasi aplikasi terhadap DB cabang. PENTING (v2.35.1): tiap helper
    # menerima koneksi pool yang WAJIB ditutup setelah dipakai. Sebelumnya
    # tiap helper dipanggil dengan `pool.get_connection()` inline tanpa
    # close → bocor hingga 5 koneksi per cabang per startup → pool cabang
    # (ukuran 5) langsung habis & semua operasi DB cabang gagal
    # ("pool exhausted") sampai container di-restart.
    from modules.notifications import ensure_notifications_table
    from modules.appointments_schema import ensure_appointments_schema
    from modules.helpers import ensure_doc_sequences
    from modules.approvals import ensure_approval_tables, ensure_manager_column  # v2.36.0
    from modules.overtime_schema import ensure_overtime_schema  # v2.36.2: paritas tabel overtime
    from modules.routes_water import ensure_water_edit_columns  # v2.37.0: jejak edit air minum
    from modules.admin_scope import ensure_branch_admin_columns  # v2.37.0: admin per-cabang

    def _run_ensure(fn, label):
        try:
            c2 = pool.get_connection()
            try:
                fn(c2)
            finally:
                try:
                    c2.close()
                except Exception:
                    pass
        except Exception as e:
            print(f'[branch {code}] {label}: {e}')

    _run_ensure(lambda c: ensure_notifications_table(conn=c), 'notifications')
    _run_ensure(lambda c: ensure_appointments_schema(conn=c), 'appointments schema')
    _run_ensure(lambda c: ensure_doc_sequences(conn=c), 'doc_sequences')
    _run_ensure(lambda c: (ensure_manager_column(c), ensure_approval_tables(c)), 'approval_requests')
    _run_ensure(lambda c: ensure_overtime_schema(conn=c), 'overtime schema')  # v2.36.2
    _run_ensure(lambda c: (ensure_water_edit_columns(c), ensure_branch_admin_columns(c)), 'water edit & admin scope')  # v2.37.0
    _run_ensure(lambda c: write_branch_identity(branch, conn=c), 'identity')

    return True, f'Database {db_name} untuk cabang {code} siap'


def branch_stats(conn=None):
    """Statistik ringkas per cabang (untuk dashboard Admin).

    - transactions (total) & appointments hari ini dari DB masing-masing cabang
    - jumlah user (master) per branch_code
    Cabang yang DB-nya tidak bisa dihubungi → 0 (tidak menggagalkan laporan).
    """
    branches = list_branches(conn=conn)
    # User per cabang (master)
    users_by_branch = {}
    mc = conn or get_master_connection()
    if mc:
        cur = mc.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT COALESCE(NULLIF(branch_code,''),%s) AS bc, COUNT(*) AS c FROM users GROUP BY bc",
                (DEFAULT_BRANCH_CODE,))
            for r in cur.fetchall():
                users_by_branch[r['bc']] = r['c']
        except Exception as e:
            print(f'[branches] users stats error: {e}')
        finally:
            cur.close()
            if conn is None:
                mc.close()

    stats = []
    for b in branches:
        db = b.get('db_name') or ''
        tx = appts_today = 0
        if b.get('is_active') and db:
            try:
                from modules.config import _pool_for
                c = None
                if db == DB_CONFIG['database']:
                    c = get_master_connection()
                else:
                    pool = _pool_for(db)
                    c = pool.get_connection() if pool else None
                if c:
                    cur = c.cursor(dictionary=True)
                    cur.execute("SELECT COUNT(*) AS c FROM transactions")
                    tx = cur.fetchone()['c'] or 0
                    cur.execute("SELECT COUNT(*) AS c FROM appointments WHERE appointment_date=CURDATE()")
                    appts_today = cur.fetchone()['c'] or 0
                    cur.close()
                    c.close()
            except Exception as e:
                print(f'[branches] stats error ({b["code"]}): {e}')
        stats.append({
            'code': b['code'], 'name': b['name'], 'db_name': db,
            'is_active': bool(b.get('is_active')),
            'transactions': tx, 'appointments_today': appts_today,
            'users': int(users_by_branch.get(b['code'], 0)),
        })
    return stats


def current_branch():
    """Info cabang aktif dari session (untuk UI)."""
    try:
        from flask import session
        code = session.get('branch_code')
        if not code:
            return {'code': DEFAULT_BRANCH_CODE, 'name': DEFAULT_BRANCH_NAME,
                    'db_name': DB_CONFIG['database'], 'main': True}
        branch = get_branch(code)
        return {
            'code': code,
            'name': (branch or {}).get('name') or session.get('branch_name') or code,
            'db_name': (branch or {}).get('db_name') or DB_CONFIG['database'],
            'main': (branch or {}).get('db_name') == DB_CONFIG['database'],
        }
    except Exception:
        return {'code': DEFAULT_BRANCH_CODE, 'name': DEFAULT_BRANCH_NAME,
                'db_name': DB_CONFIG['database'], 'main': True}
