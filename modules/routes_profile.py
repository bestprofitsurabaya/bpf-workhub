"""Profil Saya (v2.81.0) — user mengganti nama tampilan & PIN sendiri.

Berlaku untuk semua role di semua cabang: tiap user hanya bisa mengubah
akunnya sendiri (username/role/cabang tetap urusan Admin). PIN baru wajib
PIN saat ini benar, lolos kebijakan PIN kuat, dan berbeda dari PIN lama;
nilai PIN tidak pernah ditulis ke audit log.
"""
from flask import jsonify, request, session

from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, login_required,
                             validate_new_pin)
from modules.pin_security import stored_pin, verify_pin
from modules.security import rate_limit

NAME_MIN = 2
NAME_MAX = 100


def _clean_name(value):
    """Rapikan spasi ganda/leading-trailing pada nama."""
    return ' '.join(str(value or '').split())


def _public_user(row):
    """Data akun yang aman ditampilkan (tanpa PIN/hash)."""
    return {
        'username': row.get('username'),
        'full_name': row.get('full_name'),
        'role': row.get('role'),
        'branch_code': row.get('branch_code'),
        'branch_name': session.get('branch_name'),
        'last_login': str(row['last_login']) if row.get('last_login') else None,
    }


def _load_user(cursor):
    cursor.execute(
        """SELECT id, username, full_name, role, branch_code, pin, last_login
           FROM users WHERE username=%s""",
        (session.get('user_name'),),
    )
    return cursor.fetchone()


def register_profile_routes(app):
    @app.route('/api/profile')
    @login_required
    def api_profile_get():
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia'}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            row = _load_user(cursor)
            cursor.close()
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if not row:
            return jsonify({'status': 'error', 'msg': 'Akun tidak ditemukan'}), 404
        return jsonify({'user': _public_user(row)})

    @app.route('/api/profile', methods=['PATCH'])
    @login_required
    @rate_limit(limit=10, window=300, scope='profile')
    def api_profile_update():
        # Rate limit mencegah tebak PIN lewat endpoint ini dari satu perangkat.
        data = request.get_json(silent=True) or {}
        change_name = 'full_name' in data
        name = _clean_name(data.get('full_name'))
        current_pin = str(data.get('current_pin') or '').strip()
        new_pin = str(data.get('new_pin') or '').strip()

        if not change_name and not new_pin:
            return jsonify({'status': 'error', 'msg': 'Tidak ada perubahan untuk disimpan'}), 400
        if change_name:
            if len(name) < NAME_MIN:
                return jsonify({'status': 'error', 'msg': f'Nama minimal {NAME_MIN} karakter'}), 400
            if len(name) > NAME_MAX:
                return jsonify({'status': 'error', 'msg': f'Nama maksimal {NAME_MAX} karakter'}), 400
        if new_pin:
            if not current_pin:
                return jsonify({'status': 'error',
                                'msg': 'Masukkan PIN saat ini untuk mengganti PIN'}), 400
            err = validate_new_pin(new_pin)
            if err:
                return jsonify({'status': 'error', 'msg': err}), 400

        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia'}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            row = _load_user(cursor)
            if not row:
                cursor.close()
                return jsonify({'status': 'error', 'msg': 'Akun tidak ditemukan'}), 404
            if new_pin and not verify_pin(row.get('pin'), current_pin):
                cursor.close()
                log_activity_async(None, 'profile_pin_change_failed', session.get('user_role'),
                                   session.get('user_name'), ip=client_ip())
                return jsonify({'status': 'error', 'msg': 'PIN saat ini salah'}), 400
            if new_pin and current_pin == new_pin:
                cursor.close()
                return jsonify({'status': 'error',
                                'msg': 'PIN baru harus berbeda dari PIN saat ini'}), 400

            sets, params, changes = [], [], {}
            if change_name and name != row.get('full_name'):
                sets.append('full_name=%s')
                params.append(name)
                changes['full_name'] = {'from': row.get('full_name'), 'to': name}
            if new_pin:
                sets.append('pin=%s')
                params.append(stored_pin(new_pin))
            if not sets:
                cursor.close()
                return jsonify({'status': 'success', 'msg': 'Tidak ada perubahan',
                                'user': _public_user(row)})

            params.append(row['id'])
            cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=%s", tuple(params))
            conn.commit()

            actor, role = session.get('user_name'), session.get('user_role')
            if changes:
                log_activity_async(None, 'profile_update', role, actor,
                                   old_data={'full_name': row.get('full_name')},
                                   new_data=changes, ip=client_ip())
                session['full_name'] = name
                row['full_name'] = name
            if new_pin:
                # Jangan pernah mencatat PIN (baru maupun lama) di audit log.
                log_activity_async(None, 'profile_pin_change', role, actor,
                                   new_data={'username': row.get('username')},
                                   ip=client_ip())
            cursor.close()
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

        msg = 'Profil diperbarui' if changes and not new_pin else (
            'PIN berhasil diganti' if new_pin and not changes else 'Profil & PIN diperbarui')
        return jsonify({'status': 'success', 'msg': msg, 'user': _public_user(row)})
