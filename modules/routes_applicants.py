"""Sistem Pelamar Kerja (v2.16) — form pelamar -> Rekrutmen (Receptionist).

Alur bisnis (menggantikan Google Form + Google Sheet):
  - Pelamar kerja mengisi form publik (nama, pendidikan, HP, upline, user,
    posisi). Tanggal & jam interview diambil OTOMATIS dari timestamp submit.
  - Receptionist: verifikator data, bisa mengubah data bila ada kesalahan input,
    mengelola kehadiran (interview + 4 hari training), mencatat pengunduran diri
    (alasan WAJIB bila pelamar sudah hadir), dan membuat laporan PDF resmi
    berlogo BPF per tahap.
  - Traineer: melihat data pelamar cabangnya READ-ONLY (tanpa verifikasi,
    edit, kehadiran, status, atau hapus). Semua endpoint tulis di modul ini
    hanya untuk receptionist/admin; endpoint baca memakai DB cabang sesi
    sehingga data antar cabang tidak pernah tercampur.
"""
import io
import time
from datetime import datetime, date

from flask import (request, jsonify, session, make_response)
from modules.config import get_db_connection, get_master_connection
from modules.helpers import (role_required, log_activity_async,
                             generate_display_id, applicant_stage_label,
                             applicant_status_label, client_ip)
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


READ_ROLES = ['receptionist', 'traineer', 'admin']


def _scope_branch():
    """Cabang data pelamar yang sedang dilihat.

    Data pelamar hidup di DB cabang masing-masing (get_db_connection mengikuti
    session['branch_code']), jadi scope ini hanya untuk label & badge UI.
    None = Admin Pusat (boleh semua cabang lewat pemilih cabang).
    """
    if session.get('user_role') != 'admin':
        return (session.get('branch_code') or '').strip().upper() or None
    try:
        from modules.admin_scope import is_ho_admin
        if is_ho_admin():
            return None
    except Exception:
        pass
    return (session.get('branch_code') or '').strip().upper() or None


def _active_branches():
    """[(code, name)] cabang aktif dari DB master; [] bila DB gagal."""
    conn = get_master_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT code, name FROM branches WHERE is_active=1 ORDER BY code")
        rows = cursor.fetchall() or []
        cursor.close()
        return [((r.get('code') or '').strip().upper(), r.get('name') or '')
                for r in rows if (r.get('code') or '').strip()]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _scope_dbs(branch_filter=''):
    """Daftar cabang yang dibaca request ini: [(code, name, aggregate)].

    - Selain Admin Pusat: hanya cabang sesi (isolasi DB cabang).
    - Admin Pusat: semua cabang aktif, atau satu cabang bila `branch_filter`
      valid. Filter tak dikenal → daftar kosong (fail-closed), bukan master.
    """
    scope = _scope_branch()
    if scope is not None:
        name = (session.get('branch_name') or '').strip()
        return [(scope, name, False)]
    branches = _active_branches()
    if branch_filter:
        return [(code, name, False) for code, name in branches if code == branch_filter]
    if not branches:
        fallback = (session.get('branch_code') or '').strip().upper() or 'SBY'
        return [(fallback, '', False)]
    return [(code, name, True) for code, name in branches]


def _query_applicants_branch(code, where, params):
    """Baca pelamar + kehadiran + statistik dari SATU DB cabang.

    Return (rows, attendance_map, stats) atau None bila DB/tabel tak siap.
    Baris dibatasi per cabang; penggabungan & pemotongan akhir di pemanggil.
    """
    conn = get_db_connection(branch_code=code)
    if not conn:
        return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        having = ((' WHERE ' + ' AND '.join(where)) if where else '')
        cursor.execute("SELECT * FROM applicants" + having +
                       " ORDER BY interview_at DESC, id DESC LIMIT 1000", params)
        rows = cursor.fetchall() or []
        att_map = _load_attendance_map(cursor, [r['id'] for r in rows])

        # Statistik dihitung di SQL (bukan dari baris ber-LIMIT) agar total
        # tetap benar walau data cabang lebih dari 1.000 baris.
        stats = {'total': 0, 'today': 0}
        for key in STATUS_LABELS:
            stats[key] = 0
        cursor.execute("SELECT status, COUNT(*) AS c FROM applicants"
                       + having + " GROUP BY status", params)
        for r in cursor.fetchall():
            n = int(r['c'] or 0)
            stats[r['status']] = stats.get(r['status'], 0) + n
            stats['total'] += n
        cursor.execute("SELECT COUNT(*) AS c FROM applicants"
                       + (having + ' AND ' if having else ' WHERE ')
                       + "DATE(interview_at)=CURDATE()", params)
        stats['today'] = int((cursor.fetchone() or {}).get('c') or 0)
        return rows, att_map, stats
    except Exception:
        return None
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _first_work_pending_by_branch():
    """{branch_code: jumlah menunggu verifikasi} dari tabel master FirstWork."""
    conn = get_master_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT branch_code, COUNT(*) AS c FROM first_work_submissions "
                       "WHERE status='submitted' GROUP BY branch_code")
        rows = cursor.fetchall() or []
        cursor.close()
        return {((r.get('branch_code') or '').strip().upper()): int(r['c'] or 0)
                for r in rows}
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _applicant_branch_summary(dbs):
    """Ringkasan per cabang (tanpa filter aktif) untuk halaman Admin Pusat.

    Angka pelamar diambil dari DB masing-masing cabang; antrean FirstWork dari
    tabel master. Cabang yang DB-nya belum siap tetap tampil dengan angka 0.
    """
    pending = _first_work_pending_by_branch()
    out = []
    for code, name, _agg in dbs:
        counts = {}
        conn = get_db_connection(branch_code=code)
        if conn:
            cursor = None
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT status, COUNT(*) AS c FROM applicants "
                               "GROUP BY status")
                counts = {r['status']: int(r['c'] or 0) for r in cursor.fetchall()}
            except Exception:
                counts = {}
            finally:
                try:
                    if cursor is not None:
                        cursor.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
        out.append({
            'code': code,
            'name': name,
            'total': sum(counts.values()),
            'interview': counts.get('interview', 0),
            'training': sum(counts.get(f'training_{i}', 0) for i in range(1, 5)),
            'lulus': counts.get('lulus', 0),
            'resigned': counts.get('resigned', 0),
            'rejected': counts.get('rejected', 0),
            'first_work_pending': pending.get(code, 0),
        })
    return out


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
            ip = client_ip() or '?'
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
    @role_required(READ_ROLES)
    def api_applicants_meta():
        try:
            dbs = _scope_dbs()
            aggregate = len(dbs) > 1
            uplines, users, user_options = set(), set(), {}
            for code, _name, _agg in dbs:
                conn = get_db_connection(branch_code=code)
                if not conn:
                    continue
                cursor = None
                try:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute(
                        "SELECT DISTINCT upline FROM applicants WHERE upline<>''")
                    uplines |= {r['upline'] for r in cursor.fetchall()}
                    cursor.execute(
                        "SELECT DISTINCT user_field FROM applicants WHERE user_field<>''")
                    users |= {r['user_field'] for r in cursor.fetchall()}
                    cursor.execute(
                        "SELECT id, name FROM applicant_user_options WHERE is_active=1")
                    for r in cursor.fetchall():
                        user_options.setdefault(r['name'], r['id'])
                except Exception:
                    pass  # DB cabang belum siap → opsi cabang itu dilewati
                finally:
                    try:
                        if cursor is not None:
                            cursor.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
            return jsonify({
                'uplines': sorted(uplines),
                'users': sorted(users),
                'user_options': [{'id': user_options[n], 'name': n}
                                 for n in sorted(user_options)],
                'scope_branch': _scope_branch(),
                'aggregate': aggregate,
                'branches': [{'code': c, 'name': n} for c, n in _active_branches()]
                            if _scope_branch() is None else [],
                'statuses': [{'value': k, 'label': v} for k, v in STATUS_LABELS.items()],
            })
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
                               new_data={'name': name}, ip=client_ip())
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
                               ip=client_ip())
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
                               new_data={'name': row['name']}, ip=client_ip())
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Opsi "{row["name"]}" dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LIST — receptionist & traineer (traineer READ-ONLY) & admin
    # ================================================================
    @app.route('/api/applicants')
    @role_required(READ_ROLES)
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
            # Semua role baca (receptionist, traineer, admin) melihat SELURUH
            # pelamar di cabangnya sendiri; traineer tidak lagi dibatasi teks
            # UPLINE (scope lama) karena isolasi data dijaga oleh DB cabang.
            if upline:
                where.append("upline LIKE %s")
                params.append(f"%{upline}%")
            if user:
                where.append("user_field LIKE %s")
                params.append(f"%{user}%")

            # v2.80.1: Admin Pusat boleh membaca SEMUA cabang sekaligus (data
            # pelamar ada di DB cabang masing-masing). Role lain tetap terkurung
            # pada DB cabang sesi.
            branch_filter = str(request.args.get('branch', '') or '').strip().upper()
            dbs = _scope_dbs(branch_filter)
            aggregate = len(dbs) > 1

            rows_all = []
            att_all = {}
            stats = {'total': 0, 'today': 0}
            for key in STATUS_LABELS:
                stats[key] = 0
            for code, name, _agg in dbs:
                result = _query_applicants_branch(code, where, params)
                if not result:
                    continue  # DB cabang belum siap → lewati, jangan gagalkan semua
                rows, att_map, branch_stats = result
                for row in rows:
                    row['branch_code'] = code
                    row['branch_name'] = name
                rows_all.extend(rows)
                for applicant_id, stages in att_map.items():
                    att_all[(code, applicant_id)] = stages
                for key, value in branch_stats.items():
                    stats[key] = stats.get(key, 0) + value

            rows_all.sort(key=lambda r: str(r.get('interview_at') or ''), reverse=True)
            rows_all = rows_all[:1000]

            data = []
            for r in rows_all:
                item = _serialize(r)
                item['status_label'] = STATUS_LABELS.get(r['status'], r['status'])
                att = att_all.get((r.get('branch_code'), r['id']), {})
                item['attendance'] = {
                    stage: _serialize(att.get(stage) or {}) for stage in VALID_STAGES
                }
                data.append(item)

            return jsonify({'data': data, 'stats': stats,
                            'scope_branch': _scope_branch(),
                            'aggregate': aggregate,
                            'branches': [{'code': c, 'name': n}
                                         for c, n, _a in dbs] if aggregate else [],
                            'branch_summary': _applicant_branch_summary(dbs)
                                              if aggregate else []})
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
                               new_data={'fields': list(data.keys())}, ip=client_ip())
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
                               ip=client_ip())
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
                               new_data={'display_id': row['display_id']}, ip=client_ip())
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
                               ip=client_ip())
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
                               ip=client_ip())
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
