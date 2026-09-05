#!/usr/bin/env python3
"""Rapikan nama akun driver (v2.19.2).

Mengubah username akun user ber-role `driver` menjadi huruf kecil tanpa spasi
(mis. WICAK → `wicak`) dan full_name menjadi title-case (mis. `Wicak`) agar
konsisten dengan konvensi akun baru dari "Buat Akun Sekaligus".

AMAN untuk driver: identitas driver di sisi server memakai `drivers.name`
(di-UPPER-kan dari sesi), bukan username — jadi mengubah huruf besar/kecil
username TIDAK memutus koneksi akun login dengan data driver.

Idempoten & aman konflik: bila username hasil rapikan sudah dipakai user lain,
akun dilewati (tidak menimpa). Mode kering (--dry-run) menampilkan rencana
tanpa mengubah apa pun.

Jalankan di container web (kredensial dari env compose):
    docker compose exec web python3 scripts/tidy_driver_accounts.py --dry-run
    docker compose exec web python3 scripts/tidy_driver_accounts.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.config import get_db_connection  # noqa: E402


def tidy_username(raw):
    return re.sub(r'[^a-z0-9_.]', '', (raw or '').strip().lower())


def tidy_fullname(raw):
    return (raw or '').strip().title()


def main():
    dry = '--dry-run' in sys.argv
    conn = get_db_connection()
    if not conn:
        print('❌ Database tidak tersedia (cek env DB_HOST/DB_PORT/DB_USER/DB_PASSWORD)')
        return 1
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, username, full_name FROM users WHERE role='driver' ORDER BY id")
    rows = cursor.fetchall()

    # Petakan username hasil rapikan yang sudah dipakai akun LAIN (bukan driver tsb)
    cursor.execute("SELECT username FROM users")
    taken = {r['username'] for r in cursor.fetchall()}

    changed_user = changed_name = skipped = 0
    for r in rows:
        new_u = tidy_username(r['username'])
        new_f = tidy_fullname(r['full_name'])
        if new_u != r['username']:
            if new_u in taken:
                skipped += 1
                print(f"⏭  {r['username']!r} → {new_u!r} dilewati (username sudah dipakai akun lain)")
                continue
            if not dry:
                cursor.execute("UPDATE users SET username=%s WHERE id=%s", (new_u, r['id']))
                taken.add(new_u)
            changed_user += 1
            print(f"🔤 {r['username']!r} → {new_u!r}")
        if new_f and new_f != r['full_name']:
            if not dry:
                cursor.execute("UPDATE users SET full_name=%s WHERE id=%s", (new_f, r['id']))
            changed_name += 1
            print(f"👤 {r['full_name']!r} → {new_f!r}")

    if not dry:
        conn.commit()
    cursor.close()
    conn.close()
    mode = 'DRY-RUN (tidak ada perubahan)' if dry else 'diterapkan'
    print(f'✅ {mode}: {changed_user} username dirapikan, {changed_name} full_name dirapikan, {skipped} dilewati (konflik).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
