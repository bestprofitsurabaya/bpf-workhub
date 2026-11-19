"""Kolom bukti GPS: `gps_at` + `gps_accuracy` (v2.127.3).

Audit GPS 19 Nov 2026 (temuan G5): payload driver hanya mengirim koordinat
dan alamat. Tanpa waktu pengambilan posisi dan angka akurasi, GA tidak bisa
menilai apakah bukti foto memakai posisi yang segar dan teliti.

Modul ini menambah dua kolom nullable ke semua tabel yang menyimpan bukti
GPS — idempoten, aman dipanggil tiap startup untuk master + tiap DB cabang.
"""
from datetime import datetime

# Tabel bukti GPS: transaksi BBM/LPJ, trip driver, lembur OB & driver.
GPS_TABLES = ('transactions', 'trip_masters', 'overtime_driver', 'overtime_ob_security')

GPS_COLUMN_DEFS = (
    ('gps_at', 'DATETIME NULL'),
    ('gps_accuracy', 'INT NULL'),
)

# Batas akurasi wajar (meter). Di atas ini bukan posisi GPS sungguhan.
_MAX_ACCURACY_M = 100000


def ensure_gps_schema(conn=None):
    """Idempoten: tambah kolom gps_at/gps_accuracy ke tabel bukti (satu DB).

    Kolom yang sudah ada dilewati (ADD COLUMN IF NOT EXISTS, MariaDB 10.11).
    Tabel yang belum dibuat juga dilewati — jangan gagalkan startup.
    """
    own = conn is None
    if conn is None:
        from modules.config import get_master_connection
        conn = get_master_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        for table in GPS_TABLES:
            for col, definition in GPS_COLUMN_DEFS:
                try:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {definition}")
                except Exception as col_err:
                    # Tabel belum ada / kolom sudah ada — bukan alasan gagal.
                    print(f"[gps-schema] {table}.{col}: {col_err}")
        conn.commit()
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if own:
            try:
                conn.close()
            except Exception:
                pass


def parse_gps_at(value):
    """Normalisasi waktu posisi GPS → 'YYYY-MM-DD HH:MM:SS' atau None.

    Menerima ISO-8601 (dengan/tanpa milidetik, `Z` atau offset), format
    MySQL, dan `DD/MM/YYYY HH:MM:SS`. Nilai tak dikenali diabaikan (NULL)
    — waktu posisi bersifat pelengkap, bukan syarat submit.
    """
    raw = str(value or '').strip()
    if not raw:
        return None
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    dt = None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d-%m-%Y %H:%M:%S'):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except (TypeError, ValueError):
                continue
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Simpan sebagai waktu lokal server (kolom DATETIME tanpa zona).
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_gps_accuracy(value):
    """Akurasi GPS (meter) → int positif, atau None bila tidak masuk akal."""
    if value is None or str(value).strip() == '':
        return None
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if n <= 0 or n > _MAX_ACCURACY_M:
        return None
    return n
