#!/usr/bin/env python3
"""Cek konsistensi 7 titik stamp versi BPF WorkHub.

Pemakaian:
    python3 scripts/check_version_stamps.py             # 7 titik file
    python3 scripts/check_version_stamps.py --with-db   # + probe DB (master & branches)
    python3 scripts/check_version_stamps.py --json      # output machine-readable

Exit 0 = semua konsisten; exit 1 = ada stamp menyimpang/hilang.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from modules.version_stamp import check_all, check_db_stamps  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='Cek 7 titik stamp versi')
    ap.add_argument('--with-db', action='store_true',
                    help='probe juga stamp DB (master system_config + branches.system_version)')
    ap.add_argument('--json', action='store_true', help='output JSON')
    args = ap.parse_args()

    report = check_all()
    report['db'] = check_db_stamps() if args.with_db else None
    db_ok = report['db'] is None or all(d['ok'] for d in report['db'])

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Versi referensi: {report['version']}")
        for p in report['points']:
            mark = 'OK  ' if p['ok'] else 'BEDA'
            print(f"  [{mark}] {p['name']:<34} {p['file']:<42} {p['value']}")
        if report['db'] is not None:
            for d in report['db']:
                mark = 'OK  ' if d['ok'] else 'BEDA'
                extra = f"  ({d['error']})" if d.get('error') else ''
                print(f"  [{mark}] {d['name']:<34} {'':42} {d['value']}{extra}")
        bad = [p for p in report['points'] if not p['ok']]
        if bad:
            print(f"\n❌ {len(bad)} titik tidak konsisten — bump versi harus menyentuh SEMUA titik.")
        elif not db_ok:
            print('\n❌ Stamp DB tidak konsisten dengan kode.')
        else:
            print('\n✅ Semua titik stamp konsisten.')

    sys.exit(0 if (report['all_ok'] and db_ok) else 1)


if __name__ == '__main__':
    main()
