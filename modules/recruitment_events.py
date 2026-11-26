"""Linimasa kejadian rekrutmen berbasis NIK (Rilis C — Task C2).

Event adalah jejak audit tambahan, bukan sumber kebenaran: tabel modul tetap
yang berlaku. Penulisan bersifat best-effort — kegagalan master tidak pernah
menggagalkan aksi pengguna di cabang. Kunci idempoten event adalah
`(source_module, branch_code, source_id, event_type)`.
"""
import json
import re
from datetime import datetime

from modules.config import get_master_connection

EVENT_TYPES = frozenset({
    'RECEPTIONIST_CREATED', 'VERIFIED', 'INTERVIEW',
    'TRAINING_H1', 'TRAINING_H2', 'TRAINING_H3', 'TRAINING_H4',
    'RESIGNED', 'PASSED', 'REJECTED',
    'CV_SUBMITTED', 'TRAINING_PORTAL_D1', 'TRAINING_PORTAL_D2',
    'TKD_STARTED', 'TKD_SUBMITTED', 'TKD_SCORED',
    'FIRSTWORK_SUBMITTED', 'CARD_ISSUED',
    'EMPLOYEE_CREATED', 'EMPLOYEE_DEACTIVATED', 'EMPLOYEE_REACTIVATED',
    'NIK_LINKED',
})

_INSERT_SQL = """
    INSERT IGNORE INTO recruitment_events
        (case_id, nik, event_type, event_at, branch_code, actor_role,
         actor_name, source_module, source_id, note, metadata_json)
    VALUES
        (%(case_id)s, %(nik)s, %(event_type)s,
         COALESCE(%(event_at)s, NOW()), %(branch_code)s,
         %(actor_role)s, %(actor_name)s, %(source_module)s, %(source_id)s,
         %(note)s, %(metadata_json)s)
"""

_STEP_EVENTS = {
    'CV': 'CV_SUBMITTED',
    'TRAINING': 'TRAINING_PORTAL_D2',
    'TKD': 'TKD_SCORED',
    'FIRSTWORK': 'FIRSTWORK_SUBMITTED',
}

_STATUS_EVENTS = {
    'lulus': 'PASSED',
    'resigned': 'RESIGNED',
    'rejected': 'REJECTED',
    'training_1': 'TRAINING_H1',
    'training_2': 'TRAINING_H2',
    'training_3': 'TRAINING_H3',
    'training_4': 'TRAINING_H4',
}


def _masked(value):
    """Mask 16 digit NIK yang mungkin muncul di pesan error driver DB."""
    return re.sub(r'\d{16}', '****************', str(value or ''))


def _write_event(case_id, nik, event_type, branch_code='', actor_role='',
                 actor_name='', source_module='manual', source_id='',
                 event_at=None, note='', metadata=None, conn=None):
    """Tulis satu event. Return 'inserted' | 'duplicate' | 'invalid' | 'error'."""
    if event_type not in EVENT_TYPES:
        return 'invalid'
    own = conn is None
    db = conn or get_master_connection()
    if db is None:
        return 'error'
    params = {
        'case_id': case_id,
        'nik': nik,
        'event_type': event_type,
        'event_at': event_at,
        'branch_code': str(branch_code or '')[:10],
        'actor_role': str(actor_role or '')[:50],
        'actor_name': str(actor_name or '')[:100],
        'source_module': str(source_module or 'manual')[:30],
        'source_id': str(source_id or '')[:64],
        'note': str(note or '')[:500],
        'metadata_json': json.dumps(metadata or {}, ensure_ascii=False),
    }
    try:
        cur = db.cursor(dictionary=True)
        cur.execute(_INSERT_SQL, params)
        rowcount = getattr(cur, 'rowcount', 1)
        cur.close()
        if own:
            db.commit()
        return 'inserted' if rowcount else 'duplicate'
    except Exception as exc:
        print(f'[recruitment-events] gagal menulis {event_type}: {_masked(exc)}')
        if own:
            try:
                db.rollback()
            except Exception:
                pass
        return 'error'
    finally:
        if own:
            try:
                db.close()
            except Exception:
                pass


def record_event(case_id, nik, event_type, branch_code='', actor_role='',
                 actor_name='', source_module='manual', source_id='',
                 event_at=None, note='', metadata=None, conn=None):
    """Best-effort event writer — tidak pernah melempar exception.

    `INSERT IGNORE` membuat putaran ulang aman; duplikat dianggap sukses agar
    aksi sumber tidak perlu tahu apakah event sudah pernah ditulis.
    """
    status = _write_event(
        case_id, nik, event_type, branch_code=branch_code,
        actor_role=actor_role, actor_name=actor_name,
        source_module=source_module, source_id=source_id, event_at=event_at,
        note=note, metadata=metadata, conn=conn,
    )
    return status in ('inserted', 'duplicate')


def fetch_timeline(cursor, case_id, limit=200):
    """Kembalikan event terbaru dalam bentuk siap-JSON (tanpa NIK lengkap)."""
    cursor.execute(
        """SELECT id, event_type, event_at, branch_code, actor_role,
                  actor_name, source_module, note, metadata_json
           FROM recruitment_events
           WHERE case_id = %s
           ORDER BY event_at DESC, id DESC
           LIMIT %s""",
        (case_id, min(int(limit or 200), 500)),
    )
    rows = []
    for raw in cursor.fetchall() or []:
        row = dict(raw)
        meta = row.pop('metadata_json', None)
        try:
            row['metadata'] = json.loads(meta or '{}')
        except (TypeError, ValueError):
            row['metadata'] = {}
        when = row.get('event_at')
        if isinstance(when, datetime):
            row['event_at'] = when.isoformat(sep=' ')
        rows.append(row)
    return rows


def _select_rows(db, table):
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(f'SELECT * FROM {table}')
        return [dict(row) for row in (cur.fetchall() or [])]
    finally:
        cur.close()


def rebuild_events(conn=None, branch_rows=None, commit=True):
    """Bangun ulang event dari tabel sumber. Idempoten lewat kunci unik DB."""
    own = conn is None
    db = conn or get_master_connection()
    if db is None:
        return {'inserted': 0, 'skipped': 0}
    inserted = 0
    skipped = 0
    emitted = set()
    try:
        cases = _select_rows(db, 'recruitment_cases')
        case_by_nik = {str(r.get('nik') or ''): r for r in cases}

        def emit(row, event_type, event_at=None, branch_code='',
                 actor_role='', actor_name='', source_module='', source_id='',
                 note='', metadata=None):
            nonlocal inserted, skipped
            nik = str(row.get('nik') or '')
            case = case_by_nik.get(nik)
            case_id = (row.get('case_id') or (case or {}).get('case_id') or '')
            if not case_id:
                skipped += 1
                return
            code = str(branch_code or row.get('branch_code') or
                       (case or {}).get('first_branch') or '')
            key = (source_module, code, str(source_id), event_type)
            if key in emitted:
                skipped += 1
                return
            emitted.add(key)
            status = _write_event(
                case_id, nik, event_type, branch_code=code,
                actor_role=actor_role, actor_name=actor_name,
                source_module=source_module, source_id=str(source_id),
                event_at=event_at, note=note, metadata=metadata, conn=db,
            )
            if status == 'inserted':
                inserted += 1
            else:
                skipped += 1

        for case in cases:
            emit(case, 'RECEPTIONIST_CREATED',
                 event_at=case.get('first_seen_at'),
                 source_module='case', source_id=case.get('case_id', ''))

        steps = _select_rows(db, 'recruitment_steps')
        cv_cases = set()
        for step in steps:
            if str(step.get('status') or '').upper() != 'SELESAI':
                continue
            kind = str(step.get('step_type') or '')
            if kind == 'CV':
                cv_cases.add(step.get('case_id'))
            event_type = _STEP_EVENTS.get(kind)
            if not event_type or not step.get('completed_at'):
                continue
            emit({'nik': '', 'case_id': step.get('case_id')}, event_type,
                 event_at=step.get('completed_at'),
                 branch_code=step.get('branch_code', ''),
                 source_module='step', source_id=step.get('id', ''))

        for row in _select_rows(db, 'cv_online_submissions'):
            case = case_by_nik.get(str(row.get('nik') or ''))
            if case and case.get('case_id') in cv_cases:
                continue
            emit(row, 'CV_SUBMITTED', event_at=row.get('submitted_at'),
                 source_module='cv', source_id=row.get('id', ''))

        for row in _select_rows(db, 'first_work_submissions'):
            emit(row, 'CARD_ISSUED', event_at=row.get('submitted_at'),
                 source_module='first_work', source_id=row.get('id', ''),
                 metadata={'registration_no': row.get('registration_no', '')})

        for row in branch_rows or []:
            code = str(row.get('branch_code') or '')
            sid = row.get('display_id') or row.get('id') or ''
            emit(row, 'RECEPTIONIST_CREATED', event_at=row.get('created_at'),
                 branch_code=code, source_module='applicants', source_id=sid)
            if row.get('verified_at'):
                emit(row, 'VERIFIED', event_at=row.get('verified_at'),
                     branch_code=code, source_module='applicants', source_id=sid)
            if row.get('interview_at'):
                emit(row, 'INTERVIEW', event_at=row.get('interview_at'),
                     branch_code=code, source_module='applicants', source_id=sid)
            final = _STATUS_EVENTS.get(str(row.get('status') or ''))
            if final:
                emit(row, final, event_at=row.get('updated_at') or row.get('created_at'),
                     branch_code=code, source_module='applicants', source_id=sid)

        if commit:
            db.commit()
        else:
            db.rollback()
    finally:
        if own:
            db.close()
    return {'inserted': inserted, 'skipped': skipped}
