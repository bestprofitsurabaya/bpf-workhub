"""API Routes - Vehicle Assignments"""
import os

from flask import current_app, jsonify, request, session

from modules import assignment_swap_service as svc
from modules.config import get_db_connection
from modules.helpers import (log_activity_async, resolve_driver_scope,
                             role_required, save_file)
from modules.notifications import push_driver_notification


def ensure_assignment_tables(conn=None):
    """Migrasi tabel riwayat tukar driver (idempoten) — dipanggil app.py di startup.

    assignment_swaps dulu hanya di init.sql (DB baru), sehingga DB lama yang
    sudah hidup sebelum fitur swap memunculkan ERROR 1146 begitu endpoint
    swap/riwayat dipakai dari UI. Pola mengikuti ensure schema modul lain:
    conn opsional; bila diberikan dipakai langsung dan tidak ditutup di sini.
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[assignment-schema] DB unavailable, skip ensure')
            return False
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS assignment_swaps (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nopol VARCHAR(20) DEFAULT NULL,
                old_driver VARCHAR(100) DEFAULT NULL,
                new_driver VARCHAR(100) DEFAULT NULL,
                category VARCHAR(30) DEFAULT NULL,
                reason TEXT DEFAULT NULL,
                ga_name VARCHAR(100) DEFAULT NULL,
                request_id INT DEFAULT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_swap_created (created_at),
                INDEX idx_swap_nopol (nopol),
                INDEX idx_swap_request (request_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # v2.132.0 — antrean pengajuan driver (lihat init.sql).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS assignment_swap_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                request_code VARCHAR(24) DEFAULT NULL,
                branch_code VARCHAR(10) DEFAULT NULL,
                swap_type VARCHAR(10) NOT NULL DEFAULT 'exchange',
                requester_driver VARCHAR(100) NOT NULL,
                requester_nopol VARCHAR(20) NOT NULL,
                target_driver VARCHAR(100) DEFAULT NULL,
                target_nopol VARCHAR(20) NOT NULL,
                category VARCHAR(30) NOT NULL,
                reason VARCHAR(500) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                ga_name VARCHAR(100) DEFAULT NULL,
                ga_note VARCHAR(500) DEFAULT NULL,
                decided_at DATETIME DEFAULT NULL,
                executed_at DATETIME DEFAULT NULL,
                requester_odo INT DEFAULT NULL,
                requester_photo VARCHAR(255) DEFAULT NULL,
                requester_handover_at DATETIME DEFAULT NULL,
                target_odo INT DEFAULT NULL,
                target_photo VARCHAR(255) DEFAULT NULL,
                target_handover_at DATETIME DEFAULT NULL,
                completed_at DATETIME NULL DEFAULT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_swap_request_code (request_code),
                INDEX idx_swap_req_status (status, created_at),
                INDEX idx_swap_req_requester (requester_driver, status),
                INDEX idx_swap_req_target (target_driver, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # DB lama: assignment_swaps belum punya request_id.
        try:
            cur.execute(
                "SELECT COUNT(*) AS n FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'assignment_swaps' "
                "AND COLUMN_NAME = 'request_id'")
            row = cur.fetchone() or {}
            has_request_id = bool(row.get('n')) if isinstance(row, dict) else bool(row[0])
        except Exception:
            has_request_id = False
        if not has_request_id:
            try:
                cur.execute(
                    "ALTER TABLE assignment_swaps "
                    "ADD COLUMN request_id INT DEFAULT NULL, "
                    "ADD INDEX idx_swap_request (request_id)")
            except Exception as exc:
                text = str(exc)
                if '1060' not in text and 'Duplicate column' not in text:
                    raise

        try:
            conn.commit()
        except Exception:
            pass
        cur.close()
        print("✔ Assignment swaps schema ready")
        return True
    except Exception as e:
        print(f"[assignment-schema] error: {e}")
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def _swap_error_response(exc):
    payload = {'status': 'error', 'code': exc.code, 'msg': exc.msg}
    payload.update(exc.extra or {})
    return jsonify(payload), exc.http_status


def _session_branch():
    return (session.get('branch_code') or '').strip().upper()


def register_assignment_api(app):

    @app.route('/api/assignments/active')
    @role_required(['ga', 'finance', 'admin'])
    def api_active_assignments():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM vehicle_assignments WHERE is_current = 1 ORDER BY assigned_date DESC")
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assignments/history')
    @role_required(['ga', 'finance', 'admin'])
    def api_assignment_history():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT va.*, DATEDIFF(COALESCE(va.unassigned_date, CURDATE()), va.assigned_date) as duration_days FROM vehicle_assignments va ORDER BY va.id DESC LIMIT 100")
            history = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(history)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assignments/pending')
    @role_required(['driver', 'ga', 'finance', 'admin'])
    def api_pending_assignments():
        """Daftar assignment menunggu konfirmasi driver (v2.74.0 hardening).

        Dulu endpoint ini TANPA autentikasi — daftar penugasan (nama driver,
        nopol, catatan) bocor ke siapa pun. Kini wajib sesi; role driver hanya
        melihat baris miliknya sendiri (identitas dari sesi via
        `resolve_driver_scope`, bukan dari query string).
        """
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            if session.get('user_role') == 'driver':
                me = resolve_driver_scope('')
                if not me:
                    cursor.close(); conn.close()
                    return jsonify({'error': 'Login driver diperlukan'}), 401
                cursor.execute("SELECT * FROM vehicle_assignments WHERE is_current = 1 AND confirmed_by_driver = 0 AND driver_name = %s ORDER BY assigned_date DESC", (me,))
                pending = cursor.fetchall()
                # v2.132.0: assignment hasil tukar wajib memakai bukti
                # odometer + foto, bukan tombol konfirmasi biasa.
                for row in pending:
                    rid = svc.handover_request_for(conn, me, row.get('nopol'))
                    if rid:
                        row['handover_request_id'] = rid
            else:
                cursor.execute("SELECT * FROM vehicle_assignments WHERE is_current = 1 AND confirmed_by_driver = 0 ORDER BY assigned_date DESC")
                pending = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify(pending)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assignments/unassigned')
    @role_required(['ga', 'finance', 'admin'])
    def api_unassigned_vehicles():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT v.nopol, v.vehicle_type, COALESCE(v.bbm_default, 'PERTALITE') as bbm_type FROM vehicles v WHERE v.is_active = 1 AND v.nopol IS NOT NULL AND v.nopol != '' AND v.nopol NOT IN (SELECT va.nopol FROM vehicle_assignments va WHERE va.is_current = 1) ORDER BY v.nopol")
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assignments/swap-history')
    @role_required(['ga', 'finance', 'admin'])
    def api_swap_history():
        try:
            conn = get_db_connection()
            if not conn: return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM assignment_swaps ORDER BY created_at DESC LIMIT 100")
            data = cursor.fetchall(); cursor.close(); conn.close()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assignments/create', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_create_assignment():
        try:
            data = request.get_json()
            driver_name = data.get('driver_name', '').strip().upper()
            nopol = data.get('nopol', '').strip().upper()
            vehicle_type = data.get('vehicle_type', '').strip()
            bbm_type = data.get('bbm_type', 'PERTALITE').strip()
            notes = data.get('notes', '').strip()
            if not driver_name or not nopol: return jsonify({'status': 'error', 'msg': 'Driver dan Nopol wajib'}), 400
            conn = get_db_connection()
            if not conn: return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            try:
                # v2.132.0: transaksi + kunci baris agar pengajuan tukar driver
                # tidak dieksekusi di tengah perubahan manual GA (dan sebaliknya).
                conn.autocommit = False
                cursor.execute("SELECT id FROM vehicle_assignments WHERE (nopol = %s OR driver_name = %s) AND is_current = 1 FOR UPDATE", (nopol, driver_name))
                cursor.fetchall()
                # v2.78.0: satu driver hanya boleh punya SATU penugasan aktif.
                cursor.execute("UPDATE vehicle_assignments SET is_current = 0, unassigned_date = CURDATE() WHERE (nopol = %s OR driver_name = %s) AND is_current = 1", (nopol, driver_name))
                cursor.execute("INSERT INTO vehicle_assignments (driver_name, nopol, vehicle_type, bbm_type, assigned_date, is_current, driver_notes) VALUES (%s, %s, %s, %s, CURDATE(), 1, %s)", (driver_name, nopol, vehicle_type, bbm_type, notes))
                cursor.execute("INSERT INTO drivers (name, nopol, vehicle_type, bbm_type, is_active) VALUES (%s, %s, %s, %s, 1) ON DUPLICATE KEY UPDATE nopol = VALUES(nopol), vehicle_type = VALUES(vehicle_type), bbm_type = VALUES(bbm_type), is_active = 1", (driver_name, nopol, vehicle_type, bbm_type))
                svc.supersede_requests_for(cursor, [driver_name], [nopol],
                                           'Penugasan diubah oleh GA')
                svc.assert_single_active(cursor, [driver_name], [nopol])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close(); conn.close()
            log_activity_async(0, 'ga_assign_vehicle', 'ga', 'GA Officer', new_data={'driver': driver_name, 'nopol': nopol}, ip=request.remote_addr)
            push_driver_notification(driver_name, 'assignment', 'assigned',
                                     f'Kendaraan {nopol} ({vehicle_type}) ditugaskan ke Anda — konfirmasi serah terima', nopol)
            return jsonify({'status': 'success', 'msg': f'{driver_name} ditugaskan ke {nopol} ({vehicle_type})'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_swap_assignment():
        try:
            data = request.get_json()
            nopol = data.get('nopol', '').strip(); new_driver = data.get('new_driver', '').strip()
            category = data.get('category', 'other').strip(); reason = data.get('reason', '').strip()
            ga_name = data.get('ga_name', 'GA Officer').strip()
            if not all([nopol, new_driver, category, reason, ga_name]): return jsonify({'status': 'error', 'msg': 'Semua field wajib diisi'}), 400
            conn = get_db_connection()
            if not conn: return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                conn.autocommit = False
                cursor.execute("SELECT * FROM vehicle_assignments WHERE nopol = %s AND is_current = 1 ORDER BY id DESC LIMIT 1 FOR UPDATE", (nopol,))
                old = cursor.fetchone()
                old_driver = old['driver_name'] if old else None
                vehicle_type = old['vehicle_type'] if old else 'AVANZA'
                bbm_type = old['bbm_type'] if old else 'PERTALITE'
                if old: cursor.execute("UPDATE vehicle_assignments SET is_current = 0, unassigned_date = CURDATE() WHERE id = %s", (old['id'],))
                # v2.78.0: driver penerima hanya boleh punya satu penugasan aktif.
                cursor.execute("UPDATE vehicle_assignments SET is_current = 0, unassigned_date = CURDATE() WHERE driver_name = %s AND is_current = 1", (new_driver,))
                cursor.execute("INSERT INTO vehicle_assignments (driver_name, nopol, vehicle_type, bbm_type, assigned_date, is_current, driver_notes) VALUES (%s, %s, %s, %s, CURDATE(), 1, %s)", (new_driver, nopol, vehicle_type, bbm_type, reason))
                cursor.execute("UPDATE drivers SET nopol = %s, vehicle_type = %s, bbm_type = %s WHERE name = %s", (nopol, vehicle_type, bbm_type, new_driver))
                if old_driver: cursor.execute("UPDATE drivers SET nopol = '' WHERE name = %s AND nopol = %s", (old_driver, nopol))
                cursor.execute("INSERT INTO assignment_swaps (nopol, old_driver, new_driver, category, reason, ga_name) VALUES (%s, %s, %s, %s, %s, %s)", (nopol, old_driver, new_driver, category, reason, ga_name))
                touched_drivers = [d for d in (old_driver, new_driver) if d]
                svc.supersede_requests_for(cursor, touched_drivers, [nopol],
                                           'Penugasan diubah oleh GA')
                svc.assert_single_active(cursor, touched_drivers, [nopol])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close(); conn.close()
            log_activity_async(0, 'ga_swap_vehicle', 'ga', ga_name, new_data={'nopol': nopol, 'old_driver': old_driver, 'new_driver': new_driver}, ip=request.remote_addr)
            push_driver_notification(new_driver, 'assignment', 'swapped',
                                     f'Kendaraan {nopol} ditukar ke Anda — konfirmasi serah terima', nopol)
            if old_driver:
                push_driver_notification(old_driver, 'assignment', 'released',
                                         f'Kendaraan {nopol} dilepas dari Anda', nopol)
            return jsonify({'status': 'success', 'msg': f'{nopol} ditukar: {old_driver or "-"} → {new_driver}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/release', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_release_assignment():
        try:
            data = request.get_json()
            nopol = data.get('nopol', '').strip(); reason = data.get('reason', '').strip()
            ga_name = data.get('ga_name', 'GA Officer').strip()
            if not nopol or not reason: return jsonify({'status': 'error', 'msg': 'Nopol dan alasan wajib'}), 400
            conn = get_db_connection()
            if not conn: return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                conn.autocommit = False
                cursor.execute("SELECT * FROM vehicle_assignments WHERE nopol = %s AND is_current = 1 ORDER BY id DESC LIMIT 1 FOR UPDATE", (nopol,))
                assignment = cursor.fetchone()
                if not assignment:
                    return jsonify({'status': 'error', 'msg': f'Tidak ada assignment aktif untuk {nopol}'}), 404
                cursor.execute("UPDATE vehicle_assignments SET is_current = 0, unassigned_date = CURDATE(), cancel_reason = %s, cancelled_by = %s WHERE id = %s", (reason, ga_name, assignment['id']))
                cursor.execute("INSERT INTO assignment_swaps (nopol, old_driver, new_driver, category, reason, ga_name) VALUES (%s, %s, %s, %s, %s, %s)", (nopol, assignment['driver_name'], '- (Dilepas)', 'vehicle_issue', reason, ga_name))
                cursor.execute("SELECT nopol FROM vehicle_assignments WHERE driver_name = %s AND id < %s ORDER BY id DESC LIMIT 1", (assignment['driver_name'], assignment['id']))
                prev = cursor.fetchone()
                if prev and prev['nopol']: cursor.execute("UPDATE drivers SET nopol = %s WHERE name = %s", (prev['nopol'], assignment['driver_name']))
                else: cursor.execute("UPDATE drivers SET nopol = '' WHERE name = %s", (assignment['driver_name'],))
                svc.supersede_requests_for(cursor, [assignment['driver_name']], [nopol],
                                           'Penugasan diubah oleh GA')
                svc.assert_single_active(cursor, [assignment['driver_name']], [nopol])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close(); conn.close()
            log_activity_async(0, 'ga_release_vehicle', 'ga', ga_name, new_data={'nopol': nopol}, ip=request.remote_addr)
            push_driver_notification(assignment['driver_name'], 'assignment', 'released',
                                     f'Kendaraan {nopol} dilepas dari Anda', nopol)
            return jsonify({'status': 'success', 'msg': f'{nopol} dilepas dari {assignment["driver_name"]}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/confirm', methods=['POST'])
    def api_confirm_assignment():
        """Konfirmasi kendaraan oleh driver yang LOGIN.

        v2.47.1 (hardening): endpoint ini dulu TANPA autentikasi — siapa pun
        bisa menandai assignment terkonfirmasi atas nama driver mana pun
        hanya dengan menebak `driver_name`+`nopol` (dan termasuk daftar
        pengecualian CSRF). Kini identitas diambil dari sesi
        (`resolve_driver_scope`) — body tidak lagi dipercaya sebagai identitas.
        """
        try:
            data = request.get_json(silent=True) or {}
            driver_name = resolve_driver_scope(str(data.get('driver_name') or ''))
            if driver_name is None:
                return jsonify({'status': 'error', 'msg': 'Login driver wajib'}), 401
            nopol = str(data.get('nopol') or '').strip().upper()
            if not driver_name or not nopol:
                return jsonify({'status': 'error', 'msg': 'Data tidak lengkap'}), 400
            conn = get_db_connection()
            if not conn: return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            # v2.132.0: kendaraan hasil tukar WAJIB lewat bukti odometer+foto.
            # Guard hanya aktif bila masih ada pengajuan approved yang cocok
            # dengan nopol ini; pengajuan superseded tidak mengunci driver.
            if session.get('user_role') == 'driver':
                handover_id = svc.handover_request_for(conn, driver_name, nopol)
                if handover_id:
                    conn.close()
                    return jsonify({
                        'status': 'error', 'code': 'handover_required',
                        'request_id': handover_id,
                        'msg': 'Isi serah terima (odometer + foto) untuk kendaraan ini.'}), 409
            cursor = conn.cursor()
            cursor.execute("UPDATE vehicle_assignments SET confirmed_by_driver = 1, confirmed_at = NOW() WHERE driver_name = %s AND nopol = %s AND is_current = 1 AND confirmed_by_driver = 0 ORDER BY id DESC LIMIT 1", (driver_name, nopol))
            affected = cursor.rowcount; conn.commit(); cursor.close(); conn.close()
            if affected > 0: return jsonify({'status': 'success', 'msg': f'Konfirmasi {nopol} berhasil! ✅'})
            return jsonify({'status': 'error', 'msg': 'Tidak ada assignment pending'}), 404
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ========================================================
    # v2.132.0 — Driver mengajukan ganti kendaraan (tukar / pindah)
    # ========================================================

    @app.route('/api/assignments/swap-context')
    @role_required(['driver'])
    def api_swap_context():
        try:
            me = resolve_driver_scope('')
            if not me:
                return jsonify({'status': 'error', 'msg': 'Login driver diperlukan'}), 401
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                return jsonify(svc.fetch_context(conn, me, _session_branch()))
            finally:
                conn.close()
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests', methods=['POST'])
    @role_required(['driver'])
    def api_create_swap_request():
        try:
            me = resolve_driver_scope('')
            if not me:
                return jsonify({'status': 'error', 'msg': 'Login driver diperlukan'}), 401
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                row = svc.create_request(
                    conn, me,
                    swap_type=data.get('swap_type'),
                    target_driver=data.get('target_driver'),
                    target_nopol=data.get('target_nopol'),
                    category=data.get('category'),
                    reason=data.get('reason'),
                    branch_code=_session_branch())
            finally:
                conn.close()
            if row.get('target_driver'):
                push_driver_notification(
                    row['target_driver'], 'assignment', 'swap_request',
                    f"{row['requester_driver']} mengajukan tukar kendaraan "
                    f"({row['requester_nopol']} \u2194 {row['target_nopol']}). "
                    'Menunggu persetujuan GA.', str(row['id']))
            log_activity_async(0, 'driver_swap_request', 'driver', me,
                               new_data={'request': row.get('request_code'),
                                         'type': row.get('swap_type')},
                               ip=request.remote_addr,
                               branch_code=_session_branch())
            return jsonify(row), 201
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests')
    @role_required(['driver', 'ga', 'finance', 'admin'])
    def api_list_swap_requests():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                status = (request.args.get('status') or '').strip() or None
                if session.get('user_role') == 'driver':
                    me = resolve_driver_scope('')
                    if not me:
                        return jsonify({'status': 'error', 'msg': 'Login driver diperlukan'}), 401
                    rows = svc.list_requests(conn, me, status)
                else:
                    rows = svc.list_requests(conn, None, status)
            finally:
                conn.close()
            return jsonify(rows)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests/<int:request_id>/cancel', methods=['POST'])
    @role_required(['driver'])
    def api_cancel_swap_request(request_id):
        try:
            me = resolve_driver_scope('')
            if not me:
                return jsonify({'status': 'error', 'msg': 'Login driver diperlukan'}), 401
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                row = svc.cancel_request(conn, request_id, me)
            finally:
                conn.close()
            return jsonify(row)
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests/<int:request_id>/approve',
               methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_approve_swap_request(request_id):
        try:
            data = request.get_json(silent=True) or {}
            ga_name = (session.get('user_name') or session.get('full_name')
                       or 'GA Officer')
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                row = svc.approve_request(
                    conn, request_id, ga_name,
                    acknowledge_supersede=bool(data.get('acknowledge_supersede')))
                code = row.get('request_code') or f'#{request_id}'
                parties = [row['requester_driver']]
                if row.get('target_driver'):
                    parties.append(row['target_driver'])
                action = ('Pindah kendaraan disetujui'
                          if row.get('swap_type') == 'move'
                          else 'Tukar disetujui')
                for name in parties:
                    received = (row['target_nopol']
                                if name == row['requester_driver']
                                else row['requester_nopol'])
                    push_driver_notification(
                        name, 'assignment', 'swap_approved',
                        f'{action} ({code}): Anda menerima {received}. '
                        'Isi serah terima (odometer + foto).', str(request_id))
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT * FROM assignment_swap_requests WHERE status = 'superseded' "
                    "AND ga_note LIKE %s", (f'Ditutup karena {code}%',))
                for old in cursor.fetchall():
                    push_driver_notification(
                        old['requester_driver'], 'assignment', 'swap_superseded',
                        f"Pengajuan {old.get('request_code') or old['id']} ditutup "
                        'karena tukar berikutnya disetujui.', str(old['id']))
                cursor.close()
            finally:
                conn.close()
            log_activity_async(0, 'ga_swap_request_approve', 'ga', ga_name,
                               new_data={'request': row.get('request_code'),
                                         'type': row.get('swap_type')},
                               ip=request.remote_addr,
                               branch_code=_session_branch())
            return jsonify(row)
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests/<int:request_id>/reject',
               methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_reject_swap_request(request_id):
        try:
            data = request.get_json(silent=True) or {}
            ga_name = (session.get('user_name') or session.get('full_name')
                       or 'GA Officer')
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                row = svc.reject_request(
                    conn, request_id, ga_name,
                    data.get('note') or data.get('reason'))
            finally:
                conn.close()
            push_driver_notification(
                row['requester_driver'], 'assignment', 'swap_rejected',
                f"Pengajuan ganti kendaraan ditolak: {row.get('ga_note') or '-'}",
                str(request_id))
            log_activity_async(0, 'ga_swap_request_reject', 'ga', ga_name,
                               new_data={'request': row.get('request_code')},
                               ip=request.remote_addr,
                               branch_code=_session_branch())
            return jsonify(row)
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignments/swap-requests/<int:request_id>/handover',
               methods=['POST'])
    @role_required(['driver'])
    def api_submit_swap_handover(request_id):
        try:
            me = resolve_driver_scope('')
            if not me:
                return jsonify({'status': 'error', 'msg': 'Login driver diperlukan'}), 401
            folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            try:
                req = svc.get_request(conn, request_id)
                if not req:
                    return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan'}), 404
                side = svc.handover_side(req, me)
                if not side:
                    return jsonify({'status': 'error',
                                    'msg': 'Anda bukan pihak pada pengajuan ini'}), 403
                nopol = svc.received_nopol(req, side)
                saved = save_file(request.files.get('photo'), 'SWAP', nopol, folder)
                if not saved:
                    return jsonify({'status': 'error', 'code': 'photo',
                                    'msg': 'Foto kendaraan wajib (JPG/PNG/PDF)'}), 400
                try:
                    row = svc.submit_handover(
                        conn, request_id, me,
                        request.form.get('odometer'), saved)
                except Exception:
                    try:
                        os.remove(os.path.join(folder, saved))
                    except OSError:
                        pass
                    raise
            finally:
                conn.close()
            parties = [row['requester_driver']]
            if row.get('target_driver'):
                parties.append(row['target_driver'])
            if row.get('status') == 'completed':
                for name in parties:
                    push_driver_notification(
                        name, 'assignment', 'swap_completed',
                        'Serah terima tukar kendaraan selesai.', str(request_id))
            else:
                for name in parties:
                    if name != me:
                        push_driver_notification(
                            name, 'assignment', 'swap_waiting',
                            'Rekan sudah mengisi serah terima — lengkapi milik Anda.',
                            str(request_id))
            return jsonify(row)
        except svc.SwapError as e:
            return _swap_error_response(e)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assignment-remark', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def api_assignment_remark():
        try:
            data = request.get_json()
            nopol = data.get('nopol', '').strip(); remark = data.get('remark', '').strip()
            driver_name = data.get('driver_name', '').strip()
            if not nopol or not remark: return jsonify({'status': 'error', 'msg': 'Nopol dan remark wajib'}), 400
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("SELECT id FROM vehicle_assignments WHERE nopol = %s AND is_current = 1 ORDER BY id DESC LIMIT 1", (nopol,))
            existing = cursor.fetchone()
            if existing: cursor.execute("UPDATE vehicle_assignments SET driver_notes = %s WHERE id = %s", (remark, existing[0]))
            else: cursor.execute("INSERT INTO vehicle_assignments (driver_name, nopol, vehicle_type, bbm_type, assigned_date, is_current, driver_notes) SELECT name, nopol, vehicle_type, bbm_type, CURDATE(), 1, %s FROM drivers WHERE nopol = %s AND is_active = 1 LIMIT 1", (remark, nopol))
            conn.commit(); cursor.close(); conn.close()
            log_activity_async(0, 'ga_remark', 'ga', driver_name or 'GA Officer', new_data={'nopol': nopol, 'remark': remark}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Remark berhasil disimpan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
