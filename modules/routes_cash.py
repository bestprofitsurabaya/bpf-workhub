"""Cash Request / Kasbon BBM Routes"""
import random
from datetime import date
from flask import request, jsonify, session
import os
from modules.config import get_db_connection
from modules.helpers import (log_activity_async, generate_display_id, safe_float,
                             role_required, session_driver_name, resolve_driver_scope)
from modules.notifications import push_driver_notification

def register_cash_routes(app):

    def get_or_create_daily_code_with_lock(cursor, conn):
        cursor.execute(
            "SELECT unique_code FROM daily_unique_codes WHERE code_date = CURDATE() FOR UPDATE"
        )
        row = cursor.fetchone()
        if row:
            return row["unique_code"]
        code_val = random.choice([
            100, 200, 300, 400, 500, 600, 700, 800, 900,
            1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000
        ])
        cursor.execute(
            "INSERT INTO daily_unique_codes (code_date, unique_code) VALUES (CURDATE(), %s)",
            (code_val,)
        )
        return code_val


    # ================================================================
    # DAILY UNIQUE CODE
    # ================================================================
    @app.route('/api/cash/daily-code', methods=['GET', 'POST'])
    def api_daily_code():
        # Check mode
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key = 'cash_code_manual'")
        mode_row = cursor.fetchone()
        manual_mode = mode_row['config_value'] == 'true' if mode_row else False
        cursor.close(); conn.close()

        if request.method == 'POST':
            # Hanya admin Finance yang boleh mengubah kode harian (driver hanya GET)
            if not session.get('user_role') or session.get('user_role') not in ('finance', 'admin'):
                return jsonify({'status': 'error', 'msg': 'Akses ditolak. Hanya Finance yang dapat mengubah kode.'}), 401
            data = request.get_json()
            new_code = data.get('code', 0)
            if new_code < 100 or new_code > 2000:
                return jsonify({'status': 'error', 'msg': 'Kode harus 100-2000'}), 400
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO daily_unique_codes (code_date, unique_code) VALUES (CURDATE(), %s) ON DUPLICATE KEY UPDATE unique_code = %s", (new_code, new_code))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_code_set', 'admin', 'Admin', new_data={'code': new_code})
            return jsonify({'status': 'success', 'msg': f'Kode harian diatur ke {new_code}', 'code': new_code})
        """Get or generate today's unique 2-digit code"""
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            code_val = get_or_create_daily_code_with_lock(cursor, conn)
            cursor.close(); conn.close()
            return jsonify({'code': code_val, 'date': str(date.today()), 'manual_mode': manual_mode})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # DRIVER: SUBMIT CASH REQUEST
    # ================================================================
    @app.route('/api/cash/request', methods=['POST'])
    def api_cash_request():
        """Driver submits a cash advance request"""
        try:
            data = request.get_json()
            # v2.5: identitas driver WAJIB dari sesi login PIN; jalur legacy
            # anonim (field driver_name) DITUTUP — anti impersonasi & spam.
            driver_name = session_driver_name()
            if not driver_name:
                if not session.get('user_role'):
                    return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
                driver_name = (data.get('driver_name', '') or '').strip().upper()
            nopol = data.get('nopol', '').strip().upper()
            vehicle_type = data.get('vehicle_type', 'AVANZA')
            bbm_type = data.get('bbm_type', 'PERTALITE')
            base_amount = safe_float(data.get('base_amount', 0))

            if not driver_name or base_amount <= 0:
                return jsonify({'status': 'error', 'msg': 'Driver dan nominal wajib'}), 400

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Get today's unique code
            code_val = get_or_create_daily_code_with_lock(cursor, conn)
            unique_cents = code_val
            total_amount = base_amount + unique_cents
            display_id = generate_display_id('CASH', conn)

            cursor.execute("""
                INSERT INTO fuel_cash_requests (display_id, driver_name, nopol, vehicle_type, bbm_type,
                    base_amount, unique_cents, total_amount, daily_code, status, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT', %s)
            """, (display_id, driver_name, nopol, vehicle_type, bbm_type,
                  base_amount, unique_cents, total_amount, code_val, data.get('notes', '')))

            cash_id = cursor.lastrowid
            conn.commit()

            log_activity_async(0, 'cash_request_submit', 'driver', driver_name,
                             new_data={'cash_id': cash_id, 'total': total_amount, 'code': code_val})

            cursor.close(); conn.close()

            return jsonify({
                'status': 'success',
                'msg': f'Pengajuan {display_id} berhasil. Total: Rp {total_amount:,.0f} (kode: {code_val})',
                'cash_id': cash_id,
                'display_id': display_id,
                'total_amount': total_amount,
                'unique_code': code_val
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA: APPROVE CASH REQUEST
    # ================================================================
    @app.route('/api/cash/approve-ga/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_cash_approve_ga(cash_id):
        """GA approves the cash request"""
        try:
            data = request.get_json() or {}
            ga_name = data.get('ga_name', 'GA Officer').strip()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'DRAFT'", (cash_id,))
            req = cursor.fetchone()

            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau sudah diproses'}), 404

            cursor.execute("""
                UPDATE fuel_cash_requests SET status = 'GA_APPROVED', ga_approved_by = %s, ga_approved_at = NOW()
                WHERE id = %s
            """, (ga_name, cash_id))
            conn.commit()

            log_activity_async(0, 'cash_ga_approve', 'ga', ga_name,
                             new_data={'cash_id': cash_id, 'display_id': req['display_id']})
            push_driver_notification(req['driver_name'], 'cash', 'approved',
                                     f'Kasbon {req["display_id"]} disetujui GA', req['display_id'])

            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Pengajuan {req["display_id"]} disetujui GA'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # FINANCE: APPROVE CASH DISBURSEMENT
    # ================================================================
    @app.route('/api/cash/approve-finance/<int:cash_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_cash_approve_finance(cash_id):
        """Finance approves the cash disbursement"""
        try:
            data = request.get_json() or {}
            fin_name = data.get('finance_name', 'Finance Officer').strip()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'GA_APPROVED'", (cash_id,))
            req = cursor.fetchone()

            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau belum GA approve'}), 404

            cursor.execute("""
                UPDATE fuel_cash_requests SET status = 'FINANCE_APPROVED', finance_approved_by = %s, finance_approved_at = NOW()
                WHERE id = %s
            """, (fin_name, cash_id))
            conn.commit()

            log_activity_async(0, 'cash_finance_approve', 'finance', fin_name,
                             new_data={'cash_id': cash_id, 'display_id': req['display_id']})
            push_driver_notification(req['driver_name'], 'cash', 'paid',
                                     f'Kasbon {req["display_id"]} dicairkan Finance — dana siap diambil', req['display_id'])

            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Pencairan {req["display_id"]} disetujui Finance. Silakan ambil dana.'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA: HANDOVER - Konfirmasi dana di tangan Driver
    # ================================================================
    @app.route('/api/cash/handover/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_cash_handover(cash_id):
        """GA confirms funds handed to driver"""
        try:
            data = request.get_json() or {}
            ga_name = data.get('ga_name', 'GA Officer').strip()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'FINANCE_APPROVED'", (cash_id,))
            req = cursor.fetchone()

            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau belum Finance approve'}), 404

            cursor.execute("""
                UPDATE fuel_cash_requests SET status = 'FUNDS_WITH_DRIVER', handover_by = %s, handover_at = NOW()
                WHERE id = %s
            """, (ga_name, cash_id))
            conn.commit()

            log_activity_async(0, 'cash_handover', 'ga', ga_name,
                             new_data={'cash_id': cash_id, 'display_id': req['display_id'], 'driver': req['driver_name']})
            push_driver_notification(req['driver_name'], 'cash', 'handover',
                                     f'Dana kasbon {req["display_id"]} sudah diserahkan ke Anda', req['display_id'])

            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Dana {req["display_id"]} sudah di tangan {req["driver_name"]}. Menunggu LPJ.'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DRIVER: GET PENDING LPJ
    # ================================================================
    @app.route('/api/cash/pending-lpj')
    def api_cash_pending_lpj():
        """Get cash requests that need LPJ submission"""
        try:
            # v2.5: tanpa sesi sama sekali → ditolak (jalur legacy ?driver= ditutup)
            driver = resolve_driver_scope(request.args.get('driver', ''))
            if driver is None:
                return jsonify({'error': 'Login driver wajib'}), 401
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)

            query = "SELECT * FROM fuel_cash_requests WHERE status = 'FUNDS_WITH_DRIVER'"
            params = []
            if driver:
                query += " AND driver_name = %s"
                params.append(driver)
            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            data = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================

    # ================================================================
    # GA: APPROVE LPJ (Verifikasi LPJ -> Complete)
    # ================================================================
    @app.route('/api/cash/approve-lpj/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_cash_approve_lpj(cash_id):
        """GA verifies LPJ -> marks cash as COMPLETED and transaction as verified_ga"""
        try:
            data = request.get_json() or {}
            ga_name = data.get('ga_name', 'GA Officer').strip()
            notes = data.get('notes', '').strip()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'LPJ_SUBMITTED'", (cash_id,))
            cash_req = cursor.fetchone()

            if not cash_req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Cash request tidak ditemukan atau belum submit LPJ'}), 404

            tx_id = cash_req.get('lpj_transaction_id')
            if not tx_id:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada transaksi LPJ terkait'}), 400

            cursor.execute("UPDATE transactions SET status = 'verified_ga' WHERE id = %s AND status = 'pending'", (tx_id,))

            cursor.execute("""
                UPDATE fuel_cash_requests
                SET status = 'COMPLETED',
                    notes = CONCAT(COALESCE(notes,''), '\n[LPJ APPROVED by ', %s, '] ', %s)
                WHERE id = %s
            """, (ga_name, notes if notes else 'LPJ diverifikasi', cash_id))

            conn.commit()

            log_activity_async(0, 'cash_lpj_approve', 'ga', ga_name,
                             new_data={'cash_id': cash_id, 'tx_id': tx_id,
                                      'display_id': cash_req['display_id'],
                                      'notes': notes})
            push_driver_notification(cash_req['driver_name'], 'cash', 'completed',
                                     f'LPJ kasbon {cash_req["display_id"]} disetujui — selesai 🎉', cash_req['display_id'])

            cursor.close(); conn.close()
            return jsonify({
                'status': 'success',
                'msg': f'LPJ {cash_req["display_id"]} diverifikasi. Status: COMPLETED.',
                'cash_id': cash_id,
                'transaction_id': tx_id
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA: REJECT LPJ
    # ================================================================
    @app.route('/api/cash/reject-lpj/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_cash_reject_lpj(cash_id):
        """GA rejects LPJ -> returns to FUNDS_WITH_DRIVER for revision"""
        try:
            data = request.get_json() or {}
            ga_name = data.get('ga_name', 'GA Officer').strip()
            reason = data.get('reason', 'LPJ perlu direvisi').strip()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'LPJ_SUBMITTED'", (cash_id,))
            cash_req = cursor.fetchone()

            if not cash_req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Cash request tidak ditemukan atau belum submit LPJ'}), 404

            tx_id = cash_req.get('lpj_transaction_id')

            if tx_id:
                cursor.execute("UPDATE transactions SET status = 'rejected' WHERE id = %s", (tx_id,))

            cursor.execute("""
                UPDATE fuel_cash_requests
                SET status = 'FUNDS_WITH_DRIVER',
                    lpj_transaction_id = NULL,
                    lpj_submitted_at = NULL,
                    notes = CONCAT(COALESCE(notes,''), '\n[LPJ REJECTED by ', %s, '] ', %s)
                WHERE id = %s
            """, (ga_name, reason, cash_id))

            conn.commit()

            log_activity_async(0, 'cash_lpj_reject', 'ga', ga_name,
                             new_data={'cash_id': cash_id, 'tx_id': tx_id, 'reason': reason})
            push_driver_notification(cash_req['driver_name'], 'cash', 'lpj_rejected',
                                     f'LPJ kasbon {cash_req["display_id"]} ditolak: {reason} — silakan submit ulang', cash_req['display_id'])

            cursor.close(); conn.close()
            return jsonify({
                'status': 'success',
                'msg': f'LPJ {cash_req["display_id"]} ditolak. Driver harus submit ulang.',
                'cash_id': cash_id
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500


    # CASH REQUEST HISTORY
    # ================================================================
    @app.route('/api/cash/history')
    def api_cash_history():
        try:
            # v2.5: tanpa sesi sama sekali → ditolak (jalur legacy ?driver= ditutup)
            driver = resolve_driver_scope(request.args.get('driver', ''))
            if driver is None:
                return jsonify({'error': 'Login driver wajib'}), 401
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            if driver:
                cursor.execute("SELECT * FROM fuel_cash_requests WHERE driver_name = %s ORDER BY created_at DESC LIMIT 50", (driver,))
            else:
                cursor.execute("SELECT * FROM fuel_cash_requests ORDER BY created_at DESC LIMIT 100")
            data = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/cash/detail/<int:cash_id>')
    @role_required(['ga', 'finance', 'admin'])
    def api_cash_detail(cash_id):
        """Get cash request detail with tracking"""
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s", (cash_id,))
            data = cursor.fetchone()
            if not data:
                cursor.close(); conn.close()
                return jsonify({'error': 'Not found'}), 404

            # Get LPJ if submitted
            if data.get('lpj_transaction_id'):
                cursor.execute("SELECT * FROM transactions WHERE id = %s", (data['lpj_transaction_id'],))
                data['lpj'] = cursor.fetchone()

            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/cash/reject/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_cash_reject(cash_id):
        try:
            data = request.get_json() or {}
            reason = data.get('reason', 'Tanpa alasan').strip()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s", (cash_id,))
            req = cursor.fetchone()
            cursor.execute("UPDATE fuel_cash_requests SET status = 'REJECTED', rejection_reason = %s WHERE id = %s", (reason, cash_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_reject', 'ga', 'GA Officer', new_data={'cash_id': cash_id, 'reason': reason})
            if req:
                push_driver_notification(req['driver_name'], 'cash', 'rejected',
                                         f'Kasbon {req["display_id"]} ditolak: {reason}', req['display_id'])
            return jsonify({'status': 'success', 'msg': 'Pengajuan ditolak'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DRIVER: SUBMIT LPJ (Link to transaction)
    # ================================================================
    @app.route('/api/cash/submit-lpj/<int:cash_id>', methods=['POST'])
    def api_cash_submit_lpj(cash_id):
        # Support juga cash_id dari FormData (fallback)
        if not cash_id or cash_id == 0:
            cash_id = int(request.form.get('cash_request_id', 0))
        try:
            # v2.5: submit LPJ WAJIB sesi driver login (jalur legacy ditutup)
            if not session_driver_name():
                return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'FUNDS_WITH_DRIVER'", (cash_id,))
            cash_req = cursor.fetchone()
            if not cash_req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan'}), 404

            # v2.4: sesi driver login hanya boleh submit LPJ untuk kasbon miliknya sendiri
            # (anti IDOR antar driver — ISO/IEC 27001 A.8.2).
            if session_driver_name() and session_driver_name() != (cash_req['driver_name'] or '').strip().upper():
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'LPJ hanya bisa diisi untuk kasbon milik Anda'}), 403

            driver_name = cash_req['driver_name']
            nopol = cash_req['nopol']
            vehicle_type = cash_req['vehicle_type']
            bbm_type = request.form.get('bbm_type', cash_req['bbm_type'])
            nominal = safe_float(request.form.get('nominal', cash_req['total_amount']))
            price_per_liter = safe_float(request.form.get('price_per_liter', 10000))
            liter = nominal / price_per_liter if price_per_liter > 0 else 0
            odo_km = int(request.form.get('odo_km', 0))
            spbu_type = request.form.get('spbu_type', 'rekanan')

            from modules.helpers import save_file
            upload_dir = app.config['UPLOAD_FOLDER']
            foto_odo = save_file(request.files.get('foto_odo_sebelum'), 'ODO1', nopol, upload_dir)
            foto_nota = save_file(request.files.get('foto_nota_odo_sesudah'), 'ODO2', nopol, upload_dir)
            foto_struk = save_file(request.files.get('foto_struk'), 'STRUK', nopol, upload_dir)
            foto_dispenser = save_file(request.files.get('foto_struk_dispenser'), 'DISP', nopol, upload_dir) if spbu_type == 'non_rekanan' else None

            # Validasi server: foto wajib yang gagal disimpan (format tidak aman) harus menolak LPJ
            # — jangan pernah menyimpan LPJ tanpa bukti (ISO 9001:8.6). Termasuk foto dispenser
            # (wajib utk SPBU non-rekanan).
            rejected_photos = [field for field, saved in (
                ('foto_odo_sebelum', foto_odo),
                ('foto_nota_odo_sesudah', foto_nota),
                ('foto_struk', foto_struk),
                ('foto_struk_dispenser', foto_dispenser),
            ) if request.files.get(field) and not saved]
            if rejected_photos:
                for saved in (foto_odo, foto_nota, foto_struk, foto_dispenser):
                    if saved:
                        try:
                            _p = os.path.join(upload_dir, saved)
                            if os.path.exists(_p):
                                os.remove(_p)
                        except OSError:
                            pass
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Foto wajib gagal disimpan (format tidak didukung): ' + ', '.join(rejected_photos)}), 400
            gps_lat = request.form.get('gps_lat') or None
            gps_lon = request.form.get('gps_lon') or None
            gps_address = request.form.get('gps_address', '')
            gps_kelurahan = request.form.get('gps_kelurahan', '')
            gps_kecamatan = request.form.get('gps_kecamatan', '')
            gps_kota = request.form.get('gps_kota', '')
            gps_provinsi = request.form.get('gps_provinsi', '')
            gps_kode_pos = request.form.get('gps_kode_pos', '')
            jumlah_appointment = int(request.form.get('jumlah_appointment', 0) or 0)

            display_id = generate_display_id('BPF', conn)
            cursor.execute(
                "INSERT INTO transactions (display_id, transaction_type, cash_request_id, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter, odo_km, spbu_type, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser, status, km_per_liter, gps_latitude, gps_longitude, gps_address, gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (display_id, 'CASH_LPJ', cash_id, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter, odo_km, spbu_type, foto_odo, foto_nota, foto_struk, foto_dispenser, 'pending', 0, gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment)
            )
            tx_id = cursor.lastrowid

            cursor.execute("UPDATE fuel_cash_requests SET status = 'LPJ_SUBMITTED', lpj_transaction_id = %s, lpj_submitted_at = NOW() WHERE id = %s", (tx_id, cash_id))
            conn.commit()

            log_activity_async(0, 'cash_lpj_submit', 'driver', driver_name, new_data={'cash_id': cash_id, 'tx_id': tx_id})
            cursor.close(); conn.close()

            return jsonify({'status': 'success', 'msg': 'LPJ selesai!', 'transaction_id': display_id, 'numeric_id': tx_id, 'cash_id': cash_id})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

            return jsonify({'error': str(e)}), 500

    @app.route('/api/cash/delete/<int:cash_id>', methods=['POST', 'DELETE'])
    def api_cash_delete(cash_id):
        try:
            # v2.5: tanpa sesi sama sekali → ditolak (jalur legacy ditutup).
            # Sesi driver login dipaksa memakai identitas sendiri; back-office
            # (ga/finance/admin) tetap boleh menghapus DRAFT apa pun.
            driver = resolve_driver_scope(request.args.get('driver', ''))
            if driver is None:
                return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
            is_driver_session = bool(session_driver_name())
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'DRAFT'", (cash_id,))
            req = cursor.fetchone()
            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Hanya pengajuan DRAFT yang bisa dihapus'}), 400
            if (is_driver_session
                    and req['driver_name'].upper() != (driver or '').upper()):
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan ini bukan milik Anda'}), 403
            cursor.execute("DELETE FROM fuel_cash_requests WHERE id = %s", (cash_id,))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_delete', 'admin', 'Admin', new_data={'cash_id': cash_id, 'display_id': req['display_id']})
            return jsonify({'status': 'success', 'msg': f'Pengajuan {req["display_id"]} dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # EDIT NOMINAL (DRAFT only)
    # ================================================================
    @app.route('/api/cash/edit/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_cash_edit(cash_id):
        try:
            data = request.get_json()
            new_base = safe_float(data.get('base_amount', 0))
            reason = data.get('reason', 'Revisi nominal').strip()
            if new_base <= 0:
                return jsonify({'status': 'error', 'msg': 'Nominal harus > 0'}), 400
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'DRAFT'", (cash_id,))
            req = cursor.fetchone()
            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Hanya DRAFT yang bisa diedit'}), 400
            new_total = new_base + float(req['unique_cents'])
            cursor.execute("UPDATE fuel_cash_requests SET base_amount = %s, total_amount = %s, notes = CONCAT(COALESCE(notes,''), '\n[EDIT] ', %s) WHERE id = %s",
                (new_base, new_total, reason, cash_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_edit', 'admin', 'Admin', new_data={'cash_id': cash_id, 'old_base': float(req['base_amount']), 'new_base': new_base, 'reason': reason})
            return jsonify({'status': 'success', 'msg': f'Nominal diubah: Rp {float(req["base_amount"]):,.0f} → Rp {new_base:,.0f}', 'new_total': new_total})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # BATALKAN PENGAJUAN (kembali ke DRAFT)
    # ================================================================
    @app.route('/api/cash/cancel/<int:cash_id>', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_cash_cancel(cash_id):
        try:
            data = request.get_json() or {}
            reason = data.get('reason', 'Dibatalkan').strip()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status != 'COMPLETED' AND status != 'REJECTED'", (cash_id,))
            req = cursor.fetchone()
            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau sudah selesai'}), 404
            old_status = req['status']
            # Reset status ke DRAFT untuk SEMUA status yang bisa dibatalkan
            # (sebelumnya hanya FUNDS_WITH_DRIVER yang di-update — bug pra-ada:
            #  status GA_APPROVED/FINANCE_APPROVED/LPJ_SUBMITTED tidak pernah berubah).
            cursor.execute(
                "UPDATE fuel_cash_requests SET status = 'DRAFT', "
                "lpj_transaction_id = NULL, lpj_submitted_at = NULL, "
                "ga_approved_by = NULL, ga_approved_at = NULL, "
                "finance_approved_by = NULL, finance_approved_at = NULL, "
                "handover_by = NULL, handover_at = NULL, "
                "notes = CONCAT(COALESCE(notes,''), '\n[CANCEL] ', %s) WHERE id = %s",
                (reason, cash_id)
            )
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_cancel', 'admin', 'Admin', new_data={'cash_id': cash_id, 'old_status': old_status, 'reason': reason})
            push_driver_notification(req['driver_name'], 'cash', 'cancelled',
                                     f'Kasbon {req["display_id"]} dibatalkan: {reason}', req['display_id'])
            return jsonify({'status': 'success', 'msg': f'Pengajuan {req["display_id"]} dikembalikan ke DRAFT'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # RESET LPJ (COMPLETED → FUNDS_WITH_DRIVER)
    # ================================================================
    @app.route('/api/cash/reset-lpj/<int:cash_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_cash_reset_lpj(cash_id):
        try:
            data = request.get_json() or {}
            reason = data.get('reason', 'LPJ di-reset').strip()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fuel_cash_requests WHERE id = %s AND status = 'COMPLETED' AND lpj_transaction_id IS NOT NULL", (cash_id,))
            req = cursor.fetchone()
            if not req:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Hanya COMPLETED dengan LPJ yang bisa di-reset'}), 404
            tx_id = req['lpj_transaction_id']
            # Hapus transaksi LPJ
            cursor.execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
            # Reset cash request
            cursor.execute("UPDATE fuel_cash_requests SET status = 'FUNDS_WITH_DRIVER', lpj_transaction_id = NULL, lpj_submitted_at = NULL, notes = CONCAT(COALESCE(notes,''), '\n[RESET LPJ] ', %s) WHERE id = %s", (reason, cash_id))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'cash_reset_lpj', 'admin', 'Admin', new_data={'cash_id': cash_id, 'old_tx_id': tx_id, 'reason': reason})
            push_driver_notification(req['driver_name'], 'cash', 'reset',
                                     f'LPJ kasbon {req["display_id"]} di-reset — silakan submit ulang', req['display_id'])
            return jsonify({'status': 'success', 'msg': f'LPJ di-reset. Driver bisa submit ulang.'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
