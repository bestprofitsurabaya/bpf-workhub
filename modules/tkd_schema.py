"""Skema TKD online (Rilis C) — idempoten, DB master.

Dijalankan saat startup dari app.py tepat setelah ensure_recruitment_schema().
Seluruh DDL memakai CREATE TABLE IF NOT EXISTS; kolom skor di
recruitment_cases ditambahkan lewat ALTER idempoten seperti pola
ensure_cv_online_nik_columns(). Aman diulang pada DB lama maupun baru.

Tabel:
- tkd_questions     : bank soal global (bukan per cabang)
- tkd_settings      : satu baris pengaturan ujian (id=1)
- tkd_attempts      : satu baris per percobaan ujian
- tkd_attempt_items : snapshot soal & jawaban per posisi
"""
import json

from modules.tkd_core import DEFAULT_QUOTA

TKD_TABLES = ('tkd_questions', 'tkd_settings',
              'tkd_attempts', 'tkd_attempt_items')


def _run(cursor, sql, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f'[tkd-schema] {label}: {e}')
        return False


_DDL = (
    ('tkd_questions', """
        CREATE TABLE IF NOT EXISTS tkd_questions (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          code VARCHAR(40) NOT NULL,
          category ENUM('REGULASI','PERUSAHAAN','PRODUK','HITUNG','PROFIL') NOT NULL,
          type ENUM('MCQ','NUMERIC','SHORT_TEXT','PROFILE_TEXT') NOT NULL,
          prompt TEXT NOT NULL,
          options JSON NULL,
          answer JSON NULL,
          points DECIMAL(5,2) NOT NULL DEFAULT 1,
          modal_tier VARCHAR(10) NULL,
          active TINYINT NOT NULL DEFAULT 0,
          sort_order INT NOT NULL DEFAULT 0,
          created_by VARCHAR(100) NOT NULL DEFAULT '',
          updated_by VARCHAR(100) NOT NULL DEFAULT '',
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uq_tkd_q_code (code),
          KEY idx_tkd_q_cat (category, active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """),
    ('tkd_settings', """
        CREATE TABLE IF NOT EXISTS tkd_settings (
          id TINYINT PRIMARY KEY DEFAULT 1,
          question_count INT NOT NULL DEFAULT 20,
          duration_minutes INT NOT NULL DEFAULT 25,
          pass_score DECIMAL(5,2) NOT NULL DEFAULT 70,
          max_attempts INT NOT NULL DEFAULT 2,
          quota JSON NULL,
          shuffle_options TINYINT NOT NULL DEFAULT 1,
          active TINYINT NOT NULL DEFAULT 0,
          updated_by VARCHAR(100) NOT NULL DEFAULT '',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """),
    ('tkd_attempts', """
        CREATE TABLE IF NOT EXISTS tkd_attempts (
          id VARCHAR(40) NOT NULL,
          case_id VARCHAR(40) NOT NULL,
          attempt_no INT NOT NULL,
          branch_code VARCHAR(10) NOT NULL DEFAULT '',
          modal_tier VARCHAR(10) NOT NULL DEFAULT '',
          status ENUM('BERLANGSUNG','SELESAI','KEDALUWARSA') NOT NULL,
          settings_snapshot JSON NOT NULL,
          pass_score_snapshot DECIMAL(5,2) NOT NULL,
          started_at DATETIME NOT NULL,
          expires_at DATETIME NOT NULL,
          submitted_at DATETIME NULL,
          score DECIMAL(5,2) NULL,
          total_points DECIMAL(6,2) NOT NULL DEFAULT 0,
          correct_count INT NOT NULL DEFAULT 0,
          passed TINYINT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_tkd_a_case_no (case_id, attempt_no),
          KEY idx_tkd_a_case (case_id, status),
          KEY idx_tkd_a_branch (branch_code, submitted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """),
    ('tkd_attempt_items', """
        CREATE TABLE IF NOT EXISTS tkd_attempt_items (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          attempt_id VARCHAR(40) NOT NULL,
          question_id BIGINT NOT NULL,
          position INT NOT NULL,
          snapshot JSON NOT NULL,
          answer JSON NULL,
          answered_at DATETIME NULL,
          is_correct TINYINT NULL,
          points_awarded DECIMAL(5,2) NULL,
          UNIQUE KEY uq_tkd_i_attempt_pos (attempt_id, position),
          KEY idx_tkd_i_attempt (attempt_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """),
)

# Tujuh kolom skor resmi di kasus (spec §3.5). AFTER menjaga urutan kolom
# sama dengan CREATE TABLE recruitment_cases di init.sql.
CASE_SCORE_COLUMNS = (
    ('tkd_score', 'ALTER TABLE recruitment_cases '
                  'ADD COLUMN tkd_score DECIMAL(5,2) NULL AFTER merged_from'),
    ('tkd_score_source', 'ALTER TABLE recruitment_cases '
                         "ADD COLUMN tkd_score_source ENUM('AUTO','MANUAL') NULL "
                         'AFTER tkd_score'),
    ('tkd_score_note', 'ALTER TABLE recruitment_cases '
                       'ADD COLUMN tkd_score_note VARCHAR(500) NULL '
                       'AFTER tkd_score_source'),
    ('tkd_score_updated_by', 'ALTER TABLE recruitment_cases '
                             'ADD COLUMN tkd_score_updated_by VARCHAR(100) NULL '
                             'AFTER tkd_score_note'),
    ('tkd_score_updated_at', 'ALTER TABLE recruitment_cases '
                             'ADD COLUMN tkd_score_updated_at DATETIME NULL '
                             'AFTER tkd_score_updated_by'),
    ('tkd_best_attempt_id', 'ALTER TABLE recruitment_cases '
                            'ADD COLUMN tkd_best_attempt_id VARCHAR(40) NULL '
                            'AFTER tkd_score_updated_at'),
    ('tkd_passed', 'ALTER TABLE recruitment_cases '
                   'ADD COLUMN tkd_passed TINYINT NULL '
                   'AFTER tkd_best_attempt_id'),
)


def ensure_tkd_schema(conn=None):
    """Pastikan tabel TKD & kolom skor kasus ada di DB master (idempoten).

    `conn` opsional: bila diberikan dipakai langsung dan TIDAK ditutup di sini.
    Return True bila seluruh DDL, seed settings, dan ALTER berhasil.
    """
    own = conn is None
    try:
        if conn is None:
            from modules.config import get_master_connection
            conn = get_master_connection()
        if not conn:
            print('[tkd-schema] DB master unavailable, skip migration')
            return False

        cursor = conn.cursor()
        try:
            results = [_run(cursor, sql, label) for label, sql in _DDL]

            try:
                cursor.execute(
                    'INSERT IGNORE INTO tkd_settings (id, quota) VALUES (1, %s)',
                    (json.dumps(DEFAULT_QUOTA),))
                results.append(True)
            except Exception as e:
                print(f'[tkd-schema] seed settings: {e}')
                results.append(False)

            try:
                placeholders = ', '.join(['%s'] * len(CASE_SCORE_COLUMNS))
                cursor.execute(
                    'SELECT COLUMN_NAME FROM information_schema.COLUMNS '
                    'WHERE TABLE_SCHEMA=DATABASE() '
                    "AND TABLE_NAME='recruitment_cases' "
                    f'AND COLUMN_NAME IN ({placeholders})',
                    tuple(name for name, _ in CASE_SCORE_COLUMNS))
                rows = cursor.fetchall() or []
                existing = set()
                for row in rows:
                    if isinstance(row, dict):
                        name = row.get('COLUMN_NAME')
                    elif isinstance(row, (tuple, list)):
                        name = row[0]
                    else:
                        name = row
                    existing.add(str(name or '').lower())
            except Exception as e:
                print(f'[tkd-schema] information_schema kolom: {e}')
                existing = set()

            for column, sql in CASE_SCORE_COLUMNS:
                if column in existing:
                    results.append(True)
                    continue
                try:
                    cursor.execute(sql)
                    results.append(True)
                except Exception as e:
                    text = str(e).lower()
                    if '1060' in text or 'duplicate column' in text:
                        results.append(True)  # worker lain menambah lebih dulu
                    else:
                        print(f'[tkd-schema] {column}: {e}')
                        results.append(False)

            conn.commit()
            return all(results)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[tkd-schema] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
