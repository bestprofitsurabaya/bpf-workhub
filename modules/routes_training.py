"""Endpoint publik absensi training portal (2 hari).

Identitas cukup NIK 16 digit; tanggal lahir tidak lagi diminta. Cabang selalu
berasal dari token `cv_online_branch_forms` — tidak pernah dari input pengguna.
NIK penuh tidak pernah dikirim balik ke browser maupun ke log.
"""
import secrets

from flask import request, jsonify

from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, normalize_nik,
                             redis_rate_hit)
from modules.routes_recruitment import _masked_name
from modules.training_service import (attendance_status, mask_nik,
                                      record_attendance)

_MAX = 20
_WINDOW = 600
_NOT_FOUND = ('Data peserta belum kami temukan. Mohon periksa kembali NIK '
              'Anda, lalu coba lagi.')
_TOKEN_MSG = ('Tautan form tidak valid atau sudah tidak aktif. '
              'Minta tautan terbaru ke Traineer/Admin.')


def _branch_tokens(conn=None):
    """Peta branch_code -> {form_token, active} (tabel boleh belum ada)."""
    own = conn is None
    try:
        if own:
            conn = get_master_connection()
        if not conn:
            return {}
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                'SELECT branch_code, form_token, active '
                'FROM cv_online_branch_forms')
            return {str(r.get('branch_code') or '').upper(): r
                    for r in (cursor.fetchall() or [])}
        finally:
            cursor.close()
    except Exception:
        return {}
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def _token_from(payload=None):
    payload = payload or {}
    for candidate in (request.args.get('token'), request.args.get('t'),
                      payload.get('token'), payload.get('t')):
        if candidate:
            return str(candidate).strip()[:200]
    return ''


def _branch_for_token(supplied):
    """Cabang pemilik token aktif; '' bila token tidak sah/nonaktif."""
    if not supplied:
        return ''
    for code, row in (_branch_tokens() or {}).items():
        stored = str(row.get('form_token') or '')
        if not stored or not row.get('active'):
            continue
        if secrets.compare_digest(str(supplied), stored):
            return code
    return ''


def _rate_ok(ip):
    return redis_rate_hit(f'training|{ip}', _MAX, _WINDOW)


def _audit(action, day, branch, nik, link_status, ip):
    try:
        log_activity_async(
            None, action, 'public', 'portal',
            new_data={'day': day, 'branch_code': branch,
                      'nik_masked': mask_nik(nik), 'link_status': link_status},
            ip=ip)
    except Exception:
        pass  # audit gagal tidak boleh menggagalkan absensi


def _days_json(days):
    return {str(day): value for day, value in (days or {}).items()}


def register_training_routes(app):
    @app.route('/api/recruitment/training/status', methods=['GET'])
    def api_training_status():
        ip = client_ip()
        if not _rate_ok(ip):
            return jsonify({'status': 'error',
                            'msg': 'Terlalu banyak percobaan. Coba lagi nanti.'}), 429
        token = _token_from()
        branch = _branch_for_token(token)
        if not branch:
            return jsonify({'status': 'error', 'msg': _TOKEN_MSG}), 403

        nik, _raw = normalize_nik(request.args.get('nik'))
        if not nik:
            return jsonify({'status': 'error',
                            'msg': 'NIK 16 digit wajib diisi.'}), 400

        result = attendance_status(nik, branch)
        if not result.get('ok'):
            if result.get('error') == 'db':
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            return jsonify({'status': 'error', 'msg': _NOT_FOUND}), 404

        return jsonify({'status': 'success', 'data': {
            'nama': _masked_name(result.get('nama') or ''),
            'days': _days_json(result.get('days')),
            'next_day': result.get('next_day'),
        }})

    @app.route('/api/recruitment/training/attendance', methods=['POST'])
    def api_training_attendance():
        ip = client_ip()
        if not _rate_ok(ip):
            return jsonify({'status': 'error',
                            'msg': 'Terlalu banyak percobaan. Coba lagi nanti.'}), 429
        body = request.get_json(silent=True) or {}
        token = _token_from(body)
        branch = _branch_for_token(token)
        if not branch:
            return jsonify({'status': 'error', 'msg': _TOKEN_MSG}), 403

        if body.get('consent') is not True:
            return jsonify({'status': 'error',
                            'msg': 'Mohon centang pernyataan kebenaran data.'}), 400

        nik, _raw = normalize_nik(body.get('nik'))
        if not nik:
            return jsonify({'status': 'error',
                            'msg': 'NIK 16 digit wajib diisi.'}), 400

        result = record_attendance(
            nik, branch, body.get('day'), ip=ip,
            user_agent=str(request.headers.get('User-Agent') or ''))
        if not result.get('ok'):
            error = result.get('error')
            if error == 'day2_locked':
                return jsonify({'status': 'error',
                                'msg': 'Hari 2 terbuka setelah absensi Hari 1 tercatat.'}), 409
            if error == 'invalid_day':
                return jsonify({'status': 'error',
                                'msg': 'Pilih Hari 1 atau Hari 2.'}), 400
            if error == 'not_found':
                return jsonify({'status': 'error', 'msg': _NOT_FOUND}), 404
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500

        _audit('training_attendance_portal', result.get('day'), branch, nik,
               result.get('link_status'), ip)
        return jsonify({'status': 'success', 'data': {
            'day': result.get('day'),
            'link_status': result.get('link_status'),
            'days': _days_json(result.get('days')),
        }})
