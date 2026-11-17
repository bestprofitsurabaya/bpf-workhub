"""MFA TOTP (v2.112.0) — verifikasi dua langkah berbasis aplikasi authenticator.

Mengapa TOTP?
-------------
Tabel `users` tidak menyimpan email/no. HP dan backend tidak punya SMTP, jadi
OTP via email/SMS tidak mungkin dikirim. TOTP (RFC 6238) tidak butuh kanal
pengiriman: rahasia dibagikan sekali lewat QR saat pendaftaran, lalu aplikasi
authenticator yang menghitung kode 6 digit setiap 30 detik.

Kompatibilitas
--------------
Parameter yang dipakai: HMAC-SHA1, 6 digit, periode 30 detik — persis standar
yang didukung Google Authenticator, **Microsoft Authenticator** (menu
"Other account"/"Akun lain"), Authy, 1Password, Bitwarden, FreeOTP, dsb.
Microsoft Authenticator TIDAK mendukung SHA256/8 digit untuk akun non-Microsoft,
karena itu kita sengaja memakai SHA1/6 digit.

Keamanan penyimpanan rahasia
----------------------------
Rahasia TOTP disimpan terenkripsi di kolom `users.mfa_secret` (bukan plaintext),
memakai konstruksi encrypt-then-MAC dengan stdlib saja (tanpa dependency baru):

    ciphertext = plaintext XOR HMAC-SHA256(key, nonce || counter)
    tag        = HMAC-SHA256(key, "enc1" || nonce || ciphertext)
    blob       = base64url(nonce(16) || ciphertext || tag(32))

Kunci diturunkan dari env `MFA_ENC_KEY` (disarankan) atau `SECRET_KEY`.
Bila kunci berubah, semua rahasia lama tidak bisa didekripsi — user cukup
mendaftar ulang (admin dapat mereset MFA user dari Pengaturan).

Anti-replay
-----------
`users.mfa_last_step` menyimpan step waktu terakhir yang berhasil dipakai.
Kode yang sama (atau kode lebih lama) ditolak, meski masih di dalam window ±1.

Kebijakan (tabel `system_config`)
---------------------------------
    mfa_policy         : off | optional | required_roles
    mfa_required_roles : CSV role yang wajib MFA
    mfa_grace_days     : masa tenggang (hari) sejak mfa_enforced_at
    mfa_enforced_at    : waktu kebijakan required_roles mulai berlaku

    off            → MFA tidak diminta siapa pun (kill switch global).
    optional       → user yang sudah mendaftar wajib verifikasi; user lain
                     boleh mendaftar sendiri dari Profil Saya.
    required_roles → role terdaftar wajib MFA. Yang belum mendaftar wajib
                     mendaftar saat login setelah masa tenggang habis.
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Parameter TOTP (jangan diubah tanpa migrasi — mengubahnya membatalkan semua
# pendaftaran yang sudah ada).
# ---------------------------------------------------------------------------
PERIOD = 30
DIGITS = 6
WINDOW = 1          # toleransi ±1 step (30 detik ke belakang/ke depan)
ISSUER = 'BPF WorkHub'
RECOVERY_COUNT = 10

# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------
# Role lapangan yang sengaja TIDAK diwajibkan MFA (keputusan pemilik sistem:
# "untuk semua role kecuali marketing, ob dan driver"). chief_driver tetap
# diwajibkan karena merupakan role pengawas/back-office.
EXCLUDED_ROLES = ('marketing', 'ob', 'driver')

KNOWN_ROLES = (
    'admin', 'ga', 'finance', 'marketing', 'chief_driver', 'driver', 'ob',
    'security', 'receptionist', 'traineer', 'ga_hr',
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn',
    'it_bjm', 'it_plm', 'it_lpg',
)

DEFAULT_REQUIRED_ROLES = tuple(r for r in KNOWN_ROLES if r not in EXCLUDED_ROLES)
DEFAULT_REQUIRED_ROLES_CSV = ','.join(DEFAULT_REQUIRED_ROLES)

POLICY_OFF = 'off'
POLICY_OPTIONAL = 'optional'
POLICY_REQUIRED = 'required_roles'
POLICIES = (POLICY_OFF, POLICY_OPTIONAL, POLICY_REQUIRED)
POLICY_LABELS = {
    POLICY_OFF: 'Nonaktif',
    POLICY_OPTIONAL: 'Opsional',
    POLICY_REQUIRED: 'Wajib untuk role terpilih',
}

_POLICY_DEFAULTS = {
    'mfa_policy': POLICY_REQUIRED,
    'mfa_required_roles': DEFAULT_REQUIRED_ROLES_CSV,
    'mfa_grace_days': '7',
    'mfa_enforced_at': '',
}


# ---------------------------------------------------------------------------
# Enkripsi rahasia (stdlib: HMAC-SHA256 CTR keystream + HMAC tag)
# ---------------------------------------------------------------------------
def _enc_key():
    raw = (os.environ.get('MFA_ENC_KEY') or '').strip()
    if not raw:
        raw = (os.environ.get('SECRET_KEY') or '').strip()
    if not raw:
        raw = 'bpf-workhub-mfa-fallback'
    return hashlib.sha256(b'bpf-mfa-v1|' + raw.encode('utf-8')).digest()


def _keystream(key, nonce, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + struct.pack('>I', counter),
                            hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plain):
    """Enkripsi rahasia TOTP. Mengembalikan '' bila input kosong."""
    plain = str(plain or '')
    if not plain:
        return ''
    key = _enc_key()
    nonce = secrets.token_bytes(16)
    data = plain.encode('utf-8')
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    tag = hmac.new(key, b'enc1' + nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + cipher + tag).decode('ascii')


def decrypt_secret(blob):
    """Dekripsi rahasia TOTP. Mengembalikan '' bila blob rusak/tag salah."""
    blob = str(blob or '').strip()
    if not blob:
        return ''
    try:
        raw = base64.urlsafe_b64decode(blob.encode('ascii'))
    except Exception:
        return ''
    if len(raw) < 16 + 32:
        return ''
    nonce, cipher, tag = raw[:16], raw[16:-32], raw[-32:]
    key = _enc_key()
    expect = hmac.new(key, b'enc1' + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        return ''
    data = bytes(a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher))))
    try:
        return data.decode('utf-8')
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# TOTP inti
# ---------------------------------------------------------------------------
def generate_secret(nbytes=20):
    """Rahasia acak 160-bit dalam base32 tanpa padding (untuk QR/manual entry)."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode('ascii').rstrip('=')


def _b32decode(secret):
    s = str(secret or '').strip().replace(' ', '').replace('-', '').upper()
    s += '=' * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s, casefold=True)


def _hotp(secret, counter):
    key = _b32decode(secret)
    digest = hmac.new(key, struct.pack('>Q', int(counter)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def current_step(at=None):
    ts = time.time() if at is None else at
    return int(ts) // PERIOD


def totp_now(secret, at=None):
    """Kode TOTP untuk waktu tertentu (default sekarang) — untuk tes/verifikasi."""
    return _hotp(secret, current_step(at))


def match_step(secret, code, window=WINDOW, last_step=None, at=None):
    """Cocokkan kode TOTP. Kembalikan step yang cocok, atau None.

    `last_step` (opsional) menolak pemakaian ulang kode yang sudah dipakai.
    """
    candidate = str(code or '').strip().replace(' ', '').replace('-', '')
    if len(candidate) != DIGITS or not candidate.isdigit():
        return None
    if not secret:
        return None
    now = current_step(at)
    try:
        floor = int(last_step) if last_step not in (None, '', 0) else None
    except Exception:
        floor = None
    for delta in range(-window, window + 1):
        step = now + delta
        if floor is not None and step <= floor:
            continue
        try:
            if hmac.compare_digest(_hotp(secret, step), candidate):
                return step
        except Exception:
            return None
    return None


def otpauth_uri(secret, account, issuer=ISSUER):
    """URI `otpauth://` untuk QR (dipahami semua aplikasi authenticator)."""
    label = quote(f'{issuer}:{account}', safe='')
    return (f'otpauth://totp/{label}'
            f'?secret={secret}&issuer={quote(issuer, safe="")}'
            f'&algorithm=SHA1&digits={DIGITS}&period={PERIOD}')


def qr_svg_data_uri(uri):
    """QR dalam bentuk data-URI SVG (segno). '' bila segno tidak tersedia."""
    try:
        import io
        import segno
        qr = segno.make(uri, error='m')
        buf = io.BytesIO()
        qr.save(buf, kind='svg', scale=6, border=2,
                dark='#111827', light='#ffffff')
        return ('data:image/svg+xml;base64,'
                + base64.b64encode(buf.getvalue()).decode('ascii'))
    except Exception as exc:  # pragma: no cover — segno terpasang di image
        print(f'[mfa] qr gagal: {exc}')
        return ''


# ---------------------------------------------------------------------------
# Kode pemulihan (recovery codes)
# ---------------------------------------------------------------------------
def generate_recovery_code():
    raw = secrets.token_hex(5).upper()
    return f'{raw[:5]}-{raw[5:]}'


def normalize_recovery(code):
    return str(code or '').strip().upper().replace('-', '').replace(' ', '')


def hash_recovery(code):
    return hashlib.sha256(
        b'bpf-mfa-recovery-v1|' + normalize_recovery(code).encode('utf-8')
    ).hexdigest()


def generate_recovery_codes(n=RECOVERY_COUNT):
    codes, seen = [], set()
    while len(codes) < n:
        code = generate_recovery_code()
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


# ---------------------------------------------------------------------------
# Kebijakan
# ---------------------------------------------------------------------------
def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def parse_roles(value):
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = str(value or '').split(',')
    out = []
    for role in items:
        role = str(role or '').strip().lower()
        if role and role not in out:
            out.append(role)
    return out


def policy_from_db(conn=None):
    """Baca kebijakan MFA dari `system_config`.

    `ok=False` menandakan pembacaan GAGAL (DB tidak tersedia/error). Pemanggil
    memakai flag ini untuk **fail-open**: jangan memaksa pendaftaran MFA saat
    kebijakan tidak bisa dibaca (mis. pool DB habis) — login harus tetap jalan.
    User yang SUDAH mendaftar tetap diminta verifikasi (fail-closed untuk akun
    ber-MFA), karena verifikasi tidak butuh pembacaan kebijakan yang sukses.
    """
    own = conn is None
    if own:
        try:
            from modules.config import get_master_connection
            conn = get_master_connection()
        except Exception as exc:
            print(f'[mfa] koneksi kebijakan gagal: {exc}')
            conn = None
    values = dict(_POLICY_DEFAULTS)
    read_ok = False
    if conn:
        cur = None
        try:
            cur = conn.cursor(dictionary=True)
            keys = tuple(_POLICY_DEFAULTS.keys())
            placeholders = ','.join(['%s'] * len(keys))
            cur.execute(
                f"SELECT config_key, config_value FROM system_config "
                f"WHERE config_key IN ({placeholders})", keys)
            for row in cur.fetchall() or []:
                key = row.get('config_key')
                if key in values and row.get('config_value') is not None:
                    values[key] = row.get('config_value')
            read_ok = True
        except Exception as exc:
            print(f'[mfa] baca kebijakan gagal: {exc}')
        finally:
            try:
                if cur:
                    cur.close()
            except Exception:
                pass
    if own and conn:
        try:
            conn.close()
        except Exception:
            pass

    policy = str(values.get('mfa_policy') or POLICY_REQUIRED).strip().lower()
    if policy not in POLICIES:
        policy = POLICY_REQUIRED
    try:
        grace = max(0, int(str(values.get('mfa_grace_days') or '0').strip()))
    except Exception:
        grace = 7
    return {
        'policy': policy,
        'required_roles': parse_roles(values.get('mfa_required_roles')),
        'grace_days': grace,
        'enforced_at': _parse_dt(values.get('mfa_enforced_at')),
        'ok': read_ok,
    }


def grace_days_left(policy):
    """Sisa masa tenggang (hari, float). 0 = tidak ada tenggang/berakhir."""
    if not policy or policy.get('policy') != POLICY_REQUIRED:
        return 0.0
    days = int(policy.get('grace_days') or 0)
    if days <= 0:
        return 0.0
    start = policy.get('enforced_at')
    if not start:
        return 0.0
    end = start + timedelta(days=days)
    left = (end - datetime.now()).total_seconds() / 86400.0
    return max(0.0, left)


def requirement_for_user(user, policy=None):
    """Tentukan apakah user ini harus melewati MFA saat login.

    Mengembalikan dict:
        required        : bool  → wajib verifikasi/daftar sekarang
        mode            : 'verify' | 'enroll' | None
        policy          : kebijakan aktif
        enrolled        : user sudah punya rahasia TOTP
        role_required   : role user termasuk daftar wajib
        optional        : user boleh mendaftar sendiri (kebijakan optional)
        nudge           : user wajib MFA tapi masih dalam masa tenggang
        grace_days_left : sisa hari tenggang
    """
    pol = policy if policy is not None else policy_from_db()
    active = str(pol.get('policy') or POLICY_OFF)
    role = str((user or {}).get('role') or '').strip().lower()
    required_roles = pol.get('required_roles') or []
    enrolled = bool((user or {}).get('mfa_enabled')) and bool((user or {}).get('mfa_secret'))

    result = {
        'required': False,
        'mode': None,
        'policy': active,
        'enrolled': enrolled,
        'role_required': role in required_roles,
        'optional': False,
        'nudge': False,
        'grace_days_left': 0.0,
    }

    # Kill switch global: walau user pernah mendaftar, MFA tidak diminta.
    if active == POLICY_OFF:
        return result

    # Kebijakan gagal dibaca (DB down/pool habis): jangan memaksa pendaftaran
    # (fail-open — login harus tetap bisa), tetapi akun yang sudah ber-MFA tetap
    # wajib verifikasi (fail-closed — mereka punya aplikasi, tidak terhambat).
    if pol.get('ok') is False:
        if enrolled:
            result.update(required=True, mode='verify')
        return result

    if enrolled:
        result.update(required=True, mode='verify')
        return result

    if active == POLICY_OPTIONAL:
        result['optional'] = True
        return result

    if role in required_roles:
        left = grace_days_left(pol)
        if left > 0:
            result.update(nudge=True, grace_days_left=round(left, 1))
            return result
        result.update(required=True, mode='enroll')
    return result
