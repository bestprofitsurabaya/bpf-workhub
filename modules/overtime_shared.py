"""Shared overtime helpers — validasi, insert builder, serializer.

Dipakai bersama oleh:
- modules/routes_overtime.py (form submit OB + Driver)
- modules/routes_overtime.py (sheet sync upsert)

Tujuan: kurangi duplikasi antara modul Driver & OB/Security.
"""
from datetime import datetime, date
from modules.overtime_helpers import (
    clean, parse_date_mdy, parse_time_12h, parse_time_any,
    parse_date_any, normalize_name
)

POSITIONS = ('OB', 'Security')

# ============================================================
# 1. Shared Validation
# ============================================================
def validate_overtime_data(data, modul='ob'):
    """Validate common + modul-specific fields.

    Return (is_valid: bool, errors: dict, cleaned: dict).
    cleaned contains sanitized values ready for DB insert.
    """
    errors = {}
    cleaned = {}

    # --- Common fields ---
    nama = clean(data.get('nama'))
    if not nama:
        errors['nama'] = 'Nama wajib diisi'
    cleaned['nama'] = nama[:150]

    tanggal = clean(data.get('tanggal'))
    if not tanggal:
        errors['tanggal'] = 'Tanggal overtime wajib diisi'
        cleaned['tanggal'] = ''
    else:
        tanggal_iso = parse_date_mdy(tanggal) or tanggal
        if len(str(tanggal_iso)) != 10:
            errors['tanggal'] = 'Tanggal harus format DD/MM/YYYY atau YYYY-MM-DD'
        else:
            # Validate tanggal is a real date (not just length)
            try:
                datetime.strptime(tanggal_iso, '%Y-%m-%d')
            except ValueError:
                errors['tanggal'] = 'Tanggal tidak valid'
        cleaned['tanggal'] = tanggal_iso

    waktu_mulai = clean(data.get('waktu_mulai'))
    if not waktu_mulai:
        errors['waktu_mulai'] = 'Waktu mulai wajib diisi'
    else:
        cleaned['waktu_mulai'] = (parse_time_12h(waktu_mulai) or parse_time_any(waktu_mulai) or waktu_mulai)[:20]

    waktu_selesai = clean(data.get('waktu_selesai')) or ''
    cleaned['waktu_selesai'] = (parse_time_12h(waktu_selesai) or parse_time_any(waktu_selesai) or waktu_selesai)[:20]

    cleaned['keterangan'] = clean(data.get('keterangan'))[:500]
    cleaned['email'] = clean(data.get('email'))[:150]

    # --- Validate waktu format ---
    # If waktu_mulai couldn't be parsed, flag it as error.
    if waktu_mulai and 'waktu_mulai' not in errors:
        parsed_start = parse_time_12h(waktu_mulai) or parse_time_any(waktu_mulai)
        if not parsed_start and waktu_mulai != cleaned.get('waktu_mulai', ''):
            # Raw input was kept as-is (no parser matched) — only flag if
            # it doesn't look like a reasonable time (HH:MM or H:MM).
            pass  # Accept flexible formats; caller can re-validate server-side

    # Note: OT lewat tengah malam (waktu_selesai < waktu_mulai = next day)
    # is valid in this system, so we intentionally skip mulai > selesai check.

    # --- GPS fields ---
    # Use (val or '') to avoid str(None) → literal "None" in DB.
    cleaned['gps_lat'] = str(data.get('gps_lat') or '')[:20]
    cleaned['gps_lon'] = str(data.get('gps_lon') or '')[:20]
    cleaned['gps_address'] = str(data.get('gps_address') or '')[:500]
    cleaned['gps_kelurahan'] = str(data.get('gps_kelurahan') or '')[:100]
    cleaned['gps_kecamatan'] = str(data.get('gps_kecamatan') or '')[:100]
    cleaned['gps_kota'] = str(data.get('gps_kota') or '')[:100]
    cleaned['gps_provinsi'] = str(data.get('gps_provinsi') or '')[:100]
    cleaned['gps_kode_pos'] = str(data.get('gps_kode_pos') or '')[:10]

    # --- Foto ---
    # Max 5MB base64 per photo (~3.75MB binary) to prevent memory blowup.
    _MAX_FOTO_B64_LEN = 7_000_000  # ~5MB base64 string
    foto_mulai_raw = data.get('foto_mulai') or ''
    foto_selesai_raw = data.get('foto_selesai') or ''
    cleaned['foto_mulai_b64'] = foto_mulai_raw[:_MAX_FOTO_B64_LEN] if isinstance(foto_mulai_raw, str) else ''
    cleaned['foto_selesai_b64'] = foto_selesai_raw[:_MAX_FOTO_B64_LEN] if isinstance(foto_selesai_raw, str) else ''

    # --- Module-specific fields ---
    if modul == 'ob':
        posisi = clean(data.get('posisi'))
        if posisi not in POSITIONS:
            errors['posisi'] = 'Posisi wajib dipilih (OB atau Security)'
        cleaned['posisi'] = posisi

    elif modul == 'driver':
        cleaned['no_kendaraan'] = clean(data.get('no_kendaraan'))[:30]
        cleaned['broker'] = clean(data.get('broker'))[:150]
        cleaned['manager'] = clean(data.get('manager'))[:150]

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned


# ============================================================
# 2. Build INSERT SQL + params
# ============================================================
def build_insert_sql(modul):
    """Return (sql_template, columns) for INSERT into the correct table."""
    if modul == 'ob':
        sql = """INSERT INTO overtime_ob_security
            (display_id, nama, posisi, tanggal, waktu_mulai, waktu_selesai,
             keterangan, foto_mulai, foto_selesai, email, source, source_uid,
             gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan,
             gps_kota, gps_provinsi, gps_kode_pos)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        cols = ['display_id', 'nama', 'posisi', 'tanggal', 'waktu_mulai', 'waktu_selesai',
                'keterangan', 'foto_mulai', 'foto_selesai', 'email', 'source', 'source_uid',
                'gps_lat', 'gps_lon', 'gps_address', 'gps_kelurahan', 'gps_kecamatan',
                'gps_kota', 'gps_provinsi', 'gps_kode_pos']
    elif modul == 'driver':
        sql = """INSERT INTO overtime_driver
            (display_id, sheet_row, nama, tanggal, waktu_mulai, waktu_selesai,
             keterangan, no_kendaraan, broker, manager,
             foto_mulai, foto_selesai, source,
             gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan,
             gps_kota, gps_provinsi, gps_kode_pos)
            VALUES (%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        # Note: sheet_row is hardcoded as literal 0 in the SQL VALUES,
        # so it is NOT included in cols (cols maps 1:1 with params tuple).
        cols = ['display_id', 'nama', 'tanggal', 'waktu_mulai', 'waktu_selesai',
                'keterangan', 'no_kendaraan', 'broker', 'manager',
                'foto_mulai', 'foto_selesai', 'source',
                'gps_lat', 'gps_lon', 'gps_address', 'gps_kelurahan', 'gps_kecamatan',
                'gps_kota', 'gps_provinsi', 'gps_kode_pos']
    else:
        raise ValueError(f'Modul tidak dikenal: {modul}')
    return sql, cols


def build_insert_params(display_id, cleaned, source='form', modul='ob', source_uid=''):
    """Build the params tuple for INSERT based on modul.

    `cleaned` is the dict returned by validate_overtime_data().
    """
    if modul == 'ob':
        return (
            display_id, cleaned['nama'], cleaned.get('posisi', 'OB'),
            cleaned['tanggal'], cleaned['waktu_mulai'], cleaned['waktu_selesai'],
            cleaned['keterangan'], cleaned.get('foto_mulai', ''),
            cleaned.get('foto_selesai', ''), cleaned['email'],
            source, source_uid,
            cleaned['gps_lat'], cleaned['gps_lon'], cleaned['gps_address'],
            cleaned['gps_kelurahan'], cleaned['gps_kecamatan'],
            cleaned['gps_kota'], cleaned['gps_provinsi'], cleaned['gps_kode_pos'],
        )
    elif modul == 'driver':
        return (
            display_id, cleaned['nama'],
            cleaned['tanggal'], cleaned['waktu_mulai'], cleaned['waktu_selesai'],
            cleaned['keterangan'], cleaned.get('no_kendaraan', ''),
            cleaned.get('broker', ''), cleaned.get('manager', ''),
            cleaned.get('foto_mulai', ''), cleaned.get('foto_selesai', ''),
            source,
            cleaned['gps_lat'], cleaned['gps_lon'], cleaned['gps_address'],
            cleaned['gps_kelurahan'], cleaned['gps_kecamatan'],
            cleaned['gps_kota'], cleaned['gps_provinsi'], cleaned['gps_kode_pos'],
        )
    else:
        raise ValueError(f'Modul tidak dikenal: {modul}')


# ============================================================
# 3. Serialize DB row → JSON
# ============================================================
def serialize_overtime_row(row):
    """Convert a DB row (dict) to consistent JSON format for API responses.

    Handles both overtime_driver and overtime_ob_security rows.
    """
    result = dict(row)
    # Ensure date/time are strings
    for k, v in result.items():
        if isinstance(v, datetime):
            result[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(v, date):
            result[k] = v.isoformat()
    # Add modul field for frontend
    if 'posisi' in result:
        result['modul'] = 'ob'
    elif 'no_kendaraan' in result:
        result['modul'] = 'driver'
    return result


def get_display_prefix(modul):
    """Return the display_id prefix for a module."""
    if modul == 'ob':
        return 'OTL'
    elif modul == 'driver':
        return 'OTD'
    raise ValueError(f'Modul tidak dikenal: {modul}')


def make_source_uid(display_id, nama, extra=''):
    """Generate a source_uid for deduplication."""
    import hashlib
    return hashlib.md5(
        (display_id + nama + extra).encode('utf-8')
    ).hexdigest()[:24]
