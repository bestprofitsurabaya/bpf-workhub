"""Helper functions for BPF WorkHub"""
import os
import json
import ipaddress
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

production_pool_executor = ThreadPoolExecutor(max_workers=20)

def safe_float(val, default=0.0):
    """Convert Decimal/None/str to float safely"""
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default

def resolve_user_pin(pin_field):
    """Kebijakan update PIN user (ISO/IEC 27001 A.9.4 — integritas kredensial).

    Mengembalikan PIN baru HANYA bila field `pin` dikirim eksplisit dan tidak kosong.
    Jika tidak dikirim / kosong, kembalikan None — artinya "jangan ubah";
    pemanggil (route) yang memutuskan untuk mempertahankan PIN yang sudah ada
    atau memakai default untuk user baru.

    >>> resolve_user_pin('111222')
    '111222'
    >>> resolve_user_pin(None) is None
    True
    >>> resolve_user_pin('') is None
    True
    >>> resolve_user_pin('   ') is None
    True
    """
    if pin_field is not None and str(pin_field or '').strip():
        return str(pin_field).strip()
    return None

def finalize_pin(pin, existing_pin=None, default='123456'):
    """Fallback PIN di level route (ISO/IEC 27001 A.9.4).

    `pin` None (artinya "jangan ubah" dari resolve_user_pin) -> pertahankan
    existing_pin; bila user baru (tidak ada existing) -> default.

    >>> finalize_pin('777333', existing_pin='555111')
    '777333'
    >>> finalize_pin(None, existing_pin='555111')
    '555111'
    >>> finalize_pin(None, existing_pin=None)
    '123456'
    """
    if pin is not None:
        return pin
    return existing_pin if existing_pin is not None else default

def resolve_driver_form_context(driver_data, driver_name, nopol, vehicle_type, bbm_type):
    """Resolve the final driver context for claim submission using master data when available."""
    resolved_nopol = nopol
    resolved_vehicle_type = vehicle_type
    resolved_bbm_type = bbm_type
    if driver_data:
        resolved_nopol = driver_data.get('nopol') or resolved_nopol
        resolved_vehicle_type = driver_data.get('vehicle_type') or resolved_vehicle_type
        resolved_bbm_type = driver_data.get('bbm_type') or resolved_bbm_type
    return {
        'driver_name': driver_name,
        'nopol': resolved_nopol,
        'vehicle_type': resolved_vehicle_type,
        'bbm_type': resolved_bbm_type,
    }

_generated_display_ids = set()
_display_id_lock = threading.Lock()


def generate_display_id(prefix='BPF', conn=None):
    """Generate unique display ID: BPF-YYYYMMDD-HHMMSSXX (timestamp + random).

    Uniqueness dijaga via dedupe in-memory thread-safe + double-check di DB
    bila koneksi tersedia.
    """
    import random, string
    now = datetime.now()
    date_part = now.strftime('%Y%m%d')
    time_part = now.strftime('%H%M%S')

    def _candidate():
        random_part = ''.join(random.choices(string.digits, k=2))
        return f"{prefix}-{date_part}-{time_part}{random_part}"

    unique_id = _candidate()
    guard = 0
    with _display_id_lock:
        while unique_id in _generated_display_ids:
            unique_id = _candidate()
            guard += 1
            if guard > 500:
                break
        _generated_display_ids.add(unique_id)

    # Double-check uniqueness in DB (rare collision lintas-restart)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE display_id = %s", (unique_id,))
            exists = cursor.fetchone()[0]
            cursor.close()
            if exists > 0:
                with _display_id_lock:
                    unique_id = _candidate()
                    _generated_display_ids.add(unique_id)
        except Exception:
            pass

    return unique_id

def generate_trip_display_id(conn=None):
    """Generate trip display ID: TRIP-YYYYMMDD-XXXX"""
    return generate_display_id('TRIP', conn)

# Ekstensi bukti yang diizinkan (ISO/IEC 27001 A.8.2 — hanya file aman).
ALLOWED_UPLOAD_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'pdf'}


def save_file(file_obj, prefix, nopol, upload_folder):
    """Save uploaded file with timestamp prefix — HARDENED.

    Keamanan (sebelumnya celah path traversal & stored XSS):
    - `secure_filename` menghilangkan path (../, /, \\) & karakter berbahaya.
    - Ekstensi di-whitelist (hanya gambar & PDF) — file .html/.svg/.py dsb DITOLAK.
    - Nama file dibangkitkan server-side (tidak memakai nama asli user).
    Return nama file bila berhasil, None bila tidak ada/berbahaya.
    """
    if file_obj and file_obj.filename:
        from werkzeug.utils import secure_filename
        raw = secure_filename(file_obj.filename)
        if not raw or '.' not in raw:
            return None
        ext = raw.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXT:
            print(f"[save_file] DITOLAK ekstensi tidak aman: {raw!r}")
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_nopol = secure_filename(str(nopol)) or 'x'
        filename = f"{prefix}_{safe_nopol}_{ts}_{secrets_rand(6)}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        try:
            file_obj.save(filepath)
        except Exception as e:
            print(f"[save_file] gagal simpan: {e}")
            return None
        return filename
    return None


def secrets_rand(n=6):
    """Acak aman (hex) untuk nama file — menghindari tabrakan & tebakan."""
    import secrets as _s
    return _s.token_hex(n // 2 + 1)[:n]

def log_activity_async(tx_id, action, user_type, user_name, old_data=None, new_data=None, ip=None, ua=None, branch_code=None):
    """Log activity asynchronously.

    Cabang aktif (session['branch_code']) ditangkap di thread pemanggil lalu
    dicatat ke activity_logs.branch_code — jejak audit lintas cabang (v2.20.0).
    Caller dapat menimpa dengan `branch_code` eksplisit (mis. aksi yang menyasar
    cabang lain, seperti seed-demo per cabang).
    """
    from modules.config import get_db_connection
    # Sesi Flask hanya valid di thread pemanggil — tangkap di sini, bukan di _log.
    if branch_code is None:
        try:
            from flask import session as _s
            branch_code = _s.get('branch_code')
        except Exception:
            pass
    def _log():
        conn = None
        try:
            conn = get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            # tx_id 0/'0' dipakai banyak caller untuk aksi tanpa transaksi terkait;
            # activity_logs.transaction_id ber-FK ke transactions(id) sehingga
            # 0 ditolak DB (1452) dan membanjiri log error. NULL = tanpa referensi.
            log_tx_id = tx_id if isinstance(tx_id, int) and tx_id > 0 else None
            cursor.execute("""
                INSERT INTO activity_logs (transaction_id, action, user_type, user_name, old_data, new_data, ip_address, user_agent, branch_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (log_tx_id, action, user_type, user_name,
                  json.dumps(old_data) if old_data else None,
                  json.dumps(new_data) if new_data else None, ip, ua, branch_code))
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Log error: {e}")
        finally:
            # Selalu kembalikan koneksi ke pool — koneksi yang bocor akan
            # menghabiskan pool (10–15) dan melumpuhkan seluruh aplikasi.
            if conn:
                try: conn.close()
                except Exception: pass
    production_pool_executor.submit(_log)

def validate_bbm_for_vehicle(vehicle_type, bbm_type):
    """Validate BBM type for vehicle"""
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn: return {'valid': False, 'error': 'DB error'}
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM vehicle_bbm_allowed WHERE vehicle_type=%s AND bbm_type=%s", (vehicle_type, bbm_type))
        result = cursor.fetchone()
        cursor.close(); conn.close()
        if result:
            return {'valid': True, 'limits': {
                'min': result['min_km_per_liter'], 'max': result['max_km_per_liter'],
                'warning': result['warning_km_per_liter'], 'good': result['good_km_per_liter']
            }}
        return {'valid': False, 'error': f'BBM {bbm_type} tidak tersedia untuk {vehicle_type}'}
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def get_or_create_driver(driver_name, nopol, vehicle_type, bbm_type='PERTALITE'):
    """Auto-discover or create driver profile"""
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name, is_active FROM drivers WHERE name = %s", (driver_name,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE drivers SET nopol = %s, vehicle_type = %s, bbm_type = %s, is_active = TRUE
                WHERE name = %s
            """, (nopol, vehicle_type, bbm_type, driver_name))
        else:
            cursor.execute("""
                INSERT INTO drivers (name, nopol, vehicle_type, bbm_type, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
            """, (driver_name, nopol, vehicle_type, bbm_type))
        conn.commit()
        cursor.close(); conn.close()
        return True
    except Exception as e:
        print(f"get_or_create_driver error: {e}")
        return False

def get_or_create_vehicle(vehicle_type, brand='TOYOTA', capacity=45):
    """Auto-discover or create vehicle type"""
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM vehicles WHERE vehicle_type = %s", (vehicle_type,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO vehicles (vehicle_type, brand, fuel_capacity, is_active)
                VALUES (%s, %s, %s, TRUE)
            """, (vehicle_type, brand, capacity))
            conn.commit()
        cursor.close(); conn.close()
        return True
    except Exception as e:
        print(f"get_or_create_vehicle error: {e}")
        return False

def get_or_create_bbm(bbm_type, price_per_liter=10000):
    """Auto-discover or create BBM type"""
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM bbm_types WHERE name = %s", (bbm_type,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO bbm_types (name, price_per_liter, is_active)
                VALUES (%s, %s, TRUE)
            """, (bbm_type, price_per_liter))
            conn.commit()
        cursor.close(); conn.close()
        return True
    except Exception as e:
        print(f"get_or_create_bbm error: {e}")
        return False

def get_or_create_vehicle_bbm_allowed(vehicle_type, bbm_type):
    """Auto-discover or create vehicle-BBM allowed relation"""
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id FROM vehicle_bbm_allowed WHERE vehicle_type = %s AND bbm_type = %s
        """, (vehicle_type, bbm_type))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO vehicle_bbm_allowed 
                (vehicle_type, bbm_type, min_km_per_liter, max_km_per_liter, warning_km_per_liter, good_km_per_liter, is_default)
                VALUES (%s, %s, 5.0, 20.0, 10.0, 12.5, FALSE)
            """, (vehicle_type, bbm_type))
            conn.commit()
        cursor.close(); conn.close()
        return True
    except Exception as e:
        print(f"get_or_create_vehicle_bbm_allowed error: {e}")
        return False

def ensure_all_master_data(driver_name, nopol, vehicle_type, bbm_type, price_per_liter=10000):
    """One-call to ensure all master data exists"""
    get_or_create_vehicle(vehicle_type)
    get_or_create_bbm(bbm_type, price_per_liter)
    get_or_create_vehicle_bbm_allowed(vehicle_type, bbm_type)
    get_or_create_driver(driver_name, nopol, vehicle_type, bbm_type)
    return True
# ============================================================
# TAMBAHKAN INI DI AKHIR FILE helpers.py
# (Sebelum baris terakhir, setelah fungsi ensure_all_master_data)
# ============================================================

# --- AUTH DECORATORS ---
from functools import wraps
from flask import request, jsonify, session, g, redirect, flash

def _auth_denied_response():
    """Respons saat belum login: halaman -> redirect ke SPA login, API/SPA -> JSON 401."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'msg': 'Akses ditolak. Silakan login terlebih dahulu.'}), 401
    # v2.5: halaman klasik dipensiunkan — semua login lewat SPA /app/login
    return redirect('/app/login')

def _auth_forbidden_response():
    """Respons saat role tidak sesuai: halaman -> redirect ke home sesuai role, API/SPA -> JSON 403."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'msg': 'Role tidak diizinkan untuk aksi ini.'}), 403
    return redirect(home_for_role(session.get('user_role')))

def role_required(allowed_roles):
    """
    Decorator: Hanya izinkan user dengan role tertentu.
    Bekerja dengan session-based auth (login PIN).
    
    Usage:
        @app.route('/admin/settings')
        @role_required(['admin'])
        def settings():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Cek session dulu
            user_role = session.get('user_role')
            user_name = session.get('user_name')

            if not user_role:
                return _auth_denied_response()

            if user_role not in allowed_roles:
                return _auth_forbidden_response()

            # Simpan ke g untuk dipakai di view
            g.user_role = user_role
            g.user_name = user_name

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Shortcut decorator: hanya admin."""
    return role_required(['admin'])(f)


def ga_or_admin_required(f):
    """Shortcut decorator: GA atau admin."""
    return role_required(['ga', 'admin'])(f)


def finance_or_admin_required(f):
    """Shortcut decorator: Finance atau admin."""
    return role_required(['finance', 'admin'])(f)


# ============================================================
# APPOINTMENT SYSTEM HELPERS
# ============================================================

# Sesi perjalanan appointment. Sesi 1 = 08.30, Sesi 2 = 14.30.
SESI_INFO = {
    '1': {'label': 'Sesi 1', 'time': '08:30', 'display': '08.30', 'icon': '🌅'},
    '2': {'label': 'Sesi 2', 'time': '14:30', 'display': '14.30', 'icon': '🌆'},
}
VALID_SESI = ('1', '2')
APPOINTMENT_STATUSES = ('scheduled', 'assigned', 'completed', 'cancelled')

# Rentang jam kunjungan bebas per sesi (v2.15 — masukan Marketing).
# Marketing tetap memilih sesi, lalu bisa menentukan jam spesifik kunjungan
# di dalam rentang sesi tersebut (default: jam mulai sesi).
SESI_TIME_RANGE = {
    '1': ('08:00', '12:59'),
    '2': ('13:00', '17:59'),
}


def sesi_info(sesi):
    """Return dict sesi (label, waktu mulai, display) atau None jika tidak valid."""
    return SESI_INFO.get(str(sesi))


def sesi_time(sesi):
    """Jam mulai sesi sebagai string HH:MM ('08:30' / '14:30')."""
    info = SESI_INFO.get(str(sesi))
    return info['time'] if info else None


def normalize_visit_time(value, sesi):
    """Normalisasi jam kunjungan appointment (HH:MM) dalam rentang sesi.

    - Kosong -> jam mulai sesi (default 08:30 / 14:30).
    - Format HH:MM (24 jam) wajib; di luar rentang sesi ditolak.

    Return (normalized_time_str | None, error_msg | None).
    """
    sesi = str(sesi or '').strip()
    if sesi not in VALID_SESI:
        return None, 'Pilih sesi yang valid terlebih dahulu'
    raw = str(value or '').strip()
    if not raw:
        return sesi_time(sesi), None
    try:
        hh, mm = raw.split(':')[:2]
        hh, mm = int(hh), int(mm)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None, 'Format jam harus HH:MM (contoh 09:30)'
    except (ValueError, AttributeError):
        return None, 'Format jam harus HH:MM (contoh 09:30)'
    t = f'{hh:02d}:{mm:02d}'
    lo, hi = SESI_TIME_RANGE.get(sesi, ('00:00', '23:59'))
    if t < lo or t > hi:
        label = SESI_INFO.get(sesi, {}).get('label', sesi)
        return None, f'Jam kunjungan harus dalam rentang {label} ({lo}–{hi})'
    return t, None


# Pemetaan kata kunci area -> zona (digunakan untuk membantu Chief Driver
# membagi driver berdasarkan wilayah, dan preview otomatis untuk marketing).
AREA_KEYWORDS = [
    ('Surabaya Pusat', ['surabaya pusat', 'pasar atom', 'tunjungan', 'genteng', 'gubeng', 'tegalsari', 'sawahan', 'simokerto', 'bubutan', 'krejongan', 'gemblongan']),
    ('Surabaya Barat', ['surabaya barat', 'darmo', 'darmo permai', 'darmo park', 'wiyung', 'karang pilang', 'lakarsantri', 'benowo', 'pakal', 'tandes', 'sukomanunggal', 'asemrowo']),
    ('Surabaya Utara', ['surabaya utara', 'kenjeran', 'bulak', 'semampir', 'pabean cantian', 'krembangan', 'perak', 'tanjung perak']),
    ('Surabaya Timur', ['surabaya timur', 'rungkut', 'gunung anyar', 'mulyorejo', 'sukolilo', 'tambaksari', 'tenggilis', 'gayungan', 'wonocolo', 'medokan']),
    ('Surabaya Selatan', ['surabaya selatan', 'wonokromo', 'jambangan', 'wonokusumo', 'karang gayam', 'pucang', 'siwalankerto', 'ketintang']),
    ('Sidoarjo', ['sidoarjo', 'gedangan', 'taman', 'waru', 'sedati', 'buduran', 'candi', 'tanggulangin', 'porong', 'jabon', 'krian', 'balongbendo', 'wonoayu', 'tarik', 'prambon', 'tulangan']),
    ('Gresik', ['gresik', 'kebomas', 'manyar', 'bunder', 'driyorejo', 'menganti', 'cerme']),
    ('Mojokerto', ['mojokerto', 'puri', 'sooko', 'jetis', 'gedeg', 'dawarblandong']),
    ('Pasuruan', ['pasuruan', 'pandaan', 'gempol', 'bangil', 'beji']),
    ('Lamongan', ['lamongan', 'kembangbahu', 'sugio', 'turi', 'paciran']),
]


def detect_area(alamat):
    """Deteksi zona wilayah dari teks alamat (Surabaya & sekitarnya).

    Return nama area ('Surabaya Timur', 'Sidoarjo', ...) atau 'Lainnya'.
    """
    if not alamat:
        return 'Lainnya'
    text = str(alamat).lower()
    for area, keywords in AREA_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return area
    return 'Lainnya'


def generate_appointment_display_id(conn=None):
    """Generate display ID appointment: APP-YYYYMMDD-HHMMSSXX"""
    return generate_display_id('APP', conn)


def get_or_create_team(name, leader_name=''):
    """Pastikan tim marketing ada di marketing_teams; return nama tim."""
    name = (name or '').strip()
    if not name:
        return ''
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn:
            return name
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO marketing_teams (name, leader_name, is_active) VALUES (%s, %s, 1) "
            "ON DUPLICATE KEY UPDATE is_active=1",
            (name, leader_name)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"get_or_create_team error: {e}")
    return name


def register_marketing_member(team_name, member_name):
    """Auto-register anggota tim marketing ke tabel marketing_members.

    Setiap nama marketing yang dipakai saat input appointment dicatat sekali
    (per tim) sehingga bisa jadi daftar saran (datalist) pada input berikutnya.
    """
    team_name = (team_name or '').strip()
    member_name = (member_name or '').strip()
    if not member_name:
        return False
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO marketing_members (team_name, member_name, is_active) "
            "VALUES (%s, %s, 1) "
            "ON DUPLICATE KEY UPDATE is_active=1, updated_at=NOW()",
            (team_name, member_name)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"register_marketing_member error: {e}")
        return False


def get_team_members(team_name):
    """Daftar anggota marketing aktif untuk satu tim (untuk saran input)."""
    team_name = (team_name or '').strip()
    from modules.config import get_db_connection
    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_name FROM marketing_members "
            "WHERE team_name=%s AND is_active=1 ORDER BY member_name",
            (team_name,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [r['member_name'] for r in rows]
    except Exception as e:
        print(f"get_team_members error: {e}")
        return []


def validate_appointment_input(item):
    """Validasi satu item input appointment.

    Return (is_valid, errors_dict, normalized_dict).
    """
    errors = {}
    nasabah = str(item.get('nasabah_name', '') or '').strip()
    alamat = str(item.get('alamat', '') or '').strip()
    sesi = str(item.get('sesi', '') or '').strip()
    tanggal = str(item.get('appointment_date', '') or item.get('date', '') or '').strip()
    phone = str(item.get('nasabah_phone', '') or '').strip()
    notes = str(item.get('notes', '') or '').strip()
    member = str(item.get('marketing_member', '') or '').strip()

    # Jam kunjungan: bebas dalam rentang sesi (default = jam mulai sesi)
    visit_time, vt_err = normalize_visit_time(item.get('visit_time'), sesi)
    if vt_err:
        errors['visit_time'] = vt_err

    if not nasabah:
        errors['nasabah_name'] = 'Nama calon nasabah wajib diisi'
    if not alamat:
        errors['alamat'] = 'Alamat wajib diisi'
    elif len(alamat) > 500:
        errors['alamat'] = 'Alamat maksimal 500 karakter'
    if sesi not in VALID_SESI:
        errors['sesi'] = 'Pilih sesi (1 = 08.30 atau 2 = 14.30)'
    if not tanggal:
        errors['appointment_date'] = 'Tanggal appointment wajib diisi'
    if not member:
        errors['marketing_member'] = 'Nama marketing yang memprospek wajib diisi'
    if len(nasabah) > 150:
        errors['nasabah_name'] = 'Nama maksimal 150 karakter'
    if len(phone) > 30:
        errors['nasabah_phone'] = 'No. HP maksimal 30 karakter'
    if len(member) > 100:
        errors['marketing_member'] = 'Nama marketing maksimal 100 karakter'

    normalized = {
        'nasabah_name': nasabah,
        'nasabah_phone': phone,
        'alamat': alamat,
        'sesi': sesi,
        'appointment_date': tanggal,
        'visit_time': visit_time,
        'notes': notes[:500],
        'marketing_member': member,
    }
    return (not errors, errors, normalized)


# ============================================================
# SPA V2.0 — Home per role (sumber tunggal, dipakai routes_auth & routes_spa)
# ============================================================
ROLE_HOME = {
    'marketing': '/app/marketing',
    'chief_driver': '/app/chief-driver',
    'driver': '/app/driver',
    'ob': '/app/water',
    'finance': '/app/finance',   # v2.7: dashboard khusus Finance (rekap air minum + kasbon)
    'ga': '/app/ga',             # v2.8: dashboard khusus GA (antrean klaim + kasbon + trip)
    'receptionist': '/app/receptionist',  # v2.16: sistem pelamar kerja (verifikasi & kehadiran)
    'traineer': '/app/traineer',          # v2.16: pantau rekrutan (upline)
    'ga_hr': '/app/ga-hr',                # v2.22: data overtime (Driver + OB/Security)
    'it_sby': '/app/it', 'it_hu': '/app/it', 'it_jkt2': '/app/it', 'it_bdg': '/app/it', 'it_smg': '/app/it', 'it_mlg': '/app/it', 'it_mdn': '/app/it', 'it_bjm': '/app/it', 'it_plm': '/app/it', 'it_lpg': '/app/it',
}


def home_for_role(role):
    """Halaman awal sesuai role user setelah login (SPA /app/*)."""
    return ROLE_HOME.get(role, '/app/dashboard')


# ============================================================
# PELAMAR KERJA (v2.16) — tahapan interview + 4 hari training
# ============================================================
APPLICANT_STAGES = ('interview', 'training_1', 'training_2', 'training_3', 'training_4')
APPLICANT_STATUSES = ('interview', 'training_1', 'training_2', 'training_3', 'training_4',
                      'lulus', 'resigned', 'rejected')

APPLICANT_STAGE_LABELS = {
    'interview': 'Interview',
    'training_1': 'Training Hari 1',
    'training_2': 'Training Hari 2',
    'training_3': 'Training Hari 3',
    'training_4': 'Training Hari 4',
}

APPLICANT_STATUS_LABELS = {
    'interview': '📅 Interview',
    'training_1': '📘 Training H1',
    'training_2': '📗 Training H2',
    'training_3': '📙 Training H3',
    'training_4': '📕 Training H4',
    'lulus': '🎓 Lulus',
    'resigned': '🚪 Mengundurkan Diri',
    'rejected': '✕ Ditolak',
}


def applicant_stage_label(stage):
    return APPLICANT_STAGE_LABELS.get(str(stage), str(stage))


def applicant_status_label(status):
    return APPLICANT_STATUS_LABELS.get(str(status), str(status))


def session_driver_name():
    """Nama driver dari sesi (role 'driver' → username di-UPPER-kan) atau None.

    Dipakai endpoint driver (v2.4): sesi login PIN driver menjadi identitas
    tunggal yang TIDAK bisa dipalsukan lewat parameter `driver`/`driver_name`
    (anti impersonasi & IDOR antar driver — ISO/IEC 27001 A.8.2).
    Jalur legacy (PWA klasik tanpa sesi) tetap memakai parameter query/form.

    >>> from flask import session
    >>> # (perlu Flask test request context; lihat tests/test_driver_session.py)
    """
    if session.get('user_role') == 'driver':
        return (session.get('user_name') or '').strip().upper() or None


def resolve_driver_scope(param_value=''):
    """Identitas driver efektif untuk endpoint scope (v2.5 — jalur legacy ditutup).

    - Sesi role 'driver' → identitas sesi (tidak bisa dipalsukan via param).
    - Sesi back-office (admin/ga/finance/...) → param eksplisit diizinkan
      (UI admin query data per driver); '' bila tanpa param (artinya semua).
    - Tanpa sesi sama sekali → None; pemanggil wajib menolak 401.
      (Sebelum v2.5, param `?driver=` anonim masih diterima — kini DITUTUP.)
    """
    sid = session_driver_name()
    if sid:
        return sid
    if session.get('user_role'):
        return (param_value or '').strip().upper()
    return None


# ============================================================
# Rate limiting login sederhana (ISO/IEC 27001 A.8.5 · anti brute-force)
# In-memory per-IP: 5x gagal dalam 5 menit → lockout 15 menit.
# Single-process (eventlet) sehingga aman memakai dict global.
# ============================================================
import time
import json as _json

# ============================================================
# Backing store rate limit (ISO/IEC 27001 A.8.5 · A.12.6)
# Redis bila tersedia (konsisten antar replica), fallback memori proses.
# ============================================================
try:
    import redis as _redis_lib
except ImportError:
    _redis_lib = None

_redis_client = None
_redis_retry_at = 0.0


def _get_redis():
    """Klien Redis lazy singleton; None bila tidak dikonfigurasi / gagal connect.

    Bila Redis down saat mencoba, tidak di-set permanen: retry dilakukan
    maksimal 1x per 30 detik (cooldown) sehingga Redis yang pulih otomatis
    dipakai lagi — sementara itu fallback memori menjaga layanan tetap jalan.
    """
    global _redis_client, _redis_retry_at
    if _redis_client is not None:
        return _redis_client
    now = time.time()
    if now < _redis_retry_at:
        return None
    _redis_retry_at = now + 30
    if _redis_lib is None:
        return None
    url = os.environ.get('REDIS_URL', '').strip()
    if not url:
        return None
    try:
        _redis_client = _redis_lib.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


class _RateStore:
    """State rate limit: Redis (atomik, TTL) dengan fallback dict memori proses.

    Path Redis memakai INCR/EXPIRE atomik sehingga penghitungan gagal tidak
    hilang saat request paralel (anti brute-force efektif); fallback memori
    mempertahankan perilaku lama (cek window saat baca).
    """

    def __init__(self, prefix):
        self._prefix = prefix
        self._mem = {}

    def _key(self, key, suffix=''):
        return f'bpf_rl:{self._prefix}:{key}{suffix}'

    def record_fail(self, key, window, max_fails, lockout):
        """Catat satu kegagalan secara atomik. Return (locked, retry_after)."""
        now = time.time()
        r = _get_redis()
        if r:
            try:
                base = self._key(key)
                fk = base + ':f'  # first_fail
                lk = base + ':l'  # locked_until
                pipe = r.pipeline(transaction=True)
                pipe.incr(base)
                pipe.expire(base, window + 60)
                pipe.execute()
                if not r.exists(fk):
                    r.setex(fk, window + 60, now)
                first_fail = float(r.get(fk))
                if now - first_fail > window:  # window bergulir: mulai baru
                    r.setex(fk, window + 60, now)
                    r.setex(base, window + 60, 1)
                if int(r.get(base)) >= max_fails:
                    r.setex(lk, lockout + 60, now + lockout)  # nilai = kapan lock berakhir
                    r.delete(base, fk)
                    return True, lockout
                return False, 0
            except Exception:
                pass  # Redis bermasalah → fallback memori
        entry = self._mem.get(key)
        if not entry or now - entry.get('first_fail', now) > window:
            entry = {'fails': 0, 'first_fail': now, 'locked_until': None}
        entry['fails'] += 1
        if entry['fails'] >= max_fails:
            entry['locked_until'] = now + lockout
            entry['fails'] = 0
            self._mem[key] = entry
            return True, lockout
        self._mem[key] = entry
        return False, 0

    def check(self, key, window):
        """Cek status. Return (allowed, retry_after)."""
        now = time.time()
        r = _get_redis()
        if r:
            try:
                lock = r.get(self._key(key, ':l'))
                if lock:
                    lock_ts = float(lock)
                    if now < lock_ts:
                        return False, int(lock_ts - now)
                return True, 0
            except Exception:
                pass
        entry = self._mem.get(key)
        if not entry:
            return True, 0
        if entry.get('locked_until') and now < entry['locked_until']:
            return False, int(entry['locked_until'] - now)
        if now - entry.get('first_fail', now) > window:
            self._mem.pop(key, None)
        return True, 0

    def reset(self, key):
        r = _get_redis()
        if r:
            try:
                base = self._key(key)
                r.delete(base, base + ':f', base + ':l')
            except Exception:
                pass
        self._mem.pop(key, None)


_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW = 300
_LOGIN_LOCKOUT = 900
_login_store = _RateStore('login')


def login_rate_check(ip):
    """Cek apakah IP boleh mencoba login. Return (allowed: bool, retry_after: int)."""
    return _login_store.check(ip, _LOGIN_WINDOW)


def login_fail(ip):
    """Catat percobaan login gagal; kembalikan (locked, retry_after)."""
    return _login_store.record_fail(ip, _LOGIN_WINDOW, _LOGIN_MAX_FAILS, _LOGIN_LOCKOUT)


def login_success(ip):
    """Reset penghitung gagal setelah login sukses."""
    _login_store.reset(ip)


# ============================================================
# Rate limiting /api/verify-pin (ISO/IEC 27001 A.8.5 · anti brute-force PIN)
# Terpisah dari login agar lockout satu jalur tidak mengunci jalur lain.
# 8x gagal / 5 menit per IP → lockout 10 menit.
# ============================================================
_PIN_MAX_FAILS = 8
_PIN_WINDOW = 300
_PIN_LOCKOUT = 600
_pin_store = _RateStore('pin')


def _is_trusted_proxy(ip):
    """True bila peer TCP adalah loopback atau IP privat (proxy lokal tepercaya)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private


def client_ip():
    """IP klien anti-spoofing (ISO/IEC 27001 A.12.6 — kontrol teknis).

    - Via Cloudflare Tunnel (cloudflared di host): `CF-Connecting-IP` di-set oleh
      Cloudflare dan request masuk lewat loopback/private → dipercaya.
    - Akses langsung origin (remote_addr publik): header CF bisa dipalsukan klien
      → `CF-Connecting-IP` DIABAIKAN, dipakai `remote_addr` (peer TCP nyata).
    - `X-Forwarded-For` DIABAIKAN total: nilainya dikontrol penuh oleh klien bila
      request sampai ke origin tanpa proxy tepercaya (celah bypass rate limit).
    """
    cf = (request.headers.get('CF-Connecting-IP') or '').strip()
    raddr = (request.remote_addr or '').strip()
    if cf and _is_trusted_proxy(raddr):
        return cf
    return raddr or '?'


def pin_rate_check(ip):
    """Cek apakah IP boleh memverifikasi PIN. Return (allowed, retry_after)."""
    return _pin_store.check(ip, _PIN_WINDOW)


def pin_fail(ip):
    """Catat verifikasi PIN gagal; kembalikan (locked, retry_after)."""
    return _pin_store.record_fail(ip, _PIN_WINDOW, _PIN_MAX_FAILS, _PIN_LOCKOUT)


def pin_success(ip):
    """Reset penghitung setelah verifikasi PIN sukses."""
    _pin_store.reset(ip)
