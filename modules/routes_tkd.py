"""TKD online — endpoint publik status/mulai dan endpoint staff (Rilis C).

Alur publik memakai NIK + tanggal lahir + token cabang hanya untuk verifikasi;
NIK tidak pernah ditulis ke sesi, respons, atau audit. Sesi menyimpan
`tkd_case_id`, `tkd_verified_at` (epoch), dan `tkd_branch` selama maksimal
dua jam. Semua jawaban route publik bersifat `no-store` dan kunci jawaban
tidak pernah dikirim ke pelamar.

Endpoint staff (hasil, review, koreksi skor, pengaturan) memakai NIK hanya
sebagai filter/identitas dan selalu mengirimkannya dalam bentuk termasker;
kunci jawaban sengaja dikirim hanya lewat `/review`.

Semua akses DB lewat `svc.<fn>` supaya pemanggil/tes dapat mengganti layanan.
"""
import csv
import hashlib
import io
import json
import re
import time
from datetime import datetime, timedelta

from flask import Response, jsonify, request, session

from modules import tkd_service as svc
from modules.recruitment_events import record_event
from modules.admin_scope import is_ho_admin
# Sumber tunggal masker NIK — routes_recruitment tidak mengimpor routes_tkd,
# jadi import ini tidak membentuk siklus.
from modules.routes_recruitment import _mask_nik
from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, normalize_nik,
                             redis_rate_hit, role_required)
from modules.tkd_core import (CSV_COLUMNS, MODAL_TIERS, as_json,
                              csv_to_question_rows, import_rows,
                              normalize_question, parse_numeric, public_state,
                              question_row_to_csv, readiness, validate_question,
                              validate_settings)

# Peran staff yang boleh mengelola TKD.
_STAFF_ROLES = ('traineer', 'ga_hr', 'admin')
# Batas teks CSV impor: 300 ribu karakter (~500 baris soal dengan prompt panjang).
_MAX_IMPORT_CHARS = 300_000
_SESSION_HOURS = 2
_SESSION_SECONDS = _SESSION_HOURS * 3600
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# Dua jalur kuota publik: 10/min per IP dan 5/min per hash NIK (lihat `_rate`).
_IP_LIMIT = 10
_NIK_LIMIT = 5
_RATE_WINDOW = 60
_RATE_PREFIX = 'tkd'

# Pesan kegagalan sengaja generik: tidak menyebut nama, skor, cabang, atau attempt.
_MSG_INCOMPLETE = 'Data belum lengkap.'
_MSG_BAD_LINK = 'Tautan tidak valid atau sudah dirotasi.'
_MSG_IDENTITY = 'Data belum lengkap, hubungi Traineer.'
_MSG_CLOSED = 'TKD belum dibuka. Hubungi Traineer cabang.'
_MSG_RATE = 'Terlalu banyak permintaan. Coba lagi sebentar.'
_MSG_DB = 'DB error'
_MSG_SESSION = 'Sesi tidak valid atau sudah berakhir.'
_MSG_NOT_FOUND = 'Attempt tidak ditemukan.'
_MSG_FINISHED = 'Ujian sudah selesai.'
_MSG_EXPIRED = 'Waktu ujian habis.'
_MSG_UNFINISHED = 'Ujian belum selesai.'

# Staff: `None` hanya untuk Admin Pusat; cabang kosong memakai sentinel agar
# tidak naik menjadi akses lintas cabang.
_NO_BRANCH = '__NOBRANCH__'
_MAX_ATTEMPT_ROWS = 200
_REVIEW_SNAPSHOT_KEYS = ('prompt', 'type', 'category', 'options', 'answer',
                         'points')
_REVIEW_ATTEMPT_KEYS = ('id', 'case_id', 'attempt_no', 'branch_code',
                        'modal_tier', 'status', 'started_at', 'expires_at',
                        'submitted_at', 'score', 'passed')
_SETTINGS_KEYS = ('question_count', 'duration_minutes', 'pass_score',
                  'max_attempts', 'quota', 'shuffle_options', 'active')

_START_BLOCK_MESSAGES = {
    'DIKECUALIKAN': 'TKD dikecualikan staff. Hubungi Traineer cabang.',
    'LULUS': 'Selamat, Anda lulus TKD.',
    'HABIS': 'Kesempatan habis. Hubungi Traineer cabang.',
    'SKOR_BELUM_TERCATAT': 'Skor belum tercatat. Hubungi Traineer cabang.',
    'SEGERA': _MSG_CLOSED,
    'BERLANGSUNG': 'Ujian masih berlangsung.',
}


def _public(payload, status=200):
    """Semua respons TKD (termasuk error) tidak boleh disimpan browser/proxy."""
    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'no-store'
    return resp, status


def _nik_key(nik):
    """Kunci hash NIK untuk rate limit — NIK mentah tidak dipakai sebagai kunci."""
    return hashlib.sha256(str(nik or '').encode()).hexdigest()[:32]


def _rate(ip, nik, action):
    """Satu hit kuota per IP dan per hash NIK; keduanya harus masih diizinkan."""
    return (redis_rate_hit(f'{action}|ip|{ip}', _IP_LIMIT, _RATE_WINDOW,
                           prefix=_RATE_PREFIX)
            and redis_rate_hit(f'{action}|nik|{_nik_key(nik)}', _NIK_LIMIT,
                               _RATE_WINDOW, prefix=_RATE_PREFIX))


def _valid_date(value):
    """Terima hanya tanggal ISO YYYY-MM-DD yang benar-benar ada."""
    text = str(value or '').strip()
    if not _DATE_RE.match(text):
        return False
    try:
        datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        return False
    return True


def _verify_body(body):
    """Validasi isian publik; kembalikan `(data, None)` atau `(None, error)`."""
    body = body if isinstance(body, dict) else {}
    nik, _raw = normalize_nik(body.get('nik'))
    dob = str(body.get('dob') or '').strip()
    token = str(body.get('token') or '').strip()
    if len(nik) != 16 or not _valid_date(dob) or not token:
        return None, ('error', 400, _MSG_INCOMPLETE)
    return {'nik': nik, 'dob': dob, 'token': token}, None


def _as_datetime(value):
    """Tanggal DB (datetime/teks ISO) jadi datetime naive; None bila rusak."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    return None


def _as_iso(value):
    """Waktu kedaluwarsa attempt untuk UI (ISO, tanpa NIK atau kunci)."""
    parsed = _as_datetime(value)
    return parsed.isoformat() if parsed else (str(value) if value is not None else None)


def _attempt_payload(attempt, items):
    """Payload attempt untuk pelamar: soal tanpa kunci + jawaban tersimpan."""
    attempt = attempt or {}
    questions, answers = [], {}
    for item in items or []:
        item = item or {}
        snap = as_json(item.get('snapshot'), {}) or {}
        if not isinstance(snap, dict):
            snap = {}
        position = item.get('position')
        # Hanya field tampilan yang dikirim — answer/points/is_correct/snapshot
        # dan metadata lain tidak pernah masuk payload publik.
        questions.append({
            'position': position,
            'type': snap.get('type'),
            'category': snap.get('category'),
            'prompt': snap.get('prompt'),
            'options': snap.get('options') or [],
        })
        saved = as_json(item.get('answer'))
        if saved is not None:
            answers[str(position)] = saved
    expiry = _as_datetime(attempt.get('expires_at'))
    remaining = max(0, int((expiry - datetime.now()).total_seconds())) if expiry else 0
    snapshot = as_json(attempt.get('settings_snapshot'), {})
    duration = snapshot.get('duration_minutes', 25) if isinstance(snapshot, dict) else 25
    return {
        'attempt_id': attempt.get('id'),
        'attempt_no': attempt.get('attempt_no'),
        'modal_tier': attempt.get('modal_tier'),
        'expires_at': _as_iso(attempt.get('expires_at')),
        'remaining_seconds': remaining,
        'duration_minutes': duration,
        'questions': questions,
        'answers': answers,
    }


def _session_valid():
    """Sesi TKD hanya berlaku dua jam sejak verifikasi terakhir."""
    try:
        verified_at = int(session.get('tkd_verified_at') or 0)
    except (TypeError, ValueError):
        return False
    return (bool(session.get('tkd_case_id'))
            and 0 < time.time() - verified_at <= _SESSION_SECONDS)


def _verified_context(cursor, verified):
    """Cocokkan token + identitas, lalu siapkan sesi terbatas dua jam."""
    if not _session_valid():
        # Sesi basi dibersihkan dulu agar tidak terbawa ke attempt berikutnya.
        for key in ('tkd_case_id', 'tkd_verified_at', 'tkd_branch'):
            session.pop(key, None)
    branch = svc.resolve_branch_token(cursor, verified['token'])
    if not branch:
        return None, ('error', 400, _MSG_BAD_LINK)
    case = svc.verify_identity(cursor, verified['nik'], verified['dob'])
    if not case:
        return None, ('error', 403, _MSG_IDENTITY)
    session['tkd_case_id'] = str(case.get('case_id') or '')
    session['tkd_verified_at'] = int(time.time())
    session['tkd_branch'] = branch
    return {'case': case, 'branch': branch}, None


def _state_for(cursor, case, settings):
    """Finalisasi lazy + ringkasan state publik untuk satu kasus."""
    case_id = case.get('case_id')
    svc.finalize_expired(cursor, case_id)
    attempts = svc.fetch_attempts(cursor, case_id) or []
    steps = svc.fetch_tkd_steps(cursor, case_id) or []
    return public_state(case, attempts, steps, settings), attempts


def _audit_start(attempt_id, case_id, branch):
    """Jejak audit mulai ujian; NIK tidak pernah ikut tercatat."""
    try:
        log_activity_async(
            None, 'tkd_attempt_start',
            session.get('user_role') or 'pelamar',
            session.get('user_name') or str(case_id or ''),
            new_data={'attempt_id': attempt_id, 'case_id': case_id,
                      'branch_code': branch},
            branch_code=branch)
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan attempt yang sudah dibuat.


def _close_cursor(cursor):
    """Tutup cursor bila tersedia; cursor tiruan tidak selalu punya `close`."""
    close = getattr(cursor, 'close', None)
    if callable(close):
        close()


def _require_session(attempt):
    """Sesi verifikasi dua jam + kepemilikan attempt.

    Kembalikan `(attempt, None)` atau `(None, respons error)`; attempt dari
    kasus lain tidak boleh dibaca pemilik sesi mana pun.
    """
    case_id = session.get('tkd_case_id')
    try:
        verified_at = int(session.get('tkd_verified_at') or 0)
    except (TypeError, ValueError):
        verified_at = 0
    if (not case_id or not 0 < time.time() - verified_at <= _SESSION_SECONDS):
        return None, _public({'status': 'error', 'msg': _MSG_SESSION}, 403)
    if not attempt or str(attempt.get('case_id')) != str(case_id):
        return None, _public({'status': 'error', 'msg': _MSG_NOT_FOUND}, 404)
    return attempt, None


def _valid_answer(snapshot, answer):
    """Validasi jawaban terhadap snapshot beku; None bila bentuknya tidak sah."""
    snap = as_json(snapshot, {})
    if not isinstance(snap, dict):
        return None
    qtype = str(snap.get('type') or '').upper()
    if qtype == 'MCQ':
        if not isinstance(answer, dict):
            return None
        option = answer.get('option')
        if isinstance(option, bool) or not isinstance(option, (str, int)):
            return None
        # Simpan id dari snapshot, bukan nilai mentah klien: penilaian
        # memakai perbandingan persis, jadi '1' vs 1 tidak boleh beda.
        matched = next((row.get('id') for row in (snap.get('options') or [])
                        if isinstance(row, dict) and row.get('id') is not None
                        and str(row.get('id')) == str(option)), None)
        return {'option': matched} if matched is not None else None
    if qtype == 'NUMERIC':
        # Klien mengirim angka/string mentah atau `{"value": ...}`; keduanya
        # dinormalisasi memakai aturan angka Indonesia dari `parse_numeric`.
        if (isinstance(answer, bool)
                or not isinstance(answer, (dict, int, float, str))):
            return None
        raw = answer.get('value') if isinstance(answer, dict) else answer
        number = parse_numeric(raw)
        return {'value': number} if number is not None else None
    if qtype in ('SHORT_TEXT', 'PROFILE', 'PROFILE_TEXT'):
        if not isinstance(answer, dict):
            return None
        text = answer.get('text')
        if not isinstance(text, str):
            return None
        limit = 500 if qtype == 'SHORT_TEXT' else 1000
        return {'text': text[:limit]}
    return None


def _save_answer(cursor, item, answer):
    """Tulis satu jawaban ke item attempt; True bila helper sudah commit.

    Transaksi tetap milik route: bila cursor tidak mengekspos koneksinya,
    pemanggil yang melakukan commit.
    """
    item = item or {}
    cursor.execute(
        'UPDATE tkd_attempt_items SET answer=%s, answered_at=NOW() '
        'WHERE attempt_id=%s AND position=%s',
        (json.dumps(answer, ensure_ascii=False),
         item.get('attempt_id'), item.get('position')))
    connection = getattr(cursor, 'connection', None)
    if connection is not None and callable(getattr(connection, 'commit', None)):
        connection.commit()
        return True
    return False


def _audit_submit(attempt, case_id):
    """Jejak submit: attempt/status/skor saja, tanpa NIK, nama, atau kunci."""
    attempt = attempt or {}
    try:
        log_activity_async(
            None, 'tkd_attempt_submit',
            session.get('user_role') or 'pelamar',
            str(case_id or ''),
            new_data={'attempt_id': attempt.get('id'), 'case_id': case_id,
                      'status': attempt.get('status'),
                      'score': parse_numeric(attempt.get('score'))},
            branch_code=session.get('tkd_branch') or attempt.get('branch_code'))
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan submit yang sudah tersimpan.


def _question_payload(row):
    """Baris bank soal untuk staff: kunci dan poin memang sengaja dikirim."""
    payload = dict(row or {})
    payload['options'] = as_json(payload.get('options'), []) or []
    payload['answer'] = as_json(payload.get('answer'))
    payload['updated_at'] = _as_iso(payload.get('updated_at'))
    return payload


def _insert_question(cursor, question, actor='', active=0):
    """Tulis satu soal; `active` jadi parameter terakhir untuk pemanggil draft.

    Menerima `options`/`answer` dari `normalize_question` maupun dari baris
    CSV, sehingga route tambah/impor dan seed memakai satu jalur INSERT.
    """
    question = question or {}
    options = as_json(question.get('options'), []) or []
    answer = as_json(question.get('answer'))
    user = str(actor or '')[:100]
    cursor.execute(
        'INSERT INTO tkd_questions '
        '(code, category, type, prompt, options, answer, points, modal_tier, '
        'sort_order, created_by, updated_by, active) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (question.get('code'), question.get('category'), question.get('type'),
         question.get('prompt'), json.dumps(options, ensure_ascii=False),
         json.dumps(answer, ensure_ascii=False), question.get('points'),
         question.get('modal_tier'), question.get('sort_order') or 0,
         user, user, active))


def _audit_question(action, question_id, code, **extra):
    """Jejak CRUD bank soal: id/kode saja, tanpa NIK atau data pelamar."""
    payload = {'question_id': question_id, 'code': code}
    payload.update(extra)
    try:
        log_activity_async(None, action, session.get('user_role') or '',
                           session.get('user_name') or '', new_data=payload,
                           branch_code=session.get('branch_code'))
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan perubahan yang tersimpan.


def _audit_import(counts):
    """Jejak impor CSV: hitungan saja, isi soal/NIK tidak ikut tercatat."""
    try:
        log_activity_async(None, 'tkd_questions_import',
                           session.get('user_role') or '',
                           session.get('user_name') or '', new_data=dict(counts),
                           branch_code=session.get('branch_code'))
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan impor yang tersimpan.


def _duplicate_code_errors(text, rows):
    """Cari kode ganda dalam satu CSV impor (kolom `code` UNIQUE di DB).

    Duplikat ditolak sebagai error parse, bukan digabung diam-diam. Nomor
    baris fisik CSV dipakai agar petugas langsung tahu baris yang harus
    dibuang; baris yang sudah gugur saat validasi tidak ikut dihitung.
    """
    valid = {str((row or {}).get('code') or '') for row in (rows or [])}
    seen, errors = set(), []
    reader = csv.DictReader(io.StringIO((text or '').lstrip('\ufeff')))
    for raw in reader:
        code = str((raw or {}).get('code') or '').strip()
        if code not in valid:
            continue
        if code in seen:
            errors.append(f'baris {reader.line_num}: kode {code} duplikat')
        else:
            seen.add(code)
    return errors


def _scope_branch(conn):
    """None hanya untuk Admin Pusat; selain itu cabang sesi (fail-closed)."""
    try:
        if is_ho_admin(conn):
            return None
    except Exception:
        pass  # Kegagalan baca hak tidak boleh menaikkan ke akses lintas cabang.
    return str(session.get('branch_code') or '').strip().upper()[:10] or _NO_BRANCH


def finalize_expired_all(cursor, scope):
    """Finalisasi lazy maksimal 200 attempt kedaluwarsa dalam satu cakupan.

    Satu nilai `now` dipakai untuk SELECT maupun `svc.finalize_expired` agar
    clock skew DB/Python tidak membuat attempt terlewat. `svc.finalize_expired`
    bekerja per kasus; route yang memanggil helper ini bertugas commit agar
    UPDATE finalisasi tidak gulung.
    """
    now = datetime.now()
    sql = ('SELECT DISTINCT a.case_id FROM tkd_attempts a '
           "WHERE a.status='BERLANGSUNG' AND a.expires_at < %s")
    params = (now,)
    if scope is not None:
        sql += ' AND a.branch_code=%s'
        params = (now, scope)
    sql += f' ORDER BY a.case_id LIMIT {_MAX_ATTEMPT_ROWS}'
    cursor.execute(sql, params)
    case_ids = [(row or {}).get('case_id') for row in (cursor.fetchall() or [])]
    done = []
    for case_id in case_ids:
        if case_id:
            done.extend(svc.finalize_expired(cursor, case_id, now) or [])
    return done


def _fetch_attempt_rows(cursor, scope, params):
    """Baris hasil attempt staff; NIK mentah dipakai filter, bukan respons."""
    params = params or {}
    clauses, values = [], []
    branch = str(params.get('branch_code') or '').strip().upper()[:10]
    if scope is not None:
        # Cabang sesi mengikat filter: petugas tidak boleh meminta cabang lain.
        branch = scope
    if branch:
        clauses.append('a.branch_code=%s')
        values.append(branch)
    status = str(params.get('status') or '').strip().upper()[:30]
    if status:
        clauses.append('a.status=%s')
        values.append(status)
    date_from = str(params.get('from') or '').strip()
    if date_from:
        clauses.append('a.started_at >= %s')
        values.append(date_from + ' 00:00:00')
    date_to = str(params.get('to') or '').strip()
    if date_to:
        clauses.append('a.started_at <= %s')
        values.append(date_to + ' 23:59:59')
    search = str(params.get('q') or '').strip()[:100]
    nik, _raw = normalize_nik(search)
    if len(nik) == 16:
        clauses.append('c.nik=%s')
        values.append(nik)
    elif search:
        clauses.append('c.nama LIKE %s')
        values.append(f'%{search}%')
    sql = ('SELECT a.id, a.case_id, c.nama, c.nik, a.branch_code, '
           'a.attempt_no, a.status, a.score, a.passed, a.started_at, '
           'a.submitted_at, c.tkd_score_source AS score_source, '
           'c.tkd_score AS official_score '
           'FROM tkd_attempts a JOIN recruitment_cases c ON c.case_id=a.case_id')
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += f' ORDER BY a.started_at DESC, a.id DESC LIMIT {_MAX_ATTEMPT_ROWS}'
    cursor.execute(sql, tuple(values))
    return list(cursor.fetchall() or [])


def _attempt_row_payload(row):
    """Whitelist respons daftar hasil — NIK penuh tidak pernah diteruskan."""
    row = row or {}
    return {
        'id': row.get('id'),
        'case_id': row.get('case_id'),
        'nama': row.get('nama'),
        'nik_masked': _mask_nik(row.get('nik')),
        'branch_code': row.get('branch_code'),
        'attempt_no': row.get('attempt_no'),
        'status': row.get('status'),
        'score': parse_numeric(row.get('score')),
        'passed': row.get('passed'),
        'started_at': _as_iso(row.get('started_at')),
        'submitted_at': _as_iso(row.get('submitted_at')),
        'score_source': row.get('score_source'),
        'official_score': parse_numeric(row.get('official_score')),
    }


def _case_in_scope(cursor, case_id, scope):
    """Cabang kasus dari asal/riwayat/langkah harus cocok dengan scope staff."""
    if scope is None:
        return True
    case_id = str(case_id or '').strip()
    if not case_id:
        return False
    cursor.execute('SELECT first_branch FROM recruitment_cases WHERE case_id=%s',
                   (case_id,))
    row = cursor.fetchone() or {}
    if str(row.get('first_branch') or '').strip().upper()[:10] == scope:
        return True
    # Nama tabel konstan, bukan input pengguna — aman dari injeksi.
    for table in ('case_branch_history', 'recruitment_steps'):
        cursor.execute(
            f'SELECT 1 FROM {table} WHERE case_id=%s AND branch_code=%s '
            'LIMIT 1', (case_id, scope))
        if cursor.fetchone():
            return True
    return False


def _review_item_payload(item):
    """Satu butir review: kunci snapshot sengaja dikirim ke staff."""
    item = item or {}
    snap = as_json(item.get('snapshot'), {}) or {}
    if not isinstance(snap, dict):
        snap = {}
    snapshot = {key: snap.get(key) for key in _REVIEW_SNAPSHOT_KEYS}
    snapshot['options'] = snapshot.get('options') or []
    return {
        'position': item.get('position'),
        'snapshot': snapshot,
        'answer': as_json(item.get('answer')),
        'is_correct': item.get('is_correct'),
        'points_awarded': item.get('points_awarded'),
    }


def _fetch_review(cursor, attempt_id, scope):
    """Attempt + kasus + butir untuk review staff; None bila tidak ada."""
    attempt = svc.fetch_attempt(cursor, attempt_id)
    if not attempt:
        return None
    branch = str(attempt.get('branch_code') or '').strip().upper()[:10]
    # Otorisasi review hanya memakai cabang attempt: kasus bisa sah diuji di
    # cabang lain sebelum langkah/riwayat cabang ditulis saat finalisasi.
    if scope is not None and branch != scope:
        raise PermissionError('Attempt di luar cabang staff.')
    case_id = attempt.get('case_id')
    cursor.execute(
        'SELECT case_id, nama, nik, first_branch, tkd_score, '
        'tkd_score_source, tkd_passed FROM recruitment_cases '
        'WHERE case_id=%s LIMIT 1', (case_id,))
    case = cursor.fetchone() or {}
    items = svc.fetch_attempt_items(cursor, attempt_id) or []
    profile = None
    for item in reversed(items):
        snap = as_json((item or {}).get('snapshot'), {}) or {}
        if (isinstance(snap, dict)
                and str(snap.get('type') or '').upper() == 'PROFILE_TEXT'):
            profile = item
            break
    return {
        'attempt': attempt,
        'case': case,
        'items': items,
        'profile_text_answer': (as_json(profile.get('answer'))
                                if profile else None),
        'modal_tier': attempt.get('modal_tier'),
        'settings_snapshot': as_json(attempt.get('settings_snapshot'), {}),
        'score': parse_numeric(attempt.get('score')),
        'passed': attempt.get('passed'),
    }


def _review_attempt_payload(attempt):
    """Whitelist field attempt yang boleh tampil di layar review staff."""
    attempt = attempt or {}
    data = {key: attempt.get(key) for key in _REVIEW_ATTEMPT_KEYS}
    for key in ('started_at', 'expires_at', 'submitted_at'):
        data[key] = _as_iso(data.get(key))
    data['pass_score_snapshot'] = parse_numeric(
        attempt.get('pass_score_snapshot'))
    snapshot = as_json(attempt.get('settings_snapshot'), {})
    data['settings_snapshot'] = snapshot if isinstance(snapshot, dict) else {}
    return data


def _review_payload(review):
    """Bersihkan NIK kasus, whitelist attempt, dan bentuk butir review."""
    review = dict(review or {})
    case = dict(review.get('case') or {})
    if 'nik' in case:
        case['nik_masked'] = _mask_nik(case.pop('nik'))
    review['case'] = case
    review['attempt'] = _review_attempt_payload(review.get('attempt'))
    review['items'] = [_review_item_payload(item)
                       for item in (review.get('items') or [])]
    snapshot = as_json(review.get('settings_snapshot'), {})
    review['settings_snapshot'] = snapshot if isinstance(snapshot, dict) else {}
    for key in ('profile_text_answer', 'modal_tier', 'score', 'passed'):
        review.setdefault(key, None)
    return review


def _settings_payload(settings, ready=None):
    """Delapan field pengaturan + ringkasan kesiapan bank soal."""
    settings = settings or {}
    data = {key: settings.get(key) for key in _SETTINGS_KEYS}
    data['readiness'] = ready if ready is not None else {}
    return data


def _audit_score_edit(case_id, result, reason, actor, branch_code):
    """Jejak koreksi skor: angka/alasan/aktor, tanpa NIK atau nama pelamar."""
    result = result or {}
    try:
        log_activity_async(
            None, 'recruitment_tkd_score_edit',
            session.get('user_role') or '', actor or '',
            new_data={'case_id': case_id,
                      'old_score': parse_numeric(result.get('old_score')),
                      'score': parse_numeric(result.get('score')),
                      'reason': reason, 'actor': actor},
            branch_code=branch_code)
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan koreksi yang tersimpan.


def _audit_settings_update(settings):
    """Jejak perubahan pengaturan: konfigurasi saja, tanpa data pelamar."""
    try:
        log_activity_async(None, 'tkd_settings_update',
                           session.get('user_role') or '',
                           session.get('user_name') or '',
                           new_data=_settings_payload(settings))
    except Exception:
        pass  # Audit gagal tidak boleh menggagalkan pengaturan yang tersimpan.


def register_tkd_routes(app):
    @app.route('/api/recruitment/tkd/status', methods=['POST'])
    def api_tkd_status():
        """Status publik: verifikasi identitas + ringkasan tanpa data sensitif."""
        verified, error = _verify_body(request.get_json(silent=True) or {})
        if error:
            return _public({'status': error[0], 'msg': error[2]}, error[1])
        if not _rate(client_ip() or '?', verified['nik'], 'status'):
            return _public({'status': 'error', 'msg': _MSG_RATE}, 429)

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                context, error = _verified_context(cursor, verified)
                if error:
                    return _public({'status': error[0], 'msg': error[2]}, error[1])
                case = context['case']
                settings = dict(svc.load_settings(cursor) or {})
                questions = svc.fetch_active_questions(cursor) or []
                ready = readiness(questions, settings) or {}
                settings['bank_ready'] = bool(ready.get('ready'))
                state, _attempts = _state_for(cursor, case, settings)
                # finalize_expired menulis UPDATE; koneksi tidak autocommit, jadi
                # commit di sini agar finalisasi tidak gulung saat close().
                conn.commit()
                state['bank_ready'] = bool(ready.get('ready'))
                return _public({'status': 'success', 'data': state})
            finally:
                cursor.close()
        except Exception:
            # Jangan kembalikan str(e): detail DB/PII tidak boleh bocor.
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/start', methods=['POST'])
    def api_tkd_start():
        """Mulai (atau lanjutkan) ujian setelah verifikasi dan penguncian kasus."""
        body = request.get_json(silent=True) or {}
        verified, error = _verify_body(body)
        if error:
            return _public({'status': error[0], 'msg': error[2]}, error[1])
        modal_tier = str(body.get('modal_tier') or '').strip()
        if modal_tier not in MODAL_TIERS:
            return _public({'status': 'error', 'msg': _MSG_INCOMPLETE}, 400)
        if not _rate(client_ip() or '?', verified['nik'], 'start'):
            return _public({'status': 'error', 'msg': _MSG_RATE}, 429)

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                context, error = _verified_context(cursor, verified)
                if error:
                    return _public({'status': error[0], 'msg': error[2]}, error[1])
                # Kunci baris kasus sebelum memeriksa kesempatan/membuat attempt.
                case = svc.fetch_case_by_nik(
                    cursor, verified['nik'], for_update=True)
                if not case:
                    return _public({'status': 'error', 'msg': _MSG_IDENTITY}, 403)

                settings = dict(svc.load_settings(cursor) or {})
                questions = svc.fetch_active_questions(cursor) or []
                ready = readiness(questions, settings) or {}
                if not settings.get('active') or not ready.get('ready'):
                    return _public({'status': 'error', 'msg': _MSG_CLOSED}, 409)
                settings['bank_ready'] = bool(ready.get('ready'))

                state, attempts = _state_for(cursor, case, settings)
                if state['state'] == 'BERLANGSUNG':
                    # Jalur resume tidak membuat attempt, jadi commit finalisasi
                    # di sini (sebelum return, termasuk return 409 di bawah).
                    conn.commit()
                    active_id = (state.get('active_attempt') or {}).get('id')
                    active = next((row for row in attempts
                                   if str((row or {}).get('id')) == str(active_id)), None)
                    if active is None:
                        return _public({'status': 'error', 'msg': _MSG_CLOSED}, 409)
                    items = svc.fetch_attempt_items(cursor, active.get('id')) or []
                    return _public({'status': 'success',
                                    'data': _attempt_payload(active, items)})

                if not state.get('can_start'):
                    # Tidak ada attempt baru: commit UPDATE finalisasi sebelum
                    # return 409; jalur sukses tetap menyimpan commit-nya sendiri.
                    conn.commit()
                    msg = _START_BLOCK_MESSAGES.get(
                        state['state'], 'Hubungi Traineer cabang.')
                    return _public({'status': 'error', 'msg': msg}, 409)

                created = svc.create_attempt(
                    cursor, case, context['branch'], modal_tier, settings, questions)
                attempt = (created or {}).get('attempt') or {}
                items = (created or {}).get('items') or []
                conn.commit()
                try:
                    record_event(case.get('case_id') or '',
                                 verified.get('nik') or '', 'TKD_STARTED',
                                 branch_code=context['branch'],
                                 source_module='tkd',
                                 source_id=str(attempt.get('id') or ''),
                                 metadata={'attempt_no': attempt.get('attempt_no')})
                except Exception:
                    pass
                _audit_start(attempt.get('id'), case.get('case_id'),
                             context['branch'])
                return _public({'status': 'success',
                                'data': _attempt_payload(attempt, items)})
            finally:
                cursor.close()
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/attempts/<attempt_id>', methods=['GET'])
    def api_tkd_attempt(attempt_id):
        """Resume attempt milik sesi; kunci jawaban tidak pernah dikirim."""
        if not _session_valid():
            return _public({'status': 'error', 'msg': _MSG_SESSION}, 403)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                attempt, error = _require_session(
                    svc.fetch_attempt(cursor, attempt_id))
                if error:
                    return error
                expiry = _as_datetime(attempt.get('expires_at'))
                active = str(attempt.get('status') or '').upper() == 'BERLANGSUNG'
                expired = expiry is not None and expiry < datetime.now()
                if not active or expired:
                    if active:
                        # Finalisasi lazy menulis UPDATE; commit sebelum hasil dibaca.
                        attempt = svc.finalize_attempt(
                            cursor, attempt, 'KEDALUWARSA') or attempt
                        conn.commit()
                    settings = dict(svc.load_settings(cursor) or {})
                    return _public({'status': 'success',
                                    'data': {'finished': True,
                                             'result': svc.attempt_result(
                                                 cursor, attempt, settings)}})
                items = svc.fetch_attempt_items(cursor, attempt_id) or []
                return _public({'status': 'success',
                                'data': _attempt_payload(attempt, items)})
            finally:
                _close_cursor(cursor)
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/attempts/<attempt_id>/answers/<int:position>',
               methods=['PUT'])
    def api_tkd_answer(attempt_id, position):
        """Autosave satu jawaban attempt yang masih berlangsung."""
        if not _session_valid():
            return _public({'status': 'error', 'msg': _MSG_SESSION}, 403)
        if not redis_rate_hit(f'tkd-answer|{attempt_id}', 60, 60,
                              prefix=_RATE_PREFIX):
            return _public({'status': 'error', 'msg': _MSG_RATE}, 429)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                attempt, error = _require_session(
                    svc.fetch_attempt(cursor, attempt_id))
                if error:
                    return error
                items = svc.fetch_attempt_items(cursor, attempt_id) or []
                item = next((row for row in items
                             if row and str(row.get('position')) == str(position)), None)
                if item is None:
                    return _public({'status': 'error', 'msg': _MSG_NOT_FOUND}, 404)

                expiry = _as_datetime(attempt.get('expires_at'))
                active = str(attempt.get('status') or '').upper() == 'BERLANGSUNG'
                expired = expiry is not None and expiry < datetime.now()
                if not active or expired:
                    if active:
                        attempt = svc.finalize_attempt(
                            cursor, attempt, 'KEDALUWARSA') or attempt
                        conn.commit()
                    settings = dict(svc.load_settings(cursor) or {})
                    return _public({
                        'status': 'error',
                        'msg': _MSG_EXPIRED if expired else _MSG_FINISHED,
                        'data': svc.attempt_result(cursor, attempt, settings),
                    }, 409)

                body = request.get_json(silent=True) or {}
                answer = _valid_answer(item.get('snapshot'), body.get('answer'))
                if answer is None:
                    return _public({'status': 'error',
                                    'msg': _MSG_INCOMPLETE}, 400)
                item = dict(item)
                item.setdefault('attempt_id', attempt_id)
                if not _save_answer(cursor, item, answer):
                    conn.commit()
                return _public({'status': 'success',
                                'data': {'position': position, 'saved': True}})
            finally:
                _close_cursor(cursor)
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/attempts/<attempt_id>/submit',
               methods=['POST'])
    def api_tkd_submit(attempt_id):
        """Kumpulkan attempt sekali; submit ulang mengembalikan hasil yang sama."""
        if not _session_valid():
            return _public({'status': 'error', 'msg': _MSG_SESSION}, 403)
        if not redis_rate_hit(f'tkd-submit|{attempt_id}', 5, 60,
                              prefix=_RATE_PREFIX):
            return _public({'status': 'error', 'msg': _MSG_RATE}, 429)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                # Kunci baris attempt supaya submit ganda tidak menulis dua kali.
                attempt, error = _require_session(
                    svc.fetch_attempt(cursor, attempt_id, for_update=True))
                if error:
                    return error
                settings = dict(svc.load_settings(cursor) or {})
                active = str(attempt.get('status') or '').upper() == 'BERLANGSUNG'
                if not active:
                    return _public({'status': 'success',
                                    'data': svc.attempt_result(
                                        cursor, attempt, settings)})

                expiry = _as_datetime(attempt.get('expires_at'))
                deadline = expiry + timedelta(seconds=60) if expiry else None
                final_status = ('KEDALUWARSA'
                                if deadline is not None and datetime.now() > deadline
                                else 'SELESAI')
                attempt = svc.finalize_attempt(
                    cursor, attempt, final_status) or attempt
                conn.commit()
                try:
                    common = dict(
                        case_id=attempt.get('case_id') or '',
                        nik='',
                        branch_code=str(attempt.get('branch_code') or ''),
                        source_module='tkd',
                        source_id=str(attempt.get('id') or ''),
                        metadata={'attempt_no': attempt.get('attempt_no'),
                                  'score': attempt.get('score')})
                    record_event(**common, event_type='TKD_SUBMITTED')
                    record_event(**common, event_type='TKD_SCORED')
                except Exception:
                    pass
                _audit_submit(attempt, attempt.get('case_id'))
                return _public({'status': 'success',
                                'data': svc.attempt_result(
                                    cursor, attempt, settings)})
            finally:
                _close_cursor(cursor)
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/attempts/<attempt_id>/result',
               methods=['GET'])
    def api_tkd_result(attempt_id):
        """Hasil publik attempt: status dan angka saja."""
        if not _session_valid():
            return _public({'status': 'error', 'msg': _MSG_SESSION}, 403)
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _public({'status': 'error', 'msg': _MSG_DB}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                attempt, error = _require_session(
                    svc.fetch_attempt(cursor, attempt_id))
                if error:
                    return error
                expiry = _as_datetime(attempt.get('expires_at'))
                active = str(attempt.get('status') or '').upper() == 'BERLANGSUNG'
                if active and expiry is not None and expiry < datetime.now():
                    attempt = svc.finalize_attempt(
                        cursor, attempt, 'KEDALUWARSA') or attempt
                    conn.commit()
                    active = False
                if active:
                    return _public({'status': 'error', 'msg': _MSG_UNFINISHED}, 409)
                settings = dict(svc.load_settings(cursor) or {})
                return _public({'status': 'success',
                                'data': svc.attempt_result(
                                    cursor, attempt, settings)})
            finally:
                _close_cursor(cursor)
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return _public({'status': 'error', 'msg': _MSG_DB}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/questions', methods=['GET'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_questions():
        """Daftar soal staff beserta kunci; filter kategori/status/pencarian."""
        category = str(request.args.get('category') or '').strip().upper()
        active = str(request.args.get('active') or '').strip().lower()
        search = str(request.args.get('q') or '').strip()
        clauses, params = [], []
        if category:
            clauses.append('category=%s')
            params.append(category)
        if active in ('0', '1'):
            clauses.append('active=%s')
            params.append(int(active))
        if search:
            clauses.append('(prompt LIKE %s OR code LIKE %s)')
            like = f'%{search}%'
            params.extend((like, like))
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        sql = ('SELECT id, code, category, type, prompt, options, answer, '
               'points, modal_tier, active, sort_order, created_by, updated_by, '
               'updated_at FROM tkd_questions' + where +
               ' ORDER BY category, sort_order, id')

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, tuple(params))
                rows = [_question_payload(row)
                        for row in (cursor.fetchall() or [])]
            finally:
                _close_cursor(cursor)
            return jsonify({'status': 'success', 'data': rows})
        except Exception:
            # Detail DB tidak dikirim ke klien.
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/questions', methods=['POST'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_question_create():
        """Tambah soal baru; tanpa `active` soal masuk sebagai draft (0)."""
        body = request.get_json(silent=True) or {}
        errors = validate_question(body)
        if errors:
            return jsonify({'status': 'error', 'msg': '; '.join(errors)}), 400
        question = normalize_question(body)
        actor = session.get('user_name') or ''

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                _insert_question(cursor, question, actor=actor,
                                 active=question['active'])
                question_id = cursor.lastrowid
                conn.commit()
            finally:
                _close_cursor(cursor)
            _audit_question('tkd_question_create', question_id, question['code'])
            return jsonify({'status': 'success',
                            'data': {'id': question_id}}), 201
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/questions/<int:question_id>', methods=['PUT'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_question_update(question_id):
        """Ubah soal; kunci lama tidak menimpa snapshot attempt yang sudah ada."""
        body = request.get_json(silent=True) or {}
        errors = validate_question(body)
        if errors:
            return jsonify({'status': 'error', 'msg': '; '.join(errors)}), 400
        question = normalize_question(body)
        actor = session.get('user_name') or ''

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT id FROM tkd_questions WHERE id=%s', (question_id,))
                if not cursor.fetchone():
                    return jsonify({'status': 'error',
                                    'msg': 'Soal tidak ditemukan'}), 404
                cursor.execute(
                    'UPDATE tkd_questions SET code=%s, category=%s, type=%s, '
                    'prompt=%s, options=%s, answer=%s, points=%s, '
                    'modal_tier=%s, active=%s, sort_order=%s, updated_by=%s, '
                    'updated_at=NOW() WHERE id=%s',
                    (question['code'], question['category'], question['type'],
                     question['prompt'], question['options'], question['answer'],
                     question['points'], question['modal_tier'],
                     question['active'], question['sort_order'], actor,
                     question_id))
                conn.commit()
            finally:
                _close_cursor(cursor)
            _audit_question('tkd_question_update', question_id, question['code'])
            return jsonify({'status': 'success',
                            'data': {'id': question_id,
                                     'code': question['code']}})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/questions/<int:question_id>/toggle',
               methods=['POST'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_question_toggle(question_id):
        """Aktifkan/nonaktifkan soal (penghapusan fisik tidak dipakai)."""
        actor = session.get('user_name') or ''
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT code, active FROM tkd_questions WHERE id=%s',
                    (question_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error',
                                    'msg': 'Soal tidak ditemukan'}), 404
                new_active = 0 if row.get('active') in (1, True, '1') else 1
                cursor.execute(
                    'UPDATE tkd_questions SET active=1-active, updated_by=%s, '
                    'updated_at=NOW() WHERE id=%s', (actor, question_id))
                conn.commit()
            finally:
                _close_cursor(cursor)
            _audit_question('tkd_question_toggle', question_id, row.get('code'),
                            active=new_active)
            return jsonify({'status': 'success',
                            'data': {'id': question_id, 'active': new_active}})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/questions/import', methods=['POST'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_questions_import():
        """Impor CSV sebagai draft; kode aktif tidak pernah ditimpa."""
        body = request.get_json(silent=True) or {}
        text = body.get('csv') if isinstance(body, dict) else None
        if (not isinstance(text, str) or not text.strip()
                or len(text) > _MAX_IMPORT_CHARS):
            return jsonify({'status': 'error',
                            'msg': 'CSV wajib berupa teks maksimal 300.000 karakter'}), 400
        rows, errors = csv_to_question_rows(text)
        errors.extend(_duplicate_code_errors(text, rows))
        if errors:
            # Batasi pesan: error validasi bisa sangat banyak pada CSV besar.
            return jsonify({'status': 'error',
                            'msg': '; '.join(errors[:10])}), 400
        by_code = {row.get('code'): row for row in rows}
        actor = session.get('user_name') or ''

        counts = None
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT code, active FROM tkd_questions')
                existing = {
                    str((row or {}).get('code')): {'active': (row or {}).get('active')}
                    for row in (cursor.fetchall() or [])
                }
                plan = import_rows(existing, rows, bool(body.get('update_drafts')))
                inserted = 0
                for code in plan['insert']:
                    _insert_question(cursor, by_code.get(code), actor=actor, active=0)
                    inserted += 1
                updated = 0
                for code in plan['update']:
                    row = by_code.get(code) or {}
                    # Guard active=0 pada WHERE: draft aktif tidak boleh tertimpa.
                    cursor.execute(
                        'UPDATE tkd_questions SET category=%s, type=%s, prompt=%s, '
                        'options=%s, answer=%s, points=%s, modal_tier=%s, '
                        'sort_order=%s, updated_by=%s, updated_at=NOW() '
                        'WHERE code=%s AND active=0',
                        (row.get('category'), row.get('type'), row.get('prompt'),
                         json.dumps(row.get('options') or [], ensure_ascii=False),
                         json.dumps(row.get('answer'), ensure_ascii=False),
                         row.get('points'), row.get('modal_tier'),
                         row.get('sort_order') or 0, actor, code))
                    # DB-API memberi jumlah baris yang benar-benar tertulis;
                    # cursor tiruan tanpa rowcount memakai hitungan rencana.
                    affected = getattr(cursor, 'rowcount', None)
                    if not isinstance(affected, int) or affected < 0:
                        affected = 1
                    updated += affected
                # Draft yang berubah aktif sebelum UPDATE ikut dihitung skipped.
                skipped = max(0, len(plan['skip']) + len(plan['update']) - updated)
                counts = {'inserted': inserted, 'updated': updated,
                          'skipped': skipped}
                conn.commit()
            finally:
                _close_cursor(cursor)
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()
        _audit_import(counts)
        return jsonify({'inserted': counts['inserted'], 'updated': counts['updated'],
                        'skipped': counts['skipped'], 'errors': []})

    @app.route('/api/recruitment/tkd/questions/export.csv', methods=['GET'])
    @role_required(['traineer', 'ga_hr', 'admin'])
    def api_tkd_questions_export():
        """Ekspor seluruh bank soal (termasuk draft) untuk tinjauan staff."""
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT code, category, type, prompt, options, answer, points, '
                    'modal_tier, active, sort_order FROM tkd_questions '
                    'ORDER BY category, sort_order, id')
                rows = cursor.fetchall() or []
            finally:
                _close_cursor(cursor)
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(CSV_COLUMNS)
            for row in rows:
                writer.writerow(question_row_to_csv(row))
            return Response(
                buffer.getvalue(), mimetype='text/csv',
                headers={'Content-Disposition':
                         'attachment; filename=tkd_bank.csv'})
        except Exception:
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/attempts', methods=['GET'])
    @role_required(_STAFF_ROLES)
    def api_tkd_staff_attempts():
        """Daftar hasil attempt staff: NIK termasker, tanpa kunci jawaban."""
        branch = str(request.args.get('branch_code') or '').strip().upper()[:10]
        status = str(request.args.get('status') or '').strip().upper()[:30]
        date_from = str(request.args.get('from') or '').strip()
        date_to = str(request.args.get('to') or '').strip()
        search = str(request.args.get('q') or '').strip()[:100]
        if ((date_from and not _valid_date(date_from))
                or (date_to and not _valid_date(date_to))):
            return jsonify({'status': 'error',
                            'msg': 'Format tanggal harus YYYY-MM-DD.'}), 400

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                scope = _scope_branch(conn)
                if scope is not None and branch and branch != scope:
                    return jsonify({'status': 'error',
                                    'msg': 'Cabang di luar hak akses Anda.'}), 403
                finalize_expired_all(cursor, scope)
                # Finalisasi menulis UPDATE; commit sebelum daftar dibaca.
                conn.commit()
                params = {'branch_code': branch or (scope or ''),
                          'status': status, 'from': date_from, 'to': date_to,
                          'q': search}
                rows = _fetch_attempt_rows(cursor, scope, params) or []
                data = [_attempt_row_payload(row) for row in rows]
            finally:
                _close_cursor(cursor)
            return jsonify({'status': 'success', 'data': data})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/review/<attempt_id>', methods=['GET'])
    @role_required(_STAFF_ROLES)
    def api_tkd_staff_review(attempt_id):
        """Review attempt: kunci butir sengaja tampil, NIK kasus termasker."""
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                scope = _scope_branch(conn)
                try:
                    review = _fetch_review(cursor, attempt_id, scope)
                except PermissionError:
                    return jsonify({'status': 'error',
                                    'msg': 'Attempt di luar cabang Anda.'}), 403
                if not review:
                    return jsonify({'status': 'error',
                                    'msg': _MSG_NOT_FOUND}), 404
                data = _review_payload(review)
            finally:
                _close_cursor(cursor)
            return jsonify({'status': 'success', 'data': data})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/score', methods=['POST'])
    @role_required(_STAFF_ROLES)
    def api_tkd_staff_score():
        """Koreksi skor manual; alasan wajib dan tercatat di audit."""
        body = request.get_json(silent=True) or {}
        case_id = str(body.get('case_id') or '').strip()[:40]
        score = parse_numeric(body.get('score'))
        reason = str(body.get('reason') or '').strip()
        if (not case_id or score is None or not 0 <= score <= 100
                or not reason or len(reason) > 500):
            return jsonify({
                'status': 'error',
                'msg': 'case_id dan skor 0–100 wajib diisi; '
                       'alasan wajib (maks. 500 karakter).'}), 400

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                scope = _scope_branch(conn)
                if not _case_in_scope(cursor, case_id, scope):
                    return jsonify({'status': 'error',
                                    'msg': 'Kasus di luar cabang Anda.'}), 403
                settings = dict(svc.load_settings(cursor) or {})
                actor = session.get('user_name') or ''
                result = svc.set_manual_score(
                    cursor, case_id, score, reason, actor,
                    settings.get('pass_score'), branch_code=scope or '')
                conn.commit()
            finally:
                _close_cursor(cursor)
            _audit_score_edit(case_id, result, reason, actor, scope)
            return jsonify({'status': 'success', 'data': result})
        except ValueError as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            # Pesan layanan sudah berupa teks validasi aman (tanpa data PII).
            return jsonify({'status': 'error', 'msg': str(exc)}), 400
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/settings', methods=['GET'])
    @role_required(_STAFF_ROLES)
    def api_tkd_settings_get():
        """Pengaturan ujian + kesiapan bank untuk layar staff."""
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                settings = dict(svc.load_settings(cursor) or {})
                questions = svc.fetch_active_questions(cursor) or []
                ready = readiness(questions, settings) or {}
                data = _settings_payload(settings, ready)
            finally:
                _close_cursor(cursor)
            return jsonify({'status': 'success', 'data': data})
        except Exception:
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/tkd/settings', methods=['PUT'])
    @role_required(_STAFF_ROLES)
    def api_tkd_settings_put():
        """Ubah pengaturan — hanya Admin; aktif butuh bank soal siap."""
        # Satu path untuk GET/PUT dengan guard berbeda: cek admin di handler.
        if session.get('user_role') != 'admin':
            return jsonify({'status': 'error',
                            'msg': 'Pengaturan hanya dapat diubah Admin.'}), 403
        settings, errors = validate_settings(request.get_json(silent=True) or {})
        if errors:
            return jsonify({'status': 'error', 'msg': '; '.join(errors)}), 400
        actor = session.get('user_name') or ''

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                ready = readiness(svc.fetch_active_questions(cursor),
                                  settings) or {}
                if settings['active'] and not ready.get('ready'):
                    return jsonify({
                        'status': 'error',
                        'msg': 'Bank soal belum siap.',
                        'reasons': ready.get('reasons') or []}), 409
                cursor.execute(
                    'UPDATE tkd_settings SET question_count=%s, '
                    'duration_minutes=%s, pass_score=%s, max_attempts=%s, '
                    'quota=%s, shuffle_options=%s, active=%s, updated_by=%s '
                    'WHERE id=1',
                    (settings['question_count'], settings['duration_minutes'],
                     settings['pass_score'], settings['max_attempts'],
                     json.dumps(settings['quota'], ensure_ascii=False),
                     int(bool(settings['shuffle_options'])),
                     int(bool(settings['active'])), actor))
                conn.commit()
            finally:
                _close_cursor(cursor)
            _audit_settings_update(settings)
            return jsonify({'status': 'success',
                            'data': _settings_payload(settings, ready)})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': _MSG_DB}), 500
        finally:
            if conn:
                conn.close()
