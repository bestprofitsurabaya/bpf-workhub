"""Skema Inventaris IT (v2.78.0) — idempoten, dipanggil saat startup.

Tabel hidup di DB cabang (pola modul operasional lain) dan memuat
`branch_code` sebagai penanda denormalisasi agar laporan lintas cabang
tidak perlu menebak asal baris.

Pola pemakaian sama dengan `overtime_schema.ensure_overtime_schema()`:
`ensure_it_inventory_schema(conn)` menerima koneksi (dipakai app.py saat
loop semua DB cabang) atau membuka sendiri bila `conn` None.
"""
from modules.config import get_db_connection

# Kategori aset IT. Kode dipakai sebagai bagian tag (SBY-IT-PC-0001) dan
# disimpan di kolom `category` — jangan ganti kode yang sudah dipakai.
IT_CATEGORIES = [
    ('pc', 'PC / Desktop', '🖥️'),
    ('laptop', 'Laptop / Notebook', '💻'),
    ('monitor', 'Monitor', '🖥️'),
    ('printer', 'Printer / Scanner', '🖨️'),
    ('network', 'Perangkat Jaringan', '🌐'),
    ('ups', 'UPS / Power', '🔋'),
    ('projector', 'Proyektor / TV', '📽️'),
    ('cctv', 'CCTV', '📹'),
    ('server', 'Server / NAS', '🗄️'),
    ('phone', 'Telepon / IP Phone', '☎️'),
    ('peripheral', 'Periferal & Aksesori', '🖱️'),
    ('license', 'Lisensi Software', '🔑'),
    ('consumable', 'Consumable / Stok', '📦'),
    ('other', 'Lainnya', '📎'),
]

IT_CATEGORY_CODES = [c[0] for c in IT_CATEGORIES]

IT_STATUSES = ['stok', 'aktif', 'dipinjam', 'service', 'rusak', 'hilang', 'disposed']
IT_CONDITIONS = ['baik', 'rusak_ringan', 'rusak_berat']

_DDL = [
    # ---------------- master aset ----------------
    """
    CREATE TABLE IF NOT EXISTS it_assets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_tag VARCHAR(40) NOT NULL,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        category VARCHAR(30) NOT NULL DEFAULT 'other',
        brand VARCHAR(60) DEFAULT '',
        model VARCHAR(80) DEFAULT '',
        serial_number VARCHAR(80) DEFAULT '',
        status ENUM('stok','aktif','dipinjam','service','rusak','hilang','disposed')
               NOT NULL DEFAULT 'aktif',
        cond ENUM('baik','rusak_ringan','rusak_berat') NOT NULL DEFAULT 'baik',
        location_room VARCHAR(80) DEFAULT '',
        location_detail VARCHAR(120) DEFAULT '',
        assigned_to VARCHAR(100) DEFAULT '',
        purchase_date DATE NULL,
        purchase_price DECIMAL(14,2) NULL,
        vendor VARCHAR(100) DEFAULT '',
        warranty_until DATE NULL,
        hostname VARCHAR(80) DEFAULT '',
        ip_address VARCHAR(45) DEFAULT '',
        mac_address VARCHAR(20) DEFAULT '',
        os_name VARCHAR(80) DEFAULT '',
        specs JSON NULL,
        notes VARCHAR(1000) DEFAULT '',
        source ENUM('manual','import','discovery') NOT NULL DEFAULT 'manual',
        discovery_id INT NULL,
        label_printed_at DATETIME NULL,
        last_seen_at DATETIME NULL,
        created_by VARCHAR(50) DEFAULT '',
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_it_tag (asset_tag),
        KEY idx_it_branch (branch_code, status),
        KEY idx_it_cat (category),
        KEY idx_it_mac (mac_address),
        KEY idx_it_room (location_room),
        KEY idx_it_warranty (warranty_until)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---------------- riwayat (append-only) ----------------
    """
    CREATE TABLE IF NOT EXISTS it_asset_events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        asset_id INT NOT NULL,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        kind VARCHAR(30) NOT NULL,
        before_json JSON NULL,
        after_json JSON NULL,
        note VARCHAR(500) DEFAULT '',
        photo_path VARCHAR(255) DEFAULT '',
        actor VARCHAR(50) DEFAULT '',
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_ev_asset (asset_id, created_at),
        CONSTRAINT fk_it_ev_asset FOREIGN KEY (asset_id)
            REFERENCES it_assets (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---------------- discovery ----------------
    """
    CREATE TABLE IF NOT EXISTS it_discovery_runs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        method VARCHAR(30) NOT NULL DEFAULT 'mixed',
        subnet VARCHAR(80) DEFAULT '',
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        found INT DEFAULT 0,
        new_count INT DEFAULT 0,
        status ENUM('running','ok','error') NOT NULL DEFAULT 'running',
        error VARCHAR(500) DEFAULT '',
        actor VARCHAR(50) DEFAULT ''
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS it_discovered_devices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        run_id INT NULL,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        ip VARCHAR(45) DEFAULT '',
        mac VARCHAR(20) DEFAULT '',
        dedupe_key VARCHAR(90) NOT NULL DEFAULT '',
        hostname VARCHAR(120) DEFAULT '',
        vendor VARCHAR(80) DEFAULT '',
        open_ports VARCHAR(120) DEFAULT '',
        category_suggest VARCHAR(30) DEFAULT '',
        confidence DECIMAL(4,2) DEFAULT 0,
        reasons JSON NULL,
        specs JSON NULL,
        state ENUM('new','ignored','adopted') NOT NULL DEFAULT 'new',
        asset_id INT NULL,
        note VARCHAR(300) DEFAULT '',
        first_seen DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_it_disc (dedupe_key),
        KEY idx_it_disc_state (state, last_seen),
        KEY idx_it_disc_ip (branch_code, ip)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---------------- stok opname ----------------
    """
    CREATE TABLE IF NOT EXISTS it_stocktake_sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        location_room VARCHAR(80) DEFAULT '',
        started_by VARCHAR(50) DEFAULT '',
        started_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
        closed_at DATETIME NULL,
        total_expected INT DEFAULT 0,
        total_found INT DEFAULT 0,
        notes VARCHAR(300) DEFAULT ''
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS it_stocktake_items (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        asset_id INT NOT NULL,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        scanned_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
        result ENUM('found','missing','moved') NOT NULL DEFAULT 'found',
        note VARCHAR(200) DEFAULT '',
        UNIQUE KEY uniq_it_scan (session_id, asset_id),
        CONSTRAINT fk_it_scan_session FOREIGN KEY (session_id)
            REFERENCES it_stocktake_sessions (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---------------- registry agen inventaris (v2.79.0) ----------------
    # Satu baris per PC yang pernah menerima agen (push terkontrol dari host
    # IT) atau pernah melapor sendiri. Dipakai untuk mengukur CAKUPAN, bukan
    # untuk menyebar agen otomatis: baris hanya lahir dari laporan eksplisit.
    """
    CREATE TABLE IF NOT EXISTS it_agent_hosts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        branch_code VARCHAR(10) NOT NULL DEFAULT 'SBY',
        host_key VARCHAR(120) NOT NULL,
        hostname VARCHAR(120) DEFAULT '',
        ip VARCHAR(45) DEFAULT '',
        mac VARCHAR(20) DEFAULT '',
        os_name VARCHAR(120) DEFAULT '',
        agent_version VARCHAR(20) DEFAULT '',
        install_method VARCHAR(30) DEFAULT '',
        deploy_status ENUM('pending','installed','failed','unreachable','ignored')
            NOT NULL DEFAULT 'pending',
        deploy_message VARCHAR(300) DEFAULT '',
        asset_tag VARCHAR(40) DEFAULT '',
        first_installed_at DATETIME NULL,
        last_report_at DATETIME NULL,
        last_deploy_at DATETIME NULL,
        deployed_by VARCHAR(50) DEFAULT '',
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_agent_host (branch_code, host_key),
        KEY idx_agent_status (branch_code, deploy_status),
        KEY idx_agent_report (branch_code, last_report_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def ensure_it_inventory_schema(conn=None):
    """Buat semua tabel inventaris IT bila belum ada (idempoten).

    Returns True bila selesai tanpa error.
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[it-inventory] DB unavailable, skip migration')
            return False
        cur = conn.cursor()
        try:
            for ddl in _DDL:
                cur.execute(ddl)
            conn.commit()
            return True
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[it-inventory] ensure schema error: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
