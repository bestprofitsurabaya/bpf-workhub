"""Identitas perusahaan / cabang (v2.19.2) — variabel dinamis multi-cabang.

Nilai disimpan di tabel `system_config` (bisa diubah Admin di /app/settings),
dengan fallback ke default saat DB tidak tersedia atau key belum diset.

Dipakai oleh: PDF generator (kop surat & footer), branding frontend
(login, sidebar, judul tab), watermark foto, dan halaman login — sehingga
aplikasi bisa dipakai ulang oleh cabang perusahaan lain tanpa ubah kode.
"""
IDENTITY_KEYS = ('company_name', 'company_subtitle', 'system_name', 'system_version',
                  'company_address', 'company_phone')

IDENTITY_DEFAULTS = {
    'company_name': 'PT BESTPROFIT FUTURES',
    'company_subtitle': 'Kantor Pusat | Jakarta',
    'system_name': 'BPF WorkHub',
    'system_version': 'v2.35.1',
    'company_address': 'Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190',
    'company_phone': '031-5349888',
}


def get_company_identity(conn=None):
    """Baca identitas dari system_config; key yang belum diset → default.

    Aman dipanggil tanpa DB (mis. saat tes / DB warming up) — mengembalikan
    default murni.
    """
    own_conn = conn is None
    result = dict(IDENTITY_DEFAULTS)
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    if not conn:
        return result
    cursor = conn.cursor(dictionary=True)
    try:
        placeholders = ','.join(['%s'] * len(IDENTITY_KEYS))
        cursor.execute(
            f"SELECT config_key, config_value FROM system_config WHERE config_key IN ({placeholders})",
            IDENTITY_KEYS)
        for row in cursor.fetchall():
            val = row.get('config_value')
            if val not in (None, ''):
                result[row['config_key']] = str(val).strip()
    except Exception:
        pass
    finally:
        cursor.close()
        if own_conn and conn:
            conn.close()
    return result


def save_company_identity(values, conn=None):
    """Simpan identitas (hanya key yang dikenal di IDENTITY_KEYS).

    values: dict {key: value}. Return dict key yang berhasil disimpan.
    """
    own_conn = conn is None
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    saved = {}
    if not conn:
        return saved
    cursor = conn.cursor()
    try:
        for key in IDENTITY_KEYS:
            if key in values:
                val = str(values[key] or '').strip()
                cursor.execute(
                    "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (key, val))
                saved[key] = val
        conn.commit()
    finally:
        cursor.close()
        if own_conn and conn:
            conn.close()
    return saved
