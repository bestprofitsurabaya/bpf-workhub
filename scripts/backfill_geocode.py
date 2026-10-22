#!/usr/bin/env python3
"""Backfill koordinat (lat/lng) untuk appointment lama yang belum ter-geocode.

Menelusuri appointment ber-status scheduled/assigned yang koordinatnya masih
NULL, lalu mengisi dari geocode cache / Nominatim (rate-limited 1 req/detik —
aman untuk puluhan alamat).

Jalankan (di dalam container web):
    docker exec bpf-workhub-web python3 scripts/backfill_geocode.py

Idempotent: hanya memproses baris dengan lat IS NULL — aman dijalankan ulang.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.config import get_db_connection
from modules.geocode import geocode_address


def main():
    conn = get_db_connection()
    if not conn:
        print('❌ Database tidak tersedia')
        return 1
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, display_id, nasabah_name, alamat, appointment_date "
        "FROM appointments "
        "WHERE lat IS NULL AND lng IS NULL AND status IN ('scheduled','assigned') "
        "ORDER BY appointment_date ASC, id ASC")
    rows = cursor.fetchall()
    print(f'Ditemukan {len(rows)} appointment tanpa koordinat.')

    ok = 0
    fail = 0
    for r in rows:
        lat, lng = geocode_address(r['alamat'])
        if lat is not None:
            cursor.execute(
                "UPDATE appointments SET lat=%s, lng=%s, updated_at=NOW() WHERE id=%s",
                (lat, lng, r['id']))
            ok += 1
            print(f'  ✓ {r["display_id"]} {r["nasabah_name"]} '
                  f'({r["appointment_date"]}) -> {lat:.5f},{lng:.5f}')
        else:
            fail += 1
            print(f'  ✗ {r["display_id"]} {r["nasabah_name"]}: koordinat tidak '
                  f'ditemukan — alamat: {r["alamat"]}')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'Selesai: {ok} terisi koordinat, {fail} gagal.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
