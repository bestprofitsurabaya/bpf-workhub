"""Guard peta cabang→DB (v2.40.3) — konvensi SBY=master + peta via branches.db_name.

Latar: cabang default (SBY) sengaja memakai DB master bpf_asset_system; cabang
lain memakai bpf_branch_<x> via kolom branches.db_name. Konvensi ini tak bisa
ditebak dan pernah membuat sesi audit nyasar mencari bpf_branch_sby — guard
menjaga konvensi tetap konsisten TANPA mengubahnya (tanpa rename/split DB).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from modules.branch_db_map import (  # noqa: E402
    check_init_seed, check_live_map, check_no_db_literals, parse_branch_seed,
)

SEED_OK = """
INSERT IGNORE INTO branches (code, name, db_name, city)
VALUES ('SBY', 'Cabang Surabaya', 'bpf_asset_system', 'Surabaya');
INSERT IGNORE INTO branches (code, name, db_name, city, address, phone)
VALUES ('JKT', 'Kantor Pusat', 'bpf_branch_jkt', 'Jakarta', 'x', 'y'),
       ('JKT2', 'Pacific Place', 'bpf_branch_jkt2', 'Jakarta', 'x', 'y');
"""


class TestSeedParsing(unittest.TestCase):
    def test_parse_seed_multi_statement_multi_tuple(self):
        rows = parse_branch_seed(SEED_OK)
        self.assertEqual(rows, [('SBY', 'bpf_asset_system'),
                                ('JKT', 'bpf_branch_jkt'),
                                ('JKT2', 'bpf_branch_jkt2')])

    def test_parse_seed_ignores_other_tables(self):
        rows = parse_branch_seed("INSERT INTO users (code, db_name) VALUES ('a','b');")
        self.assertEqual(rows, [])


class TestSeedConvention(unittest.TestCase):
    def test_seed_sesuai_konvensi(self):
        r = check_init_seed(SEED_OK, master_db='bpf_asset_system', default_code='SBY')
        self.assertTrue(r['ok'], r['violations'])

    def test_seed_cabang_non_default_menunjuk_master_ditolak(self):
        bad = SEED_OK + "\nINSERT INTO branches (code, name, db_name) VALUES ('BDG','Bdg','bpf_asset_system');"
        r = check_init_seed(bad, master_db='bpf_asset_system', default_code='SBY')
        self.assertFalse(r['ok'])
        self.assertTrue(any('BDG' in v for v in r['violations']))

    def test_seed_default_tidak_menunjuk_master_ditolak(self):
        bad = "INSERT INTO branches (code, name, db_name) VALUES ('SBY','Sby','bpf_branch_sby');"
        r = check_init_seed(bad, master_db='bpf_asset_system', default_code='SBY')
        self.assertFalse(r['ok'])

    def test_seed_db_name_kosong_ditolak(self):
        bad = "INSERT INTO branches (code, name, db_name) VALUES ('JKT','Ho','');"
        r = check_init_seed(bad, master_db='bpf_asset_system', default_code='SBY')
        self.assertFalse(r['ok'])

    def test_init_sql_repo_sesuai_konvensi(self):
        """Guard file asli: seed init.sql repo harus selalu sesuai konvensi."""
        path = os.path.join(os.path.dirname(__file__), '..', 'init.sql')
        with open(path, encoding='utf-8') as f:
            sql = f.read()
        r = check_init_seed(sql)
        self.assertTrue(r['ok'], r['violations'])


class TestLiveMap(unittest.TestCase):
    CLEAN = [
        {'code': 'SBY', 'db_name': 'bpf_asset_system', 'is_active': 1},
        {'code': 'BDG', 'db_name': 'bpf_branch_bdg', 'is_active': 1},
        {'code': 'SMG', 'db_name': 'bpf_branch_smg', 'is_active': 1},
        {'code': 'JMB', 'db_name': 'bpf_branch_jmb', 'is_active': 0},
    ]

    def test_peta_bersih_ok(self):
        r = check_live_map(self.CLEAN, ['bpf_asset_system', 'bpf_branch_bdg',
                                        'bpf_branch_smg'])
        self.assertTrue(r['ok'], r['violations'])

    def test_cabang_aktif_berbagi_db_ditolak(self):
        rows = self.CLEAN + [{'code': 'BDG2', 'db_name': 'bpf_branch_bdg', 'is_active': 1}]
        r = check_live_map(rows, ['bpf_asset_system', 'bpf_branch_bdg', 'bpf_branch_smg'])
        self.assertFalse(r['ok'])
        self.assertTrue(any('split-brain' in v or 'bpf_branch_bdg' in v for v in r['violations']))

    def test_db_cabang_aktif_tidak_ada_ditolak(self):
        r = check_live_map(self.CLEAN, ['bpf_asset_system', 'bpf_branch_smg'])
        self.assertFalse(r['ok'])
        self.assertTrue(any('bpf_branch_bdg' in v for v in r['violations']))

    def test_cabang_inactive_tanpa_db_dibiarkan(self):
        rows = [b for b in self.CLEAN if b['code'] == 'JMB']
        r = check_live_map(rows, [])  # DB-nya tak ada — inactive, tak diverifikasi
        self.assertTrue(r['ok'], r['violations'])

    def test_non_default_menunjuk_master_ditolak(self):
        rows = [{'code': 'BDG', 'db_name': 'bpf_asset_system', 'is_active': 1}]
        r = check_live_map(rows, ['bpf_asset_system'], master_db='bpf_asset_system',
                           default_code='SBY')
        self.assertFalse(r['ok'])

    def test_db_name_kosong_ditolak(self):
        rows = [{'code': 'BDG', 'db_name': '', 'is_active': 1}]
        r = check_live_map(rows, [])
        self.assertFalse(r['ok'])


class TestLiteralScan(unittest.TestCase):
    def test_literal_terdeteksi(self):
        r = check_no_db_literals("cfg = 'bpf_branch_foo'  # hardcode")
        self.assertFalse(r['ok'])
        self.assertEqual(r['found'], ['bpf_branch_foo'])

    def test_tanpa_literal_ok(self):
        r = check_no_db_literals("db = resolve_db_name(branch_code)")
        self.assertTrue(r['ok'])

    def test_guard_kode_repo_bebas_literal(self):
        """Guard file asli: kode aplikasi repo tak boleh hardcode nama DB cabang."""
        root = os.path.join(os.path.dirname(__file__), '..')
        for sub in ('modules', 'scripts'):
            d = os.path.join(root, sub)
            for fn in sorted(os.listdir(d)):
                if not fn.endswith('.py') or fn == 'branch_db_map.py':
                    continue
                with open(os.path.join(d, fn), encoding='utf-8', errors='ignore') as f:
                    r = check_no_db_literals(f.read())
                self.assertTrue(r['ok'], f'{sub}/{fn}: {r["found"]}')

    def test_scanner_menangkap_file_baru(self):
        """Kontrol negatif: file baru berisi literal harus ketahuan scanner."""
        import importlib
        import scripts.check_branch_db_map as scanner
        importlib.reload(scanner)
        root = os.path.join(os.path.dirname(__file__), '..', 'modules')
        probe = os.path.join(root, '_tmp_literal_probe.py')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write("DB = 'bpf_branch_probe'\n")
        try:
            r = scanner.scan_code_literals()
        finally:
            os.remove(probe)
        self.assertFalse(r['ok'])
        self.assertTrue(any('bpf_branch_probe' in x for x in r['found']))


if __name__ == '__main__':
    unittest.main()
