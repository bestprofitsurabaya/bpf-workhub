"""Guard peta cabang→database (v2.40.3).

Latar (14 Sep 2026): cabang SBY sengaja memakai DB master (`bpf_asset_system`)
sesuai seed init.sql — cabang default = DB utama; cabang lain memakai
`bpf_branch_<x>` sesuai kolom `branches.db_name`. Konvensi ini konsisten tapi
tidak bisa ditebak (sudah membuat sesi audit nyasar mencari `bpf_branch_<kode>`).

Guard ini mencegah tiga kelas masalah TANPA mengubah konvensi:
1. Seed init.sql menyimpang (cabang non-default menunjuk master, db_name kosong).
2. Hardcode literal `bpf_branch_*` di kode (peta WAJIB lewat branches.db_name).
3. Peta live rusak (db_name ganda antar cabang aktif, DB cabang tak ada).

Murni fungsi — tanpa koneksi DB — agar bisa diuji di CI tanpa MariaDB.
"""
import os
import re

MASTER_DB = os.environ.get('DB_NAME', 'bpf_asset_system')
DEFAULT_BRANCH_CODE = os.environ.get('BRANCH_MAIN_CODE', 'SBY')

# Sumber seed resmi peta cabang→DB.
INIT_SQL = os.path.join(os.path.dirname(__file__), '..', 'init.sql')

_RE_INSERT_BRANCHES = re.compile(
    r"INSERT\s+(?:IGNORE\s+)?INTO\s+branches\s*\(([^)]*)\)\s*VALUES\s*(.*?);",
    re.IGNORECASE | re.DOTALL)
_RE_STRING = re.compile(r"'((?:[^']|'')*)'")
# Literal nama DB cabang di kode — pola yang dilarang (docs/guides dikecualikan).
_RE_DB_LITERAL = re.compile(r"\bbpf_branch_[a-z0-9_]+\b")


def _unquote(val):
    return str(val or '').strip().strip('`').replace("''", "'")


def parse_branch_seed(sql_text):
    """Parse INSERT INTO branches dari init.sql → list of (code, db_name).

    Kolom dinamai eksplisit di tiap statement; idx kolom dicari per statement.
    Baris VALUES dipisah `),(` atau `), (` — cukup utk seed statik repo.
    """
    rows = []
    for m in _RE_INSERT_BRANCHES.finditer(sql_text or ''):
        cols = [_unquote(c) for c in m.group(1).split(',')]
        try:
            i_code = cols.index('code')
            i_db = cols.index('db_name')
        except ValueError:
            continue  # statement tanpa kolom code/db_name — bukan seed cabang
        values_blob = m.group(2)
        # Pisah antar tuple: '),' atau '), (' di level atas (tanpa nested quote).
        for tup in re.split(r"\)\s*,\s*\(", values_blob):
            vals = _RE_STRING.findall(tup)
            if len(vals) <= max(i_code, i_db):
                continue
            code = _unquote(vals[i_code])
            db_name = _unquote(vals[i_db])
            if code:
                rows.append((code, db_name))
    return rows


def check_init_seed(sql_text, master_db=MASTER_DB, default_code=DEFAULT_BRANCH_CODE):
    """Seed init.sql: default branch → master; cabang lain wajib db_name sendiri."""
    v = []
    for code, db_name in parse_branch_seed(sql_text):
        if not db_name:
            v.append(f"seed {code}: db_name kosong")
        elif code.upper() == default_code.upper():
            if db_name != master_db:
                v.append(f"seed {default_code} wajib menunjuk master {master_db}, dapat {db_name}")
        elif db_name == master_db:
            v.append(f"seed {code}: cabang non-default tidak boleh menunjuk master {master_db}")
    return {'ok': not v, 'violations': v, 'seeded': parse_branch_seed(sql_text)}


def check_no_db_literals(text, allow_master=True):
    """Deteksi hardcode literal `bpf_branch_*` pada potongan kode."""
    found = sorted(set(_RE_DB_LITERAL.findall(text or '')))
    return {'ok': not found, 'found': found}


def check_live_map(branches, existing_dbs, master_db=MASTER_DB,
                   default_code=DEFAULT_BRANCH_CODE):
    """Validasi peta live dari tabel branches.

    branches: list of dict (code, db_name, is_active).
    existing_dbs: list nama schema yang ada (information_schema.SCHEMATA).
    """
    v = []
    seen = {}
    for b in branches or []:
        code = str(b.get('code', '') or '').strip()
        db_name = str(b.get('db_name', '') or '').strip()
        active = bool(b.get('is_active'))
        if not code:
            v.append("baris branches tanpa code")
            continue
        if not db_name:
            v.append(f"{code}: db_name kosong")
            continue
        if code.upper() == default_code.upper():
            if db_name != master_db:
                v.append(f"{default_code} wajib menunjuk master {master_db}, dapat {db_name}")
        elif db_name == master_db:
            v.append(f"{code}: cabang non-default menunjuk master {master_db}")
        if active:
            if db_name in seen:
                v.append(f"{code} & {seen[db_name]} aktif berbagi DB {db_name} (split-brain)")
            else:
                seen[db_name] = code
    have = set(existing_dbs or [])
    for db_name, code in sorted(seen.items()):
        if db_name not in have:
            v.append(f"{code}: DB {db_name} tidak ada di server")
    return {'ok': not v, 'violations': v}
