"""Badge angka sidebar (P1 UI/UX) — hitungan ringan, tanpa audit log.

Satu endpoint `GET /api/nav/badges` mengembalikan hanya angka yang relevan
dengan role sesi. Hitungan memakai DB cabang sesi (multi-cabang), jadi admin
cabang otomatis hanya melihat antrean cabangnya.

Endpoint ini sengaja tanpa `log_activity_async`: dipanggil saat layout dimuat
dan setelah event realtime, bukan aksi pengguna yang perlu diaudit.
"""
from flask import jsonify, session

from modules.config import get_db_connection, get_master_connection
from modules.helpers import role_required

# Semua role yang memakai AppLayout (driver punya tampilan mobile sendiri).
_APP_ROLES = [
    'admin', 'ga', 'finance', 'marketing', 'chief_driver', 'ob', 'security',
    'receptionist', 'traineer', 'ga_hr',
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn',
    'it_bjm', 'it_lpg',
]


def _count(conn, sql, params=()):
    """COUNT(*) yang aman: error/DB tak siap → 0 (badge opsional)."""
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return 0
        try:
            return int(row[0] or 0)
        except (KeyError, IndexError, TypeError):
            return int((row or {}).get('c') or 0)
    except Exception:
        return 0
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass


def _approvals_pending(conn, role):
    """Jumlah jurnal ACC yang memang menjadi wewenang role ini."""
    try:
        from modules.approvals import decision_allowed
        actor = session.get('full_name') or session.get('user_name') or ''
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM approval_requests "
                        "WHERE status='pending' ORDER BY created_at ASC LIMIT 500")
            rows = cur.fetchall()
        finally:
            try:
                cur.close()
            except Exception:
                pass
        return sum(1 for r in rows if decision_allowed(r, actor, role))
    except Exception:
        return 0


def _first_work_pending():
    """Antrean verifikasi Absensi FirstWork untuk traineer/admin.

    Data FirstWork ada di DB MASTER dengan kolom `branch_code`, jadi hitungannya
    memakai koneksi master + scope cabang sesi (Admin Pusat = semua cabang).
    Badge opsional: error apa pun → 0, jangan ganggu sidebar.
    """
    conn = None
    try:
        from modules.routes_first_work import _scope_branch
        conn = get_master_connection()
        if not conn:
            return 0
        scope = _scope_branch(conn)
        sql = "SELECT COUNT(*) FROM first_work_submissions WHERE status='submitted'"
        params = []
        if scope:
            sql += ' AND branch_code=%s'
            params.append(scope)
        return _count(conn, sql, params)
    except Exception:
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def register_nav_routes(app):

    @app.route('/api/nav/badges')
    @role_required(_APP_ROLES)
    def api_nav_badges():
        role = session.get('user_role')
        out = {}
        conn = get_db_connection()
        if not conn:
            return jsonify({'badges': out})
        try:
            if role in ('ga', 'admin'):
                out['ga_pending'] = _count(
                    conn, "SELECT COUNT(*) FROM transactions "
                          "WHERE status IN ('pending','modified') AND (is_dummy=0 OR is_dummy IS NULL)")
                out['assignments_pending'] = _count(
                    conn, "SELECT COUNT(*) FROM vehicle_assignments "
                          "WHERE is_current=1 AND confirmed_by_driver=0")

            if role in ('finance', 'admin'):
                out['water_pending'] = _count(
                    conn, "SELECT COUNT(*) FROM water_purchases WHERE status='pending'")
                # v2.53.0: klaim AG terverifikasi siap pencairan — badge
                # 'Antrean Verifikasi' (klaim BBM kini bisa dibuka finance).
                out['bbm_verify_pending'] = _count(
                    conn, "SELECT COUNT(*) FROM transactions WHERE status='verified_ga' AND (is_dummy=0 OR is_dummy IS NULL)")

            if role in ('ga', 'finance', 'admin'):
                cash = 0
                if role in ('ga', 'admin'):
                    cash += _count(
                        conn, "SELECT COUNT(*) FROM fuel_cash_requests "
                              "WHERE status='LPJ_SUBMITTED'")
                if role in ('finance', 'admin'):
                    cash += _count(
                        conn, "SELECT COUNT(*) FROM fuel_cash_requests "
                              "WHERE status='GA_APPROVED'")
                out['cash_pending'] = cash

            if role in ('ga', 'chief_driver', 'ga_hr'):
                out['approvals_pending'] = _approvals_pending(conn, role)

            # v2.80.1: antrean verifikasi Absensi FirstWork (traineer & admin
            # yang memang boleh memverifikasi) — sumbernya DB master.
            if role in ('traineer', 'admin'):
                out['first_work_pending'] = _first_work_pending()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return jsonify({'badges': out})
