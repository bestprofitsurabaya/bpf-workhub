"""Sinkronisasi Google Sheet untuk Receptionist (v2.42.0).

Dua sumber data Google Sheet (paritas pola overtime v2.22 — tombol Refresh
manual, fetch CSV gviz / JSON Apps Script, upsert kunci stabil):

1. **Sheet Pelamar** — pendaftaran via Google Form lama. Sync menarik baris
   sheet lalu upsert ke tabel `applicants` dengan source_uid =
   'plm-' + md5(nama|tanggal|jam) — STABIL walau posisi baris sheet bergeser.
   Data yang dikelola di aplikasi (status, verifikasi, kehadiran, resign)
   TIDAK tersentuh sync. Input baru ke depan memakai form dalam aplikasi
   (POST /api/applicants/manual). Sejak v2.42.0: pelamar LULUS dijadikan
   karyawan lewat POST /api/applicants/<id>/register-employee.
2. **In-Out Karyawan** — sejak v2.42.0 bukan lagi read-only. Mode
   pencatatan diatur admin (`receptionist_inout_mode`):
   - `sheet` (mode lama): aplikasi hanya membaca, sumber tetap sheet.
   - `hybrid` (default): resepsionis mencatat keluar/masuk langsung dari
     aplikasi (source='app', terkunci) berdampingan dengan baris sheet;
     keduanya tampil menyatu di halaman In-Out Karyawan.
   Guard sync melindungi data aplikasi: baris source='app'/'registrasi'
   atau locked=1 TIDAK ditimpa/dihapus sync sheet, dan sync berhenti bila
   integritas sheet meragukan (paritas guard overtime v2.39.5).
   Setiap perubahan tercatat di `employee_inout_events` (audit trail);
   edit/hapus memakai step-up PIN (paritas edit air minum v2.37.0).

Role: `receptionist` & `admin`.
"""
import hashlib
import io
import json
import re
import secrets
import threading
import time
from datetime import datetime

from flask import request, jsonify, session, make_response

from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async,
                             generate_display_id)
from modules.stepup import stepup_required
from modules.realtime import emit_event
from modules.overtime_helpers import clean, parse_date_mdy, parse_time_12h, parse_time_any
from modules.routes_overtime import _fetch_sheet_rows

# Sheet sumber (default publik via gviz CSV). URL sesungguhnya dibaca dari
# system_config — bila sheet diubah jadi privat, admin cukup mengganti URL
# dengan Google Apps Script Web App (JSON) tanpa ubah kode; _fetch_sheet_rows
# mendukung keduanya (paritas overtime_driver_sheet_url).
DEFAULT_APPLICANTS_SHEET_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1VIavwXGX1e9R6dbfkmLltEUo0QgpgDEalUPxD2SF8a0/gviz/tq?tqx=out:csv')
DEFAULT_INOUT_SHEET_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1oBmm62eY06QDzErmt1jWw0VX4usScd0hOKqX0I0o2gM/gviz/tq?tqx=out:csv')

SHEET_URL_KEYS = {
    'applicants': 'receptionist_applicants_sheet_url',
    'inout': 'receptionist_inout_sheet_url',
}

# v2.42.0: mode pencatatan In-Out Karyawan.
#   'sheet'  — read-only, sumber tetap Google Sheet (perilaku v2.41).
#   'hybrid' — resepsionis mencatat dari aplikasi berdampingan dgn sheet.
DEFAULT_INOUT_MODE = 'hybrid'
INOUT_MODES = ('sheet', 'hybrid')
INOUT_MODE_CONFIG_KEY = 'receptionist_inout_mode'

# v2.42.0: secret webhook untuk push realtime dari Apps Script (onEdit).
WEBHOOK_SECRET_CONFIG_KEY = 'receptionist_webhook_secret'

# Sumber baris employee_inout: 'sheet' (sync), 'app' (input manual),
# 'registrasi' (pelamar lulus dijadikan karyawan).
INOUT_SOURCES = ('sheet', 'app', 'registrasi')

# Daftar karyawan aktif untuk dropdown & pelaporan — agregat dari catatan
# in-out (tanpa tabel master terpisah; identitas cukup dari riwayat).
EMPLOYEE_ROSTER_SQL = (
    "SELECT TRIM(nama) AS nama, MAX(jabatan) AS jabatan, "
    "MAX(GREATEST(COALESCE(waktu_pergi, '1970-01-01'), "
    "COALESCE(waktu_datang, '1970-01-01'))) AS terakhir_aktif "
    "FROM employee_inout WHERE TRIM(COALESCE(nama, ''))<>'' "
    "GROUP BY TRIM(nama) ORDER BY nama")


# ================================================================
# SCHEMA (idempoten, dipanggil saat startup dari app.py)
# ================================================================

def _column_exists(cursor, table, column):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s""",
        (table, column))
    return cursor.fetchone()[0] > 0


def ensure_receptionist_schema(conn=None):
    """Tabel employee_inout + kolom sync di applicants (v2.41.0)."""
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[receptionist-schema] DB unavailable, skip migration')
            return False
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employee_inout (
                id INT AUTO_INCREMENT PRIMARY KEY,
                source_uid VARCHAR(40) NOT NULL UNIQUE,
                sheet_row INT NULL,
                nama VARCHAR(100) DEFAULT '',
                jabatan VARCHAR(100) DEFAULT '',
                pergi TINYINT(1) DEFAULT 0,
                waktu_pergi DATETIME NULL,
                datang TINYINT(1) DEFAULT 0,
                waktu_datang DATETIME NULL,
                keterangan VARCHAR(255) DEFAULT '',
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_inout_nama (nama),
                INDEX idx_inout_pergi (waktu_pergi),
                INDEX idx_inout_datang (waktu_datang)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        for col, ddl in (('source_uid', 'VARCHAR(40) DEFAULT NULL'),
                         ('sheet_row', 'INT NULL'),
                         ('h2_date', 'DATE NULL')):
            if not _column_exists(cursor, 'applicants', col):
                cursor.execute(f'ALTER TABLE applicants ADD COLUMN {col} {ddl}')
        # v2.42.0: in-out dari aplikasi — sumber baris, kunci edit, aktor,
        # penaut ke pelamar, + tabel audit trail employee_inout_events.
        for col, ddl in (('source', "VARCHAR(10) DEFAULT 'sheet'"),
                         ('locked', 'TINYINT(1) DEFAULT 0'),
                         ('created_by', "VARCHAR(100) DEFAULT ''"),
                         ('updated_by', "VARCHAR(100) DEFAULT ''"),
                         ('created_at', 'DATETIME NULL'),
                         ('updated_at', 'DATETIME NULL'),
                         ('applicant_id', 'INT NULL')):
            if not _column_exists(cursor, 'employee_inout', col):
                cursor.execute(f'ALTER TABLE employee_inout ADD COLUMN {col} {ddl}')
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employee_inout_stage (
                id INT AUTO_INCREMENT PRIMARY KEY,
                source_uid VARCHAR(40) NOT NULL UNIQUE,
                sheet_row INT NULL,
                nama VARCHAR(100) DEFAULT '',
                jabatan VARCHAR(100) DEFAULT '',
                pergi TINYINT(1) DEFAULT 0,
                waktu_pergi DATETIME NULL,
                datang TINYINT(1) DEFAULT 0,
                waktu_datang DATETIME NULL,
                keterangan VARCHAR(255) DEFAULT ''
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employee_inout_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                inout_id INT NULL,
                event_type VARCHAR(30) NOT NULL,
                event_at DATETIME NOT NULL,
                actor_username VARCHAR(100) DEFAULT '',
                actor_name VARCHAR(150) DEFAULT '',
                actor_role VARCHAR(50) DEFAULT '',
                nama VARCHAR(100) DEFAULT '',
                keterangan VARCHAR(255) DEFAULT '',
                payload_json VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_inout_events_id (inout_id),
                INDEX idx_inout_events_type (event_type),
                INDEX idx_inout_events_at (event_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='employee_inout'
                 AND INDEX_NAME='idx_inout_applicant'""")
        if cursor.fetchone()[0] == 0:
            try:
                cursor.execute(
                    'ALTER TABLE employee_inout ADD INDEX idx_inout_applicant (applicant_id)')
            except Exception as e:
                print(f'[receptionist-schema] idx applicant_id: {e}')
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='applicants'
                 AND INDEX_NAME='uq_applicants_source_uid'""")
        if cursor.fetchone()[0] == 0:
            try:
                # Aman bila semua baris existing NULL (MySQL mengizinkan
                # banyak NULL pada kolom UNIQUE).
                cursor.execute('ALTER TABLE applicants '
                               'ADD UNIQUE KEY uq_applicants_source_uid (source_uid)')
            except Exception as e:
                print(f'[receptionist-schema] uq source_uid: {e}')
        # Seed URL sheet (v2.41.1) — INSERT IGNORE agar URL kustom yang
        # diganti admin (mis. Apps Script Web App) tidak tertimpa redeploy.
        for key, default in (
                ('receptionist_applicants_sheet_url', DEFAULT_APPLICANTS_SHEET_URL),
                ('receptionist_inout_sheet_url', DEFAULT_INOUT_SHEET_URL),
                ('receptionist_inout_mode', DEFAULT_INOUT_MODE)):
            try:
                cursor.execute(
                    'INSERT IGNORE INTO system_config (config_key, config_value) '
                    'VALUES (%s, %s)', (key, default))
            except Exception as e:
                print(f'[receptionist-schema] seed {key}: {e}')
        # v2.42.0: secret webhook push realtime — dibuat acak SEKALI, bisa
        # dirotasi admin via /api/receptionist/webhook-config.
        try:
            cursor.execute(
                'SELECT config_value FROM system_config WHERE config_key=%s',
                (WEBHOOK_SECRET_CONFIG_KEY,))
            if cursor.fetchone() is None:
                cursor.execute(
                    'INSERT INTO system_config (config_key, config_value) VALUES (%s, %s)',
                    (WEBHOOK_SECRET_CONFIG_KEY, secrets.token_urlsafe(32)))
        except Exception as e:
            print(f'[receptionist-schema] seed webhook secret: {e}')
        conn.commit()
        cursor.close()
        print('✔ Receptionist sync schema ready')
        return True
    except Exception as e:
        print(f'[receptionist-schema] error: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


# ================================================================
# PARSING — header & baris sheet
# ================================================================

def _norm_header(h):
    s = clean(str(h or '')).lower()
    return ''.join(ch for ch in s if ch.isalnum())


APPLICANT_HEADERS = {
    'tanggalinterview': 'tanggal',
    'jam': 'jam',
    'namalengkap': 'nama',
    'pendidikanterakhir': 'pendidikan',
    'nomorteleponhp': 'no_hp',
    'upline': 'upline',
    'user': 'user',
    'posisiyangdilamar': 'posisi',
    'tanggalh2': 'h2',
}

INOUT_HEADERS = {
    'nama': 'nama',
    'jabatanposisi': 'jabatan',
    'jabatan': 'jabatan',
    'pergi': 'pergi',
    'waktupergi': 'waktu_pergi',
    'datang': 'datang',
    'waktudatang': 'waktu_datang',
    'keterangan': 'keterangan',
}


def _map_headers(headers, mapping):
    """{field: header_asli} — header tak dikenal diabaikan (paritas map_headers)."""
    idx = {}
    for h in headers:
        f = mapping.get(_norm_header(h))
        if f and f not in idx:
            idx[f] = h
    return idx


def _truthy(v):
    return clean(str(v or '')).upper() in ('TRUE', '1', 'YA', 'YES', 'V')


# ================================================================
# MODE & AUDIT (v2.42.0) — pencatatan In-Out dari aplikasi
# ================================================================

def _inout_mode(conn=None):
    """Mode pencatatan in-out: 'sheet' (read-only) atau 'hybrid' (app+sheet)."""
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            return DEFAULT_INOUT_MODE
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s",
                       (INOUT_MODE_CONFIG_KEY,))
        row = cursor.fetchone()
        cursor.close()
        mode = clean(str((row or {}).get('config_value', '') or '')).lower()
        return mode if mode in INOUT_MODES else DEFAULT_INOUT_MODE
    except Exception:
        return DEFAULT_INOUT_MODE
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def _audit_payload(data):
    """Serialisasi aman utk kolom payload_json (maks 500 karakter)."""
    try:
        return json.dumps(data, ensure_ascii=False, default=str)[:500]
    except Exception:
        return ''


def _log_inout_event(cursor, inout_id, event_type, row=None, payload=None):
    """Catat peristiwa in-out ke employee_inout_events (audit trail).
    Best-effort: kegagalan audit tidak membatalkan operasi utama."""
    try:
        cursor.execute(
            """INSERT INTO employee_inout_events
               (inout_id, event_type, event_at, actor_username, actor_name,
                actor_role, nama, keterangan, payload_json)
               VALUES (%s,%s,NOW(),%s,%s,%s,%s,%s,%s)""",
            (inout_id, event_type,
             session.get('user_name', ''),
             session.get('full_name', session.get('user_name', '')),
             session.get('user_role', ''),
             (row or {}).get('nama', '')[:100],
             (row or {}).get('keterangan', '')[:255],
             _audit_payload(payload or {})))
    except Exception as e:
        print(f'[receptionist-inout] audit gagal ({event_type}): {e}')


def _parse_time_with_sec(value):
    """Jam sheet receptionist ('6:53:19 AM', '14:24:05', '9:56') -> 'HH:MM:SS'.

    v2.43.1: detik dipertahankan — sebelumnya memakai parse_time_12h/any
    (warisan overtime, HH:MM) sehingga 9:56:16 tersimpan 09:56:00 dan data di
    aplikasi tak sama dgn sumber sheet (1.103 baris tergeser detiknya).
    Return None bila format tak dikenal.
    """
    s = clean(str(value or ''))
    if not s:
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)?$', s, re.I)
    if not m:
        # Fallback format lain (ISO dsb.) via helper overtime, lalu lengkapi detik.
        t = parse_time_any(s)
        return f'{t}:00' if t else None
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    ampm = (m.group(4) or '').upper()
    if ampm == 'PM' and hh < 12:
        hh += 12
    elif ampm == 'AM' and hh == 12:
        hh = 0
    if mm > 59 or ss > 59:
        return None
    return f'{hh:02d}:{mm:02d}:{ss:02d}'


def _parse_dt_parts(date_raw, time_raw):
    """'9/14/2026' + '6:53:19 AM' -> '2026-09-14 06:53:19' atau None."""
    d = parse_date_mdy(date_raw)
    if not d:
        return None
    jam = _parse_time_with_sec(time_raw) or '00:00:00'
    return f'{d} {jam}'


def _parse_full_dt(raw):
    """'5/1/2026 9:56:16' -> '2026-05-01 09:56:16' atau None (detik dipertahankan, v2.43.1)."""
    raw = clean(str(raw or ''))
    if not raw:
        return None
    parts = raw.split(None, 1)
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ''
    d = parse_date_mdy(date_part)
    if not d:
        return None
    jam = _parse_time_with_sec(time_part) or '00:00:00'
    return f'{d} {jam}'


def normalize_applicant_row(r, idx):
    """Baris sheet pelamar -> kolom applicants, atau None bila tak layak."""
    def g(f):
        return clean(str(r[idx[f]])) if f in idx and idx[f] in r else ''

    nama = g('nama')
    if not nama:
        return None
    interview_at = _parse_dt_parts(g('tanggal'), g('jam'))
    if not interview_at:
        return None  # baris tanpa tanggal interview valid → dilewati
    return {
        'nama': nama[:150],
        'pendidikan': g('pendidikan')[:100],
        'no_hp': g('no_hp')[:30],
        'upline': g('upline')[:100],
        'user': g('user')[:100],
        'posisi': g('posisi')[:100],
        'interview_at': interview_at,
        'h2_date': parse_date_mdy(g('h2')) or None,
        'tanggal_raw': g('tanggal'),
        'jam_raw': g('jam'),
    }


def normalize_inout_row(r, idx, n):
    """Baris sheet in-out -> kolom employee_inout, atau None bila kosong."""
    def g(f):
        return clean(str(r[idx[f]])) if f in idx and idx[f] in r else ''

    nama = g('nama')
    waktu_pergi = _parse_full_dt(g('waktu_pergi'))
    waktu_datang = _parse_full_dt(g('waktu_datang'))
    keterangan = g('keterangan')[:255]
    if not nama and not waktu_pergi and not waktu_datang:
        return None  # baris kosong / di luar area data
    return {
        'nama': nama[:100],
        'jabatan': g('jabatan')[:100],
        'pergi': 1 if _truthy(g('pergi')) else 0,
        'waktu_pergi': waktu_pergi,
        'datang': 1 if _truthy(g('datang')) else 0,
        'waktu_datang': waktu_datang,
        'keterangan': keterangan,
        'uid': 'io-' + hashlib.md5('|'.join(
            [nama, g('waktu_pergi'), g('waktu_datang'), keterangan, str(n)]
        ).encode('utf-8')).hexdigest(),
    }


# ================================================================
# SYNC — sheet pelamar (upsert) & in-out (full replace)
# ================================================================

def _set_last_sync(conn, key, summary):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
        (key, f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {summary}"))
    conn.commit()
    cursor.close()


def _get_last_sync(conn, key):
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (key,))
        row = cursor.fetchone()
        cursor.close()
        return (row or {}).get('config_value', '')
    except Exception:
        return ''


def _get_sheet_url(conn, modul='applicants'):
    """URL sumber sheet dari system_config (paritas _get_sheet_url overtime).
    Fallback ke default bila baris belum di-seed / kosong."""
    key = SHEET_URL_KEYS.get(modul, SHEET_URL_KEYS['applicants'])
    default = (DEFAULT_APPLICANTS_SHEET_URL if modul == 'applicants'
               else DEFAULT_INOUT_SHEET_URL)
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (key,))
        row = cursor.fetchone()
        cursor.close()
        return ((row or {}).get('config_value') or default).strip() or default
    except Exception:
        return default


def _do_sync_applicants():
    """Tarik sheet pelamar lalu upsert ke `applicants` (source_uid stabil).

    Return dict {'added', 'updated', 'skipped', 'total_rows', 'summary'}.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB error')
    try:
        rows = _fetch_sheet_rows(_get_sheet_url(conn, 'applicants'))
        cursor = conn.cursor(dictionary=True)
        added = updated = skipped = 0
        for n, r in enumerate(rows):
            idx = _map_headers(r.keys(), APPLICANT_HEADERS)
            row = normalize_applicant_row(r, idx)
            if not row:
                skipped += 1
                continue
            uid = 'plm-' + hashlib.md5('|'.join(
                [row['nama'], row['tanggal_raw'], row['jam_raw']]
            ).encode('utf-8')).hexdigest()
            cursor.execute("SELECT id FROM applicants WHERE source_uid=%s", (uid,))
            existing = cursor.fetchone()
            if existing:
                # v2.42.0: pelamar yang sudah LULUS dijaga — data identitas di
                # sheet boleh diperbarui, status final (karyawan) tidak ditimpa.
                cursor.execute(
                    """UPDATE applicants SET
                       nama_lengkap=%s, pendidikan=%s, no_hp=%s, upline=%s,
                       user_field=%s, posisi=%s, interview_at=%s, h2_date=%s, sheet_row=%s
                       WHERE id=%s AND status<>'lulus'""",
                    (row['nama'], row['pendidikan'], row['no_hp'], row['upline'],
                     row['user'], row['posisi'], row['interview_at'],
                     row['h2_date'], n + 1, existing['id']))
                updated += 1
            else:
                display_id = generate_display_id('PLM', conn)
                cursor.execute(
                    """INSERT INTO applicants
                       (display_id, nama_lengkap, pendidikan, no_hp, upline, user_field,
                        posisi, interview_at, h2_date, source_uid, sheet_row)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (display_id, row['nama'], row['pendidikan'], row['no_hp'],
                     row['upline'], row['user'], row['posisi'], row['interview_at'],
                     row['h2_date'], uid, n + 1))
                added += 1
            # v2.17 parity: nilai User dari sheet ikut jadi opsi dropdown form.
            if row['user']:
                cursor.execute('INSERT IGNORE INTO applicant_user_options (name) VALUES (%s)',
                               (row['user'],))
        conn.commit()
        cursor.close()
        result = {'added': added, 'updated': updated, 'skipped': skipped,
                  'total_rows': len(rows)}
        summary = (f"{result['added']} baru, {result['updated']} diperbarui, "
                   f"{result['skipped']} dilewati (dari {result['total_rows']} baris)")
        result['summary'] = summary
        _set_last_sync(conn, 'applicants_last_sync', summary)
        return result
    finally:
        conn.close()


def _do_sync_inout():
    """Tarik sheet in-out lalu full-replace baris sumber sheet.

    v2.42.0: full-replace hanya menyentuh baris source='sheet' — catatan dari
    aplikasi (source='app'/'registrasi', locked=1) dijamin utuh. Sheet tetap
    sumber kebenaran untuk barisnya sendiri; app adalah sumber kedua.
    Return dict {'replaced', 'skipped', 'preserved', 'total_rows', 'summary'}.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB error')
    try:
        rows = _fetch_sheet_rows(_get_sheet_url(conn, 'inout'))
        cursor = conn.cursor()
        # Paritas guard overtime v2.39.5: sync berhenti bila integritas sheet
        # meragukan — mencegah data hilang karena sheet kosong/rusak.
        valid_rows = []
        for n, r in enumerate(rows):
            idx = _map_headers(r.keys(), INOUT_HEADERS)
            row = normalize_inout_row(r, idx, n)
            if not row:
                continue
            valid_rows.append((n, r, idx, row))
        if rows and len(valid_rows) < 0.5 * len(rows):
            raise ValueError(
                f'Sheet in-out tidak wajar: hanya {len(valid_rows)} dari '
                f'{len(rows)} baris valid — sync dibatalkan (data aman).')

        # Simpan dulu ke tabel staging, baru tukar — transaksi tunggal.
        cursor.execute('DELETE FROM employee_inout_stage')
        for n, r, idx, row in valid_rows:
            cursor.execute(
                """INSERT IGNORE INTO employee_inout_stage
                   (source_uid, sheet_row, nama, jabatan, pergi, waktu_pergi,
                    datang, waktu_datang, keterangan)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (row['uid'], n + 1, row['nama'], row['jabatan'], row['pergi'],
                 row['waktu_pergi'], row['datang'], row['waktu_datang'],
                 row['keterangan']))
        # Hitung data aplikasi yang terlindungi (tidak pernah disentuh sync).
        cursor.execute(
            "SELECT COUNT(*) FROM employee_inout "
            "WHERE source<>'sheet' OR locked=1")
        preserved = int(cursor.fetchone()[0])
        cursor.execute('DELETE FROM employee_inout WHERE source=%s AND locked=0', ('sheet',))
        cursor.execute(
            """INSERT INTO employee_inout
               (source_uid, sheet_row, nama, jabatan, pergi, waktu_pergi,
                datang, waktu_datang, keterangan, source, locked)
               SELECT source_uid, sheet_row, nama, jabatan, pergi, waktu_pergi,
                      datang, waktu_datang, keterangan, 'sheet', 0
               FROM employee_inout_stage""")
        replaced = cursor.rowcount
        cursor.execute('DELETE FROM employee_inout_stage')
        conn.commit()
        cursor.close()
        result = {'replaced': replaced, 'skipped': len(rows) - len(valid_rows),
                  'preserved': preserved, 'total_rows': len(rows)}
        summary = (f"{result['replaced']} baris sheet tersinkron "
                   f"(dari {result['total_rows']} baris sheet; "
                   f"{result['preserved']} catatan app dipertahankan)")
        result['summary'] = summary
        _set_last_sync(conn, 'inout_last_sync', summary)
        return result
    finally:
        conn.close()


def _serialize(row):
    """Konversi nilai DB (datetime/date) ke string JSON-safe."""
    row = dict(row)
    for k, v in row.items():
        if hasattr(v, 'strftime'):
            row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
    return row


# ================================================================
# AUTO-SYNC berkala + trigger saat login/logout (v2.41.1)
# Paritas pola overtime v2.22.1: fire-and-forget background thread,
# debounce mencegah spam Google saat user login/logout berulang.
# ================================================================

AUTO_SYNC_INTERVAL = 30 * 60      # 30 menit (detik)
_DEBOUNCE_MIN_INTERVAL = 30       # jeda minimum antar sync dipicu login/logout
_last_trigger = {'applicants': 0.0, 'inout': 0.0}

_TRIGGER_ROLES = ('receptionist', 'admin')

# v2.42.0: debounce realtime-sync on-demand (dipicu buka halaman / event socket).
_REALTIME_DEBOUNCE = 15
_realtime_state = {'last_sync': 0.0}

# v2.41.2: pelacak kegagalan beruntun — admin dinotifikasi bila sync gagal
# berkali-kali (sheet dibuat privat / dihapus / URL salah). Counter
# in-memory; reset ke 0 saat sync sukses.
_FAIL_THRESHOLD = 3
_sync_failures = {'applicants': 0, 'inout': 0}


def _notify_sync_failure(modul, err):
    """Beri tahu admin (room ga_hr_board + tabel notifications) bila sync
    gagal beruntun >= _FAIL_THRESHOLD. Best-effort, tak pernah raise."""
    count = _sync_failures[modul]
    if count < _FAIL_THRESHOLD:
        return
    label = 'Pelamar' if modul == 'applicants' else 'In-Out Karyawan'
    try:
        from modules.notifications import push_overtime_notification
        push_overtime_notification(
            'receptionist_sync_failed', f'sync_{modul}_failed',
            f'❌ Auto-sync sheet {label} gagal {count}x beruntun — '
            f'cek URL di Pengaturan: {str(err)[:140]}',
            ref_id=None)
    except Exception as ne:
        print(f'[receptionist-sync] notif gagal: {ne}')


# ================================================================
# PUSH REALTIME (v2.42.0) — Apps Script onEdit → webhook
# ================================================================

def _get_webhook_secret(conn=None):
    """Secret webhook dari system_config (paritas _get_sheet_url)."""
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            return ''
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s",
                       (WEBHOOK_SECRET_CONFIG_KEY,))
        row = cursor.fetchone()
        cursor.close()
        return ((row or {}).get('config_value') or '').strip()
    except Exception:
        return ''
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def _upsert_webhook_rows(conn, rows, modul):
    """Upsert baris hasil push webhook (subset sheet terbaru) ke tabel target.

    Baris dikirim Apps Script lengkap per baris (getDisplayValues satu baris),
    jadi upsert di sini = paritas sync pull: kunci stabil source_uid, baris
    app/registrasi tidak pernah tersentuh (khusus inout).
    Return {'added', 'updated', 'skipped'}.
    """
    cursor = conn.cursor(dictionary=True)
    added = updated = skipped = 0
    try:
        for n, r in enumerate(rows):
            if not isinstance(r, dict):
                skipped += 1
                continue
            if modul == 'applicants':
                idx = _map_headers(r.keys(), APPLICANT_HEADERS)
                row = normalize_applicant_row(r, idx)
                if not row:
                    skipped += 1
                    continue
                uid = 'plm-' + hashlib.md5('|'.join(
                    [row['nama'], row['tanggal_raw'], row['jam_raw']]
                ).encode('utf-8')).hexdigest()
                cursor.execute("SELECT id FROM applicants WHERE source_uid=%s", (uid,))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """UPDATE applicants SET
                           nama_lengkap=%s, pendidikan=%s, no_hp=%s, upline=%s,
                           user_field=%s, posisi=%s, interview_at=%s, h2_date=%s
                           WHERE id=%s AND status<>'lulus'""",
                        (row['nama'], row['pendidikan'], row['no_hp'], row['upline'],
                         row['user'], row['posisi'], row['interview_at'],
                         row['h2_date'], existing['id']))
                    updated += 1
                else:
                    display_id = generate_display_id('PLM', conn)
                    cursor.execute(
                        """INSERT INTO applicants
                           (display_id, nama_lengkap, pendidikan, no_hp, upline, user_field,
                            posisi, interview_at, h2_date, source_uid)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (display_id, row['nama'], row['pendidikan'], row['no_hp'],
                         row['upline'], row['user'], row['posisi'], row['interview_at'],
                         row['h2_date'], uid))
                    added += 1
                if row['user']:
                    cursor.execute('INSERT IGNORE INTO applicant_user_options (name) VALUES (%s)',
                                   (row['user'],))
            else:  # inout
                idx = _map_headers(r.keys(), INOUT_HEADERS)
                row = normalize_inout_row(r, idx, 0)
                if not row:
                    skipped += 1
                    continue
                # UID pull memakai posisi baris sheet; push hanya membawa satu
                # baris (tanpa posisi). Maka cocokkan dulu berdasar ISI baris
                # (nama+waktu+keterangan) agar edit satu baris tidak menciptakan
                # duplikat. UID khusus push bebas posisi ('io-push-').
                cursor.execute(
                    """SELECT id FROM employee_inout WHERE source IN ('sheet', 'app')
                       AND nama=%s AND keterangan=%s
                       AND ((waktu_pergi IS NULL AND %s IS NULL) OR waktu_pergi=%s)
                       AND ((waktu_datang IS NULL AND %s IS NULL) OR waktu_datang=%s)
                       LIMIT 1""",
                    (row['nama'], row['keterangan'],
                     row['waktu_pergi'], row['waktu_pergi'],
                     row['waktu_datang'], row['waktu_datang']))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """UPDATE employee_inout SET nama=%s, jabatan=%s, pergi=%s,
                           waktu_pergi=%s, datang=%s, waktu_datang=%s, keterangan=%s
                           WHERE id=%s""",
                        (row['nama'], row['jabatan'], row['pergi'], row['waktu_pergi'],
                         row['datang'], row['waktu_datang'], row['keterangan'],
                         existing['id']))
                    updated += 1
                else:
                    push_uid = ('io-push-' + hashlib.md5('|'.join(
                        [row['nama'], row['waktu_pergi'] or '',
                         row['waktu_datang'] or '', row['keterangan']]
                    ).encode('utf-8')).hexdigest()[:32])
                    cursor.execute(
                        """INSERT INTO employee_inout
                           (source_uid, nama, jabatan, pergi, waktu_pergi, datang,
                            waktu_datang, keterangan, source, locked)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'sheet',0)""",
                        (push_uid, row['nama'], row['jabatan'], row['pergi'],
                         row['waktu_pergi'], row['datang'], row['waktu_datang'],
                         row['keterangan']))
                    added += 1
        return {'added': added, 'updated': updated, 'skipped': skipped}
    finally:
        cursor.close()


def _verify_webhook_secret(provided):
    """Bandingkan secret via compare_digest (anti timing attack)."""
    expected = _get_webhook_secret()
    if not expected or not provided:
        return False
    return secrets.compare_digest(str(provided), expected)


def _do_sync_both():
    """Sync kedua sheet sekali jalan (applicants + inout) — dipakai
    auto-refresh login & realtime-refresh halaman. Return dict per modul."""
    out = {}
    for m, fn in (('applicants', _do_sync_applicants), ('inout', _do_sync_inout)):
        try:
            out[m] = fn()
            _sync_failures[m] = 0
        except Exception as e:
            _sync_failures[m] += 1
            out[m] = {'error': str(e)[:200]}
    return out


def trigger_receptionist_sync_async(role, full_name, ip=None):
    """Picu sync kedua sheet di background saat login/logout receptionis/admin.
    Debounce 30 detik; gagal diam-diam — auth tidak boleh terganggu."""
    if role not in _TRIGGER_ROLES:
        return
    now = time.time()
    due = [m for m in ('applicants', 'inout')
           if now - _last_trigger[m] >= _DEBOUNCE_MIN_INTERVAL]
    if not due:
        return
    for m in due:
        _last_trigger[m] = now

    def _run():
        for m in due:
            fn = _do_sync_applicants if m == 'applicants' else _do_sync_inout
            try:
                result = fn()
                print(f'[receptionist-sync] auto ({m}, trigger={role}): {result.get("summary")}')
            except Exception as e:
                print(f'[receptionist-sync] auto ({m}, trigger={role}) gagal: {e}')

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f'[receptionist-sync] gagal start thread trigger: {e}')


def start_receptionist_auto_sync(interval=AUTO_SYNC_INTERVAL):
    """Daemon thread: sync kedua sheet tiap `interval` detik (default 30 menit).
    Sync pertama ditunda 60 detik agar startup app tetap cepat."""

    def _loop():
        # Tunda sync pertama — beri jeda startup (schema ensure dulu selesai).
        time.sleep(60)
        while True:
            for m, fn in (('applicants', _do_sync_applicants),
                          ('inout', _do_sync_inout)):
                try:
                    result = fn()
                    _sync_failures[m] = 0
                    print(f'[receptionist-sync] periodik ({m}): {result.get("summary")}')
                except Exception as e:
                    _sync_failures[m] += 1
                    print(f'[receptionist-sync] periodik ({m}) gagal '
                          f'({_sync_failures[m]}x beruntun): {e}')
                    _notify_sync_failure(m, e)
            threading.Event().wait(interval)

    try:
        t = threading.Thread(target=_loop, daemon=True, name='receptionist-auto-sync')
        t.start()
        print(f'[receptionist-sync] Auto-sync thread started (tiap {interval // 60} menit)')
        return t
    except Exception as e:
        print(f'[receptionist-sync] gagal start auto-sync thread: {e}')
        return None


# ================================================================
# ROUTES
# ================================================================

def register_receptionist_routes(app):
    """Endpoint sync sheet + input manual + list in-out (receptionist & admin)."""

    # ---- SYNC: sheet pelamar -> applicants -------------------------------
    @app.route('/api/receptionist/sync/applicants', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_receptionist_sync_applicants():
        try:
            result = _do_sync_applicants()
        except ValueError as ve:
            return jsonify({'status': 'error', 'msg': str(ve)}), 400
        except Exception as fe:
            return jsonify({
                'status': 'error',
                'msg': 'Gagal mengambil data dari Google Sheet pelamar. '
                       'Pastikan sheet di-share "Anyone with the link".',
                'detail': str(fe)[:300],
            }), 502
        log_activity_async(None, 'receptionist_sheet_sync',
                           session.get('user_role', ''),
                           session.get('full_name', session.get('user_name', '')),
                           new_data=result, ip=request.remote_addr)
        return jsonify({'status': 'success', **result})

    # ---- SYNC: sheet in-out -> employee_inout ----------------------------
    @app.route('/api/receptionist/sync/inout', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_receptionist_sync_inout():
        try:
            result = _do_sync_inout()
        except ValueError as ve:
            return jsonify({'status': 'error', 'msg': str(ve)}), 400
        except Exception as fe:
            return jsonify({
                'status': 'error',
                'msg': 'Gagal mengambil data dari Google Sheet In-Out Karyawan. '
                       'Pastikan sheet di-share "Anyone with the link".',
                'detail': str(fe)[:300],
            }), 502
        log_activity_async(None, 'inout_sheet_sync',
                           session.get('user_role', ''),
                           session.get('full_name', session.get('user_name', '')),
                           new_data=result, ip=request.remote_addr)
        return jsonify({'status': 'success', **result})

    # ---- INPUT MANUAL pelamar (form dalam aplikasi, v2.41) ---------------
    @app.route('/api/applicants/manual', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_applicants_manual_add():
        try:
            data = request.get_json(silent=True) or {}
            nama = clean(str(data.get('nama_lengkap', '') or ''))[:150]
            if not nama:
                return jsonify({'status': 'error', 'msg': 'Nama Lengkap wajib diisi'}), 400
            pendidikan = clean(str(data.get('pendidikan', '') or ''))[:100]
            no_hp = clean(str(data.get('no_hp', '') or ''))[:30]
            upline = clean(str(data.get('upline', '') or ''))[:100]
            user_field = clean(str(data.get('user', '') or ''))[:100]
            posisi = clean(str(data.get('posisi', '') or ''))[:100]
            h2_date = clean(str(data.get('h2_date', '') or '')) or None
            jabatan = clean(str(data.get('jabatan', '') or ''))[:100]

            # datetime-local 'YYYY-MM-DDTHH:MM' -> 'YYYY-MM-DD HH:MM:00';
            # kosong = sekarang (paritas form publik: timestamp submit).
            interview_at = clean(str(data.get('interview_at', '') or ''))
            if interview_at:
                try:
                    interview_at = datetime.strptime(
                        interview_at.replace('T', ' ')[:16], '%Y-%m-%d %H:%M'
                    ).strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return jsonify({'status': 'error',
                                    'msg': 'Format tanggal interview tidak valid'}), 400
            else:
                interview_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            display_id = generate_display_id('PLM', conn)
            cursor.execute(
                """INSERT INTO applicants
                   (display_id, nama_lengkap, pendidikan, no_hp, upline, user_field,
                    posisi, interview_at, h2_date, verified_by, verified_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                (display_id, nama, pendidikan, no_hp, upline, user_field,
                 posisi, interview_at, h2_date,
                 session.get('user_name', '')))
            appt_id = cursor.lastrowid
            # v2.42.0: bila diisi jabatan, pelamar langsung dijadikan karyawan —
            # baris in-out aktif (source='registrasi', terkunci) dibuat sekarang.
            inout_id = None
            if jabatan:
                now = datetime.now()
                cursor.execute(
                    "SELECT id FROM employee_inout WHERE nama=%s AND pergi=1 AND datang=0 "
                    "AND DATE(waktu_pergi)=%s ORDER BY id DESC LIMIT 1",
                    (nama, now.strftime('%Y-%m-%d')))
                open_row = cursor.fetchone()
                cursor.execute(
                    """UPDATE applicants SET status='lulus', updated_at=NOW()
                       WHERE id=%s""", (appt_id,))
                if open_row:
                    inout_id = open_row[0]  # kursor non-dictionary → tuple
                else:
                    cursor.execute(
                        """INSERT INTO employee_inout
                           (source_uid, nama, jabatan, pergi, datang, keterangan,
                            source, locked, created_by, created_at, updated_at, applicant_id)
                           VALUES (%s,%s,%s,0,0,%s,'registrasi',1,%s,%s,%s,%s)""",
                        ('io-reg-' + hashlib.md5(
                            f"{display_id}|{nama}".encode('utf-8')).hexdigest()[:32],
                         nama, jabatan, 'Registrasi karyawan baru (input manual)',
                         session.get('user_name', ''), now, now, appt_id))
                    inout_id = cursor.lastrowid
                _log_inout_event(cursor, inout_id, 'registrasi',
                                 {'nama': nama, 'keterangan': 'Registrasi karyawan baru'},
                                 {'applicant_id': appt_id, 'display_id': display_id,
                                  'jabatan': jabatan, 'via': 'manual_add'})
            if user_field:
                cursor.execute('INSERT IGNORE INTO applicant_user_options (name) VALUES (%s)',
                               (user_field,))
            conn.commit()
            cursor.close()
            conn.close()
            log_activity_async(None, 'applicant_manual_add',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'display_id': display_id, 'nama': nama,
                                         'jadikan_karyawan': bool(jabatan)},
                               ip=request.remote_addr)
            return jsonify({
                'status': 'success',
                'msg': (f'Pelamar {nama} tercatat (interview {interview_at[:16]}) '
                        f'dan langsung dijadikan karyawan.' if jabatan else
                        f'Pelamar {nama} tercatat (interview {interview_at[:16]}).'),
                'display_id': display_id,
                'inout_id': inout_id,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- REGISTRASI PELAMAR -> KARYAWAN (v2.42.0) --------------------------
    # Pelamar LULUS dijadikan karyawan: status final + baris in-out aktif
    # (source='registrasi', terkunci) sehingga langsung muncul di daftar
    # Karyawan & bisa langsung dicatat keluar/masuknya oleh resepsionis.
    @app.route('/api/applicants/<int:appt_id>/register-employee', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_applicant_register_employee(appt_id):
        try:
            data = request.get_json(silent=True) or {}
            jabatan = clean(str(data.get('jabatan', '') or ''))[:100]
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applicants WHERE id=%s", (appt_id,))
            appt = cursor.fetchone()
            if not appt:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pelamar tidak ditemukan'}), 404
            if appt['status'] == 'lulus':
                cursor.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': 'Pelamar ini sudah menjadi karyawan'}), 409
            if appt['status'] in ('rejected', 'resigned'):
                cursor.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': f'Pelamar berstatus {appt["status"]} — '
                                       f'ubah status dulu bila memang lulus'}), 409
            nama = appt['nama_lengkap']
            now = datetime.now()
            # Sama hari: apakah sudah ada catatan keluar terbuka utk nama ini?
            cursor.execute(
                "SELECT id FROM employee_inout WHERE nama=%s AND pergi=1 AND datang=0 "
                "AND DATE(waktu_pergi)=%s ORDER BY id DESC LIMIT 1",
                (nama, now.strftime('%Y-%m-%d')))
            open_row = cursor.fetchone()
            cursor.execute(
                """UPDATE applicants SET status='lulus', updated_at=NOW()
                   WHERE id=%s""",
                (appt_id,))
            if open_row:
                inout_id = open_row['id']
            else:
                cursor.execute(
                    """INSERT INTO employee_inout
                       (source_uid, nama, jabatan, pergi, datang, keterangan,
                        source, locked, created_by, created_at, updated_at, applicant_id)
                       VALUES (%s,%s,%s,0,0,%s,'registrasi',1,%s,%s,%s,%s)""",
                    ('io-reg-' + hashlib.md5(
                        f"{appt['display_id']}|{nama}".encode('utf-8')).hexdigest()[:32],
                     nama, jabatan, 'Registrasi karyawan baru (lulus training)',
                     session.get('user_name', ''), now, now, appt_id))
                inout_id = cursor.lastrowid
            _log_inout_event(cursor, inout_id, 'registrasi',
                             {'nama': nama, 'keterangan': 'Registrasi karyawan baru'},
                             {'applicant_id': appt_id, 'display_id': appt['display_id'],
                              'jabatan': jabatan})
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(None, 'applicant_register_employee',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'applicant_id': appt_id, 'display_id': appt['display_id'],
                                         'nama': nama, 'jabatan': jabatan}, ip=request.remote_addr)
            return jsonify({'status': 'success',
                            'msg': f'{nama} terdaftar sebagai karyawan — siap dicatat in-out.',
                            'inout_id': inout_id})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- DAFTAR KARYAWAN (roster, v2.42.0) ---------------------------------
    @app.route('/api/receptionist/employees')
    @role_required(['receptionist', 'admin'])
    def api_receptionist_employees():
        try:
            search = clean(request.args.get('search', ''))
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = EMPLOYEE_ROSTER_SQL
            params = []
            if search:
                sql = ("SELECT * FROM (" + EMPLOYEE_ROSTER_SQL + ") roster "
                       "WHERE nama LIKE %s OR jabatan LIKE %s ORDER BY nama")
                like = f'%{search}%'
                params = [like, like]
            cursor.execute(sql, params)
            roster = cursor.fetchall()
            # Status hari ini: keluar terbuka = masih di luar.
            cursor.execute(
                """SELECT nama FROM employee_inout
                   WHERE pergi=1 AND datang=0 AND DATE(waktu_pergi)=CURDATE()""")
            out_now = {r['nama'] for r in cursor.fetchall()}
            cursor.close(); conn.close()
            data = [{**r, 'di_luar': r['nama'] in out_now} for r in roster]
            return jsonify({'status': 'success', 'data': data,
                            'total': len(data)})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- WEBHOOK PUSH REALTIME (v2.42.0, dipanggil Apps Script) ------------
    @app.route('/api/receptionist/webhook', methods=['POST'])
    def api_receptionist_webhook():
        """Terima push realtime dari Google Apps Script (trigger onEdit).

        Autentikasi: header X-BPF-Token = secret dari system_config
        (tanpa login — Apps Script tidak punya sesi). Payload:
        {"modul": "inout"|"applicants", "rows": [ {...header: nilai...} ]}
        """
        try:
            if not _verify_webhook_secret(request.headers.get('X-BPF-Token', '')):
                return jsonify({'status': 'error', 'msg': 'Token webhook tidak valid'}), 401
            data = request.get_json(silent=True) or {}
            modul = data.get('modul') if data.get('modul') in ('applicants', 'inout') else 'inout'
            rows = data.get('rows') or []

            # Header sheet berubah (v2.42.0): Apps Script mengirim rows kosong
            # + tanda header_changed. Jawab 200 (bukan 400 "rows kosong") agar
            # log Apps Script tetap bersih, lalu jadwalkan sinkron penuh kedua
            # modul di background — sumber kebenaran tetap pull, bukan payload
            # satu baris yang tak lagi cocok dengan header baru.
            if data.get('header_changed') and not rows:

                def _resync_header():
                    try:
                        out = _do_sync_both()
                        print('[receptionist-webhook] header berubah — resync penuh: '
                              + ', '.join(f'{m}={v.get("summary") or v}' for m, v in out.items()))
                    except Exception as e:
                        print(f'[receptionist-webhook] resync pascaperubahan header gagal: {e}')

                try:
                    threading.Thread(target=_resync_header, daemon=True).start()
                    emit_event('receptionist_sync', {
                        'modul': modul,
                        'summary': 'Header sheet berubah — sinkron penuh dijalankan'})
                except Exception as e:
                    print(f'[receptionist-webhook] gagal start resync header: {e}')
                return jsonify({'status': 'success',
                                'msg': 'Header sheet berubah — sinkron penuh dijadwalkan',
                                'header_changed': True})

            if not isinstance(rows, list) or not rows:
                return jsonify({'status': 'error', 'msg': 'rows kosong'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            result = _upsert_webhook_rows(conn, rows, modul)
            conn.commit()
            summary = (f"push realtime {modul}: {result['added']} baru, "
                       f"{result['updated']} diperbarui")
            _set_last_sync(conn, f'{modul}_last_sync', summary)
            conn.close()
            log_activity_async(None, 'receptionist_webhook_push', 'system', 'Google Sheet',
                               new_data={'modul': modul, **result},
                               ip=request.remote_addr)
            # Realtime UI: beri tahu halaman In-Out & Pelamar yang sedang terbuka.
            emit_event('receptionist_sync', {'modul': modul, 'summary': summary})
            return jsonify({'status': 'success', 'msg': summary, **result})
        except Exception as e:
            print(f'[receptionist-webhook] error: {e}')
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500

    # ---- REALTIME SYNC ON-DEMAND (v2.42.0, paritas overtime) ---------------
    @app.route('/api/receptionist/realtime-sync', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_receptionist_realtime_sync():
        """Sinkron kedua sheet sekarang (dipanggil saat halaman dibuka /
        Socket.IO event receptionist_sync diterima) — debounce in-memory."""
        try:
            now = time.time()
            if now - _realtime_state['last_sync'] >= _REALTIME_DEBOUNCE:
                _realtime_state['last_sync'] = now

                def _run():
                    result = _do_sync_both()
                    emit_event('receptionist_sync', {
                        'modul': 'both',
                        'summary': '; '.join(
                            f"{m}: {r.get('summary', r.get('error', 'ok'))}"
                            for m, r in result.items()),
                    })

                try:
                    threading.Thread(target=_run, daemon=True).start()
                except Exception as te:
                    print(f'[receptionist-sync] realtime thread gagal: {te}')
                return jsonify({'status': 'success', 'synced': True})
            return jsonify({'status': 'success', 'synced': False})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- KONFIG WEBHOOK (v2.42.0, admin) -----------------------------------
    @app.route('/api/receptionist/webhook-config', methods=['GET'])
    @role_required(['admin'])
    def api_receptionist_webhook_config_get():
        try:
            secret = _get_webhook_secret()
            return jsonify({'status': 'success', 'secret': secret,
                            'header': 'X-BPF-Token',
                            'url_hint': 'https://<host>:5000/api/receptionist/webhook'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/receptionist/webhook-config', methods=['POST'])
    @role_required(['admin'])
    def api_receptionist_webhook_config_rotate():
        """Rotasi secret webhook — token lama langsung tidak berlaku."""
        try:
            new_secret = secrets.token_urlsafe(32)
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                (WEBHOOK_SECRET_CONFIG_KEY, new_secret))
            conn.commit()
            cursor.close()
            conn.close()
            log_activity_async(None, 'receptionist_webhook_rotate',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'rotated': True}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'secret': new_secret,
                            'msg': 'Secret webhook baru dibuat — perbarui di Apps Script'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- PENGATURAN: URL sumber sheet (v2.41.2, admin) -------------------
    @app.route('/api/receptionist/sheet-urls', methods=['GET'])
    @role_required(['admin'])
    def api_receptionist_sheet_urls_get():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            data = {m: _get_sheet_url(conn, m) for m in ('applicants', 'inout')}
            data['last_sync'] = {
                'applicants': _get_last_sync(conn, 'applicants_last_sync'),
                'inout': _get_last_sync(conn, 'inout_last_sync'),
            }
            conn.close()
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/receptionist/sheet-urls', methods=['POST'])
    @role_required(['admin'])
    def api_receptionist_sheet_urls_set():
        try:
            data = request.get_json(silent=True) or {}
            updates = {m: clean(str(data.get(m, '') or '')).strip()
                       for m in ('applicants', 'inout')}
            for m, url in updates.items():
                if url and not (url.startswith('http://') or url.startswith('https://')):
                    return jsonify({'status': 'error',
                                    'msg': f'URL {m} harus diawali http(s)://'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            for m, url in updates.items():
                if not url:
                    continue
                cursor.execute(
                    "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (SHEET_URL_KEYS[m], url))
            conn.commit()
            cursor.close()
            conn.close()
            log_activity_async(None, 'receptionist_sheet_url_update',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data=updates, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'URL sumber sheet disimpan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/receptionist/test-url', methods=['POST'])
    @role_required(['admin'])
    def api_receptionist_test_url():
        """Uji URL sebelum dipakai: fetch + hitung baris + cek header dikenal."""
        try:
            data = request.get_json(silent=True) or {}
            modul = data.get('modul') if data.get('modul') in ('applicants', 'inout') else 'applicants'
            url = clean(str(data.get('url', '') or '')).strip()
            if not url:
                return jsonify({'status': 'error', 'msg': 'URL wajib diisi'}), 400
            rows = _fetch_sheet_rows(url)
            mapping = APPLICANT_HEADERS if modul == 'applicants' else INOUT_HEADERS
            known = any(_map_headers(r.keys(), mapping) for r in rows[:5])
            sample = ', '.join(list(rows[0].keys())[:6]) if rows else ''
            return jsonify({'status': 'success', 'rows': len(rows),
                            'header_ok': bool(known), 'sample_header': sample})
        except Exception as e:
            return jsonify({'status': 'error', 'detail': str(e)[:200]}), 502

    # ---- MODE: pencatatan in-out (v2.42.0, admin) -------------------------
    @app.route('/api/receptionist/inout-mode', methods=['GET'])
    @role_required(['receptionist', 'admin'])
    def api_inout_mode_get():
        try:
            return jsonify({'status': 'success', 'mode': _inout_mode(),
                            'modes': list(INOUT_MODES)})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/receptionist/inout-mode', methods=['POST'])
    @role_required(['admin'])
    def api_inout_mode_set():
        try:
            data = request.get_json(silent=True) or {}
            mode = clean(str(data.get('mode', '') or '')).lower()
            if mode not in INOUT_MODES:
                return jsonify({'status': 'error',
                                'msg': 'Mode harus sheet atau hybrid'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                (INOUT_MODE_CONFIG_KEY, mode))
            conn.commit()
            cursor.close()
            conn.close()
            log_activity_async(None, 'inout_mode_change',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'mode': mode}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'mode': mode,
                            'msg': f'Mode in-out: {mode}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- LIST: in-out karyawan (sumber app + sheet, v2.42.0) ---------------
    @app.route('/api/receptionist/inout')
    @role_required(['receptionist', 'admin'])
    def api_receptionist_inout_list():
        try:
            date_from = clean(request.args.get('date_from', ''))
            date_to = clean(request.args.get('date_to', ''))
            search = clean(request.args.get('search', ''))
            status = clean(request.args.get('status', ''))
            source = clean(request.args.get('source', ''))
            try:
                limit = min(max(int(request.args.get('limit', 1000) or 1000), 1), 2000)
            except ValueError:
                limit = 1000

            where, params = [], []
            if date_from:
                where.append('DATE(COALESCE(waktu_pergi, waktu_datang)) >= %s')
                params.append(date_from)
            if date_to:
                where.append('DATE(COALESCE(waktu_pergi, waktu_datang)) <= %s')
                params.append(date_to)
            if search:
                where.append('(nama LIKE %s OR jabatan LIKE %s OR keterangan LIKE %s)')
                like = f'%{search}%'
                params.extend([like, like, like])
            if status == 'out':
                where.append('pergi=1 AND datang=0')
            elif status == 'in':
                where.append('datang=1')
            if source in INOUT_SOURCES:
                where.append('source = %s')
                params.append(source)
            where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"""SELECT * FROM employee_inout {where_sql}
                    ORDER BY COALESCE(waktu_pergi, waktu_datang) DESC, id DESC
                    LIMIT %s""", (*params, limit))
            data = []
            for r in cursor.fetchall():
                r = _serialize(r)
                r['locked'] = bool(r.get('locked'))
                r['source'] = r.get('source') or 'sheet'
                data.append(r)
            cursor.execute(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(pergi=1 AND datang=0), 0) AS out_now,
                          COALESCE(SUM(DATE(waktu_pergi)=CURDATE()), 0) AS pergi_today,
                          COALESCE(SUM(DATE(waktu_datang)=CURDATE()), 0) AS datang_today,
                          COALESCE(SUM(DATE(COALESCE(waktu_pergi, waktu_datang))=CURDATE()
                                       AND source<>'sheet'), 0) AS app_today
                   FROM employee_inout""")
            stats = cursor.fetchone() or {}
            cursor.execute(EMPLOYEE_ROSTER_SQL)
            roster = [{'nama': r['nama'], 'jabatan': r['jabatan'] or ''}
                      for r in cursor.fetchall()]
            last_sync = _get_last_sync(conn, 'inout_last_sync')
            # Baca mode SELAGI koneksi masih hidup. Sebelumnya dipanggil setelah
            # conn.close() sehingga query melempar error, _inout_mode()
            # menangkap lewat except dan mengembalikan default 'hybrid' —
            # gejala diam: saat admin set mode 'sheet', UI tetap menampilkan
            # tombol catat padahal backend menolak dengan 403.
            mode = _inout_mode(conn)
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'success',
                'data': data,
                'stats': {
                    'total': int(stats.get('total') or 0),
                    'out_now': int(stats.get('out_now') or 0),
                    'pergi_today': int(stats.get('pergi_today') or 0),
                    'datang_today': int(stats.get('datang_today') or 0),
                    'app_today': int(stats.get('app_today') or 0),
                },
                'roster': roster,
                'mode': mode,
                'last_sync': last_sync,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- CATAT: keluar/masuk langsung dari aplikasi (v2.42.0) -------------
    @app.route('/api/receptionist/inout', methods=['POST'])
    @role_required(['receptionist', 'admin'])
    def api_receptionist_inout_create():
        try:
            if _inout_mode() != 'hybrid':
                return jsonify({'status': 'error',
                                'msg': 'Pencatatan dari aplikasi nonaktif '
                                       '(mode sheet). Minta admin mengaktifkan mode hybrid.'}), 403
            data = request.get_json(silent=True) or {}
            nama = clean(str(data.get('nama', '') or ''))[:100]
            if not nama:
                return jsonify({'status': 'error', 'msg': 'Nama karyawan wajib diisi'}), 400
            jabatan = clean(str(data.get('jabatan', '') or ''))[:100]
            keterangan = clean(str(data.get('keterangan', '') or ''))[:255]
            arah = clean(str(data.get('arah', '') or '')).lower()
            if arah not in ('keluar', 'masuk'):
                return jsonify({'status': 'error',
                                'msg': "Arah harus 'keluar' atau 'masuk'"}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            now = datetime.now()
            # Sama hari: apakah karyawan ini sudah tercatat keluar (belum masuk)?
            cursor.execute(
                "SELECT id FROM employee_inout WHERE nama=%s AND pergi=1 AND datang=0 "
                "AND DATE(waktu_pergi)=%s ORDER BY id DESC LIMIT 1",
                (nama, now.strftime('%Y-%m-%d')))
            open_row = cursor.fetchone()
            if arah == 'keluar':
                if open_row:
                    cursor.close(); conn.close()
                    return jsonify({'status': 'error',
                                    'msg': f'{nama} sudah tercatat keluar hari ini dan belum masuk.'}), 409
                cursor.execute(
                    """INSERT INTO employee_inout
                       (source_uid, nama, jabatan, pergi, waktu_pergi, datang,
                        keterangan, source, locked, created_by, created_at, updated_at)
                       VALUES (%s,%s,%s,1,%s,0,%s,'app',1,%s,%s,%s)""",
                    ('io-app-' + hashlib.md5(
                        f"{nama}|{now}".encode('utf-8')).hexdigest()[:32],
                     nama, jabatan, now, keterangan,
                     session.get('user_name', ''), now, now))
                inout_id = cursor.lastrowid
                event = 'app_keluar'
                row = {'nama': nama, 'keterangan': keterangan}
                _log_inout_event(cursor, inout_id, event, row,
                                 {'arah': 'keluar', 'waktu': now.strftime('%Y-%m-%d %H:%M:%S')})
                conn.commit()
                cursor.close(); conn.close()
                log_activity_async(None, 'inout_app_keluar',
                                   session.get('user_role', ''),
                                   session.get('full_name', session.get('user_name', '')),
                                   new_data={'nama': nama, 'id': inout_id}, ip=request.remote_addr)
                return jsonify({'status': 'success',
                                'msg': f'{nama} tercatat KELUAR ({now.strftime("%H:%M")}). '
                                       f'Jangan lupa catat masuk saat kembali.',
                                'id': inout_id})

            # arah == 'masuk': lengkapi baris keluar yang terbuka, bila ada.
            if open_row:
                cursor.execute(
                    """UPDATE employee_inout SET datang=1, waktu_datang=%s,
                       keterangan=CASE WHEN %s<>'' THEN %s ELSE keterangan END,
                       updated_by=%s, updated_at=%s WHERE id=%s""",
                    (now, keterangan, keterangan,
                     session.get('user_name', ''), now, open_row['id']))
                inout_id = open_row['id']
            else:
                cursor.execute(
                    """INSERT INTO employee_inout
                       (source_uid, nama, jabatan, pergi, datang, waktu_datang,
                        keterangan, source, locked, created_by, created_at, updated_at)
                       VALUES (%s,%s,%s,0,1,%s,%s,'app',1,%s,%s,%s)""",
                    ('io-app-' + hashlib.md5(
                        f"{nama}|{now}".encode('utf-8')).hexdigest()[:32],
                     nama, jabatan, now, keterangan,
                     session.get('user_name', ''), now, now))
                inout_id = cursor.lastrowid
            _log_inout_event(cursor, inout_id, 'app_masuk',
                             {'nama': nama, 'keterangan': keterangan},
                             {'arah': 'masuk', 'waktu': now.strftime('%Y-%m-%d %H:%M:%S'),
                              'menutup_baris_keluar': bool(open_row)})
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(None, 'inout_app_masuk',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'nama': nama, 'id': inout_id}, ip=request.remote_addr)
            return jsonify({'status': 'success',
                            'msg': f'{nama} tercatat MASUK ({now.strftime("%H:%M")}).',
                            'id': inout_id})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- EDIT catatan app (step-up PIN, v2.42.0) ---------------------------
    @app.route('/api/receptionist/inout/<int:inout_id>', methods=['PATCH'])
    @role_required(['receptionist', 'admin'])
    @stepup_required
    def api_receptionist_inout_edit(inout_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM employee_inout WHERE id=%s", (inout_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Catatan tidak ditemukan'}), 404
            if row['source'] == 'sheet' and not row['locked']:
                cursor.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': 'Catatan berasal dari Google Sheet — sumber tetap sheet. '
                                       'Hanya catatan dari aplikasi yang bisa diedit di sini.'}), 409
            fields, params, changes = [], [], {}
            for field, maxlen in (('nama', 100), ('jabatan', 100), ('keterangan', 255)):
                if field in data:
                    val = clean(str(data[field] or ''))[:maxlen]
                    old = row[field] or ''
                    if val != old:
                        changes[field] = {'dari': old, 'menjadi': val}
                    fields.append(f'{field} = %s')
                    params.append(val)
            for field in ('waktu_pergi', 'waktu_datang'):
                if field in data:
                    raw = clean(str(data[field] or ''))
                    try:
                        val = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S') if raw else None
                    except ValueError:
                        cursor.close(); conn.close()
                        return jsonify({'status': 'error',
                                        'msg': f'{field} harus format YYYY-MM-DD HH:MM:SS'}), 400
                    old = _serialize(dict(row)).get(field)
                    if (val.strftime('%Y-%m-%d %H:%M:%S') if val else None) != old:
                        changes[field] = {'dari': old,
                                          'menjadi': val.strftime('%Y-%m-%d %H:%M:%S') if val else None}
                    fields.append(f'{field} = %s')
                    params.append(val)
            if 'pergi' in data:
                fields.append('pergi = %s')
                params.append(1 if data['pergi'] else 0)
            if 'datang' in data:
                fields.append('datang = %s')
                params.append(1 if data['datang'] else 0)
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(session.get('user_name', ''))
            params.append(datetime.now())
            params.append(inout_id)
            cursor.execute("UPDATE employee_inout SET " + ', '.join(fields) +
                           ", updated_by=%s, updated_at=%s WHERE id=%s", params)
            _log_inout_event(cursor, inout_id, 'app_edit', row, {'changes': changes})
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(None, 'inout_app_edit',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'id': inout_id, 'changes': changes}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Catatan diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- HAPUS catatan app (step-up PIN, v2.42.0) --------------------------
    @app.route('/api/receptionist/inout/<int:inout_id>', methods=['DELETE'])
    @role_required(['receptionist', 'admin'])
    @stepup_required
    def api_receptionist_inout_delete(inout_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM employee_inout WHERE id=%s", (inout_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Catatan tidak ditemukan'}), 404
            if row['source'] == 'sheet' and not row['locked']:
                cursor.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': 'Catatan berasal dari Google Sheet — sumber tetap sheet. '
                                       'Hanya catatan dari aplikasi yang bisa dihapus di sini.'}), 409
            snap = _serialize(dict(row))
            cursor.execute("DELETE FROM employee_inout WHERE id=%s", (inout_id,))
            _log_inout_event(cursor, inout_id, 'app_delete', row,
                             {'snapshot': {k: snap.get(k) for k in
                                           ('nama', 'jabatan', 'pergi', 'waktu_pergi',
                                            'datang', 'waktu_datang', 'keterangan', 'source')}})
            conn.commit()
            cursor.close(); conn.close()
            log_activity_async(None, 'inout_app_delete',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'id': inout_id, 'nama': snap.get('nama')},
                               ip=request.remote_addr)
            return jsonify({'status': 'success',
                            'msg': f'Catatan {snap.get("nama") or ""} dihapus (tercatat di audit log)'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- RIWAYAT AUDIT satu catatan (v2.42.0) ------------------------------
    @app.route('/api/receptionist/inout/<int:inout_id>/events')
    @role_required(['receptionist', 'admin'])
    def api_receptionist_inout_events(inout_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, inout_id, event_type, event_at, actor_username,
                          actor_name, actor_role, nama, keterangan, payload_json
                   FROM employee_inout_events WHERE inout_id=%s ORDER BY id DESC""",
                (inout_id,))
            events = [_serialize(e) for e in cursor.fetchall()]
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'data': events})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- LAPORAN harian in-out (PDF resmi, v2.42.0) -------------------------
    @app.route('/api/receptionist/inout/report')
    @role_required(['receptionist', 'admin'])
    def api_receptionist_inout_report():
        try:
            d = clean(request.args.get('date', ''))
            try:
                report_date = datetime.strptime(d, '%Y-%m-%d').date() if d else datetime.now().date()
            except ValueError:
                return jsonify({'status': 'error', 'msg': 'Format tanggal harus YYYY-MM-DD'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT nama, jabatan, pergi, waktu_pergi, datang, waktu_datang,
                          keterangan, source FROM employee_inout
                   WHERE DATE(COALESCE(waktu_pergi, waktu_datang))=%s
                   ORDER BY COALESCE(waktu_pergi, waktu_datang) ASC, nama""",
                (report_date.isoformat(),))
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            from modules.pdf_generator import InOutReportPDF
            pdf = InOutReportPDF()
            pdf.generate(rows, report_date=report_date,
                         generated_by=session.get('full_name', session.get('user_name', '')))
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            response = make_response(buf.read())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = \
                f'attachment; filename=Laporan_InOut_{report_date.isoformat()}.pdf'
            return response
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
