"""Routes for the Vue 3 SPA (v2.0).

- /api/auth/*  : JSON auth (session-based, CSRF-aware) untuk SPA.
- /api/trips*  : JSON endpoints log perjalanan (dipakai view SPA Trips).
- /app/*       : serve SPA bundle (static/app) dengan fallback ke index.html.
"""
import os
import secrets

from flask import jsonify, request, session, send_from_directory

from modules.helpers import role_required, log_activity_async, home_for_role, login_rate_check, login_fail, login_success, client_ip, save_file, safe_float
from modules.config import get_db_connection, get_master_connection

SPA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'app')

# Asset ber-hash (Vite) bisa di-cache lama; index.html wajib no-cache.
_SPA_IMMUTABLE_HINTS = ('/assets/', '.js', '.css', '.svg', '.png', '.woff2', '.ico')


def _ensure_csrf():
    """Pastikan session punya csrf_token (untuk header X-CSRF-Token SPA)."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']


def _client_ip():
    return client_ip()


def register_spa_routes(app):

    # ================================================================
    # AUTH (JSON) — sesi sama dengan login klasik
    # ================================================================
    @app.route('/api/auth/me')
    def api_auth_me():
        _ensure_csrf()
        if session.get('user_role'):
            return jsonify({
                'authenticated': True,
                'user': {
                    'role': session.get('user_role'),
                    'user_name': session.get('user_name'),
                    'full_name': session.get('full_name'),
                    'branch_code': session.get('branch_code'),
                    'branch_name': session.get('branch_name'),
                },
                'csrf_token': session.get('csrf_token'),
                'home': home_for_role(session.get('user_role')),
            })
        return jsonify({'authenticated': False, 'csrf_token': session.get('csrf_token')})

    @app.route('/api/auth/login', methods=['POST'])
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        username = str(data.get('username', '')).strip()
        pin = str(data.get('pin', '')).strip()
        if not username or not pin:
            return jsonify({'status': 'error', 'msg': 'Username dan PIN wajib diisi'}), 400

        # Rate limit anti brute-force (ISO/IEC 27001 A.8.5) — sama dengan login klasik
        ip = _client_ip()
        allowed, retry_after = login_rate_check(ip, username)
        if not allowed:
            return jsonify({'status': 'error', 'msg': f'Terlalu banyak percobaan. Coba lagi dalam {retry_after // 60} menit.'}), 429

        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'Database tidak tersedia'}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username=%s AND pin=%s AND is_active=TRUE", (username, pin))
            user = cursor.fetchone()
            cursor.close(); conn.close()
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        if not user:
            login_fail(ip, username)
            return jsonify({'status': 'error', 'msg': 'Username atau PIN salah'}), 401

        # Multi-cabang: tentukan cabang user; cabang nonaktif → tolak login
        from modules.branch_manager import get_branch, DEFAULT_BRANCH_CODE
        branch_code = (user.get('branch_code') or '').strip() or DEFAULT_BRANCH_CODE
        branch = get_branch(branch_code)
        if not branch or not branch.get('is_active'):
            login_fail(ip, username)
            return jsonify({'status': 'error',
                            'msg': 'Cabang tidak aktif atau tidak terdaftar. Hubungi Admin.'}), 403

        login_success(ip, username)
        session.clear()
        session['user_role'] = user['role']
        session['user_name'] = user['username']
        session['full_name'] = user['full_name']
        session['branch_code'] = branch['code']
        session['branch_name'] = branch['name']
        session.permanent = True
        csrf = _ensure_csrf()
        log_activity_async(None, 'login', 'user', user['username'], ip=request.remote_addr)
        # v2.22.1: sinkronisasi sheet Driver otomatis di background (ga_hr/admin)
        try:
            from modules.routes_overtime import trigger_driver_refresh_async
            trigger_driver_refresh_async(user['role'], user['full_name'],
                                         ip=request.remote_addr)
        except Exception:
            pass  # sinkronisasi gagal tidak boleh menghalangi login
        return jsonify({
            'status': 'success',
            'user': {'role': user['role'], 'user_name': user['username'], 'full_name': user['full_name'],
                     'branch_code': branch['code'], 'branch_name': branch['name']},
            'csrf_token': csrf,
            'home': home_for_role(user['role']),
        })

    @app.route('/api/auth/logout', methods=['POST'])
    def api_auth_logout():
        role = session.get('user_role')
        full_name = session.get('full_name') or session.get('user_name')
        # v2.22.1: sinkronisasi sheet Driver otomatis di background (ga_hr/admin)
        try:
            from modules.routes_overtime import trigger_driver_refresh_async
            trigger_driver_refresh_async(role, full_name, ip=request.remote_addr)
        except Exception:
            pass  # sinkronisasi gagal tidak boleh menghalangi logout
        session.clear()
        return jsonify({'status': 'success'})

    # ================================================================
    # TRIPS (JSON) — list + verify + reject
    # ================================================================
    @app.route('/api/trips')
    @role_required(['ga', 'finance', 'admin'])
    def api_trips_list():
        try:
            driver_filter = request.args.get('driver', '').strip()
            date_filter = request.args.get('date', '').strip()
            status_filter = request.args.get('status', '').strip()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            query = """SELECT tm.id, tm.display_id, tm.driver_name, tm.trip_date, tm.status,
                       tm.km_awal, tm.km_akhir, tm.verified_by, tm.verified_at,
                       (SELECT COUNT(*) FROM trip_details WHERE trip_master_id = tm.id) AS total_routes
                       FROM trip_masters tm WHERE 1=1"""
            params = []
            if driver_filter:
                query += " AND tm.driver_name LIKE %s"; params.append(f"%{driver_filter}%")
            if date_filter:
                query += " AND tm.trip_date = %s"; params.append(date_filter)
            if status_filter in ('pending', 'verified_ga', 'rejected'):
                query += " AND tm.status = %s"; params.append(status_filter)
            query += " ORDER BY tm.created_at DESC LIMIT 200"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'data': rows})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/trips/verify/<int:trip_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_trip_verify(trip_id):
        try:
            # verified_by selalu dari session — jangan pernah percaya input klien (anti audit forgery)
            admin_name = (session.get('full_name') or session.get('user_name') or 'GA Officer').strip()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE trip_masters SET status='verified_ga', verified_by=%s, verified_at=NOW() "
                "WHERE id=%s AND status='pending'",
                (admin_name, trip_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(trip_id, 'trip_verify', 'ga', admin_name, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'Trip #{trip_id} diverifikasi'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/trips/reject/<int:trip_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_trip_reject(trip_id):
        try:
            data = request.get_json(silent=True) or {}
            reason = (data.get('reason') or 'Tidak valid').strip()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE trip_masters SET status='rejected', rejection_reason=%s WHERE id=%s",
                (reason, trip_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(trip_id, 'trip_reject', 'ga', session.get('user_name', 'GA Officer'),
                               new_data={'reason': reason}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'Trip #{trip_id} ditolak'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # QUEUE KERJA (JSON) — antrean approve GA / payout / archive / reject
    # Nama pelaku diambil dari session (anti audit-trail forgery),
    # bukan dari body/query seperti endpoint klasik.
    # ================================================================
    def _queue_actor():
        return (session.get('full_name') or session.get('user_name') or 'Admin').strip()

    @app.route('/api/queue')
    @role_required(['ga', 'finance', 'admin'])
    def api_queue():
        try:
            tab = request.args.get('tab', 'ga')
            if tab not in ('ga', 'finance', 'driver_confirm'):
                tab = 'ga'
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cols = "id, display_id, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, odo_km, ml_anomaly_flag, created_at"
            if tab == 'finance':
                cursor.execute(f"SELECT {cols} FROM transactions WHERE status='verified_ga' AND (is_dummy=0 OR is_dummy IS NULL) ORDER BY created_at ASC")
            elif tab == 'driver_confirm':
                cursor.execute(f"SELECT {cols} FROM transactions WHERE status='os_finance' AND (is_dummy=0 OR is_dummy IS NULL) ORDER BY created_at ASC")
            else:
                cursor.execute(f"SELECT {cols} FROM transactions WHERE status IN ('pending','modified') AND (is_dummy=0 OR is_dummy IS NULL) ORDER BY created_at ASC")
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(rows)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/queue/approve-ga/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_queue_approve_ga(tx_id):
        actor = _queue_actor()
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            # Transaksi ber-flag anomali ML wajib verifikasi penuh (foto bukti)
            # dari modal detail SPA — tidak boleh di-approve cepat dari antrean.
            cursor.execute("SELECT ml_anomaly_flag FROM transactions WHERE id=%s", (tx_id,))
            prow = cursor.fetchone()
            if prow and prow.get('ml_anomaly_flag'):
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} ber-flag anomali ML — wajib verifikasi penuh (foto bukti) dari baris antrean.'}), 409
            cursor.execute("UPDATE transactions SET status='verified_ga', ga_approved_by=%s, ga_approved_at=NOW(), approved_by_user=%s WHERE id=%s AND status IN ('pending','modified')", (actor, actor, tx_id))
            affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                try:
                    cursor.execute("SELECT driver_name, display_id FROM transactions WHERE id=%s", (tx_id,))
                    row = cursor.fetchone()
                    if row:
                        from modules.notifications import push_driver_notification
                        push_driver_notification(row[0], 'claim', 'approved', f'Klaim {row[1]} Anda disetujui GA', row[1])
                except Exception as ne:
                    print(f"[notify] approve error: {ne}")
            cursor.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan atau sudah diproses.'}), 409
            log_activity_async(tx_id, 'ga_approve', 'ga', actor, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Klaim #{tx_id} disetujui GA!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/payout/<int:tx_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_queue_payout(tx_id):
        actor = _queue_actor()
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute("UPDATE transactions SET status='os_finance', finance_payout_by=%s, finance_payout_at=NOW(), payout_by_user=%s WHERE id=%s AND status='verified_ga'", (actor, actor, tx_id))
            affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                try:
                    cursor.execute("SELECT driver_name, display_id FROM transactions WHERE id=%s", (tx_id,))
                    row = cursor.fetchone()
                    if row:
                        from modules.notifications import push_driver_notification
                        push_driver_notification(row[0], 'claim', 'paid', f'Dana klaim {row[1]} sudah dicairkan Finance', row[1])
                except Exception as ne:
                    print(f"[notify] payout error: {ne}")
            cursor.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan atau sudah diproses.'}), 409
            log_activity_async(tx_id, 'finance_payout', 'finance', actor, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Dana #{tx_id} dicairkan!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/archive/<int:tx_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_queue_archive(tx_id):
        actor = _queue_actor()
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute("UPDATE transactions SET status='archived', archived_by=%s, archived_at=NOW(), archived_by_user=%s WHERE id=%s AND status='os_finance'", (actor, actor, tx_id))
            affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                try:
                    cursor.execute("SELECT driver_name, display_id FROM transactions WHERE id=%s", (tx_id,))
                    row = cursor.fetchone()
                    if row:
                        from modules.notifications import push_driver_notification
                        push_driver_notification(row[0], 'claim', 'archived', f'Klaim {row[1]} selesai & diarsipkan', row[1])
                except Exception as ne:
                    print(f"[notify] archive error: {ne}")
            cursor.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan atau sudah diproses.'}), 409
            log_activity_async(tx_id, 'archive', 'finance', actor, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Transaksi #{tx_id} diarsipkan!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/reject/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_queue_reject(tx_id):
        actor = _queue_actor()
        data = request.get_json(silent=True) or {}
        reason = str(data.get('reason') or 'Tanpa alasan').strip()[:500]
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT driver_name, display_id FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            cursor.execute("UPDATE transactions SET status='rejected', rejection_reason=%s WHERE id=%s AND status <> 'rejected'", (reason, tx_id))
            affected = cursor.rowcount
            conn.commit()
            if affected > 0 and tx:
                try:
                    from modules.notifications import push_driver_notification
                    push_driver_notification(tx['driver_name'], 'claim', 'rejected', f'Klaim {tx["display_id"]} ditolak: {reason}', tx['display_id'])
                except Exception as ne:
                    print(f"[notify] reject error: {ne}")
            cursor.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan atau sudah ditolak.'}), 409
            log_activity_async(tx_id, 'reject', 'ga', actor, new_data={'reason': reason}, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Klaim #{tx_id} ditolak'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/verify/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_queue_verify(tx_id):
        """Verifikasi mendalam dari SPA (pengganti form klasik /admin action=verify).
        Termasuk jalur verifikasi transaksi ber-flag anomali ML: GA/Admin memeriksa
        foto bukti & mengonfirmasi eksplisit (confirm_anomaly) — kontrol ISO 9001.
        """
        actor = _queue_actor()
        data = request.form or (request.get_json(silent=True) or {})
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT ml_anomaly_flag, status, nopol FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            if not tx:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan.'}), 404
            if tx['status'] not in ('pending', 'modified'):
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Status saat ini ({tx["status"]}) tidak bisa diverifikasi.'}), 409
            if tx.get('ml_anomaly_flag') and str(data.get('confirm_anomaly', '')).strip().lower() not in ('1', 'true', 'yes', 'on'):
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Transaksi ber-flag anomali ML — centang konfirmasi setelah memeriksa foto bukti.'}), 422

            is_error = 1 if str(data.get('mypertamina_error', '')).strip().lower() in ('1', 'true', 'on') else 0
            foto_mypertamina = None
            uploaded = request.files.get('foto_mypertamina')
            if uploaded and uploaded.filename:
                foto_mypertamina = save_file(uploaded, 'ADMIN_MYPTM', tx.get('nopol') or '', app.config['UPLOAD_FOLDER'])
                if not foto_mypertamina:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error', 'msg': 'Foto MyPertamina gagal disimpan (format tidak didukung).'}), 400
            cursor.execute("UPDATE transactions SET is_mypertamina_error=%s, foto_mypertamina_admin=%s, status='verified_ga', ga_approved_by=%s, ga_approved_at=NOW(), approved_by_user=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                           (is_error, foto_mypertamina, actor, actor, tx_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(tx_id, 'verify', 'ga', actor, new_data={'is_mypertamina_error': is_error}, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Klaim #{tx_id} diverifikasi & disetujui GA!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/modify/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_queue_modify(tx_id):
        """Perbaiki data transaksi dari SPA (pengganti form klasik /admin action=modify).
        Perubahan menandai status 'modified' untuk review ulang."""
        actor = _queue_actor()
        data = request.get_json(silent=True) or {}
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM transactions WHERE id=%s", (tx_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan.'}), 404
            if row[0] not in ('pending', 'modified'):
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Status saat ini ({row[0]}) tidak bisa dimodifikasi.'}), 409
            nominal = safe_float(data.get('nominal'), -1)
            odo_km = int(safe_float(data.get('odo_km'), -1))
            if nominal < 0 or odo_km < 0:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Nominal dan ODO harus angka valid.'}), 422
            cursor.execute("UPDATE transactions SET vehicle_type=%s, bbm_type=%s, nominal=%s, odo_km=%s, spbu_type=%s, status='modified', updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                           (str(data.get('vehicle_type', ''))[:50], str(data.get('bbm_type', ''))[:30],
                            nominal, odo_km, str(data.get('spbu_type', ''))[:20], tx_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(tx_id, 'modify', 'ga', actor, new_data={'nominal': nominal, 'odo_km': odo_km}, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Data klaim #{tx_id} diperbaiki (status modified — review ulang)'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DETAIL TRANSAKSI (JSON) — untuk modal verifikasi mendalam di SPA
    # ================================================================
    @app.route('/api/transactions/detail/<int:tx_id>')
    @role_required(['ga', 'finance', 'admin'])
    def api_tx_detail(tx_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            if not tx:
                cursor.close(); conn.close()
                return jsonify({'error': 'Transaksi tidak ditemukan'}), 404
            photos = []
            for field, label in [('foto_odo_sebelum', 'ODO Sebelum'), ('foto_nota_odo_sesudah', 'Nota + ODO Sesudah'),
                                 ('foto_struk', 'Struk'), ('foto_struk_dispenser', 'Dispenser'),
                                 ('foto_mypertamina_admin', 'MyPertamina (Admin)')]:
                if tx.get(field):
                    photos.append({'label': label, 'url': '/uploads/' + str(tx[field])})
            cursor.close(); conn.close()
            return jsonify({
                'id': tx['id'], 'display_id': tx['display_id'], 'driver_name': tx['driver_name'],
                'nopol': tx['nopol'], 'vehicle_type': tx.get('vehicle_type'), 'bbm_type': tx.get('bbm_type'),
                'nominal': float(tx['nominal'] or 0), 'liter': float(tx['liter'] or 0),
                'price_per_liter': float(tx.get('price_per_liter') or 0),
                'odo_km': float(tx['odo_km'] or 0), 'km_per_liter': float(tx.get('km_per_liter') or 0),
                'spbu_type': tx.get('spbu_type'), 'status': tx['status'],
                'ml_anomaly_flag': bool(tx.get('ml_anomaly_flag')),
                'is_mypertamina_error': bool(tx.get('is_mypertamina_error')),
                'rejection_reason': tx.get('rejection_reason'),
                'gps_address': tx.get('gps_address'), 'jumlah_appointment': tx.get('jumlah_appointment') or 0,
                'created_at': str(tx['created_at']),
                'ga_approved_by': tx.get('ga_approved_by'), 'finance_payout_by': tx.get('finance_payout_by'),
                'archived_by': tx.get('archived_by'),
                'photos': photos,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # UNVERIFY & DELETE transaksi (JSON) — dari modal detail SPA
    # ================================================================
    @app.route('/api/queue/unverify/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_queue_unverify(tx_id):
        actor = _queue_actor()
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute("UPDATE transactions SET status='pending' WHERE id=%s AND status='verified_ga'", (tx_id,))
            affected = cursor.rowcount
            conn.commit()
            cursor.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan atau status bukan verified_ga.'}), 409
            log_activity_async(tx_id, 'unverify', 'ga', actor, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Transaksi #{tx_id} dikembalikan ke antrean GA'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/queue/delete/<int:tx_id>', methods=['POST'])
    @role_required(['admin'])
    def api_queue_delete(tx_id):
        actor = _queue_actor()
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            if not tx:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Transaksi #{tx_id} tidak ditemukan.'}), 404
            # Hapus file bukti terkait (aman: tidak menggagalkan jika file tak ada)
            import os as _os
            upload_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'uploads')
            for field in ('foto_odo_sebelum', 'foto_nota_odo_sesudah', 'foto_struk', 'foto_struk_dispenser', 'foto_mypertamina_admin'):
                if tx.get(field):
                    try:
                        p = _os.path.join(upload_dir, str(tx[field]))
                        if _os.path.isfile(p):
                            _os.remove(p)
                    except Exception:
                        pass
            cursor.execute("DELETE FROM transactions WHERE id=%s", (tx_id,))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(tx_id, 'delete_tx', 'admin', actor, new_data={'display_id': tx['display_id']}, ip=_client_ip())
            return jsonify({'status': 'success', 'msg': f'Transaksi {tx["display_id"]} dihapus permanen'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # SPA — serve bundle + fallback client routing
    # ================================================================
    @app.route('/app/')
    @app.route('/app/<path:path>')
    def spa_app(path=''):
        if not os.path.isfile(os.path.join(SPA_DIR, 'index.html')):
            return ("SPA belum di-build. Jalankan: bash scripts/build-spa.sh, "
                    "lalu rebuild container."), 503
        if path:
            full = os.path.join(SPA_DIR, path)
            if os.path.isfile(full):
                resp = send_from_directory(SPA_DIR, path)
                # Asset ber-hash (Vite) aman di-cache lama; app.py after_request
                # tidak menimpa header yang sudah di-set di sini.
                if any(hint in path for hint in _SPA_IMMUTABLE_HINTS):
                    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
                return resp
        # index.html + fallback client-routing: selalu fresh (no-store dari after_request)
        return send_from_directory(SPA_DIR, 'index.html')
