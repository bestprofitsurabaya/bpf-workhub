"""Keamanan PIN (v2.74.0) — hash PBKDF2, bukan plaintext (ISO/IEC 27001 A.9.4.3).

Dulu PIN 6-digit disimpan PLAINTEXT di kolom `users.pin` (TODO lama dari
routes_api_master): siapa pun yang bisa membaca DB master (dump, backup bocor,
log slow-query, akses baca langsung) langsung memegang PIN login semua orang.

Sekarang:
- Penulisan PIN baru (reset-pin, bulk-create, reset PIN massal driver,
  users/sync) → hash PBKDF2-SHA256 via werkzeug.security (sama mesin dengan
  hash password Flask).
- Verifikasi mendukung DUA format: hash baru dan plaintext legacy — login/
  step-up yang sukses dengan PIN plaintext lama otomatis lazy-upgrade ke hash,
  sehingga deploy tanpa reset massal dan tanpa mematahkan akun yang sudah ada.
"""
import hmac

from werkzeug.security import generate_password_hash, check_password_hash

# Scheme hash yang dikenali werkzeug (prefix yang selalu ada di stored value).
_HASH_PREFIXES = ('pbkdf2:', 'scrypt:', 'argon2')


def is_pin_hash(stored):
    """True bila nilai tersimpan berupa hash (bukan plaintext legacy)."""
    return bool(stored) and str(stored).startswith(_HASH_PREFIXES)


def hash_pin(pin):
    """PIN teks → hash PBKDF2. PIN kosong → None (biarkan kolom apa adanya)."""
    pin = str(pin or '').strip()
    if not pin:
        return None
    return generate_password_hash(pin)


def stored_pin(value):
    """Normalisasi nilai yang akan DITULIS ke users.pin (v2.74.0).

    - None → None (pemanggil memutuskan fallback-nya sendiri).
    - Sudah hash → diteruskan apa adanya.
    - Plaintext (PIN baru ATAU pin legacy lama yang ikut ditulis ulang) → hash.
    """
    value = str(value or '').strip()
    if not value:
        return None
    if is_pin_hash(value):
        return value
    return hash_pin(value)


def verify_pin(stored, provided):
    """True bila `provided` cocok dengan `stored` (hash baru atau plaintext legacy)."""
    stored = str(stored or '')
    provided = str(provided or '')
    if not stored or not provided:
        return False
    if is_pin_hash(stored):
        try:
            return check_password_hash(stored, provided)
        except Exception:
            return False
    # Legacy plaintext — pembanding konstan-waktu (anti timing attack).
    return hmac.compare_digest(stored, provided)
