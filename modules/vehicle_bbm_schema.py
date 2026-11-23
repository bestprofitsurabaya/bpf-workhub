"""Pastikan tabel `vehicle_bbm_allowed` ada dan terisi (v2.131.4).

Insiden 20 Nov 2026: rekonsiliasi Subsidi Tepat (15:37–15:46) menghilangkan
tabel ini dari DB master `bpf_asset_system` — DB yang dipakai cabang SBY &
MALANG. `validate_bbm_for_vehicle()` lalu menolak SEMUA klaim BBM driver
dengan HTTP 400 `Table ... doesn't exist` sampai 23 Nov.

Modul ini membuat tabel secara idempoten (struktur sama dengan DB cabang:
tanpa foreign key, karena `vehicles.vehicle_type` di master tidak unik) dan
mengisi kombinasi kendaraan×BBM standar hanya bila tabel masih kosong.
Dijalankan saat startup untuk master + seluruh cabang, dan dipanggil ulang
oleh validator bila error 1146 terdeteksi.
"""

_DDL = """
CREATE TABLE IF NOT EXISTS vehicle_bbm_allowed (
  id int(11) NOT NULL AUTO_INCREMENT,
  vehicle_type varchar(50) NOT NULL,
  bbm_type varchar(50) NOT NULL,
  min_km_per_liter decimal(10,2) DEFAULT 5.00,
  max_km_per_liter decimal(10,2) DEFAULT 18.00,
  warning_km_per_liter decimal(10,2) DEFAULT 10.50,
  good_km_per_liter decimal(10,2) DEFAULT 12.50,
  is_default tinyint(1) DEFAULT 0,
  created_at timestamp NULL DEFAULT current_timestamp(),
  updated_at timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY unique_vehicle_bbm (vehicle_type,bbm_type),
  KEY bbm_type (bbm_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""

# Seed hanya saat tabel kosong. Sumbernya master data yang sudah ada supaya
# aman untuk instalasi baru (tanpa parent → tidak ada baris, tanpa FK error).
_SEED = """
INSERT IGNORE INTO vehicle_bbm_allowed
  (vehicle_type, bbm_type, min_km_per_liter, max_km_per_liter,
   warning_km_per_liter, good_km_per_liter, is_default)
SELECT v.vehicle_type, b.name AS bbm_type, 5.00, 18.00, 10.50, 12.50,
       CASE WHEN b.name = v.bbm_default THEN 1 ELSE 0 END
FROM (
    SELECT vehicle_type, MAX(bbm_default) AS bbm_default
    FROM vehicles
    GROUP BY vehicle_type
) v
JOIN bbm_types b ON b.is_active = 1
"""


def ensure_vehicle_bbm_schema(conn=None):
    """Buat + seed tabel vehicle_bbm_allowed di SATU database (idempoten).

    `conn` boleh koneksi master maupun cabang. Bila None, memakai master.
    Return True bila tabel tersedia setelah pemanggilan.
    """
    own = conn is None
    if own:
        from modules.config import get_master_connection
        conn = get_master_connection()
    if not conn:
        return False

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(_DDL)
        cur.execute("SELECT COUNT(*) FROM vehicle_bbm_allowed")
        row = cur.fetchone()
        empty = (int(row[0]) if row else 0) == 0
        if empty:
            try:
                cur.execute(_SEED)
            except Exception as seed_err:
                # Tabel sudah dibuat; seed bisa gagal di DB baru tanpa
                # vehicles/bbm_types. Jangan gagalkan startup karenanya.
                print(f"[vehicle-bbm] seed: {seed_err}")
        conn.commit()
        return True
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[vehicle-bbm] ensure schema: {exc}")
        return False
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if own:
            try:
                conn.close()
            except Exception:
                pass
