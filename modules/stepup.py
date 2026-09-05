"""Step-up authentication (v2.31) — ISO/IEC 27001 A.8.2/A.8.3/A.8.5.

Aksi berisiko yang menggerakkan uang (approve/pay kasbon, payout klaim BBM,
verifikasi pengajuan air minum) WAJIB didahului verifikasi PIN ulang user yang
sedang login (step-up). Ini menutup celah "sesi menyala di komputer bersama"
dan memperkuat faktor tunggal PIN 6 digit dengan peristiwa autentikasi kedua
yang dekat waktunya dengan aksi (A.8.5 secure authentication).

Alur:
1. SPA memanggil aksi berisiko → backend menjawab 428 `STEPUP_REQUIRED`
   bila sesi tidak punya grant step-up yang masih berlaku.
2. SPA membuka modal PIN → POST /api/step-up (PIN user SENDIRI — username
   diambil dari sesi, TIDAK dari body — anti verifikasi PIN orang lain).
3. PIN valid (rate-limited anti brute-force, sama seperti login) → backend
   menerbitkan grant sesi berumur pendek (`stepup_until`).
4. Aksi berisiko berikutnya dalam masa berlaku grant lolos tanpa PIN ulang;
   grant hilang saat logout (session.clear) atau kedaluwarsa.

Masa berlaku grant bisa diatur via env `STEPUP_TTL_SECONDS` (default 600 =
10 menit): cukup untuk batch approve, terlalu pendek untuk dieksploitasi bila
sesi diretas.
"""
import os
import time
from functools import wraps

from flask import jsonify, request, session

from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, pin_fail,
                             pin_rate_check, pin_success)

# Masa berlaku grant step-up (detik). Minimum 60 detik — nilai di bawah itu
# tidak masuk akal untuk kerja nyata dan hanya menambah gesekan.
STEPUP_TTL = max(60, int(os.environ.get('STEPUP_TTL_SECONDS', '600')))

STEPUP_REQUIRED_MSG = 'Verifikasi PIN ulang diperlukan untuk aksi ini.'
STEPUP_REQUIRED_CODE = 'STEPUP_REQUIRED'


def stepup_expiry():
    """Sisa detik grant step-up sesi aktif (0 bila tidak ada / kedaluwarsa)."""
    until = session.get('stepup_until')
    if not until:
        return 0
    left = float(until) - time.time()
    return int(left) if left > 0 else 0


def grant_stepup():
    """Terbitkan grant step-up untuk sesi ini (dipanggil setelah PIN valid)."""
    session['stepup_until'] = time.time() + STEPUP_TTL
    session['stepup_granted_at'] = time.time()


def clear_stepup():
    """Cabut grant step-up (dipakai saat logout / sesi dibersihkan)."""
    session.pop('stepup_until', None)
    session.pop('stepup_granted_at', None)


def stepup_required(fn):
    """Decorator: tolak aksi berisiko tanpa grant step-up yang masih berlaku.

    Menjawab 428 (status resmi "Precondition Required") dengan
    `code='STEPUP_REQUIRED'` — SPA menangkapnya untuk membuka modal PIN.
    Dipasang DI BAWAH `@role_required` (cek role dulu, lalu step-up).
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_role'):
            return jsonify({'status': 'error', 'msg': 'Login diperlukan.'}), 401
        if stepup_expiry() <= 0:
            return jsonify({'status': 'error', 'msg': STEPUP_REQUIRED_MSG,
                            'code': STEPUP_REQUIRED_CODE}), 428
        return fn(*args, **kwargs)
    return wrapper


def register_stepup_routes(app):

    @app.route('/api/step-up', methods=['POST'])
    def api_stepup():
        """Verifikasi PIN ulang user yang SEDANG LOGIN (step-up).

        Username diambil dari sesi — body hanya membawa PIN. Dengan begitu,
        pemegang sesi tidak bisa memverifikasi PIN orang lain, dan PIN user
        tidak pernah keluar ke body selain yang dibutuhkan.
        """
        username = session.get('user_name')
        role = session.get('user_role')
        if not username or not role:
            return jsonify({'status': 'error', 'msg': 'Login diperlukan.'}), 401

        data = request.get_json(silent=True) or {}
        pin = str(data.get('pin', '') or '').strip()
        if not pin:
            return jsonify({'status': 'error', 'msg': 'PIN wajib diisi'}), 400

        ip = client_ip()
        allowed, retry_after = pin_rate_check(ip)
        if not allowed:
            return jsonify({'status': 'error',
                            'msg': f'Terlalu banyak percobaan. Coba lagi dalam {retry_after // 60} menit.'}), 429

        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia'}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            # PIN dibandingkan untuk username SESI — bukan sembarang username.
            cursor.execute("SELECT id FROM users WHERE username=%s AND pin=%s AND is_active=TRUE",
                           (username, pin))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f'[stepup] db error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500

        if not user:
            pin_fail(ip)
            return jsonify({'status': 'error', 'msg': 'PIN salah'}), 401

        pin_success(ip)
        grant_stepup()
        log_activity_async(None, 'step_up', role, username, ip=request.remote_addr)
        return jsonify({'status': 'success',
                        'msg': 'Verifikasi PIN berhasil',
                        'expires_in': STEPUP_TTL})