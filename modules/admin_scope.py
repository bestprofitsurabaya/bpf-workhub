"""Admin per-cabang (v2.37.0) — scoping hak admin per cabang.

Konvensi username (lanjutan v2.29.7 `{divisi}_{cabang}`):
- `admin` (tanpa sufiks) → Admin Pusat: akses seluruh cabang, boleh ganti
  cabang kerja, kelola cabang/user global, reset nomor dokumen, arsip audit,
  access review. Akun `admin` yang sudah ada tetap berkuasa penuh.
- `admin_<cabang>` (mis. `admin_sby`, `admin_bdg`) → Admin Cabang: rolenya
  tetap `admin` (semua halaman admin tampil), tapi operasinya terkunci ke
  cabangnya — tidak bisa mengganti cabang kerja & tidak bisa menjalankan
  aksi lintas cabang (reset nomor dokumen cabang lain, arsip audit global,
  kelola cabang/user, dsb.).

Aturan (fail-closed): akun `admin_<kode>` hanya di-scope ke `kode` bila kode
itu terdaftar di tabel branches; suffix tak dikenal → dianggap admin cabang
yang belum punya cabang valid (bukan otomatis naik jadi Admin Pusat).

Kolom pendukung di `users` (DB master, dibuat otomatis saat startup):
- `admin_all_branches` : flag khusus — paksa akun boleh semua cabang
  (pemisahan tugas khusus / darurat, di-set langsung via SQL oleh Admin Pusat).
- `managed_branches`   : daftar kode cabang tambahan dipisah koma
  (mis. "SBY,BDG") — satu admin untuk dua cabang.

Nama akun Admin Pusat tambahan bisa diisi via env `ADMIN_HO_USERNAMES`
(dipisah koma) tanpa mengubah kode.
"""
import os

from flask import jsonify, session

# Username admin pusat legacy (tanpa sufiks cabang) + tambahan via env —
# dipertahankan agar akun lama `admin` tidak kehilangan akses.
HO_ADMIN_USERNAMES = {'admin'} | {
    u.strip().lower() for u in os.environ.get('ADMIN_HO_USERNAMES', '').split(',')
    if u.strip()
}


def _norm_code(code):
    return str(code or '').strip().upper()


def _username():
    return str(session.get('user_name') or '').strip().lower()


def _session_branch():
    return _norm_code(session.get('branch_code'))


def ensure_branch_admin_columns(conn=None):
    """ALTER users ADD admin_all_branches + managed_branches (master) — idempoten."""
    own = conn is None
    if own:
        from modules.config import get_master_connection
        conn = get_master_connection()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        for ddl in (
            "ALTER TABLE users ADD COLUMN admin_all_branches TINYINT(1) DEFAULT 0",
            "ALTER TABLE users ADD COLUMN managed_branches VARCHAR(255) DEFAULT ''",
        ):
            try:
                cursor.execute(ddl)
            except Exception:
                pass  # kolom sudah ada
        conn.commit()
        return True
    finally:
        cursor.close()
        if own and conn:
            conn.close()


def _admin_row(conn=None):
    """Baris users untuk admin yang sedang login (None bila tidak ditemukan).

    DB mati / tidak tersedia → None (fail-closed: dianggap Admin cabang).
    """
    uname = _username()
    if not uname:
        return None
    own = conn is None
    if own:
        try:
            from modules.config import get_master_connection
            conn = get_master_connection()
        except Exception:
            conn = None
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT admin_all_branches, managed_branches FROM users "
            "WHERE username=%s AND is_active=TRUE LIMIT 1", (uname,))
        return cursor.fetchone()
    except Exception:
        return None
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def is_ho_admin(conn=None):
    """True bila sesi saat ini adalah Admin Pusat — boleh semua cabang.

    Aturan sederhana & fail-closed:
    - username persis `admin` (atau terdaftar di ADMIN_HO_USERNAMES) → Pusat.
    - username `admin_<apa pun>` → Admin cabang (suffix = kode cabang).
    - Pengecualian: flag `admin_all_branches` di tabel users memaksa akun
      manapun berperilaku sebagai Admin Pusat.

    Tanpa DB (flag tak bisa dibaca) → hanya username Pusat yang lolos.
    """
    if session.get('user_role') != 'admin':
        return False
    if _username() in HO_ADMIN_USERNAMES:
        return True
    row = _admin_row(conn)
    if row and row.get('admin_all_branches'):
        return True
    return False


def admin_managed_branches(conn=None):
    """Kode cabang tambahan milik admin ini (dari users.managed_branches)."""
    row = _admin_row(conn)
    if not row:
        return []
    raw = str(row.get('managed_branches') or '')
    return [_norm_code(c) for c in raw.split(',') if _norm_code(c)]


def admin_branches(conn=None):
    """Daftar kode cabang yang boleh dioperasikan admin ini.

    Returns (codes, all_branches):
    - Admin Pusat   → ([], True)  — semua cabang.
    - Admin cabang  → ([kode], False) + tambahan managed_branches; kode diambil
      dari suffix username (`admin_sby` → SBY) sebagai sumber utama, fallback
      cabang sesi bila suffix tidak terbaca.
    """
    if is_ho_admin(conn):
        return [], True
    codes = []
    suffix = _username().split('_', 1)[1] if '_' in _username() else ''
    if suffix:
        codes.append(_norm_code(suffix))
    if not codes:
        own_branch = _session_branch()
        if own_branch:
            codes.append(own_branch)
    for c in admin_managed_branches(conn):
        if c not in codes:
            codes.append(c)
    return codes, False


def admin_can_operate_branch(code, conn=None):
    """True bila admin sesi boleh mengoperasikan cabang `code`."""
    if session.get('user_role') != 'admin':
        return False
    codes, all_b = admin_branches(conn)
    if all_b:
        return True
    return _norm_code(code) in codes


def scope_denied_response():
    """Respons 403 standar untuk admin di luar cakupannya."""
    return jsonify({'status': 'error',
                    'msg': 'Aksi ini hanya untuk Admin Pusat (HO) — '
                           'akun admin cabang tidak punya akses lintas cabang.'}), 403


def ho_only(fn=None):
    """Decorator endpoint: lanjut hanya bila admin sesi = Admin Pusat (HO)."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get('user_role'):
                return jsonify({'status': 'error', 'msg': 'Login diperlukan.'}), 401
            if session.get('user_role') != 'admin':
                return jsonify({'status': 'error',
                                'msg': 'Role tidak diizinkan untuk aksi ini.'}), 403
            if not is_ho_admin():
                return scope_denied_response()
            return f(*args, **kwargs)
        return wrapper
    if fn is not None:
        return decorator(fn)
    return decorator


def assert_branch_row_scope(row):
    """Cek admin cabang hanya menyentuh baris cabangnya sendiri.

    `row` = baris operasional (mis. water_purchases) dari DB cabang sesi.
    Finance/OB di-scope oleh DB-nya masing-masing (get_db_connection), jadi
    hanya role admin yang perlu dicek di sini.

    Returns None bila lolos, atau (jsonify, 403) bila ditolak.
    """
    if session.get('user_role') != 'admin':
        return None
    code = _session_branch()
    if admin_can_operate_branch(code):
        return None
    return scope_denied_response()
