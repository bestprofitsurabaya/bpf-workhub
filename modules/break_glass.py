"""Break-glass untuk Admin Pusat (v2.117.0 — Fase 3 tata kelola).

Prinsip Pusat: **pengawas read-only + konfigurasi**, bukan approver harian.
Namun ada keadaan darurat (GA cabang tidak bisa masuk, tenggat laporan) yang
menuntut Pusat melakukan aksi sensitif — mis. menghapus transaksi uji yang
salah. Aksi seperti itu tidak boleh menjadi kebiasaan, jadi:

1. **Alasan wajib** (min. 15 karakter) — bukan sekadar klik "ya".
2. **Step-up PIN** — memakai grant `/api/step-up` yang sudah ada.
3. **Token sekali pakai & berumur pendek** — terikat cabang + aksi + target;
   disimpan sebagai hash, bukan token mentah.
4. **Jejak audit** — `break_glass_issue` dan `break_glass_use` masuk
   `activity_logs` cabang, sehingga Admin cabang melihatnya di Log.
5. **Notifikasi in-app** — entri audit bertanda `break_glass_*` adalah
   notifikasi yang terlihat di Log cabang & panel Pusat (email belum
   dikonfigurasi di deploy ini; jangan menjanjikan yang tidak ada).

Tabel dibuat otomatis di DB master (idempoten, aman di setiap startup).
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta

from flask import jsonify, request, session

from modules.admin_scope import is_ho_admin, scope_denied_response
from modules import branch_manager as bm
from modules.config import get_master_connection
from modules.helpers import client_ip, log_activity_async, role_required
from modules.stepup import stepup_required

# Umur grant: cukup untuk satu aksi, terlalu pendek untuk disalahgunakan.
TTL_SECONDS = max(60, min(
    int(os.environ.get('BREAK_GLASS_TTL_SECONDS', '300')), 900))

ALLOWED_ACTIONS = {'delete_tx'}
REASON_MIN = 15
REASON_MAX = 500


def _ensure_table(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS break_glass_grants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                token_hash CHAR(64) NOT NULL,
                branch_code VARCHAR(10) NOT NULL,
                action VARCHAR(30) NOT NULL,
                target_ref VARCHAR(60) NOT NULL,
                reason VARCHAR(500) NOT NULL,
                issued_by VARCHAR(100) NOT NULL,
                issued_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                used_at DATETIME DEFAULT NULL,
                used_by VARCHAR(100) DEFAULT NULL,
                ip VARCHAR(45) DEFAULT NULL,
                KEY idx_bg_token (token_hash),
                KEY idx_bg_issued (issued_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        return True
    finally:
        cur.close()


def _hash(token):
    return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()


def _clean(value, length):
    return str(value or '').strip()[:length]


def issue(branch, action, target, reason, username, ip=None):
    """Terbitkan token sekali pakai. Return (token, row_id, expires_at) / raise."""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(seconds=TTL_SECONDS)
    conn = get_master_connection()
    if not conn:
        raise RuntimeError('DB master tidak tersedia')
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO break_glass_grants (token_hash, branch_code, action, "
                "target_ref, reason, issued_by, issued_at, expires_at, ip) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (_hash(token), branch, action, target, reason, username,
                 now, expires, ip))
            conn.commit()
            return token, cur.lastrowid, expires.strftime('%Y-%m-%d %H:%M:%S')
        finally:
            cur.close()
    finally:
        conn.close()


def consume(token, branch, action, target, username):
    """Pakai token sekali. Return (ok, row_dict|error_message)."""
    if not token:
        return False, 'Token break-glass wajib diisi'
    conn = get_master_connection()
    if not conn:
        return False, 'DB master tidak tersedia'
    try:
        _ensure_table(conn)
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT * FROM break_glass_grants WHERE token_hash=%s LIMIT 1",
                (_hash(token),))
            row = cur.fetchone()
            if not row:
                return False, 'Token break-glass tidak dikenal'
            if row.get('used_at'):
                return False, 'Token break-glass sudah dipakai'
            if str(row.get('expires_at')) < datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                return False, 'Token break-glass kedaluwarsa'
            if (str(row.get('branch_code')).upper() != branch
                    or str(row.get('action')) != action
                    or str(row.get('target_ref')) != target):
                return False, 'Token break-glass tidak cocok dengan aksi/cabang ini'
            cur.execute(
                "UPDATE break_glass_grants SET used_at=NOW(), used_by=%s "
                "WHERE id=%s AND used_at IS NULL", (username, row['id']))
            if cur.rowcount != 1:
                return False, 'Token break-glass sudah dipakai'
            conn.commit()
            row['used_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return True, row
        finally:
            cur.close()
    except Exception as exc:
        # Jangan bocorkan detail driver/SQL ke klien; cukup catat di server.
        print(f'[break-glass] consume: {exc}')
        return False, 'Gagal memakai token'
    finally:
        conn.close()


def _session_name():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def register_break_glass_routes(app):

    @app.route('/api/admin/break-glass', methods=['POST'])
    @role_required(['admin'])
    @stepup_required
    def api_break_glass_issue():
        if not is_ho_admin():
            return scope_denied_response()
        data = request.get_json(silent=True) or {}
        action = _clean(data.get('action'), 30)
        target = _clean(data.get('target'), 60)
        reason = _clean(data.get('reason'), REASON_MAX)
        branch = str(session.get('branch_code') or '').strip().upper()
        if action not in ALLOWED_ACTIONS:
            return jsonify({'status': 'error',
                            'msg': 'Aksi tidak diizinkan lewat break-glass'}), 400
        if not branch:
            return jsonify({'status': 'error',
                            'msg': 'Cabang sesi tidak diketahui'}), 400
        info = bm.get_branch(branch)
        if not info or not info.get('is_active'):
            return jsonify({'status': 'error',
                            'msg': 'Cabang sesi tidak aktif'}), 400
        if not target:
            return jsonify({'status': 'error', 'msg': 'Target aksi wajib'}), 400
        if len(reason) < REASON_MIN:
            return jsonify({'status': 'error',
                            'msg': f'Alasan wajib, minimal {REASON_MIN} karakter'}), 400
        who = _session_name() or 'Admin Pusat'
        try:
            token, grant_id, expires_at = issue(
                branch, action, target, reason, who, ip=client_ip())
        except Exception as exc:
            print(f'[break-glass] issue: {exc}')
            return jsonify({'status': 'error', 'msg': 'Gagal menerbitkan izin'}), 500
        log_activity_async(
            int(target) if target.isdigit() else None,
            'break_glass_issue', 'admin', who,
            new_data={'grant_id': grant_id, 'action': action, 'target': target,
                      'branch': branch, 'reason': reason,
                      'expires_at': expires_at},
            ip=client_ip())
        return jsonify({
            'status': 'success', 'token': token, 'grant_id': grant_id,
            'branch': branch, 'action': action, 'target': target,
            'expires_at': expires_at,
            'msg': f'Izin darurat diterbitkan untuk {branch} (berlaku {TTL_SECONDS} detik)',
        })

    @app.route('/api/admin/break-glass')
    @role_required(['admin'])
    def api_break_glass_list():
        """Riwayat izin darurat terbaru — tampil sebagai konteks di Pusat."""
        if not is_ho_admin():
            return scope_denied_response()
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB master tidak tersedia'}), 500
        try:
            _ensure_table(conn)
            cur = conn.cursor(dictionary=True)
            try:
                cur.execute(
                    "SELECT id, branch_code, action, target_ref, reason, issued_by, "
                    "issued_at, expires_at, used_at, used_by, ip "
                    "FROM break_glass_grants ORDER BY id DESC LIMIT 20")
                rows = cur.fetchall() or []
            finally:
                cur.close()
            for row in rows:
                for key in ('issued_at', 'expires_at', 'used_at'):
                    if row.get(key) is not None:
                        row[key] = str(row[key])
            return jsonify({'grants': rows, 'ttl_seconds': TTL_SECONDS})
        finally:
            conn.close()
