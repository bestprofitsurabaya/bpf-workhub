"""Impor pengajuan FirstWork unitedw (CSV) ke DB master WorkHub (Rilis B Task 4).

Pemakaian:
    python3 scripts/import_unitedw_firstwork.py --csv /path/unitedw.csv        # dry-run
    python3 scripts/import_unitedw_firstwork.py --csv /path/unitedw.csv --commit

Sifat impor:
  - Kunci alami: `source='unitedw'` + `source_uid` = `ID FP` dari CSV. Baris yang
    sama tidak pernah ditambahkan dua kali (idempoten).
  - NIK ganda digabung ke SATU `recruitment_cases` (kunci UNIQUE `nik`) dengan
    catatan `merged_from` berisi semua ID FP yang tergabung.
  - Email ganda ditandai di `verification_note` (bukan dibuang).
  - NIK wajib 16 digit angka; yang tidak valid masuk hitungan `invalid`.
  - `ID FP`/`ID BPF` dipertahankan apa adanya sebagai `fingerprint_no`/`bpf_no`;
    tidak memakai counter / tidak dinomori ulang.
  - NIK di log/report cukup 4 digit terakhir. Path `File KTP` hanya disimpan
    sebagai referensi sumber — file tidak diunduh/disalin.
  - Satu transaksi untuk seluruh berkas: `--commit` meng-commit sekali di akhir;
    kegagalan apa pun di-rollback (termasuk kasus/langkah dari upsert_case_step).
  - Dry-run adalah DEFAULT dan tidak menulis apa pun (hanya menghitung).

Skema (`first_work_submissions`, `recruitment_*`) dijamin oleh migrasi startup;
script ini sengaja tidak menjalankan DDL yang bisa meng-commit di tengah transaksi.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from modules.config import get_master_connection  # noqa: E402
from modules.helpers import normalize_nik  # noqa: E402
from modules.recruitment_service import upsert_case_step  # noqa: E402
from modules.routes_first_work import (  # noqa: E402
    DEMOGRAPHIC_FIELDS, DEMOGRAPHIC_MAXLEN, _clean, _next_reg_no,
    normalize_hp, normalize_name, normalize_pendidikan, parse_datetime)

SOURCE = 'unitedw'
REPORT_KEYS = ('inserted', 'skipped', 'merged', 'invalid')

# Nama tampilan unitedw -> branch_code WorkHub (desain E).
BRANCH_ID_PREFIX = {
    'JKT': 'EI', 'JKT2': 'EA', 'JMB': 'EB', 'MLG': 'EC', 'PTK': 'ED',
    'SBY': 'EF', 'BDG': 'EG', 'MDN': 'EH', 'BJM': 'EJ', 'PKU': 'EK',
    'LPG': 'EL', 'SMG': 'EM',
}
PREFIX_TO_CODE = {prefix: code for code, prefix in BRANCH_ID_PREFIX.items()}
# Alias diurutkan oleh map_branch berdasarkan panjang (paling spesifik dulu).
BRANCH_NAME_ALIASES = {
    'kantor pusat - equity tower, jakarta': 'JKT',
    'equity tower': 'JKT',
    'jakarta - pacific place mall': 'JKT2',
    'pacific place': 'JKT2',
    'bandar lampung': 'LPG',
    'lampung': 'LPG',
    'banjarmasin': 'BJM',
    'pontianak': 'PTK',
    'pekanbaru': 'PKU',
    'surabaya': 'SBY',
    'bandung': 'BDG',
    'malang': 'MLG',
    'semarang': 'SMG',
    'medan': 'MDN',
    'jambi': 'JMB',
}

CSV_DEMO_FIELDS = {
    'tempat_lahir': 'Tempat Lahir',
    'tanggal_lahir': 'Tanggal Lahir',
    'jenis_kelamin': 'Jenis Kelamin',
    'golongan_darah': 'Gol. Darah',
    'alamat': 'Alamat',
    'rt_rw': 'RT/RW',
    'kel_desa': 'Kel/Desa',
    'kecamatan': 'Kecamatan',
    'agama': 'Agama',
    'status_perkawinan': 'Status Perkawinan',
    'pekerjaan': 'Pekerjaan',
    'kewarganegaraan': 'Kewarganegaraan',
    'berlaku_hingga': 'Berlaku Hingga',
}

REQUIRED_HEADERS = (
    'ID FP', 'ID BPF', 'Email', 'NIK KTP', 'Nama Lengkap', 'Cabang',
    'Waktu kirim', 'Pendidikan', 'Referensi', 'No. Handphone', 'File KTP',
)

SUBMISSION_COLUMNS = (
    'registration_no', 'source', 'source_uid', 'submitted_at',
    'email', 'nik', 'nik_raw', 'nik_valid', 'nama',
) + tuple(DEMOGRAPHIC_FIELDS) + (
    'pendidikan_raw', 'pendidikan_norm', 'referensi_raw', 'referensi_norm',
    'no_hp', 'no_hp_norm', 'branch_code', 'fingerprint_no', 'bpf_no',
    'ktp_file', 'status', 'verification_note',
)


def map_branch(cabang='', id_fp=''):
    """Nama cabang unitedw (atau kode WorkHub) -> branch_code.

    Bila nama tidak dikenal, prefix dua huruf pada ID FP dipakai sebagai
    fallback — prefix itu berasal dari tabel resmi desain E dan selalu konsisten
    dengan cabang pengajuan.
    """
    name = _clean(cabang, 100)
    if name.upper() in BRANCH_ID_PREFIX:
        return name.upper()
    lowered = name.lower()
    for alias, code in sorted(BRANCH_NAME_ALIASES.items(),
                              key=lambda item: len(item[0]), reverse=True):
        if alias in lowered:
            return code
    prefix = str(id_fp or '').split('_', 1)[0].strip().upper()
    return PREFIX_TO_CODE.get(prefix, '')


def _mask_nik(nik):
    """Tampilkan hanya 4 digit terakhir di log (data pribadi)."""
    digits = ''.join(ch for ch in str(nik or '') if ch.isdigit())
    if not digits:
        return ''
    if len(digits) <= 4:
        return '•' * len(digits)
    return '•' * (len(digits) - 4) + digits[-4:]


def _log(source_uid, nik, status):
    print(f'[unitedw] {source_uid} NIK {_mask_nik(nik)} -> {status}')


def read_csv(path):
    """Baca CSV unitedw (BOM-tolerant). Header wajib divalidasi."""
    with open(path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [name for name in REQUIRED_HEADERS if name not in headers]
        if missing:
            raise ValueError('Kolom CSV wajib tidak ada: ' + ', '.join(missing))
        return [dict(row) for row in reader]


def _iso_date(value):
    """Tanggal demografi bebas -> ISO YYYY-MM-DD, atau None."""
    text = _clean(value, 30)
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    parsed = parse_datetime(text)
    return parsed.date().isoformat() if parsed else None


def _submitted_at(value):
    parsed = parse_datetime(value)
    return parsed or datetime.now()


def _demographic_values(row):
    values = {}
    for field in DEMOGRAPHIC_FIELDS:
        raw = row.get(CSV_DEMO_FIELDS.get(field, ''))
        if field == 'tanggal_lahir':
            values[field] = _iso_date(raw)
        else:
            values[field] = _clean(raw, DEMOGRAPHIC_MAXLEN[field]) or None
    return values


def normalize_row(row, email_counts, nik_counts):
    """Satu baris CSV -> payload first_work_submissions, atau None bila invalid."""
    nik, nik_raw = normalize_nik(row.get('NIK KTP'))
    if not nik:
        return None
    nama = _clean(row.get('Nama Lengkap'), 150)
    source_uid = _clean(row.get('ID FP'), 64)
    if not nama or not source_uid:
        return None

    fingerprint_no = source_uid
    bpf_no = _clean(row.get('ID BPF'), 30)
    branch_code = map_branch(row.get('Cabang'), fingerprint_no)
    # Email disimpan apa adanya; lower-case hanya dipakai untuk deteksi duplikat.
    email = _clean(row.get('Email'), 150)
    demo = _demographic_values(row)
    no_hp = _clean(row.get('No. Handphone'), 30)
    pendidikan_raw = _clean(row.get('Pendidikan'), 100)
    referensi_raw = _clean(row.get('Referensi'), 150)

    flags = []
    if email_counts[email.lower()] > 1:
        flags.append('EMAIL_DUPLIKAT')
    if nik_counts[nik] > 1:
        flags.append('NIK_MERGE')

    payload = {
        'source': SOURCE,
        'source_uid': source_uid,
        'submitted_at': _submitted_at(row.get('Waktu kirim')),
        'email': email,
        'nik': nik,
        'nik_raw': nik_raw,
        'nik_valid': 1,
        'nama': nama,
        'pendidikan_raw': pendidikan_raw,
        'pendidikan_norm': normalize_pendidikan(pendidikan_raw),
        'referensi_raw': referensi_raw,
        'referensi_norm': normalize_name(referensi_raw),
        'no_hp': no_hp,
        'no_hp_norm': normalize_hp(no_hp),
        'branch_code': branch_code,
        'fingerprint_no': fingerprint_no,
        'bpf_no': bpf_no,
        # Referensi sumber saja: file KTP tidak diunduh/disalin.
        'ktp_file': _clean(row.get('File KTP'), 255),
        'status': 'submitted',
        'verification_note': '; '.join(flags)[:500],
    }
    payload.update(demo)
    return payload


def _already_imported(conn, source_uid):
    if conn is None:
        return False
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT id FROM first_work_submissions '
            'WHERE source=%s AND source_uid=%s', (SOURCE, source_uid))
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def _insert_submission(conn, payload, registration_no):
    values = [registration_no]
    values += [payload.get(column) for column in SUBMISSION_COLUMNS[1:]]
    columns = ', '.join(SUBMISSION_COLUMNS)
    marks = ', '.join(['%s'] * len(SUBMISSION_COLUMNS))
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO first_work_submissions (' + columns + ') VALUES ('
            + marks + ')', tuple(values))
        return cursor.lastrowid
    finally:
        cursor.close()


def _insert_event(conn, submission_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO first_work_events
                (submission_id, event, status_from, status_to, note,
                 actor, actor_role)
            VALUES (%s,'created','','submitted','Impor unitedw','import','system')
        """, (submission_id,))
    finally:
        cursor.close()


def _set_merged_from(conn, nik, note):
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE recruitment_cases SET merged_from=%s WHERE nik=%s',
            (note[:255], nik))
    finally:
        cursor.close()


def import_unitedw(csv_path, conn=None, commit=False):
    """Impor satu CSV unitedw. Return {'inserted','skipped','merged','invalid'}.

    `conn` boleh None pada dry-run (tidak ada DB → semua baris dihitung baru).
    Saat `commit=True` seluruh tulisan terjadi dalam satu transaksi `conn`;
    pemanggil yang menyediakan `conn` tetap memilikinya (script tidak menutup).
    """
    rows = read_csv(csv_path)
    email_counts = Counter(_clean(r.get('Email'), 150).lower() for r in rows)
    nik_counts = Counter(nik for nik, _raw in
                         (normalize_nik(r.get('NIK KTP')) for r in rows) if nik)

    parsed, invalid = [], 0
    for row in rows:
        payload = normalize_row(row, email_counts, nik_counts)
        if payload is None:
            invalid += 1
            continue
        parsed.append(payload)

    # ID FP pertama per NIK menentukan baris "inserted"; sisanya "merged".
    first_uid = {}
    for payload in parsed:
        first_uid.setdefault(payload['nik'], payload['source_uid'])
    merged_notes = {}
    by_nik = defaultdict(list)
    for payload in parsed:
        by_nik[payload['nik']].append(payload['source_uid'])
    for nik, uids in by_nik.items():
        if len(uids) > 1:
            merged_notes[nik] = ('unitedw — digabung dari ID FP: '
                                 + ', '.join(uids))[:255]

    report = {key: 0 for key in REPORT_KEYS}
    seen_uids = set()
    own_conn = False
    if commit and conn is None:
        conn = get_master_connection()
        own_conn = bool(conn)
        if not conn:
            raise RuntimeError('DB master tidak tersedia untuk impor --commit')

    try:
        for payload in parsed:
            uid = payload['source_uid']
            if uid in seen_uids or _already_imported(conn, uid):
                report['skipped'] += 1
                _log(uid, payload['nik'], 'skipped')
                continue
            seen_uids.add(uid)

            is_merge = (payload['nik'] in merged_notes
                        and uid != first_uid[payload['nik']])
            key = 'merged' if is_merge else 'inserted'
            report[key] += 1
            _log(uid, payload['nik'], key)
            if not commit:
                continue

            registration_no = _next_reg_no(
                conn, payload['submitted_at'], payload['branch_code'])
            submission_id = _insert_submission(conn, payload, registration_no)
            _insert_event(conn, submission_id)
            upsert_case_step(
                payload['nik'], payload['nama'], payload['tanggal_lahir'],
                payload['branch_code'], 'FIRSTWORK', registration_no,
                evidence_type='unitedw', conn=conn)
            if payload['nik'] in merged_notes:
                _set_merged_from(conn, payload['nik'],
                                 merged_notes[payload['nik']])

        report['invalid'] = invalid
        if commit:
            conn.commit()
    except Exception:
        if commit and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if own_conn and conn:
            try:
                conn.close()
            except Exception:
                pass
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Impor pengajuan FirstWork unitedw ke DB master WorkHub')
    parser.add_argument('--csv', required=True, dest='csv_path',
                        help='Path CSV unitedw (di luar repo)')
    parser.add_argument('--commit', action='store_true',
                        help='Tulis ke DB (default: dry-run tanpa menulis)')
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
        report = import_unitedw(args.csv_path, conn=conn, commit=args.commit)
    except Exception as exc:
        # Pesan exception bisa memuat data pribadi — tampilkan jenisnya saja.
        print(f'❌ Impor gagal ({type(exc).__name__}).', file=sys.stderr)
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
