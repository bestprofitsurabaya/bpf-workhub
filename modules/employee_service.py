"""Master karyawan: promosi dari kasus, absensi OUT/IN, nonaktif (Rilis D)."""
from datetime import date, datetime

from modules.config import get_master_connection
from modules.recruitment_events import record_event

_SOURCE = 'recruitment'


def _open(conn):
    if conn is not None:
        return conn, False
    db = get_master_connection()
    return db, db is not None


def next_employee_no(cursor, branch_code):
    """Nomor KRY-<CABANG>-<5 digit> memakai counter per cabang."""
    code = str(branch_code or '').strip().upper()[:10] or 'SBY'
    cursor.execute(
        'SELECT last_value FROM employee_counters '
        "WHERE branch_code=%s AND series='EMPLOYEE'", (code,))
    row = cursor.fetchone() or {}
    value = int(row.get('last_value') or 0) + 1
    cursor.execute(
        "INSERT INTO employee_counters (branch_code, series, last_value) "
        "VALUES (%s,'EMPLOYEE',%s) ON DUPLICATE KEY UPDATE last_value=%s",
        (code, value, value))
    return f'KRY-{code}-{value:05d}'


def _latest(cursor, table, nik):
    cursor.execute(
        f'SELECT * FROM {table} WHERE nik=%s ORDER BY submitted_at DESC LIMIT 1',
        (nik,))
    return cursor.fetchone() or {}


def promote_to_employee(case_id, jabatan='Business Consultant', branch_code='',
                        actor='', actor_role='', conn=None):
    """Promosikan kasus lulus menjadi karyawan; idempoten per NIK."""
    db, own = _open(conn)
    if not db:
        raise RuntimeError('DB master tidak tersedia')
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM recruitment_cases WHERE case_id=%s',
                       (case_id,))
        case = cursor.fetchone()
        if not case:
            raise ValueError('Kasus tidak ditemukan')
        nik = str(case.get('nik') or '').strip()
        if len(nik) != 16:
            raise ValueError('NIK wajib dilengkapi')
        cursor.execute('SELECT * FROM employees WHERE nik=%s', (nik,))
        existing = cursor.fetchone()
        cv = _latest(cursor, 'cv_online_submissions', nik)
        fw = _latest(cursor, 'first_work_submissions', nik)
        nama = str(case.get('nama') or cv.get('nama') or '')
        branch = str(branch_code or case.get('first_branch') or '')[:10]

        if existing:
            cursor.execute(
                """UPDATE employees SET jabatan=COALESCE(NULLIF(jabatan,''),%s),
                   is_active=1, deactivated_at=NULL, deactivated_by=NULL,
                   deactivation_reason=NULL, updated_at=NOW() WHERE id=%s""",
                (jabatan, existing['id']))
            was_inactive = not bool(existing.get('is_active'))
            if was_inactive:
                record_event(case_id, nik, 'EMPLOYEE_REACTIVATED',
                             branch_code=branch, actor_name=actor,
                             actor_role=actor_role, conn=db)
            if own:
                db.commit()
            return {'employee_id': existing['id'],
                    'employee_no': existing.get('employee_no') or '',
                    'created': False, 'reactivated': was_inactive}

        employee_no = next_employee_no(cursor, branch)
        cursor.execute(
            """INSERT INTO employees
               (employee_no, nik, nama, nama_norm, jabatan, branch_code,
                tanggal_masuk, source, source_uid, case_id, needs_nik, no_hp,
                tanggal_lahir, jenis_kelamin, tempat_lahir, pendidikan_terakhir)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (employee_no, nik, nama[:150], nama.strip().lower()[:150],
             jabatan[:100], branch, date.today().isoformat(), _SOURCE,
             case_id, case_id, 0, str(cv.get('no_hp') or '')[:30],
             str(cv.get('tanggal_lahir') or case.get('tanggal_lahir') or '')[:10] or None,
             str(cv.get('jenis_kelamin') or '')[:20] or None,
             str(cv.get('tempat_lahir') or '')[:100] or None,
             str(cv.get('pendidikan_terakhir') or '')[:100] or None))
        employee_id = cursor.lastrowid
        record_event(case_id, nik, 'EMPLOYEE_CREATED', branch_code=branch,
                     actor_name=actor, actor_role=actor_role, conn=db,
                     metadata={'employee_no': employee_no,
                               'registration_no': fw.get('registration_no')})
        if own:
            db.commit()
        return {'employee_id': employee_id, 'employee_no': employee_no,
                'created': True, 'reactivated': False}
    except Exception:
        if own:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                db.close()
            except Exception:
                pass


def current_status(cursor, employee_id):
    """Arah event absensi terakhir yang belum di-void ('IN' bila kosong)."""
    cursor.execute(
        """SELECT direction FROM employee_attendance_events
           WHERE employee_id=%s AND voided_at IS NULL
           ORDER BY event_at DESC, id DESC LIMIT 1""", (employee_id,))
    row = cursor.fetchone() or {}
    return str(row.get('direction') or 'IN')


def toggle_attendance(employee_id, direction, actor_username, actor_name,
                      branch_code, note='', conn=None):
    """Catat satu kejadian keluar/masuk; arah yang sama berturut-turut ditolak."""
    direction = str(direction or '').upper()
    if direction not in ('OUT', 'IN'):
        raise ValueError('invalid_direction')
    db, own = _open(conn)
    if not db:
        raise RuntimeError('DB master tidak tersedia')
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM employees WHERE id=%s', (employee_id,))
        employee = cursor.fetchone()
        if not employee:
            raise ValueError('not_found')
        branch = str(branch_code or '').upper()
        if branch != '*' and str(employee.get('branch_code') or '') != branch:
            raise ValueError('wrong_branch')
        status = current_status(cursor, employee_id)
        if status == direction:
            raise ValueError('already_' + direction.lower())
        now = datetime.now()
        cursor.execute(
            """INSERT INTO employee_attendance_events
               (employee_id, nik, branch_code, direction, event_at,
                actor_username, actor_name, note, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'manual')""",
            (employee_id, employee.get('nik'), branch, direction, now,
             str(actor_username or '')[:100], str(actor_name or '')[:150],
             str(note or '')[:500]))
        event_id = cursor.lastrowid
        if own:
            db.commit()
        return {'event_id': event_id, 'direction': direction,
                'event_at': now, 'status': direction}
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                db.close()
            except Exception:
                pass


def void_attendance(employee_id, event_id, reason, actor, conn=None):
    """Koreksi event absensi: tandai void, jangan hapus riwayat."""
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('alasan wajib diisi')
    db, own = _open(conn)
    if not db:
        raise RuntimeError('DB master tidak tersedia')
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM employee_attendance_events
               WHERE id=%s AND employee_id=%s""", (event_id, employee_id))
        row = cursor.fetchone()
        if not row:
            raise ValueError('not_found')
        if row.get('voided_at'):
            raise ValueError('already_voided')
        cursor.execute(
            """UPDATE employee_attendance_events SET voided_at=NOW(),
               voided_by=%s, void_reason=%s WHERE id=%s""",
            (str(actor or '')[:100], reason[:500], event_id))
        if own:
            db.commit()
        return {'event_id': event_id, 'voided': True}
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                db.close()
            except Exception:
                pass


def deactivate_employee(employee_id, reason, actor, conn=None):
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('alasan wajib diisi')
    db, own = _open(conn)
    if not db:
        raise RuntimeError('DB master tidak tersedia')
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM employees WHERE id=%s', (employee_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError('not_found')
        cursor.execute(
            """UPDATE employees SET is_active=0, deactivation_reason=%s,
               deactivated_by=%s, deactivated_at=NOW(), updated_at=NOW()
               WHERE id=%s""",
            (reason[:500], str(actor or '')[:100], employee_id))
        record_event(row.get('case_id') or '', row.get('nik') or '',
                     'EMPLOYEE_DEACTIVATED', branch_code=row.get('branch_code', ''),
                     actor_name=actor, note=reason, conn=db)
        if own:
            db.commit()
        return {'employee_id': employee_id, 'is_active': 0}
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                db.close()
            except Exception:
                pass


def reactivate_employee(employee_id, actor, conn=None):
    db, own = _open(conn)
    if not db:
        raise RuntimeError('DB master tidak tersedia')
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM employees WHERE id=%s', (employee_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError('not_found')
        cursor.execute(
            """UPDATE employees SET is_active=1, deactivated_at=NULL,
               deactivated_by=NULL, deactivation_reason=NULL,
               updated_at=NOW() WHERE id=%s""", (employee_id,))
        record_event(row.get('case_id') or '', row.get('nik') or '',
                     'EMPLOYEE_REACTIVATED', branch_code=row.get('branch_code', ''),
                     actor_name=actor, conn=db)
        if own:
            db.commit()
        return {'employee_id': employee_id, 'is_active': 1}
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                db.close()
            except Exception:
                pass
