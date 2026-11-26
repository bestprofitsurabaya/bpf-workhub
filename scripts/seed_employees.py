#!/usr/bin/env python3
"""Seed idempoten master karyawan dari FirstWork/unitedw dan In-Out lama.

Default dry-run. `--commit` menulis baris baru; putaran kedua tidak mengubah
status karyawan yang sudah dinonaktifkan GA HR.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.config import get_db_connection, get_master_connection  # noqa: E402
from modules.helpers import normalize_nik  # noqa: E402

_COLUMNS = ('employee_no', 'nik', 'nama', 'nama_norm', 'jabatan',
            'branch_code', 'tanggal_masuk', 'source', 'source_uid',
            'case_id', 'needs_nik', 'is_active', 'no_hp',
            'pendidikan_terakhir', 'tempat_lahir', 'tanggal_lahir',
            'jenis_kelamin')


def _norm_name(value):
    return ' '.join(str(value or '').split()).upper()


def _mask(nik):
    text = str(nik or '')
    return ('****' + text[-4:]) if text else '-'


def _next_no(cursor, branch, counter):
    code = str(branch or 'SBY')[:10]
    counter[code] = counter.get(code, 0) + 1
    return f'KRY-{code}-{counter[code]:05d}'


def seed_employees(conn, first_work_rows, inout_names, commit=False):
    """Masukkan karyawan dari tiga sumber; idempoten dan aman diulang."""
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'needs_nik': 0}
    if not conn:
        return stats
    cursor = conn.cursor(dictionary=True)
    counter = {}
    try:
        for row in first_work_rows or []:
            nik = normalize_nik(row.get('nik'))[0]
            if not nik:
                stats['needs_nik'] += 1
            source = ('unitedw' if str(row.get('source') or '') == 'unitedw'
                      else 'firstwork')
            uid = nik or f"fw:{row.get('id') or ''}"
            cursor.execute('SELECT * FROM employees WHERE nik=%s', (nik,)) if nik else None
            existing = cursor.fetchone() if nik else None
            if not existing:
                cursor.execute('SELECT * FROM employees WHERE source=%s AND source_uid=%s',
                               (source, uid))
                existing = cursor.fetchone()
            if existing:
                stats['updated'] += 1
                continue
            values = (
                _next_no(cursor, row.get('branch_code'), counter),
                nik or None, str(row.get('nama') or '')[:150],
                _norm_name(row.get('nama'))[:150], 'Business Consultant',
                str(row.get('branch_code') or 'SBY')[:10],
                str(row.get('submitted_at') or date.today())[:10],
                source, uid, None, 0 if nik else 1, 1,
                str(row.get('no_hp') or '')[:30],
                str(row.get('pendidikan') or row.get('pendidikan_terakhir') or '')[:100],
                str(row.get('tempat_lahir') or '')[:100],
                str(row.get('tanggal_lahir') or '')[:10] or None,
                str(row.get('jenis_kelamin') or '')[:20] or None,
            )
            cursor.execute(
                f"INSERT INTO employees ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(['%s'] * len(_COLUMNS))})", values)
            stats['inserted'] += 1
            print(f'[seed-employees] {source} {_mask(nik)}')

        for row in inout_names or []:
            nama = str(row.get('nama') or '').strip()
            if not nama:
                continue
            branch = str(row.get('branch_code') or 'SBY')[:10]
            uid = f"io:{branch}:{_norm_name(nama)}"
            cursor.execute('SELECT * FROM employees WHERE source=%s AND source_uid=%s',
                           ('inout_legacy', uid))
            if cursor.fetchone():
                stats['updated'] += 1
                continue
            values = (
                _next_no(cursor, branch, counter), None, nama[:150],
                _norm_name(nama)[:150], str(row.get('jabatan') or 'Staf')[:100],
                branch, str(row.get('created_at') or date.today())[:10],
                'inout_legacy', uid, None, 1, 1, '', '', '', None, None,
            )
            cursor.execute(
                f"INSERT INTO employees ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(['%s'] * len(_COLUMNS))})", values)
            stats['inserted'] += 1
            print(f'[seed-employees] inout_legacy {nama[:20]}')
        if commit:
            conn.commit()
    finally:
        cursor.close()
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true', help='Tulis ke DB master')
    parser.add_argument('--dry-run', action='store_true', help='Mode baca-saja (default)')
    args = parser.parse_args(argv)
    if args.dry_run:
        args.commit = False
    master = get_master_connection()
    if not master:
        print('[seed-employees] koneksi master gagal')
        return 1
    try:
        cur = master.cursor(dictionary=True)
        cur.execute('SELECT * FROM first_work_submissions')
        fw_rows = cur.fetchall() or []
        cur.execute('SELECT code FROM branches WHERE is_active=1')
        codes = [str(r.get('code') or '') for r in (cur.fetchall() or [])]
        cur.close()
        inout = []
        for code in codes:
            conn = get_db_connection(branch_code=code)
            if not conn:
                continue
            try:
                c = conn.cursor(dictionary=True)
                c.execute('SELECT DISTINCT nama, jabatan, created_at '
                          'FROM employee_inout')
                for r in c.fetchall() or []:
                    item = dict(r)
                    item['branch_code'] = code
                    inout.append(item)
                c.close()
            finally:
                conn.close()
        result = seed_employees(master, fw_rows, inout, commit=args.commit)
    finally:
        master.close()
    mode = 'commit' if args.commit else 'dry-run'
    print(f'[seed-employees] {mode}: {result}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
