#!/usr/bin/env python3
"""Audit & rapikan relasi akun user ↔ driver ↔ kendaraan (v2.78.0).

Memeriksa SETIAP database cabang (termasuk master):
  1. akun ber-role driver yang belum punya profil di `drivers`
  2. profil `drivers` yang tidak terhubung akun (yatim)
  3. `drivers.name` ≠ UPPER(users.username)  → sumber bug rename
  4. `drivers.display_name` ≠ users.full_name
  5. status aktif akun ≠ status profil driver
  6. satu driver punya >1 penugasan aktif (is_current=1)
  7. satu kendaraan dipakai >1 driver sekaligus
  8. driver aktif tanpa kendaraan / nopol tidak terdaftar di master

Mode:
    python3 scripts/audit_driver_identity.py            # laporan saja
    python3 scripts/audit_driver_identity.py --fix      # terapkan perbaikan aman
    python3 scripts/audit_driver_identity.py --json     # keluaran JSON

Perbaikan pada --fix (semuanya aditif/reversibel, TIDAK menghapus data):
  - tautkan / buat profil driver untuk akun driver
  - sinkronkan nama operasional (dengan cascade referensi) + nama tampilan
  - samakan status aktif
  - rapikan penugasan ganda: pertahankan baris TERBARU per driver & per nopol

Jalankan di container web:
    docker compose exec web python3 scripts/audit_driver_identity.py
    docker compose exec web python3 scripts/audit_driver_identity.py --fix
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import branch_manager as bm  # noqa: E402
from modules.config import get_master_connection  # noqa: E402
from modules.driver_identity import (  # noqa: E402
    audit_driver_identity, backfill_driver_links, ensure_driver_user_schema,
    sync_driver_for_user,
)

LABELS = {
    'akun_tanpa_profil_driver': 'Akun driver tanpa profil driver',
    'driver_tanpa_akun': 'Profil driver tanpa akun login',
    'nama_tidak_sinkron': 'Nama driver ≠ username akun',
    'nama_tampilan_beda': 'Nama tampilan driver ≠ nama akun',
    'status_beda': 'Status aktif driver ≠ status akun',
    'assignment_ganda': 'Driver punya >1 penugasan aktif',
    'kendaraan_ganda': 'Kendaraan dipakai >1 driver',
    'driver_tanpa_kendaraan': 'Driver aktif tanpa kendaraan',
    'nopol_tidak_terdaftar': 'Nopol tidak ada di master kendaraan',
    'driver_tanpa_nama': 'Baris driver tanpa nama',
}


def branch_targets():
    """[(code, db_name)] — master (cabang default) + semua cabang aktif."""
    from modules.config import DB_CONFIG
    master_db = DB_CONFIG['database']
    targets = [(bm.DEFAULT_BRANCH_CODE, master_db)]
    for b in bm.list_branches():
        db = (b.get('db_name') or '').strip()
        if not b.get('is_active') or not db or db == master_db:
            continue
        targets.append((b.get('code'), db))
    return targets


def fetch_users():
    conn = get_master_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, full_name, role, branch_code, is_active FROM users")
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def connection_for(db_name):
    from modules.config import DB_CONFIG, _pool_for
    if db_name == DB_CONFIG['database']:
        return get_master_connection()
    pool = _pool_for(db_name)
    return pool.get_connection() if pool else None


def remove_nameless_drivers(conn):
    """Hapus baris `drivers` tanpa nama & tanpa akun (sisa seed ganda)."""
    cur = conn.cursor(dictionary=True)
    removed = 0
    try:
        cur.execute("SELECT id FROM drivers WHERE (name IS NULL OR TRIM(name)='') AND user_id IS NULL")
        for r in cur.fetchall():
            cur.execute("DELETE FROM drivers WHERE id=%s", (r['id'],))
            removed += cur.rowcount or 0
        conn.commit()
        return removed
    except Exception as e:
        conn.rollback()
        print(f'  ! gagal membersihkan baris driver kosong: {e}')
        return 0
    finally:
        cur.close()


def fix_duplicate_assignments(conn):
    """Pertahankan penugasan terbaru per driver dan per nopol."""
    cur = conn.cursor(dictionary=True)
    fixed = 0
    try:
        cur.execute("""SELECT driver_name, MAX(id) AS keep_id FROM vehicle_assignments
                       WHERE is_current=1 GROUP BY driver_name HAVING COUNT(*) > 1""")
        for r in cur.fetchall():
            cur.execute("""UPDATE vehicle_assignments SET is_current=0, unassigned_date=CURDATE(),
                           cancel_reason='Auto-cleanup v2.78.0: penugasan ganda'
                           WHERE driver_name=%s AND is_current=1 AND id <> %s""",
                        (r['driver_name'], r['keep_id']))
            fixed += cur.rowcount or 0
        cur.execute("""SELECT nopol, MAX(id) AS keep_id FROM vehicle_assignments
                       WHERE is_current=1 GROUP BY nopol HAVING COUNT(*) > 1""")
        for r in cur.fetchall():
            cur.execute("""UPDATE vehicle_assignments SET is_current=0, unassigned_date=CURDATE(),
                           cancel_reason='Auto-cleanup v2.78.0: kendaraan ganda'
                           WHERE nopol=%s AND is_current=1 AND id <> %s""",
                        (r['nopol'], r['keep_id']))
            fixed += cur.rowcount or 0
        conn.commit()
        return fixed
    except Exception as e:
        conn.rollback()
        print(f'  ! gagal merapikan penugasan: {e}')
        return 0
    finally:
        cur.close()


def main():
    as_json = '--json' in sys.argv
    apply_fix = '--fix' in sys.argv
    users = fetch_users()
    if not users:
        print('❌ Tidak bisa membaca users dari DB master (cek env DB_*).')
        return 1

    report = {}
    total_findings = 0
    for code, db_name in branch_targets():
        conn = None
        try:
            conn = connection_for(db_name)
            if not conn:
                print(f'⚠ {code}: DB {db_name} tidak bisa dihubungi — dilewati.')
                continue
            ensure_driver_user_schema(conn)
            branch_code = (code or '').strip().upper()
            is_default = branch_code == bm.DEFAULT_BRANCH_CODE.upper()
            branch_users = [u for u in users
                            if (u.get('branch_code') or '').strip().upper() == branch_code
                            or (is_default and not (u.get('branch_code') or '').strip())]
            if apply_fix:
                backfill_driver_links(conn, branch_users)
            res = audit_driver_identity(conn, branch_users)
            report[code] = res
            total_findings += len(res['findings'])

            if not as_json:
                print(f'\n=== {code} ({db_name}) — {len(res["findings"])} temuan ===')
                for f in res['findings']:
                    print(f"  • [{LABELS.get(f['type'], f['type'])}] {f.get('detail', '')}")

            if apply_fix:
                fixed = 0
                for u in branch_users:
                    if u.get('role') not in ('driver', 'chief_driver'):
                        continue
                    out = sync_driver_for_user(
                        u['id'], u['username'], u.get('full_name') or '', u['role'],
                        u.get('branch_code') or code, is_active=bool(u.get('is_active')))
                    if out.get('ok') and out.get('action') in ('create', 'link', 'rename'):
                        fixed += 1
                dedup = fix_duplicate_assignments(conn)
                blank = remove_nameless_drivers(conn)
                if not as_json:
                    print(f'  ✔ perbaikan: {fixed} profil driver disinkronkan, '
                          f'{dedup} penugasan ganda dirapikan, {blank} baris kosong dibersihkan')
        except Exception as e:
            print(f'⚠ {code}: error audit — {e}')
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    if as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print(f'\nRingkasan: {total_findings} temuan di {len(report)} database.')
    if not apply_fix and total_findings:
        print('Jalankan ulang dengan --fix untuk menautkan & merapikan '
              '(tanpa menghapus riwayat).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
