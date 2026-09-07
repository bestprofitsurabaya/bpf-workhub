"""Driver & PWA routes"""
from flask import (request, redirect, session,
                   send_from_directory, jsonify, make_response)
from modules.config import get_db_connection
from modules.helpers import (save_file, resolve_driver_form_context, validate_bbm_for_vehicle,
                             ensure_all_master_data, generate_display_id, log_activity_async,
                             session_driver_name, role_required)
from modules.engine import PerformanceAnalyzer
from modules.approvals import hook_create_approval  # v2.36.0
from datetime import datetime
import os

def register_driver_routes(app, socketio):

    @app.route('/')
    def index():
        # v2.5: root mengarah ke SPA (router memilih dashboard sesuai role)
        return redirect('/app/')

    @app.route('/driver', methods=['GET', 'POST'])
    def driver_form():
        # v2.4 (Fase 2 migrasi Vue): halaman klasik digantikan SPA /app/driver.
        # GET dialihkan ke SPA (login PIN driver; SPA guard yang mengarahkan ke login).
        # POST dipakai SPA driver (BBM offline queue) — identitas WAJIB dari sesi.
        if request.method == 'GET':
            return redirect('/app/driver')
        if request.method == 'POST':
            conn = None
            try:
                # v2.5: identitas driver WAJIB dari sesi login PIN (jalur legacy
                # anonim lewat field `driver_name` DITUTUP — anti impersonasi).
                driver_name = session_driver_name()
                if not driver_name:
                    return jsonify({'status': 'error', 'msg': 'Login driver wajib — buka /app/driver'}), 401
                driver_name = driver_name.strip().upper()
                nopol = request.form.get('nopol', '').strip().upper()
                vehicle_type = request.form.get('vehicle_type', 'AVANZA')
                bbm_type = request.form.get('bbm_type', 'PERTALITE')
                try:
                    nominal = float(request.form.get('nominal', 0))
                    odo_km = int(request.form.get('odo_km', 0))
                    jumlah_appointment = int(request.form.get('jumlah_appointment', 0) or 0)
                except (ValueError, TypeError):
                    return jsonify({'status': 'error', 'msg': 'Nominal, Odo KM, dan jumlah appointment harus angka'}), 400
                spbu_type = request.form.get('spbu_type', 'rekanan')
                gps_lat = request.form.get('gps_lat')
                gps_lon = request.form.get('gps_lon')
                gps_address = request.form.get('gps_address', '')
                gps_kelurahan = request.form.get('gps_kelurahan', '')
                gps_kecamatan = request.form.get('gps_kecamatan', '')
                gps_kota = request.form.get('gps_kota', '')
                gps_provinsi = request.form.get('gps_provinsi', '')
                gps_kode_pos = request.form.get('gps_kode_pos', '')

                conn = get_db_connection()
                if not conn:
                    return jsonify({'status': 'error', 'msg': 'Database error'}), 500
                cursor = conn.cursor(dictionary=True)

                # --- Basic validation BEFORE any DB writes ---
                if not driver_name or not nopol or nominal <= 0 or odo_km <= 0:
                    return jsonify({'status': 'error', 'msg': 'Semua field harus diisi!'}), 400

                cursor.execute("SELECT * FROM drivers WHERE name=%s AND is_active=TRUE", (driver_name,))
                driver_data = cursor.fetchone()
                if not driver_data:
                    return jsonify({'status': 'error', 'msg': 'Driver tidak ditemukan atau nonaktif. Hubungi Admin.'}), 403
                resolved = resolve_driver_form_context(driver_data, driver_name, nopol, vehicle_type, bbm_type)
                nopol = resolved['nopol']
                vehicle_type = resolved['vehicle_type']
                bbm_type = resolved['bbm_type']

                validation = validate_bbm_for_vehicle(vehicle_type, bbm_type)
                if not validation['valid']:
                    return jsonify({'status': 'error', 'msg': validation['error']}), 400

                # --- Use server-side price, NOT client-provided ---
                cursor.execute("SELECT price_per_liter FROM vehicle_fuel_prices WHERE vehicle_type=%s AND bbm_type=%s", (vehicle_type, bbm_type))
                price_row = cursor.fetchone()
                price_per_liter = float(price_row['price_per_liter']) if price_row and price_row.get('price_per_liter') else 10000
                liter = nominal / price_per_liter if price_per_liter > 0 else 0

                ensure_all_master_data(driver_name, nopol, vehicle_type, bbm_type, price_per_liter)

                upload_dir = app.config['UPLOAD_FOLDER']
                foto_odo_sebelum = save_file(request.files.get('foto_odo_sebelum'), 'ODO1', nopol, upload_dir)
                foto_nota_odo_sesudah = save_file(request.files.get('foto_nota_odo_sesudah'), 'ODO2', nopol, upload_dir)
                foto_struk = save_file(request.files.get('foto_struk'), 'STRUK', nopol, upload_dir)
                foto_struk_dispenser = save_file(request.files.get('foto_struk_dispenser'), 'DISP', nopol, upload_dir) if spbu_type=='non_rekanan' else None

                # Validasi server: foto wajib yang gagal disimpan (format tidak aman) HARUS menolak
                # transaksi — jangan pernah menyimpan klaim tanpa bukti (ISO 9001:8.6).
                # Termasuk foto dispenser (wajib utk SPBU non-rekanan); kasus foto tidak dikirim
                # sama sekali tidak ditolak karena alur offline PWA (sync.js) kirim tanpa foto.
                rejected_photos = [field for field, saved in (
                    ('foto_odo_sebelum', foto_odo_sebelum),
                    ('foto_nota_odo_sesudah', foto_nota_odo_sesudah),
                    ('foto_struk', foto_struk),
                    ('foto_struk_dispenser', foto_struk_dispenser),
                ) if request.files.get(field) and not saved]
                if rejected_photos:
                    for saved in (foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser):
                        if saved:
                            try:
                                _p = os.path.join(upload_dir, saved)
                                if os.path.exists(_p):
                                    os.remove(_p)
                            except OSError:
                                pass
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error',
                                    'msg': 'Foto wajib gagal disimpan (format file tidak didukung): ' + ', '.join(rejected_photos)}), 400

                cursor.execute("SELECT odo_km FROM transactions WHERE nopol=%s ORDER BY created_at DESC LIMIT 1", (nopol,))
                previous = cursor.fetchone()
                km_per_liter = 0
                if previous and previous['odo_km']<odo_km and liter>0:
                    km_per_liter = (odo_km - previous['odo_km'])/liter

                analysis = PerformanceAnalyzer.analyze_performance(nopol, km_per_liter, conn, vehicle_type, bbm_type)
                display_id = generate_display_id('BPF', conn)

                cursor.execute("""
                    INSERT INTO transactions (display_id, transaction_type, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter,
                    odo_km, spbu_type, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser,
                    status, ml_anomaly_flag, km_per_liter, gps_latitude, gps_longitude, gps_address,
                    gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment)
                    VALUES (%s,'CLAIM',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (display_id, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter,
                      odo_km, spbu_type, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser,
                      analysis['is_anomaly'], km_per_liter, gps_lat, gps_lon, gps_address,
                      gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment))

                tx_id = cursor.lastrowid
                conn.commit()
                # v2.36.0: jurnal ACC berjenjang (Chief Driver → GA) — best-effort.
                hook_create_approval(conn, 'bbm', tx_id, display_id=display_id, role='driver')
                log_activity_async(tx_id, 'create', 'driver', driver_name, ip=request.remote_addr)
                try:
                    socketio.emit('new_claim', {
                        'driver_name': driver_name, 'nopol': nopol, 'display_id': display_id,
                        'nominal': nominal, 'created_at': datetime.now().strftime('%d/%m/%Y %H:%M')
                    })
                except Exception:
                    pass
                cursor.close(); conn.close()
                conn = None

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                    return jsonify({'status': 'success', 'transaction_id': display_id, 'numeric_id': tx_id, 'message': analysis['message']})
                return redirect('/app/driver')
            except Exception as e:
                print(f"Driver error: {e}")
                import traceback; traceback.print_exc()
                return jsonify({'status': 'error', 'msg': str(e)}), 500
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    @app.route('/api/driver/me')
    @role_required(['driver'])
    def api_driver_me():
        """Profil driver dari sesi (v2.4): nama, nopol, kendaraan, BBM, aktif."""
        try:
            driver_name = session_driver_name()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT name, nopol, vehicle_type, bbm_type, is_active FROM drivers WHERE name=%s",
                (driver_name,))
            profile = cursor.fetchone()
            cursor.close(); conn.close()
            if not profile or not profile.get('is_active'):
                return jsonify({'status': 'error', 'msg': 'Profil driver tidak ditemukan / nonaktif. Hubungi Admin.'}), 404
            return jsonify(profile)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        # Auth check: require login session to access uploaded files (IDOR prevention).
        if not session.get('user_name') and not session.get('driver_name'):
            return jsonify({'error': 'Login diperlukan'}), 401
        # Hardening (ISO/IEC 27001): file bukti dibuka inline, tapi cegah
        # MIME sniffing & eksekusi sebagai HTML (stored XSS).
        resp = make_response(send_from_directory(app.config['UPLOAD_FOLDER'], filename))
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Disposition'] = 'inline'
        resp.headers['Cache-Control'] = 'private, max-age=3600'
        return resp

    @app.route('/submit-trip', methods=['POST'])
    def submit_trip():
        """Process multi-destination trip log submission"""
        conn = None
        try:
            # v2.5: identitas driver WAJIB dari sesi login (jalur legacy ditutup)
            driver_name = session_driver_name()
            if not driver_name:
                return jsonify({'status': 'error', 'msg': 'Login driver wajib — buka /app/driver'}), 401
            driver_name = driver_name.strip().upper()
            nopol = request.form.get('nopol', '').strip().upper()
            trip_date = request.form.get('trip_date', datetime.now().strftime('%Y-%m-%d'))
            jam_berangkat = request.form.get('jam_keberangkatan', '')
            jam_tiba = request.form.get('jam_tiba', '')
            km_awal = int(request.form.get('km_awal', 0) or 0)
            km_akhir = int(request.form.get('km_akhir', 0) or 0)

            if not all([driver_name, nopol, jam_berangkat, km_awal > 0]):
                return jsonify({'status': 'error', 'msg': 'Driver, Nopol, Jam Berangkat, dan KM Awal wajib diisi!'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error — koneksi database gagal'}), 500
            cursor = conn.cursor()

            trip_display_id = generate_trip_display_id(conn)
            gps_lat = request.form.get('gps_lat', '')
            gps_lon = request.form.get('gps_lon', '')
            gps_address = request.form.get('gps_address', '')
            gps_kelurahan = request.form.get('gps_kelurahan', '')
            gps_kecamatan = request.form.get('gps_kecamatan', '')
            gps_kota = request.form.get('gps_kota', '')
            gps_provinsi = request.form.get('gps_provinsi', '')
            gps_kode_pos = request.form.get('gps_kode_pos', '')
            cursor.execute("""
                INSERT INTO trip_masters (display_id, driver_name, nopol, trip_date, jam_keberangkatan,
                                         jam_tiba, km_awal, km_akhir, status,
                                         gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                        %s, %s, %s, %s, %s, %s, %s, %s)
            """, (trip_display_id, driver_name, nopol, trip_date, jam_berangkat, jam_tiba or None, km_awal, km_akhir or 0,
                    gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos))
            trip_id = cursor.lastrowid

            lokasi_berangkat_list = request.form.getlist('lokasi_berangkat[]')
            pukul_berangkat_list = request.form.getlist('pukul_berangkat[]')
            km_berangkat_list = request.form.getlist('km_berangkat[]')
            lokasi_tujuan_list = request.form.getlist('lokasi_tujuan[]')
            pukul_tujuan_list = request.form.getlist('pukul_tujuan[]')
            km_tujuan_list = request.form.getlist('km_tujuan[]')
            # Referensi appointment (hasil integrasi appointment -> log perjalanan)
            appointment_id_list = request.form.getlist('appointment_id[]')

            detail_count = 0
            completed_appt_ids = []
            for i in range(len(lokasi_berangkat_list)):
                if lokasi_berangkat_list[i].strip() and lokasi_tujuan_list[i].strip():
                    appt_id = None
                    if i < len(appointment_id_list) and appointment_id_list[i].strip().isdigit():
                        appt_id = int(appointment_id_list[i])
                    cursor.execute("""
                        INSERT INTO trip_details (trip_master_id, no_urut, lokasi_berangkat,
                                                 pukul_berangkat, km_berangkat, lokasi_tujuan,
                                                 pukul_tujuan, km_tujuan, appointment_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (trip_id, i+1, lokasi_berangkat_list[i], pukul_berangkat_list[i] or None,
                          int(km_berangkat_list[i] or 0), lokasi_tujuan_list[i],
                          pukul_tujuan_list[i] or None, int(km_tujuan_list[i] or 0), appt_id))
                    detail_count += 1
                    # Auto-complete: driver mengonfirmasi kunjungan dengan submit log perjalanan
                    # yang memuat appointment tsb (hanya miliknya & masih assigned).
                    if appt_id:
                        cursor.execute(
                            "UPDATE appointments SET status='completed', completed_at=NOW(), "
                            "updated_at=NOW() WHERE id=%s AND status='assigned' AND driver_name=%s",
                            (appt_id, driver_name))
                        if cursor.rowcount:
                            completed_appt_ids.append(appt_id)

            conn.commit()

            # Notifikasi real-time utk setiap appointment yang auto-complete
            if completed_appt_ids:
                try:
                    from modules.notifications import push_marketing_notification
                    from modules.realtime import emit_event
                    c2 = conn.cursor(dictionary=True)
                    for aid in completed_appt_ids:
                        c2.execute(
                            "SELECT id, display_id, nasabah_name, marketing_username, "
                            "appointment_date FROM appointments WHERE id=%s", (aid,))
                        ar = c2.fetchone()
                        if not ar:
                            continue
                        push_marketing_notification(
                            ar['marketing_username'], 'appointment', 'completed',
                            f'Driver {driver_name} selesai mengunjungi {ar["nasabah_name"]} '
                            f'({ar["display_id"]}) via log perjalanan', ar['display_id'])
                        emit_event('appointment_update',
                                   {'action': 'completed', 'id': aid, 'display_id': ar['display_id'],
                                    'driver': driver_name, 'date': str(ar['appointment_date'])},
                                   room='appointments_board')
                        log_activity_async(aid, 'appointment_complete_by_trip', 'driver',
                                           driver_name, new_data={'trip_id': trip_id},
                                           ip=request.remote_addr)
                    c2.close()
                except Exception as e:
                    print(f"Appointment auto-complete notif error: {e}")

            log_activity_async(trip_id, 'trip_submit', 'driver', driver_name,
                              new_data={'details': detail_count}, ip=request.remote_addr)
            cursor.close(); conn.close()
            conn = None

            try:
                socketio.emit('new_trip_report', {
                    'id': trip_id, 'driver_name': driver_name, 'nopol': nopol,
                    'trip_date': trip_date, 'total_routes': detail_count, 'status': 'pending',
                    'created_at': datetime.now().strftime('%d/%m/%Y %H:%M')
                })
            except Exception:
                pass

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                return jsonify({'status': 'success', 'trip_id': trip_display_id, 'numeric_id': trip_id, 'routes': detail_count})
            return redirect('/app/driver')
        except Exception as e:
            print(f"Trip submit error: {e}")
            import traceback; traceback.print_exc()
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    from modules.helpers import generate_trip_display_id
