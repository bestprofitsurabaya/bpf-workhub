"""Appointment System - schema migration.

Safe to run at every startup (CREATE IF NOT EXISTS + guarded ALTERs)
so existing databases get upgraded without dropping any data.
"""
from modules.config import get_db_connection


def _run(sql, cursor, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f"[appointments-schema] {label}: {e}")
        return False


def ensure_appointments_schema(conn=None):
    """Migrasi skema appointment & air minum (idempoten).

    conn opsional: bila diberikan dipakai langsung (mis. DB cabang) dan
    tidak ditutup di sini.
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print("[appointments-schema] DB unavailable, skip migration")
            return
        cursor = conn.cursor()

        # --- marketing_teams ---
        _run("""
            CREATE TABLE IF NOT EXISTS marketing_teams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                leader_name VARCHAR(100) DEFAULT '',
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "marketing_teams")

        # --- marketing_members (anggota tim marketing yang memprospek) ---
        _run("""
            CREATE TABLE IF NOT EXISTS marketing_members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                team_name VARCHAR(100) NOT NULL DEFAULT '',
                member_name VARCHAR(100) NOT NULL,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_team_member (team_name, member_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "marketing_members")

        # --- appointments ---
        _run("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                display_id VARCHAR(30) NOT NULL UNIQUE,
                marketing_username VARCHAR(50) NOT NULL,
                marketing_name VARCHAR(100) NOT NULL,
                marketing_member VARCHAR(100) DEFAULT '',
                team_name VARCHAR(100) DEFAULT '',
                nasabah_name VARCHAR(150) NOT NULL,
                nasabah_phone VARCHAR(30) DEFAULT '',
                alamat VARCHAR(500) NOT NULL,
                area VARCHAR(100) DEFAULT '',
                appointment_date DATE NOT NULL,
                sesi ENUM('1','2') NOT NULL DEFAULT '1',
                status ENUM('scheduled','assigned','completed','cancelled') DEFAULT 'scheduled',
                driver_name VARCHAR(100) DEFAULT NULL,
                driver_note VARCHAR(255) DEFAULT '',
                notes VARCHAR(500) DEFAULT '',
                completed_at DATETIME DEFAULT NULL,
                visit_result ENUM('ditemui','prospek','gagal') DEFAULT NULL,
                visit_note VARCHAR(255) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_date_sesi (appointment_date, sesi),
                INDEX idx_driver (driver_name),
                INDEX idx_status (status),
                INDEX idx_marketing (marketing_username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "appointments")

        # --- activity_logs: branch_code (v2.20.0 — audit bertanda cabang) ---
        _run("""
            ALTER TABLE activity_logs ADD COLUMN branch_code VARCHAR(20) DEFAULT NULL
        """, cursor, "activity_logs.branch_code")
        _run("""
            CREATE INDEX idx_activity_branch ON activity_logs (branch_code)
        """, cursor, "activity_logs.branch_code index")

        # --- users: extend role enum (v2.4: role 'driver' untuk login PIN PWA driver;
        # v2.6: role 'ob' untuk Office Boy — pengajuan pembelian air minum;
        # v2.16: role 'receptionist' & 'traineer' — sistem pelamar kerja;
        # v2.22: role 'ga_hr' — halaman khusus GA HR untuk data overtime;
        # v2.39: role 'security' — user Security, form overtime sendiri di SPA) ---
        # WAJIB superset lengkap (termasuk it_*) — MODIFY enum yang menghilangkan
        # nilai yang sudah ada di baris mana pun gagal "Data truncated 1265"
        # (dulu: gagal senyap tiap startup sejak role it_* masuk produksi).
        _run("""
            ALTER TABLE users
            MODIFY role ENUM('admin','ga','finance','marketing','chief_driver','driver','ob','receptionist','traineer','ga_hr','security','it_sby','it_hu','it_jkt2','it_bdg','it_smg','it_mlg','it_mdn','it_bjm','it_plm','it_lpg') NOT NULL DEFAULT 'ga'
        """, cursor, "users.role enum")

        # --- users: team_name column ---
        _run("""
            ALTER TABLE users ADD COLUMN team_name VARCHAR(100) DEFAULT ''
        """, cursor, "users.team_name")

        # --- trip_details: appointment_id ---
        _run("""
            ALTER TABLE trip_details ADD COLUMN appointment_id INT DEFAULT NULL
        """, cursor, "trip_details.appointment_id")

        # --- appointments: marketing_member (upgrade DB lama) ---
        _run("""
            ALTER TABLE appointments ADD COLUMN marketing_member VARCHAR(100) DEFAULT ''
        """, cursor, "appointments.marketing_member")

        # --- appointments: hasil kunjungan (visit_result / visit_note) ---
        _run("""
            ALTER TABLE appointments ADD COLUMN visit_result ENUM('ditemui','prospek','gagal') DEFAULT NULL
        """, cursor, "appointments.visit_result")
        _run("""
            ALTER TABLE appointments ADD COLUMN visit_note VARCHAR(255) DEFAULT ''
        """, cursor, "appointments.visit_note")

        # --- appointments: rute canggih (v2.15) ---
        # visit_time: jam kunjungan bebas dalam rentang sesi (HH:MM)
        # lat/lng: koordinat hasil geocoding alamat (untuk optimasi rute)
        # route_order: urutan kunjungan dalam rute driver (dari Atur Rute Otomatis)
        _run("""
            ALTER TABLE appointments ADD COLUMN visit_time TIME NULL
        """, cursor, "appointments.visit_time")
        _run("""
            ALTER TABLE appointments ADD COLUMN lat DOUBLE NULL
        """, cursor, "appointments.lat")
        _run("""
            ALTER TABLE appointments ADD COLUMN lng DOUBLE NULL
        """, cursor, "appointments.lng")
        _run("""
            ALTER TABLE appointments ADD COLUMN route_order INT NULL
        """, cursor, "appointments.route_order")

        # --- trip_masters: display_id (gap init.sql lama; upgrade DB lama) ---
        _run("""
            ALTER TABLE trip_masters ADD COLUMN display_id VARCHAR(30) DEFAULT NULL
        """, cursor, "trip_masters.display_id")
        # Backfill trip lama yang display_id-nya masih NULL (idempotent)
        _run("""
            UPDATE trip_masters SET display_id = CONCAT('TRIP-', id)
            WHERE display_id IS NULL OR display_id = ''
        """, cursor, "trip_masters.display_id backfill")

        # ============================================================
        # AIR MINUM (v2.6) — tanda terima pembelian air minum galon
        # Master tipe & merk dikelola Finance; pengajuan diisi OB;
        # verifikasi (approve/tolak) oleh Finance; PDF TTD Finance+GA.
        # ============================================================

        # --- water_drink_types: gelas / botol / galon ---
        _run("""
            CREATE TABLE IF NOT EXISTS water_drink_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(50) NOT NULL UNIQUE,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "water_drink_types")
        # Seed tipe default (idempotent)
        _run("""
            INSERT IGNORE INTO water_drink_types (name) VALUES ('Gelas'), ('Botol'), ('Galon')
        """, cursor, "water_drink_types seed")

        # --- water_drink_brands: merk per tipe (dikelola Finance) ---
        _run("""
            CREATE TABLE IF NOT EXISTS water_drink_brands (
                id INT AUTO_INCREMENT PRIMARY KEY,
                type_id INT NOT NULL,
                brand VARCHAR(100) NOT NULL,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_type_brand (type_id, brand),
                FOREIGN KEY (type_id) REFERENCES water_drink_types(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "water_drink_brands")

        # --- water_purchases: pengajuan pembelian (diisi OB) ---
        _run("""
            CREATE TABLE IF NOT EXISTS water_purchases (
                id INT AUTO_INCREMENT PRIMARY KEY,
                display_id VARCHAR(30) NOT NULL UNIQUE,
                ob_name VARCHAR(100) NOT NULL,
                purchase_date DATE NOT NULL,
                status ENUM('pending','verified','rejected') DEFAULT 'pending',
                remark VARCHAR(500) DEFAULT '',
                note TEXT,
                rejection_reason VARCHAR(500) DEFAULT '',
                verified_by VARCHAR(100) DEFAULT '',
                verified_at DATETIME DEFAULT NULL,
                foto_before VARCHAR(255),
                foto_after VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_ob (ob_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "water_purchases")

        # --- water_purchase_items: rincian multi-item ---
        _run("""
            CREATE TABLE IF NOT EXISTS water_purchase_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                purchase_id INT NOT NULL,
                drink_type VARCHAR(50) NOT NULL,
                brand VARCHAR(100) NOT NULL,
                satuan VARCHAR(20) DEFAULT 'pcs',
                quantity INT NOT NULL DEFAULT 1,
                FOREIGN KEY (purchase_id) REFERENCES water_purchases(id) ON DELETE CASCADE,
                INDEX idx_purchase (purchase_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "water_purchase_items")
        # Upgrade DB lama: kolom satuan
        _run("""
            ALTER TABLE water_purchase_items ADD COLUMN satuan VARCHAR(20) DEFAULT 'pcs'
        """, cursor, "water_purchase_items.satuan")

        conn.commit()

        # ============================================================
        # PELAMAR KERJA (v2.16) — form pelamar -> resepsionis (verifikasi,
        # kehadiran interview + 4 hari training, PDF) -> traineer (pantau)
        # ============================================================

        # --- applicants: data pelamar dari form publik ---
        _run("""
            CREATE TABLE IF NOT EXISTS applicants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                display_id VARCHAR(30) NOT NULL UNIQUE,
                nama_lengkap VARCHAR(150) NOT NULL,
                pendidikan VARCHAR(100) DEFAULT '',
                no_hp VARCHAR(30) DEFAULT '',
                upline VARCHAR(100) DEFAULT '',
                user_field VARCHAR(100) DEFAULT '',
                posisi VARCHAR(100) DEFAULT '',
                interview_at DATETIME NOT NULL,
                status ENUM('interview','training_1','training_2','training_3','training_4','lulus','resigned','rejected') DEFAULT 'interview',
                resign_reason VARCHAR(500) DEFAULT '',
                rejected_reason VARCHAR(500) DEFAULT '',
                verified_by VARCHAR(100) DEFAULT '',
                verified_at DATETIME NULL,
                notes VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_upline (upline),
                INDEX idx_interview_at (interview_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "applicants")

        # --- applicant_attendance: kehadiran interview + training hari 1-4 ---
        _run("""
            CREATE TABLE IF NOT EXISTS applicant_attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                applicant_id INT NOT NULL,
                stage ENUM('interview','training_1','training_2','training_3','training_4') NOT NULL,
                attended_at DATETIME NOT NULL,
                marked_by VARCHAR(100) DEFAULT '',
                note VARCHAR(255) DEFAULT '',
                UNIQUE KEY uq_applicant_stage (applicant_id, stage),
                CONSTRAINT fk_att_applicant FOREIGN KEY (applicant_id)
                    REFERENCES applicants(id) ON DELETE CASCADE,
                INDEX idx_stage (stage)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "applicant_attendance")

        # --- applicant_user_options (v2.17): pilihan dropdown 'User' pada form
        # pelamar. Dikelola Receptionist (tambah/hapus/aktif-nonaktif). Nilai
        # awal di-seed dari daftar User unik pada Google Sheet lama (idempotent). ---
        _run("""
            CREATE TABLE IF NOT EXISTS applicant_user_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "applicant_user_options")
        # Seed awal: daftar User unik dari Google Sheet (v2.17)
        _run("""
            INSERT IGNORE INTO applicant_user_options (name) VALUES
                ('TEAM YUSIE 3'), ('TEAM EDI 2'), ('TEAM LULUK 5'),
                ('TEAM SISKA 4'), ('TEAM BAPAKE 1')
        """, cursor, "applicant_user_options seed")

        # Commit DML seed (DDL di MySQL ter-commit implisit, DML tidak)
        try:
            conn.commit()
        except Exception as e:
            print(f"[appointments-schema] commit seed: {e}")

        # ============================================================
        # ASET & PEMELIHARAAN (v2.18) — migrasi dari bpf-asset-system
        # (Streamlit) ke BPF WorkHub: AC kantor + kendaraan + komponen +
        # log servis + rekomendasi otomatis (aturan tanggal/odometer).
        # Role: GA & Admin (pemeliharaan aset).
        # ============================================================

        # --- asset_ac: master unit AC kantor ---
        _run("""
            CREATE TABLE IF NOT EXISTS asset_ac (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(50) NOT NULL UNIQUE,
                merk VARCHAR(50) NOT NULL,
                tipe VARCHAR(50) NOT NULL,
                kapasitas VARCHAR(50) NOT NULL,
                lokasi VARCHAR(150) NOT NULL,
                refrigerant VARCHAR(50) DEFAULT '',
                installation_date DATE NULL,
                warranty_until DATE NULL,
                last_maintenance DATE NULL,
                status ENUM('Aktif','Rusak','Maintenance','Nonaktif') DEFAULT 'Aktif',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_ac_lokasi (lokasi),
                INDEX idx_ac_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "asset_ac")

        # --- asset_ac_logs: log servis AC (parameter teknikal + health score) ---
        _run("""
            CREATE TABLE IF NOT EXISTS asset_ac_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(50) NOT NULL,
                tanggal DATE NOT NULL,
                teknisi VARCHAR(100) NOT NULL,
                v_supply DECIMAL(8,2) NULL,
                amp_kompresor DECIMAL(8,2) NULL,
                low_p DECIMAL(8,2) NULL,
                high_p DECIMAL(8,2) NULL,
                temp_ret DECIMAL(8,2) NULL,
                temp_sup DECIMAL(8,2) NULL,
                temp_outdoor DECIMAL(8,2) NULL,
                delta_t DECIMAL(8,2) NULL,
                drainage VARCHAR(20) DEFAULT '',
                test_run VARCHAR(20) DEFAULT '',
                health_score INT NULL,
                sparepart_cost DECIMAL(12,2) DEFAULT 0,
                catatan VARCHAR(500) DEFAULT '',
                next_service_date DATE NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_aclog_asset (asset_id, tanggal),
                INDEX idx_aclog_health (health_score),
                CONSTRAINT fk_aclog FOREIGN KEY (asset_id)
                    REFERENCES asset_ac(asset_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "asset_ac_logs")

        # --- vehicle_assets: master kendaraan KANTOR (bukan sample).
        # vehicle_id -> vehicles.id (tabel kendaraan BBM WorkHub) agar satu
        # sumber data kendaraan; nopol asli kantor di-seed dari tabel tsb. ---
        _run("""
            CREATE TABLE IF NOT EXISTS vehicle_assets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_id INT NULL,
                nopol VARCHAR(20) NOT NULL UNIQUE,
                vehicle_type VARCHAR(50) NOT NULL DEFAULT '',
                brand VARCHAR(50) DEFAULT 'Toyota',
                model VARCHAR(50) DEFAULT '',
                year INT NULL,
                color VARCHAR(30) DEFAULT '',
                fuel_type VARCHAR(30) DEFAULT 'Bensin',
                status ENUM('Aktif','Rusak','Nonaktif') DEFAULT 'Aktif',
                purchase_date DATE NULL,
                last_odometer INT DEFAULT 0,
                insurance_until DATE NULL,
                tax_until DATE NULL,
                notes VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_va_nopol (nopol),
                INDEX idx_va_status (status),
                CONSTRAINT fk_va_vehicle FOREIGN KEY (vehicle_id)
                    REFERENCES vehicles(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "vehicle_assets")

        # --- vehicle_service_logs: log servis kendaraan per komponen ---
        _run("""
            CREATE TABLE IF NOT EXISTS vehicle_service_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_asset_id INT NOT NULL,
                service_date DATE NOT NULL,
                odometer INT NOT NULL DEFAULT 0,
                service_type VARCHAR(50) NOT NULL,
                component_name VARCHAR(100) NOT NULL,
                component_life_km INT DEFAULT 0,
                component_life_months INT DEFAULT 0,
                current_usage_km INT DEFAULT 0,
                current_usage_months INT DEFAULT 0,
                next_service_km INT DEFAULT 0,
                next_service_months INT DEFAULT 0,
                cost DECIMAL(12,2) DEFAULT 0,
                mechanic_name VARCHAR(100) DEFAULT '',
                parts_replaced VARCHAR(500) DEFAULT '',
                invoice_number VARCHAR(50) DEFAULT '',
                notes VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_vslog_vehicle (vehicle_asset_id, service_date),
                INDEX idx_vslog_component (component_name),
                CONSTRAINT fk_vslog FOREIGN KEY (vehicle_asset_id)
                    REFERENCES vehicle_assets(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "vehicle_service_logs")

        # --- vehicle_components: master komponen + standar umur pakai ---
        _run("""
            CREATE TABLE IF NOT EXISTS vehicle_components (
                id INT AUTO_INCREMENT PRIMARY KEY,
                component_name VARCHAR(100) NOT NULL UNIQUE,
                standard_life_km INT DEFAULT 0,
                standard_life_months INT DEFAULT 0,
                category VARCHAR(50) DEFAULT '',
                priority INT DEFAULT 1,
                estimated_cost DECIMAL(12,2) DEFAULT 0,
                is_active TINYINT(1) DEFAULT 1,
                notes VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "vehicle_components")

        # --- maintenance_recommendations: rekomendasi servis otomatis ---
        _run("""
            CREATE TABLE IF NOT EXISTS maintenance_recommendations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_type ENUM('ac','vehicle') NOT NULL,
                asset_ref VARCHAR(50) NOT NULL,
                recommendation_date DATE NOT NULL,
                priority ENUM('Kritis','Tinggi','Sedang','Rutin') NOT NULL DEFAULT 'Rutin',
                urgency_days INT DEFAULT 0,
                actions VARCHAR(500) NOT NULL,
                estimated_cost DECIMAL(12,2) DEFAULT 0,
                status ENUM('Pending','Selesai','Dibatalkan') DEFAULT 'Pending',
                completed_date DATE NULL,
                notes VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_rec_asset (asset_type, asset_ref, status),
                INDEX idx_rec_date (recommendation_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, cursor, "maintenance_recommendations")

        # --- geocode_cache (v2.15): cache geocoding alamat -> koordinat ---
        try:
            from modules.geocode import ensure_geocode_schema
            ensure_geocode_schema()
        except Exception as e:
            print(f"[appointments-schema] geocode schema error: {e}")

        cursor.close()
        print("✔ Appointment & Air Minum schema ready")
        return True
    except Exception as e:
        print(f"[appointments-schema] error: {e}")
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
