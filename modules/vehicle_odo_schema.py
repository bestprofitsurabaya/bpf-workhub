"""KM awal kendaraan (v2.108.0) — idempoten.

Kendaraan operasional sudah berjalan sebelum masuk sistem, jadi ODO tidak
mulai dari 0. Kolom `vehicles.initial_odo_km` menyimpan odometer saat
kendaraan mulai dipakai. Nilai ini menjadi **acuan awal** di aplikasi driver;
setelah ada transaksi, ODO terakhir dari transaksi yang dipakai.

Kolom tidak menimpa riwayat: mengubah KM awal hanya memengaruhi entri baru.
Dijalankan saat startup untuk DB master + setiap DB cabang.
"""
from modules.config import get_master_connection


def ensure_vehicle_odo_schema(conn=None):
    """Pastikan `vehicles.initial_odo_km` ada. `conn` opsional (master bila None)."""
    own = conn is None
    if conn is None:
        conn = get_master_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS "
            "initial_odo_km INT NOT NULL DEFAULT 0")
        conn.commit()
        return True
    except Exception as e:
        print(f'[vehicle-odo] ensure error: {e}')
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
