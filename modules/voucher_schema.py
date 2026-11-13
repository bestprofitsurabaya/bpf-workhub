"""Schema Voucher BBM Rekanan (v2.107.0) — idempoten.

Alur BBM rekanan: SPBU mitra menyerahkan voucher + blanko ke driver; kantor
membayar mitra per periode. Transaksi TIDAK dipisah menjadi jenis baru —
tetap `transaction_type='CLAIM'` seperti laporan BBM biasa. Yang membedakan
hanya label SPBU: `spbu_type='rekanan'` (voucher) vs `non_rekanan` (cash),
ditambah kolom voucher yang terisi (penanda pasti baris voucher).

Skema ini menambah:
- kolom pemakaian: nilai voucher, kode harian, nama mitra, nomor nota,
  kunci settlement (anti tagihan dobel),
- tabel `voucher_settlements` untuk tagihan/rekonsiliasi per periode.

Semua langkah aman dijalankan berulang (startup master + tiap DB cabang).
"""
from modules.config import get_master_connection

_TX_COLUMNS = (
    # Nilai voucher disimpan per transaksi supaya perubahan harga di kemudian
    # hari tidak mengubah histori.
    ('voucher_value', 'DECIMAL(15,2) DEFAULT 0'),
    ('daily_code', 'INT NULL'),
    ('voucher_partner', 'VARCHAR(120) NULL'),
    ('nota_no', 'VARCHAR(60) NULL'),
    ('settlement_id', 'INT NULL'),
    ('settled_at', 'DATETIME NULL'),
    ('settled_by', 'VARCHAR(100) NULL'),
)

_SETTLEMENTS_DDL = """
CREATE TABLE IF NOT EXISTS voucher_settlements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    display_id VARCHAR(30) DEFAULT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    partner VARCHAR(120) DEFAULT NULL,
    invoice_no VARCHAR(60) DEFAULT NULL,
    voucher_count INT NOT NULL DEFAULT 0,
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    status ENUM('draft','paid','cancelled') NOT NULL DEFAULT 'draft',
    paid_at DATETIME NULL,
    paid_by VARCHAR(100) NULL,
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT NULL,
    UNIQUE KEY uq_display (display_id),
    KEY idx_period (period_start, period_end),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# Nilai default per cabang (SBY 130.000). Bisa diubah di Pengaturan.
_CONFIG_DEFAULTS = (
    ('voucher_default_value', '130000'),
    ('voucher_partner_name', ''),
)


def _ensure_on_conn(conn):
    cur = conn.cursor()
    try:
        for col, definition in _TX_COLUMNS:
            try:
                cur.execute(
                    f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col} {definition}")
            except Exception as col_err:
                print(f"[voucher] kolom {col}: {col_err}")
        cur.execute(_SETTLEMENTS_DDL)
        for key, value in _CONFIG_DEFAULTS:
            try:
                cur.execute(
                    "INSERT IGNORE INTO system_config (config_key, config_value) "
                    "VALUES (%s, %s)", (key, value))
            except Exception as cfg_err:
                print(f"[voucher] config {key}: {cfg_err}")
        conn.commit()
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass


def ensure_voucher_schema(conn=None):
    """Pastikan skema voucher ada. `conn` opsional (master bila None)."""
    own = conn is None
    if conn is None:
        conn = get_master_connection()
    if not conn:
        return False
    try:
        return _ensure_on_conn(conn)
    finally:
        if own:
            try:
                conn.close()
            except Exception:
                pass
