#!/usr/bin/env python3
"""Cek drift skema DB master CI terhadap init.sql (sumber kebenaran).

Dijalankan di CI setelah pytest, memakai DB `bpf_asset_system` yang sama
dengan service MariaDB CI (env DB_HOST/DB_USER/DB_PASSWORD/DB_NAME dibaca
oleh modules.config). Hanya tabel/kolom yang HILANG yang dianggap drift;
kolom tambahan hasil migrasi DB lama tidak menggagalkan pemeriksaan.

Exit 0 = skema sesuai (atau DB tidak tersedia → SKIP), 1 = ada tabel/kolom
hilang. Branch DB tidak tersedia di CI, jadi check ini hanya untuk DB master.
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
        expected = parse_init_sql(f.read())

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
        finally:
            cursor.close()
    except Exception as exc:
        print(f'SKIP: gagal membaca information_schema ({exc})')
        return 0
    finally:
        conn.close()

    if missing:
        print(f'❌ Schema drift — {len(missing)} tabel/kolom hilang dari DB:')
        for item in missing:
            print(f'  - {item}')
        return 1
    print(f'✅ Skema DB sesuai init.sql ({len(expected)} tabel)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
