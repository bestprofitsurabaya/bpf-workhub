"""Skema master karyawan dan absensi (Rilis D — Task D1).

Semua DDL aditif dan idempoten. `employees` berada di DB master dengan NIK
global (NULL diperbolehkan untuk baris legacy yang belum dilengkapi GA HR).
"""
from modules.config import get_master_connection


_DDL = (
    ('employees', """
        CREATE TABLE IF NOT EXISTS employees (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            employee_no VARCHAR(30) NOT NULL,
            nik CHAR(16) NULL,
            nama VARCHAR(150) NOT NULL,
            nama_norm VARCHAR(150) NOT NULL DEFAULT '',
            tempat_lahir VARCHAR(100) NULL,
            tanggal_lahir DATE NULL,
            jenis_kelamin VARCHAR(20) NULL,
            agama VARCHAR(40) NULL,
            status_perkawinan VARCHAR(40) NULL,
            kewarganegaraan VARCHAR(40) NULL,
            golongan_darah VARCHAR(10) NULL,
            alamat VARCHAR(2000) NULL,
            rt_rw VARCHAR(30) NULL,
            kel_desa VARCHAR(100) NULL,
            kecamatan VARCHAR(100) NULL,
            domisili VARCHAR(100) NULL,
            no_hp VARCHAR(30) NULL,
            no_hp_norm VARCHAR(30) NULL,
            email VARCHAR(150) NULL,
            kontak_darurat VARCHAR(255) NULL,
            jabatan VARCHAR(100) NOT NULL DEFAULT 'Business Consultant',
            branch_code VARCHAR(10) NOT NULL DEFAULT '',
            tanggal_masuk DATE NULL,
            status_kepegawaian VARCHAR(50) NULL,
            atasan VARCHAR(150) NULL,
            referensi VARCHAR(150) NULL,
            pendidikan_terakhir VARCHAR(100) NULL,
            sekolah_menengah VARCHAR(150) NULL,
            perguruan_tinggi VARCHAR(150) NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'manual',
            source_uid VARCHAR(100) NULL,
            case_id VARCHAR(40) NULL,
            needs_nik TINYINT(1) NOT NULL DEFAULT 0,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            deactivated_at DATETIME NULL,
            deactivated_by VARCHAR(100) NULL,
            deactivation_reason VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_emp_no (employee_no),
            UNIQUE KEY uq_emp_nik (nik),
            UNIQUE KEY uq_emp_source (source, source_uid),
            KEY idx_emp_nama_norm (nama_norm),
            KEY idx_emp_branch (branch_code),
            KEY idx_emp_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ('employee_attendance_events', """
        CREATE TABLE IF NOT EXISTS employee_attendance_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            employee_id BIGINT NOT NULL,
            nik CHAR(16) NULL,
            branch_code VARCHAR(10) NOT NULL DEFAULT '',
            direction ENUM('OUT','IN') NOT NULL,
            event_at DATETIME NOT NULL,
            actor_username VARCHAR(100) NOT NULL DEFAULT '',
            actor_name VARCHAR(150) NOT NULL DEFAULT '',
            note VARCHAR(500) NULL,
            voided_at DATETIME NULL,
            voided_by VARCHAR(100) NULL,
            void_reason VARCHAR(500) NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_eae_employee (employee_id, event_at),
            KEY idx_eae_branch (branch_code, event_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ('employee_counters', """
        CREATE TABLE IF NOT EXISTS employee_counters (
            branch_code VARCHAR(10) NOT NULL,
            series VARCHAR(20) NOT NULL,
            last_value INT NOT NULL DEFAULT 0,
            PRIMARY KEY (branch_code, series)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
)


def ensure_employee_schema(conn=None):
    """Pastikan tabel karyawan ada; False bila tidak ada koneksi master."""
    own = conn is None
    if own:
        conn = get_master_connection()
        if not conn:
            return False
    cursor = conn.cursor()
    try:
        for _name, ddl in _DDL:
            cursor.execute(ddl)
        if own:
            conn.commit()
        return True
    except Exception as exc:
        if own:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f'[employee-schema] gagal: {str(exc)[:160]}')
        return False
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
