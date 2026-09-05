"""Access Review & Laporan Akun Basi (v2.32.0 — Tahap 3/6 ISO/IEC 27001).

Kontrol ISO/IEC 27001:2022:
- A.5.15  Access control — hak akses direview berkala (triwulanan).
- A.8.2   Unique identification — setiap user teridentifikasi unik.
- A.8.3   Termination / revocation of access rights — akun yang tidak
          dipakai lagi harus dinonaktifkan.

Fitur:
1. `GET  /api/admin/access-review` — daftar SEMUA user (master DB) dengan
   klasifikasi status akun:
   - `never_login`  : aktif tapi BELUM PERNAH login (last_login NULL)
   - `stale`        : aktif tapi login terakhir > N hari (default 90,
                      env `STALE_ACCOUNT_DAYS`) — kandidat dinonaktifkan
   - `ok`           : aktif & login dalam N hari terakhir
   - `inactive`     : sudah dinonaktifkan
   + ringkasan jumlah & info review terakhir (system_config).
2. `POST /api/admin/access-review/complete` — tandai review selesai
   (tersimpan: siapa + kapan; audit `access_review_complete`).
3. `GET  /api/admin/access-review/export` — CSV lengkap untuk arsip review
   triwulanan (UTF-8 BOM agar terbuka rapi di Excel).

Admin-only (sesuai A.5.15: review dilakukan pihak berwenang).
"""
import csv
import io as _io
import os
from datetime import datetime, timedelta

from flask import jsonify, make_response, request, session

from modules.config import get_master_connection
from modules.helpers import role_required, log_activity_async, client_ip

# Ambang "akun basi": login terakhir lebih lama dari N hari (default 90).
STALE_ACCOUNT_DAYS = max(30, int(os.environ.get('STALE_ACCOUNT_DAYS', '90')))

REVIEW_AT_KEY = 'access_review_last_at'
REVIEW_BY_KEY = 'access_review_last_by'

ROLE_LABELS = {
    'admin': 'Admin', 'ga': 'GA', 'finance': 'Finance', 'marketing': 'Marketing',
    'chief_driver': 'Chief Driver', 'driver': 'Driver', 'ob': 'OB',
    'receptionist': 'Receptionist', 'traineer': 'Traineer', 'ga_hr': 'GA HR',
    'it_sby': 'IT Surabaya', 'it_hu': 'IT Jakarta HO', 'it_jkt2': 'IT Jakarta 2',
    'it_bdg': 'IT Bandung', 'it_smg': 'IT Semarang', 'it_mlg': 'IT Malang',
    'it_mdn': 'IT Medan', 'it_bjm': 'IT Banjarmasin', 'it_plm': 'IT Palembang',
    'it_lpg': 'IT Lampung',
}


def classify_account(row, stale_days=STALE_ACCOUNT_DAYS):
    """Klasifikasi status akun dari satu baris users (dict).

    Return salah satu dari: 'never_login' | 'stale' | 'ok' | 'inactive'.

    >>> classify_account({'is_active': 0, 'last_login': None})
    'inactive'
    >>> classify_account({'is_active': 1, 'last_login': None})
    'never_login'
    >>> classify_account({'is_active': 1, 'last_login': datetime.now()})
    'ok'
    >>> classify_account({'is_active': 1, 'last_login': datetime.now() - timedelta(days=200)})
    'stale'
    """
    if not row.get('is_active'):
        return 'inactive'
    last = row.get('last_login')
    if last is None:
        return 'never_login'
    try:
        if isinstance(last, str):
            last = datetime.fromisoformat(last.replace('Z', '+00:00'))
        cutoff = datetime.now() - timedelta(days=stale_days)
        # last_login dari DB biasanya naive (Asia/Jakarta) — bandingkan naive.
        if last.tzinfo is not None:
            last = last.replace(tzinfo=None)
        if last < cutoff:
            return 'stale'
    except (TypeError, ValueError):
        # Tanggal tidak terbaca → anggap basi (perlu dicek manual).
        return 'stale'
    return 'ok'


ACCOUNT_STATUS_LABELS = {
    'ok': 'OK', 'stale': 'Basi', 'never_login': 'Belum Pernah Login',
    'inactive': 'Nonaktif',
}


def _fetch_users(conn):
    """Semua user master (kolom yang relevan untuk review)."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, username, full_name, role, team_name, branch_code, "
            "is_active, last_login FROM users ORDER BY is_active DESC, role, username")
        return cur.fetchall()
    finally:
        cur.close()


def _fetch_review_info(conn):
    """Info review terakhir dari system_config."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT config_key, config_value FROM system_config "
            "WHERE config_key IN (%s, %s)", (REVIEW_AT_KEY, REVIEW_BY_KEY))
        info = {}
        for r in cur.fetchall():
            info[r['config_key']] = r['config_value']
        return {
            'last_at': info.get(REVIEW_AT_KEY, ''),
            'last_by': info.get(REVIEW_BY_KEY, ''),
        }
    finally:
        cur.close()


def _build_report(rows):
    """Susun laporan dari daftar user + klasifikasi (murni, tanpa DB)."""
    users = []
    summary = {'total': 0, 'active': 0, 'inactive': 0,
               'ok': 0, 'stale': 0, 'never_login': 0}
    for r in rows:
        status = classify_account(r)
        users.append({
            'id': r['id'],
            'username': r['username'],
            'full_name': r['full_name'],
            'role': r['role'],
            'role_label': ROLE_LABELS.get(r['role'], r['role']),
            'team_name': r.get('team_name') or '',
            'branch_code': r.get('branch_code') or '',
            'is_active': bool(r.get('is_active')),
            'last_login': str(r['last_login']) if r.get('last_login') else '',
            'account_status': status,
            'account_status_label': ACCOUNT_STATUS_LABELS[status],
        })
        summary['total'] += 1
        if status == 'inactive':
            summary['inactive'] += 1
        else:
            summary['active'] += 1
        if status in ('ok', 'stale', 'never_login'):
            summary[status] += 1
    return {'users': users, 'summary': summary}


def _build_csv(report):
    """CSV (UTF-8 BOM) satu baris per user — arsip review triwulanan."""
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Username', 'Nama Lengkap', 'Role', 'Tim', 'Cabang',
                'Status Akun', 'Aktif', 'Terakhir Login'])
    for u in report['users']:
        w.writerow([
            u['username'], u['full_name'], u['role_label'], u['team_name'],
            u['branch_code'], u['account_status_label'],
            'Ya' if u['is_active'] else 'Tidak', u['last_login'],
        ])
    return '\ufeff' + buf.getvalue()


def _session_name():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def register_access_review_routes(app):

    @app.route('/api/admin/access-review')
    @role_required(['admin'])
    def api_access_review():
        """Laporan akses lengkap: user + klasifikasi + ringkasan + review info."""
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
        try:
            rows = _fetch_users(conn)
            review = _fetch_review_info(conn)
            report = _build_report(rows)
            report['review'] = review
            report['stale_days'] = STALE_ACCOUNT_DAYS
            log_activity_async(None, 'access_review_view', 'admin', _session_name(),
                               ip=client_ip())
            return jsonify(report)
        except Exception as e:
            print(f'[access-review] {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500
        finally:
            conn.close()

    @app.route('/api/admin/access-review/complete', methods=['POST'])
    @role_required(['admin'])
    def api_access_review_complete():
        """Tandai review triwulanan selesai — simpan siapa + kapan (audit)."""
        who = _session_name() or 'Admin'
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
        cur = conn.cursor()
        try:
            for key, val in ((REVIEW_AT_KEY, now), (REVIEW_BY_KEY, who)):
                cur.execute(
                    "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (key, val))
            conn.commit()
        except Exception as e:
            print(f'[access-review] complete error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500
        finally:
            cur.close()
            conn.close()
        log_activity_async(None, 'access_review_complete', 'admin', who,
                           new_data={'at': now}, ip=client_ip())
        return jsonify({'status': 'success',
                        'msg': f'Review akses ditandai selesai ({now})',
                        'last_at': now, 'last_by': who})

    @app.route('/api/admin/access-review/export')
    @role_required(['admin'])
    def api_access_review_export():
        """Unduh CSV laporan akses — arsip review triwulanan."""
        conn = get_master_connection()
        if not conn:
            return make_response('DB tidak tersedia', 500)
        try:
            rows = _fetch_users(conn)
            report = _build_report(rows)
            csv_text = _build_csv(report)
            resp = make_response(csv_text)
            resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
            fname = f'AccessReview_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
            resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
            log_activity_async(None, 'access_review_export', 'admin', _session_name(),
                               ip=client_ip())
            return resp
        except Exception as e:
            print(f'[access-review] export error: {e}')
            return make_response('Terjadi kesalahan server', 500)
        finally:
            conn.close()