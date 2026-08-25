"""Sistem Overtime (v2.22) — schema migration.

Dua sumber data overtime:
1. `overtime_driver`      — SINKRONISASI dari Google Sheet read-only (diisi
   Google Form lama). Data di-refresh oleh GA HR (tombol Refresh di SPA);
   sumber dibaca server via URL publik / Google Apps Script Web App.
2. `overtime_ob_security` — MIGRASI PENUH data sheet lama + form publik baru
   (karyawan mengisi sendiri tanpa login, dropdown posisi & nama).

Aman dijalankan tiap startup (CREATE IF NOT EXISTS + guarded ALTER).
"""
from modules.config import get_db_connection


def _run(sql, cursor, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f"[overtime-schema] {label}: {e}")
        return False


def ensure_overtime_schema(conn=None):
    """Migrasi skema tabel overtime (idempoten)."""
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print("[overtime-schema] DB unavailable, skip migration")
            return False
        cursor = conn.cursor()

        # --- overtime_driver: sinkronisasi dari Google Sheet (refresh) ---
        _run("""
            CREATE TABLE IF NOT EXISTS overtime_driver (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sheet_row INT NOT NULL UNIQUE,
                submitted_at DATETIME NULL,
                email VARCHAR(150) DEFAULT '',
                nama VARCHAR(150) NOT NULL,
                tanggal DATE NULL,
                waktu_mulai VARCHAR(20) DEFAULT '',
                waktu_selesai VARCHAR(20) DEFAULT '',
                keterangan VARCHAR(500) DEFAULT '',
                foto_mulai VARCHAR(600) DEFAULT '',
                foto_selesai VARCHAR(600) DEFAULT '',
                notes VARCHAR(500) DEFAULT '',
                no_kendaraan VARCHAR(30) DEFAULT '',
                broker VARCHAR(150) DEFAULT '',
                manager VARCHAR(150) DEFAULT '',
                doc_url VARCHAR(600) DEFAULT '',
                gps_lat VARCHAR(20) DEFAULT '',
                gps_lon VARCHAR(20) DEFAULT '',
                gps_address VARCHAR(500) DEFAULT '',
                gps_kelurahan VARCHAR(100) DEFAULT '',
                gps_kecamatan VARCHAR(100) DEFAULT '',
                gps_kota VARCHAR(100) DEFAULT '',
                gps_provinsi VARCHAR(100) DEFAULT '',
                gps_kode_pos VARCHAR(10) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_otd_tanggal (tanggal),
                INDEX idx_otd_nama (nama)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "overtime_driver")

        # v2.22.1: kolom baru untuk data Driver lengkap (NO KENDARAAN, broker,
        # manager, dokumen merge). Guarded — aman bila tabel sudah dibuat duluan.
        for col, ddl in (
            ('no_kendaraan', "ALTER TABLE overtime_driver ADD COLUMN no_kendaraan VARCHAR(30) DEFAULT ''"),
            ('broker', "ALTER TABLE overtime_driver ADD COLUMN broker VARCHAR(150) DEFAULT ''"),
            ('manager', "ALTER TABLE overtime_driver ADD COLUMN manager VARCHAR(150) DEFAULT ''"),
            ('doc_url', "ALTER TABLE overtime_driver ADD COLUMN doc_url VARCHAR(600) DEFAULT ''"),
        ):
            _run(ddl, cursor, f"overtime_driver.{col}")

        # --- overtime_ob_security: migrasi penuh + submit form publik ---
        _run("""
            CREATE TABLE IF NOT EXISTS overtime_ob_security (
                id INT AUTO_INCREMENT PRIMARY KEY,
                display_id VARCHAR(30) NOT NULL UNIQUE,
                nama VARCHAR(150) NOT NULL,
                posisi ENUM('OB','Security') NOT NULL DEFAULT 'OB',
                tanggal DATE NULL,
                waktu_mulai VARCHAR(20) DEFAULT '',
                waktu_selesai VARCHAR(20) DEFAULT '',
                keterangan VARCHAR(500) DEFAULT '',
                foto_mulai VARCHAR(600) DEFAULT '',
                foto_selesai VARCHAR(600) DEFAULT '',
                email VARCHAR(150) DEFAULT '',
                source VARCHAR(20) DEFAULT 'form',
                source_uid VARCHAR(64) DEFAULT '',
                gps_lat VARCHAR(20) DEFAULT '',
                gps_lon VARCHAR(20) DEFAULT '',
                gps_address VARCHAR(500) DEFAULT '',
                gps_kelurahan VARCHAR(100) DEFAULT '',
                gps_kecamatan VARCHAR(100) DEFAULT '',
                gps_kota VARCHAR(100) DEFAULT '',
                gps_provinsi VARCHAR(100) DEFAULT '',
                gps_kode_pos VARCHAR(10) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_oto_source (source_uid),
                INDEX idx_oto_tanggal (tanggal),
                INDEX idx_oto_nama (nama),
                INDEX idx_oto_posisi (posisi)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "overtime_ob_security")

        # v2.27.1/v2.28.4: kolom GPS detail — paritas Driver vs OB/Security.
        # Sebelumnya kolom ini hanya ditambah manual di DB produksi (tidak ada
        # di kode migrasi → fresh deploy gagal saat submit OT/Trip dengan GPS).
        _GPS_COLUMNS = (
            ('gps_lat', "VARCHAR(20) DEFAULT ''"),
            ('gps_lon', "VARCHAR(20) DEFAULT ''"),
            ('gps_address', "VARCHAR(500) DEFAULT ''"),
            ('gps_kelurahan', "VARCHAR(100) DEFAULT ''"),
            ('gps_kecamatan', "VARCHAR(100) DEFAULT ''"),
            ('gps_kota', "VARCHAR(100) DEFAULT ''"),
            ('gps_provinsi', "VARCHAR(100) DEFAULT ''"),
            ('gps_kode_pos', "VARCHAR(10) DEFAULT ''"),
        )
        for table in ('overtime_driver', 'overtime_ob_security', 'trip_masters'):
            for col, ddl in _GPS_COLUMNS:
                _run(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}", cursor, f"{table}.{col}")

        # --- system_config: URL sumber sheet Driver + OB/Security ---
        # GA HR bisa mengganti dengan URL Google Apps Script Web App
        _run("""
            INSERT IGNORE INTO system_config (config_key, config_value)
            VALUES ('overtime_driver_sheet_url',
                    'https://docs.google.com/spreadsheets/d/1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM/gviz/tq?tqx=out:csv')
        """, cursor, "system_config.overtime_driver_sheet_url")
        _run("""
            INSERT IGNORE INTO system_config (config_key, config_value)
            VALUES ('overtime_ob_sheet_url', '')
        """, cursor, "system_config.overtime_ob_sheet_url")

        conn.commit()
        cursor.close()
        print("✔ Overtime schema ready")
        return True
    except Exception as e:
        print(f"[overtime-schema] error: {e}")
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
