"""First Work (Absensi FirstWork) — API publik + pengelolaan role.

Alur:
- Form publik `/app/first-work-form` (tanpa login) mengirim NIK, nama, pendidikan,
  referensi, HP, dan file KTP ke `POST /api/first-work/public`.
- Traineer memverifikasi/menolak. Finance hanya melihat & mengekspor.
- Admin dapat mengoreksi data, mengelola referrer, sync sheet, dan menarik
  file KTP lama lewat Apps Script.
- Data historis dari Sheet masuk lewat `POST /api/first-work/sync` dengan
  `source_uid` stabil; status/verifikasi/KTP lokal tidak ditimpa sync.

Role lihat: `traineer`, `finance`, `ga_hr`, `admin` (termasuk `admin_master`).
"""
import base64
import csv
import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, date

import requests
from flask import (request, jsonify, session, send_file, make_response)

# First Work = fitur terpusat (SBY) di DB master. Koneksi default mengikuti
# cabang sesi; admin cabang lain tidak punya tabel ini, jadi pakai master dan
# batasi baris lewat _scope_branch().
from modules.config import get_master_connection
from modules.helpers import (role_required, log_activity_async, client_ip,
                             generate_display_id, save_file)
from modules.routes_overtime import _check_public_url

# ================================================================
# KONSTANTA
# ================================================================
STATUS_LABELS = {
    'submitted': '🕒 Menunggu Verifikasi',
    'verified': '✅ Terverifikasi',
    'rejected': '✕ Ditolak',
}
VALID_STATUSES = tuple(STATUS_LABELS)
VIEW_ROLES = ['traineer', 'finance', 'ga_hr', 'admin']
EDIT_ROLES = ['traineer', 'admin']
ADMIN_ROLES = ['admin']

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'uploads', 'first_work')
MAX_KTP_BYTES = 5 * 1024 * 1024

CONFIG_SHEET_URL = 'first_work_sheet_url'
CONFIG_KTP_TOKEN = 'first_work_ktp_token'
CONFIG_LAST_SYNC = 'first_work_last_sync'

# Rate limit publik: 10 submit / 10 menit per IP.
_SUBMIT_MAX = 10
_SUBMIT_WINDOW = 600
_submit_log = {}

# Header sheet -> kunci internal. Header dinormalisasi: lowercase, alnum saja.
HEADER_MAP = {
    '': 'timestamp',
    'timestamp': 'timestamp',
    '28161': 'sheet_seq1',
    '6495': 'sheet_seq2',
    'emailaddress': 'email',
    'nikktp': 'nik_raw',
    'nik': 'nik_raw',
    'namalengkap': 'nama',
    'nama': 'nama',
    'pendidikan': 'pendidikan_raw',
    'pendidikanterakhir': 'pendidikan_raw',
    'referensi': 'referensi_raw',
    'nohandphone': 'no_hp',
    'nohp': 'no_hp',
    'uploadktp': 'ktp_drive_url',
    'photoid': 'photoid_url',
    'mergeddocid1stsby': 'merged_doc_id',
    'mergeddocurl1stsby': 'merged_doc_url',
    'linktomergeddoc1stsby': 'merged_doc_link',
    'documentmergestatus1stsby': 'merge_status',
}

HONORIFIC_RE = re.compile(
    r'^(kak|kaka|bu|ibu|pak|bapak|mas|mbak|mba|sdr|sdri|saudara|saudari)\s+',
    re.IGNORECASE)


# ================================================================
# UTIL
# ================================================================
def _clean(value, maxlen=None):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:maxlen] if maxlen else text


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def normalize_nik(value):
    """Return (nik_valid_16, raw). Notasi ilmiah / panjang salah = invalid."""
    raw = _clean(value, 32)
    if not raw:
        return '', ''
    if re.search(r'[eE]\+|,', raw):
        return '', raw
    digits = _digits(raw)
    if len(digits) == 16:
        return digits, raw
    return '', raw


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


def normalize_pendidikan(value):
    raw = _clean(value, 100)
    up = re.sub(r'[^A-Z0-9 ]', ' ', raw.upper())
    up = re.sub(r'\s+', ' ', up).strip()
    tokens = set(up.replace('/', ' ').split())
    for level in ('S3', 'S2', 'S1', 'D4', 'D3', 'SMK', 'SMA', 'MA'):
        if level in tokens:
            return level
    for level in ('S3', 'S2', 'S1', 'D4', 'D3', 'SMK', 'SMA', 'MA'):
        if level in up.split():
            return level
    return up[:30]


def normalize_name(value):
    """Nama referrer untuk pencocokan: buang gelar sapaan & tanda baca."""
    text = _clean(value, 150).lower()
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = HONORIFIC_RE.sub('', text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_datetime(value):
    text = _clean(value, 40)
    if not text:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M:%S',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M',
                '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _serialize(row):
    if not row:
        return row
    out = dict(row)
    for key, value in out.items():
        if isinstance(value, datetime):
            out[key] = value.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(value, date):
            out[key] = value.isoformat()
    if out.get('status'):
        out['status_label'] = STATUS_LABELS.get(out['status'], out['status'])
    return out


_check_log = {}
_CHECK_WINDOW = 60
_CHECK_MAX = 20


def _check_ok(ip):
    """Rate limit ringan khusus cek NIK (tidak memakai kuota submit)."""
    now = time.time()
    stamps = [t for t in _check_log.get(ip, []) if now - t < _CHECK_WINDOW]
    if len(stamps) >= _CHECK_MAX:
        _check_log[ip] = stamps
        return False
    stamps.append(now)
    _check_log[ip] = stamps
    return True


def _rate_ok(ip):
    now = time.time()
    stamps = [t for t in _submit_log.get(ip, []) if now - t < _SUBMIT_WINDOW]
    if len(stamps) >= _SUBMIT_MAX:
        _submit_log[ip] = stamps
        return False
    stamps.append(now)
    _submit_log[ip] = stamps
    return True


def _config_get(conn, key):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (key,))
        row = cursor.fetchone()
        return (row or {}).get('config_value') or ''
    finally:
        cursor.close()


def _config_set(conn, key, value):
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
            (key, value))
    finally:
        cursor.close()


def _next_reg_no(conn, submitted_at):
    """Nomor registrasi FW-YYYYMMDD-#### (atomik via doc_sequences)."""
    date_part = (submitted_at or datetime.now()).strftime('%Y%m%d')
    key = f'FW|{date_part}'
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO doc_sequences (seq_key, seq) VALUES (%s, LAST_INSERT_ID(1)) "
            "ON DUPLICATE KEY UPDATE seq = LAST_INSERT_ID(seq + 1)", (key,))
        cursor.execute("SELECT LAST_INSERT_ID()")
        seq = int(cursor.fetchone()[0])
        return f'FW-{date_part}-{seq:04d}'
    finally:
        cursor.close()


# Sentinel: user tanpa branch_code tidak boleh otomatis melihat data cabang lain.
_NO_BRANCH = '__NOBRANCH__'


def _scope_branch(conn=None):
    """None = semua cabang (admin pusat/admin_master), selain itu kode cabang."""
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
    """Daftar cabang aktif untuk whitelist link form publik."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT code, name, city FROM branches WHERE is_active=1 ORDER BY code')
        return cursor.fetchall() or []
    finally:
        cursor.close()


def _request_branch(conn, value=None, branches=None):
    """Cabang tujuan form publik dari link (?cabang=MLG); default SBY.

    Nilai di luar master `branches` ditolak ke SBY supaya data tidak pernah
    masuk ke cabang yang tidak valid.
    """
    rows = branches if branches is not None else _branches(conn)
    codes = [str(row.get('code') or '').strip().upper() for row in rows]
    code = (value or request.args.get('cabang') or request.args.get('branch')
            or request.form.get('branch') or '').strip().upper()
    if code in codes:
        return code
    return 'SBY' if 'SBY' in codes else (codes[0] if codes else 'SBY')


# ================================================================
# REFERRER
# ================================================================
def _load_referrers(conn, active_only=True, branch=None):
    cursor = conn.cursor(dictionary=True)
    try:
        sql = ("SELECT id, name, aliases_json, user_id, branch_code, active "
               "FROM first_work_referrers")
        where = []
        params = []
        if active_only:
            where.append('active=1')
        if branch:
            # Referrer milik cabang itu saja; baris tanpa cabang dianggap milik SBY
            # (data historis) agar tidak bocor ke cabang lain.
            where.append('(branch_code=%s OR (branch_code IS NULL AND %s=\'SBY\'))')
            params += [branch, branch]
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += " ORDER BY name"
        cursor.execute(sql, params)
        return cursor.fetchall() or []
    finally:
        cursor.close()


def _referrer_index(conn):
    index = {}
    for row in _load_referrers(conn, active_only=False):
        keys = {normalize_name(row.get('name'))}
        try:
            aliases = json.loads(row.get('aliases_json') or '[]')
            if isinstance(aliases, list):
                keys |= {normalize_name(a) for a in aliases if str(a).strip()}
        except Exception:
            pass
        for key in keys:
            if key:
                index.setdefault(key, row)
    return index


def resolve_referrer(conn, raw_value, index=None):
    """Cari referrer_id dari teks bebas. Return (id, normalized, needs_review)."""
    normalized = normalize_name(raw_value)
    if not normalized:
        return None, '', 1
    index = index if index is not None else _referrer_index(conn)
    hit = index.get(normalized)
    if hit:
        return hit['id'], normalized, 0
    # "lino marketing" -> "lino"
    first = normalized.split()[0]
    hit = index.get(first)
    if hit:
        return hit['id'], first, 0
    # variasi ringan: nama master adalah awalan/akhiran
    candidates = [row for key, row in index.items()
                  if key and (key.startswith(first + ' ') or normalized.startswith(key + ' '))]
    if len(candidates) == 1:
        return candidates[0]['id'], normalized, 0
    return None, normalized, 1


# ================================================================
# KTP
# ================================================================
def _drive_file_id(url):
    text = str(url or '')
    match = re.search(r'[?&]id=([A-Za-z0-9_-]{10,})', text)
    if match:
        return match.group(1)
    match = re.search(r'/d/([A-Za-z0-9_-]{10,})', text)
    return match.group(1) if match else ''


def _file_ext_from_mime(mime):
    return {
        'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
        'image/webp': '.webp', 'application/pdf': '.pdf',
    }.get((mime or '').lower(), '')


def _save_ktp_bytes(conn, row, data, mime):
    ext = _file_ext_from_mime(mime)
    if not ext:
        raise ValueError('Tipe file KTP tidak didukung')
    if len(data) > MAX_KTP_BYTES:
        raise ValueError('File KTP melebihi 5 MB')
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"FWKTP_{row['registration_no']}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, 'wb') as handle:
        handle.write(data)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE first_work_submissions SET ktp_file=%s WHERE id=%s",
            (filename, row['id']))
    finally:
        cursor.close()
    return filename


def _fetch_ktp_from_bridge(conn, row):
    """Ambil file KTP lama via Apps Script (?ktp=&token=). Return filename."""
    file_id = _drive_file_id(row.get('ktp_drive_url') or row.get('photoid_url'))
    if not file_id:
        raise ValueError('Link KTP tidak berisi file ID')
    url = _config_get(conn, CONFIG_SHEET_URL)
    token = _config_get(conn, CONFIG_KTP_TOKEN)
    if not url or not token:
        raise ValueError('Integrasi Apps Script / token KTP belum diatur admin')
    _check_public_url(url)
    response = requests.get(url, params={'ktp': file_id, 'token': token},
                            timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    _check_public_url(response.url)
    response.raise_for_status()
    payload = response.json()
    if payload.get('error'):
        raise ValueError(payload['error'])
    data = base64.b64decode(payload.get('data_base64') or '')
    return _save_ktp_bytes(conn, row, data, payload.get('mimeType'))


# ================================================================
# SYNC SHEET
# ================================================================
def _http_json(url, params, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            _check_public_url(url)
            response = requests.get(url, params=params, timeout=60,
                                    headers={'User-Agent': 'Mozilla/5.0'})
            _check_public_url(response.url)
            response.raise_for_status()
            return response
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            time.sleep(1 + attempt)
    raise last_error


def _headers_and_rows(response):
    text = response.content.decode('utf-8-sig', errors='replace')
    stripped = text.lstrip()
    if stripped.startswith('{'):
        payload = response.json()
        headers = payload.get('headers') or []
        rows = payload.get('rows') or []
        if rows and isinstance(rows[0], dict):
            keys = list(rows[0].keys())
            return keys, [[row.get(key) for key in keys] for row in rows]
        return headers, rows
    reader = csv.reader(io.StringIO(text))
    all_rows = [row for row in reader]
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]


def _header_keys(headers):
    """Header -> kunci internal, unik per kolom.

    Sheet punya kolom tanpa judul di ujung kanan; tanpa penjagaan ini kolom
    kosong terakhir menimpa `timestamp` kolom pertama sehingga semua baris
    migrasi memakai waktu sekarang dan source_uid tidak stabil (duplikat).
    """
    keys, used = [], set()
    for index, header in enumerate(headers):
        normalized = re.sub(r'[^a-z0-9]', '', str(header or '').lower())
        key = HEADER_MAP.get(normalized, f'col_{index}')
        if not normalized and index > 0:
            key = f'col_{index}'
        if key in used:
            key = f'col_{index}'
        used.add(key)
        keys.append(key)
    return keys


def _fetch_sheet_rows(conn, since=None):
    url = _config_get(conn, CONFIG_SHEET_URL)
    if not url:
        raise ValueError('URL Apps Script First Work belum diatur (system_config)')
    collected = []
    headers = []
    offset = 0
    for _ in range(50):
        params = {'rows': '1', 'offset': offset, 'limit': 500}
        if since:
            params['since'] = since
        response = _http_json(url, params)
        page_headers, page_rows = _headers_and_rows(response)
        if not headers:
            headers = page_headers
        collected.extend(page_rows)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        next_offset = payload.get('next_offset')
        if next_offset is None:
            break
        offset = int(next_offset)
    return headers, collected


def _normalize_sheet_row(headers, row, row_index):
    keys = _header_keys(headers)
    raw = {}
    for index, key in enumerate(keys):
        raw[key] = row[index] if index < len(row) else ''
    submitted_at = parse_datetime(raw.get('timestamp')) or parse_datetime(raw.get('col_0'))
    nama = _clean(raw.get('nama'), 150)
    if not nama:
        return None
    nik, nik_raw = normalize_nik(raw.get('nik_raw'))
    if not nik_raw:
        nik_raw = _clean(raw.get('nik_raw'), 32)
    pendidikan_raw = _clean(raw.get('pendidikan_raw'), 100)
    referensi_raw = _clean(raw.get('referensi_raw'), 150)
    no_hp = _clean(raw.get('no_hp'), 30)
    no_hp_norm = normalize_hp(no_hp)
    if not submitted_at:
        # Jangan menebak; baris tanpa timestamp tetap masuk tetapi ditandai.
        submitted_at = datetime.now()
    stamp = submitted_at.strftime('%Y-%m-%d %H:%M:%S')
    uid_src = '|'.join([stamp, nik_raw or '', nama.lower()])
    source_uid = 'sheet-' + hashlib.md5(uid_src.encode('utf-8')).hexdigest()
    normalized = {
        'source_uid': source_uid,
        'sheet_row': row_index + 2,
        'sheet_seq': _clean(raw.get('sheet_seq1') or raw.get('sheet_seq2'), 20),
        'submitted_at': submitted_at,
        'email': _clean(raw.get('email'), 150),
        'nik': nik,
        'nik_raw': nik_raw,
        'nik_valid': 1 if nik else 0,
        'nama': nama,
        'pendidikan_raw': pendidikan_raw,
        'pendidikan_norm': normalize_pendidikan(pendidikan_raw),
        'referensi_raw': referensi_raw,
        'referensi_norm': normalize_name(referensi_raw),
        'no_hp': no_hp,
        'no_hp_norm': no_hp_norm,
        'branch_code': 'SBY',
        'ktp_drive_url': _clean(raw.get('ktp_drive_url'), 500),
        'photoid_url': _clean(raw.get('photoid_url'), 500),
        'merged_doc_id': _clean(raw.get('merged_doc_id'), 100),
        'merged_doc_url': _clean(raw.get('merged_doc_url') or raw.get('merged_doc_link'), 500),
        'merge_status': _clean(raw.get('merge_status'), 255),
        '_raw': raw,
    }
    return normalized


def _upsert_stage(conn, normalized):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO first_work_sheet_stage
                (source_uid, sheet_row, payload_json, normalized_json,
                 import_status, import_note)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                sheet_row=VALUES(sheet_row),
                payload_json=VALUES(payload_json),
                normalized_json=VALUES(normalized_json),
                import_status=VALUES(import_status),
                import_note=VALUES(import_note)
        """, (
            normalized['source_uid'], normalized['sheet_row'],
            json.dumps(normalized.get('_raw') or {}, ensure_ascii=False, default=str),
            json.dumps({k: v for k, v in normalized.items() if k != '_raw'},
                       ensure_ascii=False, default=str),
            'imported', '',
        ))
    finally:
        cursor.close()


def _serialize_for_db(normalized):
    data = dict(normalized)
    data.pop('_raw', None)
    return data


def _upsert_submission(conn, normalized, referrer_index):
    referrer_id, referrer_norm, needs_review = resolve_referrer(
        conn, normalized.get('referensi_raw'), referrer_index)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id FROM first_work_submissions WHERE source_uid=%s",
            (normalized['source_uid'],))
        existing = cursor.fetchone()
    finally:
        cursor.close()

    fields = _serialize_for_db(normalized)
    fields['referrer_id'] = referrer_id
    fields['referrer_needs_review'] = needs_review

    if existing:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE first_work_submissions SET
                    email=VALUES(email), nik=%s, nik_raw=%s, nik_valid=%s,
                    nama=%s, pendidikan_raw=%s, pendidikan_norm=%s,
                    referensi_raw=%s, referensi_norm=%s,
                    referrer_id=COALESCE(referrer_id, %s),
                    referrer_needs_review=%s,
                    no_hp=%s, no_hp_norm=%s,
                    ktp_drive_url=%s, photoid_url=%s,
                    merged_doc_id=%s, merged_doc_url=%s, merge_status=%s,
                    sheet_row=%s, sheet_seq=%s
                WHERE id=%s
            """.replace('email=VALUES(email)', 'email=%s'), (
                fields['email'], fields['nik'], fields['nik_raw'], fields['nik_valid'],
                fields['nama'], fields['pendidikan_raw'], fields['pendidikan_norm'],
                fields['referensi_raw'], fields['referensi_norm'],
                referrer_id, needs_review,
                fields['no_hp'], fields['no_hp_norm'],
                fields['ktp_drive_url'], fields['photoid_url'],
                fields['merged_doc_id'], fields['merged_doc_url'], fields['merge_status'],
                fields['sheet_row'], fields['sheet_seq'], existing['id'],
            ))
        finally:
            cursor.close()
        return 'updated'

    registration_no = _next_reg_no(conn, fields['submitted_at'])
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO first_work_submissions
                (registration_no, source, source_uid, sheet_row, sheet_seq,
                 submitted_at, email, nik, nik_raw, nik_valid, nama,
                 pendidikan_raw, pendidikan_norm, referensi_raw, referensi_norm,
                 referrer_id, referrer_needs_review, no_hp, no_hp_norm, branch_code,
                 ktp_drive_url, photoid_url, merged_doc_id, merged_doc_url,
                 merge_status, status)
            VALUES (%s,'sheet',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,'submitted')
        """, (
            registration_no, fields['source_uid'], fields['sheet_row'],
            fields['sheet_seq'], fields['submitted_at'], fields['email'],
            fields['nik'], fields['nik_raw'], fields['nik_valid'], fields['nama'],
            fields['pendidikan_raw'], fields['pendidikan_norm'],
            fields['referensi_raw'], fields['referensi_norm'],
            referrer_id, needs_review, fields['no_hp'], fields['no_hp_norm'],
            fields['branch_code'], fields['ktp_drive_url'], fields['photoid_url'],
            fields['merged_doc_id'], fields['merged_doc_url'], fields['merge_status'],
        ))
        submission_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO first_work_events
                (submission_id, event, status_from, status_to, note, actor, actor_role)
            VALUES (%s,'created','','submitted','Migrasi Sheet','system','system')
        """, (submission_id,))
    finally:
        cursor.close()
    return 'inserted'


def _sync_sheet(conn, dry_run=False, full=False):
    since = None
    if not full:
        last = _config_get(conn, CONFIG_LAST_SYNC)
        if last:
            since = last.split('|')[0].strip()[:10]
    headers, rows = _fetch_sheet_rows(conn, since=since)
    referrer_index = _referrer_index(conn)
    stats = {'fetched': len(rows), 'inserted': 0, 'updated': 0,
             'skipped': 0, 'invalid_nik': 0, 'needs_review': 0}
    samples = []
    for index, row in enumerate(rows):
        normalized = _normalize_sheet_row(headers, row, index)
        if not normalized:
            stats['skipped'] += 1
            continue
        if not normalized['nik_valid']:
            stats['invalid_nik'] += 1
        referrer_id, _, needs_review = resolve_referrer(
            conn, normalized.get('referensi_raw'), referrer_index)
        if needs_review:
            stats['needs_review'] += 1
        if dry_run:
            # Tidak menulis apa pun.
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT id FROM first_work_submissions WHERE source_uid=%s",
                    (normalized['source_uid'],))
                exists = cursor.fetchone()
            finally:
                cursor.close()
            stats['updated' if exists else 'inserted'] += 1
            if len(samples) < 10:
                samples.append({
                    'sheet_row': normalized['sheet_row'],
                    'submitted_at': normalized['submitted_at'].strftime('%Y-%m-%d %H:%M:%S'),
                    'nama': normalized['nama'],
                    'nik_valid': normalized['nik_valid'],
                    'referensi': normalized['referensi_raw'],
                    'referrer_id': referrer_id,
                    'needs_review': needs_review,
                })
            continue
        _upsert_stage(conn, normalized)
        result = _upsert_submission(conn, normalized, referrer_index)
        stats[result] += 1

    if not dry_run:
        _config_set(conn, CONFIG_LAST_SYNC,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' | ' +
                    f"{stats['inserted']} baru, {stats['updated']} update")
        conn.commit()
    return stats, samples


# ================================================================
# ROUTES
# ================================================================
def register_first_work_routes(app):

    # ---------------- PUBLIK ----------------
    @app.route('/api/first-work/referrers')
    def api_first_work_referrers_public():
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            branches = _branches(conn)
            branch = _request_branch(conn, branches=branches)
            rows = _load_referrers(conn, active_only=True, branch=branch)
            info = next((b for b in branches if b['code'] == branch), None)
            conn.close()
            return jsonify({
                'branch': branch,
                'branch_name': (info or {}).get('name') or branch,
                'referrers': [{'id': r['id'], 'name': r['name']} for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/first-work/check-nik')
    def api_first_work_check_nik():
        """Cek cepat apakah NIK sudah terdaftar (form publik, tanpa data pribadi)."""
        ip = client_ip() or '?'
        if not _check_ok(ip):
            return jsonify({'status': 'error',
                            'msg': 'Terlalu banyak pengecekan. Coba lagi sebentar.'}), 429
        nik, _raw = normalize_nik(request.args.get('nik'))
        if len(nik) != 16:
            return jsonify({'status': 'success', 'valid': False, 'exists': False})
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'SELECT COUNT(*) FROM first_work_submissions WHERE nik=%s', (nik,))
                count = int((cursor.fetchone() or [0])[0] or 0)
            finally:
                cursor.close()
            return jsonify({'status': 'success', 'valid': True, 'exists': count > 0})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/first-work/public', methods=['POST'])
    def api_first_work_public_submit():
        conn = None
        try:
            ip = client_ip() or '?'
            if not _rate_ok(ip):
                return jsonify({'status': 'error',
                                'msg': 'Terlalu banyak pengiriman dari perangkat ini. '
                                       'Coba lagi beberapa saat.'}), 429

            nik, nik_raw = normalize_nik(request.form.get('nik') or request.form.get('nik_raw'))
            nama = _clean(request.form.get('nama'), 150)
            pendidikan = _clean(request.form.get('pendidikan'), 100)
            no_hp_raw = _clean(request.form.get('no_hp'), 30)
            no_hp = normalize_hp(no_hp_raw)
            referrer_id_raw = _clean(request.form.get('referrer_id'), 20)
            referensi_text = _clean(request.form.get('referensi_text'), 150)

            if len(nik) != 16:
                return jsonify({'status': 'error',
                                'msg': 'NIK sesuai KTP wajib 16 digit angka'}), 400
            if len(nama) < 3:
                return jsonify({'status': 'error',
                                'msg': 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter)'}), 400
            if not pendidikan:
                return jsonify({'status': 'error',
                                'msg': 'Pendidikan Terakhir wajib diisi'}), 400
            if not no_hp:
                return jsonify({'status': 'error',
                                'msg': 'Nomor Handphone tidak valid'}), 400

            file = request.files.get('ktp')
            if file is None or not file.filename:
                return jsonify({'status': 'error',
                                'msg': 'Upload Identitas (KTP) wajib dilampirkan'}), 400

            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500

            # Duplikat NIK: tolak dengan pesan tanpa membocorkan data orang lain.
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT id FROM first_work_submissions WHERE nik=%s LIMIT 1", (nik,))
                if cursor.fetchone():
                    return jsonify({'status': 'error',
                                    'msg': 'NIK ini sudah terdaftar. Hubungi Traineer '
                                           'bila perlu koreksi data.'}), 409
            finally:
                cursor.close()

            referrer_id = None
            referensi_raw = referensi_text
            referrer_needs_review = 0
            if referrer_id_raw.isdigit():
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute(
                        "SELECT id, name FROM first_work_referrers "
                        "WHERE id=%s AND active=1", (int(referrer_id_raw),))
                    ref = cursor.fetchone()
                finally:
                    cursor.close()
                if not ref:
                    return jsonify({'status': 'error',
                                    'msg': 'Referensi tidak valid. Pilih dari daftar.'}), 400
                referrer_id = ref['id']
                referensi_raw = ref['name']
            else:
                if len(referensi_text) < 2:
                    return jsonify({'status': 'error',
                                    'msg': 'Referensi wajib dipilih atau diisi'}), 400
                referrer_needs_review = 1

            # Validasi isi file (magic bytes) + ukuran.
            header = file.stream.read(8)
            file.stream.seek(0)
            is_jpeg = header.startswith(b'\xff\xd8')
            is_png = header.startswith(b'\x89PNG\r\n\x1a\n'[:8])
            is_pdf = header.startswith(b'%PDF')
            if not (is_jpeg or is_png or is_pdf):
                return jsonify({'status': 'error',
                                'msg': 'File KTP harus berupa JPG, PNG, atau PDF'}), 400
            file.stream.seek(0, os.SEEK_END)
            size = file.stream.tell()
            file.stream.seek(0)
            if size > MAX_KTP_BYTES:
                return jsonify({'status': 'error',
                                'msg': 'Ukuran file KTP maksimal 5 MB'}), 400

            submitted_at = datetime.now()
            registration_no = _next_reg_no(conn, submitted_at)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            filename = save_file(file, 'FWKTP', registration_no, UPLOAD_DIR)
            if not filename:
                conn.rollback()
                return jsonify({'status': 'error',
                                'msg': 'Gagal menyimpan file KTP. Coba lagi.'}), 400

            source_uid = 'form-' + uuid.uuid4().hex
            branch_code = _request_branch(conn)
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO first_work_submissions
                        (registration_no, source, source_uid, submitted_at,
                         nik, nik_raw, nik_valid, nama, pendidikan_raw,
                         pendidikan_norm, referensi_raw, referensi_norm,
                         referrer_id, referrer_needs_review, no_hp, no_hp_norm,
                         branch_code, ktp_file, status)
                    VALUES (%s,'form',%s,%s,%s,%s,1,%s,%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,%s,'submitted')
                """, (
                    registration_no, source_uid, submitted_at, nik, nik_raw,
                    nama, pendidikan, normalize_pendidikan(pendidikan),
                    referensi_raw, normalize_name(referensi_raw),
                    referrer_id, referrer_needs_review, no_hp_raw, no_hp,
                    branch_code, filename,
                ))
                submission_id = cursor.lastrowid
                cursor.execute("""
                    INSERT INTO first_work_events
                        (submission_id, event, status_from, status_to, note,
                         actor, actor_role, ip)
                    VALUES (%s,'created','','submitted','Kirim form publik',
                            'public','public',%s)
                """, (submission_id, ip))
                conn.commit()
            finally:
                cursor.close()

            log_activity_async(None, 'first_work_submit', 'public', nama,
                               new_data={'registration_no': registration_no}, ip=ip)
            return jsonify({
                'status': 'success',
                'msg': 'Absensi FirstWork berhasil dikirim.',
                'registration_no': registration_no,
                'nama': nama,
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

    # ---------------- DAFTAR / DETAIL ----------------
    @app.route('/api/first-work')
    @role_required(VIEW_ROLES)
    def api_first_work_list():
        conn = None
        try:
            page = max(1, int(request.args.get('page', 1) or 1))
            limit = min(max(1, int(request.args.get('limit', 50) or 50)), 200)
            offset = (page - 1) * limit
            status = _clean(request.args.get('status'), 30)
            q = _clean(request.args.get('q'), 100)
            referrer_id = _clean(request.args.get('referrer_id'), 20)
            date_from = _clean(request.args.get('date_from'), 10)
            date_to = _clean(request.args.get('date_to'), 10)
            branch_filter = _clean(request.args.get('branch'), 10).upper()

            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500

            where, params = [], []
            scope = _scope_branch(conn)
            if scope:
                where.append('s.branch_code=%s')
                params.append(scope)
            elif branch_filter:
                where.append('s.branch_code=%s')
                params.append(branch_filter)
            if status:
                if status not in VALID_STATUSES:
                    return jsonify({'error': 'Status tidak valid'}), 400
                where.append('s.status=%s')
                params.append(status)
            if referrer_id.isdigit():
                where.append('s.referrer_id=%s')
                params.append(int(referrer_id))
            if date_from:
                where.append('DATE(s.submitted_at) >= %s')
                params.append(date_from)
            if date_to:
                where.append('DATE(s.submitted_at) <= %s')
                params.append(date_to)
            if q:
                like = f'%{q}%'
                where.append('(s.nama LIKE %s OR s.nik LIKE %s OR s.no_hp_norm LIKE %s '
                             'OR s.referensi_raw LIKE %s OR s.registration_no LIKE %s)')
                params += [like] * 5

            where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM first_work_submissions s" + where_sql,
                    params)
                total = int((cursor.fetchone() or {}).get('total') or 0)

                cursor.execute("""
                    SELECT s.*, r.name AS referrer_name
                    FROM first_work_submissions s
                    LEFT JOIN first_work_referrers r ON r.id = s.referrer_id
                """ + where_sql + " ORDER BY s.submitted_at DESC, s.id DESC LIMIT %s OFFSET %s",
                    params + [limit, offset])
                rows = cursor.fetchall() or []

                # Statistik memakai scope+filters selain status agar badge stabil.
                stat_where, stat_params = [], []
                if scope:
                    stat_where.append('branch_code=%s')
                    stat_params.append(scope)
                cursor.execute(
                    "SELECT status, COUNT(*) AS n FROM first_work_submissions"
                    + ((' WHERE ' + ' AND '.join(stat_where)) if stat_where else '')
                    + " GROUP BY status", stat_params)
                stats = {'total': 0, 'submitted': 0, 'verified': 0,
                         'rejected': 0, 'today': 0, 'needs_review': 0}
                for stat in cursor.fetchall():
                    stats[stat['status']] = int(stat['n'] or 0)
                    stats['total'] += int(stat['n'] or 0)
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM first_work_submissions"
                    + ((' WHERE ' + ' AND '.join(stat_where + ['referrer_needs_review=1']))
                       if stat_where else ' WHERE referrer_needs_review=1'),
                    stat_params)
                stats['needs_review'] = int((cursor.fetchone() or {}).get('n') or 0)
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM first_work_submissions WHERE DATE(submitted_at)=CURDATE()"
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

    @app.route('/api/first-work/meta')
    @role_required(VIEW_ROLES)
    def api_first_work_meta():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            # Referrer ikut scope cabang — daftar nama referrer cabang lain
            # tidak boleh muncul di dropdown traineer/admin cabang ini.
            scope = _scope_branch(conn)
            referrers = _load_referrers(conn, active_only=False, branch=scope)
            return jsonify({
                'referrers': referrers,
                'statuses': [{'value': k, 'label': v} for k, v in STATUS_LABELS.items()],
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

    @app.route('/api/first-work/<int:submission_id>')
    @role_required(VIEW_ROLES)
    def api_first_work_detail(submission_id):
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT s.*, r.name AS referrer_name
                    FROM first_work_submissions s
                    LEFT JOIN first_work_referrers r ON r.id=s.referrer_id
                    WHERE s.id=%s
                """, (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'error': 'Data di luar cabang Anda'}), 403
                cursor.execute("""
                    SELECT event, status_from, status_to, note, actor, actor_role,
                           created_at
                    FROM first_work_events WHERE submission_id=%s
                    ORDER BY id DESC
                """, (submission_id,))
                events = cursor.fetchall() or []
            finally:
                cursor.close()
            data = _serialize(row)
            data['can_download_ktp'] = bool(row.get('ktp_file') or row.get('ktp_drive_url')
                                            or row.get('photoid_url'))
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

    # ---------------- VERIFIKASI ----------------
    @app.route('/api/first-work/<int:submission_id>/verify', methods=['POST'])
    @role_required(EDIT_ROLES)
    def api_first_work_verify(submission_id):
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            action = _clean(body.get('action'), 20).lower()
            note = _clean(body.get('note'), 500)
            if action not in ('verify', 'reject'):
                return jsonify({'status': 'error',
                                'msg': 'Aksi harus verify atau reject'}), 400
            if action == 'reject' and not note:
                return jsonify({'status': 'error',
                                'msg': 'Alasan penolakan wajib diisi'}), 400

            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM first_work_submissions WHERE id=%s",
                               (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error', 'msg': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'status': 'error', 'msg': 'Data di luar cabang Anda'}), 403
                new_status = 'verified' if action == 'verify' else 'rejected'
                actor = session.get('full_name') or session.get('user_name') or ''
                cursor.execute("""
                    UPDATE first_work_submissions
                    SET status=%s, verification_note=%s, verified_by=%s,
                        verified_at=NOW()
                    WHERE id=%s
                """, (new_status, note, actor, submission_id))
                cursor.execute("""
                    INSERT INTO first_work_events
                        (submission_id, event, status_from, status_to, note,
                         actor, actor_role, ip)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (submission_id, new_status, row.get('status'), new_status,
                      note, actor, session.get('user_role', ''), client_ip()))
                conn.commit()
            finally:
                cursor.close()

            log_activity_async(None, 'first_work_' + action, session.get('user_role', ''),
                               session.get('full_name') or session.get('user_name') or '',
                               old_data={'status': row.get('status')},
                               new_data={'status': new_status, 'note': note},
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': 'Data diperbarui.',
                            'new_status': new_status})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- EDIT (ADMIN) ----------------
    @app.route('/api/first-work/<int:submission_id>', methods=['PATCH'])
    @role_required(ADMIN_ROLES)
    def api_first_work_edit(submission_id):
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM first_work_submissions WHERE id=%s",
                               (submission_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error', 'msg': 'Data tidak ditemukan'}), 404
                if not _row_allowed(row, conn):
                    return jsonify({'status': 'error', 'msg': 'Data di luar cabang Anda'}), 403

                updates, params = [], []
                for field, column in (('nama', 'nama'), ('pendidikan', 'pendidikan_raw'),
                                      ('no_hp', 'no_hp')):
                    if field in body:
                        value = _clean(body.get(field), 150)
                        updates.append(f'{column}=%s')
                        params.append(value)
                if 'nik' in body:
                    nik, nik_raw = normalize_nik(body.get('nik'))
                    if len(nik) != 16:
                        return jsonify({'status': 'error',
                                        'msg': 'NIK harus 16 digit'}), 400
                    updates += ['nik=%s', 'nik_raw=%s', 'nik_valid=1']
                    params += [nik, nik_raw]
                if 'no_hp' in body:
                    updates.append('no_hp_norm=%s')
                    params.append(normalize_hp(body.get('no_hp')))
                if 'pendidikan' in body:
                    updates.append('pendidikan_norm=%s')
                    params.append(normalize_pendidikan(body.get('pendidikan')))
                if 'referrer_id' in body:
                    ref_id = body.get('referrer_id')
                    if ref_id in (None, '', 0):
                        updates += ['referrer_id=NULL', 'referrer_needs_review=1']
                    else:
                        cursor.execute(
                            "SELECT id FROM first_work_referrers WHERE id=%s",
                            (int(ref_id),))
                        if not cursor.fetchone():
                            return jsonify({'status': 'error',
                                            'msg': 'Referrer tidak ditemukan'}), 400
                        updates += ['referrer_id=%s', 'referrer_needs_review=0']
                        params.append(int(ref_id))
                if not updates:
                    return jsonify({'status': 'error', 'msg': 'Tidak ada perubahan'}), 400
                params.append(submission_id)
                cursor.execute(
                    "UPDATE first_work_submissions SET " + ', '.join(updates) +
                    " WHERE id=%s", params)
                actor = session.get('full_name') or session.get('user_name') or ''
                cursor.execute("""
                    INSERT INTO first_work_events
                        (submission_id, event, status_from, status_to, note,
                         actor, actor_role, ip)
                    VALUES (%s,'edit',%s,%s,'Koreksi admin',%s,%s,%s)
                """, (submission_id, row.get('status'), row.get('status'), actor,
                      session.get('user_role', ''), client_ip()))
                conn.commit()
            finally:
                cursor.close()
            log_activity_async(None, 'first_work_edit', session.get('user_role', ''),
                               session.get('full_name') or session.get('user_name') or '',
                               old_data={'id': submission_id}, new_data=body,
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': 'Data diperbarui.'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- KTP ----------------
    @app.route('/api/first-work/<int:submission_id>/ktp')
    @role_required(EDIT_ROLES)
    def api_first_work_ktp(submission_id):
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM first_work_submissions WHERE id=%s",
                               (submission_id,))
                row = cursor.fetchone()
            finally:
                cursor.close()
            if not row:
                return jsonify({'error': 'Data tidak ditemukan'}), 404
            if not _row_allowed(row, conn):
                return jsonify({'error': 'Data di luar cabang Anda'}), 403

            filename = row.get('ktp_file') or ''
            path = os.path.join(UPLOAD_DIR, os.path.basename(filename)) if filename else ''
            if not (filename and os.path.isfile(path)):
                filename = _fetch_ktp_from_bridge(conn, row)
                conn.commit()
                path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
            if not os.path.isfile(path):
                return jsonify({'error': 'File KTP tidak tersedia'}), 404
            return send_file(path, as_attachment=True,
                             download_name=f"KTP_{row['registration_no']}"
                                           f"{os.path.splitext(filename)[1]}")
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- EXPORT ----------------
    @app.route('/api/first-work/export')
    @role_required(VIEW_ROLES)
    def api_first_work_export():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            scope = _scope_branch(conn)
            where, params = [], []
            if scope:
                where.append('s.branch_code=%s')
                params.append(scope)
            status = _clean(request.args.get('status'), 30)
            if status in VALID_STATUSES:
                where.append('s.status=%s')
                params.append(status)
            date_from = _clean(request.args.get('date_from'), 10)
            date_to = _clean(request.args.get('date_to'), 10)
            if date_from:
                where.append('DATE(s.submitted_at) >= %s')
                params.append(date_from)
            if date_to:
                where.append('DATE(s.submitted_at) <= %s')
                params.append(date_to)
            where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT s.registration_no, s.submitted_at, s.nama, s.nik,
                           s.nik_raw, s.nik_valid, s.pendidikan_raw,
                           s.pendidikan_norm, s.referensi_raw, r.name AS referrer_name,
                           s.no_hp, s.status, s.verification_note, s.verified_by,
                           s.verified_at, s.merge_status
                    FROM first_work_submissions s
                    LEFT JOIN first_work_referrers r ON r.id=s.referrer_id
                """ + where_sql + " ORDER BY s.submitted_at DESC, s.id DESC", params)
                rows = cursor.fetchall() or []
            finally:
                cursor.close()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['No. Registrasi', 'Waktu Kirim', 'Nama', 'NIK',
                             'NIK Valid', 'Pendidikan', 'Referensi', 'No. HP',
                             'Status', 'Catatan Verifikasi', 'Diverifikasi Oleh',
                             'Waktu Verifikasi'])
            for row in rows:
                writer.writerow([
                    row.get('registration_no'), row.get('submitted_at'),
                    row.get('nama'), row.get('nik') or row.get('nik_raw'),
                    'Ya' if row.get('nik_valid') else 'Tidak',
                    row.get('pendidikan_raw') or row.get('pendidikan_norm'),
                    row.get('referrer_name') or row.get('referensi_raw'),
                    row.get('no_hp'), STATUS_LABELS.get(row.get('status'), row.get('status')),
                    row.get('verification_note'), row.get('verified_by'),
                    row.get('verified_at'),
                ])
            response = make_response('\ufeff' + output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = \
                'attachment; filename=first_work_export.csv'
            return response
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- SYNC ----------------
    @app.route('/api/first-work/sync', methods=['POST'])
    @role_required(ADMIN_ROLES)
    def api_first_work_sync():
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            dry_run = bool(body.get('dry_run'))
            full = bool(body.get('full'))
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            stats, samples = _sync_sheet(conn, dry_run=dry_run, full=full)
            log_activity_async(None, 'first_work_sync', 'admin',
                               session.get('full_name') or session.get('user_name') or '',
                               new_data={'dry_run': dry_run, **stats}, ip=client_ip())
            return jsonify({'status': 'success', 'dry_run': dry_run,
                            'stats': stats, 'samples': samples})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------------- REFERRER MANAGE (ADMIN) ----------------
    @app.route('/api/first-work/referrers/manage')
    @role_required(ADMIN_ROLES)
    def api_first_work_referrers_manage():
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            scope = _scope_branch(conn)
            where = ''
            params = []
            if scope:
                where = ' WHERE r.branch_code=%s OR r.branch_code IS NULL'
                params = [scope]
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT r.*, COUNT(s.id) AS submission_count
                    FROM first_work_referrers r
                    LEFT JOIN first_work_submissions s ON s.referrer_id=r.id
                """ + where + """
                    GROUP BY r.id
                    ORDER BY r.active DESC, r.name
                """, params)
                rows = cursor.fetchall() or []
                cursor.execute("""
                    SELECT id, username, full_name, role, branch_code
                    FROM users ORDER BY full_name
                """)
                users = cursor.fetchall() or []
            finally:
                cursor.close()
            return jsonify({'referrers': rows, 'users': users})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/first-work/referrers', methods=['POST'])
    @role_required(ADMIN_ROLES)
    def api_first_work_referrer_add():
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            name = _clean(body.get('name'), 100).upper()
            if len(name) < 2:
                return jsonify({'status': 'error', 'msg': 'Nama referrer wajib diisi'}), 400
            user_id = body.get('user_id') or None
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                scope = _scope_branch(conn)
                branch_code = 'SBY' if (not scope or scope == _NO_BRANCH) else scope
                cursor.execute(
                    "INSERT INTO first_work_referrers (name, user_id, branch_code) "
                    "VALUES (%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE user_id=COALESCE(%s, user_id), active=1",
                    (name, user_id, branch_code, user_id))
                conn.commit()
                cursor.execute("SELECT * FROM first_work_referrers WHERE name=%s", (name,))
                row = cursor.fetchone()
            finally:
                cursor.close()
            return jsonify({'status': 'success', 'referrer': row})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/first-work/referrers/<int:referrer_id>', methods=['PATCH'])
    @role_required(ADMIN_ROLES)
    def api_first_work_referrer_patch(referrer_id):
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            updates, params = [], []
            if 'name' in body:
                name = _clean(body.get('name'), 100).upper()
                if len(name) < 2:
                    return jsonify({'status': 'error', 'msg': 'Nama tidak valid'}), 400
                updates.append('name=%s')
                params.append(name)
            if 'user_id' in body:
                updates.append('user_id=%s')
                params.append(body.get('user_id') or None)
            if 'active' in body:
                updates.append('active=%s')
                params.append(1 if body.get('active') else 0)
            if not updates:
                return jsonify({'status': 'error', 'msg': 'Tidak ada perubahan'}), 400
            params.append(referrer_id)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE first_work_referrers SET " + ', '.join(updates) +
                    " WHERE id=%s", params)
                conn.commit()
            finally:
                cursor.close()
            return jsonify({'status': 'success', 'msg': 'Referrer diperbarui.'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
