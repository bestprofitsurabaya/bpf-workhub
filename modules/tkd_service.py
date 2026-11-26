"""Layanan DB untuk TKD online (Rilis C — Task 5).

Semua fungsi di sini menerima cursor yang sudah dibuka pemanggil dan
TIDAK commit/rollback/close: pemanggil mengatur transaksi. NIK dipakai hanya
sebagai kunci pencarian identitas, tidak pernah ditulis ke tabel TKD.

Identitas pelamar = NIK 16 digit. Tanggal lahir tidak lagi diminta karena
sudah terenkode di NIK dan tidak menambah keamanan. Kegagalan identitas selalu
dilaporkan sebagai `None` tanpa detail.
"""
import json
import math
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from modules.helpers import normalize_nik
from modules.tkd_core import (DEFAULT_QUOTA, MAX_ATTEMPTS, as_json,
                              compute_score, grade_answer,
                              public_state, select_questions)

# Mengikuti nilai DEFAULT pada tkd_settings (skema) bila baris belum ada.
DEFAULT_SETTINGS = {
    'question_count': 20,
    'duration_minutes': 25,
    'pass_score': 70.0,
    'max_attempts': MAX_ATTEMPTS,
    'quota': dict(DEFAULT_QUOTA),
    'shuffle_options': 1,
    'active': 0,
}

_CASE_COLUMNS = ('case_id, nik, nama, tanggal_lahir, first_branch, '
                'tkd_score, tkd_score_source, tkd_score_note, tkd_passed')


def _as_iso(value):
    """Ubah tanggal DB menjadi teks ISO; None tetap None, teks apa adanya."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _as_float(value):
    """Ubah angka DB (termasuk Decimal/str) menjadi float; sampah → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_bool(value):
    """Normalisasi flag angka/teks dari DB menjadi bool."""
    if isinstance(value, bool):
        return value
    number = _as_float(value)
    return bool(number) if number is not None else False


def _as_datetime(value):
    """Ubah tanggal DB menjadi datetime; None bila tidak terbaca."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        text = value.strip().replace('Z', '+00:00')
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    return None


def resolve_branch_token(cursor, token: str) -> str:
    """Cari cabang untuk token form aktif; '' bila token tidak sah."""
    if not token:
        return ''
    cursor.execute(
        'SELECT branch_code FROM cv_online_branch_forms '
        'WHERE form_token=%s AND active=1 LIMIT 1', (str(token).strip(),))
    row = cursor.fetchone()
    return str(row['branch_code'] or '').strip() if row and row.get('branch_code') else ''


def load_settings(cursor) -> dict:
    """Baca pengaturan TKD dengan kuota ter-parse; default bila baris hilang."""
    cursor.execute('SELECT * FROM tkd_settings WHERE id=1')
    row = cursor.fetchone()
    stored = dict(row) if row else {}

    settings = dict(DEFAULT_SETTINGS)
    for key, value in stored.items():
        if value is not None:
            settings[key] = value
    settings['pass_score'] = _as_float(settings.get('pass_score'))
    if settings['pass_score'] is None:
        settings['pass_score'] = DEFAULT_SETTINGS['pass_score']

    quota = as_json(settings.get('quota'))
    settings['quota'] = dict(quota) if isinstance(quota, dict) and quota else dict(DEFAULT_QUOTA)
    return settings


def fetch_case_by_nik(cursor, nik: str, for_update: bool = False) -> dict | None:
    """Ambil kasus berdasarkan NIK; kunci baris bila `for_update`."""
    sql = ('SELECT ' + _CASE_COLUMNS + ' FROM recruitment_cases '
           'WHERE nik=%s LIMIT 1')
    if for_update:
        sql += ' FOR UPDATE'
    cursor.execute(sql, (nik,))
    return cursor.fetchone()


def verify_identity(cursor, nik: str) -> dict | None:
    """Verifikasi NIK 16 digit; kembalikan kasus tanpa detail bila gagal."""
    nik, _raw = normalize_nik(nik)
    if len(nik) != 16:
        return None

    case = fetch_case_by_nik(cursor, nik)
    if not case:
        return None

    result = dict(case)
    result['tanggal_lahir'] = _as_iso(case.get('tanggal_lahir'))
    result['tkd_score'] = _as_float(case.get('tkd_score'))
    return result


def fetch_attempts(cursor, case_id: str) -> list[dict]:
    """Daftar attempt satu kasus, urut berdasarkan nomor attempt."""
    cursor.execute('SELECT * FROM tkd_attempts WHERE case_id=%s '
                   'ORDER BY attempt_no', (case_id,))
    return list(cursor.fetchall() or [])


def fetch_tkd_steps(cursor, case_id: str) -> list[dict]:
    """Langkah TKD kasus; urutan id membuat hasil deterministik."""
    cursor.execute(
        'SELECT id, step_type, status, branch_code, evidence_type, evidence_id, '
        "completed_at FROM recruitment_steps WHERE case_id=%s AND step_type='TKD' "
        'ORDER BY id', (case_id,))
    return list(cursor.fetchall() or [])


def fetch_active_questions(cursor) -> list[dict]:
    """Bank soal aktif dalam urutan kategori, sort_order, lalu id."""
    cursor.execute('SELECT * FROM tkd_questions WHERE active=1 '
                   'ORDER BY category, sort_order, id')
    return list(cursor.fetchall() or [])


def fetch_attempt(cursor, attempt_id: str, for_update=False) -> dict | None:
    """Ambil satu attempt; kunci baris bila `for_update`."""
    sql = 'SELECT * FROM tkd_attempts WHERE id=%s LIMIT 1'
    if for_update:
        sql += ' FOR UPDATE'
    cursor.execute(sql, (attempt_id,))
    return cursor.fetchone()


def fetch_attempt_items(cursor, attempt_id: str) -> list[dict]:
    """Item attempt beserta snapshot jawaban, urut berdasarkan posisi."""
    cursor.execute('SELECT * FROM tkd_attempt_items WHERE attempt_id=%s '
                   'ORDER BY position', (attempt_id,))
    return list(cursor.fetchall() or [])


# ---------------------------------------------------------------------------
# Attempt: mulai, finalisasi lazy, dan skor resmi kasus
# ---------------------------------------------------------------------------

def create_attempt(cursor, case, branch_code, modal_tier, settings,
                   questions, now=None, rng=None) -> dict:
    """Buat satu attempt beserta 20 soal + 1 soal profil tersnapshot.

    Kunci jawaban dibekukan di `tkd_attempt_items.snapshot`, jadi edit bank
    soal setelah attempt dibuat tidak pernah mengubah penilaiannya.
    """
    settings = settings or {}
    case = case or {}
    selected = select_questions(questions, settings, modal_tier, rng)
    if not selected:
        raise ValueError('Bank soal belum siap')

    cursor.execute('SELECT MAX(attempt_no) AS attempt_no FROM tkd_attempts '
                   'WHERE case_id=%s', (case.get('case_id'),))
    rows = list(cursor.fetchall() or [])
    last_no = max((number for number in (
        _as_float((row or {}).get('attempt_no')) for row in rows)
        if number is not None), default=None)
    attempt_no = int(last_no) + 1 if last_no is not None else 1

    now = now or datetime.now()
    duration = int(_as_float(settings.get('duration_minutes'))
                   or DEFAULT_SETTINGS['duration_minutes'])
    pass_score = _as_float(settings.get('pass_score'))
    if pass_score is None:
        pass_score = DEFAULT_SETTINGS['pass_score']
    quota = as_json(settings.get('quota'), {})
    if not isinstance(quota, dict) or not quota:
        quota = dict(DEFAULT_QUOTA)
    settings_snapshot = json.dumps({
        'question_count': int(_as_float(settings.get('question_count'))
                              or DEFAULT_SETTINGS['question_count']),
        'duration_minutes': duration,
        'quota': dict(quota),
        'max_attempts': int(_as_float(settings.get('max_attempts'))
                            or DEFAULT_SETTINGS['max_attempts']),
        'shuffle_options': _as_bool(settings.get(
            'shuffle_options', DEFAULT_SETTINGS['shuffle_options'])),
    }, ensure_ascii=False)

    attempt_id = 'TKD-' + uuid.uuid4().hex[:16]
    attempt = {
        'id': attempt_id,
        'case_id': case.get('case_id'),
        'attempt_no': attempt_no,
        'branch_code': str(branch_code or ''),
        'modal_tier': str(modal_tier or ''),
        'status': 'BERLANGSUNG',
        'settings_snapshot': settings_snapshot,
        'pass_score_snapshot': pass_score,
        'started_at': now,
        'expires_at': now + timedelta(minutes=duration),
        'submitted_at': None,
        'score': None,
        'total_points': 0,
        'correct_count': 0,
        'passed': None,
    }
    columns = ('id, case_id, attempt_no, branch_code, modal_tier, status, '
               'settings_snapshot, pass_score_snapshot, started_at, expires_at, '
               'submitted_at, score, total_points, correct_count, passed')
    cursor.execute(
        'INSERT INTO tkd_attempts (' + columns + ') VALUES '
        '(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        tuple(attempt[name] for name in (
            'id', 'case_id', 'attempt_no', 'branch_code', 'modal_tier', 'status',
            'settings_snapshot', 'pass_score_snapshot', 'started_at', 'expires_at',
            'submitted_at', 'score', 'total_points', 'correct_count', 'passed')))

    shuffle = _as_bool(settings.get(
        'shuffle_options', DEFAULT_SETTINGS['shuffle_options']))
    picker = rng or random
    for position, question in enumerate(selected, 1):
        question = question or {}
        raw_options = as_json(question.get('options'), [])
        options = ([dict(option) if isinstance(option, dict)
                    else {'text': str(option)} for option in raw_options]
                   if isinstance(raw_options, (list, tuple)) else [])
        if shuffle and question.get('type') == 'MCQ' and len(options) > 1:
            picker.shuffle(options)
        key = as_json(question.get('answer'))
        key = dict(key) if isinstance(key, dict) else None
        snapshot = {
            'code': str(question.get('code') or ''),
            'prompt': str(question.get('prompt') or ''),
            'type': str(question.get('type') or ''),
            'category': str(question.get('category') or ''),
            'options': options,
            'answer': key,
            'points': _as_float(question.get('points')) or 0.0,
            'tolerance': _as_float((key or {}).get('tolerance')) or 0.0,
            'modal_tier': question.get('modal_tier') or None,
        }
        cursor.execute(
            'INSERT INTO tkd_attempt_items '
            '(attempt_id, question_id, position, snapshot) '
            'VALUES (%s,%s,%s,%s)',
            (attempt_id, question.get('id'), position,
             json.dumps(snapshot, ensure_ascii=False)))

    # Baca lagi baris item: pemanggil (dan route) memakai objek hasil akhir ini.
    items = fetch_attempt_items(cursor, attempt_id)
    return {'attempt': attempt, 'items': items}


def finalize_attempt(cursor, attempt, status='KEDALUWARSA', now=None) -> dict:
    """Nilai item dari snapshot, simpan hasil, lalu sinkronkan skor kasus.

    Idempoten: attempt yang sudah SELESAI/KEDALUWARSA dikembalikan apa adanya.
    Dict attempt yang diberikan pemanggil dimutasi in-place agar pemanggil
    dan DB tiruan melihat status/skor terbaru tanpa query ulang.
    """
    attempt = attempt or {}
    if str(attempt.get('status') or '').upper() in ('SELESAI', 'KEDALUWARSA'):
        return attempt

    attempt_id = attempt.get('id')
    threshold = _as_float(attempt.get('pass_score_snapshot'))
    if threshold is None:
        threshold = DEFAULT_SETTINGS['pass_score']
    scored = []
    for item in fetch_attempt_items(cursor, attempt_id):
        item = item or {}
        snapshot = as_json(item.get('snapshot'), {}) or {}
        correct, awarded = grade_answer(snapshot, as_json(item.get('answer')))
        item['is_correct'] = correct
        item['points_awarded'] = awarded
        cursor.execute(
            'UPDATE tkd_attempt_items SET is_correct=%s, points_awarded=%s '
            'WHERE attempt_id=%s AND position=%s',
            (correct, awarded, attempt_id, item.get('position')))
        scored.append({
            'points': _as_float(snapshot.get('points')) or 0.0,
            'is_correct': correct,
            'points_awarded': awarded,
        })

    result = compute_score(scored, threshold)
    submitted_at = now or datetime.now()
    cursor.execute(
        'UPDATE tkd_attempts SET status=%s, submitted_at=%s, score=%s, '
        'total_points=%s, correct_count=%s, passed=%s WHERE id=%s',
        (status, submitted_at, result['score'], result['total_points'],
         result['correct_count'], result['passed'], attempt_id))
    attempt.update(status=status, submitted_at=submitted_at,
                   score=result['score'], total_points=result['total_points'],
                   correct_count=result['correct_count'], passed=result['passed'])
    sync_case_score(cursor, attempt.get('case_id'), threshold,
                    attempt.get('branch_code') or '')
    return attempt


def finalize_expired(cursor, case_id, now=None) -> list[dict]:
    """Finalisasi lazy attempt BERLANGSUNG yang sudah lewat `expires_at`.

    Attempt kedaluwarsa tetap dihitung sebagai kesempatan dan tetap bisa
    menjadi skor terbaik; penilaian memakai jawaban yang tersimpan.
    """
    now = now or datetime.now()
    cursor.execute(
        'SELECT * FROM tkd_attempts WHERE case_id=%s '
        "AND status='BERLANGSUNG' AND expires_at < %s FOR UPDATE",
        (case_id, now))
    rows = list(cursor.fetchall() or [])
    done = []
    for row in rows:
        row = row or {}
        expiry = _as_datetime(row.get('expires_at'))
        # DB tiruan tidak selalu menerapkan klausa WHERE; jaga idempotensi.
        if expiry is not None and expiry >= now:
            continue
        done.append(finalize_attempt(cursor, row, 'KEDALUWARSA', now))
    return done


def sync_case_score(cursor, case_id, pass_score, attempt_branch='') -> dict:
    """Tulis skor resmi kasus dari attempt auto terbaik, kecuali MANUAL.

    Semua baris langkah TKD non-DIKECUALIKAN disamakan statusnya; skor resmi
    tetap satu di kasus walaupun attempt dibuat dari cabang berbeda.
    """
    cursor.execute(
        'SELECT score, passed, id, submitted_at FROM tkd_attempts '
        "WHERE case_id=%s AND status IN ('SELESAI','KEDALUWARSA') "
        'AND score IS NOT NULL '
        'ORDER BY score DESC, submitted_at ASC LIMIT 1', (case_id,))
    rows = [row for row in (cursor.fetchall() or [])
            if _as_float((row or {}).get('score')) is not None]

    def _order(row):
        submitted = _as_datetime(row.get('submitted_at'))
        return (-(_as_float(row.get('score')) or 0.0),
                submitted.timestamp() if submitted else float('inf'))

    best = sorted(rows, key=_order)[0] if rows else None

    cursor.execute(
        'SELECT tkd_score, tkd_score_source, tkd_passed, tkd_best_attempt_id, '
        'first_branch FROM recruitment_cases WHERE case_id=%s', (case_id,))
    case = cursor.fetchone() or {}
    source = str(case.get('tkd_score_source') or '').upper()
    current_score = _as_float(case.get('tkd_score'))
    if source == 'MANUAL' or best is None:
        return {
            'score': current_score if current_score is not None else 0.0,
            'source': source,
            'passed': _as_bool(case.get('tkd_passed')),
            'best_attempt_id': case.get('tkd_best_attempt_id'),
        }

    score = _as_float(best.get('score')) or 0.0
    passed = (_as_bool(best.get('passed')) if best.get('passed') is not None
              else score >= (_as_float(pass_score) or 0.0))
    best_id = str(best.get('id') or '')
    submitted = _as_datetime(best.get('submitted_at'))

    cursor.execute(
        "UPDATE recruitment_cases SET tkd_score=%s, tkd_score_source='AUTO', "
        "tkd_best_attempt_id=%s, tkd_passed=%s, "
        "tkd_score_updated_by='system:tkd', tkd_score_updated_at=NOW() "
        'WHERE case_id=%s', (score, best_id, passed, case_id))

    branch = str(attempt_branch or case.get('first_branch') or '').strip()
    cursor.execute(
        "INSERT IGNORE INTO recruitment_steps "
        "(case_id, step_type, status, branch_code) "
        "VALUES (%s,'TKD','PENDING',%s)", (case_id, branch))
    if passed:
        cursor.execute(
            "UPDATE recruitment_steps SET status='SELESAI', completed_at=%s, "
            "evidence_type='tkd_attempt', evidence_id=%s, actor='system:tkd' "
            "WHERE case_id=%s AND step_type='TKD' "
            "AND status<>'DIKECUALIKAN'", (submitted, best_id, case_id))
    else:
        cursor.execute(
            "UPDATE recruitment_steps SET status='PENDING', completed_at=NULL, "
            "evidence_type='', evidence_id='' "
            "WHERE case_id=%s AND step_type='TKD' "
            "AND status<>'DIKECUALIKAN'", (case_id,))
    return {'score': score, 'source': 'AUTO', 'passed': passed,
            'best_attempt_id': best_id}


# ---------------------------------------------------------------------------
# Koreksi skor manual: keputusan staff mengalahkan skor auto berapa pun
# ---------------------------------------------------------------------------

def _latest_branch_code(cursor, case_id, fallback=''):
    """Cabang terakhir yang dipakai kasus; jatuh ke cabang asal bila kosong."""
    cursor.execute(
        'SELECT branch_code FROM case_branch_history WHERE case_id=%s '
        'ORDER BY last_seen_at DESC, first_seen_at DESC LIMIT 1', (case_id,))
    row = cursor.fetchone() or {}
    return str(row.get('branch_code') or fallback or '').strip()[:10]


def set_manual_score(cursor, case_id, score, reason, actor, pass_score,
                     branch_code='') -> dict:
    """Tulis skor koreksi staff sebagai skor resmi kasus.

    Skor manual berlaku sampai staff mengubahnya lagi: `sync_case_score`
    tidak pernah menimpa sumber MANUAL, dan koreksi berikutnya memakai skor
    kasus yang sudah ada sebagai `old_score`. Baris attempt tidak disentuh.
    """
    value = _as_float(score)
    if value is None or not 0.0 <= value <= 100.0:
        raise ValueError('Skor TKD harus angka 0–100.')
    threshold = _as_float(pass_score)
    if threshold is None:
        threshold = DEFAULT_SETTINGS['pass_score']
    note = str(reason or '').strip()[:500]
    editor = str(actor or '').strip()[:100]

    cursor.execute(
        'SELECT case_id, first_branch, tkd_score FROM recruitment_cases '
        'WHERE case_id=%s LIMIT 1', (case_id,))
    case = cursor.fetchone()
    if not case:
        raise ValueError('Kasus tidak ditemukan')

    old_score = _as_float(case.get('tkd_score'))
    branch = str(branch_code or '').strip()[:10]
    if not branch:
        branch = _latest_branch_code(cursor, case_id, case.get('first_branch'))
    passed = value >= threshold

    cursor.execute(
        "UPDATE recruitment_cases SET tkd_score=%s, tkd_score_source='MANUAL', "
        "tkd_score_note=%s, tkd_score_updated_by=%s, tkd_score_updated_at=NOW(), "
        'tkd_passed=%s, tkd_best_attempt_id=NULL WHERE case_id=%s',
        (value, note, editor, passed, case_id))

    cursor.execute(
        "INSERT IGNORE INTO recruitment_steps "
        "(case_id, step_type, status, branch_code) "
        "VALUES (%s,'TKD','PENDING',%s)", (case_id, branch))
    if passed:
        cursor.execute(
            "UPDATE recruitment_steps SET status='SELESAI', completed_at=NOW(), "
            "evidence_type='manual_score', evidence_id='', actor=%s "
            "WHERE case_id=%s AND step_type='TKD' "
            "AND status<>'DIKECUALIKAN'", (editor, case_id))
    else:
        cursor.execute(
            "UPDATE recruitment_steps SET status='PENDING', completed_at=NULL, "
            "evidence_type='manual_score', evidence_id='', actor=%s "
            "WHERE case_id=%s AND step_type='TKD' "
            "AND status<>'DIKECUALIKAN'", (editor, case_id))

    return {'old_score': old_score, 'score': value, 'passed': passed,
            'source': 'MANUAL', 'branch_code': branch}


_RESULT_MESSAGES = {
    'LULUS': 'Selamat, Anda lulus TKD.',
    'HABIS': 'Kesempatan habis. Hubungi Traineer cabang.',
    'BISA_COBA': 'Anda masih bisa mencoba lagi.',
    'DIKECUALIKAN': 'TKD dikecualikan staff. Hubungi Traineer cabang.',
    'SKOR_BELUM_TERCATAT': 'Skor belum tercatat. Hubungi Traineer cabang.',
    'SEGERA': 'TKD segera tersedia.',
    'BERLANGSUNG': 'Ujian masih berlangsung.',
    'BELUM': 'TKD belum dimulai.',
}


def attempt_result(cursor, attempt, settings) -> dict:
    """Payload hasil publik: angka/status saja, tanpa kunci atau poin butir."""
    attempt = attempt or {}
    case_id = attempt.get('case_id') or ''
    attempts = fetch_attempts(cursor, case_id)
    steps = fetch_tkd_steps(cursor, case_id)
    cursor.execute(
        'SELECT tkd_score, tkd_score_source, tkd_passed FROM recruitment_cases '
        'WHERE case_id=%s', (case_id,))
    case = cursor.fetchone() or {}
    state = public_state(case, attempts, steps, settings)

    finished = [score for score in (
        _as_float((row or {}).get('score')) for row in attempts
        if str((row or {}).get('status') or '').upper() in ('SELESAI', 'KEDALUWARSA'))
        if score is not None]
    score = _as_float(attempt.get('score'))
    official_score = _as_float(case.get('tkd_score'))
    return {
        'score': score if score is not None else 0.0,
        'passed': _as_bool(attempt.get('passed')),
        'official_score': official_score,
        'official_passed': _as_bool(case.get('tkd_passed')),
        'best_score': max(finished) if finished else 0.0,
        'attempts_used': state['attempts_used'],
        'max_attempts': state['max_attempts'],
        'state': state['state'],
        'source': case.get('tkd_score_source'),
        'message': _RESULT_MESSAGES.get(state['state'], ''),
    }
