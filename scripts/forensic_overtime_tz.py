"""Forensik zona waktu feed Apps Script overtime (v2.39.2).

Ambil kedua feed (URL dari system_config DB master — persis tombol Refresh),
lalu census format nilai di kolom tanggal/timestamp/jam:

  '2020-12-12T07:08:54.000Z'  → script LAMA (ISO UTC) — server menambah +7
                                jam dgn asumsi sheet WIB; zona lain bergeser.
  '2020-12-12 14:08:54'       → script v2 (wall-clock sesuai zona spreadsheet).

Serta sanitasi: pastikan parser produksi memang menerapkan fallback +7 jam
pada feed ISO UTC (bukan menggeser feed wall-clock).

Output JSON: /tmp/bpf_ot_tz_forensic.json
Jalankan di container: python3 /tmp/forensic_overtime_tz.py
"""
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

# Jalankan di container (/app) maupun dari repo host: kandidat path root
# repo = parent folder scripts/, plus '/app' (cwd container).
_ROOT_CANDIDATES = [
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    '/app',
]
for _root in _ROOT_CANDIDATES:
    if os.path.isdir(os.path.join(_root, 'modules')):
        sys.path.insert(0, _root)

from modules.config import get_db_connection                              # noqa: E402
from modules.overtime_helpers import (normalize_driver_row, map_headers,  # noqa: E402
                                      parse_submitted_at_any,
                                      parse_submitted_at)
from modules.routes_overtime import _normalize_ob_row, _fetch_sheet_rows  # noqa: E402

ISO_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$')
WALL_TS = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
WALL_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
WALL_TIME = re.compile(r'^\d{2}:\d{2}(:\d{2})?$')
EPOCH_1899 = re.compile(r'^1899-12-3[01]T')

TIME_KEYS = ('submitted_at', 'tanggal', 'waktu_mulai', 'waktu_selesai')
URL_KEYS = (('driver', 'overtime_driver_sheet_url'),
            ('ob', 'overtime_ob_sheet_url'))
DB_TABLES = {'driver': 'overtime_driver', 'ob': 'overtime_ob_security'}


def _norm_val(v):
    """Nilai DB/feed → string pembanding (datetime/date → format standar).

    datetime (termasuk tengah malam 00:00:00) → '%Y-%m-%d %H:%M:%S';
    date murni → '%Y-%m-%d'; lainnya str().strip().
    """
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, date):
        return v.strftime('%Y-%m-%d')
    return str(v).strip()


def _row_key(nama, ts):
    return f'{nama}|{ts}'


def bandingkan_db(mod, rows, headers, idx):
    """Paritas jam sheet↔DB: normalisasi feed dgn fungsi produksi, lalu
    bandingkan (tanggal, waktu_mulai, waktu_selesai, submitted_at) per kunci
    vs baris DB. Return dict ringkas.

    Kunci = kunci desain upsert masing-masing modul:
    - driver: nama|submitted_at (source_uid = md5(nama|submitted_at))
    - ob    : nama|tanggal|waktu_mulai (source_uid = md5(nama|tanggal|mulai);
              duplikat pengajuan dgn Timestamp beda di-dedup by design —
              baris TERAKHIR sheet yang menang, persis urutan upsert)
    """
    table = DB_TABLES[mod]
    feed_map = {}
    for n, r in enumerate(rows):
        row = (normalize_driver_row(r, headers, idx, n) if mod == 'driver'
               else _normalize_ob_row(r, headers, idx, n))
        if not row:
            continue
        ts = _norm_val(row.get('submitted_at'))
        if mod == 'driver':
            if not ts:
                continue
            key = _row_key(row['nama'], ts)
        else:
            if not row.get('tanggal'):
                continue
            key = _row_key(row['nama'],
                           f"{_norm_val(row.get('tanggal'))}|{(_norm_val(row.get('waktu_mulai')) or '')[:5]}")
        feed_map[key] = (
            _norm_val(row.get('tanggal')),
            _norm_val(row.get('waktu_mulai'))[:5],
            _norm_val(row.get('waktu_selesai'))[:5],
            ts,
        )

    conn = get_db_connection()
    if not conn:
        return {'error': 'DB tidak terjangkau'}
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT nama, submitted_at, tanggal, waktu_mulai, "
                    f"waktu_selesai FROM {table}")
        db_rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    db_map = {}
    for r in db_rows:
        ts = _norm_val(r.get('submitted_at'))
        if mod == 'driver':
            if not ts:
                continue
            key = _row_key(r['nama'], ts)
        else:
            if not r.get('tanggal'):
                continue
            key = _row_key(r['nama'],
                           f"{_norm_val(r.get('tanggal'))}|{(_norm_val(r.get('waktu_mulai')) or '')[:5]}")
        db_map[key] = (
            _norm_val(r.get('tanggal')),
            _norm_val(r.get('waktu_mulai'))[:5],
            _norm_val(r.get('waktu_selesai'))[:5],
            ts,
        )

    common = set(feed_map) & set(db_map)
    beda = [k for k in common if feed_map[k] != db_map[k]][:10]
    return {
        'feed_valid': len(feed_map), 'db_dgn_ts': len(db_map),
        'cocok_kunci': len(common),
        'hilang_di_db': len(set(feed_map) - set(db_map)),
        'extra_di_db': len(set(db_map) - set(feed_map)),
        'selisih_field': len(beda), 'contoh_selisih': beda,
        'paritas': 'OK' if (common and not beda
                            and not (set(feed_map) - set(db_map))) else 'PERIKSA',
    }


def simulasi_transisi_iso_ke_wallclock(rows, headers, idx, batas=2000):
    """Bukti source_uid STABIL saat feed pindah ke script v2 (wall-clock).

    Untuk tiap baris ber-Timestamp ISO-UTC: submitted_at hasil parser (WIB)
    harus SAMA dgn bila feed mengirim wall-clock WIB yang setara — karena
    parse_submitted_at_any(wall) tanpa offset. UID = md5(nama|submitted_at)
    → tidak berubah → TIDAK ADA duplikat/kehilangan pasca-redeploy.
    """
    i_ts = idx.get('submitted_at')
    if i_ts is None or i_ts >= len(headers):
        return {'error': 'kolom Timestamp tak ditemukan'}
    key = headers[i_ts]
    total = cocok = 0
    contoh = None
    for r in rows:
        s = str(r.get(key, '')).strip()
        if not ISO_UTC.match(s):
            continue
        total += 1
        if total > batas:
            break
        # Wall-clock WIB yang AKAN dikirim script v2 utk momen yang sama:
        utc_naive = datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
        wall = (utc_naive + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
        a = parse_submitted_at_any(s)
        b = parse_submitted_at_any(wall)
        if a == b and b is not None:
            cocok += 1
        elif contoh is None:
            contoh = {'iso': s[:40], 'wall': wall, 'hasil_a': a, 'hasil_b': b}
    return {'diuji': min(total, batas), 'uid_stabil': cocok,
            'ok': total > 0 and cocok == min(total, batas),
            'contoh_gagal': contoh}


def classify(val):
    s = str(val).strip()
    if not s:
        return 'kosong'
    if ISO_UTC.match(s):
        return 'iso_utc'
    if WALL_TS.match(s):
        return 'wall_clock'
    if WALL_DATE.match(s):
        return 'tanggal_wall'
    if WALL_TIME.match(s):
        return 'jam_wall'
    if EPOCH_1899.match(s):
        return 'epoch_1899'
    return 'lain'


def census_feed(rows, headers, idx):
    """Census format nilai kolom waktu — akses via alias map_headers,
    persis cara normalize_driver_row/_normalize_ob_row membaca feed."""
    census, contoh = {}, {}
    for f in TIME_KEYS:
        i = idx.get(f)
        if i is None or i >= len(headers):
            census[f] = {'alias_tak_ditemukan': 1}
            contoh[f] = None
            continue
        raw_key = headers[i]
        c = Counter()
        example = None
        for r in rows:
            k = classify(r.get(raw_key, ''))
            c[k] += 1
            if example is None and k != 'kosong':
                example = f'{raw_key}={str(r.get(raw_key))[:40]}'
        census[f] = dict(c)
        contoh[f] = example
    if any(census.get(f, {}).get('iso_utc', 0) for f in TIME_KEYS):
        verdict = 'SCRIPT_LAMA_ISO_UTC'
    elif any(census.get(f, {}).get('wall_clock', 0) or
             census.get(f, {}).get('jam_wall', 0) or
             census.get(f, {}).get('tanggal_wall', 0) for f in TIME_KEYS):
        verdict = 'SCRIPT_V2_WALLCLOCK'
    else:
        verdict = 'TIDAK_JELAS'
    return census, contoh, verdict


def main():
    conn = get_db_connection()
    if not conn:
        print('FATAL: DB master tidak terjangkau')
        return 1
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT config_key, config_value FROM system_config "
                    "WHERE config_key IN ('overtime_driver_sheet_url', "
                    "'overtime_ob_sheet_url')")
        urls = {r['config_key']: r['config_value'] for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    out, rows_by_mod = {}, {}
    for mod, key in URL_KEYS:
        url = urls.get(key)
        if not url:
            out[mod] = {'error': f'{key} tidak ada di system_config'}
            continue
        rows = _fetch_sheet_rows(url)  # tanpa since = full, tanpa transformasi
        rows_by_mod[mod] = rows
        headers = list(rows[0].keys()) if rows else []
        idx = map_headers(headers)
        census, contoh, verdict = census_feed(rows, headers, idx)
        out[mod] = {'url_tail': url[-20:], 'total_rows': len(rows),
                    'headers_waktu': {f: (headers[idx[f]] if f in idx and idx[f] < len(headers) else None)
                                      for f in TIME_KEYS},
                    'census': census, 'contoh': contoh, 'verdict': verdict,
                    'paritas_db': bandingkan_db(mod, rows, headers, idx),
                    'simulasi_transisi': simulasi_transisi_iso_ke_wallclock(rows, headers, idx)}

    # Sanitasi parser: feed ISO UTC harus tetap dapat fallback +7 (WIB);
    # parser tidak boleh menggeser feed wall-clock.
    try:
        drows = rows_by_mod.get('driver') or []
        dhead = list(drows[0].keys()) if drows else []
        didx = map_headers(dhead) if drows else {}
        _ts_key = dhead[didx['submitted_at']] if 'submitted_at' in didx and didx['submitted_at'] < len(dhead) else 'submitted_at'
        sample = next((str(r.get(_ts_key)).strip() for r in drows
                       if str(r.get(_ts_key, '')).strip()), '')
        if ISO_UTC.match(sample):
            s_any = parse_submitted_at_any(sample)  # jalur parse_iso_dt → WIB
            dt_raw = datetime.strptime(sample[:19], '%Y-%m-%dT%H:%M:%S')
            dt_expected = (dt_raw + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
            out['sanitasi_parser'] = {
                'sample': sample[:40], 'hasil_parser': s_any,
                'ekspektasi_plus7': dt_expected,
                'fallback_plus7_aktif': s_any == dt_expected,
            }
        else:
            wall = next((str(r.get('submitted_at')).strip() for r in drows
                         if WALL_TS.match(str(r.get('submitted_at', '')).strip())), None)
            out['sanitasi_parser'] = {
                'sample': (wall or sample)[:40],
                'catatan': 'feed wall-clock — parser memakai nilai apa adanya (tanpa offset)',
            }
    except Exception as exc:  # pragma: no cover - diagnostik saja
        out['sanitasi_parser'] = {'error': repr(exc)}

    # Pastikan juga normalisasi OB tidak error di feed terbaru (spot-check).
    try:
        orows = rows_by_mod.get('ob') or []
        if orows:
            headers = list(orows[0].keys())
            idx = __import__('modules.routes_overtime',
                             fromlist=['map_headers']).map_headers(headers)
            _normalize_ob_row(orows[0], headers, idx, 0)
            out['sanitasi_normalisasi_ob'] = 'ok'
    except Exception as exc:  # pragma: no cover - diagnostik saja
        out['sanitasi_normalisasi_ob'] = repr(exc)

    with open('/tmp/bpf_ot_tz_forensic.json', 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
