"""Backfill kasus rekrutmen dari FirstWork lama WorkHub (Rilis B Task 5).

Pemakaian:
    python3 scripts/backfill_recruitment_cases.py            # dry-run (default)
    python3 scripts/backfill_recruitment_cases.py --commit   # tulis ke DB master

Sifat backfill:
  - Satu NIK = satu `recruitment_cases`; setiap baris FirstWork lama
    menghasilkan satu langkah FIRSTWORK dengan status SELESAI.
  - Penanda sumber memakai `evidence_type='sheet_legacy'` (kolom `source`
    pada `recruitment_steps` tidak ada di skema Rilis A; Task 4 memakai
    `evidence_type` untuk marker `unitedw`). `evidence_id` = id baris
    `first_work_submissions`, cabang = `branch_code` baris tersebut.
  - Tabel sumber (`first_work_submissions`, `cv_online_submissions`) HANYA
    dibaca. Tidak ada UPDATE/INSERT/DELETE/penomoran ulang pada sumber.
  - Baris `source='unitedw'` dilewati — sudah ditangani Task 4. Langkah yang
    sudah ada (dari form FirstWork maupun CV Online) tidak ditimpa.
  - Idempoten: kunci alami (NIK, cabang) dicek sebelum menulis; run kedua
    hanya menghitung `skipped`, tanpa commit.
  - Satu transaksi per NIK: bila satu NIK gagal, hanya NIK itu yang di-rollback.
  - Log/report cukup 4 digit terakhir NIK (data pribadi).
  - Dry-run adalah DEFAULT dan tidak menulis apa pun.

Laporan (JSON di stdout): `scanned`, `cases_created`, `steps_created`,
`skipped`, `invalid`, `failed`.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from modules.config import get_master_connection  # noqa: E402
from modules.helpers import normalize_nik  # noqa: E402
from modules.recruitment_service import upsert_case_step  # noqa: E402

SOURCE = 'sheet_legacy'
EXCLUDED_SOURCE = 'unitedw'
STEP_TYPE = 'FIRSTWORK'
REPORT_KEYS = ('scanned', 'cases_created', 'steps_created',
               'skipped', 'invalid', 'failed')

LEGACY_SQL = """
    SELECT id, nik, nik_raw, nama, tanggal_lahir, branch_code, registration_no
    FROM first_work_submissions
    WHERE (source IS NULL OR source <> %s)
    ORDER BY id
"""


def _mask_nik(nik):
    """Tampilkan hanya 4 digit terakhir di log."""
    digits = ''.join(ch for ch in str(nik or '') if ch.isdigit())
    if not digits:
        return ''
    if len(digits) <= 4:
        return '•' * len(digits)
    return '•' * (len(digits) - 4) + digits[-4:]


def _log(submission_id, nik, status):
    print(f'[backfill] #{submission_id} NIK {_mask_nik(nik)} -> {status}')


def _fetch_legacy(conn):
    """Baca baris FirstWork lama (read-only). conn=None -> tidak ada baris."""
    if conn is None:
        return []
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(LEGACY_SQL, (EXCLUDED_SOURCE,))
        return list(cursor.fetchall() or [])
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def _load_state(conn):
    """Kembalikan (cases_by_nik, done_pairs) dari hasil Rilis A.

    `cases_by_nik` menjaga satu kasus per NIK; `done_pairs` berisi pasangan
    (NIK, cabang) yang sudah punya langkah FIRSTWORK — baik dari backfill
    sebelumnya maupun dari submit form/CV Online.
    """
    cases, steps = {}, set()
    if conn is None:
        return cases, set()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT case_id, nik FROM recruitment_cases')
        for row in cursor.fetchall() or []:
            cases[row['nik']] = row
        cursor.execute(
            'SELECT case_id, branch_code FROM recruitment_steps '
            'WHERE step_type=%s', (STEP_TYPE,))
        by_id = {c['case_id']: nik for nik, c in cases.items()}
        for row in cursor.fetchall() or []:
            nik = by_id.get(row['case_id'])
            if nik:
                steps.add((nik, row['branch_code']))
    finally:
        try:
            cursor.close()
        except Exception:
            pass
    return cases, steps


def _plan(rows, cases, done, report):
    """Kelompokkan baris yang perlu ditulis per NIK; isi report awal."""
    groups = {}
    pending = set(done)
    for row in rows:
        nik, raw = normalize_nik(row.get('nik') or row.get('nik_raw'))
        submission_id = row.get('id')
        if not nik:
            report['invalid'] += 1
            _log(submission_id, raw, 'invalid')
            continue
        branch = str(row.get('branch_code') or '').strip().upper()[:10]
        key = (nik, branch)
        if key in pending:
            report['skipped'] += 1
            _log(submission_id, nik, 'skipped')
            continue
        pending.add(key)
        groups.setdefault(nik, []).append({
            'id': submission_id,
            'branch': branch,
            'nama': row.get('nama'),
            'dob': row.get('tanggal_lahir'),
        })
    return groups


def backfill(conn=None, commit=False):
    """Backfill FirstWork lama. Return laporan hitungan (lihat REPORT_KEYS)."""
    if commit and conn is None:
        raise RuntimeError('DB master tidak tersedia untuk --commit')
    report = {key: 0 for key in REPORT_KEYS}
    rows = _fetch_legacy(conn)
    report['scanned'] = len(rows)
    cases, done = _load_state(conn)
    groups = _plan(rows, cases, done, report)

    for nik, items in groups.items():
        case_existed = nik in cases
        if not commit:
            report['cases_created'] += 0 if case_existed else 1
            report['steps_created'] += len(items)
            for item in items:
                _log(item['id'], nik, 'would insert')
            continue

        case_id = None
        try:
            for item in items:
                case_id = upsert_case_step(
                    nik, item['nama'], item['dob'], item['branch'],
                    STEP_TYPE, str(item['id']), evidence_type=SOURCE,
                    conn=conn)
                _log(item['id'], nik, 'inserted')
            conn.commit()
        except Exception as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            report['failed'] += len(items)
            # Jenis exception saja — pesannya bisa memuat data pribadi.
            print(f'[backfill] NIK {_mask_nik(nik)} -> failed '
                  f'({type(exc).__name__})')
            continue

        report['cases_created'] += 0 if case_existed else 1
        report['steps_created'] += len(items)
        if case_id:
            cases[nik] = {'case_id': case_id, 'nik': nik,
                          'nama': items[0]['nama'],
                          'tanggal_lahir': items[0]['dob']}
        done.update((nik, item['branch']) for item in items)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Backfill kasus rekrutmen dari FirstWork lama WorkHub')
    parser.add_argument('--commit', action='store_true',
                        help='Tulis ke DB master (default: dry-run tanpa menulis)')
    args = parser.parse_args(argv)

    conn, own_conn = None, False
    try:
        conn = get_master_connection()
        own_conn = bool(conn)
    except Exception as exc:
        if args.commit:
            print(f'❌ DB master tidak tersedia ({type(exc).__name__}).',
                  file=sys.stderr)
            return 1
    if args.commit and not conn:
        print('❌ DB master tidak tersedia untuk --commit.', file=sys.stderr)
        return 1

    try:
        report = backfill(conn=conn, commit=args.commit)
    except Exception as exc:
        print(f'❌ Backfill gagal ({type(exc).__name__}).', file=sys.stderr)
        return 1
    finally:
        if own_conn and conn:
            try:
                conn.close()
            except Exception:
                pass

    print(json.dumps(report, ensure_ascii=False))
    if not args.commit:
        print('🧪 Dry-run — tidak ada yang ditulis. Ulangi dengan --commit.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
