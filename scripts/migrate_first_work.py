"""Migrasi data historis Absensi FirstWork dari Google Sheet ke database.

Pemakaian:
    python3 scripts/migrate_first_work.py export.csv            # dry-run (default)
    python3 scripts/migrate_first_work.py export.csv --apply    # tulis ke DB
    python3 scripts/migrate_first_work.py "https://...gviz/tq?tqx=out:csv" --apply

Sumber: ekspor CSV Sheet "Absensi FirstWork (Respons)"
(File > Unduh > CSV), atau URL gviz publik selama Sheet masih dibagikan.

Sifat migrasi:
  - Idempoten: source_uid = hash(timestamp|nik|nama); baris yang sama tidak
    digandakan, hanya diperbarui.
  - Status verifikasi, catatan, dan file KTP lokal TIDAK ditimpa.
  - Dry-run default: semua perubahan dibatalkan (rollback) kecuali `--apply`.
  - Referensi dipetakan ke master `first_work_referrers`; yang belum cocok
    ditandai `referrer_needs_review=1` untuk dikoreksi Traineer/Admin.
"""
import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from modules.config import get_db_connection  # noqa: E402
from modules.first_work_schema import ensure_first_work_schema  # noqa: E402
from modules.routes_first_work import (  # noqa: E402
    _normalize_sheet_row, _referrer_index, _upsert_stage, _upsert_submission,
    resolve_referrer)


def _read_source(source):
    """Return (headers, rows) dari file CSV atau URL gviz."""
    if source.startswith(('http://', 'https://')):
        import requests
        response = requests.get(source, timeout=60,
                                headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        text = response.content.decode('utf-8-sig', errors='replace')
    else:
        with open(source, newline='', encoding='utf-8-sig') as handle:
            text = handle.read()
    table = [row for row in csv.reader(io.StringIO(text))]
    if not table:
        return [], []
    return table[0], table[1:]


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
    if not args:
        print('Pemakaian: python3 scripts/migrate_first_work.py <file.csv|url> [--apply]')
        return 1
    apply_changes = '--apply' in sys.argv[1:]

    headers, rows = _read_source(args[0])
    if not headers:
        print('❌ Header CSV tidak terbaca.')
        return 1
    print(f'📄 Sumber: {len(rows)} baris, {len(headers)} kolom')

    conn = get_db_connection()
    if not conn:
        print('❌ DB tidak tersedia (periksa koneksi/pool).')
        return 1

    try:
        if not ensure_first_work_schema(conn):
            print('⚠️  Skema first_work_* belum siap; migrasi tetap dicoba.')
        referrer_index = _referrer_index(conn)
        stats = {'parsed': 0, 'skipped': 0, 'inserted': 0, 'updated': 0,
                 'invalid_nik': 0, 'needs_review': 0}

        for position, row in enumerate(rows):
            normalized = _normalize_sheet_row(headers, row, position)
            if not normalized:
                stats['skipped'] += 1
                continue
            stats['parsed'] += 1
            if not normalized['nik_valid']:
                stats['invalid_nik'] += 1
            _, _, needs_review = resolve_referrer(
                conn, normalized.get('referensi_raw'), referrer_index)
            if needs_review:
                stats['needs_review'] += 1
            _upsert_stage(conn, normalized)
            stats[_upsert_submission(conn, normalized, referrer_index)] += 1

        if apply_changes:
            conn.commit()
            print('✅ Perubahan disimpan (commit).')
        else:
            conn.rollback()
            print('🧪 Dry-run — perubahan dibatalkan. Jalankan ulang dengan '
                  '--apply untuk menyimpan.')

        print('Ringkasan migrasi:')
        for key in ('parsed', 'inserted', 'updated', 'skipped',
                    'invalid_nik', 'needs_review'):
            print(f'  - {key}: {stats[key]}')
        if stats['needs_review']:
            print('ℹ️  Referensi bertanda ⚠️ dapat dipetakan di '
                  'menu Absensi FirstWork → Referensi & Sync.')
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
