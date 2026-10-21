"""Sistem Pelamar Kerja (v2.16) — form pelamar -> Receptionist -> Traineer.

Alur bisnis (menggantikan Google Form + Google Sheet):
  - Pelamar kerja mengisi form publik (nama, pendidikan, HP, upline, user,
    posisi). Tanggal & jam interview diambil OTOMATIS dari timestamp submit.
  - Receptionist: verifikator data, bisa mengubah data bila ada kesalahan input,
    mengelola kehadiran (interview + 4 hari training), mencatat pengunduran diri
    (alasan WAJIB bila pelamar sudah hadir), dan membuat laporan PDF resmi
    berlogo BPF per tahap.
  - Traineer/Upline: memantau kehadiran orang yang direkrutnya (scope = upline
    miliknya), dengan search & filter tanggal/user/upline.
"""
import io
import time
from datetime import datetime, date

from flask import (request, jsonify, session, make_response)
from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async,
                             generate_display_id, applicant_stage_label,
                             applicant_status_label)
from modules.pdf_generator import ApplicantReportPDF
from modules.stepup import stepup_required

VALID_STAGES = ('interview', 'training_1', 'training_2', 'training_3', 'training_4')
TRAINING_STAGES = ('training_1', 'training_2', 'training_3', 'training_4')
STAGE_ORDER = {s: i for i, s in enumerate(VALID_STAGES)}
TERMINAL_STATUSES = ('lulus', 'resigned', 'rejected')
STATUS_LABELS = {
    'interview': '📅 Interview',
    'training_1': '📘 Training H1',
    'training_2': '📗 Training H2',
    'training_3': '📙 Training H3',
    'training_4': '📕 Training H4',
    'lulus': '🎓 Lulus',
    'resigned': '🚪 Mengundurkan Diri',
    'rejected': '✕ Ditolak',
}

# Rate limit form publik: maks 10 submit / 10 menit per IP (anti spam).
# (Rate limit per-proses — cukup untuk satu instance web; lihat catatan bawah.)
_SUBMIT_MAX = 10
_SUBMIT_WINDOW = 600
_submit_log = {}


def _serialize(row):
    """Konversi nilai DB (datetime/date/timedelta) ke string JSON-safe."""
    if not row:
        return row
    row = dict(row)
    for k, v in row.items():
        if isinstance(v, datetime):
            row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(v, date):
            row[k] = v.isoformat()
    return row


def _rate_ok(ip):
    """Izinkan maks _SUBMIT_MAX submit dalam _SUBMIT_WINDOW detik per IP."""
    now = time.time()
    ts = [t for t in _submit_log.get(ip, []) if now - t < _SUBMIT_WINDOW]
    if len(ts) >= _SUBMIT_MAX:
        _submit_log[ip] = ts
        return False
    ts.append(now)
    _submit_log[ip] = ts
    return True


def _current_user():
    return {
        'username': session.get('user_name', ''),
        'full_name': session.get('full_name', session.get('user_name', '')),
        'role': session.get('user_role', ''),
    }


def _traineer_upline():
    """Scope upline untuk role traineer: username & full_name akunnya sendiri.

    Pelamar menulis UPLINE bebas (bisa nama lengkap/username traineer), jadi
    filter scope memakai LIKE kecocokan parsial (case-insensitive).
    """
    if session.get('user_role') == 'traineer':
        uname = (session.get('user_name') or '').strip()
        fname = (session.get('full_name') or '').strip()
        names = [n for n in (uname, fname) if n]
        return names or [uname]
    return None


def _parse_date(value, label):
    """Parse YYYY-MM-DD; raise ValueError bila format salah."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} harus format YYYY-MM-DD')


def _load_attendance_map(cursor, applicant_ids):
    """{applicant_id: {stage: {'attended_at':..., 'note':..., 'marked_by':...}}}"""
    if not applicant_ids:
        return {}
    fmt = ','.join(['%s'] * len(applicant_ids))
    cursor.execute(
        f"SELECT applicant_id, stage, attended_at, note, marked_by "
        f"FROM applicant_attendance WHERE applicant_id IN ({fmt})", list(applicant_ids))
    out = {}
    for r in cursor.fetchall():
        out.setdefault(r['applicant_id'], {})[r['stage']] = {
            'attended_at': r['attended_at'],
            'note': r['note'] or '',
            'marked_by': r['marked_by'] or '',
        }
    return out


def register_applicant_routes(app):

    # ================================================================
    # FORM PUBLIK — submit pelamar baru (tanpa login)
    # ================================================================
    @app.route('/api/applicants', methods=['POST'])
    def api_apply_submit():
        try:
            ip = request.remote_addr or '?'
            if not _rate_ok(ip):
                return jsonify({'status': 'error',
                                'msg': 'Terlalu banyak pendaftaran dari perangkat ini. '
                                       'Coba lagi beberapa saat.'}), 429
            data = request.get_json(silent=True) or {}
            nama = str(data.get('nama_lengkap', '') or '').strip()
            pendidikan = str(data.get('pendidikan', '') or '').strip()[:100]
            no_hp = str(data.get('no_hp', '') or '').strip()[:30]
            upline = str(data.get('upline', '') or '').strip()[:100]
            user_field = str(data.get('user', '') or '').strip()[:100]
            posisi = str(data.get('posisi', '') or '').strip()[:100]

            if not nama:
                return jsonify({'status': 'error', 'msg': 'Nama Lengkap wajib diisi'}), 400
            if not no_hp:
                return jsonify({'status': 'error', 'msg': 'Nomor Telepon/HP wajib diisi'}), 400
            if len(nama) > 150:
                return jsonify({'status': 'error', 'msg': 'Nama maksimal 150 karakter'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            display_id = generate_display_id('PLM', conn)
            now = datetime.now()
            cursor.execute(
                """INSERT INTO applicants
                   (display_id, nama_lengkap, pendidikan, no_hp, upline, user_field,
                    posisi, interview_at, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'interview')""",
                (display_id, nama, pendidikan, no_hp, upline, user_field,
                 posisi, now))
            conn.commit()
            log_activity_async(None, 'applicant_submit', 'public', nama,
                               new_data={'display_id': display_id}, ip=ip)
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'success',
                'msg': 'Pendaftaran berhasil! Interview Anda tercatat otomatis.',
                'display_id': display_id,
                'interview_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # META — pilihan filter (upline, user, status)
    # ================================================================
    @app.route('/api/applicants/meta')
    @role_required(['receptionist', 'traineer', 'admin'])
    def api_applicants_meta():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT DISTINCT upline FROM applicants WHERE upline<>'' ORDER BY upline")
            uplines = [r['upline'] for r in cursor.fetchall()]
            cursor.execute(
                "SELECT DISTINCT user_field FROM applicants WHERE user_field<>'' ORDER BY user_field")
            users = [r['user_field'] for r in cursor.fetchall()]
            cursor.execute(
                "SELECT id, name FROM applicant_user_options WHERE is_active=1 ORDER BY name")
            user_options = cursor.fetchall()
            cursor.close()
            conn.close()
            return jsonify({'uplines': uplines, 'users': users,
                            'user_options': user_options,
                            'statuses': [{'value': k, 'label': v} for k, v in STATUS_LABELS.items()]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # USER OPTIONS — dropdown 'User' pada form pelamar.
    # Data diatur oleh Receptionist (tambah/rename/nonaktifkan/hapus);
    # nilai awal di-seed dari daftar User unik pada Google Sheet lama.
    # ================================================================
    @app.route('/api/applicants/user-options', methods=['GET'])
    def api_user_options_list():
        """Daftar opsi User AKTIF (dipakai form publik & edit receptionist)."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, name FROM applicant_user_options "
                "WHERE is_active=1 ORDER BY name")
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'options': rows})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/applicants/user-options/manage', methods=['GET'])
    @role_required(['receptionist', 'admin'])
    def api_user_options_manage():
        """Semua opsi (termasuk nonaktif) untuk kelola di dashboard Receptionist."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, name, is_active, created_at FROM applicant_user_options "
                "ORDER BY is_active DESC, name")
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'options': rows})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/applicants/user-options', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_user_options_add():
        try:
            data = request.get_json(silent=True) or {}
            name = str(data.get('name', '') or '').strip()[:100]
            if not name:
                return jsonify({'status': 'error', 'msg': 'Nama opsi wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("INSERT INTO applicant_user_options (name) VALUES (%s)", (name,))
            new_id = cursor.lastrowid
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'user_option_add', user['role'], user['full_name'],
                               new_data={'name': name}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Opsi "{name}" ditambahkan', 'id': new_id})
        except Exception as e:
            # Duplikat (UNIQUE name) -> pesan jelas
            if 'Duplicate' in str(e):
                return jsonify({'status': 'error', 'msg': 'Opsi dengan nama tersebut sudah ada'}), 409
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/applicants/user-options/<int:opt_id>', methods=['PATCH'])
    @role_required(['receptionist', 'admin'])
    def api_user_options_patch(opt_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applicant_user_options WHERE id=%s", (opt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Opsi tidak ditemukan'}), 404
            fields, params = [], []
            if 'name' in data:
                name = str(data['name'] or '').strip()[:100]
                if not name:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error', 'msg': 'Nama opsi tidak boleh kosong'}), 400
                fields.append('name = %s'); params.append(name)
            if 'is_active' in data:
                fields.append('is_active = %s')
                params.append(1 if data['is_active'] else 0)
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(opt_id)
            cursor.execute("UPDATE applicant_user_options SET " + ", ".join(fields) +
                           " WHERE id=%s", params)
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'user_option_edit', user['role'], user['full_name'],
                               new_data={'id': opt_id, 'fields': list(data.keys())},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Opsi diperbarui'})
        except Exception as e:
            if 'Duplicate' in str(e):
                return jsonify({'status': 'error', 'msg': 'Opsi dengan nama tersebut sudah ada'}), 409
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/applicants/user-options/<int:opt_id>', methods=['DELETE'])
    @role_required(['receptionist', 'admin'])
    def api_user_options_delete(opt_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name FROM applicant_user_options WHERE id=%s", (opt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Opsi tidak ditemukan'}), 404
            cursor.execute("DELETE FROM applicant_user_options WHERE id=%s", (opt_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'user_option_delete', user['role'], user['full_name'],
                               new_data={'name': row['name']}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Opsi "{row["name"]}" dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LIST — receptionist & traineer (scope upline utk traineer)
    # ================================================================
    @app.route('/api/applicants')
    @role_required(['receptionist', 'traineer', 'admin'])
    def api_applicants_list():
        try:
            d_from = _parse_date(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date(request.args.get('date_to'), 'Tanggal sampai')
            search = str(request.args.get('search', '') or '').strip()
            upline = str(request.args.get('upline', '') or '').strip()
            user = str(request.args.get('user', '') or '').strip()
            status = str(request.args.get('status', '') or '').strip()

            where = []
            params = []
            if d_from:
                where.append("DATE(interview_at) >= %s")
                params.append(d_from.isoformat())
            if d_to:
                where.append("DATE(interview_at) <= %s")
                params.append(d_to.isoformat())
            if search:
                like = f"%{search}%"
                where.append("(nama_lengkap LIKE %s OR no_hp LIKE %s OR posisi LIKE %s "
                             "OR upline LIKE %s OR user_field LIKE %s)")
                params += [like] * 5
            if status:
                where.append("status = %s")
                params.append(status)
            # Scope traineer: hanya rekrutan upline sendiri (cocok parsial
            # case-insensitive karena pelamar bebas menulis nama/username).
            # Flag scope_traineer mencegah klausa upline LIKE duplikat di bawah.
            t_up = _traineer_upline()
            scope_traineer = False
            if t_up is not None:
                upline = upline or t_up[0]
                scope_traineer = True
                ors = ' OR '.join(["LOWER(upline) LIKE %s"] * len(t_up))
                where.append(f"({ors})")
                params += [f"%{u.lower()}%" for u in t_up]
            if upline and not scope_traineer:
                where.append("upline LIKE %s")
                params.append(f"%{upline}%")
            if user:
                where.append("user_field LIKE %s")
                params.append(f"%{user}%")

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT * FROM applicants"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY interview_at DESC, id DESC LIMIT 1000"
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            att_map = _load_attendance_map(cursor, [r['id'] for r in rows])
            cursor.close()
            conn.close()

            data = []
            for r in rows:
                item = _serialize(r)
                item['status_label'] = STATUS_LABELS.get(r['status'], r['status'])
                item['attendance'] = {
                    stage: _serialize(att_map.get(r['id'], {}).get(stage) or {})
                    for stage in VALID_STAGES
                }
                data.append(item)

            # Stats ringkas (scope yang sama)
            stats = {'total': len(data), 'today': 0}
            today = date.today().isoformat()
            for s in STATUS_LABELS:
                stats[s] = 0
            for it in data:
                stats[it['status']] = stats.get(it['status'], 0) + 1
                if (it.get('interview_at') or '')[:10] == today:
                    stats['today'] += 1
            return jsonify({'data': data, 'stats': stats, 'scope_upline': upline})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # EDIT — receptionist memperbaiki kesalahan input pelamar
    # ================================================================
    @app.route('/api/applicants/<int:appt_id>', methods=['PATCH'])
    @role_required(['receptionist', 'admin'])
    def api_applicants_edit(appt_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applicants WHERE id=%s", (appt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404

            fields = []
            params = []
            for field, maxlen in (('nama_lengkap', 150), ('pendidikan', 100),
                                  ('no_hp', 30), ('upline', 100),
                                  ('user_field', 100), ('posisi', 100), ('notes', 500)):
                if field in data:
                    val = str(data[field] or '').strip()[:maxlen]
                    if field == 'nama_lengkap' and not val:
                        cursor.close(); conn.close()
                        return jsonify({'status': 'error', 'msg': 'Nama Lengkap tidak boleh kosong'}), 400
                    fields.append(f"{field} = %s")
                    params.append(val)
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(appt_id)
            cursor.execute("UPDATE applicants SET " + ", ".join(fields) +
                           ", updated_at=NOW() WHERE id=%s", params)
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'applicant_edit', user['role'], user['full_name'],
                               new_data={'fields': list(data.keys())}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Data pelamar diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DELETE
    # ================================================================
    @app.route('/api/applicants/<int:appt_id>', methods=['DELETE'])
    @role_required(['receptionist', 'admin'])
    def api_applicants_delete(appt_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT display_id, nama_lengkap FROM applicants WHERE id=%s", (appt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404
            # v2.42.0: pelamar yang sudah dijadikan karyawan membawa catatan
            # in-out (applicant_id) — ikut dihapus agar tidak jadi data yatim.
            cursor.execute("DELETE FROM employee_inout WHERE applicant_id=%s", (appt_id,))
            cursor.execute("DELETE FROM applicants WHERE id=%s", (appt_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'applicant_delete', user['role'], user['full_name'],
                               new_data={'display_id': row['display_id'], 'nama': row['nama_lengkap']},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'{row["display_id"]} dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # VERIFIKASI — resepsionis mengesahkan data pelamar
    # ================================================================
    @app.route('/api/applicants/<int:appt_id>/verify', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    @stepup_required  # paritas in-out — verifikasi adalah pengesahan
    def api_applicants_verify(appt_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT display_id FROM applicants WHERE id=%s", (appt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404
            user = _current_user()
            cursor.execute("UPDATE applicants SET verified_by=%s, verified_at=NOW(), "
                           "updated_at=NOW() WHERE id=%s",
                           (user['full_name'], appt_id))
            conn.commit()
            log_activity_async(None, 'applicant_verify', user['role'], user['full_name'],
                               new_data={'display_id': row['display_id']}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'{row["display_id"]} terverifikasi'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # KEHADIRAN — interview & training hari 1-4
    # ================================================================
    @app.route('/api/applicants/<int:appt_id>/attendance', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_applicants_attendance(appt_id):
        try:
            data = request.get_json(silent=True) or {}
            stage = str(data.get('stage', '') or '').strip()
            if stage not in VALID_STAGES:
                return jsonify({'status': 'error', 'msg': 'Tahap tidak valid'}), 400
            note = str(data.get('note', '') or '').strip()[:255]
            attended_at = data.get('attended_at') or None

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applicants WHERE id=%s", (appt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404
            if row['status'] in TERMINAL_STATUSES:
                cursor.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': f'Pelamar sudah berstatus {row["status"]} — ubah status dulu bila perlu'}), 409

            if attended_at:
                try:
                    attended_dt = datetime.strptime(str(attended_at).strip(), '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error', 'msg': 'Format waktu harus YYYY-MM-DD HH:MM:SS'}), 400
            else:
                attended_dt = datetime.now()

            user = _current_user()
            cursor.execute(
                """INSERT INTO applicant_attendance (applicant_id, stage, attended_at, marked_by, note)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE attended_at=VALUES(attended_at),
                       marked_by=VALUES(marked_by), note=VALUES(note)""",
                (appt_id, stage, attended_dt, user['full_name'], note))

            # Status mengikuti tahap terjauh yang sudah dihadiri
            new_status = row['status']
            if stage in TRAINING_STAGES and STAGE_ORDER[stage] > STAGE_ORDER.get(new_status, -1):
                new_status = stage
            if new_status != row['status']:
                cursor.execute("UPDATE applicants SET status=%s, updated_at=NOW() WHERE id=%s",
                               (new_status, appt_id))

            conn.commit()
            log_activity_async(None, 'applicant_attendance', user['role'], user['full_name'],
                               new_data={'stage': stage, 'status': new_status,
                                         'at': attended_dt.strftime('%Y-%m-%d %H:%M:%S')},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success',
                            'msg': f'Kehadiran {applicant_stage_label(stage)} tercatat',
                            'applicant_status': new_status})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # STATUS — lulus / mengundurkan diri (alasan wajib) / ditolak
    # ================================================================
    @app.route('/api/applicants/<int:appt_id>/status', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    @stepup_required  # paritas in-out — lulus/undur diri menutup data
    def api_applicants_status(appt_id):
        try:
            data = request.get_json(silent=True) or {}
            status = str(data.get('status', '') or '').strip()
            if status not in TERMINAL_STATUSES:
                return jsonify({'status': 'error', 'msg': 'Status tidak valid'}), 400
            reason = str(data.get('reason', '') or '').strip()[:500]

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applicants WHERE id=%s", (appt_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404
            if row['status'] in TERMINAL_STATUSES:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Status pelamar sudah final'}), 409

            # Mengundurkan diri: alasan WAJIB bila pelamar sudah pernah hadir
            if status == 'resigned' and not reason:
                cursor.execute("SELECT COUNT(*) c FROM applicant_attendance WHERE applicant_id=%s",
                               (appt_id,))
                attended = cursor.fetchone()['c']
                if attended > 0:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error',
                                    'msg': 'Alasan mengundurkan diri WAJIB diisi karena pelamar sudah pernah hadir'}), 400

            user = _current_user()
            if status == 'resigned':
                cursor.execute("UPDATE applicants SET status='resigned', resign_reason=%s, "
                               "updated_at=NOW() WHERE id=%s", (reason, appt_id))
            elif status == 'rejected':
                cursor.execute("UPDATE applicants SET status='rejected', rejected_reason=%s, "
                               "updated_at=NOW() WHERE id=%s", (reason, appt_id))
            else:
                cursor.execute("UPDATE applicants SET status='lulus', updated_at=NOW() WHERE id=%s",
                               (appt_id,))
            conn.commit()
            log_activity_async(None, 'applicant_status', user['role'], user['full_name'],
                               new_data={'status': status, 'reason': reason},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Status menjadi {applicant_status_label(status)}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LAPORAN PDF RESMI (interview / training H1-H4) + TTD receptionist
    # ================================================================
    @app.route('/api/applicants/report')
    @role_required(['receptionist', 'admin'])
    def api_applicants_report():
        try:
            stage = str(request.args.get('stage', '') or '').strip()
            if stage not in VALID_STAGES:
                return jsonify({'error': 'Pilih tahap (interview / training H1-H4)'}), 400
            d_from = _parse_date(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date(request.args.get('date_to'), 'Tanggal sampai') or d_from or date.today()
            upline = str(request.args.get('upline', '') or '').strip()
            user = str(request.args.get('user', '') or '').strip()

            where = ["att.stage = %s"]
            params = [stage]
            if d_from:
                where.append("DATE(att.attended_at) >= %s")
                params.append(d_from.isoformat())
            where.append("DATE(att.attended_at) <= %s")
            params.append(d_to.isoformat())
            if upline:
                where.append("a.upline LIKE %s")
                params.append(f"%{upline}%")
            if user:
                where.append("a.user_field LIKE %s")
                params.append(f"%{user}%")

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT a.*, att.attended_at FROM applicants a "
                "JOIN applicant_attendance att ON att.applicant_id = a.id "
                "WHERE " + " AND ".join(where) +
                " ORDER BY att.attended_at ASC", params)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            date_label = f"{d_from or d_to} s/d {d_to}" if d_from else str(d_to)
            filters = {}
            if upline:
                filters['Upline'] = upline
            if user:
                filters['User'] = user
            user_info = _current_user()
            pdf = ApplicantReportPDF(title='LAPORAN KEHADIRAN PELAMAR KERJA')
            pdf.generate(rows, stage_label=applicant_stage_label(stage),
                         date_label=date_label, filters=filters,
                         generated_by=user_info['full_name'])
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            fname = f"Laporan_Pelamar_{stage}_{d_to.isoformat()}.pdf"
            response = make_response(buf.read())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={fname}'
            return response
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
