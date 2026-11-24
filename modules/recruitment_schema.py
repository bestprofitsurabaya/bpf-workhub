"""Skema kasus rekrutmen lintas cabang — idempoten, DB master.

Dijalankan saat startup dari app.py tepat setelah ensure_appointments_schema().
Seluruh DDL memakai CREATE TABLE IF NOT EXISTS, aman diulang pada DB lama
maupun instalasi baru. Kunci identitas kasus adalah NIK (16 digit), sehingga
satu orang hanya punya satu kasus walaupun mengisi di beberapa cabang.

Tabel:
- recruitment_cases     : satu baris = satu NIK (kasus rekrutmen)
- recruitment_steps     : empat langkah generik per kasus per cabang
- case_branch_history   : jejak cabang yang pernah dipakai suatu kasus
"""


def _run(cursor, sql, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f'[recruitment-schema] {label}: {e}')
        return False


_DDL = (
    ('recruitment_cases', """
        CREATE TABLE IF NOT EXISTS recruitment_cases (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(40) NOT NULL,
            nik CHAR(16) NOT NULL,
            nama VARCHAR(150) NOT NULL,
            tanggal_lahir DATE NULL,
            first_seen_at DATETIME NULL,
            first_branch VARCHAR(10) NOT NULL DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'AKTIF',
            merged_from VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rc_case_id (case_id),
            UNIQUE KEY uq_rc_nik (nik),
            KEY idx_rc_status (status),
            KEY idx_rc_first_branch (first_branch)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ('recruitment_steps', """
        CREATE TABLE IF NOT EXISTS recruitment_steps (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(40) NOT NULL,
            step_type ENUM('CV','TRAINING','TKD','FIRSTWORK') NOT NULL,
            status ENUM('BELUM','PENDING','SELESAI','DIKECUALIKAN')
                NOT NULL DEFAULT 'BELUM',
            branch_code VARCHAR(10) NOT NULL DEFAULT '',
            evidence_type VARCHAR(30) NOT NULL DEFAULT '',
            evidence_id VARCHAR(64) NOT NULL DEFAULT '',
            exception_reason VARCHAR(500) NULL,
            completed_at DATETIME NULL,
            actor VARCHAR(100) NOT NULL DEFAULT '',
            UNIQUE KEY uq_rs_case_step_branch (case_id, step_type, branch_code),
            KEY idx_rs_case (case_id),
            KEY idx_rs_branch (branch_code),
            KEY idx_rs_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ('case_branch_history', """
        CREATE TABLE IF NOT EXISTS case_branch_history (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(40) NOT NULL,
            branch_code VARCHAR(10) NOT NULL,
            first_seen_at DATETIME NULL,
            last_seen_at DATETIME NULL,
            UNIQUE KEY uq_cbh_case_branch (case_id, branch_code),
            KEY idx_cbh_case (case_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
)


def ensure_recruitment_schema(conn=None):
    """Pastikan tabel kasus rekrutmen ada di DB master (idempoten).

    `conn` opsional: bila diberikan dipakai langsung dan tidak ditutup di sini.
    Return True bila ketiga DDL berhasil (atau tabel sudah ada).
    """
    own = conn is None
    try:
        if conn is None:
            from modules.config import get_master_connection
            conn = get_master_connection()
        if not conn:
            print('[recruitment-schema] DB master unavailable, skip migration')
            return False

        cursor = conn.cursor()
        try:
            results = [_run(cursor, sql, label) for label, sql in _DDL]
            conn.commit()
            return all(results)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[recruitment-schema] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
