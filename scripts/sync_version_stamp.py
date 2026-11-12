#!/usr/bin/env python3
"""Sinkronkan stamp versi ke DB setelah bump versi (v2.104.0).

Dua titik DB yang **tidak** ikut ter-update saat versi kode dinaikkan:

 1. `branches.system_version` (master) — kolom per cabang, tampil di UI
    Pengaturan → Cabang. `check_version_stamps.py --with-db` menuntut nilai
    ini SERAGAM antar cabang (tidak boleh berbeda-beda).
 2. `system_config.system_version` (master) — identitas utama aplikasi,
    tampil di UI Pengaturan → Identitas.

Keduanya diambil dari `IDENTITY_DEFAULTS` (sumber kebenaran di kode) — bukan
versi yang diketik manual — sehingga selalu ikut setiap bump versi. Nilai
identitas lain (nama perusahaan, alamat, telepon) TIDAK disentuh:
`save_company_identity` hanya menulis key yang ada di `values`.

Idempoten — aman dijalankan berulang kali.

Jalankan (di host NAS):
    cd ~/bpf-workhub && docker exec -w /app bpf-workhub-web \
        python3 /app/scripts/sync_version_stamp.py

Verifikasi:
    docker exec -w /app bpf-workhub-web \
        python3 scripts/check_version_stamps.py --with-db
"""
import os
import sys

sys.path.insert(0, os.environ.get('APP_ROOT', '/app'))

from modules import branch_manager as bm  # noqa: E402,F401
from modules.company_identity import IDENTITY_DEFAULTS, save_company_identity  # noqa: E402
from modules.config import get_master_connection  # noqa: E402

target = IDENTITY_DEFAULTS['system_version']


def main():
    conn = get_master_connection()
    if not conn:
        print('GAGAL: koneksi master tidak tersedia')
        return 1
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT code, system_version FROM branches ORDER BY code")
        rows = cur.fetchall() or []
        # Semua baris (aktif & nonaktif) diseragamkan — check stamp menuntut
        # nilai seragam, bukan cuma cabang aktif.
        stale = [r for r in rows if (r.get('system_version') or '') != target]
        if stale:
            cur.execute("UPDATE branches SET system_version=%s", (target,))
            conn.commit()
            print('OK: branches.system_version -> %s (%d baris diperbarui)'
                  % (target, len(stale)))
        else:
            print('OK: branches.system_version sudah %s' % target)
    finally:
        cur.close()
        try:
            conn.close()
        except Exception:
            pass

    # Hanya key versi yang ditulis — identitas lain milik Admin.
    saved = save_company_identity({'system_version': target})
    print('OK: system_config.system_version -> %s' % saved.get('system_version'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
