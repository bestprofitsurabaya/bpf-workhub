"""Schema First Work (Absensi FirstWork) — idempoten.

Dijalankan saat startup dari app.py. Aman diulang: CREATE TABLE IF NOT EXISTS,
index inline, dan seed referrer hanya menambah baris yang belum ada.

Tabel:
- first_work_submissions : satu baris = satu pengisian form / satu trainee
- first_work_events      : riwayat aksi (submit, verifikasi, koreksi)
- first_work_referrers   : master nama pengundang/pemberi informasi lowongan
- first_work_sheet_stage : staging mentah migrasi sheet (audit/remigrasi)
- first_work_branch_forms: token form publik per cabang (v2.82.0)
- first_work_id_counters : counter ID Fingerprint & ID BPF (v2.83.0)
"""
import secrets

from modules.config import get_db_connection


def _run(cursor, sql, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f'[first-work-schema] {label}: {e}')
        return False


def ensure_first_work_schema(conn=None):
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[first-work-schema] DB unavailable, skip migration')
            return False

        cursor = conn.cursor()

        # --- master referrer ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_referrers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                aliases_json JSON NULL,
                user_id INT NULL,
                branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
                active TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fwr_name (name),
                KEY idx_fwr_user (user_id),
                KEY idx_fwr_active (active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_referrers')

        # --- submission utama ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_submissions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                registration_no VARCHAR(40) NOT NULL,
                source VARCHAR(20) NOT NULL DEFAULT 'form',
                source_uid VARCHAR(64) NOT NULL,
                sheet_row INT NULL,
                sheet_seq VARCHAR(20) DEFAULT '',
                submitted_at DATETIME NOT NULL,
                email VARCHAR(150) DEFAULT '',
                nik VARCHAR(32) DEFAULT '',
                nik_raw VARCHAR(32) DEFAULT '',
                nik_valid TINYINT(1) NOT NULL DEFAULT 0,
                nama VARCHAR(150) NOT NULL,
                pendidikan_raw VARCHAR(100) DEFAULT '',
                pendidikan_norm VARCHAR(30) DEFAULT '',
                referensi_raw VARCHAR(150) DEFAULT '',
                referensi_norm VARCHAR(100) DEFAULT '',
                referrer_id INT NULL,
                referrer_needs_review TINYINT(1) NOT NULL DEFAULT 0,
                no_hp VARCHAR(30) DEFAULT '',
                no_hp_norm VARCHAR(20) DEFAULT '',
                branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
                ktp_file VARCHAR(255) DEFAULT '',
                ktp_drive_url VARCHAR(500) DEFAULT '',
                photoid_url VARCHAR(500) DEFAULT '',
                merged_doc_id VARCHAR(100) DEFAULT '',
                merged_doc_url VARCHAR(500) DEFAULT '',
                merge_status VARCHAR(255) DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'submitted',
                verification_note VARCHAR(500) DEFAULT '',
                verified_by VARCHAR(100) DEFAULT '',
                verified_at DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fw_registration (registration_no),
                UNIQUE KEY uq_fw_source_uid (source_uid),
                KEY idx_fw_status (status),
                KEY idx_fw_branch (branch_code),
                KEY idx_fw_submitted (submitted_at),
                KEY idx_fw_nik (nik),
                KEY idx_fw_hp (no_hp_norm),
                KEY idx_fw_referrer (referrer_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_submissions')

        # --- event/audit ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_events (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                submission_id BIGINT NOT NULL,
                event VARCHAR(30) NOT NULL,
                status_from VARCHAR(30) DEFAULT '',
                status_to VARCHAR(30) DEFAULT '',
                note VARCHAR(500) DEFAULT '',
                actor VARCHAR(100) NOT NULL,
                actor_role VARCHAR(30) DEFAULT '',
                ip VARCHAR(45) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                KEY idx_fwe_submission (submission_id),
                CONSTRAINT fk_fwe_submission FOREIGN KEY (submission_id)
                    REFERENCES first_work_submissions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_events')

        # --- staging migrasi ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_sheet_stage (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                source_uid VARCHAR(64) NOT NULL,
                sheet_row INT NULL,
                payload_json JSON NULL,
                normalized_json JSON NULL,
                import_status VARCHAR(20) DEFAULT 'pending',
                import_note VARCHAR(255) DEFAULT '',
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fws_uid (source_uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_sheet_stage')

        # --- ID Fingerprint & ID BPF (v2.83.0) ---
        # Setiap pengisian form wajib punya ID Fingerprint & ID BPF. Keduanya
        # mengalir dari dua kolom counter sheet (header '28161' = seri B,
        # '6495' = seri C) dan pemetaannya bisa diatur traineer.
        _run(cursor, """
            ALTER TABLE first_work_submissions
                ADD COLUMN IF NOT EXISTS fingerprint_no INT NULL AFTER sheet_seq,
                ADD COLUMN IF NOT EXISTS bpf_no INT NULL AFTER fingerprint_no,
                ADD INDEX IF NOT EXISTS idx_fw_fingerprint (fingerprint_no),
                ADD INDEX IF NOT EXISTS idx_fw_bpf (bpf_no)
        """, 'first_work_submissions.id_columns')

        # v2.88.0: versi scan KTP (lurus + watermark) dan hash integritasnya.
        _run(cursor, """
            ALTER TABLE first_work_submissions
                ADD COLUMN IF NOT EXISTS ktp_scan_file VARCHAR(255) DEFAULT '' AFTER ktp_file,
                ADD COLUMN IF NOT EXISTS ktp_sha256 CHAR(64) DEFAULT '' AFTER ktp_scan_file
        """, 'first_work_submissions.ktp_scan_columns')

        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_id_counters (
                series VARCHAR(4) NOT NULL PRIMARY KEY,
                last_value INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_id_counters')

        # --- tautan form per cabang (v2.82.0) ---
        # Satu cabang = satu token unik. Token ini membuat tautan form cabang A
        # tidak bisa dipakai mengirim isian atas nama cabang B (data pribadi
        # tidak tertukar), dan menjadi dasar tautan form yang berbeda per cabang.
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS first_work_branch_forms (
                branch_code VARCHAR(10) NOT NULL PRIMARY KEY,
                form_token VARCHAR(64) NOT NULL,
                active TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fwbf_token (form_token)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'first_work_branch_forms')
        try:
            cursor.execute("SELECT code FROM branches WHERE is_active=1")
            active_codes = [str((row[0] if isinstance(row, tuple) else row) or '').strip().upper()
                            for row in (cursor.fetchall() or [])]
            seeded = 0
            for code in [c for c in active_codes if c]:
                cursor.execute(
                    'SELECT form_token FROM first_work_branch_forms WHERE branch_code=%s',
                    (code,))
                if cursor.fetchone():
                    continue
                cursor.execute(
                    'INSERT INTO first_work_branch_forms (branch_code, form_token) '
                    'VALUES (%s, %s)', (code, secrets.token_urlsafe(24)))
                seeded += 1
            if seeded:
                print(f'[first-work-schema] token form cabang: {seeded} baru')
        except Exception as e:
            print(f'[first-work-schema] token form cabang dilewati: {e}')

        # --- seed referrer dari data pelamar (nama upline) ---
        # Nama referrer historis ada di applicants.upline; belum tentu punya akun.
        try:
            cursor.execute("""
                INSERT IGNORE INTO first_work_referrers (name, branch_code)
                SELECT DISTINCT UPPER(TRIM(upline)), 'SBY'
                FROM applicants
                WHERE TRIM(COALESCE(upline, '')) <> ''
            """)
            print(f'[first-work-schema] seed referrer: {cursor.rowcount} baru')
        except Exception as e:
            print(f'[first-work-schema] seed referrer dilewati: {e}')

        # --- seed dari akun marketing/traineer yang sudah ada ---
        try:
            cursor.execute("""
                INSERT IGNORE INTO first_work_referrers (name, user_id, branch_code)
                SELECT DISTINCT UPPER(TRIM(full_name)), id,
                       COALESCE(NULLIF(TRIM(branch_code), ''), 'SBY')
                FROM users
                WHERE role IN ('marketing', 'traineer')
                  AND TRIM(COALESCE(full_name, '')) <> ''
            """)
            print(f'[first-work-schema] seed akun referrer: {cursor.rowcount} baru')
        except Exception as e:
            print(f'[first-work-schema] seed akun referrer dilewati: {e}')

        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f'[first-work-schema] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
