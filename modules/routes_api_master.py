"""API Routes - Master Data (Vehicles, BBM, Drivers, Users)"""
from flask import request, jsonify, session
from mysql.connector import IntegrityError
from modules.config import get_db_connection, get_master_connection
from modules.helpers import (finalize_pin, log_activity_async, resolve_user_pin, role_required,
                             pin_rate_check, pin_fail, pin_success, client_ip)

# ================================================================
# Konvensi username v2.29.8/9: `{divisi}_{cabang}` — username WAJIB
# diawali token divisi untuk role back-office. Pengecualian:
#   - driver   : username = nama orang (login PWA pendek di HP)
#   - admin    : tetap "admin"
#   - it_*     : role per-cabang, username mengikuti role (it_sby, ...)
#   - legacy   : akun sistem/test lama yang masih dipakai (qa, test_check,
#                e2e_driver) — harus tetap bisa disimpan/ditoggle apa adanya.
# Username yang SUDAH ADA di DB dengan role sama (mis. hasil bulk-create
# marketing lama bernama orang) juga tetap boleh disimpan tanpa rename.
# ================================================================
_USERNAME_LEGACY = ('qa', 'test_check', 'e2e_driver')
_ROLE_USERNAME_PREFIX = {
    'ga': 'ga_',
    'finance': 'finance_',
    'marketing': 'marketing_',
    'ob': 'ob_',
    'chief_driver': 'chief_driver_',
    'receptionist': 'receptionist_',
    'traineer': 'traineer_',
    'ga_hr': 'gahr_',
}


def _username_prefix_error(username, role):
    """Pesan error bila username tidak diawali token divisi; None bila valid.

    Hanya berlaku untuk role ber-awalan divisi (lihat peta di atas). Role
    driver/admin/it_* dan akun legacy dibebaskan dari aturan awalan.
    """
    prefix = _ROLE_USERNAME_PREFIX.get(role)
    if not prefix:
        return None
    if username in _USERNAME_LEGACY:
        return None
    if username.startswith(prefix):
        return None
    return (f"Username wajib diawali '{prefix}' sesuai konvensi "
            f"{{divisi}}_{{cabang}} — mis. {prefix}sby (1 orang) / "
            f"{prefix}nama_sby (bila >1 orang per cabang). "
            f"Huruf kecil, angka, dan underscore saja.")


def _username_exists(conn, username, role):
    """True bila (username, role) sudah ada — akun lama tetap boleh disimpan."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username=%s AND role=%s LIMIT 1",
                       (username, role))
        found = cursor.fetchone() is not None
        cursor.close()
        return found
    except Exception:
        return False


def register_master_api(app):

    @app.route('/api/vehicles')
    def api_vehicles():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT vehicle_type, brand, fuel_capacity FROM vehicles WHERE is_active=TRUE ORDER BY vehicle_type")
            data = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/bbm_types')
    def api_bbm_types():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name, price_per_liter FROM bbm_types WHERE is_active=TRUE ORDER BY name")
            data = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/drivers')
    def api_drivers():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name, nopol, vehicle_type, bbm_type, is_active FROM drivers ORDER BY name")
            data = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/drivers/sync', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def sync_driver():
        try:
            data = request.get_json()
            n = data.get('driver_name', '').strip().upper()
            p = data.get('nopol', '').strip().upper()
            v = data.get('vehicle_type', 'AVANZA')
            b = data.get('bbm_type', 'PERTALITE')
            if not n: return jsonify({'status': 'error', 'msg': 'Nama driver wajib'}), 400
            if not p: p = n
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("INSERT INTO drivers (name, nopol, vehicle_type, bbm_type) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nopol=VALUES(nopol), vehicle_type=VALUES(vehicle_type), bbm_type=VALUES(bbm_type), is_active=TRUE", (n, p, v, b))
            conn.commit(); cursor.close(); conn.close()
            log_activity_async(0, 'driver_sync', 'admin', 'Admin', new_data={'driver': n, 'nopol': p}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'Driver {n} synced'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/drivers/<driver_name>/activate', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def activate_driver(driver_name):
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("UPDATE drivers SET is_active = TRUE WHERE name = %s", (driver_name,))
            conn.commit(); cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Driver {driver_name} activated'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/drivers/<driver_name>/deactivate', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def deactivate_driver(driver_name):
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("UPDATE drivers SET is_active=FALSE WHERE name=%s", (driver_name,))
            conn.commit(); cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Driver {driver_name} deactivated'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/drivers/<driver_name>/delete', methods=['POST', 'DELETE'])
    @role_required(['admin'])
    def delete_driver(driver_name):
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("DELETE FROM drivers WHERE name = %s", (driver_name,))
            conn.commit(); affected = cursor.rowcount; cursor.close(); conn.close()
            if affected > 0: return jsonify({'status': 'success', 'msg': f'Driver {driver_name} dihapus'})
            return jsonify({'status': 'error', 'msg': 'Driver tidak ditemukan'}), 404
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/drivers/pin-reset', methods=['POST'])
    @role_required(['admin'])
    def bulk_reset_driver_pin():
        """Reset PIN massal seluruh user ber-role driver (default 123456).

        Dipakai tombol 'Reset PIN Massal Driver' di SPA Settings (halaman admin).
        ISO/IEC 27001 A.9.4 — kredensial dikelola Admin (audit trail tercatat).
        """
        try:
            data = request.get_json(silent=True) or {}
            new_pin = str(data.get('new_pin', '123456') or '123456').strip()
            if not new_pin.isdigit() or len(new_pin) != 6:
                return jsonify({'status': 'error', 'msg': 'PIN harus 6 digit angka'}), 400
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            # Jumlah total akun driver (untuk laporan), lalu setel PIN semuanya.
            cursor.execute("SELECT COUNT(*) FROM users WHERE role='driver'")
            total = cursor.fetchone()[0]
            cursor.execute("UPDATE users SET pin=%s WHERE role='driver'", (new_pin,))
            affected = cursor.rowcount
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'bulk_driver_pin_reset', 'admin',
                               (session.get('full_name') or session.get('user_name') or 'Admin'),
                               new_data={'total': total, 'changed': affected},
                               ip=request.remote_addr)
            return jsonify({'status': 'success',
                            'msg': f'PIN {total} akun driver berhasil direset'})
        except Exception as e:
            print(f'[api-master] bulk_reset_pin error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500

    @app.route('/api/users')
    @role_required(['admin'])
    def api_users():
        try:
            conn = get_master_connection(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, username, full_name, role, team_name, branch_code, is_active, last_login FROM users ORDER BY role, username")
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/users/sync', methods=['POST'])
    @role_required(['admin'])
    def sync_user():
        try:
            data = request.get_json()
            u = data.get('username', '').strip(); f = data.get('full_name', '').strip()
            r = data.get('role', 'ga'); a = data.get('is_active', True)
            if r not in ('admin', 'ga', 'finance', 'marketing', 'chief_driver', 'driver', 'ob',
                         'receptionist', 'traineer', 'ga_hr', 'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'):
                return jsonify({'status': 'error', 'msg': 'Role tidak valid'}), 400
            if not u or not f: return jsonify({'status': 'error', 'msg': 'Username dan nama wajib'}), 400

            # v2.29.9: username wajib mengikuti konvensi {divisi}_{cabang}
            # (awalan divisi) utk role back-office. Simpan/toggle akun lama
            # yang sudah ada dgn (username, role) sama tetap diperbolehkan.
            prefix_err = _username_prefix_error(u, r)
            if prefix_err:
                conn = get_master_connection()
                ok_existing = _username_exists(conn, u, r) if conn else False
                if conn:
                    conn.close()
                if not ok_existing:
                    return jsonify({'status': 'error', 'msg': prefix_err}), 400

            # PIN hanya diubah bila dikirim eksplisit & tidak kosong (agar
            # toggle is_active / update role / delete tidak menimpa PIN user).
            pin = resolve_user_pin(data.get('pin'))

            # Team hanya diubah bila dikirim eksplisit (agar toggle is_active
            # atau update role tidak menghapus tim marketing yang sudah ada).
            team = None
            if 'team_name' in data:
                team = str(data.get('team_name', '') or '').strip()
                if r == 'marketing':
                    if not team:
                        return jsonify({'status': 'error', 'msg': 'User marketing wajib memiliki tim'}), 400
                    from modules.helpers import get_or_create_team
                    team = get_or_create_team(team)

            # Cabang hanya diubah bila dikirim eksplisit (paritas team_name/pin):
            # toggle aktif/nonaktif atau bulk action tidak menghapus branch_code.
            branch = None
            if 'branch_code' in data:
                branch = str(data.get('branch_code', '') or '').strip() or None

            conn = get_master_connection(); cursor = conn.cursor()
            if team is None or pin is None or branch is None:
                cursor.execute("SELECT team_name, pin, branch_code FROM users WHERE username=%s OR id=%s", (u, data.get('id')))
                row = cursor.fetchone()
                if team is None:
                    team = row[0] if row else ''
                if pin is None:
                    pin = finalize_pin(None, row[1] if row else None)
                if branch is None:
                    branch = row[2] if row else None

            # Edit user lama dipakai id (bila dikirim) supaya username juga bisa
            # diganti — username adalah kunci login, bukan primary key. Update
            # by-id ini juga menyimpan branch_code yang dipilih Admin.
            uid = data.get('id')
            if uid is not None:
                try:
                    cursor.execute(
                        "UPDATE users SET username=%s, full_name=%s, role=%s, pin=%s, "
                        "team_name=%s, branch_code=%s, is_active=%s WHERE id=%s",
                        (u, f, r, pin, team, branch, 1 if a else 0, uid))
                except IntegrityError:
                    conn.rollback()
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error', 'msg': 'Username sudah dipakai user lain'}), 400
                if cursor.rowcount == 0:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error', 'msg': 'User tidak ditemukan'}), 404
            else:
                cursor.execute("INSERT INTO users (username, full_name, role, pin, team_name, branch_code, is_active) VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE full_name=VALUES(full_name), role=VALUES(role), pin=VALUES(pin), team_name=VALUES(team_name), branch_code=VALUES(branch_code), is_active=VALUES(is_active)", (u, f, r, pin, team, branch, 1 if a else 0))
            conn.commit(); cursor.close(); conn.close()
            log_activity_async(0, 'user_sync', 'admin', 'Admin', new_data={'username': u, 'role': r, 'team': team, 'branch_code': branch}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'User {u} saved'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/users/bulk-create', methods=['POST'])
    @role_required(['admin'])
    def bulk_create_user_accounts():
        """Buat akun login sekaligus (PIN default 123456) untuk:

        - scope 'driver'   : seluruh driver AKTIF di tabel `drivers`
                             yang belum punya akun users (username = nama driver).
        - scope 'marketing': seluruh anggota AKTIF di tabel `marketing_members`
                             (dropdown User di form marketing) yang belum punya akun
                             (username = nama anggota, team_name ikut diset).
        - scope 'all'      : keduanya.

        Idempoten — akun yang sudah ada dilewati (tidak menimpa PIN/role).
        Username dirapikan: huruf kecil tanpa spasi (mis. WICAK → `wicak`),
        full_name memakai huruf kapital awal (title-case, mis. `Wicak`).
        Audit trail: user_bulk_create.
        """
        try:
            data = request.get_json(silent=True) or {}
            scope = str(data.get('scope', 'all') or 'all').strip().lower()
            new_pin = str(data.get('pin', '123456') or '123456').strip()
            if scope not in ('driver', 'marketing', 'all'):
                return jsonify({'status': 'error', 'msg': 'Scope tidak valid (driver/marketing/all)'}), 400
            if not new_pin.isdigit() or len(new_pin) != 6:
                return jsonify({'status': 'error', 'msg': 'PIN harus 6 digit angka'}), 400

            # Data driver/marketing dibaca dari DB cabang aktif (sesi);
            # akun users ditulis ke DB master dengan branch_code cabang aktif.
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            mconn = get_master_connection()
            if not mconn:
                conn.close()
                return jsonify({'status': 'error', 'msg': 'DB master error'}), 500
            cursor = conn.cursor(dictionary=True)
            mcur = mconn.cursor(dictionary=True)
            from modules.branch_manager import DEFAULT_BRANCH_CODE
            branch_code = session.get('branch_code') or DEFAULT_BRANCH_CODE

            created = []
            skipped = []

            def _tidy_username(raw):
                """Username rapi: huruf kecil, tanpa spasi/karakter aneh."""
                import re
                return re.sub(r'[^a-z0-9_.]', '', (raw or '').strip().lower())

            def _tidy_fullname(raw):
                """Nama tampilan rapi: title-case (mis. WICAK → Wicak)."""
                return (raw or '').strip().title()

            def _create(name, role, team=''):
                username = _tidy_username(name)
                full_name = _tidy_fullname(name)
                if not username:
                    skipped.append({'name': name or '?', 'reason': 'nama kosong'})
                    return
                mcur.execute("SELECT id FROM users WHERE username=%s", (username,))
                if mcur.fetchone():
                    skipped.append({'name': username, 'reason': 'akun sudah ada'})
                    return
                mcur.execute(
                    "INSERT INTO users (username, full_name, role, pin, team_name, branch_code, is_active) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 1)",
                    (username, full_name[:100], role, new_pin, (team or '')[:100], branch_code))
                created.append({'username': username, 'role': role, 'team': team or '', 'branch_code': branch_code})

            if scope in ('driver', 'all'):
                cursor.execute(
                    "SELECT name FROM drivers WHERE is_active=TRUE "
                    "AND name IS NOT NULL AND TRIM(name) <> '' ORDER BY name")
                for row in cursor.fetchall():
                    _create(row['name'], 'driver')

            if scope in ('marketing', 'all'):
                cursor.execute(
                    "SELECT member_name, team_name FROM marketing_members "
                    "WHERE is_active=1 ORDER BY team_name, member_name")
                for row in cursor.fetchall():
                    _create(row['member_name'], 'marketing', row['team_name'])

            mconn.commit()
            actor = session.get('full_name') or session.get('user_name') or 'Admin'
            log_activity_async(0, 'user_bulk_create', 'admin', actor,
                               new_data={'scope': scope, 'created': len(created),
                                         'skipped': len(skipped), 'pin': new_pin,
                                         'branch_code': branch_code},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            mcur.close(); mconn.close()
            return jsonify({
                'status': 'success',
                'msg': f'{len(created)} akun dibuat (PIN {new_pin}); {len(skipped)} dilewati',
                'created': created,
                'skipped': skipped,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/users/reset-pin', methods=['POST'])
    @role_required(['admin'])
    def reset_user_pin():
        try:
            data = request.get_json()
            username = data.get('username', '').strip(); new_pin = data.get('new_pin', '').strip()
            if not username or not new_pin or len(new_pin) != 6:
                return jsonify({'status': 'error', 'msg': 'Username dan PIN 6-digit wajib'}), 400
            conn = get_master_connection(); cursor = conn.cursor()
            cursor.execute("UPDATE users SET pin = %s WHERE username = %s", (new_pin, username))
            affected = cursor.rowcount; conn.commit(); cursor.close(); conn.close()
            if affected > 0:
                log_activity_async(0, 'user_reset_pin', 'admin', 'Admin', new_data={'username': username})
                return jsonify({'status': 'success', 'msg': f'PIN untuk {username} berhasil direset'})
            return jsonify({'status': 'error', 'msg': 'User tidak ditemukan'}), 404
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/verify-pin', methods=['POST'])
    def verify_pin():
        try:
            ip = client_ip()
            allowed, retry_after = pin_rate_check(ip)
            if not allowed:
                return jsonify({'status': 'error', 'msg': f'Terlalu banyak percobaan. Coba lagi dalam {retry_after // 60} menit.'}), 429
            data = request.get_json()
            username = data.get('username', '').strip(); pin = data.get('pin', '').strip()
            if not username or not pin: return jsonify({'status': 'error', 'msg': 'Username dan PIN wajib'}), 400
            conn = get_master_connection(); cursor = conn.cursor(dictionary=True)
            # NOTE: PIN is currently stored in plaintext — hashing migration
            # TODO: hash PINs with bcrypt/sha256 and compare server-side.
            cursor.execute("SELECT * FROM users WHERE username=%s AND pin=%s AND is_active=TRUE", (username, pin))
            user = cursor.fetchone()
            if user:
                pin_success(ip)
                cursor.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user['id'],))
                conn.commit(); cursor.close(); conn.close()
                return jsonify({'status': 'success', 'user': {'username': user['username'], 'full_name': user['full_name'], 'role': user['role']}})
            cursor.close(); conn.close()
            pin_fail(ip)
            return jsonify({'status': 'error', 'msg': 'PIN salah'}), 401
        except Exception as e:
            print(f'[api-master] verify_pin error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500

    @app.route('/api/vehicles/with-nopol')
    def api_vehicles_with_nopol():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT nopol, vehicle_type, bbm_default FROM vehicles WHERE is_active=1 AND nopol IS NOT NULL AND nopol != '' ORDER BY nopol")
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/vehicles/add', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_add_vehicle():
        try:
            data = request.get_json()
            nopol = data.get('nopol', '').strip().upper(); vehicle_type = data.get('vehicle_type', 'AVANZA').strip().upper()
            brand = data.get('brand', 'Toyota').strip(); bbm_default = data.get('bbm_default', 'PERTALITE').strip().upper()
            if not nopol: return jsonify({'status': 'error', 'msg': 'No. Polisi wajib'}), 400
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("INSERT INTO vehicles (vehicle_type, nopol, brand, fuel_capacity, bbm_default, is_active) VALUES (%s, %s, %s, 45, %s, 1) ON DUPLICATE KEY UPDATE vehicle_type=VALUES(vehicle_type), brand=VALUES(brand), bbm_default=VALUES(bbm_default), is_active=1", (vehicle_type, nopol, brand, bbm_default))
            conn.commit(); cursor.close(); conn.close()
            log_activity_async(0, 'vehicle_add', 'admin', 'Admin', new_data={'nopol': nopol, 'type': vehicle_type})
            return jsonify({'status': 'success', 'msg': f'Kendaraan {nopol} ({vehicle_type}) ditambahkan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/vehicle_bbm/<vehicle_type>')
    def api_vehicle_bbm(vehicle_type):
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""SELECT vba.bbm_type, vba.min_km_per_liter, vba.max_km_per_liter, vba.warning_km_per_liter, vba.good_km_per_liter, vba.is_default, bt.price_per_liter FROM vehicle_bbm_allowed vba JOIN bbm_types bt ON vba.bbm_type=bt.name WHERE vba.vehicle_type=%s AND bt.is_active=TRUE ORDER BY vba.is_default DESC""", (vehicle_type,))
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/vehicle-allowed-bbm/<vehicle_type>')
    def api_vehicle_allowed_bbm(vehicle_type):
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""SELECT vba.bbm_type, bt.price_per_liter, vba.is_default FROM vehicle_bbm_allowed vba JOIN bbm_types bt ON vba.bbm_type=bt.name WHERE vba.vehicle_type=%s AND bt.is_active=TRUE ORDER BY vba.is_default DESC""", (vehicle_type,))
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system-config/<config_key>')
    def api_system_config(config_key):
        try:
            conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (config_key,))
            row = cursor.fetchone(); cursor.close(); conn.close()
            return jsonify({'key': config_key, 'value': row['config_value'] if row else None})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/dummy-data/status')
    @role_required(['ga', 'finance', 'admin'])
    def dummy_data_status():
        try:
            conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_value FROM system_config WHERE config_key='dummy_data_enabled'")
            row = cursor.fetchone(); cursor.close(); conn.close()
            return jsonify({'enabled': row['config_value'] == 'true' if row else False})
        except Exception as e:
            return jsonify({'enabled': False, 'error': str(e)})

    @app.route('/api/dummy-data/toggle', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def toggle_dummy_data():
        try:
            data = request.get_json(); enable = data.get('enable', False)
            conn = get_db_connection(); cursor = conn.cursor()
            if enable:
                cursor.execute("""INSERT IGNORE INTO transactions (driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter, odo_km, spbu_type, status, km_per_liter, jumlah_appointment, is_dummy, gps_address) VALUES ('AKHAD','L 1413 CBI','AVANZA','PERTALITE',200000,20.00,10000,12936,'rekanan','archived',12.50,3,1,'Jl. Raya Darmo 45, Surabaya'),('AHMAT','B 2628 SRP','INNOVA','PERTAMAX',270000,20.00,13500,71126,'rekanan','archived',10.20,5,1,'Jl. Ahmad Yani 120, Surabaya')""")
            else: cursor.execute("DELETE FROM transactions WHERE is_dummy=1")
            cursor.execute("INSERT INTO system_config (config_key, config_value) VALUES ('dummy_data_enabled',%s) ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)", ('true' if enable else 'false',))
            conn.commit(); cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Dummy data {"enabled" if enable else "disabled"}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/system-config/<config_key>', methods=['PUT'])
    @role_required(['ga', 'finance', 'admin'])
    def api_update_system_config(config_key):
        try:
            data = request.get_json()
            value = data.get('value', '')
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)", (config_key, value))
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(0, 'config_update', 'admin', 'Admin', new_data={config_key: value})
            return jsonify({'status': 'success', 'msg': f'Konfigurasi {config_key} disimpan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # IDENTITAS PERUSAHAAN / CABANG (v2.19.2) — multi-cabang
    # Variabel branding (nama perusahaan, subjudul, nama sistem, versi)
    # bisa diubah Admin di /app/settings; dipakai PDF, login, sidebar,
    # watermark foto & judul dokumen.
    # ================================================================
    @app.route('/api/system-config/identity')
    def api_identity_get():
        """GET publik: identitas perusahaan/cabang (untuk branding pra-login)."""
        try:
            from modules.company_identity import get_company_identity
            return jsonify(get_company_identity())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system-config/identity', methods=['PUT'])
    @role_required(['admin'])
    def api_identity_put():
        """PUT admin: simpan identitas perusahaan/cabang (semua/beberapa key)."""
        try:
            from modules.company_identity import save_company_identity
            data = request.get_json(silent=True) or {}
            saved = save_company_identity(data)
            if not saved:
                return jsonify({'status': 'error',
                                'msg': 'Tidak ada key identitas valid (company_name/company_subtitle/system_name/system_version)'}), 400
            actor = session.get('full_name') or session.get('user_name') or 'Admin'
            log_activity_async(0, 'identity_update', 'admin', actor,
                               new_data=saved, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Identitas perusahaan disimpan', 'identity': saved})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DATA DEMO (v2.19.2) — dibuat & dibersihkan Admin (flexible)
    # - Rute demo  : appointment display_id berawalan 'DEMO-'
    # - Transaksi demo : transactions.is_dummy = 1
    # ================================================================
    DEMO_TX_SQL = """INSERT IGNORE INTO transactions
        (driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter,
         odo_km, spbu_type, status, km_per_liter, jumlah_appointment, is_dummy, gps_address)
        VALUES
        ('AKHAD','L 1413 CBI','AVANZA','PERTALITE',200000,20.00,10000,12936,'rekanan','archived',12.50,3,1,'Jl. Raya Darmo 45, Surabaya'),
        ('AHMAT','B 2628 SRP','INNOVA','PERTAMAX',270000,20.00,13500,71126,'rekanan','archived',10.20,5,1,'Jl. Ahmad Yani 120, Surabaya')"""

    def _valid_scope(scope):
        return scope in ('routes', 'transactions', 'all')

    @app.route('/api/demo/status')
    @role_required(['admin'])
    def api_demo_status():
        """Status data demo: jumlah appointment rute demo & transaksi dummy."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS c FROM appointments WHERE display_id LIKE 'DEMO-%'")
            demo_appts = cursor.fetchone()['c'] or 0
            cursor.execute("SELECT COUNT(*) AS c FROM transactions WHERE is_dummy=1")
            demo_tx = cursor.fetchone()['c'] or 0
            cursor.execute("SELECT config_value FROM system_config WHERE config_key='dummy_data_enabled'")
            row = cursor.fetchone()
            cursor.close(); conn.close()
            return jsonify({
                'demo_appointments': demo_appts,
                'demo_transactions': demo_tx,
                'dummy_enabled': row['config_value'] == 'true' if row else False,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/demo/seed', methods=['POST'])
    @role_required(['admin'])
    def api_demo_seed():
        """Buat data demo (idempoten): scope routes / transactions / all."""
        try:
            data = request.get_json(silent=True) or {}
            scope = str(data.get('scope', 'all') or 'all').strip().lower()
            if not _valid_scope(scope):
                return jsonify({'status': 'error', 'msg': 'Scope tidak valid (routes/transactions/all)'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            summary = {'routes': 0, 'transactions': 0, 'skipped_routes': 0, 'error': None}
            if scope in ('routes', 'all'):
                from scripts.seed_demo_routes import seed_demo_appointments
                res = seed_demo_appointments(conn=conn, commit=False)
                summary['routes'] = res['created']
                summary['skipped_routes'] = res['skipped']
                summary['error'] = res['error']
            if scope in ('transactions', 'all'):
                cursor.execute(DEMO_TX_SQL)
                summary['transactions'] = cursor.rowcount
                cursor.execute("INSERT INTO system_config (config_key, config_value) VALUES ('dummy_data_enabled','true') ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)")
            conn.commit()
            cursor.close(); conn.close()
            if summary['error']:
                return jsonify({'status': 'error', 'msg': summary['error']}), 400
            actor = session.get('full_name') or session.get('user_name') or 'Admin'
            log_activity_async(0, 'demo_seed', 'admin', actor, new_data=summary, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Data demo dibuat', 'summary': summary})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/demo/clean', methods=['POST'])
    @role_required(['admin'])
    def api_demo_clean():
        """Bersihkan data demo: scope routes / transactions / all (idempoten)."""
        try:
            data = request.get_json(silent=True) or {}
            scope = str(data.get('scope', 'all') or 'all').strip().lower()
            if not _valid_scope(scope):
                return jsonify({'status': 'error', 'msg': 'Scope tidak valid (routes/transactions/all)'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            summary = {'routes': 0, 'transactions': 0}
            if scope in ('routes', 'all'):
                from scripts.seed_demo_routes import clean_demo_appointments
                res = clean_demo_appointments(conn=conn, commit=False)
                summary['routes'] = res['deleted']
            if scope in ('transactions', 'all'):
                cursor.execute("DELETE FROM transactions WHERE is_dummy=1")
                summary['transactions'] = cursor.rowcount
                cursor.execute("INSERT INTO system_config (config_key, config_value) VALUES ('dummy_data_enabled','false') ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)")
            conn.commit()
            cursor.close(); conn.close()
            actor = session.get('full_name') or session.get('user_name') or 'Admin'
            log_activity_async(0, 'demo_clean', 'admin', actor, new_data=summary, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Data demo dibersihkan', 'summary': summary})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
