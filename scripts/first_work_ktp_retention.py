"""Retensi foto KTP FirstWork (v2.85.0 — UU PDP pembatasan penyimpanan).

Kebijakan: foto KTP (file lokal + referensi Drive) dihapus N hari setelah
keputusan verifikasi (status `verified`/`rejected`). Default 90 hari, bisa
diubah lewat `system_config.first_work_ktp_retention_days`.

Setiap pemusnahan tercatat sebagai event `ktp_purge` di `first_work_events`
(jumlah file + tanggal), mengikuti prinsip retensi `docs/internal/RETENTION_POLICY.md`:
hapus hanya data yang tidak lagi diperlukan, selalu dengan jejak.

Pemakaian (di container web — cron harian atau manual):
    python3 scripts/first_work_ktp_retention.py [--dry-run]
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config import get_master_connection
from modules.routes_first_work import (
    UPLOAD_DIR,
    _config_get,
    _config_set,
)

RETENTION_CONFIG_KEY = 'first_work_ktp_retention_days'
DEFAULT_RETENTION_DAYS = 90


def _retention_days(conn):
    raw = (_config_get(conn, RETENTION_CONFIG_KEY) or '').strip()
    try:
        days = int(raw)
        if 1 <= days <= 3650:
            return days
    except (TypeError, ValueError):
        pass
    if raw:
        _config_set(conn, RETENTION_CONFIG_KEY, str(DEFAULT_RETENTION_DAYS))
    return DEFAULT_RETENTION_DAYS


def purge_expired_ktp(conn, days, dry_run=False):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, registration_no, ktp_file,
                   COALESCE(verified_at, updated_at) AS decided_at
            FROM first_work_submissions
            WHERE ktp_file <> ''
              AND status IN ('verified', 'rejected')
              AND COALESCE(verified_at, updated_at) <= %s
        """, (datetime.now() - timedelta(days=days),))
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    purged, missing, errors = [], 0, 0
    for row in rows:
        filename = row['ktp_file']
        if dry_run:
            purged.append((row['registration_no'], filename, row['decided_at']))
            continue
        path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
        try:
            if os.path.exists(path):
                os.remove(path)
            else:
                missing += 1
        except OSError as e:
            errors += 1
            print(f'[ktp-retention] gagal hapus {path}: {e}')
            continue
        cursor = conn.cursor()
        try:
            # File lokal + referensi eksternal keduanya dibereskan: setelah
            # masa retensi, KTP tidak lagi dilayani dari sumber mana pun.
            cursor.execute("""
                UPDATE first_work_submissions
                SET ktp_file='', ktp_drive_url='', photoid_url=''
                WHERE id=%s
            """, (row['id'],))
            cursor.execute("""
                INSERT INTO first_work_events
                    (submission_id, event, status_from, status_to, note,
                     actor, actor_role)
                VALUES (%s,'ktp_purge',%s,%s,%s,'system','system')
            """, (row['id'], row['status'], row['status'],
                  f"Foto KTP dihapus otomatis (retensi {days} hari setelah "
                  f"keputusan {row['decided_at']})"))
        finally:
            cursor.close()
        purged.append((row['registration_no'], filename, row['decided_at']))
    if not dry_run:
        conn.commit()
    return {'due': len(purged), 'purged': purged, 'missing_files': missing,
            'errors': errors}


def main():
    dry_run = '--dry-run' in sys.argv
    conn = get_master_connection()
    if not conn:
        print('[ktp-retention] DB tidak tersedia')
        return 1
    try:
        days = _retention_days(conn)
        stats = purge_expired_ktp(conn, days, dry_run=dry_run)
        label = 'dipurge' if not dry_run else 'akan dipurge (dry-run)'
        print(f'[ktp-retention] retensi={days} hari, {stats["due"]} berkas '
              f'{label}, missing={stats["missing_files"]}, '
              f'errors={stats["errors"]}')
        if not dry_run and stats['due']:
            print(json.dumps([r[0] for r in stats['purged']], default=str))
        return 0 if not stats['errors'] else 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
