"""Sinkronisasi Google Sheet untuk Receptionist (v2.41.0).

Dua sumber data Google Sheet (paritas pola overtime v2.22 — tombol Refresh
manual, fetch CSV gviz / JSON Apps Script, upsert kunci stabil):

1. **Sheet Pelamar** — pendaftaran via Google Form lama. Sync menarik baris
   sheet lalu upsert ke tabel `applicants` dengan source_uid =
   'plm-' + md5(nama|tanggal|jam) — STABIL walau posisi baris sheet bergeser.
   Data yang dikelola di aplikasi (status, verifikasi, kehadiran, resign)
   TIDAK tersentuh sync. Input baru ke depan memakai form dalam aplikasi
   (POST /api/applicants/manual).
2. **Sheet In-Out Karyawan** — catatan keluar-masuk karyawan; halaman app
   read-only, sumber tetap sheet. Full-replace ke tabel `employee_inout`
   tiap sync (log harian, tanpa state di app yang harus dijaga).

Role: `receptionist` & `admin`.
"""
import hashlib
import threading
import time
from datetime import datetime

from flask import request, jsonify, session

from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async,
                             generate_display_id)
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
                ('receptionist_inout_sheet_url', DEFAULT_INOUT_SHEET_URL)):
            try:
                cursor.execute(
                    'INSERT IGNORE INTO system_config (config_key, config_value) '
                    'VALUES (%s, %s)', (key, default))
            except Exception as e:
                print(f'[receptionist-schema] seed {key}: {e}')
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


def _parse_dt_parts(date_raw, time_raw):
    """'9/14/2026' + '6:53:19 AM' -> '2026-09-14 06:53:00' atau None."""
    d = parse_date_mdy(date_raw)
    if not d:
        return None
    jam = parse_time_12h(time_raw) or parse_time_any(time_raw) or '00:00'
    return f'{d} {jam}:00'


def _parse_full_dt(raw):
    """'5/1/2026 9:56:16' -> '2026-05-01 09:56:00' atau None."""
    raw = clean(str(raw or ''))
    if not raw:
        return None
    parts = raw.split(None, 1)
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ''
    d = parse_date_mdy(date_part)
    if not d:
        return None
    jam = parse_time_any(time_part) or '00:00'
    return f'{d} {jam}:00'


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
                cursor.execute(
                    """UPDATE applicants SET
                       nama_lengkap=%s, pendidikan=%s, no_hp=%s, upline=%s,
                       user_field=%s, posisi=%s, interview_at=%s, h2_date=%s, sheet_row=%s
                       WHERE id=%s""",
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
    """Tarik sheet in-out lalu full-replace `employee_inout`.

    Full-replace disengaja: sheet = sumber kebenaran, app hanya membaca.
    Return dict {'replaced', 'skipped', 'total_rows', 'summary'}.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB error')
    try:
        rows = _fetch_sheet_rows(_get_sheet_url(conn, 'inout'))
        cursor = conn.cursor()
        cursor.execute('DELETE FROM employee_inout')
        replaced = skipped = 0
        for n, r in enumerate(rows):
            idx = _map_headers(r.keys(), INOUT_HEADERS)
            row = normalize_inout_row(r, idx, n)
            if not row:
                skipped += 1
                continue
            cursor.execute(
                """INSERT IGNORE INTO employee_inout
                   (source_uid, sheet_row, nama, jabatan, pergi, waktu_pergi,
                    datang, waktu_datang, keterangan)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (row['uid'], n + 1, row['nama'], row['jabatan'], row['pergi'],
                 row['waktu_pergi'], row['datang'], row['waktu_datang'],
                 row['keterangan']))
            if cursor.rowcount == 1:
                replaced += 1
            else:
                skipped += 1
        conn.commit()
        cursor.close()
        result = {'replaced': replaced, 'skipped': skipped, 'total_rows': len(rows)}
        summary = f"{result['replaced']} baris tersinkron (dari {result['total_rows']} baris sheet)"
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
                    print(f'[receptionist-sync] periodik ({m}): {result.get("summary")}')
                except Exception as e:
                    print(f'[receptionist-sync] periodik ({m}) gagal: {e}')
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
            if user_field:
                cursor.execute('INSERT IGNORE INTO applicant_user_options (name) VALUES (%s)',
                               (user_field,))
            conn.commit()
            cursor.close()
            conn.close()
            log_activity_async(None, 'applicant_manual_add',
                               session.get('user_role', ''),
                               session.get('full_name', session.get('user_name', '')),
                               new_data={'display_id': display_id, 'nama': nama},
                               ip=request.remote_addr)
            return jsonify({
                'status': 'success',
                'msg': f'Pelamar {nama} tercatat (interview {interview_at[:16]}).',
                'display_id': display_id,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---- LIST: in-out karyawan (read-only) --------------------------------
    @app.route('/api/receptionist/inout')
    @role_required(['receptionist', 'admin'])
    def api_receptionist_inout_list():
        try:
            date_from = clean(request.args.get('date_from', ''))
            date_to = clean(request.args.get('date_to', ''))
            search = clean(request.args.get('search', ''))
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
            where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"""SELECT * FROM employee_inout {where_sql}
                    ORDER BY COALESCE(waktu_pergi, waktu_datang) DESC, id DESC
                    LIMIT %s""", (*params, limit))
            data = [_serialize(r) for r in cursor.fetchall()]
            cursor.execute(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(pergi=1 AND datang=0), 0) AS out_now,
                          COALESCE(SUM(DATE(waktu_pergi)=CURDATE()), 0) AS pergi_today,
                          COALESCE(SUM(DATE(waktu_datang)=CURDATE()), 0) AS datang_today
                   FROM employee_inout""")
            stats = cursor.fetchone() or {}
            last_sync = _get_last_sync(conn, 'inout_last_sync')
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
                },
                'last_sync': last_sync,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
