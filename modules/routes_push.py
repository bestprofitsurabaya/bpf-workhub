"""API Web Push driver (v2.128.0).

Endpoint:
- GET  /api/push/public-key  → kunci publik VAPID (frontend subscribe)
- POST /api/push/subscribe   → simpan/refresh langganan perangkat driver
- POST /api/push/unsubscribe → hapus langganan perangkat ini
- GET  /api/push/status      → jumlah perangkat terdaftar untuk driver
"""
from flask import request, jsonify

from modules.config import get_db_connection
from modules.helpers import session_driver_name
from modules import webpush


def register_push_routes(app):

    @app.route('/api/push/public-key')
    def api_push_public_key():
        if not webpush.push_available():
            return jsonify({'enabled': False, 'reason': 'Web Push belum tersedia di server.'})
        try:
            return jsonify({
                'enabled': True,
                'public_key': webpush.get_vapid_public_key(),
                'subject': webpush.SUBJECT,
            })
        except Exception as e:
            return jsonify({'enabled': False, 'reason': str(e)}), 500

    @app.route('/api/push/subscribe', methods=['POST'])
    def api_push_subscribe():
        driver = session_driver_name()
        if not driver:
            return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
        if not webpush.push_available():
            return jsonify({'status': 'error', 'msg': 'Web Push belum tersedia di server.'}), 503
        sub = webpush.subscription_from_payload(request.get_json(silent=True) or {})
        if not sub:
            return jsonify({'status': 'error', 'msg': 'Data langganan push tidak valid.'}), 400
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            ok = webpush.save_subscription(
                driver, sub, user_agent=request.headers.get('User-Agent', ''), conn=conn)
            if not ok:
                return jsonify({'status': 'error', 'msg': 'Gagal menyimpan langganan.'}), 500
            count = webpush.count_subscriptions(driver, conn=conn)
            return jsonify({'status': 'success', 'devices': count,
                            'msg': 'Notifikasi HP aktif di perangkat ini.'})
        finally:
            try: conn.close()
            except Exception: pass

    @app.route('/api/push/unsubscribe', methods=['POST'])
    def api_push_unsubscribe():
        driver = session_driver_name()
        if not driver:
            return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
        data = request.get_json(silent=True) or {}
        endpoint = str(data.get('endpoint') or '').strip()
        if not endpoint:
            return jsonify({'status': 'error', 'msg': 'Endpoint langganan wajib.'}), 400
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            removed = webpush.delete_subscription(driver, endpoint, conn=conn)
            count = webpush.count_subscriptions(driver, conn=conn)
            return jsonify({'status': 'success', 'removed': removed, 'devices': count})
        finally:
            try: conn.close()
            except Exception: pass

    @app.route('/api/push/status')
    def api_push_status():
        driver = session_driver_name()
        if not driver:
            return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            return jsonify({
                'status': 'success',
                'enabled': webpush.push_available(),
                'devices': webpush.count_subscriptions(driver, conn=conn),
            })
        finally:
            try: conn.close()
            except Exception: pass
