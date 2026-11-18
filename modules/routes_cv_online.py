"""Registrasi CV Online (v2.113.0) — form publik + pengelolaan role.

Alur (konsep sama dengan Absensi FirstWork):
- Form publik `/app/cv-online-form?cabang=CODE&t=TOKEN` (tanpa login) mengirim
  data registrasi CV pelamar ke `POST /api/cv-online/public`.
- Hanya role `traineer`, `ga_hr`, dan `admin` (termasuk Admin Pusat) yang dapat
  melihat datanya. Traineer & Admin dapat memverifikasi/menolak.
- Admin Pusat melihat semua cabang; role lain dibatasi cabang sesi.

Isi formulir mengikuti Google Form "Registrasi CV Online" (26 item, 5 bagian):
sumber informasi, data pribadi, latar pendidikan, pendidikan formal, dan
pengalaman bekerja.
"""
import csv
import io
import re
import secrets
from datetime import datetime, date

from flask import (request, jsonify, session, make_response)

# Data CV = fitur terpusat di DB master. Koneksi default mengikuti cabang sesi;
# admin cabang lain tidak punya tabel ini, jadi pakai master dan batasi baris
# lewat _scope_branch().
from modules.config import get_master_connection
from modules.helpers import (role_required, log_activity_async, client_ip,
                             redis_rate_hit)

# ================================================================
# KONSTANTA
# ================================================================
STATUS_LABELS = {
    'submitted': '🕒 Menunggu',
    'verified': '✅ Terverifikasi',
    'rejected': '✕ Ditolak',
}
VALID_STATUSES = tuple(STATUS_LABELS)

# Hanya tiga role ini yang boleh MELIHAT data registrasi CV.
VIEW_ROLES = ['traineer', 'ga_hr', 'admin']
EDIT_ROLES = ['traineer', 'admin']

USER_OPTIONS = [f'EF {n}' for n in range(1, 9)]
DOMISILI_OPTIONS = ['JABODETABEK', 'JAWA BARAT', 'JAWA TENGAH', 'JAWA TIMUR',
                    'SUMATERA', 'KALIMANTAN', 'SULAWESI', 'PAPUA']
PENDIDIKAN_OPTIONS = ['SMU/K SEDERAJAT', 'D1', 'D2', 'D3', 'D4', 'S1', 'S2']
GENDER_OPTIONS = ['Pria', 'Wanita']
PENGALAMAN_OPTIONS = {
    'sudah': 'Sudah memiliki pengalaman kerja',
    'belum': 'Belum memiliki pengalaman kerja / Fresh Graduate',
}
LAMA_OPTIONS = ['<1 Tahun', '1 - 2 Tahun', '3 - 4 Tahun', '> 5 Tahun']

# Rate limit publik: 10 kiriman / 10 menit per IP (Redis, fallback memori).
_SUBMIT_MAX = 10
_SUBMIT_WINDOW = 600

_NO_BRANCH = '__NOBRANCH__'


# ================================================================
# UTIL
# ================================================================
def _clean(value, maxlen=None):
    text = ('' if value is None else str(value)).strip()
    if maxlen is not None:
        text = text[:maxlen]
    return text


def _digits(value):
    return re.sub(r'\D', '', _clean(value))


def normalize_hp(value):
    """Normalisasi nomor HP Indonesia ke 08xxxxxxxxxx (best effort)."""
    raw = _clean(value, 30)
    digits = _digits(raw)
    if not digits:
        return ''
    if digits.startswith('62'):
        digits = '0' + digits[2:]
    elif digits.startswith('8'):
        digits = '0' + digits
    elif digits.startswith('05'):
        digits = '08' + digits[2:]
    if 10 <= len(digits) <= 15:
        return digits
    return ''


def normalize_name(value):
    """Rapikan nama untuk pencarian: huruf besar, spasi tunggal."""
    text = re.sub(r'\s+', ' ', _clean(value, 150)).strip().upper()
    return text


def parse_date(value):
    """Tanggal ISO (YYYY-MM-DD) -> date, atau None bila tidak valid."""
    raw = _clean(value, 10)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _consent_given(value):
    """Persetujuan afirmatif: hanya nilai yang jelas menyetujui yang lolos."""
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'ya', 'on')


def _rate_ok(ip):
    """Rate limit submit publik — Redis atomik (fallback memori)."""
    return redis_rate_hit(f'kirim|{ip}', _SUBMIT_MAX, _SUBMIT_WINDOW,
                          prefix='cvonline')


def _serialize(row):
    """Ubah row DB menjadi JSON-friendly (tanggal/waktu -> string)."""
    out = dict(row)
    for key in ('submitted_at', 'reviewed_at', 'consent_at', 'created_at', 'updated_at'):
        value = out.get(key)
        if isinstance(value, (datetime, date)):
            out[key] = value.strftime('%Y-%m-%d %H:%M:%S' if isinstance(value, datetime)
                                      else '%Y-%m-%d')
    value = out.get('tanggal_lahir')
    if isinstance(value, (datetime, date)):
        out['tanggal_lahir'] = value.strftime('%Y-%m-%d')
    return out


# ================================================================
# CABANG & TOKEN FORM
# ================================================================
def _scope_branch(conn=None):
    """None = semua cabang (Admin Pusat), selain itu kode cabang sesi."""
    role = session.get('user_role', '')
    username = (session.get('user_name') or '').strip().lower()
    if role == 'admin':
        if username in ('admin', 'admin_master'):
            return None
        try:
            from modules.admin_scope import is_ho_admin
            if is_ho_admin(conn):
                return None
        except Exception:
            pass
        return (session.get('branch_code') or '').strip().upper() or _NO_BRANCH
    return (session.get('branch_code') or '').strip().upper() or _NO_BRANCH


def _row_allowed(row, conn=None):
    branch = _scope_branch(conn)
    return branch is None or (row.get('branch_code') or '') == branch


def _branches(conn):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT code, name, city FROM branches WHERE is_active=1 ORDER BY code')
        return cursor.fetchall() or []
    finally:
        cursor.close()


def _explicit_branch_value(value=None):
    """Nilai cabang yang DISENGAJA dikirim (link/form), '' bila tidak ada."""
    if value:
        return _clean(value, 10).upper()
    for candidate in (request.args.get('cabang'), request.args.get('branch'),
                      request.form.get('branch'), request.form.get('cabang')):
        if candidate:
            return _clean(candidate, 10).upper()
    return ''


def _default_branch_code(branches):
    codes = [str(b.get('code') or '').strip().upper() for b in (branches or [])]
    return 'SBY' if 'SBY' in codes else (codes[0] if codes else 'SBY')


def _resolve_form_branch(conn, branches=None, value=None):
    """Tentukan cabang form publik. Return (code, error).

    Cabang yang disebut eksplisit tetapi tidak terdaftar/tidak aktif ditolak
    (bukan dipindahkan ke cabang default). Tanpa parameter cabang = cabang utama.
    """
    rows = branches if branches is not None else _branches(conn)
    codes = [str(row.get('code') or '').strip().upper() for row in rows]
    explicit = _explicit_branch_value(value)
    if explicit:
        if explicit not in codes:
            return None, (f'Cabang "{explicit}" tidak dikenal atau tidak aktif. '
                          'Minta tautan form yang benar ke Traineer/Admin.')
        return explicit, ''
    return _default_branch_code(rows), ''


def _branch_form_tokens(conn):
    """Peta branch_code -> {form_token, active} (tabel boleh belum ada)."""
    try:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                'SELECT branch_code, form_token, active FROM cv_online_branch_forms')
            return {str(r.get('branch_code') or '').upper(): r
                    for r in (cursor.fetchall() or [])}
        finally:
            cursor.close()
    except Exception:
        return {}


def _form_token_from_request():
    for candidate in (request.args.get('t'), request.args.get('token'),
                      request.form.get('t'), request.form.get('token')):
        if candidate:
            return _clean(candidate, 200)
    return ''


def _token_error(branch_code, supplied, token_row):
    """Error string bila token cabang tidak sah; '' bila boleh lanjut."""
    if not token_row or not token_row.get('active'):
        return ''
    stored = str(token_row.get('form_token') or '')
    if supplied and stored and secrets.compare_digest(str(supplied), stored):
        return ''
    return (f'Tautan form tidak valid untuk cabang {branch_code}. '
            'Minta tautan terbaru ke Traineer/Admin.')


def _enforce_branch_token(conn, branch_code, branches=None):
    return _token_error(branch_code, _form_token_from_request(),
                        _branch_form_tokens(conn).get(branch_code))


def _form_path(branch_code, token=''):
    """Path form publik milik satu cabang (relatif, host diisi frontend)."""
    code = (branch_code or 'SBY').strip().upper() or 'SBY'
    path = f'/app/cv-online-form?cabang={code}'
    return path + (f'&t={token}' if token else '')


# ================================================================
# VALIDASI & NOMOR REGISTRASI
# ================================================================
def validate_payload(form):
    """Validasi isian form publik. Return (data, error_message)."""
    data = {
        'sumber_informasi': _clean(form.get('sumber_informasi'), 150),
        'diundang_oleh': _clean(form.get('diundang_oleh'), 150),
        'kontak_serumah': _clean(form.get('kontak_serumah'), 2000),
        'kontak_tidak_serumah': _clean(form.get('kontak_tidak_serumah'), 2000),
        'user_ef': _clean(form.get('user_ef'), 20),
        'nama': re.sub(r'\s+', ' ', _clean(form.get('nama'), 150)),
        'tempat_lahir': _clean(form.get('tempat_lahir'), 100),
        'tanggal_lahir': _clean(form.get('tanggal_lahir'), 10),
        'jenis_kelamin': _clean(form.get('jenis_kelamin'), 10),
        'domisili': _clean(form.get('domisili'), 50),
        'alamat': _clean(form.get('alamat'), 2000),
        'no_hp': _clean(form.get('no_hp'), 30),
        'pendidikan_terakhir': _clean(form.get('pendidikan_terakhir'), 50),
        'sekolah_menengah': _clean(form.get('sekolah_menengah'), 150),
        'perguruan_tinggi': _clean(form.get('perguruan_tinggi'), 150),
        'pengalaman_status': _clean(form.get('pengalaman_status'), 20).lower(),
        'pengalaman_lama': _clean(form.get('pengalaman_lama'), 30),
        'posisi_terakhir': _clean(form.get('posisi_terakhir'), 150),
        'pengalaman_1': _clean(form.get('pengalaman_1'), 2000),
        'pengalaman_2': _clean(form.get('pengalaman_2'), 2000),
    }

    required = (
        ('sumber_informasi', 'Sumber Informasi wajib diisi'),
        ('diundang_oleh', 'Diundang Oleh wajib diisi'),
        ('kontak_serumah', 'Kontak serumah wajib diisi'),
        ('kontak_tidak_serumah', 'Kontak tidak serumah wajib diisi'),
        ('user_ef', 'User (pengundang) wajib dipilih'),
        ('nama', 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter)'),
        ('tempat_lahir', 'Tempat Lahir wajib diisi'),
        ('tanggal_lahir', 'Tanggal Lahir wajib diisi'),
        ('jenis_kelamin', 'Jenis Kelamin wajib dipilih'),
        ('domisili', 'Domisili wajib dipilih'),
        ('alamat', 'Alamat sesuai KTP wajib diisi'),
        ('no_hp', 'Nomor Handphone wajib diisi'),
        ('pendidikan_terakhir', 'Pendidikan Terakhir wajib dipilih'),
    )
    for key, message in required:
        if not data[key]:
            return None, message
    if len(data['nama']) < 3:
        return None, 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter)'

    if data['user_ef'] not in USER_OPTIONS:
        return None, 'Pilihan User tidak valid'
    if data['jenis_kelamin'] not in GENDER_OPTIONS:
        return None, 'Pilihan Jenis Kelamin tidak valid'
    if data['domisili'] not in DOMISILI_OPTIONS:
        return None, 'Pilihan Domisili tidak valid'
    if data['pendidikan_terakhir'] not in PENDIDIKAN_OPTIONS:
        return None, 'Pilihan Pendidikan Terakhir tidak valid'

    birth = parse_date(data['tanggal_lahir'])
    if not birth:
        return None, 'Tanggal Lahir tidak valid'
    if birth > date.today():
        return None, 'Tanggal Lahir tidak boleh di masa depan'
    if birth.year < 1940:
        return None, 'Tanggal Lahir tidak masuk akal'

    no_hp = normalize_hp(data['no_hp'])
    if not no_hp:
        return None, 'Nomor Handphone tidak valid'
    data['no_hp_norm'] = no_hp

    if data['pengalaman_status'] and data['pengalaman_status'] not in PENGALAMAN_OPTIONS:
        return None, 'Pilihan Pengalaman Bekerja tidak valid'
    if data['pengalaman_lama'] and data['pengalaman_lama'] not in LAMA_OPTIONS:
        return None, 'Pilihan lama pengalaman bekerja tidak valid'

    data['nama_norm'] = normalize_name(data['nama'])
    return data, ''


def _next_reg_no(conn, submitted_at, branch_code):
    """Nomor registrasi unik: CV-<CABANG>-<YYMMDD>-<urut 3 digit>."""
    prefix = f'CV-{branch_code}-{submitted_at.strftime("%y%m%d")}-'
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT COUNT(*) AS n FROM cv_online_submissions '
            'WHERE registration_no LIKE %s', (prefix + '%',))
        seq = int((cursor.fetchone() or {}).get('n') or 0)
        for _ in range(50):
            seq += 1
            candidate = f'{prefix}{seq:03d}'
            cursor.execute(
                'SELECT id FROM cv_online_submissions WHERE registration_no=%s',
                (candidate,))
            if not cursor.fetchone():
                return candidate
        return f'{prefix}{secrets.randbelow(900) + 100}'
    finally:
        cursor.close()


def _add_event(cursor, submission_id, event, status_from='', status_to='',
               note='', actor='public', actor_role='public', ip=''):
    cursor.execute("""
        INSERT INTO cv_online_events
            (submission_id, event, status_from, status_to, note, actor,
             actor_role, ip)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (submission_id, event, status_from, status_to, note, actor,
          actor_role, ip))


# ================================================================
# ROUTES
# ================================================================
def register_cv_online_routes(app):

    # ---------------- PUBLIK ----------------
    @app.route('/api/cv-online/form-meta')
    def api_cv_online_form_meta():
        """Info cabang + pilihan isian untuk form publik (validasi tautan)."""
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            branches = _branches(conn)
            branch, branch_error = _resolve_form_branch(conn, branches=branches)
            if branch_error:
                return jsonify({'error': branch_error}), 400
            token_error = _enforce_branch_token(conn, branch, branches=branches)
            if token_error:
                return jsonify({'error': token_error}), 403
            info = next((b for b in branches if b['code'] == branch), None)
            return jsonify({
                'branch': branch,
                'branch_name': (info or {}).get('name') or branch,
                'options': {
                    'user': USER_OPTIONS,
                    'domisili': DOMISILI_OPTIONS,
                    'pendidikan': PENDIDIKAN_OPTIONS,
                    'jenis_kelamin': GENDER_OPTIONS,
                    'lama': LAMA_OPTIONS,
                },
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/public', methods=['POST'])
    def api_cv_online_public_submit():
        conn = None
        try:
            ip = client_ip() or '?'
            if not _rate_ok(ip):
                return jsonify({'status': 'error',
                                'msg': 'Terlalu banyak pengiriman dari perangkat ini. '
                                       'Coba lagi beberapa saat.'}), 429

            data, error = validate_payload(request.form)
            if error:
                return jsonify({'status': 'error', 'msg': error}), 400

            # Persetujuan pemrosesan data pribadi wajib eksplisit & tercatat.
            if not _consent_given(request.form.get('consent')):
                return jsonify({'status': 'error',
                                'msg': 'Persetujuan syarat & ketentuan serta '
                                       'pemrosesan data pribadi wajib dicentang '
                                       'sebelum mengirim.'}), 400

            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500

            branch_code, branch_error = _resolve_form_branch(conn)
            if branch_error:
                return jsonify({'status': 'error', 'msg': branch_error}), 400
            token_error = _enforce_branch_token(conn, branch_code)
            if token_error:
                return jsonify({'status': 'error', 'msg': token_error}), 403

            submitted_at = datetime.now()

            # Cegah kiriman ganda karena tombol ditekan dua kali / jaringan lambat:
            # isian dengan HP & nama sama dalam 10 menit dianggap duplikat.
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT id FROM cv_online_submissions
                    WHERE no_hp_norm=%s AND nama=%s
                      AND submitted_at >= DATE_SUB(%s, INTERVAL 10 MINUTE)
                    LIMIT 1
                """, (data['no_hp_norm'], data['nama'], submitted_at))
                if cursor.fetchone():
                    return jsonify({'status': 'error',
                                    'msg': 'Pendaftaran dengan nama dan nomor HP ini '
                                           'baru saja terkirim. Tidak perlu mengisi ulang.'}), 409
            finally:
                cursor.close()

            registration_no = _next_reg_no(conn, submitted_at, branch_code)
            birth = parse_date(data['tanggal_lahir'])

            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO cv_online_submissions
                        (registration_no, source, submitted_at, sumber_informasi,
                         diundang_oleh, kontak_serumah, kontak_tidak_serumah,
                         user_ef, nama, tempat_lahir, tanggal_lahir,
                         jenis_kelamin, domisili, alamat, no_hp, no_hp_norm,
                         pendidikan_terakhir, sekolah_menengah, perguruan_tinggi,
                         pengalaman_status, pengalaman_lama, posisi_terakhir,
                         pengalaman_1, pengalaman_2, branch_code, status,
                         consent_at)
                    VALUES (%s,'form',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,'submitted',%s)
                """, (
                    registration_no, submitted_at, data['sumber_informasi'],
                    data['diundang_oleh'], data['kontak_serumah'],
                    data['kontak_tidak_serumah'], data['user_ef'], data['nama'],
                    data['tempat_lahir'], birth, data['jenis_kelamin'],
                    data['domisili'], data['alamat'], data['no_hp'],
                    data['no_hp_norm'], data['pendidikan_terakhir'],
                    data['sekolah_menengah'], data['perguruan_tinggi'],
                    data['pengalaman_status'], data['pengalaman_lama'],
                    data['posisi_terakhir'], data['pengalaman_1'],
                    data['pengalaman_2'], branch_code, submitted_at,
                ))
                submission_id = cursor.lastrowid
                _add_event(cursor, submission_id, 'created', '', 'submitted',
                           'Kirim form publik', 'public', 'public', ip)
                _add_event(cursor, submission_id, 'consent', '', '',
                           'Persetujuan syarat & ketentuan serta pemrosesan '
                           'data pribadi dicatat saat pengiriman form',
                           'public', 'public', ip)
                conn.commit()
            finally:
                cursor.close()

            log_activity_async(None, 'cv_online_submit', 'public', data['nama'],
                               new_data={'registration_no': registration_no}, ip=ip)
            return jsonify({
                'status': 'success',
                'msg': 'Registrasi CV Online berhasil dikirim.',
                'registration_no': registration_no,
                'nama': data['nama'],
                'submitted_at': submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- PENGELOLA ----------------
    @app.route('/api/cv-online/meta')
    @role_required(VIEW_ROLES)
    def api_cv_online_meta():
        conn = None
        try:
            conn = get_master_connection()
            scope = _scope_branch(conn) if conn else None
            return jsonify({
                'statuses': [{'value': k, 'label': v}
                             for k, v in STATUS_LABELS.items()],
                'options': {
                    'user': USER_OPTIONS,
                    'domisili': DOMISILI_OPTIONS,
                    'pendidikan': PENDIDIKAN_OPTIONS,
                    'jenis_kelamin': GENDER_OPTIONS,
                    'lama': LAMA_OPTIONS,
                },
                'scope_branch': scope,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online')
    @role_required(VIEW_ROLES)
    def api_cv_online_list():
        conn = None
        try:
            page = max(1, int(request.args.get('page', 1) or 1))
            limit = min(max(1, int(request.args.get('limit', 50) or 50)), 200)
            offset = (page - 1) * limit
            status = _clean(request.args.get('status'), 30)
            q = _clean(request.args.get('q'), 100)
            user_ef = _clean(request.args.get('user_ef'), 20)
            date_from = _clean(request.args.get('date_from'), 10)
            date_to = _clean(request.args.get('date_to'), 10)
            branch_filter = _clean(request.args.get('branch'), 10).upper()

            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500

            where, params = [], []
            scope = _scope_branch(conn)
            if scope:
                where.append('branch_code=%s')
                params.append(scope)
            elif branch_filter:
                where.append('branch_code=%s')
                params.append(branch_filter)
            if status:
                if status not in VALID_STATUSES:
                    return jsonify({'error': 'Status tidak valid'}), 400
                where.append('status=%s')
                params.append(status)
            if user_ef:
                where.append('user_ef=%s')
                params.append(user_ef)
            if date_from:
                where.append('DATE(submitted_at) >= %s')
                params.append(date_from)
            if date_to:
                where.append('DATE(submitted_at) <= %s')
                params.append(date_to)
            if q:
                like = f'%{q}%'
                where.append('(nama LIKE %s OR no_hp_norm LIKE %s OR '
                             'diundang_oleh LIKE %s OR sumber_informasi LIKE %s OR '
                             'registration_no LIKE %s OR tempat_lahir LIKE %s)')
                params += [like] * 6

            where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT COUNT(*) AS total FROM cv_online_submissions' + where_sql,
                    params)
                total = int((cursor.fetchone() or {}).get('total') or 0)

                cursor.execute(
                    'SELECT * FROM cv_online_submissions' + where_sql
                    + ' ORDER BY submitted_at DESC, id DESC LIMIT %s OFFSET %s',
                    params + [limit, offset])
                rows = cursor.fetchall() or []

                stat_where, stat_params = [], []
                if scope:
                    stat_where.append('branch_code=%s')
                    stat_params.append(scope)
                cursor.execute(
                    'SELECT status, COUNT(*) AS n FROM cv_online_submissions'
                    + ((' WHERE ' + ' AND '.join(stat_where)) if stat_where else '')
                    + ' GROUP BY status', stat_params)
                stats = {'total': 0, 'submitted': 0, 'verified': 0,
                         'rejected': 0, 'today': 0}
                for stat in cursor.fetchall():
                    stats[stat['status']] = int(stat['n'] or 0)
                    stats['total'] += int(stat['n'] or 0)
                cursor.execute(
                    'SELECT COUNT(*) AS n FROM cv_online_submissions '
                    'WHERE DATE(submitted_at)=CURDATE()'
                    + ((' AND branch_code=%s') if scope else ''),
                    ([scope] if scope else []))
                stats['today'] = int((cursor.fetchone() or {}).get('n') or 0)
            finally:
                cursor.close()

            return jsonify({
                'data': [_serialize(row) for row in rows],
                'stats': stats,
                'total': total,
                'page': page,
                'limit': limit,
                'scope_branch': scope,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/<int:submission_id>')
    @role_required(VIEW_ROLES)
    def api_cv_online_detail(submission_id):
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT * FROM cv_online_submissions WHERE id=%s',
                    (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'error': 'Data di luar cabang Anda'}), 403
                cursor.execute("""
                    SELECT event, status_from, status_to, note, actor, actor_role,
                           created_at
                    FROM cv_online_events WHERE submission_id=%s
                    ORDER BY id DESC
                """, (submission_id,))
                events = cursor.fetchall() or []
            finally:
                cursor.close()
            data = _serialize(row)
            data['events'] = [_serialize(e) for e in events]
            return jsonify({'data': data})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/<int:submission_id>/review', methods=['POST'])
    @role_required(EDIT_ROLES)
    def api_cv_online_review(submission_id):
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            action = _clean(body.get('action'), 20).lower()
            note = _clean(body.get('note'), 500)

            transitions = {
                'verify': (('submitted', 'rejected'), 'verified'),
                'reject': (('submitted', 'verified'), 'rejected'),
                'reopen': (('verified', 'rejected'), 'submitted'),
            }
            if action not in transitions:
                return jsonify({'error': 'Aksi tidak valid'}), 400
            allowed_from, new_status = transitions[action]
            if action == 'reject' and len(note) < 3:
                return jsonify({'error': 'Catatan alasan penolakan wajib diisi'}), 400

            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT * FROM cv_online_submissions WHERE id=%s',
                    (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'error': 'Data di luar cabang Anda'}), 403
                if row.get('status') not in allowed_from:
                    return jsonify({'error': 'Status data tidak mendukung aksi ini'}), 409

                actor = session.get('user_name') or 'system'
                role = session.get('user_role') or ''
                cursor.execute("""
                    UPDATE cv_online_submissions
                    SET status=%s, review_note=%s, reviewed_by=%s, reviewed_at=%s
                    WHERE id=%s
                """, (new_status, note, actor, datetime.now(), submission_id))
                _add_event(cursor, submission_id, action,
                           row.get('status') or '', new_status, note,
                           actor, role, client_ip() or '')
                conn.commit()
            finally:
                cursor.close()

            log_activity_async(None, f'cv_online_{action}', 'user',
                               session.get('user_name') or 'system',
                               old_data={'status': row.get('status')},
                               new_data={'registration_no': row.get('registration_no'),
                                         'status': new_status})
            return jsonify({'status': 'success', 'msg': 'Status diperbarui',
                            'data': {'id': submission_id, 'status': new_status}})
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/<int:submission_id>', methods=['DELETE'])
    @role_required(EDIT_ROLES)
    def api_cv_online_delete(submission_id):
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            if _clean(body.get('confirm'), 20).upper() != 'HAPUS':
                return jsonify({'error': 'Ketik HAPUS untuk konfirmasi'}), 400
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT * FROM cv_online_submissions WHERE id=%s',
                    (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'error': 'Data di luar cabang Anda'}), 403
                # Data terverifikasi = arsip; hanya Admin Pusat yang boleh hapus.
                scope = _scope_branch(conn)
                if row.get('status') == 'verified' and scope is not None:
                    return jsonify({'error': 'Data terverifikasi hanya dapat '
                                             'dihapus Admin Pusat'}), 403
                cursor.execute(
                    'DELETE FROM cv_online_submissions WHERE id=%s', (submission_id,))
                conn.commit()
            finally:
                cursor.close()
            log_activity_async(None, 'cv_online_delete', 'user',
                               session.get('user_name') or 'system',
                               old_data={'registration_no': row.get('registration_no'),
                                         'nama': row.get('nama')})
            return jsonify({'status': 'success', 'msg': 'Data dihapus'})
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/export')
    @role_required(VIEW_ROLES)
    def api_cv_online_export():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            where, params = [], []
            scope = _scope_branch(conn)
            if scope:
                where.append('branch_code=%s')
                params.append(scope)
            status = _clean(request.args.get('status'), 30)
            if status and status in VALID_STATUSES:
                where.append('status=%s')
                params.append(status)
            date_from = _clean(request.args.get('date_from'), 10)
            if date_from:
                where.append('DATE(submitted_at) >= %s')
                params.append(date_from)
            date_to = _clean(request.args.get('date_to'), 10)
            if date_to:
                where.append('DATE(submitted_at) <= %s')
                params.append(date_to)
            where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT * FROM cv_online_submissions' + where_sql
                    + ' ORDER BY submitted_at DESC, id DESC', params)
                rows = cursor.fetchall() or []
            finally:
                cursor.close()

            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow([
                'No. Registrasi', 'Waktu Kirim', 'Cabang', 'Status', 'Nama',
                'Tempat Lahir', 'Tanggal Lahir', 'Jenis Kelamin', 'Domisili',
                'Alamat', 'No. HP', 'Pendidikan Terakhir',
                'Sekolah Menengah', 'Perguruan Tinggi', 'Pengalaman',
                'Lama Pengalaman', 'Posisi Terakhir', 'Pengalaman Kerja 1',
                'Pengalaman Kerja 2', 'Sumber Informasi', 'Diundang Oleh',
                'Kontak Serumah', 'Kontak Tidak Serumah', 'User', 'Catatan',
            ])
            for row in rows:
                data = _serialize(row)
                writer.writerow([
                    data.get('registration_no') or '',
                    data.get('submitted_at') or '',
                    data.get('branch_code') or '',
                    STATUS_LABELS.get(data.get('status'), data.get('status') or ''),
                    data.get('nama') or '',
                    data.get('tempat_lahir') or '',
                    data.get('tanggal_lahir') or '',
                    data.get('jenis_kelamin') or '',
                    data.get('domisili') or '',
                    data.get('alamat') or '',
                    data.get('no_hp') or '',
                    data.get('pendidikan_terakhir') or '',
                    data.get('sekolah_menengah') or '',
                    data.get('perguruan_tinggi') or '',
                    PENGALAMAN_OPTIONS.get(data.get('pengalaman_status'),
                                           data.get('pengalaman_status') or ''),
                    data.get('pengalaman_lama') or '',
                    data.get('posisi_terakhir') or '',
                    data.get('pengalaman_1') or '',
                    data.get('pengalaman_2') or '',
                    data.get('sumber_informasi') or '',
                    data.get('diundang_oleh') or '',
                    data.get('kontak_serumah') or '',
                    data.get('kontak_tidak_serumah') or '',
                    data.get('user_ef') or '',
                    data.get('review_note') or '',
                ])

            output = make_response('\ufeff' + buffer.getvalue())
            output.headers['Content-Type'] = 'text/csv; charset=utf-8'
            output.headers['Content-Disposition'] = (
                'attachment; filename=cv-online-'
                f'{datetime.now().strftime("%Y%m%d-%H%M")}.csv')
            log_activity_async(None, 'cv_online_export', 'user',
                               session.get('user_name') or 'system',
                               new_data={'rows': len(rows)})
            return output
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/cv-online/branch-forms')
    @role_required(VIEW_ROLES)
    def api_cv_online_branch_forms():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            scope = _scope_branch(conn)
            branches = _branches(conn)
            tokens = _branch_form_tokens(conn)
            out = []
            for info in branches:
                code = str(info.get('code') or '').strip().upper()
                if not code:
                    continue
                if scope and code != scope:
                    continue
                token_row = tokens.get(code) or {}
                token = str(token_row.get('form_token') or '')
                out.append({
                    'branch_code': code,
                    'branch_name': info.get('name') or code,
                    'form_token': token,
                    'form_path': _form_path(code, token) if token else '',
                    'active': bool(token_row.get('active', 1)),
                })
            return jsonify({'data': out, 'scope_branch': scope})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
