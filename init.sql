-- ============================================================
-- BPF ASSET SYSTEM - CLEAN SCHEMA (No Seed Data)
-- ============================================================

CREATE DATABASE IF NOT EXISTS bpf_asset_system;
USE bpf_asset_system;

-- Vehicles
CREATE TABLE IF NOT EXISTS vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_type VARCHAR(50) NOT NULL UNIQUE,
    brand VARCHAR(50) DEFAULT 'Toyota',
    fuel_capacity DECIMAL(10,2) DEFAULT 45,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- BBM Types
CREATE TABLE IF NOT EXISTS bbm_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    price_per_liter DECIMAL(15,2) NOT NULL,
    octane_rating INT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Vehicle-BBM Allowed
CREATE TABLE IF NOT EXISTS vehicle_bbm_allowed (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_type VARCHAR(50) NOT NULL,
    bbm_type VARCHAR(50) NOT NULL,
    min_km_per_liter DECIMAL(10,2) DEFAULT 5.0,
    max_km_per_liter DECIMAL(10,2) DEFAULT 18.0,
    warning_km_per_liter DECIMAL(10,2) DEFAULT 10.5,
    good_km_per_liter DECIMAL(10,2) DEFAULT 12.5,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_type) REFERENCES vehicles(vehicle_type) ON DELETE CASCADE,
    FOREIGN KEY (bbm_type) REFERENCES bbm_types(name) ON DELETE CASCADE,
    UNIQUE KEY unique_vehicle_bbm (vehicle_type, bbm_type)
);

-- Drivers
CREATE TABLE IF NOT EXISTS drivers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    nopol VARCHAR(20) NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL,
    bbm_type VARCHAR(50) NOT NULL DEFAULT 'PERTALITE',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_nopol (nopol)
);

-- Users (PIN Security)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    -- v2.29.11: enum role lengkap + branch_code — init.sql harus
    -- self-sufficient (migrasi ALTER di startup TIDAK jalan saat seed ini
    -- dieksekusi oleh entrypoint MariaDB, sehingga INSERT users di bawah
    -- gagal 'Unknown column branch_code' di fresh deploy tanpa ini).
    role ENUM('admin','ga','finance','marketing','chief_driver','driver','ob','receptionist','traineer','ga_hr','it_sby','it_hu','it_jkt2','it_bdg','it_smg','it_mlg','it_mdn','it_bjm','it_plm','it_lpg') NOT NULL DEFAULT 'ga',
    pin VARCHAR(255) NOT NULL,
    team_name VARCHAR(100) DEFAULT '',
    branch_code VARCHAR(20) DEFAULT NULL,
    -- v2.36.0 (approval berjenjang): override atasan per user — NULL = pakai
    -- atasan default per role (driver→chief_driver, ob→ga_hr).
    manager_username VARCHAR(50) DEFAULT NULL,
    is_active TINYINT(1) DEFAULT 1,
    last_login DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_role (role)
);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    nopol VARCHAR(20) NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL,
    bbm_type VARCHAR(50) NOT NULL,
    nominal DECIMAL(15,2) NOT NULL,
    liter DECIMAL(10,2) NOT NULL,
    price_per_liter DECIMAL(10,2) NOT NULL,
    odo_km INT NOT NULL,
    spbu_type ENUM('rekanan', 'non_rekanan') NOT NULL,
    foto_odo_sebelum VARCHAR(255),
    foto_nota_odo_sesudah VARCHAR(255),
    foto_struk VARCHAR(255),
    foto_struk_dispenser VARCHAR(255),
    foto_mypertamina_admin VARCHAR(255),
    is_mypertamina_error BOOLEAN DEFAULT FALSE,
    kronologis_text TEXT,
    status ENUM('pending','verified_ga','os_finance','archived','rejected','modified') DEFAULT 'pending',
    ml_anomaly_flag BOOLEAN DEFAULT FALSE,
    km_per_liter DECIMAL(10,2) DEFAULT 0,
    gps_latitude DECIMAL(10,8),
    gps_longitude DECIMAL(11,8),
    gps_address TEXT,
    jumlah_appointment INT DEFAULT 0,
    is_reported BOOLEAN DEFAULT FALSE,
    is_dummy TINYINT(1) DEFAULT 0,
    modified_by VARCHAR(100),
    modification_note TEXT,
    ga_approved_by VARCHAR(100) DEFAULT NULL,
    ga_approved_at DATETIME DEFAULT NULL,
    approved_by_user VARCHAR(50) DEFAULT NULL,
    finance_payout_by VARCHAR(100) DEFAULT NULL,
    finance_payout_at DATETIME DEFAULT NULL,
    payout_by_user VARCHAR(50) DEFAULT NULL,
    archived_by VARCHAR(100) DEFAULT NULL,
    archived_at DATETIME DEFAULT NULL,
    archived_by_user VARCHAR(50) DEFAULT NULL,
    rejection_reason TEXT DEFAULT NULL,
    transaction_notes TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_type) REFERENCES vehicles(vehicle_type),
    FOREIGN KEY (bbm_type) REFERENCES bbm_types(name),
    INDEX idx_nopol (nopol),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_status_created (status, created_at),
    INDEX idx_archived (archived_at)
);

-- Activity Logs
CREATE TABLE IF NOT EXISTS activity_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT,
    action VARCHAR(50) NOT NULL,
    user_type VARCHAR(20) NOT NULL,
    user_name VARCHAR(100),
    old_data JSON,
    new_data JSON,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    INDEX idx_transaction (transaction_id),
    INDEX idx_created_at (created_at)
);

-- Daily Summary
CREATE TABLE IF NOT EXISTS daily_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    summary_date DATE NOT NULL,
    vehicle_type VARCHAR(50),
    total_transactions INT DEFAULT 0,
    total_liter DECIMAL(15,2) DEFAULT 0,
    total_nominal DECIMAL(15,2) DEFAULT 0,
    avg_km_per_liter DECIMAL(10,2) DEFAULT 0,
    total_odo_km INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_daily_vehicle (summary_date, vehicle_type)
);

-- System Config
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(50) PRIMARY KEY,
    config_value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Trip Masters
CREATE TABLE IF NOT EXISTS trip_masters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) NOT NULL UNIQUE,
    driver_name VARCHAR(100) NOT NULL,
    nopol VARCHAR(20) NOT NULL,
    trip_date DATE NOT NULL,
    jam_keberangkatan TIME NOT NULL,
    jam_tiba TIME,
    km_awal INT NOT NULL,
    km_akhir INT,
    status ENUM('pending','verified_ga','rejected') DEFAULT 'pending',
    verified_by VARCHAR(100),
    verified_at DATETIME,
    rejection_reason TEXT,
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
    INDEX idx_driver (driver_name),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Trip Details
CREATE TABLE IF NOT EXISTS trip_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trip_master_id INT NOT NULL,
    no_urut INT NOT NULL,
    lokasi_berangkat VARCHAR(255) NOT NULL,
    pukul_berangkat TIME NOT NULL,
    km_berangkat INT NOT NULL,
    lokasi_tujuan VARCHAR(255) NOT NULL,
    pukul_tujuan TIME NOT NULL,
    km_tujuan INT NOT NULL,
    appointment_id INT DEFAULT NULL,
    FOREIGN KEY (trip_master_id) REFERENCES trip_masters(id) ON DELETE CASCADE,
    INDEX idx_trip_master (trip_master_id),
    INDEX idx_appointment (appointment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Vehicle Assignments
CREATE TABLE IF NOT EXISTS vehicle_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    nopol VARCHAR(20) NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL,
    bbm_type VARCHAR(50) NOT NULL,
    assigned_date DATE NOT NULL,
    unassigned_date DATE DEFAULT NULL,
    is_current TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_driver (driver_name),
    INDEX idx_nopol (nopol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- MARKETING TEAMS
-- ============================================================
CREATE TABLE IF NOT EXISTS marketing_teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    leader_name VARCHAR(100) DEFAULT '',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- APPOINTMENTS (Marketing -> Chief Driver -> Trip Log)
-- Sesi 1 = 08.30, Sesi 2 = 14.30
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) NOT NULL UNIQUE,
    marketing_username VARCHAR(50) NOT NULL,
    marketing_name VARCHAR(100) NOT NULL,
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- DEFAULT USERS (PIN: 123456)
-- ============================================================
-- Konvensi username (v2.29.7): {divisi}_{cabang} — user tahu divisi & cabang
-- dari nama loginnnya. Contoh: ga_sby, finance_sby. Bila >1 orang per divisi di
-- cabang yang sama, username memakai nama: ob_faisol_sby (dibuat manual Admin).
-- v2.37.0: admin mengikuti konvensi yang sama — 'admin' = Admin Pusat (semua
-- cabang), 'admin_<kode>' = Admin cabang (terkunci ke cabangnya).
INSERT INTO users (username, full_name, role, pin, branch_code) VALUES 
('admin', 'Administrator', 'admin', '123456', 'SBY'),
('ga_sby', 'GA Officer', 'ga', '123456', 'SBY'),
('finance_sby', 'Finance Officer', 'finance', '123456', 'SBY');

-- Default system config
INSERT INTO system_config (config_key, config_value) VALUES 
('multifill_km_threshold', '40'),
('dummy_data_enabled', 'false'),
('water_edit_enabled', 'false');

-- ============================================================
-- NOTIFICATIONS (driver PWA real-time + offline catch-up)
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,
    action VARCHAR(30) NOT NULL,
    message VARCHAR(255) NOT NULL,
    ref_id VARCHAR(60) DEFAULT NULL,
    is_read TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_driver_read (driver_name, is_read),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- AIR MINUM (v2.6) — Tanda Terima Pembelian Air Minum
-- Master tipe & merk dikelola Finance; pengajuan diisi OB;
-- verifikasi (approve/tolak) oleh Finance; PDF TTD Finance+GA.
-- ============================================================
CREATE TABLE IF NOT EXISTS water_drink_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO water_drink_types (name) VALUES ('Gelas'), ('Botol'), ('Galon');

CREATE TABLE IF NOT EXISTS water_drink_brands (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type_id INT NOT NULL,
    brand VARCHAR(100) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_type_brand (type_id, brand),
    FOREIGN KEY (type_id) REFERENCES water_drink_types(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    edited_by VARCHAR(100) DEFAULT '',
    edited_at DATETIME DEFAULT NULL,
    edit_count INT NOT NULL DEFAULT 0,
    foto_before VARCHAR(255),
    foto_after VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_ob (ob_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS water_purchase_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    purchase_id INT NOT NULL,
    drink_type VARCHAR(50) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    satuan VARCHAR(20) DEFAULT 'pcs',
    quantity INT NOT NULL DEFAULT 1,
    FOREIGN KEY (purchase_id) REFERENCES water_purchases(id) ON DELETE CASCADE,
    INDEX idx_purchase (purchase_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SELECT '✅ Clean database ready' AS result;
-- ============================================================
-- BPF WORKHUB — Additional Tables (v2.x)
-- Tables ini di-auto-create oleh app.py saat startup,
-- tapi disertakan di init.sql untuk fresh deploy yang lebih robust.
-- Semua pakai CREATE TABLE IF NOT EXISTS (idempoten).
-- ============================================================

-- ============================================================
-- BRANCHES (Multi-cabang)
-- ============================================================
CREATE TABLE IF NOT EXISTS branches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    db_name VARCHAR(64) NOT NULL,
    city VARCHAR(100) DEFAULT '',
    address VARCHAR(255) DEFAULT '',
    phone VARCHAR(30) DEFAULT '',
    company_name VARCHAR(150) DEFAULT '',
    company_subtitle VARCHAR(150) DEFAULT '',
    system_name VARCHAR(100) DEFAULT '',
    system_version VARCHAR(30) DEFAULT '',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Default branch (identitas resmi dari bestprofit-futures.co.id/hubungi-kami)
INSERT IGNORE INTO branches (code, name, db_name, city, address, phone, company_name, company_subtitle, system_name, system_version)
VALUES ('SBY', 'Cabang Surabaya', 'bpf_asset_system', 'Surabaya',
        'Graha Bukopin, Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271', '031-5349888',
        'PT BESTPROFIT FUTURES', 'Cabang Surabaya', 'BPF WorkHub', 'v2.37.0');

-- Kantor Pusat Jakarta (HO) + cabang JKT kedua
INSERT IGNORE INTO branches (code, name, db_name, city, address, phone, company_name, company_subtitle, system_name, system_version)
VALUES ('JKT', 'Kantor Pusat Jakarta', 'bpf_branch_jkt', 'Jakarta',
        'Equity Tower Lt. 47, Kawasan Niaga Terpadu Sudirman (SCBD), Jl. Jend. Sudirman Kav. 52-53, Jakarta 12190', '021-29035005',
        'PT BESTPROFIT FUTURES', 'Kantor Pusat | Jakarta', 'BPF WorkHub', 'v2.37.0'),
       ('JKT2', 'Cabang Pacific Place', 'bpf_branch_jkt2', 'Jakarta',
        'Pacific Place Mall Shop Lt. 3, Unit 3-99, Jl. Jend. Sudirman Kav. 52-53, SCBD, Jakarta Selatan 12190', '021-57973015',
        'PT BESTPROFIT FUTURES', 'Cabang Pacific Place', 'BPF WorkHub', 'v2.37.0');

-- Add branch_code column to users if not exists
SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'branch_code');
SET @sql = IF(@exists = 0, 'ALTER TABLE users ADD COLUMN branch_code VARCHAR(20) DEFAULT NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- MARKETING MEMBERS
-- ============================================================
CREATE TABLE IF NOT EXISTS marketing_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL DEFAULT '',
    member_name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_team_member (team_name, member_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- APPLICANTS (Pelamar Kerja)
-- ============================================================
CREATE TABLE IF NOT EXISTS applicants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) NOT NULL,
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
    verified_at DATETIME DEFAULT NULL,
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY display_id (display_id),
    KEY idx_status (status),
    KEY idx_upline (upline),
    KEY idx_interview_at (interview_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS applicant_attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    applicant_id INT NOT NULL,
    stage ENUM('interview','training_1','training_2','training_3','training_4') NOT NULL,
    attended_at DATETIME NOT NULL,
    marked_by VARCHAR(100) DEFAULT '',
    note VARCHAR(255) DEFAULT '',
    PRIMARY KEY (id),
    UNIQUE KEY uq_applicant_stage (applicant_id, stage),
    KEY idx_stage (stage),
    CONSTRAINT fk_att_applicant FOREIGN KEY (applicant_id) REFERENCES applicants (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS applicant_user_options (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- ASSET AC
-- ============================================================
CREATE TABLE IF NOT EXISTS asset_ac (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id VARCHAR(50) NOT NULL,
    merk VARCHAR(50) NOT NULL,
    tipe VARCHAR(50) NOT NULL,
    kapasitas VARCHAR(50) NOT NULL,
    lokasi VARCHAR(150) NOT NULL,
    refrigerant VARCHAR(50) DEFAULT '',
    installation_date DATE DEFAULT NULL,
    warranty_until DATE DEFAULT NULL,
    last_maintenance DATE DEFAULT NULL,
    status ENUM('Aktif','Rusak','Maintenance','Nonaktif') DEFAULT 'Aktif',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY asset_id (asset_id),
    KEY idx_ac_lokasi (lokasi),
    KEY idx_ac_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS asset_ac_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id VARCHAR(50) NOT NULL,
    tanggal DATE NOT NULL,
    teknisi VARCHAR(100) NOT NULL,
    v_supply DECIMAL(8,2) DEFAULT NULL,
    amp_kompresor DECIMAL(8,2) DEFAULT NULL,
    low_p DECIMAL(8,2) DEFAULT NULL,
    high_p DECIMAL(8,2) DEFAULT NULL,
    temp_ret DECIMAL(8,2) DEFAULT NULL,
    temp_sup DECIMAL(8,2) DEFAULT NULL,
    temp_outdoor DECIMAL(8,2) DEFAULT NULL,
    delta_t DECIMAL(8,2) DEFAULT NULL,
    drainage VARCHAR(20) DEFAULT '',
    test_run VARCHAR(20) DEFAULT '',
    health_score INT DEFAULT NULL,
    sparepart_cost DECIMAL(12,2) DEFAULT 0.00,
    catatan VARCHAR(500) DEFAULT '',
    next_service_date DATE DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_aclog_asset (asset_id, tanggal),
    KEY idx_aclog_health (health_score),
    CONSTRAINT fk_aclog FOREIGN KEY (asset_id) REFERENCES asset_ac (asset_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- VEHICLE ASSETS & COMPONENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS vehicle_assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT DEFAULT NULL,
    nopol VARCHAR(20) NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL DEFAULT '',
    brand VARCHAR(50) DEFAULT 'Toyota',
    model VARCHAR(50) DEFAULT '',
    year INT DEFAULT NULL,
    color VARCHAR(30) DEFAULT '',
    fuel_type VARCHAR(30) DEFAULT 'Bensin',
    status ENUM('Aktif','Rusak','Nonaktif') DEFAULT 'Aktif',
    purchase_date DATE DEFAULT NULL,
    last_odometer INT DEFAULT 0,
    insurance_until DATE DEFAULT NULL,
    tax_until DATE DEFAULT NULL,
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY nopol (nopol),
    KEY idx_va_nopol (nopol),
    KEY idx_va_status (status),
    KEY fk_va_vehicle (vehicle_id),
    CONSTRAINT fk_va_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_components (
    id INT AUTO_INCREMENT PRIMARY KEY,
    component_name VARCHAR(100) NOT NULL,
    standard_life_km INT DEFAULT 0,
    standard_life_months INT DEFAULT 0,
    category VARCHAR(50) DEFAULT '',
    priority INT DEFAULT 1,
    estimated_cost DECIMAL(12,2) DEFAULT 0.00,
    is_active TINYINT(1) DEFAULT 1,
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY component_name (component_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    cost DECIMAL(12,2) DEFAULT 0.00,
    mechanic_name VARCHAR(100) DEFAULT '',
    parts_replaced VARCHAR(500) DEFAULT '',
    invoice_number VARCHAR(50) DEFAULT '',
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_vslog_vehicle (vehicle_asset_id, service_date),
    KEY idx_vslog_component (component_name),
    CONSTRAINT fk_vslog FOREIGN KEY (vehicle_asset_id) REFERENCES vehicle_assets (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS maintenance_recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_type ENUM('ac','vehicle') NOT NULL,
    asset_ref VARCHAR(50) NOT NULL,
    recommendation_date DATE NOT NULL,
    priority ENUM('Kritis','Tinggi','Sedang','Rutin') NOT NULL DEFAULT 'Rutin',
    urgency_days INT DEFAULT 0,
    actions VARCHAR(500) NOT NULL,
    estimated_cost DECIMAL(12,2) DEFAULT 0.00,
    status ENUM('Pending','Selesai','Dibatalkan') DEFAULT 'Pending',
    completed_date DATE DEFAULT NULL,
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_rec_asset (asset_type, asset_ref, status),
    KEY idx_rec_date (recommendation_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- OVERTIME
-- ============================================================
CREATE TABLE IF NOT EXISTS overtime_driver (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sheet_row INT NOT NULL,
    display_id VARCHAR(30) DEFAULT '',
    source VARCHAR(20) DEFAULT 'sheet',
    source_uid VARCHAR(64) DEFAULT '',
    submitted_at DATETIME DEFAULT NULL,
    email VARCHAR(150) DEFAULT '',
    nama VARCHAR(150) NOT NULL,
    tanggal DATE DEFAULT NULL,
    waktu_mulai VARCHAR(20) DEFAULT '',
    waktu_selesai VARCHAR(20) DEFAULT '',
    keterangan VARCHAR(500) DEFAULT '',
    foto_mulai VARCHAR(600) DEFAULT '',
    foto_selesai VARCHAR(600) DEFAULT '',
    notes VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
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
    UNIQUE KEY uq_otd_uid (source_uid),
    KEY idx_otd_tanggal (tanggal),
    KEY idx_otd_nama (nama)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS overtime_ob_security (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) NOT NULL,
    nama VARCHAR(150) NOT NULL,
    posisi ENUM('OB','Security') NOT NULL DEFAULT 'OB',
    tanggal DATE DEFAULT NULL,
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
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY display_id (display_id),
    UNIQUE KEY uq_oto_source (source_uid),
    KEY idx_oto_tanggal (tanggal),
    KEY idx_oto_nama (nama),
    KEY idx_oto_posisi (posisi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- CASH / FUEL REQUESTS
-- ============================================================
CREATE TABLE IF NOT EXISTS fuel_cash_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) DEFAULT NULL,
    driver_name VARCHAR(100) NOT NULL,
    nopol VARCHAR(20) DEFAULT NULL,
    vehicle_type VARCHAR(50) DEFAULT NULL,
    bbm_type VARCHAR(50) DEFAULT 'PERTALITE',
    base_amount DECIMAL(12,2) NOT NULL,
    unique_cents DECIMAL(12,2) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    daily_code INT NOT NULL,
    status ENUM('DRAFT','GA_APPROVED','FINANCE_APPROVED','FUNDS_WITH_DRIVER','LPJ_SUBMITTED','COMPLETED','REJECTED') DEFAULT 'DRAFT',
    ga_approved_by VARCHAR(100) DEFAULT NULL,
    ga_approved_at TIMESTAMP NULL DEFAULT NULL,
    finance_approved_by VARCHAR(100) DEFAULT NULL,
    finance_approved_at TIMESTAMP NULL DEFAULT NULL,
    handover_by VARCHAR(100) DEFAULT NULL,
    handover_at TIMESTAMP NULL DEFAULT NULL,
    lpj_transaction_id INT DEFAULT NULL,
    lpj_submitted_at TIMESTAMP NULL DEFAULT NULL,
    rejection_reason TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY display_id (display_id),
    KEY lpj_transaction_id (lpj_transaction_id),
    CONSTRAINT fuel_cash_requests_ibfk_1 FOREIGN KEY (lpj_transaction_id) REFERENCES transactions (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS daily_unique_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code_date DATE NOT NULL,
    unique_code INT NOT NULL,
    generated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY code_date (code_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS assignment_swaps (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nopol VARCHAR(20) DEFAULT NULL,
    old_driver VARCHAR(100) DEFAULT NULL,
    new_driver VARCHAR(100) DEFAULT NULL,
    category VARCHAR(30) DEFAULT NULL,
    reason TEXT DEFAULT NULL,
    ga_name VARCHAR(100) DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- GEOCODE CACHE
-- ============================================================
CREATE TABLE IF NOT EXISTS geocode_cache (
    address VARCHAR(500) NOT NULL,
    lat DOUBLE DEFAULT NULL,
    lng DOUBLE DEFAULT NULL,
    display_name VARCHAR(500) DEFAULT '',
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    found TINYINT(1) DEFAULT 1,
    PRIMARY KEY (address(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Approval berjenjang (v2.36.0) — jurnal ACC atasan per dokumen.
-- Juga dibuat idempoten oleh startup (master + tiap cabang).
-- ============================================================
CREATE TABLE IF NOT EXISTS approval_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doc_type VARCHAR(20) NOT NULL,
    doc_ref INT NOT NULL,
    display_id VARCHAR(40) DEFAULT '',
    requested_by VARCHAR(100) DEFAULT '',
    requester_role VARCHAR(30) DEFAULT '',
    branch_code VARCHAR(20) DEFAULT '',
    chain JSON NULL,
    step INT NOT NULL DEFAULT 1,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    decided_by VARCHAR(100) DEFAULT '',
    decided_at DATETIME NULL,
    note VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_appr_doc (doc_type, doc_ref),
    INDEX idx_appr_status (status),
    INDEX idx_appr_doc (doc_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SELECT '✅ v2 tables ready' AS result;
