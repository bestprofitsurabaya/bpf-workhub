"""Backfill ID Fingerprint & ID BPF dari data historis sheet (v2.83.0).

Sumber:
- first_work_submissions.sheet_seq : counter kolom B (header '28161'),
  sudah tersimpan sejak migrasi v2.80.0.
- first_work_sheet_stage.payload_json ('$.sheet_seq2') : counter kolom C
  (header '6495') yang dulu dibuang oleh normalisasi.

Aturan:
- Pemetaan seri -> ID diambil dari system_config 'first_work_id_config'
  (default: Fingerprint = kolom B, BPF = kolom C).
- Hanya mengisi baris yang ID-nya masih kosong — ID yang sudah diatur
  traineer TIDAK ditimpa.
- Counter di-system_config tidak tersentuh di sini; counter tabel
  first_work_id_counters dinaikkan ke nomor tertinggi yang ditemukan.

Pemakaian (di container web):
    python3 scripts/first_work_backfill_ids.py [--dry-run]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config import get_master_connection
from modules.routes_first_work import (
    CONFIG_ID,
    _config_get,
    _config_set,
    _id_counter_set,
    _parse_id_config,
    SERIES_FIELDS,
)


def main():
    dry_run = '--dry-run' in sys.argv
    conn = get_master_connection()
    if not conn:
        print('[backfill-ids] DB tidak tersedia')
        return 1
    try:
        cfg = _parse_id_config(_config_get(conn, CONFIG_ID))
        # Simpan config bila belum ada agar pemetaan eksplisit sejak kini.
        if not _config_get(conn, CONFIG_ID):
            _config_set(conn, CONFIG_ID, json.dumps({
                'fingerprint_series': cfg['fingerprint_series'],
                'bpf_series': cfg['bpf_series'],
            }))
        print(f'[backfill-ids] pemetaan: Fingerprint=seri {cfg["fingerprint_series"]}, '
              f'BPF=seri {cfg["bpf_series"]}')

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT s.id, s.source_uid, s.sheet_seq,
                       s.fingerprint_no, s.bpf_no, t.payload_json
                FROM first_work_submissions s
                LEFT JOIN first_work_sheet_stage t ON t.source_uid = s.source_uid
            """)
            rows = cursor.fetchall() or []
        finally:
            cursor.close()

        fp_series = cfg['fingerprint_series']
        bp_series = cfg['bpf_series']
        fp_field = SERIES_FIELDS[fp_series]
        bp_field = SERIES_FIELDS[bp_series]
        max_seen = {'fingerprint_no': None, 'bpf_no': None}
        stats = {'scanned': len(rows), 'updated': 0, 'skipped_filled': 0,
                 'no_number': 0}

        for row in rows:
            payload = {}
            try:
                payload = json.loads(row.get('payload_json') or '{}')
            except (ValueError, TypeError):
                payload = {}
            # sheet_seq (kolom B) sudah tersimpan di submissions; counter C
            # hanya ada di staging payload.
            available = {
                'sheet_seq1': (row.get('sheet_seq') or
                               str(payload.get('sheet_seq1') or '')).strip(),
                'sheet_seq2': str(payload.get('sheet_seq2') or '').strip(),
            }
            updates, params = [], []
            for column, series, field in (
                    ('fingerprint_no', fp_series, fp_field),
                    ('bpf_no', bp_series, bp_field)):
                if row.get(column) is not None:
                    continue
                text = str(available.get(field) or '').strip()
                if not text.isdigit():
                    stats['no_number'] += 1
                    continue
                value = int(text)
                updates.append(f'{column}=%s')
                params.append(value)
                if max_seen[column] is None or value > max_seen[column]:
                    max_seen[column] = value

            if not updates:
                stats['skipped_filled'] += 1
                continue
            if dry_run:
                stats['updated'] += 1
                continue
            params.append(row['id'])
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'UPDATE first_work_submissions SET ' + ', '.join(updates) +
                    ' WHERE id=%s', params)
            finally:
                cursor.close()
            stats['updated'] += 1

        if not dry_run:
            # Counter lanjut dari nomor tertinggi yang ditemukan.
            for column, series in (('fingerprint_no', fp_series),
                                   ('bpf_no', bp_series)):
                if max_seen[column]:
                    _id_counter_set(conn, series, max_seen[column])
            conn.commit()
            print('[backfill-ids] counter diset: Fingerprint-seri '
                  f'{fp_series} -> {max_seen["fingerprint_no"]}, '
                  f'BPF-seri {bp_series} -> {max_seen["bpf_no"]}')

        print('[backfill-ids] hasil:', json.dumps(stats))
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
