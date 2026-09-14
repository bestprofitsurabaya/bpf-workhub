#!/usr/bin/env python3
"""Cek peta cabang→database BPF WorkHub.

Pemakaian:
    python3 scripts/check_branch_db_map.py             # static: seed init.sql + scan hardcode
    python3 scripts/check_branch_db_map.py --with-db   # + validasi peta live tabel branches
    python3 scripts/check_branch_db_map.py --json      # output machine-readable

Exit 0 = peta sehat; exit 1 = ada pelanggaran konvensi.

Konvensi (sengaja dipertahankan, lihat modules/branch_db_map.py):
    - Cabang default (SBY) memakai DB master `bpf_asset_system`.
    - Cabang lain memakai `bpf_branch_<x>` sesuai kolom `branches.db_name`.
    - Peta TIDAK boleh di-hardcode di kode — selalu via branches.db_name.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from modules.branch_db_map import (  # noqa: E402
    INIT_SQL, check_init_seed, check_live_map, check_no_db_literals,
)

# Kode yang boleh menyebut literal nama DB cabang (checker sendiri + ops statik).
# Catatan: seed init.sql / *.sql / *.sh / *.yml TIDAK discan — file infra/seeding
# memang rumah resmi peta cabang→DB; yang dilarang adalah kode aplikasi.
SCAN_ALLOWLIST = (
    'scripts/check_branch_db_map.py',
)


def main():
    ap = argparse.ArgumentParser(description='Cek peta cabang→DB')
    ap.add_argument('--with-db', action='store_true',
                    help='validasi juga peta live dari tabel branches (butuh DB)')
    ap.add_argument('--json', action='store_true', help='output JSON')
    args = ap.parse_args()

    sql_text = ''
    if os.path.exists(INIT_SQL):
        with open(INIT_SQL, encoding='utf-8') as f:
            sql_text = f.read()
    else:
        print(f'⚠ init.sql tidak ditemukan di {INIT_SQL} — seed check dilewati')

    report = {
        'seed': check_init_seed(sql_text),
        'literals': scan_code_literals(),
        'live': None,
    }

    if args.with_db:
        try:
            from modules.config import DB_CONFIG, get_master_connection
            conn = get_master_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute('SELECT code, db_name, is_active FROM branches')
            branches = cur.fetchall()
            cur.execute('SHOW DATABASES')
            existing = [r['Database'] for r in cur.fetchall()]
            cur.close()
            conn.close()
            report['live'] = check_live_map(branches, existing, master_db=DB_CONFIG['database'])
        except Exception as e:
            report['live'] = {'ok': False, 'violations': [f'probe DB gagal: {e}']}

    def _viol(r):
        return (r or {}).get('violations') or (r or {}).get('found') or []

    all_ok = (report['seed']['ok'] and report['literals']['ok']
              and (report['live'] is None or report['live']['ok']))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if report['seed']['seeded']:
            for code, db in report['seed']['seeded']:
                print(f'  seed {code:<5} → {db}')
        for label, r in (('seed', report['seed']), ('literal', report['literals']),
                         ('live', report['live'])):
            v = _viol(r)
            if v:
                for x in v:
                    print(f'  [{label}] ❌ {x}')
        print('\n✅ Peta cabang→DB sesuai konvensi (default = master, lainnya bpf_branch_<x>)'
              if all_ok else '\n❌ Peta cabang→DB menyimpang — perbaiki sebelum deploy.')

    sys.exit(0 if all_ok else 1)


def scan_code_literals():
    """Deteksi hardcode `bpf_branch_*` di kode aplikasi (app.py, modules/, scripts/).

    File infra/seeding (*.sql, *.sh, *.yml) dan tests (fixture DB sementara)
    tidak discan — penyebutan nama DB di sana memang sah.
    """
    import re
    root = os.path.join(os.path.dirname(__file__), '..')
    pat = re.compile(r'\bbpf_branch_[a-z0-9_]+\b')
    found = []
    targets = [os.path.join(root, 'app.py')]
    for sub in ('modules', 'scripts'):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith('.py'):
                    targets.append(os.path.join(d, fn))
    for p in targets:
        if not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, root).replace(os.sep, '/')
        if rel in SCAN_ALLOWLIST:
            continue
        try:
            with open(p, encoding='utf-8', errors='ignore') as f:
                hits = sorted(set(pat.findall(f.read())))
            for h in hits:
                found.append(f'{rel}: {h}')
        except OSError:
            continue
    return {'ok': not found, 'found': found}


if __name__ == '__main__':
    main()
