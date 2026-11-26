"""Service absensi training portal (2 hari).

Identitas diverifikasi dari `recruitment_cases` (NIK unik + tanggal lahir).
Bukti disimpan di `training_attendance` (unik per kasus+cabang+hari); bila
identitas peserta juga ada di daftar Pelamar receptionist (nama + HP sama
persis), kehadiran disalin ke `applicant_attendance` sehingga kolom H1/H2
menyala. Tidak ada pembuatan baris `applicants` otomatis.
"""
import re
from datetime import datetime

from modules.config import get_master_connection
from modules.helpers import normalize_nik

VALID_DAYS = (1, 2)
ATTENDANCE_LABEL = {1: 'Hari 1', 2: 'Hari 2'}
# Status pelamar yang tidak boleh diubah oleh absensi portal.
TERMINAL_STATUSES = ('lulus', 'resigned', 'rejected')
STAGE_FOR_DAY = {1: 'training_1', 2: 'training_2'}


def mask_nik(value):
    text = str(value or '').strip()
    return ('****' + text[-4:]) if text else '****'


def normalize_hp(value):
    """Bakukan nomor HP Indonesia ke bentuk 08xxxx (tanpa spasi/simbol)."""
    digits = re.sub(r'\D', '', str(value or ''))
    if not digits:
        return ''
    if digits.startswith('62'):
        digits = '0' + digits[2:]
    elif digits.startswith('8'):
        digits = '0' + digits
    return digits


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def _dob_text(value):
    return str(value or '')[:10]


def _open_conn(conn):
    own = conn is None
    if own:
        conn = get_master_connection()
    return conn, own


def _case_for(cursor, nik):
    """Baris kasus berdasarkan NIK; DOB bukan lagi bukti identitas (Rilis C)."""
    cursor.execute(
        'SELECT case_id, nama, tanggal_lahir FROM recruitment_cases '
        'WHERE nik=%s', (nik,))
    return cursor.fetchone()


def _days_for(cursor, case_id, branch_code):
    cursor.execute(
        'SELECT day, attended_at, link_status FROM training_attendance '
        'WHERE case_id=%s AND branch_code=%s ORDER BY day',
        (case_id, branch_code))
    days = {1: None, 2: None}
    for row in cursor.fetchall() or []:
        try:
            day = int(row.get('day'))
        except (TypeError, ValueError):
            continue
        if day in days:
            days[day] = {
                'attended_at': _as_text(row.get('attended_at')),
                'link_status': str(row.get('link_status') or 'unlinked'),
            }
    return days


def _next_day(days):
    if days.get(1) is None:
        return 1
    if days.get(2) is None:
        return 2
    return None


def attendance_status(nik, branch_code, conn=None):
    """Status kehadiran training untuk satu identitas di satu cabang."""
    nik, _raw = normalize_nik(nik)
    if not nik:
        return {'ok': False, 'error': 'not_found'}
    branch = str(branch_code or '').strip().upper()[:10]
    conn, own = _open_conn(conn)
    if not conn:
        return {'ok': False, 'error': 'db'}
    cursor = conn.cursor(dictionary=True)
    try:
        case = _case_for(cursor, nik)
        if not case:
            return {'ok': False, 'error': 'not_found'}
        days = _days_for(cursor, case['case_id'], branch)
        return {
            'ok': True,
            'nama': str(case.get('nama') or ''),
            'days': days,
            'next_day': _next_day(days),
        }
    except Exception:
        return {'ok': False, 'error': 'db'}
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                conn.close()
            except Exception:
                pass


def _resolve_applicant(cursor, nik):
    """Cocokkan Pelamar lewat nama + HP dari CV terbaru. Hasil harus tunggal."""
    cursor.execute(
        'SELECT nama, no_hp_norm, no_hp FROM cv_online_submissions '
        'WHERE nik=%s ORDER BY submitted_at DESC LIMIT 1', (nik,))
    cv = cursor.fetchone()
    if not cv:
        return None, 'unlinked'
    nama = str(cv.get('nama') or '').strip().upper()
    hp = normalize_hp(cv.get('no_hp_norm') or cv.get('no_hp'))
    if not nama or not hp:
        return None, 'unlinked'
    cursor.execute(
        'SELECT id, nama_lengkap, no_hp, status FROM applicants '
        'WHERE UPPER(TRIM(nama_lengkap))=%s LIMIT 50', (nama,))
    matches = []
    for row in cursor.fetchall() or []:
        if normalize_hp(row.get('no_hp')) != hp:
            continue
        if str(row.get('status') or '').strip().lower() in TERMINAL_STATUSES:
            continue
        matches.append(row)
    if len(matches) == 1:
        return int(matches[0]['id']), 'linked'
    return None, ('ambiguous' if matches else 'unlinked')


def _bump_applicant_status(cursor, applicant_id, stage):
    """Naikkan status pelamar ke tahap training; tidak pernah menurunkan."""
    order = {'interview': 0, 'training_1': 1, 'training_2': 2,
             'training_3': 3, 'training_4': 4}
    cursor.execute('SELECT status FROM applicants WHERE id=%s', (applicant_id,))
    row = cursor.fetchone() or {}
    current = str(row.get('status') or '').strip().lower()
    if current in TERMINAL_STATUSES or current not in order:
        return
    if order.get(stage, -1) > order[current]:
        cursor.execute(
            'UPDATE applicants SET status=%s, updated_at=NOW() WHERE id=%s',
            (stage, applicant_id))


def _applicant_conn(branch, master_conn, app_conn=None):
    """Koneksi DB tempat tabel `applicants` berada (master atau DB cabang).

    Sejak pemisahan DB, Pelamar sebuah cabang bisa hidup di DB cabang, bukan
    master. Bukti training tetap di master (sama seperti kasus rekrutmen),
    tetapi penautan H1/H2 harus menulis ke DB yang dibaca dashboard Pelamar.
    """
    if app_conn is not None:
        return app_conn, False
    try:
        from modules.config import (DB_CONFIG, get_db_connection,
                                    resolve_db_name)
        if resolve_db_name(branch) == DB_CONFIG['database']:
            return master_conn, False
        return get_db_connection(branch_code=branch), True
    except Exception:
        return None, False


def record_attendance(nik, branch_code, day, ip='', user_agent='',
                      conn=None, app_conn=None):
    """Catat satu hari absensi; kunci Hari 2 sampai Hari 1 tercatat."""
    try:
        day = int(day)
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'invalid_day'}
    if day not in VALID_DAYS:
        return {'ok': False, 'error': 'invalid_day'}
    nik, _raw = normalize_nik(nik)
    if not nik:
        return {'ok': False, 'error': 'not_found'}
    branch = str(branch_code or '').strip().upper()[:10]
    conn, own = _open_conn(conn)
    if not conn:
        return {'ok': False, 'error': 'db'}
    cursor = conn.cursor(dictionary=True)
    app_conn, own_app = _applicant_conn(branch, conn, app_conn)
    app_cursor = app_conn.cursor(dictionary=True) if app_conn else None
    try:
        case = _case_for(cursor, nik)
        if not case:
            return {'ok': False, 'error': 'not_found'}
        case_id = case['case_id']
        days = _days_for(cursor, case_id, branch)
        if day == 2 and days.get(1) is None:
            return {'ok': False, 'error': 'day2_locked'}

        applicant_id, link_status = (None, 'unlinked')
        if app_cursor is not None:
            applicant_id, link_status = _resolve_applicant(app_cursor, nik)
        now = datetime.now()
        cursor.execute(
            """INSERT INTO training_attendance
                   (case_id, nik, branch_code, day, nama, attended_at,
                    applicant_id, link_status, ip, user_agent)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                   attended_at=VALUES(attended_at), nama=VALUES(nama),
                   applicant_id=VALUES(applicant_id),
                   link_status=VALUES(link_status), ip=VALUES(ip),
                   user_agent=VALUES(user_agent)""",
            (case_id, nik, branch, day, str(case.get('nama') or '')[:150],
             now, applicant_id, link_status, str(ip or '')[:45],
             str(user_agent or '')[:255]))

        cursor.execute(
            'SELECT id FROM training_attendance WHERE case_id=%s '
            'AND branch_code=%s AND day=%s', (case_id, branch, day))
        att_row = cursor.fetchone() or {}
        evidence_id = str(att_row.get('id') or '')

        # Hari 1 hanya PENDING bila Hari 2 belum ada; submit ulang Hari 1
        # setelah Hari 2 tidak boleh menurunkan langkah yang sudah SELESAI.
        step_status = ('SELESAI' if day == 2 or days.get(2) else 'PENDING')
        cursor.execute(
            """INSERT INTO recruitment_steps
                   (case_id, step_type, status, branch_code, evidence_type,
                    evidence_id, completed_at)
               VALUES (%s,'TRAINING',%s,%s,'training_attendance',%s,%s)
               ON DUPLICATE KEY UPDATE
                   status=VALUES(status), evidence_type=VALUES(evidence_type),
                   evidence_id=VALUES(evidence_id),
                   completed_at=VALUES(completed_at)""",
            (case_id, step_status, branch, evidence_id[:64], now))

        cursor.execute(
            """INSERT INTO case_branch_history
                   (case_id, branch_code, first_seen_at, last_seen_at)
               VALUES (%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE last_seen_at=VALUES(last_seen_at)""",
            (case_id, branch, now, now))

        if applicant_id and app_cursor is not None:
            try:
                stage = STAGE_FOR_DAY[day]
                app_cursor.execute(
                    """INSERT INTO applicant_attendance
                           (applicant_id, stage, attended_at, marked_by, note)
                       VALUES (%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE attended_at=VALUES(attended_at),
                           marked_by=VALUES(marked_by), note=VALUES(note)""",
                    (applicant_id, stage, now, 'Portal Training',
                     f'Absensi portal {ATTENDANCE_LABEL[day]}'))
                _bump_applicant_status(app_cursor, applicant_id, stage)
                # Koneksi terpisah = transaksi terpisah (master vs DB cabang).
                if app_conn is not conn:
                    app_conn.commit()
            except Exception:
                # Bukti tetap sah, tetapi jangan mengklaim Pelamar terhubung
                # bila H1/H2 gagal ditulis (mis. DB cabang sedang mati).
                try:
                    if app_conn is not conn:
                        app_conn.rollback()
                except Exception:
                    pass
                applicant_id, link_status = None, 'unlinked'
                cursor.execute(
                    'UPDATE training_attendance SET applicant_id=NULL, '
                    'link_status=%s WHERE case_id=%s AND branch_code=%s '
                    'AND day=%s', (link_status, case_id, branch, day))

        if own:
            conn.commit()
        days = _days_for(cursor, case_id, branch)
        return {
            'ok': True,
            'day': day,
            'link_status': link_status,
            'applicant_id': applicant_id,
            'case_id': case_id,
            'attendance_id': evidence_id,
            'days': days,
        }
    except Exception:
        if own:
            try:
                conn.rollback()
            except Exception:
                pass
        return {'ok': False, 'error': 'db'}
    finally:
        for cur in (app_cursor, cursor):
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
        if own_app and app_conn:
            try:
                app_conn.close()
            except Exception:
                pass
        if own:
            try:
                conn.close()
            except Exception:
                pass
