"""Sistem Overtime (v2.22) — GA HR.

Dua modul overtime:
1. **Overtime DRIVER** — data berasal dari Google Sheet read-only (diisi Google
   Form lama). GA HR menekan tombol "Refresh" → server mengambil CSV/JSON dari
   URL sumber (system_config.overtime_driver_sheet_url) lalu upsert ke tabel
   `overtime_driver`. URL default = CSV export sheet (publik). Bila sheet
   private, GA HR mengganti URL dengan Google Apps Script Web App (cukup
   akun Google mana pun yang SUDAH punya akses ke sheet — termasuk view/read-
   only — deploy script standalone; sheet tetap private, hasil JSON publik).
2. **Overtime OB & SECURITY** — data dimigrasi penuh dari sheet lama (546 baris)
   + form publik baru (tanpa login) dengan dropdown Posisi & Nama.

Role: `ga_hr` (halaman sendiri) & `admin`.
"""
import csv
import io
import time
import hashlib
import requests
from datetime import datetime, date, timedelta

from flask import request, jsonify, make_response
from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async,
                             generate_display_id, production_pool_executor)
from modules.overtime_helpers import (clean, map_headers, parse_date_mdy,
                                      parse_time_12h, parse_submitted_at,
                                      parse_date_any, parse_time_any,
                                      parse_submitted_at_any,
                                      normalize_name, guess_position,
                                      normalize_driver_row)
from modules.overtime_shared import (
    validate_overtime_data, build_insert_sql, build_insert_params,
    serialize_overtime_row, get_display_prefix, make_source_uid, POSITIONS
)
from modules.pdf_generator import OvertimeReportPDF

POSITIONS = ('OB', 'Security')

# Tabel & kolom yang boleh diedit/dihapus GA HR (v2.22.1) — didefinisikan di
# level modul agar bisa diuji & dipakai ulang.
_OT_TABLES = {'driver': 'overtime_driver', 'ob': 'overtime_ob_security'}
_OT_COLUMNS = {
    'driver': ('nama', 'no_kendaraan', 'tanggal', 'waktu_mulai', 'waktu_selesai',
               'keterangan', 'broker', 'manager', 'email'),
    'ob': ('nama', 'posisi', 'tanggal', 'waktu_mulai', 'waktu_selesai',
           'keterangan', 'email'),
}

# Rate limit form publik: maks 10 submit / 10 menit per IP (anti spam).
_SUBMIT_MAX = 10
_SUBMIT_WINDOW = 600
_submit_log = {}

# Upload directory for overtime photos
import os
_FOTO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'overtime')
os.makedirs(_FOTO_DIR, exist_ok=True)


def _save_overtime_foto(b64_data, display_id, label):
    """Save base64 photo to disk, return URL path.
    b64_data: data URL string (e.g. 'data:image/jpeg;base64,...') or empty.
    label: 'mulai' or 'selesai'.
    Returns: relative URL path or empty string.
    """
    if not b64_data or not b64_data.startswith('data:image'):
        return ''
    # Block SVG to prevent stored XSS via <script> in images.
    if 'image/svg' in b64_data[:50].lower():
        print('[overtime-foto] SVG upload blocked (XSS risk)')
        return ''
    try:
        import base64
        # Parse data URL: data:image/jpeg;base64,<data>
        header, data = b64_data.split(',', 1)
        ext = 'jpg'
        if 'png' in header:
            ext = 'png'
        elif 'webp' in header:
            ext = 'webp'
        # Sanitize display_id to prevent path traversal.
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', display_id)
        filename = f"{safe_id}_{label}.{ext}"
        filepath = os.path.join(_FOTO_DIR, filename)
        decoded = base64.b64decode(data)
        # Max 5MB decoded.
        if len(decoded) > 5_000_000:
            print(f'[overtime-foto] Photo too large ({len(decoded)} bytes)')
            return ''
        with open(filepath, 'wb') as f:
            f.write(decoded)
        return f"/uploads/overtime/{filename}"
    except Exception as e:
        print(f"[overtime-foto] Error saving {label}: {e}")
        return ''


def _cleanup_old_photos(max_age_days=180):
    """Hapus foto overtime yang lebih lama dari max_age_days (default 180 hari = 6 bulan).
    Return dict: {'deleted': int, 'errors': int}.
    Bisa dipanggil dari cron, scheduler, atau endpoint manual.
    """
    deleted = errors = 0
    if not os.path.isdir(_FOTO_DIR):
        return {'deleted': 0, 'errors': 0}
    cutoff = datetime.now() - timedelta(days=max_age_days)
    try:
        for fname in os.listdir(_FOTO_DIR):
            fpath = os.path.join(_FOTO_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    os.remove(fpath)
                    deleted += 1
            except Exception as e:
                print(f"[overtime-cleanup] Error deleting {fpath}: {e}")
                errors += 1
    except Exception as e:
        print(f"[overtime-cleanup] Error listing {_FOTO_DIR}: {e}")
        errors += 1
    if deleted > 0:
        print(f"[overtime-cleanup] Deleted {deleted} old photos ({errors} errors)")
    return {'deleted': deleted, 'errors': errors}


def _serialize(row):
    row = dict(row)
    for k, v in row.items():
        if isinstance(v, datetime):
            row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(v, date):
            row[k] = v.isoformat()
    return row


def _rate_ok(ip):
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
        'username': session_user('user_name', ''),
        'full_name': session_user('full_name', session_user('user_name', '')),
        'role': session_user('user_role', ''),
    }


def session_user(key, default=None):
    try:
        from flask import session
        return session.get(key, default)
    except Exception:
        return default


def _parse_date_filter(value, label):
    """YYYY-MM-DD -> date atau ValueError."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} harus format YYYY-MM-DD')


def _get_sheet_url(conn, modul='driver'):
    """URL sumber sheet dari system_config (driver atau ob)."""
    key = 'overtime_driver_sheet_url' if modul == 'driver' else 'overtime_ob_sheet_url'
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT config_value FROM system_config WHERE config_key=%s", (key,))
    row = cursor.fetchone()
    cursor.close()
    return (row['config_value'] if row and row.get('config_value') else '').strip()


def _set_refresh_meta(conn, summary, modul='driver'):
    """Catat metadata refresh terakhir (waktu + ringkasan)."""
    key = 'overtime_driver_last_refresh' if modul == 'driver' else 'overtime_ob_last_refresh'
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
        (key,
         f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {summary}"))
    conn.commit()
    cursor.close()


# Auto-refresh saat login/logout (v2.22.1): sinkronisasi sheet Driver dijalankan
# di background (fire-and-forget) supaya login tetap cepat. Debounce 30 detik
# mencegah spam ke Google Apps Script bila user login/logout berulang cepat.
_last_auto_refresh = {'ts': 0.0}
_AUTO_REFRESH_MIN_INTERVAL = 30  # detik


def _do_refresh_driver(full_sync=False):
    """Jalankan sinkronisasi sheet Driver. Raise bila gagal.

    Mode incremental (default): hanya ambil data baru sejak refresh terakhir.
    Mode full_sync: ambil semua data (dipakai tombol Refresh manual).

    Dipakai bersama oleh endpoint Refresh (GA HR) dan auto-refresh login/logout.
    Return dict hasil: {'added', 'updated', 'skipped', 'total_rows', 'summary', 'mode'}.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB error')
    try:
        url = _get_sheet_url(conn)
        if not url:
            raise ValueError('URL sumber sheet belum diatur. Set di Pengaturan Sumber Data.')

        # Tentukan mode: incremental (pakai since) atau full
        since = None
        mode = 'incremental'
        if not full_sync:
            # Cari waktu refresh terakhir
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_value FROM system_config "
                           "WHERE config_key='overtime_driver_last_refresh'")
            row = cursor.fetchone()
            cursor.close()
            if row and row.get('config_value'):
                # Format: '2026-08-19 12:07:53 | 0 baru, ...'
                try:
                    last_ts = row['config_value'].split('|')[0].strip()
                    last_dt = datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S')
                    # Kurangi 1 jam untuk margin keamanan (clock skew)
                    since = (last_dt - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
                except (ValueError, IndexError):
                    pass  # Gagal parse → full sync

        if not since:
            mode = 'full'  # First time atau parse gagal → full sync

        rows = _fetch_sheet_rows(url, since=since)
        result = _upsert_driver_rows(conn, rows)
        result['mode'] = mode
        summary = (f"{mode}: {result['added']} baru, {result['updated']} diperbarui, "
                   f"{result['skipped']} dilewati (dari {result['total_rows']} baris)")
        _set_refresh_meta(conn, summary)
        # v2.22.1: beri tahu GA HR bila ada data overtime DRIVER baru dari sheet
        if result.get('added', 0) > 0:
            try:
                from modules.notifications import push_overtime_notification
                push_overtime_notification(
                    'overtime_new', 'driver_sync',
                    f'{result["added"]} data overtime Driver baru dari Google Sheet',
                    ref_id=None, count=result['added'])
            except Exception as ne:
                print(f"[overtime-notif] {ne}")
        return {'status': 'success', **result, 'summary': summary}
    finally:
        conn.close()


def trigger_driver_refresh_async(role, full_name, ip=None):
    """Auto-refresh sheet Driver di background saat login/logout.

    Hanya untuk role yang melihat data overtime (ga_hr & admin); role lain
    dilewati. Debounce 30 detik agar tidak memukul Google Apps Script berulang
    kali dalam waktu singkat. Gagal diam-diam (dicatat ke stdout) — login/logout
    tidak boleh terganggu oleh error sinkronisasi.
    """
    if role not in ('ga_hr', 'admin'):
        return
    now = time.time()
    if now - _last_auto_refresh['ts'] < _AUTO_REFRESH_MIN_INTERVAL:
        return
    _last_auto_refresh['ts'] = now

    def _run():
        try:
            result = _do_refresh_driver()
            log_activity_async(None, 'overtime_driver_refresh', role, full_name,
                               new_data=result, ip=ip)
        except Exception as e:
            print(f"[overtime-auto-refresh] {e}")

    production_pool_executor.submit(_run)


# Auto-refresh OB/Security (v2.29.6): debounce terpisah dari Driver.
_last_ob_auto_refresh = {'ts': 0.0}


def trigger_ob_refresh_async(role, full_name, ip=None):
    """Auto-refresh sheet OB/Security di background saat login/logout.

    Sama seperti Driver: hanya ga_hr & admin, debounce 30 detik, gagal
    diam-diam agar login/logout tidak terganggu.
    """
    if role not in ('ga_hr', 'admin'):
        return
    now = time.time()
    if now - _last_ob_auto_refresh['ts'] < _AUTO_REFRESH_MIN_INTERVAL:
        return
    _last_ob_auto_refresh['ts'] = now

    def _run():
        try:
            result = _do_refresh_ob()
            log_activity_async(None, 'overtime_ob_refresh', role, full_name,
                               new_data=result, ip=ip)
        except Exception as e:
            print(f"[overtime-auto-refresh-ob] {e}")

    production_pool_executor.submit(_run)


def _check_public_url(url):
    """SSRF protection: hanya izinkan http/https menuju host publik.

    Dilempar ValueError bila scheme aneh atau host berupa IP private/
    loopback/link-local/reserved. Hostname domain dianggap OK (di-resolve
    DNS publik).
    """
    from urllib.parse import urlparse
    import ipaddress
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f'URL scheme tidak valid: {parsed.scheme}')
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f'URL ke private/internal IP tidak diizinkan: {parsed.hostname}')
    except (ValueError, TypeError):
        pass  # hostname is a domain, not IP — OK


def _fetch_sheet_rows(url, since=None):
    """Ambil baris data dari URL sumber. Support CSV (export/gviz) & JSON
    (Google Apps Script Web App: {"rows": [{...}]}).

    Args:
        url: URL sumber data (CSV export atau Apps Script Web App)
        since: ISO datetime string untuk incremental sync (hanya ambil data baru)
               Dokumentasi v2 Apps Script: ?since=2025-08-19T00:00:00
    Return list[dict]."""
    fetch_url = url
    if since:
        separator = '&' if '?' in url else '?'
        fetch_url = f'{url}{separator}since={since}'
    _check_public_url(fetch_url)
    # Retry transien (SSLEOFError/timeout dari Google Apps Script sering terjadi
    # sesaat — v2.29: 3 percobaan dengan backoff 1s/2s).
    # Catatan: redirect WAJIB diikuti. Google Apps Script /exec selalu menjawab
    # 302 dulu ke script.googleusercontent.com; allow_redirects=False membuat
    # body kosong → refresh diam-diam 0 baris (regresi 1963283 — mematikan
    # sinkronisasi Driver & OB). URL akhir tetap dicek SSRF (_check_public_url).
    resp = None
    for attempt in range(3):
        try:
            resp = requests.get(fetch_url, timeout=60,
                                headers={'User-Agent': 'Mozilla/5.0'})
            _check_public_url(resp.url)
            resp.raise_for_status()
            break
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            if attempt == 2:
                raise
            print(f"[overtime-sheet] retry {attempt + 1}/2 ({type(exc).__name__}): {exc}")
            time.sleep(1 + attempt)
    text = resp.content.decode('utf-8-sig', errors='replace')
    stripped = text.lstrip()
    if stripped.startswith('{'):
        data = resp.json()
        rows = data.get('rows') or []
        if not rows:
            return []
        return [{str(k): (v if v is not None else '') for k, v in r.items()} for r in rows]
    # CSV
    reader = csv.DictReader(io.StringIO(text))
    return [{k: (v if v is not None else '') for k, v in r.items()} for r in reader]


def _upsert_driver_rows(conn, rows):
    """Upsert baris sheet ke overtime_driver (kunci: sheet_row = baris sheet).

    Kolom tambahan (v2.22.1): no_kendaraan, broker, manager, doc_url.
    """
    cursor = conn.cursor(dictionary=True)
    added = updated = skipped = 0
    if rows:
        headers = list(rows[0].keys())
        idx = map_headers(headers)
        for n, r in enumerate(rows):
            row = normalize_driver_row(r, headers, idx, n)
            if not row:
                skipped += 1
                continue
            cursor.execute(
                """INSERT INTO overtime_driver
                   (sheet_row, submitted_at, email, nama, tanggal, waktu_mulai,
                    waktu_selesai, keterangan, foto_mulai, foto_selesai, notes,
                    no_kendaraan, broker, manager, doc_url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     submitted_at=VALUES(submitted_at), email=VALUES(email),
                     nama=VALUES(nama), tanggal=VALUES(tanggal),
                     waktu_mulai=VALUES(waktu_mulai), waktu_selesai=VALUES(waktu_selesai),
                     keterangan=VALUES(keterangan), foto_mulai=VALUES(foto_mulai),
                     foto_selesai=VALUES(foto_selesai), notes=VALUES(notes),
                     no_kendaraan=VALUES(no_kendaraan), broker=VALUES(broker),
                     manager=VALUES(manager), doc_url=VALUES(doc_url)""",
                (row['sheet_row'], row['submitted_at'], row['email'],
                 row['nama'], row['tanggal'], row['waktu_mulai'],
                 row['waktu_selesai'], row['keterangan'], row['foto_mulai'],
                 row['foto_selesai'], row['notes'], row['no_kendaraan'],
                 row['broker'], row['manager'], row['doc_url']))
            # rowcount: 1 = insert baru, 2 = update baris lama (MySQL)
            if cursor.rowcount == 1:
                added += 1
            elif cursor.rowcount == 2:
                updated += 1
            else:
                skipped += 1
    conn.commit()
    cursor.close()
    return {'added': added, 'updated': updated, 'skipped': skipped, 'total_rows': len(rows)}


def _upsert_ob_rows(conn, rows):
    """Upsert baris sheet ke overtime_ob_security (kunci: source_uid).

    Kolom: nama, posisi, tanggal, waktu_mulai, waktu_selesai, keterangan,
           foto_mulai, foto_selesai, email.
    """
    cursor = conn.cursor(dictionary=True)
    added = updated = skipped = 0
    if rows:
        headers = list(rows[0].keys())
        idx = map_headers(headers)
        for n, r in enumerate(rows):
            row = _normalize_ob_row(r, headers, idx, n)
            if not row:
                skipped += 1
                continue
            # Kunci stabil per SESI: nama + tanggal + jam-mulai (bukan indeks
            # baris, bukan nama+posisi+tanggal). Idempoten saat refresh ulang
            # & tahan reorder sheet; jam-mulai disertakan agar dua sesi orang
            # yang sama di hari yang sama tidak saling menimpa.
            import hashlib
            digest = hashlib.md5(
                '|'.join([row['nama'], row.get('tanggal', ''),
                          row.get('waktu_mulai', '')]).encode('utf-8')
            ).hexdigest()
            source_uid = 'sheet-' + digest
            # display_id kolom UNIQUE — TIDAK memakai generate_display_id():
            # suffix acaknya cuma 2 digit (~100 kandidat/detik), habis saat
            # batch 600+ baris → guard 500x break → id kembar → INSERT kena
            # duplicate display_id → baris lain TERTIMPA (silent data loss).
            # display_id deterministik dari digest yang sama: sama saat
            # re-sync (update in-place), unik antar sesi, tanpa query tambahan.
            display_id = 'OTL-SH-' + digest[:16]
            cursor.execute(
                """INSERT INTO overtime_ob_security
                   (display_id, nama, posisi, tanggal, waktu_mulai, waktu_selesai,
                    keterangan, foto_mulai, foto_selesai, email, submitted_at,
                    source, source_uid)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sheet',%s)
                   ON DUPLICATE KEY UPDATE
                     nama=VALUES(nama), posisi=VALUES(posisi), tanggal=VALUES(tanggal),
                     waktu_mulai=VALUES(waktu_mulai), waktu_selesai=VALUES(waktu_selesai),
                     keterangan=VALUES(keterangan), foto_mulai=VALUES(foto_mulai),
                     foto_selesai=VALUES(foto_selesai), email=VALUES(email),
                     submitted_at=VALUES(submitted_at),
                     gps_lat=VALUES(gps_lat), gps_lon=VALUES(gps_lon),
                     gps_address=VALUES(gps_address), gps_kelurahan=VALUES(gps_kelurahan),
                     gps_kecamatan=VALUES(gps_kecamatan), gps_kota=VALUES(gps_kota),
                     gps_provinsi=VALUES(gps_provinsi), gps_kode_pos=VALUES(gps_kode_pos)""",
                (display_id, row['nama'], row.get('posisi', 'OB'),
                 row.get('tanggal', ''), row.get('waktu_mulai', ''),
                 row.get('waktu_selesai', ''), row.get('keterangan', ''),
                 row.get('foto_mulai', ''), row.get('foto_selesai', ''),
                 row.get('email', ''), row.get('submitted_at', '') or None,
                 source_uid))
            if cursor.rowcount == 1:
                added += 1
            elif cursor.rowcount == 2:
                updated += 1
            else:
                skipped += 1
    conn.commit()
    cursor.close()
    return {'added': added, 'updated': updated, 'skipped': skipped, 'total_rows': len(rows)}


def _normalize_ob_row(r, headers, idx, n):
    """Normalize satu baris sheet OB/Security ke dict untuk DB.
    Return dict atau None bila data tidak valid.
    """
    def _col(field):
        i = idx.get(field)
        if i is None or i >= len(headers):
            return ''
        val = r.get(headers[i], '') if isinstance(r, dict) else ''
        return clean(str(val)) if val else ''

    nama = _col('nama')
    if not nama:
        return None

    posisi = _col('posisi')
    if posisi not in ('OB', 'Security'):
        # Try to guess
        posisi = guess_position(nama) or 'OB'

    tanggal = _col('tanggal')
    if tanggal:
        tanggal = parse_date_any(tanggal) or parse_date_mdy(tanggal) or tanggal
    # Remove time part if present (e.g. '2026-08-20 00:00:00' → '2026-08-20')
    if tanggal and ' ' in str(tanggal):
        tanggal = str(tanggal).split(' ')[0]

    waktu_mulai = _col('waktu_mulai')
    if waktu_mulai:
        waktu_mulai = (parse_time_12h(waktu_mulai) or parse_time_any(waktu_mulai) or waktu_mulai)[:20]
    waktu_selesai = _col('waktu_selesai')
    if waktu_selesai:
        waktu_selesai = (parse_time_12h(waktu_selesai) or parse_time_any(waktu_selesai) or waktu_selesai)[:20]

    return {
        'nama': nama,
        'posisi': posisi,
        'tanggal': tanggal,
        'waktu_mulai': waktu_mulai,
        'waktu_selesai': waktu_selesai,
        'keterangan': _col('keterangan'),
        'foto_mulai': _col('foto_mulai'),
        'foto_selesai': _col('foto_selesai'),
        'email': _col('email'),
        # Timestamp submit asli Google Form (kolom 'Timestamp' sheet) — dipakai
        # PDF 'TANGGAL FORM' & kolom timestamp detail report. Konversi UTC→WIB.
        'submitted_at': (parse_submitted_at_any(_col('submitted_at')) or ''),
        'display_id': '',
    }


def _do_refresh_ob(full_sync=False):
    """Sinkronisasi sheet OB/Security. Raise bila gagal.
    Return dict: {'added', 'updated', 'skipped', 'total_rows', 'summary', 'mode'}.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB error')
    try:
        url = _get_sheet_url(conn, modul='ob')
        if not url:
            raise ValueError('URL sumber sheet OB/Security belum diatur. Set di Pengaturan Sumber Data.')

        since = None
        mode = 'incremental'
        if not full_sync:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_value FROM system_config "
                           "WHERE config_key='overtime_ob_last_refresh'")
            row = cursor.fetchone()
            cursor.close()
            if row and row.get('config_value'):
                try:
                    last_ts = row['config_value'].split('|')[0].strip()
                    last_dt = datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S')
                    since = (last_dt - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
                except (ValueError, IndexError):
                    pass

        if not since:
            mode = 'full'

        rows = _fetch_sheet_rows(url, since=since)
        result = _upsert_ob_rows(conn, rows)
        result['mode'] = mode
        summary = (f"{mode}: {result['added']} baru, {result['updated']} diperbarui, "
                   f"{result['skipped']} dilewati (dari {result['total_rows']} baris)")
        _set_refresh_meta(conn, summary, modul='ob')
        if result.get('added', 0) > 0:
            try:
                from modules.notifications import push_overtime_notification
                push_overtime_notification(
                    'overtime_new', 'ob_sync',
                    f'{result["added"]} data overtime OB/Security baru dari Google Sheet',
                    ref_id=None, count=result['added'])
            except Exception as ne:
                print(f"[overtime-notif] {ne}")
        return {'status': 'success', **result, 'summary': summary}
    finally:
        conn.close()


def register_overtime_routes(app):

    # ================================================================
    # FORM PUBLIK OB/SECURITY — meta (dropdown) & submit (tanpa login)
    # ================================================================
    @app.route('/api/overtime/form-meta')
    def api_overtime_form_meta():
        """Dropdown Posisi + Nama (dari data yang ada) + keterangan umum."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT DISTINCT nama FROM overtime_ob_security "
                "WHERE nama<>'' ORDER BY nama")
            names = [r['nama'] for r in cursor.fetchall()]
            cursor.execute(
                "SELECT DISTINCT keterangan FROM overtime_ob_security "
                "WHERE keterangan<>'' ORDER BY keterangan LIMIT 100")
            keterangan = [r['keterangan'] for r in cursor.fetchall()]
            cursor.close(); conn.close()
            return jsonify({
                'positions': list(POSITIONS),
                'names': names,
                'keterangan': keterangan,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/overtime', methods=['POST'])
    def api_overtime_submit():
        """Submit overtime OB/Security dari form publik (tanpa login)."""
        try:
            ip = request.remote_addr or '?'
            if not _rate_ok(ip):
                return jsonify({'status': 'error',
                                'msg': 'Terlalu banyak pengiriman dari perangkat ini. '
                                       'Coba lagi beberapa saat.'}), 429
            data = request.get_json(silent=True) or {}

            # Shared validation
            is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
            if not is_valid:
                msg = '; '.join(f'{k}: {v}' for k, v in errors.items())
                return jsonify({'status': 'error', 'msg': msg}), 400

            nama = cleaned['nama']
            posisi = cleaned['posisi']

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            display_id = generate_display_id(get_display_prefix('ob'), conn)
            source_uid = 'form-' + make_source_uid(display_id, nama, posisi)

            # Simpan foto bukti
            cleaned['foto_mulai'] = _save_overtime_foto(cleaned['foto_mulai_b64'], display_id, 'mulai')
            cleaned['foto_selesai'] = _save_overtime_foto(cleaned['foto_selesai_b64'], display_id, 'selesai')

            sql, _ = build_insert_sql('ob')
            params = build_insert_params(display_id, cleaned, source='form', modul='ob', source_uid=source_uid)
            cursor.execute(sql, params)
            conn.commit()

            log_activity_async(None, 'overtime_submit', 'public', nama,
                               new_data={'display_id': display_id, 'posisi': posisi},
                               ip=ip)
            try:
                from modules.notifications import push_overtime_notification
                push_overtime_notification(
                    'overtime_new', 'ob_form',
                    f'{posisi} {nama} mengisi overtime baru — No. {display_id}',
                    ref_id=display_id, count=1)
            except Exception as ne:
                print(f"[overtime-notif] {ne}")
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'display_id': display_id,
                            'msg': f'Overtime {posisi} tercatat! No. {display_id}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # DRIVER — submit overtime dari PWA (login required)
    # ================================================================
    @app.route('/api/overtime/driver/submit', methods=['POST'])
    @role_required(['driver'])
    def api_overtime_driver_submit():
        """Submit overtime Driver dari PWA (perlu login driver)."""
        try:
            ip = request.remote_addr or '?'
            if not _rate_ok(ip):
                return jsonify({'status': 'error',
                                'msg': 'Terlalu banyak pengiriman dari perangkat ini. '
                                       'Coba lagi beberapa saat.'}), 429
            data = request.get_json(silent=True) or {}
            # Driver identity dari session (anti impersonasi)
            # Always override — client must NOT be able to submit as someone else.
            data['nama'] = session.get('full_name', '') or session.get('user_name', '')

            # Shared validation
            is_valid, errors, cleaned = validate_overtime_data(data, modul='driver')
            if not is_valid:
                msg = '; '.join(f'{k}: {v}' for k, v in errors.items())
                return jsonify({'status': 'error', 'msg': msg}), 400

            nama = cleaned['nama']

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            display_id = generate_display_id(get_display_prefix('driver'), conn)

            # Simpan foto bukti
            cleaned['foto_mulai'] = _save_overtime_foto(cleaned['foto_mulai_b64'], display_id, 'mulai')
            cleaned['foto_selesai'] = _save_overtime_foto(cleaned['foto_selesai_b64'], display_id, 'selesai')

            sql, _ = build_insert_sql('driver')
            params = build_insert_params(display_id, cleaned, source='form', modul='driver')
            cursor.execute(sql, params)
            conn.commit()

            log_activity_async(None, 'overtime_driver_submit', 'driver', nama,
                               new_data={'display_id': display_id}, ip=request.remote_addr)
            try:
                from modules.notifications import push_overtime_notification
                push_overtime_notification(
                    'overtime_new', 'driver_form',
                    f'Driver {nama} mengisi overtime — No. {display_id}',
                    ref_id=display_id, count=1)
            except Exception as ne:
                print(f"[overtime-notif] {ne}")
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'display_id': display_id,
                            'msg': f'Overtime Driver tercatat! No. {display_id}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA HR — daftar overtime DRIVER (sheet + form)
    # ================================================================
    @app.route('/api/overtime/driver')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_driver_list():
        try:
            d_from = _parse_date_filter(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date_filter(request.args.get('date_to'), 'Tanggal sampai')
            search = clean(request.args.get('search'))
            nama = clean(request.args.get('nama'))
            source = clean(request.args.get('source'))  # 'sheet' or 'form'
            where, params = [], []
            if d_from:
                where.append('tanggal >= %s'); params.append(d_from.isoformat())
            if d_to:
                where.append('tanggal <= %s'); params.append(d_to.isoformat())
            if search:
                like = f'%{search}%'
                where.append('(nama LIKE %s OR keterangan LIKE %s OR email LIKE %s '
                             'OR no_kendaraan LIKE %s OR broker LIKE %s OR manager LIKE %s)')
                params += [like] * 6
            if nama:
                where.append('nama LIKE %s'); params.append(f'%{nama}%')
            if source in ('sheet', 'form'):
                where.append('source = %s'); params.append(source)

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT * FROM overtime_driver"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY tanggal DESC, id DESC LIMIT 2000"
            cursor.execute(sql, params)
            rows = [_serialize(r) for r in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) c FROM overtime_driver")
            total = cursor.fetchone()['c']
            cursor.close(); conn.close()
            return jsonify({'data': rows, 'total': total})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — refresh sinkronisasi sheet DRIVER
    # ================================================================
    @app.route('/api/overtime/driver/refresh', methods=['POST'])
    @role_required(['ga_hr', 'admin'])
    def api_overtime_driver_refresh():
        try:
            full = request.args.get('full', '0') == '1'
            if not full and request.is_json and request.json:
                full = bool(request.json.get('full'))
            try:
                result = _do_refresh_driver(full_sync=full)
            except ValueError as ve:
                return jsonify({'status': 'error', 'msg': str(ve)}), 400
            except Exception as fe:
                return jsonify({
                    'status': 'error',
                    'msg': 'Gagal mengambil data dari Google Sheet. '
                           'Pastikan sheet di-share "Anyone with the link" ATAU '
                           'URL memakai Google Apps Script Web App (lihat petunjuk).',
                    'detail': str(fe)[:300],
                }), 502
            user = _current_user()
            log_activity_async(None, 'overtime_driver_refresh', user['role'],
                               user['full_name'], new_data=result, ip=request.remote_addr)
            return jsonify(result)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA HR — refresh sinkronisasi sheet OB/SECURITY
    # ================================================================
    @app.route('/api/overtime/ob/refresh', methods=['POST'])
    @role_required(['ga_hr', 'admin'])
    def api_overtime_ob_refresh():
        try:
            full = request.args.get('full', '0') == '1'
            if not full and request.is_json and request.json:
                full = bool(request.json.get('full'))
            try:
                result = _do_refresh_ob(full_sync=full)
            except ValueError as ve:
                return jsonify({'status': 'error', 'msg': str(ve)}), 400
            except Exception as fe:
                return jsonify({
                    'status': 'error',
                    'msg': 'Gagal mengambil data dari Google Sheet OB/Security. '
                           'Pastikan sheet di-share "Anyone with the link" ATAU '
                           'URL memakai Google Apps Script Web App.',
                    'detail': str(fe)[:300],
                }), 502
            user = _current_user()
            log_activity_async(None, 'overtime_ob_refresh', user['role'],
                               user['full_name'], new_data=result, ip=request.remote_addr)
            return jsonify(result)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA HR — daftar overtime OB/SECURITY (migrasi + form publik)
    # ================================================================
    @app.route('/api/overtime/ob-security')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_ob_list():
        try:
            d_from = _parse_date_filter(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date_filter(request.args.get('date_to'), 'Tanggal sampai')
            search = clean(request.args.get('search'))
            posisi = clean(request.args.get('posisi'))
            nama = clean(request.args.get('nama'))
            source = clean(request.args.get('source'))  # 'sheet' | 'form' | 'migrasi'
            where, params = [], []
            if d_from:
                where.append('tanggal >= %s'); params.append(d_from.isoformat())
            if d_to:
                where.append('tanggal <= %s'); params.append(d_to.isoformat())
            if search:
                like = f'%{search}%'
                where.append('(nama LIKE %s OR keterangan LIKE %s OR display_id LIKE %s)')
                params += [like] * 3
            if posisi in POSITIONS:
                where.append('posisi = %s'); params.append(posisi)
            if nama:
                where.append('nama LIKE %s'); params.append(f'%{nama}%')
            if source in ('sheet', 'form', 'migrasi'):
                where.append('source = %s'); params.append(source)

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT * FROM overtime_ob_security"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY tanggal DESC, id DESC LIMIT 2000"
            cursor.execute(sql, params)
            rows = [_serialize(r) for r in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) c FROM overtime_ob_security")
            total = cursor.fetchone()['c']
            cursor.close(); conn.close()
            return jsonify({'data': rows, 'total': total})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — laporan PDF resmi (Driver / OB-Security) + TTD GA HR
    # ================================================================
    @app.route('/api/overtime/report')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_report():
        try:
            modul = str(request.args.get('modul', 'driver') or '').strip()
            if modul not in ('driver', 'ob'):
                return jsonify({'error': 'Modul harus driver atau ob'}), 400
            d_from = _parse_date_filter(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date_filter(request.args.get('date_to'), 'Tanggal sampai')
            if not d_to and d_from:
                d_to = d_from
            posisi = clean(request.args.get('posisi'))
            nama = clean(request.args.get('nama'))
            source = clean(request.args.get('source'))  # 'sheet' or 'form'
            display_id = clean(request.args.get('display_id'))  # single record

            table = 'overtime_driver' if modul == 'driver' else 'overtime_ob_security'
            where, params = [], []
            if display_id:
                where.append('display_id = %s'); params.append(display_id)
            else:
                if d_from:
                    where.append('tanggal >= %s'); params.append(d_from.isoformat())
                if d_to:
                    where.append('tanggal <= %s'); params.append(d_to.isoformat())
                if posisi in POSITIONS:
                    where.append('posisi = %s'); params.append(posisi)
                if nama:
                    where.append('nama LIKE %s'); params.append(f'%{nama}%')
                if source in ('sheet', 'form', 'migrasi'):
                    where.append('source = %s'); params.append(source)

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = f'SELECT * FROM {table}'
            if where:
                sql += ' WHERE ' + ' AND '.join(where)
            sql += ' ORDER BY tanggal DESC, id DESC LIMIT 3000'
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close(); conn.close()

            date_label = f'{d_from or d_to} s/d {d_to}' if d_from else str(d_to or 'semua')
            if display_id:
                date_label = f'Record: {display_id}'
            filters = {}
            if posisi:
                filters['Posisi'] = posisi
            if nama:
                filters['Nama'] = nama
            if source in ('sheet', 'form'):
                filters['Sumber'] = 'Google Sheet' if source == 'sheet' else 'Aplikasi'
            user_info = _current_user()
            pdf = OvertimeReportPDF()
            pdf.generate(rows, modul=modul, date_label=date_label,
                         filters=filters, generated_by=user_info['full_name'])
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            fname = f'Laporan_Overtime_{modul}_{(d_to or date.today()).isoformat()}.pdf'
            response = make_response(buf.read())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={fname}'
            return response
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — Report Detail per Driver (File 2 format)
    # ================================================================
    @app.route('/api/overtime/detail-report')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_detail_report():
        """Report detail per driver/OB — PDF or Excel.
        Params: nama, date_from, date_to, format (pdf/xlsx), modul (driver|ob)
        """
        try:
            from modules.pdf_generator import OvertimeDetailReportPDF, generate_overtime_detail_excel

            modul = str(request.args.get('modul', 'driver') or '').strip()
            if modul not in ('driver', 'ob'):
                modul = 'driver'

            nama = clean(request.args.get('nama'))
            if not nama:
                return jsonify({'error': 'Parameter nama wajib diisi'}), 400

            d_from = _parse_date_filter(request.args.get('date_from'), 'Tanggal dari')
            d_to = _parse_date_filter(request.args.get('date_to'), 'Tanggal sampai')
            if not d_to and d_from:
                d_to = d_from

            table = _OT_TABLES[modul]
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            where = ['nama LIKE %s']
            params = [f'%{nama}%']
            if d_from:
                where.append('tanggal >= %s'); params.append(d_from.isoformat())
            if d_to:
                where.append('tanggal <= %s'); params.append(d_to.isoformat())
            sql = f"SELECT * FROM {table} WHERE {' AND '.join(where)} ORDER BY tanggal DESC, waktu_mulai DESC, id DESC LIMIT 500"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close(); conn.close()

            if not rows:
                return jsonify({'error': f'Tidak ada data overtime untuk "{nama}"'}), 404

            date_label = f'{d_from or "-"} s/d {d_to or "-"}' if d_from or d_to else 'Semua Periode'
            export_format = request.args.get('format', 'pdf').lower()
            driver_role = 'DRIVER' if modul == 'driver' else ((rows[0].get('posisi') or 'OB/SECURITY').upper() if rows else 'OB/SECURITY')

            if export_format == 'xlsx':
                buf = generate_overtime_detail_excel(rows, driver_name=nama, driver_role=driver_role, date_label=date_label, modul=modul)
                buf.seek(0)
                # Sanitize filename to prevent header injection.
                safe_nama = re.sub(r'[^a-zA-Z0-9_-]', '_', nama)[:50]
                fname = f'Overtime_{safe_nama}_{(d_to or date.today()).isoformat()}.xlsx'
                response = make_response(buf.read())
                response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                response.headers['Content-Disposition'] = f'attachment; filename={fname}'
                return response
            else:
                user_info = _current_user()
                pdf = OvertimeDetailReportPDF()
                pdf.generate(rows, driver_name=nama, driver_role=driver_role,
                             date_label=date_label, generated_by=user_info['full_name'], modul=modul)
                buf = io.BytesIO()
                pdf.output(buf)
                buf.seek(0)
                safe_nama = re.sub(r'[^a-zA-Z0-9_-]', '_', nama)[:50]
                fname = f'Overtime_{safe_nama}_{(d_to or date.today()).isoformat()}.pdf'
                response = make_response(buf.read())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename={fname}'
                return response
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — Cetak Form Permohonan Overtime
    # ================================================================
    @app.route('/api/overtime/form-pdf')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_form_pdf():
        """Generate Formulir Permohonan Overtime PDF untuk satu record.
        Params: id, display_id, modul (driver|ob, default=driver)
        """
        try:
            from modules.pdf_generator import OvertimeFormPDF

            modul = str(request.args.get('modul', 'driver') or '').strip()
            if modul not in ('driver', 'ob'):
                modul = 'driver'

            record_id = request.args.get('id')
            display_id = request.args.get('display_id')
            if not record_id and not display_id:
                return jsonify({'error': 'Parameter id atau display_id wajib diisi'}), 400

            table = 'overtime_driver' if modul == 'driver' else 'overtime_ob_security'
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            if record_id:
                cursor.execute(f'SELECT * FROM {table} WHERE id = %s', (record_id,))
            else:
                cursor.execute(f'SELECT * FROM {table} WHERE display_id = %s', (display_id,))
            row = cursor.fetchone()
            cursor.close(); conn.close()

            if not row:
                return jsonify({'error': 'Data overtime tidak ditemukan'}), 404

            pdf = OvertimeFormPDF()
            pdf.generate(row, modul=modul)
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            pdf_bytes = buf.read()
            fname = f'Form_OT_{modul.upper()}_{row.get("display_id", row.get("id", "unknown"))}.pdf'
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={fname}'
            # v2.35.0 (Tahap 6/6 ISO): catat integritas ke registri (best-effort).
            try:
                from modules.doc_integrity import register_pdf
                doc_no = row.get('display_id') or f'{modul}-id-{row.get("id")}'
                register_pdf(f'ot_form_{modul}', doc_no, pdf_bytes,
                             signer_name=session.get('full_name') or session.get('user_name') or '',
                             signer_role=session.get('user_role') or '',
                             branch_code=session.get('branch_code') or '',
                             filename=fname, meta={'nama': row.get('nama'),
                                                   'tanggal': str(row.get('tanggal') or '')})
            except Exception:
                pass  # registri tidak boleh menggagalkan unduhan PDF
            return response
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — daftar nama unik untuk autocomplete filter
    # ================================================================
    @app.route('/api/overtime/names')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_names():
        """Return distinct names from both tables for autocomplete."""
        try:
            modul = str(request.args.get('modul', '') or '').strip()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            names = set()
            if modul in ('driver', ''):
                cursor.execute('SELECT DISTINCT nama FROM overtime_driver WHERE nama<>\'\' ORDER BY nama')
                names.update(r['nama'] for r in cursor.fetchall())
            if modul in ('ob', ''):
                cursor.execute('SELECT DISTINCT nama FROM overtime_ob_security WHERE nama<>\'\' ORDER BY nama')
                names.update(r['nama'] for r in cursor.fetchall())
            cursor.close(); conn.close()
            return jsonify({'names': sorted(names)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — ringkasan statistik kedua modul
    # ================================================================
    @app.route('/api/overtime/stats')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_stats():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) c FROM overtime_driver")
            driver_total = cursor.fetchone()['c']
            cursor.execute("SELECT posisi, COUNT(*) c FROM overtime_ob_security GROUP BY posisi")
            by_pos = {r['posisi']: r['c'] for r in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) c FROM overtime_ob_security")
            ob_total = cursor.fetchone()['c']
            cursor.execute("SELECT config_value FROM system_config "
                           "WHERE config_key='overtime_driver_last_refresh'")
            lr = cursor.fetchone()
            cursor.execute("SELECT config_value FROM system_config "
                           "WHERE config_key='overtime_ob_last_refresh'")
            ob_lr = cursor.fetchone()
            cursor.close(); conn.close()
            return jsonify({
                'driver': {'total': driver_total,
                           'last_refresh': (lr['config_value'] if lr else 'Belum pernah refresh')},
                'ob_security': {'total': ob_total, 'by_position': by_pos,
                                'last_refresh': (ob_lr['config_value'] if ob_lr else 'Belum pernah refresh')},
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # GA HR — konfigurasi sumber data sheet (Driver + OB/Security)
    # ================================================================
    @app.route('/api/overtime/config')
    @role_required(['ga_hr', 'admin'])
    def api_overtime_config_get():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_key, config_value FROM system_config "
                           "WHERE config_key LIKE 'overtime_%'")
            cfg = {r['config_key']: r['config_value'] for r in cursor.fetchall()}
            cursor.close(); conn.close()
            return jsonify({
                'sheet_url': cfg.get('overtime_driver_sheet_url', ''),
                'last_refresh': cfg.get('overtime_driver_last_refresh', 'Belum pernah refresh'),
                'ob_sheet_url': cfg.get('overtime_ob_sheet_url', ''),
                'ob_last_refresh': cfg.get('overtime_ob_last_refresh', 'Belum pernah refresh'),
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/overtime/config', methods=['PATCH'])
    @role_required(['ga_hr', 'admin'])
    def api_overtime_config_set():
        try:
            data = request.get_json(silent=True) or {}
            modul = clean(data.get('modul', 'driver'))
            if modul not in ('driver', 'ob'):
                modul = 'driver'
            url = clean(data.get('sheet_url'))
            if not url:
                return jsonify({'status': 'error', 'msg': 'URL tidak boleh kosong'}), 400
            if not url.startswith('http://') and not url.startswith('https://'):
                return jsonify({'status': 'error', 'msg': 'URL harus diawali http(s)://'}), 400
            config_key = 'overtime_driver_sheet_url' if modul == 'driver' else 'overtime_ob_sheet_url'
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                (config_key, url[:600]))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'overtime_config', user['role'], user['full_name'],
                               new_data={'modul': modul, 'sheet_url': url[:120]}, ip=request.remote_addr)
            cursor.close(); conn.close()
            label = 'Driver' if modul == 'driver' else 'OB/Security'
            return jsonify({'status': 'success', 'msg': f'URL sumber data {label} diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # GA HR — edit & hapus data overtime (Driver / OB-Security)
    # ================================================================
    def _ot_row(modul, row_id):
        """Ambil satu baris overtime utk keperluan edit/hapus. Return dict/None."""
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {_OT_TABLES[modul]} WHERE id=%s", (row_id,))
        row = cursor.fetchone()
        cursor.close(); conn.close()
        return _serialize(row) if row else None

    @app.route('/api/overtime/<modul>/<int:row_id>', methods=['PATCH'])
    @role_required(['ga_hr', 'admin'])
    def api_overtime_update(modul, row_id):
        try:
            if modul not in _OT_TABLES:
                return jsonify({'status': 'error', 'msg': 'Modul harus driver atau ob'}), 400
            old = _ot_row(modul, row_id)
            if not old:
                return jsonify({'status': 'error', 'msg': 'Data tidak ditemukan'}), 404

            data = request.get_json(silent=True) or {}
            sets, params = [], []
            for col in _OT_COLUMNS[modul]:
                if col not in data:
                    continue
                # Handle None/null values — don't convert to string "None"
                raw = data[col]
                if raw is None:
                    val = ''
                else:
                    val = clean(str(raw))
                if col == 'tanggal':
                    val = parse_date_any(val) or val
                elif col == 'posisi':
                    if val not in POSITIONS:
                        return jsonify({'status': 'error',
                                        'msg': 'Posisi harus OB atau Security'}), 400
                elif col in ('waktu_mulai', 'waktu_selesai'):
                    val = (parse_time_any(val) or val)[:20]
                elif col == 'email':
                    val = val[:150]
                elif col in ('keterangan',):
                    val = val[:500]
                elif col in ('nama', 'broker', 'manager'):
                    val = val[:150]
                elif col == 'no_kendaraan':
                    val = val[:30]
                sets.append(f'{col}=%s'); params.append(val)
            if not sets:
                return jsonify({'status': 'error', 'msg': 'Tidak ada kolom yang diubah'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {_OT_TABLES[modul]} SET {', '.join(sets)} WHERE id=%s",
                params + [row_id])
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'overtime_update', user['role'], user['full_name'],
                               old_data={'id': row_id, 'modul': modul},
                               new_data={'id': row_id, 'modul': modul,
                                         'changes': {c: clean(str(data[c])) for c in _OT_COLUMNS[modul] if c in data}},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Data overtime diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/overtime/<modul>/<int:row_id>', methods=['DELETE'])
    @role_required(['ga_hr', 'admin'])
    def api_overtime_delete(modul, row_id):
        try:
            if modul not in _OT_TABLES:
                return jsonify({'status': 'error', 'msg': 'Modul harus driver atau ob'}), 400
            old = _ot_row(modul, row_id)
            if not old:
                return jsonify({'status': 'error', 'msg': 'Data tidak ditemukan'}), 404
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {_OT_TABLES[modul]} WHERE id=%s", (row_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'overtime_delete', user['role'], user['full_name'],
                               old_data={'id': row_id, 'modul': modul,
                                         'nama': old.get('nama'), 'tanggal': str(old.get('tanggal'))},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Data overtime dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # Admin — cleanup foto overtime (> 6 bulan)
    # ================================================================
    @app.route('/api/overtime/cleanup-photos', methods=['POST'])
    @role_required(['admin'])
    def api_overtime_cleanup_photos():
        """Hapus foto overtime yang lebih lama dari 180 hari (6 bulan).
        Bisa dipanggil manual atau oleh cron job.
        """
        try:
            result = _cleanup_old_photos(max_age_days=180)
            user = _current_user()
            log_activity_async(None, 'overtime_photo_cleanup', user['role'],
                               user['full_name'], new_data=result, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f"{result['deleted']} foto dihapus, {result['errors']} error", **result})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
