#!/usr/bin/env python3
"""Tautkan pelamar lama tanpa NIK ke CV Online berdasarkan nama + HP.

Default dry-run. `--commit` menulis NIK ke DB cabang, memastikan kasus master,
dan mencatat event `NIK_LINKED` (best-effort). NIK lengkap tidak dicetak.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.config import get_db_connection, get_master_connection  # noqa: E402
from modules.helpers import normalize_nik  # noqa: E402
from modules.recruitment_service import ensure_case  # noqa: E402
from modules.recruitment_events import record_event  # noqa: E402


def _mask(nik):
    text = str(nik or '')
    return ('****' + text[-4:]) if text else '-'


def link_applicants_nik(conn_master, branch_rows, commit=False):
    """Tautkan baris pelamar yang belum punya NIK.

    `branch_rows` adalah daftar dict yang sudah dimuat pemanggil dari DB cabang.
    Fungsi memutakhirkan dict tersebut bila `commit=True` agar pemanggil dapat
    menuliskannya kembali ke DB cabang yang sama.
    """
    result = {'linked': 0, 'ambiguous': 0, 'unlinked': 0}
    if not conn_master:
        return result
    cursor = conn_master.cursor(dictionary=True)
    try:
        for row in branch_rows:
            if normalize_nik(row.get('nik'))[0]:
                continue
            cursor.execute(
                """SELECT nik FROM cv_online_submissions
                   WHERE nama=%s AND no_hp=%s
                   ORDER BY submitted_at DESC LIMIT 2""",
                (row.get('nama_lengkap'), row.get('no_hp')))
            rows = cursor.fetchall() or []
            niks = {normalize_nik(r.get('nik'))[0] for r in rows}
            niks.discard('')
            # Lebih dari satu kecocokan CV = identitas ambigu, walaupun NIK-nya
            # sama — jangan menebak baris mana yang benar.
            if len(rows) > 1:
                row['link_status'] = 'ambiguous'
                result['ambiguous'] += 1
                continue
            if not niks:
                result['unlinked'] += 1
                continue
            nik = niks.pop()
            # Dry-run tetap mengisi dict hasil (untuk laporan'); penulisan ke
            # DB dan event hanya terjadi bila commit=True.
            row['nik'] = nik
            row['nik_source'] = 'backfill'
            row['link_status'] = 'linked'
            if commit:
                try:
                    case_id = ensure_case(nik, row.get('nama_lengkap'),
                                          row.get('branch_code', ''),
                                          source='backfill', conn=conn_master)
                    record_event(case_id, nik, 'NIK_LINKED',
                                 branch_code=row.get('branch_code', ''),
                                 source_module='backfill',
                                 source_id=row.get('display_id', ''),
                                 conn=conn_master)
                except Exception as exc:
                    print(f'[link-nik] gagal membuat kasus: '
                          f'{str(exc)[:160]}')
            result['linked'] += 1
            print(f'[link-nik] {row.get("display_id", "")} → {_mask(nik)}')
    finally:
        cursor.close()
    if commit:
        conn_master.commit()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true',
                        help='Tulis hasil tautan (default: dry-run)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Tegaskan mode baca-saja (default)')
    args = parser.parse_args(argv)
    if args.dry_run:
        args.commit = False

    master = get_master_connection()
    if not master:
        print('[link-nik] koneksi master gagal')
        return 1
    summary = {'linked': 0, 'ambiguous': 0, 'unlinked': 0}
    try:
        cur = master.cursor(dictionary=True)
        cur.execute('SELECT code FROM branches WHERE is_active=1')
        codes = [str(r.get('code') or '') for r in (cur.fetchall() or [])]
        cur.close()
        for code in codes:
            conn = get_db_connection(branch_code=code)
            if not conn:
                continue
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT id, display_id, nama_lengkap, no_hp, nik,
                              link_status FROM applicants
                       WHERE nik IS NULL OR link_status<>'linked'""")
                rows = cur.fetchall() or []
                for row in rows:
                    row['branch_code'] = code
                cur.close()
                part = link_applicants_nik(master, rows, commit=args.commit)
                for key in summary:
                    summary[key] += part[key]
                if args.commit and part['linked']:
                    cur = conn.cursor()
                    for row in rows:
                        if row.get('nik') and row.get('link_status') == 'linked':
                            cur.execute(
                                """UPDATE applicants
                                   SET nik=%s, nik_source='backfill',
                                       linked_at=NOW(), link_status='linked'
                                   WHERE id=%s""",
                                (row['nik'], row['id']))
                    conn.commit()
                    cur.close()
            finally:
                conn.close()
    finally:
        master.close()
    mode = 'commit' if args.commit else 'dry-run'
    print(f'[link-nik] {mode}: linked={summary["linked"]} '
          f'ambiguous={summary["ambiguous"]} unlinked={summary["unlinked"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
