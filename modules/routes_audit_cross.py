"""Audit log lintas cabang untuk Admin Pusat (v2.116.0 — Fase 3 tata kelola).

Audit log hidup di DB masing-masing cabang (`activity_logs`). Sebelumnya Admin
Pusat harus memilih satu cabang di UI Log; pertanyaan "siapa mengubah apa di
seluruh cabang hari ini" tidak bisa dijawab tanpa 12 kali ganti cabang.

Endpoint ini melakukan fan-out **baca saja** ke DB cabang, menggabungkan hasil,
lalu mengurutkan berdasarkan waktu. Prinsipnya sama dengan panel Pusat:
- **Gagal sebagian boleh** — DB satu cabang mati tidak mengosongkan hasil;
  cabang itu masuk `errors` dan sisanya tetap tampil.
- **Batas per cabang** — default 50 baris/cabang supaya satu cabang ramai
  tidak menenggelamkan cabang lain; UI memfilter & memaginasi hasil gabungan.
- **Khusus HO** — Admin cabang ditolak; mereka tetap memakai endpoint per
  cabang yang sudah ada.
"""
from datetime import datetime
from flask import jsonify, request

from modules import branch_manager as bm
from modules.admin_scope import is_ho_admin, scope_denied_response
from modules.config import get_master_connection
from modules.helpers import role_required

MAX_DAYS = 90
MAX_PER_BRANCH = 200


def _clean(value, length=100):
    return str(value or '').strip()[:length]


def _connect_db(db_name):
    from modules.config import DB_CONFIG, _pool_for, get_master_connection
    if not db_name:
        return None
    if db_name == DB_CONFIG['database']:
        return get_master_connection()
    pool = _pool_for(db_name)
    return pool.get_connection() if pool else None


def _parse_json_cols(row):
    import json
    for key in ('old_data', 'new_data'):
        value = row.get(key)
        if isinstance(value, str):
            try:
                row[key] = json.loads(value)
            except (TypeError, ValueError):
                # Bukan JSON valid — biarkan string agar tetap bisa diperiksa.
                pass
    return row


def _query_branch(code, db_name, args, days, per_branch):
    """Ambil potongan log satu cabang. Return (rows, error)."""
    conn = None
    try:
        conn = _connect_db(db_name)
        if not conn:
            return [], 'DB tidak dapat dihubungi'
        where = ['created_at >= (NOW() - INTERVAL %s DAY)']
        params = [days]
        action = args.get('action')
        if action and action != 'all':
            where.append('action=%s')
            params.append(action)
        q = args.get('q')
        if q:
            like = f'%{q}%'
            where.append('(user_name LIKE %s OR action LIKE %s '
                         'OR transaction_id LIKE %s OR ip_address LIKE %s)')
            params += [like] * 4
        params.append(per_branch)
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, transaction_id, action, user_type, user_name, "
                "created_at, ip_address, branch_code FROM activity_logs "
                "WHERE " + ' AND '.join(where) +
                " ORDER BY created_at DESC, id DESC LIMIT %s", params)
            rows = cursor.fetchall() or []
        finally:
            cursor.close()
        for row in rows:
            row['branch_code'] = (row.get('branch_code') or code or '').upper()
            row['branch'] = code
            row['created_at'] = (str(row['created_at'])
                                 if row.get('created_at') else '')
        return rows, None
    except Exception as exc:
        return [], str(exc)[:160]
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _detail(code, log_id):
    """Detail satu entri (termasuk snapshot) dari DB cabang tertentu."""
    branch = bm.get_branch(code)
    if not branch:
        return None, 'Cabang tidak dikenal'
    conn = None
    try:
        conn = _connect_db(branch.get('db_name'))
        if not conn:
            return None, 'DB cabang tidak dapat dihubungi'
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, transaction_id, action, user_type, user_name, "
                "old_data, new_data, ip_address, user_agent, branch_code, "
                "created_at FROM activity_logs WHERE id=%s LIMIT 1", (log_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if not row:
            return None, 'Log tidak ditemukan'
        row['branch_code'] = (row.get('branch_code') or code or '').upper()
        row['branch'] = code
        row['created_at'] = str(row['created_at']) if row.get('created_at') else ''
        return _parse_json_cols(row), None
    except Exception as exc:
        return None, str(exc)[:160]
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def register_audit_cross_routes(app):

    @app.route('/api/admin/audit-logs/all')
    @role_required(['admin'])
    def api_audit_logs_all():
        if not is_ho_admin():
            return scope_denied_response()
        try:
            days = max(1, min(int(request.args.get('days', 7) or 7), MAX_DAYS))
            per_branch = max(10, min(
                int(request.args.get('per_branch', 50) or 50), MAX_PER_BRANCH))
            branch_filter = _clean(request.args.get('branch'), 10).upper()
            args = {
                'action': _clean(request.args.get('action'), 60),
                'q': _clean(request.args.get('q'), 100),
            }

            master = get_master_connection()
            if not master:
                return jsonify({'status': 'error',
                                'msg': 'DB master tidak tersedia'}), 500
            try:
                branches = bm.list_branches(conn=master)
            finally:
                try:
                    master.close()
                except Exception:
                    pass

            if branch_filter:
                branches = [b for b in branches
                            if str(b.get('code') or '').upper() == branch_filter]
            else:
                # Cabang nonaktif tetap ditampilkan bila diminta eksplisit,
                # tetapi tidak ikut fan-out "semua" (DB-nya bisa sudah hilang).
                branches = [b for b in branches if b.get('is_active')]

            rows, errors = [], []
            for b in branches:
                code = str(b.get('code') or '').strip().upper()
                part, err = _query_branch(code, b.get('db_name'), args,
                                          days, per_branch)
                if err:
                    errors.append({'branch': code, 'error': err})
                rows.extend(part)

            rows.sort(key=lambda r: (r.get('created_at') or '', r.get('id') or 0),
                      reverse=True)
            return jsonify({
                'logs': rows,
                'summary': {
                    'branches': len(branches),
                    'returned': len(rows),
                    'days': days,
                    'per_branch': per_branch,
                    'errors': len(errors),
                    'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                },
                'errors': errors,
            })
        except Exception as e:
            print(f'[audit-cross] {e}')
            return jsonify({'status': 'error',
                            'msg': 'Terjadi kesalahan server'}), 500

    @app.route('/api/admin/audit-logs/all/<branch>/<int:log_id>')
    @role_required(['admin'])
    def api_audit_logs_all_detail(branch, log_id):
        if not is_ho_admin():
            return scope_denied_response()
        row, err = _detail(str(branch or '').strip().upper(), log_id)
        if err:
            status = 404 if err == 'Log tidak ditemukan' else 400
            return jsonify({'status': 'error', 'msg': err}), status
        return jsonify(row)
