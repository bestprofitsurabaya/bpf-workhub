"""Schema Registrasi CV Online (v2.113.0) — idempoten.

Dijalankan saat startup dari app.py. Aman diulang: CREATE TABLE IF NOT EXISTS,
index inline, dan seed token form cabang hanya menambah baris yang belum ada.

Tabel:
- cv_online_submissions   : satu baris = satu pengisian form registrasi CV
- cv_online_events        : riwayat aksi (kirim, verifikasi, tolak, buka ulang)
- cv_online_branch_forms  : token form publik per cabang

Form ini publik (tanpa login), tetapi datanya hanya dapat dilihat oleh role
`traineer`, `ga_hr`, dan `admin` (termasuk Admin Pusat).
"""
import secrets

from modules.config import get_db_connection


def _run(cursor, sql, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f'[cv-online-schema] {label}: {e}')
        return False


def ensure_cv_online_schema(conn=None):
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[cv-online-schema] DB unavailable, skip migration')
            return False

        cursor = conn.cursor()

        # --- submission utama ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS cv_online_submissions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                registration_no VARCHAR(40) NOT NULL,
                source VARCHAR(20) NOT NULL DEFAULT 'form',
                submitted_at DATETIME NOT NULL,
                sumber_informasi VARCHAR(150) DEFAULT '',
                diundang_oleh VARCHAR(150) DEFAULT '',
                kontak_serumah TEXT NULL,
                kontak_tidak_serumah TEXT NULL,
                user_ef VARCHAR(20) DEFAULT '',
                nama VARCHAR(150) NOT NULL,
                tempat_lahir VARCHAR(100) DEFAULT '',
                tanggal_lahir DATE NULL,
                jenis_kelamin VARCHAR(10) DEFAULT '',
                domisili VARCHAR(50) DEFAULT '',
                alamat TEXT NULL,
                no_hp VARCHAR(30) DEFAULT '',
                no_hp_norm VARCHAR(20) DEFAULT '',
                pendidikan_terakhir VARCHAR(50) DEFAULT '',
                sekolah_menengah VARCHAR(150) DEFAULT '',
                perguruan_tinggi VARCHAR(150) DEFAULT '',
                pengalaman_status VARCHAR(20) DEFAULT '',
                pengalaman_lama VARCHAR(30) DEFAULT '',
                posisi_terakhir VARCHAR(150) DEFAULT '',
                pengalaman_1 TEXT NULL,
                pengalaman_2 TEXT NULL,
                branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
                status VARCHAR(20) NOT NULL DEFAULT 'submitted',
                review_note VARCHAR(500) DEFAULT '',
                reviewed_by VARCHAR(100) DEFAULT '',
                reviewed_at DATETIME NULL,
                consent_at DATETIME NULL,
                nik CHAR(16) NULL,
                nik_raw VARCHAR(32) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_cvo_registration (registration_no),
                KEY idx_cvo_status (status),
                KEY idx_cvo_branch (branch_code),
                KEY idx_cvo_submitted (submitted_at),
                KEY idx_cvo_hp (no_hp_norm),
                KEY idx_cvo_user (user_ef)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'cv_online_submissions')

        # --- event/audit ---
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS cv_online_events (
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
                KEY idx_cvoe_submission (submission_id),
                CONSTRAINT fk_cvoe_submission FOREIGN KEY (submission_id)
                    REFERENCES cv_online_submissions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'cv_online_events')

        # --- tautan form per cabang ---
        # Satu cabang = satu token unik. Tautan cabang A tidak bisa dipakai
        # mengirim isian atas nama cabang B, sehingga data pribadi pelamar
        # tidak tertukar antar cabang.
        _run(cursor, """
            CREATE TABLE IF NOT EXISTS cv_online_branch_forms (
                branch_code VARCHAR(10) NOT NULL PRIMARY KEY,
                form_token VARCHAR(64) NOT NULL,
                active TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_cvobf_token (form_token)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, 'cv_online_branch_forms')

        try:
            cursor.execute("SELECT code FROM branches WHERE is_active=1")
            active_codes = [str((row[0] if isinstance(row, tuple) else row) or '').strip().upper()
                            for row in (cursor.fetchall() or [])]
            seeded = 0
            for code in [c for c in active_codes if c]:
                cursor.execute(
                    'SELECT form_token FROM cv_online_branch_forms WHERE branch_code=%s',
                    (code,))
                if cursor.fetchone():
                    continue
                cursor.execute(
                    'INSERT INTO cv_online_branch_forms (branch_code, form_token) '
                    'VALUES (%s, %s)', (code, secrets.token_urlsafe(24)))
                seeded += 1
            if seeded:
                print(f'[cv-online-schema] token form cabang: {seeded} baru')
        except Exception as e:
            print(f'[cv-online-schema] token form cabang dilewati: {e}')

        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f'[cv-online-schema] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


# ================================================================
# NIK pada CV Online (Rilis A) — ALTER idempoten untuk DB yang sudah ada.
# CREATE TABLE IF NOT EXISTS di atas hanya berlaku untuk instalasi baru;
# DB produksi yang sudah punya tabel ini butuh penambahan kolom eksplisit.
# ================================================================
_NIK_DDL = (
    ('nik', 'ALTER TABLE cv_online_submissions '
            'ADD COLUMN nik CHAR(16) NULL AFTER consent_at'),
    ('nik_raw', 'ALTER TABLE cv_online_submissions '
                'ADD COLUMN nik_raw VARCHAR(32) NULL AFTER nik'),
)


def ensure_cv_online_nik_columns(conn=None):
    """Pastikan kolom nik & nik_raw ada di cv_online_submissions (DB master).

    Idempoten: kolom yang sudah ada dilewati; error "duplicate column"
    (1060) juga dianggap sukses untuk antisipasi dua worker startup bersamaan.
    `conn` opsional — bila diberikan dipakai langsung dan TIDAK ditutup di sini.
    """
    own = conn is None
    try:
        if conn is None:
            from modules.config import get_master_connection
            conn = get_master_connection()
        if not conn:
            print('[cv-online-nik] DB master unavailable, skip migration')
            return False

        cursor = conn.cursor()
        try:
            try:
                cursor.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() "
                    "AND TABLE_NAME='cv_online_submissions' "
                    "AND COLUMN_NAME IN ('nik','nik_raw')")
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
            except Exception:
                existing = set()

            results = []
            for column, sql in _NIK_DDL:
                if column in existing:
                    results.append(True)
                    continue
                try:
                    cursor.execute(sql)
                    results.append(True)
                except Exception as e:
                    text = str(e).lower()
                    if '1060' in text or 'duplicate column' in text:
                        results.append(True)
                    else:
                        print(f'[cv-online-nik] {column}: {e}')
                        results.append(False)
            conn.commit()
            return all(results)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[cv-online-nik] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
