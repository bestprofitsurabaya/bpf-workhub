"""Skema bukti absensi training portal (2 hari) — DB master.

Satu baris = satu kehadiran peserta pada satu hari training di satu cabang.
Kunci unik (case_id, branch_code, day) membuat submit ulang idempoten.
Bukti disimpan terpisah dari `applicant_attendance` (milik receptionist);
penyalinan ke H1/H2 dilakukan service hanya bila identitas pelamar cocok.
"""
from modules.config import get_master_connection

_DDL = """
    CREATE TABLE IF NOT EXISTS training_attendance (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        case_id VARCHAR(40) NOT NULL,
        nik CHAR(16) NOT NULL,
        branch_code VARCHAR(10) NOT NULL,
        day TINYINT NOT NULL,
        nama VARCHAR(150) NOT NULL DEFAULT '',
        attended_at DATETIME NOT NULL,
        applicant_id INT NULL,
        link_status ENUM('linked','unlinked','ambiguous')
            NOT NULL DEFAULT 'unlinked',
        ip VARCHAR(45) NOT NULL DEFAULT '',
        user_agent VARCHAR(255) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ta_case_branch_day (case_id, branch_code, day),
        KEY idx_ta_nik (nik),
        KEY idx_ta_applicant (applicant_id),
        KEY idx_ta_branch_date (branch_code, attended_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_training_attendance_schema(conn=None):
    """Pastikan tabel bukti absensi training ada (idempoten).

    `conn` opsional: bila diberikan dipakai langsung dan tidak ditutup di sini.
    Return True bila DDL berhasil (atau tabel sudah ada).
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_master_connection()
        if not conn:
            print('[training-schema] DB master unavailable, skip migration')
            return False
        cursor = conn.cursor()
        try:
            cursor.execute(_DDL)
            conn.commit()
            return True
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[training-schema] {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
