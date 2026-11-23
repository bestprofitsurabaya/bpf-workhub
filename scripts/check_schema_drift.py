#!/usr/bin/env python3
"""Cek drift skema DB master CI terhadap init.sql (sumber kebenaran).

Dijalankan di CI setelah pytest, memakai DB `bpf_asset_system` yang sama
dengan service MariaDB CI (env DB_HOST/DB_USER/DB_PASSWORD/DB_NAME dibaca
oleh modules.config). Yang dianggap drift hanya yang HILANG dari DB:
tabel, kolom, dan unique constraint (PK/UNIQUE). Kolom atau index tambahan
hasil migrasi DB lama tidak menggagalkan pemeriksaan.

v2.131.5: unique constraint ikut diperiksa — sebelumnya `vehicles.
vehicle_type UNIQUE` hilang dari produksi tanpa terdeteksi, sementara
`init.sql` masih menuntutnya (fresh install gagal menambah kendaraan kedua
dengan tipe sama, dan FK ke kolom itu mustahil).

Exit 0 = skema sesuai (atau DB tidak tersedia → SKIP), 1 = ada yang hilang.
Branch DB tidak tersedia di CI, jadi check ini hanya untuk DB master.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_SQL = os.path.join(ROOT, 'init.sql')
sys.path.insert(0, ROOT)

_CREATE_TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*?)\)'
    r'(?=\s*(?:ENGINE\b|;|$))', re.S | re.I)
_CONSTRAINT_RE = re.compile(
    r'^(?:PRIMARY|UNIQUE|KEY|INDEX|FOREIGN|CONSTRAINT|CHECK|FULLTEXT|SPATIAL)\b',
    re.I)
_COLUMN_RE = re.compile(r'^`?([A-Za-z_]\w*)`?\s+\S')
_QUOTES = ("'", '"', '`')


def _strip_sql_comments(text):
    """Buang komentar `-- ...` (quote-aware) sebelum memecah definisi."""
    out = []
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
        elif ch in _QUOTES:
            quote = ch
            out.append(ch)
            i += 1
        elif text.startswith('--', i):
            end = text.find('\n', i)
            if end == -1:
                break
            i = end + 1
            out.append('\n')
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _split_definitions(body):
    """Pecah isi CREATE TABLE pada koma level teratas (abaikan tipe ENUM/DECIMAL)."""
    parts, buf = [], []
    depth = 0
    quote = None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
            buf.append(ch)
        elif ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    if ''.join(buf).strip():
        parts.append(''.join(buf))
    return parts


def parse_init_sql(text):
    """Parse DDL → {nama_tabel: [nama_kolom, ...]}."""
    expected = {}
    for match in _CREATE_TABLE_RE.finditer(_strip_sql_comments(text)):
        columns = []
        for definition in _split_definitions(match.group(2)):
            definition = definition.strip()
            if not definition or _CONSTRAINT_RE.match(definition):
                continue
            column = _COLUMN_RE.match(definition)
            if column:
                columns.append(column.group(1))
        expected[match.group(1)] = columns
    return expected


def _parse_columns_list(text):
    """`"a, `b`, address(255)"` → ('a', 'b', 'address').

    Prefix index (`address(255)`) dibandingkan sebagai nama kolom saja —
    information_schema.STATISTICS memisahkan panjang prefix ke SUB_PART.
    Index ekspresi (mengandung fungsi) dilewati: return None.
    """
    columns = []
    for part in _split_definitions(text):
        name = re.sub(r'\s*\(\s*\d+\s*\)\s*$', '', part.strip())
        name = name.strip().strip('`').lower()
        if not name:
            continue
        if '(' in name or ')' in name:
            return None  # index ekspresi/fungsi — tidak bisa dibandingkan
        columns.append(name)
    return tuple(columns)


def parse_init_unique(text):
    """Parse DDL → {nama_tabel: {(kolom, ...), ...}} untuk PK & UNIQUE.

    Nama index sengaja tidak dipakai: produksi & init.sql boleh memberi nama
    berbeda (mis. `trip_masters.display_id` vs `idx_trip_display_id`) asal
    kumpulan kolomnya sama.
    """
    expected = {}
    for match in _CREATE_TABLE_RE.finditer(_strip_sql_comments(text)):
        table = match.group(1).lower()
        uniques = set()
        for definition in _split_definitions(match.group(2)):
            definition = definition.strip()
            if not definition:
                continue

            primary = re.match(r'^PRIMARY\s+KEY\s*\((.*)\)', definition, re.I)
            if primary:
                columns = _parse_columns_list(primary.group(1))
                if columns:
                    uniques.add(columns)
                continue

            unique = re.match(
                r'^(?:CONSTRAINT\s+`?\w+`?\s+)?UNIQUE\s+'
                r'(?:KEY|INDEX)?\s*`?\w*`?\s*\((.*)\)',
                definition, re.I)
            if unique:
                columns = _parse_columns_list(unique.group(1))
                if columns:
                    uniques.add(columns)
                continue

            if _CONSTRAINT_RE.match(definition):
                continue
            column = _COLUMN_RE.match(definition)
            if not column:
                continue
            if re.search(r'\b(?:PRIMARY|UNIQUE)\s+KEY\b', definition, re.I) or \
                    re.search(r'\bUNIQUE\b', definition, re.I):
                uniques.add((column.group(1).lower(),))
        expected[table] = uniques
    return expected


def query_unique_from_db(cursor):
    """Ambil unique constraint DB aktif → {tabel: {(kolom, ...), ...}}."""
    cursor.execute(
        'SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX '
        'FROM information_schema.STATISTICS '
        'WHERE TABLE_SCHEMA = DATABASE() AND NON_UNIQUE = 0 '
        'ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX')
    grouped = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            table = row.get('TABLE_NAME')
            index = row.get('INDEX_NAME')
            column = row.get('COLUMN_NAME')
            seq = row.get('SEQ_IN_INDEX')
        else:
            table, index, column, seq = row[0], row[1], row[2], row[3]
        columns = grouped.setdefault(str(table).lower(), {}).setdefault(
            str(index), {})
        columns[int(seq)] = str(column).lower()
    return {
        table: {
            tuple(cols[pos] for pos in sorted(cols))
            for cols in indexes.values()
        }
        for table, indexes in grouped.items()
    }


def compare_unique_with_db(expected, actual):
    """List unique constraint `expected` yang tidak ada di `actual`.

    `actual` berbentuk {tabel: {(kolom, ...), ...}} (lihat
    `query_unique_from_db`). Tabel yang tidak ada dilewati di sini karena
    sudah dilaporkan `compare_with_db`.
    """
    missing = []
    for table, uniques in expected.items():
        present = actual.get(table.lower())
        if present is None:
            continue
        for columns in sorted(uniques):
            if columns not in present:
                missing.append(
                    f'unique {table} ({", ".join(columns)}) hilang dari DB')
    return missing


def compare_with_db(expected, cursor):
    """List tabel/kolom di `expected` yang tidak ada di skema DB aktif."""
    cursor.execute(
        'SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS '
        'WHERE TABLE_SCHEMA = DATABASE()')
    actual = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            table, column = row.get('TABLE_NAME'), row.get('COLUMN_NAME')
        else:
            table, column = row[0], row[1]
        actual.setdefault(str(table).lower(), set()).add(str(column).lower())

    missing = []
    for table, columns in expected.items():
        present = actual.get(table.lower())
        if present is None:
            missing.append(f'tabel {table} hilang dari DB')
            continue
        for column in columns:
            if column.lower() not in present:
                missing.append(f'kolom {table}.{column} hilang dari DB')
    return missing


def get_db_connection():
    """Koneksi non-sesi ke DB master (bpf_asset_system di CI)."""
    from modules.config import get_master_connection
    return get_master_connection()


def main():
    with open(INIT_SQL, encoding='utf-8') as f:
        sql = f.read()
    expected = parse_init_sql(sql)
    expected_unique = parse_init_unique(sql)

    reason = ''
    try:
        conn = get_db_connection()
    except Exception as exc:  # DB belum siap / kredensial tidak ada
        conn = None
        reason = str(exc)
    if conn is None:
        suffix = f' ({reason})' if reason else ''
        print(f'SKIP: DB tidak tersedia — schema drift check dilewati{suffix}')
        return 0

    try:
        cursor = conn.cursor()
        try:
            missing = compare_with_db(expected, cursor)
            try:
                actual_unique = query_unique_from_db(cursor)
                missing += compare_unique_with_db(expected_unique, actual_unique)
            except Exception as exc:  # information_schema versi lain
                print(f'PERINGATAN: cek unique constraint dilewati ({exc})')
        finally:
            cursor.close()
    except Exception as exc:
        print(f'SKIP: gagal membaca information_schema ({exc})')
        return 0
    finally:
        conn.close()

    if missing:
        print(f'❌ Schema drift — {len(missing)} objek hilang dari DB:')
        for item in missing:
            print(f'  - {item}')
        return 1
    print(f'✅ Skema DB sesuai init.sql ({len(expected)} tabel)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
