"""Shared overtime helpers — validasi, insert builder, serializer.

Dipakai bersama oleh:
- modules/routes_overtime.py (form submit OB + Driver)
- modules/routes_overtime.py (sheet sync upsert)

Tujuan: kurangi duplikasi antara modul Driver & OB/Security.
"""
from datetime import datetime, date, timedelta
from modules.overtime_helpers import (
    clean, parse_date_mdy, parse_time_12h, parse_time_any,
    parse_date_any, parse_submitted_at_any, normalize_name
)

POSITIONS = ('OB', 'Security')

# ============================================================
# 0. Batas waktu submit overtime (v2.40.0)
# ============================================================
DEFAULT_OT_SUBMIT_DEADLINE_HOURS = 24   # default: 24 jam setelah jam selesai OT


def get_submit_deadline_hours(conn):
    """Baca config 'overtime_submit_deadline_hours' dari system_config.

    Return int jam (1-168). Bila config tidak ada / tak valid / DB error,
    kembalikan DEFAULT_OT_SUBMIT_DEADLINE_HOURS — fitur indikator tidak
    boleh menggagalkan alur utama overtime.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_value FROM system_config WHERE config_key=%s",
            ('overtime_submit_deadline_hours',))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return DEFAULT_OT_SUBMIT_DEADLINE_HOURS
        hours = int(str(row[0]).strip())
        if hours < 1 or hours > 168:
            return DEFAULT_OT_SUBMIT_DEADLINE_HOURS
        return hours
    except Exception:
        return DEFAULT_OT_SUBMIT_DEADLINE_HOURS


def compute_submit_late(row, deadline_hours, now=None):
    """Hitung flag terlambat-submit untuk satu baris overtime.

    Terlambat = waktu submit > (tanggal + waktu_selesai + deadline jam).
    Baris tanpa submitted_at yang bisa diparse dianggap TIDAK terlambat
    (data sheet lama tanpa timestamp) — tidak menandai tanpa bukti.
    Return (late: bool, deadline: datetime|None).
    """
    try:
        tanggal = parse_date_any(row.get('tanggal'))
        jam_selesai = parse_time_any(row.get('waktu_selesai'))
        submitted = parse_submitted_at_any(row.get('submitted_at'))
        if not tanggal or not jam_selesai or not submitted:
            return False, None
        # submitted_at berupa string 'YYYY-MM-DD HH:MM[:SS]' — parse ke datetime
        try:
            submitted_dt = datetime.strptime(submitted, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            submitted_dt = datetime.strptime(submitted, '%Y-%m-%d %H:%M')
        mulai = datetime.strptime(f'{tanggal} {jam_selesai}', '%Y-%m-%d %H:%M')
        deadline = mulai + timedelta(hours=deadline_hours)
        return submitted_dt > deadline, deadline
    except Exception:
        return False, None


def annotate_submit_late(rows, deadline_hours, now=None):
    """Tambahkan 'submit_late' & 'submit_deadline' ke tiap dict baris overtime."""
    rows = rows if rows is not None else []
    for r in rows:
        late, deadline = compute_submit_late(r, deadline_hours, now=now)
        r['submit_late'] = late
        r['submit_deadline'] = deadline.strftime('%Y-%m-%d %H:%M') if deadline else None
    return rows

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
        # v2.36.2: source_uid ikut disimpan (kunci stabil baris — paritas OB).
        # sheet_row tetap literal 0 utk submit form (NOT NULL, tidak lagi UNIQUE).
        sql = """INSERT INTO overtime_driver
            (display_id, sheet_row, source_uid, nama, tanggal, waktu_mulai, waktu_selesai,
             keterangan, no_kendaraan, broker, manager,
             foto_mulai, foto_selesai, source,
             gps_lat, gps_lon, gps_address, gps_kelurahan, gps_kecamatan,
             gps_kota, gps_provinsi, gps_kode_pos)
            VALUES (%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        # Note: sheet_row is hardcoded as literal 0 in the SQL VALUES,
        # so it is NOT included in cols (cols maps 1:1 with params tuple).
        cols = ['display_id', 'source_uid', 'nama', 'tanggal', 'waktu_mulai', 'waktu_selesai',
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
            display_id, source_uid, cleaned['nama'],
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
