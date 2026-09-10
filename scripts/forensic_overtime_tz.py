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
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, '/app')

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
                    'census': census, 'contoh': contoh, 'verdict': verdict}

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
