"""Skema MFA TOTP (v2.112.0) — idempoten, aman dijalankan tiap startup.

Menambah:
- kolom `users.mfa_enabled`, `mfa_secret`, `mfa_enrolled_at`, `mfa_last_step`
- tabel `mfa_recovery_codes` (kode pemulihan sekali pakai, disimpan sebagai
  hash SHA-256 — plaintext hanya ditampilkan sekali saat pendaftaran)
- kunci kebijakan di `system_config`

Catatan: `mfa_enforced_at` diisi sekali saat pertama kali (NOW()) sehingga
masa tenggang `mfa_grace_days` mulai berjalan sejak fitur dipasang. Admin dapat
mengubah kebijakan & tenggang kapan saja di Pengaturan → Keamanan.
"""
from modules.config import get_master_connection
from modules.mfa import DEFAULT_REQUIRED_ROLES_CSV, POLICY_REQUIRED

_USER_COLUMNS = (
    ('mfa_enabled', 'TINYINT(1) NOT NULL DEFAULT 0'),
    ('mfa_secret', 'VARCHAR(512) NULL'),
    ('mfa_enrolled_at', 'DATETIME NULL'),
    ('mfa_last_step', 'BIGINT NULL'),
)

_RECOVERY_DDL = """
CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    code_hash CHAR(64) NOT NULL,
    used_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mfa_recovery_user (user_id, used_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_CONFIG_DEFAULTS = (
    ('mfa_policy', POLICY_REQUIRED),
    ('mfa_required_roles', DEFAULT_REQUIRED_ROLES_CSV),
    ('mfa_grace_days', '7'),
)


def _ensure_on_conn(conn):
    cur = conn.cursor()
    try:
        for column, definition in _USER_COLUMNS:
            try:
                cur.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {definition}")
            except Exception as exc:
                print(f'[mfa] kolom {column}: {exc}')
        cur.execute(_RECOVERY_DDL)
        for key, value in _CONFIG_DEFAULTS:
            try:
                cur.execute(
                    "INSERT IGNORE INTO system_config (config_key, config_value) "
                    "VALUES (%s, %s)", (key, value))
            except Exception as exc:
                print(f'[mfa] config {key}: {exc}')
        # Titik mulai masa tenggang — hanya terisi sekali (INSERT IGNORE).
        try:
            cur.execute(
                "INSERT IGNORE INTO system_config (config_key, config_value) "
                "VALUES ('mfa_enforced_at', NOW())")
        except Exception as exc:
            print(f'[mfa] config mfa_enforced_at: {exc}')
        conn.commit()
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass


def ensure_mfa_schema(conn=None):
    """Pastikan skema MFA ada. `conn` opsional (master bila None)."""
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
