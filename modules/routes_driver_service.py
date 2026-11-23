"""v2.131.0 — Catatan Tambahan Service Mobil (PWA driver → GA).

Driver mengisi keluhan kondisi kendaraan lewat tab Service. Data masuk ke
`driver_service_reports` dengan status SUBMITTED, langsung terlihat GA lewat
`/api/ga/service-reports`, lalu GA bisa menandai selesai/ditolak dan mencetak
dokumen resmi (PDF kop perusahaan).

Bukan pengganti `vehicle_service_logs` (log teknis GA/admin): ini adalah
laporan kondisi dari sudut pandang driver.
"""
from datetime import datetime

from flask import jsonify, request, session, make_response
import io

from modules.config import get_db_connection
from modules.helpers import role_required, log_activity_async, generate_display_id

DRIVER_ROLES = ['driver']
GA_ROLES = ['ga', 'ga_hr', 'admin']


def _actor():
    return str(session.get('user_name') or session.get('user_role') or 'system').strip()


def _row_to_dict(r):
    d = dict(r or {})
    for key in ('created_at', 'updated_at', 'reviewed_at'):
        if d.get(key) is not None and hasattr(d[key], 'isoformat'):
            d[key] = d[key].isoformat()
    return d


def register_driver_service_routes(app):
    # ------------------------------------------------------------------
    # DRIVER
    # ------------------------------------------------------------------
    @app.route('/api/driver/service', methods=['POST'])
    @role_required(DRIVER_ROLES)
    def api_driver_service_submit():
        data = request.get_json(silent=True) or {}
        # v2.131.1: keluhan dikirim sebagai daftar bernomor. Terima juga string
        # lama untuk kompatibilitas klien yang belum diperbarui.
        raw_items = data.get('keluhan_items')
        if isinstance(raw_items, list):
            rows = [str(x or '').strip() for x in raw_items]
            rows = [x for x in rows if x]
            keluhan = '\n'.join(f'{i + 1}. {x}' for i, x in enumerate(rows))
        else:
            keluhan = str(data.get('keluhan') or '').strip()
        if not keluhan:
            return jsonify({'status': 'error', 'msg': 'Catatan keluhan wajib diisi'}), 400
        if len(keluhan) > 2000:
            return jsonify({'status': 'error', 'msg': 'Catatan maksimal 2000 karakter'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            name = _actor().upper()
            cur.execute("""SELECT COALESCE(NULLIF(TRIM(display_name),''), name) AS display_name,
                                  nopol, vehicle_type
                           FROM drivers WHERE name=%s""", (name,))
            drv = cur.fetchone() or {}
            nopol = str(data.get('nopol') or drv.get('nopol') or '').strip().upper()
            vehicle = str(data.get('vehicle_type') or drv.get('vehicle_type') or '').strip().upper()
            if not nopol:
                return jsonify({'status': 'error', 'msg': 'Nopol tidak ditemukan di profil driver'}), 400
            try:
                km = int(float(data.get('km_kendaraan') or 0))
            except (TypeError, ValueError):
                km = 0
            # v2.131.1: KM diisi manual driver dan wajib > 0 (ODO profil bisa basi).
            if km <= 0:
                return jsonify({'status': 'error', 'msg': 'KM kendaraan wajib diisi manual dengan angka'}), 400

            display_id = generate_display_id('SRV', conn)
            cur.execute("""INSERT INTO driver_service_reports
                (display_id, driver_name, driver_display_name, nopol, vehicle_type,
                 km_kendaraan, keluhan, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'SUBMITTED',%s)""",
                (display_id, name, drv.get('display_name') or name, nopol, vehicle,
                 km, keluhan, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            new_id = cur.lastrowid
            log_activity_async(new_id, 'driver_service_submit', 'driver', name,
                               new_data={'display_id': display_id, 'nopol': nopol},
                               ip=request.remote_addr,
                               branch_code=session.get('branch_code', ''))
            try:
                from modules.realtime import emit_event
                emit_event('new_service_report', {
                    'id': new_id, 'display_id': display_id, 'nopol': nopol,
                    'driver_name': drv.get('display_name') or name,
                }, room='appointments_board')
            except Exception:
                pass
            return jsonify({'status': 'success', 'display_id': display_id, 'id': new_id,
                            'msg': f'Catatan service {display_id} terkirim ke GA.'})
        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            conn.close()

    @app.route('/api/driver/service')
    @role_required(DRIVER_ROLES)
    def api_driver_service_list():
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""SELECT * FROM driver_service_reports
                           WHERE driver_name=%s ORDER BY created_at DESC, id DESC LIMIT 100""",
                        (_actor().upper(),))
            return jsonify({'data': [_row_to_dict(r) for r in cur.fetchall()]})
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # GA / ADMIN
    # ------------------------------------------------------------------
    @app.route('/api/ga/service-reports')
    @role_required(GA_ROLES)
    def api_ga_service_reports():
        status = (request.args.get('status') or '').strip().upper()
        date_from = (request.args.get('from') or '').strip()
        date_to = (request.args.get('to') or '').strip()
        q = (request.args.get('q') or '').strip()

        def _parse_date(value):
            try:
                return datetime.strptime(value, '%Y-%m-%d')
            except (ValueError, TypeError):
                return None

        dfrom = _parse_date(date_from) if date_from else None
        dto = _parse_date(date_to) if date_to else None
        if (date_from and not dfrom) or (date_to and not dto):
            return jsonify({'status': 'error', 'msg': 'Format tanggal harus YYYY-MM-DD'}), 400
        if dfrom and dto and dfrom > dto:
            return jsonify({'status': 'error', 'msg': 'Tanggal dari tidak boleh setelah tanggal sampai'}), 400

        params, where = [], []
        if status in ('SUBMITTED', 'REVIEWED', 'REJECTED'):
            where.append('status=%s')
            params.append(status)
        if dfrom:
            where.append('DATE(created_at) >= %s')
            params.append(date_from)
        if dto:
            where.append('DATE(created_at) <= %s')
            params.append(date_to)
        if q:
            like = '%' + q + '%'
            where.append('(display_id LIKE %s OR nopol LIKE %s OR keluhan LIKE %s)')
            params.extend([like, like, like])
        sql = "SELECT * FROM driver_service_reports"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY FIELD(status,'SUBMITTED','REVIEWED','REJECTED'), created_at DESC LIMIT 300"
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(sql, params)
            return jsonify({'data': [_row_to_dict(r) for r in cur.fetchall()]})
        finally:
            cur.close()
            conn.close()

    @app.route('/api/ga/service-reports/bulk-review', methods=['POST'])
    @role_required(GA_ROLES)
    def api_ga_service_bulk_review():
        data = request.get_json(silent=True) or {}
        ids = data.get('ids')
        if not isinstance(ids, list) or not (1 <= len(ids) <= 50):
            return jsonify({'status': 'error',
                            'msg': 'ids harus berupa daftar 1 sampai 50'}), 400
        clean_ids = []
        for value in ids:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                return jsonify({'status': 'error',
                                'msg': 'ids harus berupa bilangan bulat positif'}), 400
            if value not in clean_ids:
                clean_ids.append(value)
        status = str(data.get('status') or '').strip().upper()
        if status not in ('REVIEWED', 'REJECTED'):
            return jsonify({'status': 'error',
                            'msg': 'Status harus REVIEWED atau REJECTED'}), 400
        note = str(data.get('ga_note') or '').strip()[:500]
        if status == 'REJECTED' and not note:
            return jsonify({'status': 'error',
                            'msg': 'ga_note wajib diisi untuk penolakan'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        actor = _actor()
        placeholders = ','.join(['%s'] * len(clean_ids))
        cur = conn.cursor(dictionary=True)
        try:
            # All-or-nothing: hanya baris yang masih SUBMITTED yang boleh diubah.
            cur.execute(
                f"SELECT id, status FROM driver_service_reports WHERE id IN ({placeholders})",
                clean_ids)
            found = {r['id']: r['status'] for r in cur.fetchall()}
            if any(found.get(rid) != 'SUBMITTED' for rid in clean_ids):
                conn.rollback()
                return jsonify({'status': 'error',
                                'msg': 'Sebagian laporan tidak ditemukan atau sudah diproses'}), 409
            cur.execute(
                f"""UPDATE driver_service_reports
                    SET status=%s, ga_note=%s, reviewed_by=%s, reviewed_at=NOW()
                    WHERE id IN ({placeholders}) AND status='SUBMITTED'""",
                [status, note, actor] + clean_ids)
            updated = cur.rowcount
            if updated != len(clean_ids):
                # Jika ada baris yang berubah status di antara pra-cek dan UPDATE,
                # batalkan seluruh batch — tidak boleh ada perubahan sebagian.
                conn.rollback()
                return jsonify({'status': 'error',
                                'msg': 'Sebagian laporan tidak ditemukan atau sudah diproses'}), 409
            conn.commit()
            for rid in clean_ids:
                log_activity_async(rid, 'driver_service_bulk', 'ga', actor,
                                   new_data={'id': rid, 'status': status, 'ga_note': note},
                                   ip=request.remote_addr,
                                   branch_code=session.get('branch_code', ''))
            return jsonify({'status': 'success', 'updated': updated})
        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            conn.close()

    @app.route('/api/ga/service-reports/<int:report_id>/review', methods=['POST'])
    @role_required(GA_ROLES)
    def api_ga_service_review(report_id):
        data = request.get_json(silent=True) or {}
        status = str(data.get('status') or '').strip().upper()
        if status not in ('REVIEWED', 'REJECTED'):
            return jsonify({'status': 'error', 'msg': 'Status harus REVIEWED atau REJECTED'}), 400
        note = str(data.get('ga_note') or '').strip()[:500]
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""UPDATE driver_service_reports
                           SET status=%s, ga_note=%s, reviewed_by=%s, reviewed_at=NOW()
                           WHERE id=%s AND status='SUBMITTED'""",
                        (status, note, _actor(), report_id))
            if not cur.rowcount:
                conn.rollback()
                return jsonify({'status': 'error', 'msg': 'Laporan tidak ditemukan atau sudah diproses'}), 409
            conn.commit()
            log_activity_async(report_id, 'driver_service_review', 'ga', _actor(),
                               new_data={'id': report_id, 'status': status},
                               ip=request.remote_addr,
                               branch_code=session.get('branch_code', ''))
            return jsonify({'status': 'success', 'msg': 'Laporan service diperbarui.'})
        finally:
            cur.close()
            conn.close()

    @app.route('/api/ga/service-reports/<int:report_id>/pdf')
    @role_required(GA_ROLES)
    def api_ga_service_pdf(report_id):
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM driver_service_reports WHERE id=%s", (report_id,))
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        if not row:
            return jsonify({'error': 'Laporan tidak ditemukan'}), 404

        from modules.driver_service_pdf import DriverServicePDF
        pdf = DriverServicePDF()
        try:
            pdf.set_identity(branch_code=session.get('branch_code', ''))
        except Exception:
            pass
        pdf.generate(row)
        buf = io.BytesIO()
        pdf.output(buf)
        buf.seek(0)
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = (
            f'attachment; filename=Form_Service_{row.get("display_id", report_id)}.pdf')
        return response
