"""Regresi init.sql — fresh install harus menghasilkan skema yang dipakai kode.

Dua bug nyata yang pernah terjadi (v2.47.1):
1. `applicants` & `applicant_attendance` mendefinisikan PRIMARY KEY dua kali
   (`id ... PRIMARY KEY` + `PRIMARY KEY (id)`) → MariaDB berhenti dengan
   ERROR 1068 saat entrypoint menjalankan init.sql → container DB mati,
   deploy fresh gagal total.
2. Kolom yang hanya ditambahkan manual di DB produksi (vehicles.nopol,
   transactions.display_id, vehicle_assignments.confirmed_by_driver, ...)
   tidak ada di init.sql → endpoint inti 500 "Unknown column" pada instalasi
   baru, padahal seluruh test unit lulus (DB di-fake).

Test ini statis (tanpa DB) supaya cepat & deterministik di CI.
"""
import re
from pathlib import Path

INIT_SQL = Path(__file__).resolve().parents[1] / 'init.sql'


def _table_blocks():
    """Yield (nama_tabel, isi_definisi) untuk tiap CREATE TABLE."""
    sql = INIT_SQL.read_text(encoding='utf-8')
    # Tabel lama ditutup `);` tanpa ENGINE=, yang baru `) ENGINE=InnoDB ...;`.
    pattern = re.compile(
        r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\)[^;]*;',
        re.S | re.I)
    for m in pattern.finditer(sql):
        yield m.group(1), m.group(2)


def test_init_sql_parses_at_least_core_tables():
    names = {name for name, _ in _table_blocks()}
    for required in ('users', 'branches', 'vehicles', 'transactions',
                     'appointments', 'vehicle_assignments', 'applicants',
                     'water_purchases', 'overtime_driver'):
        assert required in names, f'tabel {required} hilang dari init.sql'


def test_no_duplicate_primary_key_definition():
    """`id ... PRIMARY KEY` + `PRIMARY KEY (id)` = ERROR 1068 (init gagal)."""
    offenders = []
    inline_pk = re.compile(r'^\s*\w+\s+[^,]*\bPRIMARY\s+KEY\b', re.I | re.M)
    table_pk = re.compile(r'^\s*PRIMARY\s+KEY\s*\(', re.I | re.M)
    for name, body in _table_blocks():
        if inline_pk.search(body) and table_pk.search(body):
            offenders.append(name)
    assert not offenders, (
        'PRIMARY KEY didefinisikan dua kali pada tabel: '
        + ', '.join(offenders))


def test_no_duplicate_column_name_per_table():
    offenders = []
    for name, body in _table_blocks():
        cols = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            if re.match(r'^(PRIMARY|UNIQUE|KEY|INDEX|CONSTRAINT|FOREIGN)\b', line, re.I):
                continue
            col = re.match(r'^(\w+)\s+', line)
            if col:
                cols.append(col.group(1).lower())
        dupes = {c for c in cols if cols.count(c) > 1}
        if dupes:
            offenders.append(f'{name}: {", ".join(sorted(dupes))}')
    assert not offenders, 'kolom duplikat: ' + '; '.join(offenders)


def test_columns_used_by_endpoints_exist_in_init_sql():
    """Kolom yang dulu hanya ada di DB produksi (drift schema)."""
    required = {
        'vehicles': ['nopol', 'bbm_default'],
        'transactions': ['display_id', 'transaction_type', 'cash_request_id',
                         'gps_kelurahan', 'gps_kecamatan', 'gps_kota',
                         'gps_provinsi', 'gps_kode_pos'],
        'vehicle_assignments': ['driver_notes', 'cancel_reason', 'cancelled_by',
                                'confirmed_by_driver', 'confirmed_at'],
    }
    blocks = dict(_table_blocks())
    missing = []
    for table, cols in required.items():
        body = blocks.get(table, '')
        for col in cols:
            if not re.search(rf'^\s*{re.escape(col)}\s+', body, re.I | re.M):
                missing.append(f'{table}.{col}')
    assert not missing, (
        'kolom dipakai kode tapi tidak ada di init.sql (fresh install 500): '
        + ', '.join(missing))


def test_applicants_schema_has_expected_columns():
    """Kolom yang dipakai modul pelamar/receptionist."""
    body = dict(_table_blocks())['applicants']
    for col in ('display_id', 'nama_lengkap', 'status', 'interview_at',
                'upline', 'user_field'):
        assert re.search(rf'^\s*{col}\s+', body, re.I | re.M), \
            f'applicants.{col} hilang'
