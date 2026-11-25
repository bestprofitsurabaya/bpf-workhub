"""Seed bank soal TKD dari CSV (dijalankan manual, bukan saat startup).

Pemakaian:
    python3 scripts/seed_tkd_bank.py                       # tulis draft ke DB master
    python3 scripts/seed_tkd_bank.py --dry-run             # hitung rencana saja
    python3 scripts/seed_tkd_bank.py --csv path/lain.csv   # berkas CSV lain

Aturan insert-if-absent memakai `code` sebagai kunci alami: kode yang sudah
ada tidak disentuh, sehingga menjalankan ulang script tidak mengembalikan
editan staff. Semua baris baru masuk sebagai draft (`active=0`) dan perlu
ditinjau/diaktifkan lewat Bank Soal. Satu jalur INSERT dipakai bersama route
impor: `modules.routes_tkd._insert_question`.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from modules.config import get_master_connection  # noqa: E402
from modules.routes_tkd import _insert_question  # noqa: E402
from modules.tkd_core import csv_to_question_rows  # noqa: E402
from modules.tkd_schema import ensure_tkd_schema  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = 'docs/seed/tkd_bank_v1.csv'


def seed_bank(cursor, csv_text):
    """Masukkan soal CSV yang belum ada; kembalikan hitungan insert/skip.

    `ValueError` dilempar bila CSV tidak valid — tidak ada baris yang boleh
    ditulis dari berkas yang sebagian rusak. Cursor dipakai apa adanya,
    commit menjadi tanggung jawab pemanggil.
    """
    rows, errors = csv_to_question_rows(csv_text)
    if errors:
        raise ValueError('; '.join(errors[:10]))
    cursor.execute('SELECT code FROM tkd_questions')
    existing = {str((row or {}).get('code')) for row in (cursor.fetchall() or [])}
    inserted = skipped = 0
    for row in rows:
        code = row['code']
        if code in existing:
            skipped += 1
            continue
        _insert_question(cursor, row, active=0)
        existing.add(code)  # kode duplikat dalam satu CSV juga dilewati
        inserted += 1
    return {'inserted': inserted, 'skipped': skipped, 'errors': []}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Seed bank soal TKD dari CSV (insert-if-absent, semua draft)')
    parser.add_argument('--csv', default=DEFAULT_CSV,
                        help=f'Berkas CSV (default: {DEFAULT_CSV})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Hitung rencana tanpa menulis ke DB')
    args = parser.parse_args(argv)

    path = Path(args.csv)
    if not path.is_absolute():
        path = ROOT / path  # selalu relatif terhadap root repo, bukan CWD
    try:
        # utf-8-sig juga menerima CSV yang disimpan Excel dengan BOM.
        csv_text = path.read_text(encoding='utf-8-sig')
    except OSError as exc:
        print(f'[tkd-seed] gagal membaca {args.csv}: {exc}', file=sys.stderr)
        return 1

    # Skema dibuat lebih dulu agar tabel tkd_questions pasti ada.
    if not ensure_tkd_schema():
        print('[tkd-seed] skema TKD tidak tersedia; seed dibatalkan.',
              file=sys.stderr)
        return 1

    conn = None
    try:
        conn = get_master_connection()
        if not conn:
            print('[tkd-seed] DB master tidak tersedia.', file=sys.stderr)
            return 1
        cursor = conn.cursor(dictionary=True)
        try:
            report = seed_bank(cursor, csv_text)
        finally:
            close = getattr(cursor, 'close', None)
            if callable(close):
                close()
        if args.dry_run:
            rollback = getattr(conn, 'rollback', None)
            if callable(rollback):
                rollback()
        else:
            conn.commit()
    except ValueError as exc:
        print(f'[tkd-seed] CSV tidak valid: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        # Detail exception bisa memuat kredensial/DB: tampilkan jenisnya saja.
        print(f'[tkd-seed] seed gagal ({type(exc).__name__}).', file=sys.stderr)
        return 1
    finally:
        if conn:
            close = getattr(conn, 'close', None)
            if callable(close):
                close()

    print(f"[tkd-seed] inserted={report['inserted']} "
          f"skipped={report['skipped']} errors={len(report['errors'])}")
    if args.dry_run:
        print('[tkd-seed] dry-run — tidak ada yang ditulis.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
