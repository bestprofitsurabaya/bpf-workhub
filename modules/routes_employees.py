"""Master karyawan — API daftar, detail, absensi, dan administrasi HR (Rilis D)."""
import csv
import io

from flask import Response, jsonify, request, session

from modules.config import get_master_connection
from modules.helpers import client_ip, log_activity_async, role_required
from modules import employee_service as es

ROLES = ['receptionist', 'ga_hr', 'admin']
HR_ROLES = ('ga_hr', 'admin')
HR_FIELDS = ('nama', 'jabatan', 'tanggal_masuk', 'status_kepegawaian',
             'atasan', 'no_hp', 'alamat', 'pendidikan_terakhir', 'branch_code')
NIK_FIELDS = ('nik',)


def _mask(nik):
    text = str(nik or '')
    return ('****' + text[-4:]) if text else ''


def _is_hr():
    return session.get('user_role') in HR_ROLES


def _scope():
    if _is_hr():
        return ''
    return str(session.get('branch_code') or '').upper()[:10] or '__NOBRANCH__'


def _visible(row, full=False):
    item = dict(row)
    nik = item.pop('nik', None)
    item['nik_masked'] = _mask(nik)
    if full:
        item['nik'] = nik
    if not full:
        for key in ('deactivation_reason', 'deactivated_by', 'email',
                    'kontak_darurat'):
            item.pop(key, None)
    return item


def _error(message, status):
    return jsonify({'status': 'error', 'msg': message}), status


def register_employee_routes(app):
    @app.route('/api/employees')
    @role_required(ROLES)
    def api_employees_list():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _error('DB error', 500)
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT * FROM employees ORDER BY id LIMIT 200')
                rows = cursor.fetchall() or []
            finally:
                cursor.close()
        except Exception:
            return _error('DB error', 500)
        finally:
            if conn:
                conn.close()

        q = (request.args.get('q') or '').strip().lower()
        active = (request.args.get('active') or '').strip()
        needs_nik = (request.args.get('needs_nik') or '').strip()
        branch = (request.args.get('branch_code') or '').strip().upper()
        scope = _scope()
        full = _is_hr()
        data = []
        for row in rows:
            if scope and str(row.get('branch_code') or '') != scope:
                continue
            if branch and full and str(row.get('branch_code') or '') != branch:
                continue
            if q and q not in str(row.get('nama') or '').lower() and \
                    q != str(row.get('nik') or ''):
                continue
            if active in ('0', '1') and int(bool(row.get('is_active'))) != int(active):
                continue
            if needs_nik == '1' and not row.get('needs_nik'):
                continue
            data.append(_visible(row, full))
        try:
            log_activity_async(None, 'employees_list', session.get('user_role', ''),
                               session.get('user_name', ''),
                               new_data={'count': len(data)}, ip=client_ip())
        except Exception:
            pass
        return jsonify({'data': data[:200]})

    @app.route('/api/employees/export.csv')
    @role_required(ROLES)
    def api_employees_export():
        if not _is_hr():
            return _error('Akses ditolak', 403)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _error('DB error', 500)
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT * FROM employees ORDER BY id LIMIT 2000')
                rows = cursor.fetchall() or []
            finally:
                cursor.close()
        except Exception:
            return _error('DB error', 500)
        finally:
            if conn:
                conn.close()
        active = (request.args.get('active') or '').strip()
        branch = (request.args.get('branch_code') or '').strip().upper()
        rows = [r for r in rows if (not active or
                int(bool(r.get('is_active'))) == int(active)) and
                (not branch or r.get('branch_code') == branch)]
        buf = io.StringIO()
        fields = ['employee_no', 'nik', 'nama', 'jabatan', 'branch_code',
                  'tanggal_masuk', 'status_kepegawaian', 'is_active']
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        resp = Response(buf.getvalue(), mimetype='text/csv')
        resp.headers['Content-Disposition'] = 'attachment; filename=employees.csv'
        resp.headers['Cache-Control'] = 'no-store'
        try:
            log_activity_async(None, 'employees_export', session.get('user_role', ''),
                               session.get('user_name', ''),
                               new_data={'count': len(rows)}, ip=client_ip())
        except Exception:
            pass
        return resp

    @app.route('/api/employees/<int:employee_id>')
    @role_required(ROLES)
    def api_employee_detail(employee_id):
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _error('DB error', 500)
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT * FROM employees WHERE id=%s', (employee_id,))
                row = cursor.fetchone()
                if not row:
                    return _error('Karyawan tidak ditemukan', 404)
                scope = _scope()
                if scope and str(row.get('branch_code') or '') != scope:
                    return _error('Data di luar cabang Anda', 403)
                cursor.execute(
                    """SELECT * FROM employee_attendance_events
                       WHERE employee_id=%s ORDER BY event_at DESC, id DESC
                       LIMIT 100""", (employee_id,))
                events = cursor.fetchall() or []
            finally:
                cursor.close()
        except Exception:
            return _error('DB error', 500)
        finally:
            if conn:
                conn.close()
        return jsonify({'data': {**_visible(row, _is_hr()), 'events': events[:100]}})

    @app.route('/api/employees/<int:employee_id>/attendance', methods=['POST'])
    @role_required(ROLES)
    def api_employee_attendance(employee_id):
        body = request.get_json(silent=True) or {}
        direction = str(body.get('direction') or '').upper()
        try:
            result = es.toggle_attendance(
                employee_id, direction, session.get('user_name', ''),
                session.get('full_name') or session.get('user_name', ''),
                session.get('branch_code', ''), note=body.get('note', ''))
        except ValueError as exc:
            code = str(exc)
            if code.startswith('already_'):
                return _error('Arah absensi sama seperti sebelumnya', 409)
            if code == 'wrong_branch':
                return _error('Data di luar cabang Anda', 403)
            return _error('Aksi tidak valid', 400)
        except Exception:
            return _error('DB error', 500)
        try:
            log_activity_async(None, 'employee_attendance', session.get('user_role', ''),
                               session.get('user_name', ''),
                               new_data={'employee_id': employee_id,
                                         'direction': direction}, ip=client_ip())
        except Exception:
            pass
        return jsonify({'status': 'success', 'data': result})

    @app.route('/api/employees/<int:employee_id>/attendance/<int:event_id>/void',
               methods=['POST'])
    @role_required(ROLES)
    def api_employee_attendance_void(employee_id, event_id):
        if not _is_hr():
            return _error('Akses ditolak', 403)
        reason = str((request.get_json(silent=True) or {}).get('reason') or '').strip()
        if not reason:
            return _error('Alasan koreksi wajib diisi', 400)
        try:
            result = es.void_attendance(employee_id, event_id, reason,
                                        session.get('user_name', ''))
        except ValueError as exc:
            return _error(str(exc), 409)
        except Exception:
            return _error('DB error', 500)
        try:
            log_activity_async(None, 'employee_attendance_void',
                               session.get('user_role', ''),
                               session.get('user_name', ''),
                               new_data={'employee_id': employee_id,
                                         'event_id': event_id}, ip=client_ip())
        except Exception:
            pass
        return jsonify({'status': 'success', 'data': result})

    @app.route('/api/employees/<int:employee_id>/deactivate', methods=['POST'])
    @role_required(ROLES)
    def api_employee_deactivate(employee_id):
        if not _is_hr():
            return _error('Akses ditolak', 403)
        reason = str((request.get_json(silent=True) or {}).get('reason') or '').strip()
        if not reason:
            return _error('Alasan wajib diisi', 400)
        try:
            result = es.deactivate_employee(employee_id, reason,
                                            session.get('user_name', ''))
        except ValueError as exc:
            return _error(str(exc), 400)
        except Exception:
            return _error('DB error', 500)
        return jsonify({'status': 'success', 'data': result})

    @app.route('/api/employees/<int:employee_id>/reactivate', methods=['POST'])
    @role_required(ROLES)
    def api_employee_reactivate(employee_id):
        if not _is_hr():
            return _error('Akses ditolak', 403)
        try:
            result = es.reactivate_employee(employee_id, session.get('user_name', ''))
        except ValueError as exc:
            return _error(str(exc), 404)
        except Exception:
            return _error('DB error', 500)
        return jsonify({'status': 'success', 'data': result})

    @app.route('/api/employees/<int:employee_id>', methods=['PATCH'])
    @role_required(ROLES)
    def api_employee_patch(employee_id):
        if not _is_hr():
            return _error('Akses ditolak', 403)
        body = request.get_json(silent=True) or {}
        fields = [f for f in HR_FIELDS + NIK_FIELDS if f in body]
        if not fields:
            return _error('Tidak ada field yang diubah', 400)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _error('DB error', 500)
            cursor = conn.cursor(dictionary=True)
            try:
                if 'nik' in fields:
                    new_nik = str(body['nik'] or '').strip()
                    if len(new_nik) != 16:
                        return _error('NIK harus 16 digit', 400)
                    cursor.execute('SELECT id FROM employees WHERE nik=%s AND id<>%s',
                                   (new_nik, employee_id))
                    if cursor.fetchone():
                        return _error('NIK sudah dipakai karyawan lain', 409)
                    body['needs_nik'] = 0
                    fields.append('needs_nik')
                sets = ', '.join(f'{f}=%s' for f in fields)
                cursor.execute(
                    f'UPDATE employees SET {sets}, updated_at=NOW() WHERE id=%s',
                    tuple(str(body[f] or '') if body[f] is not None else None
                          for f in fields) + (employee_id,))
                conn.commit()
            finally:
                cursor.close()
        except Exception:
            return _error('DB error', 500)
        finally:
            if conn:
                conn.close()
        try:
            log_activity_async(None, 'employee_patch', session.get('user_role', ''),
                               session.get('user_name', ''),
                               new_data={'employee_id': employee_id,
                                         'fields': fields}, ip=client_ip())
        except Exception:
            pass
        return jsonify({'status': 'success', 'data': {'employee_id': employee_id}})
