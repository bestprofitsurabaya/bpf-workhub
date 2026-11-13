"""Driver & PWA routes"""
from flask import (request, redirect, session,
                   send_from_directory, jsonify, make_response)
from modules.config import get_db_connection, get_master_connection
from modules.helpers import (save_file, resolve_driver_form_context, validate_bbm_for_vehicle,
                             ensure_all_master_data, generate_display_id, log_activity_async,
                             session_driver_name, role_required, sha256_file,
                             ensure_anti_fraud_schema, ensure_fuel_prices_schema)
from modules.engine import PerformanceAnalyzer
from modules.approvals import hook_create_approval  # v2.36.0
from modules.voucher_schema import ensure_voucher_schema  # v2.107.0
from datetime import datetime
import os
import json
import threading


def _register_proof_hashes(tx_id, display_id, driver_name, nopol, photo_meta, branch_db=''):
    """Catat hash bukti ke proof_registry (master) — best-effort (v2.49.3).

    Gagal tidak menggagalkan klaim (fail-open ala doc_integrity) — tapi
    duplikasi PENUH setelah foto ini tak terdeteksi hanya bila DB mati;
    saat startup normal registry selalu ada.
    """
    if not photo_meta:
        return False
    try:
        conn = get_master_connection()
        if not conn:
            return False
        cur = conn.cursor()
        try:
            for field, meta in photo_meta.items():
                h = (meta or {}).get('sha256')
                if not h:
                    continue
                cur.execute(
                    "INSERT INTO proof_registry (sha256, field, tx_id, display_id, "
                    "driver_name, nopol, branch_db) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (h, field, tx_id, display_id, driver_name, nopol, branch_db))
            conn.commit()
            return True
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        print(f"[proof_registry] gagal catat hash #{display_id}: {e}")
        return False


def register_driver_routes(app, socketio):
    # v2.49.3: pastikan kolom anti-kecurangan & registry bukti sudah ada
    # (master + tiap DB cabang) sebelum endpoint klaim dipakai. Idempoten.
    # v2.50.1: + tabel vehicle_fuel_prices (harga server-side, bug 584ba88).
    def _ensure_all_dbs():
        try:
            if ensure_anti_fraud_schema() and ensure_fuel_prices_schema():
                ensure_voucher_schema()
                from modules.branch_manager import list_branches
                from modules.config import get_db_connection as _gc
                from modules.branch_db_map import DEFAULT_BRANCH_CODE
                for b in (list_branches() or []):
                    if b.get('is_active') and b.get('db_name'):
                        c = _gc(branch_code=b.get('code'))
                        if c:
                            ensure_anti_fraud_schema(c)
                            ensure_fuel_prices_schema(c)
                            ensure_voucher_schema(c)
                            try:
                                c.close()
                            except Exception:
                                pass
        except Exception as e:
            print(f"[anti-fraud] ensure schema startup: {e}")
    try:
        threading.Thread(target=_ensure_all_dbs, daemon=True).start()
    except Exception:
        pass


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
                # v2.107.0 — voucher rekanan BUKAN jenis transaksi baru. Baris
                # tetap CLAIM; labelnya SPBU rekanan + kolom voucher terisi.
                # Driver tidak mengisi nominal pada mode voucher; server
                # menghitung dari nilai voucher cabang + kode harian.
                voucher_partner = (request.form.get('voucher_partner') or '').strip()[:120]
                nota_no = (request.form.get('nota_no') or '').strip()[:60]
                try:
                    liter_input = float(request.form.get('liter') or 0)
                except (TypeError, ValueError):
                    return jsonify({'status': 'error', 'msg': 'Liter harus angka'}), 400
                requested_voucher = (
                    (request.form.get('transaction_type') or '').strip().upper() == 'VOUCHER'
                    or str(request.form.get('is_voucher') or '').strip().lower() in ('1', 'true', 'yes')
                    or (spbu_type == 'rekanan' and bool(voucher_partner) and bool(nota_no))
                )
                is_voucher = requested_voucher
                if is_voucher:
                    spbu_type = 'rekanan'
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

                # --- Voucher: nilai dari konfigurasi cabang + kode harian ---
                voucher_value = 0.0
                daily_code = None
                if is_voucher:
                    if not voucher_partner or not nota_no:
                        cursor.close(); conn.close(); conn = None
                        return jsonify({'status': 'error',
                                        'msg': 'Nama SPBU mitra dan nomor nota wajib diisi untuk voucher'}), 400
                    if liter_input <= 0:
                        cursor.close(); conn.close(); conn = None
                        return jsonify({'status': 'error',
                                        'msg': 'Liter dari nota voucher wajib diisi'}), 400
                    from modules.routes_voucher import get_or_create_daily_code, read_voucher_config
                    cfg = read_voucher_config(conn)
                    daily_code = get_or_create_daily_code(conn)
                    voucher_value = float(cfg.get('value') or 130000)
                    nominal = voucher_value + daily_code
                    spbu_type = 'rekanan'

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

                # Voucher tanpa nomor seri: cegah input dobel pada hari yang sama
                # (ODO sama) dan nomor nota yang sama.
                if is_voucher:
                    cursor.execute(
                        "SELECT display_id FROM transactions WHERE transaction_type='CLAIM' "
                        "AND COALESCE(voucher_value, 0) > 0 "
                        "AND driver_name=%s AND nopol=%s AND DATE(created_at)=CURDATE() "
                        "AND odo_km=%s AND status<>'rejected' LIMIT 1",
                        (driver_name, nopol, odo_km))
                    dup = cursor.fetchone()
                    if dup:
                        cursor.close(); conn.close(); conn = None
                        return jsonify({'status': 'error',
                                        'msg': f"Voucher dengan ODO {odo_km} km hari ini sudah dicatat "
                                               f"({dup['display_id']}). Periksa kembali — satu pengisian satu voucher."}), 409
                    cursor.execute(
                        "SELECT display_id FROM transactions WHERE transaction_type='CLAIM' "
                        "AND COALESCE(voucher_value, 0) > 0 "
                        "AND nota_no=%s AND DATE(created_at)=CURDATE() AND status<>'rejected' LIMIT 1",
                        (nota_no,))
                    dup_nota = cursor.fetchone()
                    if dup_nota:
                        cursor.close(); conn.close(); conn = None
                        return jsonify({'status': 'error',
                                        'msg': f"Nomor nota {nota_no} sudah dipakai hari ini "
                                               f"({dup_nota['display_id']})."}), 409

                # --- Use server-side price, NOT client-provided ---
                # v2.50.1: tabel vehicle_fuel_prices dijasikan idempoten startup;
                # guard ini mencegah 500 bila tabel hilang lagi (fallback 10.000).
                try:
                    cursor.execute("SELECT price_per_liter FROM vehicle_fuel_prices WHERE vehicle_type=%s AND bbm_type=%s", (vehicle_type, bbm_type))
                    price_row = cursor.fetchone()
                    price_per_liter = float(price_row['price_per_liter']) if price_row and price_row.get('price_per_liter') else 10000
                except Exception as price_err:
                    print(f"[driver] fuel price fallback: {price_err}")
                    price_per_liter = 10000
                if is_voucher and liter_input > 0:
                    # Liter aktual dari nota voucher — bukan hasil bagi nominal,
                    # karena nilai voucher bisa berbeda dari harga per liter.
                    liter = liter_input
                else:
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
                def _photo_content_ok(filename):
                    """True bila file benar-benar gambar yang bisa dibuka.

                    Ekstensi saja tidak cukup: file teks bernama .jpg sebelumnya
                    lolos dan tersimpan sebagai bukti rusak.
                    """
                    if not filename:
                        return True
                    try:
                        from PIL import Image
                        with Image.open(os.path.join(upload_dir, filename)) as im:
                            im.verify()
                        return True
                    except Exception:
                        return False

                invalid_photos = [field for field, saved in (
                    ('foto_odo_sebelum', foto_odo_sebelum),
                    ('foto_nota_odo_sesudah', foto_nota_odo_sesudah),
                    ('foto_struk', foto_struk),
                    ('foto_struk_dispenser', foto_struk_dispenser),
                ) if saved and not _photo_content_ok(saved)]
                rejected_photos = [field for field, saved in (
                    ('foto_odo_sebelum', foto_odo_sebelum),
                    ('foto_nota_odo_sesudah', foto_nota_odo_sesudah),
                    ('foto_struk', foto_struk),
                    ('foto_struk_dispenser', foto_struk_dispenser),
                ) if request.files.get(field) and not saved]
                if invalid_photos:
                    for saved in (foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser):
                        if saved:
                            try:
                                _p = os.path.join(upload_dir, saved)
                                if os.path.exists(_p):
                                    os.remove(_p)
                            except OSError:
                                pass
                    cursor.close(); conn.close(); conn = None
                    return jsonify({'status': 'error',
                                    'msg': 'File foto tidak valid / rusak: ' + ', '.join(invalid_photos)}), 400
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

                # --- v2.49.3 anti-kecurangan bukti & input (audit 22 Okt 2026)
                # 1. ODO mundur DITOLAK hard (bukan hanya flag) — baseline
                #    hanya dari transaksi tervalidasi, bukan rejected/pending.
                cursor.execute(
                    "SELECT odo_km, display_id FROM transactions "
                    "WHERE nopol=%s AND status IN ('verified_ga','os_finance','archived') "
                    "ORDER BY created_at DESC LIMIT 1", (nopol,))
                previous = cursor.fetchone()
                if previous and odo_km < int(previous['odo_km'] or 0):
                    for saved in (foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser):
                        if saved:
                            try:
                                _p = os.path.join(upload_dir, saved)
                                if os.path.exists(_p):
                                    os.remove(_p)
                            except OSError:
                                pass
                    cursor.close(); conn.close(); conn = None
                    return jsonify({'status': 'error', 'msg':
                                    (f"ODO mundur: {odo_km} km < klaim valid terakhir "
                                     f"{int(previous['odo_km'])} km ({previous['display_id']}). "
                                     "Periksa pembacaan odometer; bila meter baru dipasang, "
                                     "laporkan GA/Admin untuk kalibrasi.")}), 400

                # 2. Kapasitas tangki fisik — liter hasil klaim tak boleh lewat
                #    kapasitas kendaraan (>100% tolak, >90% flag).
                capacity = 0
                try:
                    cursor.execute("SELECT fuel_capacity FROM vehicles WHERE vehicle_type=%s LIMIT 1", (vehicle_type,))
                    vrow = cursor.fetchone()
                    capacity = float(vrow['fuel_capacity'] or 0) if vrow and vrow.get('fuel_capacity') else 0
                except Exception:
                    capacity = 0
                if capacity > 0 and liter > capacity:
                    for saved in (foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser):
                        if saved:
                            try:
                                _p = os.path.join(upload_dir, saved)
                                if os.path.exists(_p):
                                    os.remove(_p)
                            except OSError:
                                pass
                    cursor.close(); conn.close(); conn = None
                    return jsonify({'status': 'error', 'msg':
                                    (f"Klaim {liter:.1f} L melebihi kapasitas tangki "
                                     f"{vehicle_type} ({capacity:.0f} L) — tidak mungkin fisik. "
                                     "Periksa nominal/odometer.")}), 400

                # 3. Cap nominal harian & mingguan per driver (soft — flag anomali,
                #    bukan tolak; batas diatur Admin per DB via system_config).
                anomaly_reasons = []
                if odo_repeat_check := (previous and int(previous['odo_km'] or 0) == odo_km):
                    anomaly_reasons.append('ODO tidak berubah dari klaim terakhir')
                try:
                    for cfg_key, days, label in (('bbm_daily_cap_driver', 1, 'harian'),
                                                 ('bbm_weekly_cap_driver', 7, 'mingguan')):
                        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (cfg_key,))
                        crow = cursor.fetchone()
                        cap = float(crow['config_value']) if crow and crow.get('config_value') else 0
                        if cap <= 0:
                            continue
                        cursor.execute(
                            "SELECT COALESCE(SUM(nominal),0) AS total FROM transactions "
                            "WHERE driver_name=%s AND transaction_type='CLAIM' "
                            "AND status <> 'rejected' "
                            f"AND created_at >= DATE_SUB(NOW(), INTERVAL {int(days)} DAY)", (driver_name,))
                        trow = cursor.fetchone()
                        total = float(trow['total'] or 0) if trow else 0.0
                        if total + nominal > cap:
                            anomaly_reasons.append(
                                f"Total klaim {label} akan melewati batas Rp{cap:,.0f} "
                                f"(Rp{total + nominal:,.0f})")
                except Exception as cap_err:
                    print(f"[bbm] cap check: {cap_err}")

                # 4. Duplikasi foto — hash konten vs registry master (30 hari).
                #    Foto struk/ODO yang sama dipakai ulang klaim apa pun → DITOLAK.
                photo_paths = {f: (os.path.join(upload_dir, fn) if fn else None)
                               for f, fn in (
                                   ('foto_odo_sebelum', foto_odo_sebelum),
                                   ('foto_nota_odo_sesudah', foto_nota_odo_sesudah),
                                   ('foto_struk', foto_struk),
                                   ('foto_struk_dispenser', foto_struk_dispenser))}
                photo_meta = {}
                dup_hits = []
                try:
                    reg_conn = None
                    mconn = get_master_connection()
                    if mconn:
                        cur2 = mconn.cursor(dictionary=True)
                        try:
                            cur2.execute(  # idempoten; registry di master
                                """CREATE TABLE IF NOT EXISTS proof_registry (
                                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                                    sha256 CHAR(64) NOT NULL,
                                    field VARCHAR(40) NOT NULL DEFAULT '',
                                    tx_id INT NOT NULL DEFAULT 0,
                                    display_id VARCHAR(30) DEFAULT '',
                                    driver_name VARCHAR(150) DEFAULT '',
                                    nopol VARCHAR(30) DEFAULT '',
                                    branch_db VARCHAR(60) DEFAULT '',
                                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    KEY idx_sha (sha256), KEY idx_created (created_at), KEY idx_tx (tx_id)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                            mconn.commit()
                            from modules.helpers import sha256_file, extract_photo_meta  # noqa
                            hashes = {}
                            for field, path in photo_paths.items():
                                if not path or not os.path.exists(path):
                                    continue
                                h = sha256_file(path)
                                if not h:
                                    continue
                                hashes[field] = h
                                meta = extract_photo_meta(path)
                                meta['sha256'] = h
                                meta['bytes'] = os.path.getsize(path)
                                photo_meta[field] = meta
                            if hashes:
                                ph = list(hashes.values())
                                fmt = ','.join(['%s'] * len(ph))
                                cur2.execute(
                                    f"SELECT r.sha256, r.display_id, r.created_at FROM proof_registry r "
                                    f"WHERE r.sha256 IN ({fmt}) AND r.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
                                    tuple(ph))
                                dup_hits = cur2.fetchall() or []
                        finally:
                            try:
                                cur2.close()
                            except Exception:
                                pass
                            try:
                                mconn.close()
                            except Exception:
                                pass
                except Exception as pr_err:
                    print(f"[bbm] proof registry: {pr_err}")
                if dup_hits:
                    for saved in photo_paths.values():
                        if saved:
                            try:
                                _p = saved
                                if os.path.exists(_p):
                                    os.remove(_p)
                            except OSError:
                                pass
                    ids = ', '.join(str(d.get('display_id') or '?') for d in dup_hits[:3])
                    cursor.close(); conn.close(); conn = None
                    return jsonify({'status': 'error', 'msg':
                                    (f"Foto bukti sudah pernah dipakai di klaim #{ids}. "
                                     "Setiap pengisian wajib foto asli baru — foto ulang "
                                     "di tempat pengisian.")}), 400
                if not photo_meta.get('foto_struk', {}).get('exif_datetime') and \
                   not photo_meta.get('foto_struk_dispenser', {}).get('exif_datetime'):
                    anomaly_reasons.append('Foto struk tanpa data exif kamera (periksa asal foto)')

                km_per_liter = 0
                if previous and previous['odo_km'] < odo_km and liter > 0:
                    km_per_liter = (odo_km - previous['odo_km']) / liter

                analysis = PerformanceAnalyzer.analyze_performance(nopol, km_per_liter, conn, vehicle_type, bbm_type)
                if anomaly_reasons:
                    analysis['is_anomaly'] = True
                    analysis['message'] = '; '.join(anomaly_reasons) + \
                        (f' | {analysis["message"]}' if analysis.get('message') else '')
                if capacity > 0 and liter > capacity * 0.9:
                    analysis['is_anomaly'] = True
                    analysis['message'] = (f"Pengisian {liter:.1f} L > 90% kapasitas tangki "
                                           f"({capacity:.0f} L) — verifikasi fisik struk")
                display_id = generate_display_id('BPF', conn)

                cursor.execute("""
                    INSERT INTO transactions (display_id, transaction_type, driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter,
                    odo_km, spbu_type, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser,
                    status, ml_anomaly_flag, km_per_liter, gps_latitude, gps_longitude, gps_address,
                    gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment, proof_meta,
                    voucher_value, daily_code, voucher_partner, nota_no)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (display_id, 'CLAIM', driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter,
                      odo_km, spbu_type, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk, foto_struk_dispenser,
                      analysis['is_anomaly'], km_per_liter, gps_lat, gps_lon, gps_address,
                      gps_kelurahan, gps_kecamatan, gps_kota, gps_provinsi, gps_kode_pos, jumlah_appointment,
                      (json.dumps(photo_meta, default=str) if photo_meta else None),
                      voucher_value, daily_code, (voucher_partner or None), (nota_no or None)))

                tx_id = cursor.lastrowid
                conn.commit()
                # v2.36.0: jurnal ACC berjenjang (Chief Driver → GA) untuk klaim.
                # Voucher diverifikasi langsung GA (bukan klaim reimbursement).
                if not is_voucher:
                    hook_create_approval(conn, 'bbm', tx_id, display_id=display_id, role='driver')
                # Registry hash bukti (best-effort, master DB — lintas cabang).
                _register_proof_hashes(tx_id, display_id, driver_name, nopol, photo_meta)
                log_activity_async(tx_id, 'create', 'driver', driver_name, ip=request.remote_addr)
                try:
                    socketio.emit('new_claim', {
                        'driver_name': driver_name, 'nopol': nopol, 'display_id': display_id,
                        'nominal': nominal, 'transaction_type': 'CLAIM',
                        'created_at': datetime.now().strftime('%d/%m/%Y %H:%M')
                    })
                except Exception:
                    pass
                cursor.close(); conn.close()
                conn = None

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                    label = 'Voucher' if is_voucher else 'Klaim'
                    return jsonify({'status': 'success', 'transaction_id': display_id, 'numeric_id': tx_id,
                                    'transaction_type': 'CLAIM', 'message': analysis['message'],
                                    'msg': f'{label} {display_id} terkirim'})
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
                """SELECT d.name, d.nopol, d.vehicle_type, d.bbm_type, d.is_active,
                          COALESCE(NULLIF(v.initial_odo_km, 0),
                                   (SELECT MAX(va.last_odometer) FROM vehicle_assets va
                                     WHERE va.nopol = d.nopol), 0) AS initial_odo_km,
                          (SELECT MAX(t.odo_km) FROM transactions t
                            WHERE t.nopol = d.nopol AND COALESCE(t.odo_km, 0) > 0) AS last_odo_km
                     FROM drivers d
                     LEFT JOIN vehicles v ON v.nopol = d.nopol
                    WHERE d.name=%s""",
                (driver_name,))
            profile = cursor.fetchone()
            cursor.close(); conn.close()
            if not profile or not profile.get('is_active'):
                return jsonify({'status': 'error', 'msg': 'Profil driver tidak ditemukan / nonaktif. Hubungi Admin.'}), 404
            return jsonify(profile)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        # Auth check: require login session to access uploaded files (IDOR prevention).
        if not session.get('user_name') and not session.get('driver_name'):
            return jsonify({'error': 'Login diperlukan'}), 401
        # v2.82.0: berkas FirstWork (foto KTP = dokumen identitas) HANYA untuk
        # Traineer/Admin yang berhak memverifikasi. Sebelumnya cukup punya sesi
        # login apa pun (driver/OB/marketing cabang lain) untuk membuka KTP bila
        # nama filenya diketahui. Jalur resmi: /api/first-work/<id>/ktp
        # (ter-scope cabang + tercatat di audit).
        _upload_path = str(filename or '').replace('\\', '/').lstrip('/')
        if _upload_path.startswith('first_work/') and \
                session.get('user_role') not in ('traineer', 'admin'):
            return jsonify({'error': 'Akses ditolak: berkas ini hanya untuk Traineer/Admin.'}), 403
        # v2.40.1: <filename> -> <path:filename> — foto bukti overtime disimpan
        # di SUBFOLDER uploads/overtime/ (URL 2 segmen) yang tidak tertangkap
        # route lama 1-segmen → preview & PDF foto form selalu 404.
        # send_from_directory tetap men-guard path traversal ('..').
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
            try:
                km_awal = int(request.form.get('km_awal', 0) or 0)
                km_akhir = int(request.form.get('km_akhir', 0) or 0)
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'msg': 'KM awal dan KM akhir harus angka!'}), 400

            if not all([driver_name, nopol, jam_berangkat, km_awal > 0]):
                return jsonify({'status': 'error', 'msg': 'Driver, Nopol, Jam Berangkat, dan KM Awal wajib diisi!'}), 400
            try:
                datetime.strptime(str(trip_date), '%Y-%m-%d')
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'msg': 'Tanggal trip tidak valid (format YYYY-MM-DD).'}), 400
            if km_akhir and km_akhir < km_awal:
                return jsonify({'status': 'error', 'msg':
                                f'KM akhir ({km_akhir}) tidak boleh lebih kecil dari KM awal ({km_awal}).'}), 400

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

            if detail_count == 0:
                conn.rollback()
                cursor.close(); conn.close(); conn = None
                return jsonify({'status': 'error',
                                'msg': 'Minimal 1 rute (lokasi berangkat & tujuan) wajib diisi!'}), 400

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
