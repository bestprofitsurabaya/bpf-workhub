#!/usr/bin/env python3
"""Impor data bpf-calendar lama (items.json + media) ke Agenda WorkHub.

Sumber: folder data container `bpf-calendar` (default /app/data), berisi
`items.json` dan `assets/up/*`. Tujuan: tabel `agenda_items` di DB satu
cabang + folder `uploads/agenda/`.

Sifat idempoten: item dengan `legacy_id` yang sama di cabang itu dilewati.
Media disalin dengan nama aman (`RE_SAFE_MEDIA`) dan URL ditulis ulang.

Contoh (di host/NAS, dari root repo):
    python3 scripts/import_bpf_calendar.py --data-dir /tmp/bpf-calendar-data \
        --branch SBY --dry-run
    python3 scripts/import_bpf_calendar.py --data-dir /tmp/bpf-calendar-data --branch SBY
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.agenda import _insert, clear_bridge_cache, ensure_agenda_schema, validate_payload  # noqa: E402
from modules.branch_manager import list_branches  # noqa: E402
from modules.config import get_db_connection  # noqa: E402

MEDIA_DIR = os.path.join(ROOT, 'uploads', 'agenda')
RE_SAFE = re.compile(r'^[A-Za-z0-9._-]+$')


def safe_name(name):
    """Nama file aman untuk route /assets/up/* dan URL."""
    base = os.path.basename(str(name or ''))
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base).strip('._-')
    return base or 'media'


def legacy_audience(value):
    v = str(value or 'all').lower()
    return 'all' if v in ('both', 'semua', '') else v


def legacy_dt(value):
    """Normalisasi datetime lama → 'YYYY-MM-DDTHH:MM' bila memungkinkan."""
    if not value:
        return None
    s = str(value).strip().replace(' ', 'T')
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})', s)
    return f'{m.group(1)}T{m.group(2)}' if m else None


def copy_media(media_url, src_dir, dry_run=False):
    """Salin satu media /assets/up/<nama> → uploads/agenda/<nama aman>."""
    if not media_url or not str(media_url).startswith('/assets/up/'):
        return media_url
    src_name = os.path.basename(str(media_url))
    src = os.path.join(src_dir, src_name)
    if not os.path.isfile(src):
        print(f'  ! media tidak ditemukan: {src}')
        return media_url
    dst_name = safe_name(src_name)
    dst = os.path.join(MEDIA_DIR, dst_name)
    if dst_name != src_name:
        print(f'  ~ rename media: {src_name} → {dst_name}')
    if not dry_run:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
    return f'/assets/up/{dst_name}'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir', required=True,
                    help='Folder data bpf-calendar (berisi items.json)')
    ap.add_argument('--branch', required=True, help='Kode cabang tujuan (mis. SBY)')
    ap.add_argument('--actor', default='import-bpf-calendar',
                    help='Nama pencatat created_by')
    ap.add_argument('--dry-run', action='store_true', help='Hanya tampilkan rencana')
    args = ap.parse_args()

    branch = str(args.branch).strip().upper()
    codes = {str(b.get('code') or '').upper() for b in list_branches()}
    if branch not in codes:
        sys.exit(f'Cabang {branch} tidak ditemukan. Pilihan: {", ".join(sorted(codes))}')

    items_file = os.path.join(args.data_dir, 'items.json')
    if not os.path.isfile(items_file):
        sys.exit(f'Tidak ada {items_file}')
    with open(items_file, encoding='utf-8') as fh:
        raw = json.load(fh)
    legacy = raw.get('items') if isinstance(raw, dict) else None
    if not isinstance(legacy, list):
        sys.exit('Format items.json tidak dikenal (harus {"items": [...]})')

    conn = get_db_connection(branch_code=branch)
    if not conn:
        sys.exit('Tidak bisa terhubung ke DB cabang')
    inserted = skipped = failed = 0
    try:
        ensure_agenda_schema(conn=conn)
        cur = conn.cursor(dictionary=True)
        for it in legacy:
            legacy_id = str(it.get('id') or '').strip()
            if not legacy_id:
                failed += 1
                continue
            cur.execute('SELECT id FROM agenda_items WHERE legacy_id=%s LIMIT 1',
                        (legacy_id,))
            if cur.fetchone():
                skipped += 1
                continue

            group = it.get('audience')
            publish_mode = 'scheduled' if it.get('publish_mode') == 'scheduled' else 'now'
            payload = {
                'date': it.get('date'),
                'title': it.get('title') or '(tanpa judul)',
                'body': it.get('body') or '',
                'audience': legacy_audience(group),
                'publish_mode': publish_mode,
                'publish_at': legacy_dt(it.get('publish_at')) if publish_mode == 'scheduled' else None,
                'end_at': legacy_dt(it.get('end_at')),
                'media_url': copy_media(it.get('media_url'),
                                        os.path.join(args.data_dir, 'assets', 'up'),
                                        dry_run=args.dry_run),
                'pinned': 0,
                'notify_on_day': 0,
                'active': 1 if it.get('active', True) else 0,
            }
            item, errors = validate_payload(payload)
            if errors:
                print(f'  ! {legacy_id}: {"; ".join(errors)}')
                failed += 1
                continue
            row = dict(item)
            row.update({
                # Item lama adalah agenda tunggal, BUKAN terbit lintas
                # cabang. batch_id bersama akan membuat dedupe lintas cabang
                # menganggap semuanya satu item dan hanya satu yang tampil.
                'batch_id': None,
                'branch_code': branch,
                'legacy_id': legacy_id,
                'created_by': args.actor,
                'updated_by': args.actor,
            })
            print(f'  + {row["agenda_date"]} · {row["title"]}'
                  + (' [dry-run]' if args.dry_run else ''))
            if not args.dry_run:
                _insert(conn, row)
            inserted += 1
        cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not args.dry_run:
        clear_bridge_cache()
    print(f'\nSelesai: {inserted} baru, {skipped} dilewati, {failed} gagal.'
          + (' (dry-run, tidak ada yang ditulis)' if args.dry_run else ''))


if __name__ == '__main__':
    main()
