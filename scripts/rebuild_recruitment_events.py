#!/usr/bin/env python3
"""Bangun ulang linimasa rekrutmen dari tabel sumber (idempoten).

Default adalah dry-run: tidak ada commit. Jalankan dengan `--commit` hanya
setelah jumlah event yang akan ditulis sudah diperiksa.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.config import get_db_connection, get_master_connection  # noqa: E402
from modules.recruitment_events import rebuild_events  # noqa: E402


def _applicant_rows():
    """Kumpulkan baris applicants dari semua cabang aktif."""
    master = get_master_connection()
    if master is None:
        return []
    try:
        cur = master.cursor(dictionary=True)
        cur.execute('SELECT code FROM branches WHERE is_active=1')
        codes = [str(r.get('code') or '') for r in (cur.fetchall() or [])]
        cur.close()
    finally:
        master.close()

    rows = []
    for code in codes:
        if not code:
            continue
        conn = get_db_connection(branch_code=code)
        if conn is None:
            print(f'[rebuild-events] cabang {code}: koneksi gagal')
            continue
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT display_id, nik, nama_lengkap, status,
                          verified_at, interview_at, created_at, updated_at
                   FROM applicants"""
            )
            for row in cur.fetchall() or []:
                item = dict(row)
                item['branch_code'] = code
                rows.append(item)
            cur.close()
        except Exception as exc:
            print(f'[rebuild-events] cabang {code}: gagal membaca ({exc})')
        finally:
            conn.close()
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true',
                        help='Tulis event ke DB master (default: dry-run)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Tegaskan mode baca-saja (default)')
    args = parser.parse_args(argv)
    if args.dry_run:
        args.commit = False

    master = get_master_connection()
    if master is None:
        print('[rebuild-events] koneksi master gagal')
        return 1
    try:
        branch_rows = _applicant_rows()
        result = rebuild_events(conn=master, branch_rows=branch_rows,
                                commit=args.commit)
    finally:
        master.close()
    mode = 'commit' if args.commit else 'dry-run'
    print(f'[rebuild-events] {mode}: inserted={result["inserted"]} '
          f'skipped={result["skipped"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
