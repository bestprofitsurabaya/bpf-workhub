"""Endpoint MFA TOTP (v2.112.0).

Dua kelompok endpoint:

1. Login dua langkah (sesi *pending* — belum punya `user_role`):
       POST /api/auth/mfa/verify
       POST /api/auth/mfa/enroll/start
       POST /api/auth/mfa/enroll/confirm
   Endpoint ini otomatis lolos middleware CSRF karena sesi pending belum punya
   `user_role` (perilaku sama seperti /api/auth/login).

2. Setelah login (sesi penuh):
       GET  /api/auth/mfa/status
       POST /api/auth/mfa/setup/start        (step-up PIN)
       POST /api/auth/mfa/setup/confirm      (step-up PIN)
       POST /api/auth/mfa/disable            (step-up PIN)
       POST /api/auth/mfa/recovery/regenerate(step-up PIN)

3. Admin:
       GET  /api/security/mfa/settings
       PUT  /api/security/mfa/settings       (step-up PIN)
       POST /api/security/mfa/users/<username>/reset (step-up PIN)

Semua kejadian penting dicatat ke activity_logs (ISO/IEC 27001 A.8.15/A.8.16).
"""
import time

from flask import jsonify, request, session

from modules import mfa as core
from modules.config import get_master_connection
from modules.helpers import (client_ip, home_for_role, log_activity_async,
                             login_required, mfa_fail, mfa_rate_check,
                             mfa_success, role_required)
from modules.stepup import stepup_required

PENDING_MAX_AGE = 600          # 10 menit untuk menyelesaikan langkah kedua
_PENDING_PREFIX = 'mfa_pending_'

_USER_FIELDS = ("id, username, full_name, role, branch_code, is_active, "
                "mfa_enabled, mfa_secret, mfa_enrolled_at, mfa_last_step")


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def _csrf():
    tok = session.get('csrf_token')
    if not tok:
        import secrets
        tok = secrets.token_hex(16)
        session['csrf_token'] = tok
    return tok


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _pending():
    username = session.get(_PENDING_PREFIX + 'user')
    if not username:
        return None
    return {
        'username': username,
        'uid': session.get(_PENDING_PREFIX + 'uid'),
        'role': session.get(_PENDING_PREFIX + 'role'),
        'branch_code': session.get(_PENDING_PREFIX + 'branch'),
        'branch_name': session.get(_PENDING_PREFIX + 'branch_name'),
        'at': float(session.get(_PENDING_PREFIX + 'at') or 0),
        'mode': session.get(_PENDING_PREFIX + 'mode') or 'verify',
    }


def _clear_pending():
    for key in list(session.keys()):
        if key.startswith(_PENDING_PREFIX) or key == 'mfa_setup_secret':
            session.pop(key, None)


def _fetch_user(uid):
    """Ambil satu user + koneksi master (caller wajib menutup koneksi)."""
    conn = get_master_connection()
    if not conn:
        return None, None
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"SELECT {_USER_FIELDS} FROM users WHERE id=%s", (uid,))
        return cur.fetchone(), conn
    except Exception as exc:
        print(f'[mfa] ambil user gagal: {exc}')
        try:
            conn.close()
        except Exception:
            pass
        return None, None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _fetch_user_by_name(username):
    conn = get_master_connection()
    if not conn:
        return None, None
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"SELECT {_USER_FIELDS} FROM users WHERE username=%s", (username,))
        return cur.fetchone(), conn
    except Exception as exc:
        print(f'[mfa] ambil user gagal: {exc}')
        try:
            conn.close()
        except Exception:
            pass
        return None, None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _issue_recovery_codes(cur, user_id):
    """Ganti semua kode pemulihan user dengan 10 kode baru (hash SHA-256)."""
    cur.execute("DELETE FROM mfa_recovery_codes WHERE user_id=%s", (user_id,))
    codes = core.generate_recovery_codes()
    for code in codes:
        cur.execute(
            "INSERT INTO mfa_recovery_codes (user_id, code_hash) VALUES (%s, %s)",
            (user_id, core.hash_recovery(code)))
    return codes


def _consume_recovery_code(cur, user_id, code):
    """Pakai satu kode pemulihan. Return True bila valid (sekali pakai)."""
    import hmac
    digest = core.hash_recovery(code)
    cur.execute(
        "SELECT id, code_hash FROM mfa_recovery_codes "
        "WHERE user_id=%s AND used_at IS NULL", (user_id,))
    for row in cur.fetchall() or []:
        if hmac.compare_digest(str(row.get('code_hash') or ''), digest):
            cur.execute(
                "UPDATE mfa_recovery_codes SET used_at=NOW() WHERE id=%s",
                (row['id'],))
            return True
    return False


def _recovery_left(cur, user_id):
    try:
        cur.execute(
            "SELECT COUNT(*) AS n FROM mfa_recovery_codes "
            "WHERE user_id=%s AND used_at IS NULL", (user_id,))
        row = cur.fetchone() or {}
        return int(row.get('n') or 0)
    except Exception:
        return 0


def _post_login_sync(user):
    """Sinkronisasi sheet background — sama seperti login normal."""
    try:
        from modules.routes_overtime import (trigger_driver_refresh_async,
                                             trigger_ob_refresh_async)
        trigger_driver_refresh_async(user.get('role'), user.get('full_name'),
                                     ip=client_ip())
        trigger_ob_refresh_async(user.get('role'), user.get('full_name'),
                                 ip=client_ip())
    except Exception:
        pass
    try:
        from modules.routes_receptionist import trigger_receptionist_sync_async
        trigger_receptionist_sync_async(user.get('role'), user.get('full_name'),
                                        ip=client_ip())
    except Exception:
        pass


def _establish_session(user, branch_code, branch_name):
    """Buat sesi penuh setelah MFA berhasil. Return (csrf, is_ho)."""
    session.clear()
    session['user_role'] = user['role']
    session['user_name'] = user['username']
    session['full_name'] = user['full_name']
    session['branch_code'] = branch_code
    session['branch_name'] = branch_name
    session.permanent = True
    csrf = _csrf()
    is_ho = False
    try:
        from modules.admin_scope import is_ho_admin as _is_ho
        is_ho = bool(_is_ho())
    except Exception:
        is_ho = user.get('role') == 'admin'
    return csrf, is_ho


def _login_payload(user, branch_code, branch_name, extra=None):
    csrf, is_ho = _establish_session(user, branch_code, branch_name)
    _post_login_sync(user)
    payload = {
        'status': 'success',
        'user': {
            'role': user['role'],
            'user_name': user['username'],
            'full_name': user['full_name'],
            'branch_code': branch_code,
            'branch_name': branch_name,
            'is_ho_admin': is_ho,
        },
        'csrf_token': csrf,
        'home': home_for_role(user['role']),
    }
    if extra:
        payload.update(extra)
    return payload


def _audit(action, user_name, new_data=None, ip=None):
    try:
        log_activity_async(None, action, 'user', user_name,
                           new_data=new_data, ip=ip or client_ip())
    except Exception:
        pass


def _rate_username():
    pend = _pending()
    return pend['username'] if pend else (session.get('user_name') or '')


def _rate_blocked():
    allowed, retry_after = mfa_rate_check(client_ip(), _rate_username())
    if allowed:
        return None
    return jsonify({
        'status': 'error',
        'code': 'MFA_RATE_LIMITED',
        'msg': f'Terlalu banyak percobaan kode. Coba lagi dalam '
               f'{max(1, retry_after // 60)} menit.',
    }), 429


# ---------------------------------------------------------------------------
# Registrasi route
# ---------------------------------------------------------------------------
def register_mfa_routes(app):

    # ===================== LOGIN DUA LANGKAH =====================
    @app.route('/api/auth/mfa/verify', methods=['POST'])
    def api_mfa_verify():
        pend = _pending()
        if not pend:
            return jsonify({'status': 'error',
                            'msg': 'Tidak ada proses MFA aktif. Silakan login ulang.'}), 401
        if time.time() - pend['at'] > PENDING_MAX_AGE:
            _clear_pending()
            return jsonify({'status': 'error', 'code': 'MFA_EXPIRED',
                            'msg': 'Waktu verifikasi habis. Silakan login ulang.'}), 401

        blocked = _rate_blocked()
        if blocked:
            return blocked

        data = _body()
        code = str(data.get('code') or '').strip()
        recovery = str(data.get('recovery_code') or '').strip()
        if not code and not recovery:
            return jsonify({'status': 'error', 'msg': 'Kode verifikasi wajib diisi.'}), 400

        user, conn = _fetch_user(pend['uid'])
        if not user or not user.get('is_active'):
            _clear_pending()
            return jsonify({'status': 'error',
                            'msg': 'Akun tidak aktif. Hubungi Admin.'}), 403
        if not user.get('mfa_enabled') or not user.get('mfa_secret'):
            _clear_pending()
            return jsonify({'status': 'error', 'code': 'MFA_NOT_ENROLLED',
                            'msg': 'MFA belum aktif untuk akun ini. Silakan login ulang.'}), 409

        cur = conn.cursor(dictionary=True)
        ok = False
        used_recovery = False
        try:
            if recovery:
                ok = _consume_recovery_code(cur, user['id'], recovery)
                used_recovery = ok
            else:
                secret = core.decrypt_secret(user.get('mfa_secret'))
                if not secret:
                    _clear_pending()
                    try:
                        conn.close()
                    except Exception:
                        pass
                    return jsonify({'status': 'error', 'code': 'MFA_SECRET_INVALID',
                                    'msg': 'Data MFA rusak. Minta Admin mereset MFA akun Anda.'}), 409
                step = core.match_step(secret, code, last_step=user.get('mfa_last_step'))
                if step is not None:
                    cur.execute("UPDATE users SET mfa_last_step=%s WHERE id=%s",
                                (step, user['id']))
                    ok = True
            if ok:
                conn.commit()
            else:
                conn.rollback()
        except Exception as exc:
            print(f'[mfa] verifikasi gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error', 'msg': 'Verifikasi gagal. Coba lagi.'}), 500
        finally:
            try:
                cur.close()
            except Exception:
                pass

        if not ok:
            try:
                conn.close()
            except Exception:
                pass
            mfa_fail(client_ip(), pend['username'])
            _audit('mfa_verify_failed', pend['username'],
                   {'via': 'recovery' if recovery else 'totp'})
            return jsonify({'status': 'error', 'code': 'MFA_INVALID',
                            'msg': 'Kode salah atau sudah kedaluwarsa.'}), 401

        mfa_success(client_ip(), pend['username'])
        branch_code = pend.get('branch_code') or user.get('branch_code')
        branch_name = pend.get('branch_name') or ''
        # Validasi ulang cabang (bisa saja dinonaktifkan saat proses MFA).
        try:
            from modules.branch_manager import get_branch, DEFAULT_BRANCH_CODE
            branch = get_branch(branch_code or DEFAULT_BRANCH_CODE)
            if not branch or not branch.get('is_active'):
                _clear_pending()
                return jsonify({'status': 'error',
                                'msg': 'Cabang tidak aktif. Hubungi Admin.'}), 403
            branch_code, branch_name = branch['code'], branch['name']
        except Exception:
            pass

        _clear_pending()
        payload = _login_payload(user, branch_code, branch_name,
                                 {'mfa': True, 'recovery_used': used_recovery})
        if used_recovery:
            try:
                conn2 = get_master_connection()
                cur2 = conn2.cursor(dictionary=True)
                payload['recovery_left'] = _recovery_left(cur2, user['id'])
                cur2.close()
                conn2.close()
            except Exception:
                pass
        _audit('login', pend['username'], {'mfa': True, 'via': 'recovery' if used_recovery else 'totp'})
        try:
            conn.close()
        except Exception:
            pass
        return jsonify(payload)

    @app.route('/api/auth/mfa/enroll/start', methods=['POST'])
    def api_mfa_enroll_start():
        pend = _pending()
        if not pend:
            return jsonify({'status': 'error',
                            'msg': 'Tidak ada proses MFA aktif. Silakan login ulang.'}), 401
        if time.time() - pend['at'] > PENDING_MAX_AGE:
            _clear_pending()
            return jsonify({'status': 'error', 'code': 'MFA_EXPIRED',
                            'msg': 'Waktu pendaftaran habis. Silakan login ulang.'}), 401
        secret = core.generate_secret()
        session['mfa_pending_secret'] = core.encrypt_secret(secret)
        uri = core.otpauth_uri(secret, pend['username'])
        return jsonify({
            'status': 'success',
            'secret': secret,
            'otpauth_uri': uri,
            'qr': core.qr_svg_data_uri(uri),
            'issuer': core.ISSUER,
            'account': pend['username'],
            'digits': core.DIGITS,
            'period': core.PERIOD,
            'recovery_count': core.RECOVERY_COUNT,
        })

    @app.route('/api/auth/mfa/enroll/confirm', methods=['POST'])
    def api_mfa_enroll_confirm():
        pend = _pending()
        if not pend:
            return jsonify({'status': 'error',
                            'msg': 'Tidak ada proses MFA aktif. Silakan login ulang.'}), 401
        if time.time() - pend['at'] > PENDING_MAX_AGE:
            _clear_pending()
            return jsonify({'status': 'error', 'code': 'MFA_EXPIRED',
                            'msg': 'Waktu pendaftaran habis. Silakan login ulang.'}), 401

        blocked = _rate_blocked()
        if blocked:
            return blocked

        blob = session.get('mfa_pending_secret')
        secret = core.decrypt_secret(blob)
        if not secret:
            return jsonify({'status': 'error', 'code': 'MFA_ENROLL_RESTART',
                            'msg': 'Sesi pendaftaran tidak ditemukan. Muat ulang halaman.'}), 400

        code = str(_body().get('code') or '').strip()
        step = core.match_step(secret, code)
        if step is None:
            mfa_fail(client_ip(), pend['username'])
            return jsonify({'status': 'error', 'code': 'MFA_INVALID',
                            'msg': 'Kode salah. Pastikan jam ponsel otomatis dan '
                                   'masukkan kode terbaru.'}), 401

        user, conn = _fetch_user(pend['uid'])
        if not user or not user.get('is_active'):
            _clear_pending()
            return jsonify({'status': 'error', 'msg': 'Akun tidak aktif.'}), 403

        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "UPDATE users SET mfa_enabled=1, mfa_secret=%s, "
                "mfa_enrolled_at=NOW(), mfa_last_step=%s WHERE id=%s",
                (core.encrypt_secret(secret), step, user['id']))
            codes = _issue_recovery_codes(cur, user['id'])
            conn.commit()
        except Exception as exc:
            print(f'[mfa] simpan pendaftaran gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error',
                            'msg': 'Gagal menyimpan pendaftaran MFA.'}), 500
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        mfa_success(client_ip(), pend['username'])
        branch_code = pend.get('branch_code') or user.get('branch_code')
        branch_name = pend.get('branch_name') or ''
        _clear_pending()
        payload = _login_payload(user, branch_code, branch_name,
                                 {'mfa': True, 'enrolled': True,
                                  'recovery_codes': codes})
        _audit('mfa_enroll', pend['username'], {'role': user.get('role')})
        _audit('login', pend['username'], {'mfa': True, 'enrolled': True})
        return jsonify(payload)

    # ===================== STATUS & SELF-SERVICE =====================
    @app.route('/api/auth/mfa/status')
    @login_required
    def api_mfa_status():
        user, conn = _fetch_user_by_name(session.get('user_name'))
        if not user:
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan.'}), 404
        pol = core.policy_from_db(conn)
        req = core.requirement_for_user(user, pol)
        cur = conn.cursor(dictionary=True)
        left = _recovery_left(cur, user['id'])
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
        return jsonify({
            'status': 'success',
            'enabled': bool(user.get('mfa_enabled')),
            'enrolled_at': user.get('mfa_enrolled_at'),
            'policy': pol['policy'],
            'policy_label': core.POLICY_LABELS.get(pol['policy'], pol['policy']),
            'required_for_me': bool(req.get('role_required')),
            'can_disable': not (pol['policy'] == core.POLICY_REQUIRED
                                and req.get('role_required')),
            'recovery_left': left,
            'grace_days_left': req.get('grace_days_left', 0),
            'issuer': core.ISSUER,
            'digits': core.DIGITS,
            'period': core.PERIOD,
            'recovery_count': core.RECOVERY_COUNT,
        })

    @app.route('/api/auth/mfa/setup/start', methods=['POST'])
    @login_required
    @stepup_required
    def api_mfa_setup_start():
        username = session.get('user_name')
        secret = core.generate_secret()
        session['mfa_setup_secret'] = core.encrypt_secret(secret)
        uri = core.otpauth_uri(secret, username)
        return jsonify({
            'status': 'success',
            'secret': secret,
            'otpauth_uri': uri,
            'qr': core.qr_svg_data_uri(uri),
            'issuer': core.ISSUER,
            'account': username,
            'digits': core.DIGITS,
            'period': core.PERIOD,
            'recovery_count': core.RECOVERY_COUNT,
        })

    @app.route('/api/auth/mfa/setup/confirm', methods=['POST'])
    @login_required
    @stepup_required
    def api_mfa_setup_confirm():
        username = session.get('user_name')
        secret = core.decrypt_secret(session.get('mfa_setup_secret'))
        if not secret:
            return jsonify({'status': 'error', 'code': 'MFA_ENROLL_RESTART',
                            'msg': 'Sesi pendaftaran tidak ditemukan. Ulangi.'}), 400
        blocked = _rate_blocked()
        if blocked:
            return blocked
        code = str(_body().get('code') or '').strip()
        step = core.match_step(secret, code)
        if step is None:
            mfa_fail(client_ip(), username)
            return jsonify({'status': 'error', 'code': 'MFA_INVALID',
                            'msg': 'Kode salah. Masukkan kode terbaru dari aplikasi.'}), 401

        user, conn = _fetch_user_by_name(username)
        if not user:
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan.'}), 404
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "UPDATE users SET mfa_enabled=1, mfa_secret=%s, "
                "mfa_enrolled_at=NOW(), mfa_last_step=%s WHERE id=%s",
                (core.encrypt_secret(secret), step, user['id']))
            codes = _issue_recovery_codes(cur, user['id'])
            conn.commit()
        except Exception as exc:
            print(f'[mfa] simpan setup gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error', 'msg': 'Gagal menyimpan MFA.'}), 500
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass
        session.pop('mfa_setup_secret', None)
        mfa_success(client_ip(), username)
        _audit('mfa_enroll', username, {'via': 'profile'})
        return jsonify({'status': 'success', 'recovery_codes': codes,
                        'recovery_count': len(codes)})

    @app.route('/api/auth/mfa/disable', methods=['POST'])
    @login_required
    @stepup_required
    def api_mfa_disable():
        username = session.get('user_name')
        user, conn = _fetch_user_by_name(username)
        if not user:
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan.'}), 404
        pol = core.policy_from_db(conn)
        req = core.requirement_for_user(user, pol)
        if pol['policy'] == core.POLICY_REQUIRED and req.get('role_required'):
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({'status': 'error', 'code': 'MFA_REQUIRED_POLICY',
                            'msg': 'MFA diwajibkan untuk role Anda oleh Admin, '
                                   'tidak dapat dinonaktifkan sendiri.'}), 403

        blocked = _rate_blocked()
        if blocked:
            try:
                conn.close()
            except Exception:
                pass
            return blocked

        data = _body()
        code = str(data.get('code') or '').strip()
        recovery = str(data.get('recovery_code') or '').strip()
        cur = conn.cursor(dictionary=True)
        ok = False
        try:
            if recovery:
                ok = _consume_recovery_code(cur, user['id'], recovery)
            else:
                secret = core.decrypt_secret(user.get('mfa_secret'))
                ok = core.match_step(secret, code) is not None if secret else False
            if ok:
                cur.execute(
                    "UPDATE users SET mfa_enabled=0, mfa_secret=NULL, "
                    "mfa_enrolled_at=NULL, mfa_last_step=NULL WHERE id=%s",
                    (user['id'],))
                cur.execute("DELETE FROM mfa_recovery_codes WHERE user_id=%s",
                            (user['id'],))
                conn.commit()
            else:
                conn.rollback()
        except Exception as exc:
            print(f'[mfa] nonaktifkan gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

        if not ok:
            mfa_fail(client_ip(), username)
            return jsonify({'status': 'error', 'code': 'MFA_INVALID',
                            'msg': 'Kode salah. MFA tidak dinonaktifkan.'}), 401
        mfa_success(client_ip(), username)
        _audit('mfa_disable', username)
        return jsonify({'status': 'success', 'msg': 'MFA berhasil dinonaktifkan.'})

    @app.route('/api/auth/mfa/recovery/regenerate', methods=['POST'])
    @login_required
    @stepup_required
    def api_mfa_recovery_regenerate():
        username = session.get('user_name')
        user, conn = _fetch_user_by_name(username)
        if not user:
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan.'}), 404
        if not user.get('mfa_enabled') or not user.get('mfa_secret'):
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({'status': 'error',
                            'msg': 'MFA belum aktif untuk akun ini.'}), 400

        blocked = _rate_blocked()
        if blocked:
            try:
                conn.close()
            except Exception:
                pass
            return blocked

        code = str(_body().get('code') or '').strip()
        secret = core.decrypt_secret(user.get('mfa_secret'))
        if not secret or core.match_step(secret, code, last_step=user.get('mfa_last_step')) is None:
            try:
                conn.close()
            except Exception:
                pass
            mfa_fail(client_ip(), username)
            return jsonify({'status': 'error', 'code': 'MFA_INVALID',
                            'msg': 'Kode salah.'}), 401

        cur = conn.cursor(dictionary=True)
        try:
            codes = _issue_recovery_codes(cur, user['id'])
            conn.commit()
        except Exception as exc:
            print(f'[mfa] regenerate gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error',
                            'msg': 'Gagal membuat kode pemulihan baru.'}), 500
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass
        _audit('mfa_recovery_regenerate', username)
        return jsonify({'status': 'success', 'recovery_codes': codes,
                        'recovery_count': len(codes)})

    # ===================== ADMIN =====================
    @app.route('/api/security/mfa/settings', methods=['GET'])
    @role_required(['admin'])
    def api_mfa_settings_get():
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia.'}), 500
        pol = core.policy_from_db(conn)
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT role, COUNT(*) AS total, "
                "SUM(CASE WHEN mfa_enabled=1 THEN 1 ELSE 0 END) AS enrolled "
                "FROM users WHERE is_active=TRUE GROUP BY role ORDER BY role")
            roles = cur.fetchall() or []
            cur.execute(
                "SELECT username, full_name, role, branch_code, is_active, "
                "mfa_enabled, mfa_enrolled_at FROM users "
                "ORDER BY role, username LIMIT 1000")
            users = cur.fetchall() or []
            cur.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN mfa_enabled=1 THEN 1 ELSE 0 END) AS enrolled "
                "FROM users WHERE is_active=TRUE")
            totals = cur.fetchone() or {}
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

        # Role yang dikenal kode + role yang benar-benar ada di DB.
        known = list(core.KNOWN_ROLES)
        for row in roles:
            role = row.get('role')
            if role and role not in known:
                known.append(role)
        required = set(pol['required_roles'])
        return jsonify({
            'status': 'success',
            'policy': pol['policy'],
            'policy_label': core.POLICY_LABELS.get(pol['policy'], pol['policy']),
            'policies': [{'value': p, 'label': core.POLICY_LABELS[p]}
                         for p in core.POLICIES],
            'required_roles': sorted(required),
            'grace_days': pol['grace_days'],
            'grace_days_left': round(core.grace_days_left(pol), 1),
            'enforced_at': pol['enforced_at'].strftime('%Y-%m-%d %H:%M:%S')
                           if pol.get('enforced_at') else None,
            'excluded_roles': list(core.EXCLUDED_ROLES),
            'roles': [{'role': r.get('role'),
                       'total': int(r.get('total') or 0),
                       'enrolled': int(r.get('enrolled') or 0),
                       'required': r.get('role') in required} for r in roles],
            'known_roles': known,
            'users': [{'username': u.get('username'),
                       'full_name': u.get('full_name'),
                       'role': u.get('role'),
                       'branch_code': u.get('branch_code'),
                       'is_active': bool(u.get('is_active')),
                       'mfa_enabled': bool(u.get('mfa_enabled')),
                       'mfa_enrolled_at': (u.get('mfa_enrolled_at').strftime('%Y-%m-%d %H:%M:%S')
                                           if u.get('mfa_enrolled_at') else None)}
                      for u in users],
            'stats': {'total': int(totals.get('total') or 0),
                      'enrolled': int(totals.get('enrolled') or 0)},
        })

    @app.route('/api/security/mfa/settings', methods=['PUT'])
    @role_required(['admin'])
    @stepup_required
    def api_mfa_settings_put():
        data = _body()
        policy = str(data.get('policy') or '').strip().lower()
        if policy not in core.POLICIES:
            return jsonify({'status': 'error',
                            'msg': 'Kebijakan tidak dikenal.'}), 400
        roles = core.parse_roles(data.get('required_roles'))
        try:
            grace = int(data.get('grace_days'))
        except Exception:
            grace = None
        if grace is None or grace < 0 or grace > 365:
            return jsonify({'status': 'error',
                            'msg': 'Masa tenggang harus 0–365 hari.'}), 400

        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia.'}), 500
        old = core.policy_from_db(conn)
        cur = conn.cursor()
        try:
            values = {
                'mfa_policy': policy,
                'mfa_required_roles': ','.join(roles),
                'mfa_grace_days': str(grace),
            }
            for key, value in values.items():
                cur.execute(
                    "INSERT INTO system_config (config_key, config_value) "
                    "VALUES (%s, %s) ON DUPLICATE KEY UPDATE "
                    "config_value=VALUES(config_value)", (key, value))
            # Mulai ulang masa tenggang bila kebijakan/daftar role berubah.
            changed = (old['policy'] != policy
                       or set(old['required_roles']) != set(roles))
            if policy == core.POLICY_REQUIRED and changed:
                cur.execute(
                    "INSERT INTO system_config (config_key, config_value) "
                    "VALUES ('mfa_enforced_at', NOW()) ON DUPLICATE KEY UPDATE "
                    "config_value=VALUES(config_value)")
            conn.commit()
        except Exception as exc:
            print(f'[mfa] simpan kebijakan gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error',
                            'msg': 'Gagal menyimpan kebijakan MFA.'}), 500
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

        _audit('mfa_policy_change', session.get('user_name'),
               {'old': {'policy': old['policy'],
                        'required_roles': old['required_roles'],
                        'grace_days': old['grace_days']},
                'new': {'policy': policy, 'required_roles': roles,
                        'grace_days': grace}})
        return jsonify({'status': 'success',
                        'msg': 'Kebijakan MFA disimpan.',
                        'policy': policy,
                        'required_roles': roles,
                        'grace_days': grace})

    @app.route('/api/security/mfa/users/<username>/reset', methods=['POST'])
    @role_required(['admin'])
    @stepup_required
    def api_mfa_user_reset(username):
        user, conn = _fetch_user_by_name(username)
        if not user:
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan.'}), 404
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE users SET mfa_enabled=0, mfa_secret=NULL, "
                "mfa_enrolled_at=NULL, mfa_last_step=NULL WHERE id=%s",
                (user['id'],))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE user_id=%s",
                        (user['id'],))
            conn.commit()
        except Exception as exc:
            print(f'[mfa] reset user gagal: {exc}')
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error',
                            'msg': 'Gagal mereset MFA user.'}), 500
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass
        _audit('mfa_reset', username,
               {'by': session.get('user_name'), 'role': user.get('role')})
        return jsonify({'status': 'success',
                        'msg': f"MFA {username} direset. User akan mendaftar ulang saat login."})
