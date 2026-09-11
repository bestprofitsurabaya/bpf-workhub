#!/usr/bin/env python3
"""Koreksi one-off typo tahun pada data overtime (11 Sep 2026).

Baris ber-tahun tak masuk akal (1921/2004/2029/2033/2096/2923/1926) adalah
typo input Google Form — bulan & tanggal masuk akal, hanya tahunnya salah.
Koreksi: tahun diarahkan ke tahun `submitted_at` baris tsb (MM-DD dipertahankan;
bila tanggal hasil koreksi > submitted_at + 1 hari, mundur 1 tahun — antisipasi
pengajuan lewat tengah malam seperti kasus 1921-09-22 → submitted 23 Sep).

Guard keamanan:
  - UPDATE selalu ber-syarat `AND tanggal=%s` (nilai lama) → gagal aman bila
    baris sudah diubah orang lain / sheet sudah dikoreksi.
  - Idempoten: baris yang tahunnya sudah benar tidak masuk daftar lagi.
  - Jejak audit `overtime_update` (old_data/new_data snapshot) — semantik sama
    dengan endpoint PATCH /api/overtime/<modul>/<id> (✏️ Edit UI GA HR).

Cara pakai (di container bbm_web):
    python3 /tmp/repair_overtime_year_typos.py           # dry-run (default)
    python3 /tmp/repair_overtime_year_typos.py --apply   # eksekusi + audit

Perhatian: full sync (🔄 Refresh) memakai ON DUPLICATE KEY UPDATE
tanggal=VALUES(tanggal) — nilai SALAH di sheet akan menimpa koreksi ini.
Koreksi sumber di Google Sheet (kolom 'Tanggal Overtime' / 'Tanggal') agar
permanen; baris sheet yang dikoreksi akan tertarik otomatis oleh sync.
"""

import argparse
import datetime
import json
import sys

sys.path.insert(0, '/app')

from modules.config import get_db_connection  # noqa: E402
from modules.helpers import log_activity_async  # noqa: E402

# Tahun tak masuk akal: sebelum sheet berumur (2015) atau lebih dari 1 tahun
# di masa depan relatif thn sekarang.
MIN_YEAR, MAX_YEAR = 2015, datetime.date.today().year + 1

ACTOR = ('system', 'repair_overtime_year_typos (setara ✏️ Edit GA HR)')


def target_rows(cur, table):
    cur.execute(
        f"SELECT id, display_id, nama, tanggal, submitted_at FROM {table} "
        f"WHERE YEAR(tanggal) < %s OR YEAR(tanggal) > %s ORDER BY id",
        (MIN_YEAR, MAX_YEAR))
    return cur.fetchall()


def corrected_date(row):
    """Tahun submitted_at + MM-DD lama; mundur 1 tahun bila terlalu maju."""
    sub = row['submitted_at']
    old = row['tanggal']
    candidate = old.replace(year=sub.year)
    if candidate > sub.date() + datetime.timedelta(days=1):
        candidate = candidate.replace(year=sub.year - 1)
    return candidate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='Eksekusi koreksi (default: dry-run)')
    args = ap.parse_args()

    conn = get_db_connection()
    if not conn:
        print('FATAL: DB tidak terjangkau')
        return 1
    cur = conn.cursor(dictionary=True)

    plan = []
    for table, modul in (('overtime_driver', 'driver'),
                         ('overtime_ob_security', 'ob')):
        for row in target_rows(cur, table):
            new_date = corrected_date(row)
            if new_date != row['tanggal']:
                plan.append((table, modul, row, new_date))

    print(f'Baris terdeteksi butuh koreksi: {len(plan)}')
    for table, modul, row, new_date in plan:
        print(f"  [{modul}] id={row['id']} {row['display_id']} "
              f"{row['nama'][:28]:28} {row['tanggal']} -> {new_date} "
              f"(submitted {row['submitted_at']})")

    if not args.apply:
        print('\nDRY-RUN — tidak ada perubahan. Jalankan ulang dgn --apply.')
        cur.close()
        conn.close()
        return 0

    changed = 0
    for table, modul, row, new_date in plan:
        cur.execute(
            f"UPDATE {table} SET tanggal=%s WHERE id=%s AND tanggal=%s",
            (new_date, row['id'], row['tanggal']))
        if cur.rowcount != 1:
            print(f"  ⚠️ LEWATI id={row['id']} — baris berubah sejak census "
                  f"(rowcount={cur.rowcount})")
            continue
        changed += 1
        log_activity_async(
            None, 'overtime_update', ACTOR[0], ACTOR[1],
            old_data={'id': row['id'], 'modul': modul,
                      'display_id': row['display_id'], 'tanggal': str(row['tanggal']),
                      'alasan': 'typo tahun input form (sumber: Google Sheet)'},
            new_data={'id': row['id'], 'modul': modul,
                      'display_id': row['display_id'],
                      'changes': {'tanggal': str(new_date)},
                      'note': 'repair_overtime_year_typos.py --apply'},
            branch_code=None)

    conn.commit()
    print(f'\nSelesai: {changed} baris dikoreksi + jejak audit '
          f"'overtime_update' tercatat (old_data/new_data snapshot).")
    print('⚠️ Jangan lupa koreksi sumbernya di Google Sheet — full sync akan '
          'menimpa tanggal dari sheet (ON DUPLICATE KEY UPDATE tanggal).')
    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
