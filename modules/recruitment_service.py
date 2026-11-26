"""Upsert kasus & langkah rekrutmen (Rilis A/C).

Satu NIK = satu kasus di DB master, berapa pun cabang yang dipakai. Setiap
submit CV Online / FirstWork menulis satu baris `recruitment_steps` dengan
bukti (nomor registrasi) dan menambah `case_branch_history` bila cabang itu
belum pernah dipakai kasus tersebut. Sejak Rilis C, `ensure_case` juga dipakai
langsung oleh intake manual dan penautan NIK pelamar lama.

Fungsi ini TIDAK pernah commit/rollback/close koneksi yang diberikan pemanggil:
ia berjalan di dalam transaksi submit yang sama, sehingga kegagalannya
membatalkan submit juga (tidak ada kasus/langkah yatim). Dipanggil tanpa
`conn`, fungsi membuka, meng-commit, dan menutup koneksi master sendiri.
"""
import uuid
from datetime import datetime

from modules.config import get_master_connection
from modules.helpers import normalize_nik

# Task ini hanya menyambung dua form produksi. TRAINING/TKD menyusul.
VALID_STEP_TYPES = frozenset(('CV', 'FIRSTWORK'))


def _new_case_id(nik):
    """Buat ID kasus opaque; NIK tidak pernah tertanam di primary key.

    `nik` tetap diterima untuk menjaga tanda tangan fungsi, tetapi identitas
    satu-orang-satu-kasus dijaga oleh UNIQUE KEY `nik`, bukan oleh case_id.
    ID acak juga menghindari tabrakan saat dua NIK berbagi 4 digit terakhir.
    """
    return 'RC-' + uuid.uuid4().hex[:12]


def ensure_case(nik, nama=None, branch_code='', dob=None,
                source='manual', conn=None):
    """Pastikan satu kasus untuk NIK + jejak cabang, lalu kembalikan case_id.

    Nama dan tanggal lahir yang sudah ada tidak pernah ditimpa oleh cabang
    lain. `source` diterima agar pemanggil dapat menyatakan asal kasus
    (manual/cv/firstwork); event audit ditulis pemanggil, bukan di sini.

    Bila `conn` diberikan, perubahan ikut transaksi pemanggil (tanpa commit).
    """
    nik, _raw = normalize_nik(nik)
    if not nik:
        raise ValueError('NIK harus 16 digit angka')
    own = conn is None
    if own:
        conn = get_master_connection()
        if not conn:
            raise RuntimeError('DB master tidak tersedia untuk upsert kasus')

    cursor = conn.cursor(dictionary=True)
    try:
        now = datetime.now()
        cursor.execute(
            'SELECT case_id, nama, tanggal_lahir FROM recruitment_cases '
            'WHERE nik=%s', (nik,))
        row = cursor.fetchone()

        if row:
            case_id = row['case_id']
            sets, params = [], []
            if not row.get('nama') and nama:
                sets.append('nama=%s')
                params.append(str(nama).strip()[:150])
            if not row.get('tanggal_lahir') and dob:
                sets.append('tanggal_lahir=%s')
                params.append(str(dob)[:10])
            if sets:
                params.append(case_id)
                cursor.execute(
                    'UPDATE recruitment_cases SET ' + ', '.join(sets)
                    + ' WHERE case_id=%s', tuple(params))
        else:
            case_id = _new_case_id(nik)
            cursor.execute("""
                INSERT INTO recruitment_cases
                    (case_id, nik, nama, tanggal_lahir, first_seen_at, first_branch)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (case_id, nik, str(nama or '').strip()[:150],
                  str(dob)[:10] if dob else None, now,
                  str(branch_code or '').strip().upper()[:10]))

        cursor.execute("""
            INSERT INTO case_branch_history
                (case_id, branch_code, first_seen_at, last_seen_at)
            VALUES (%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE last_seen_at=VALUES(last_seen_at)
        """, (case_id, str(branch_code or '').strip().upper()[:10], now, now))

        if own:
            conn.commit()
        return case_id
    except Exception:
        if own:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        if own:
            try:
                conn.close()
            except Exception:
                pass


def upsert_case_step(nik, nama, dob, branch_code, step_type, evidence_id,
                     evidence_type=None, conn=None):
    """Pastikan kasus + langkah ada, lalu kembalikan case_id.

    `step_type` hanya CV/FIRSTWORK pada rilis ini. Exception diteruskan agar
    submit ikut rollback bila master gagal.
    """
    if step_type not in VALID_STEP_TYPES:
        raise ValueError(f'step_type {step_type!r} belum didukung')
    nik, _raw = normalize_nik(nik)
    if not nik:
        raise ValueError('NIK harus 16 digit angka')

    own = conn is None
    db = conn or get_master_connection()
    if not db:
        raise RuntimeError('DB master tidak tersedia untuk upsert kasus')

    cursor = None
    try:
        case_id = ensure_case(nik, nama, branch_code, dob=dob, conn=db)
        now = datetime.now()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO recruitment_steps
                (case_id, step_type, status, branch_code, evidence_type,
                 evidence_id, completed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                status=VALUES(status), evidence_type=VALUES(evidence_type),
                evidence_id=VALUES(evidence_id), completed_at=VALUES(completed_at)
        """, (case_id, step_type, 'SELESAI',
              str(branch_code or '').strip().upper()[:10],
              str(evidence_type or '')[:30], str(evidence_id or '')[:64], now))
        if own:
            db.commit()
        return case_id
    except Exception:
        if own:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if own:
            try:
                db.close()
            except Exception:
                pass
