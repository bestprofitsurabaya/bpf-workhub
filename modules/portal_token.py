"""Token bertanda tangan untuk portal rekrutmen dan unduhan kartu (Rilis C).

Payload token sesi hanya `{nik, branch, purpose, iat, exp}` — tidak ada nama,
HP, atau tanggal lahir. Token kartu hanya `{submission_id, purpose, iat, exp}`.
Keduanya memakai `current_app.secret_key` dan kedaluwarsa.
"""
import time

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous import URLSafeTimedSerializer

_SESSION_SALT = 'recruitment-session'
_CARD_SALT = 'recruitment-card'
_SESSION_TTL = 1800
_CARD_TTL = 604800


def _now():
    """Detak waktu yang bisa diganti tes; tidak dipakai untuk logging."""
    return int(time.time())


def _serializer(salt):
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


def issue_session_token(nik, branch_code, purpose='portal',
                        ttl_seconds=_SESSION_TTL):
    """Terbitkan token sesi portal untuk NIK + cabang tertentu."""
    now = _now()
    payload = {
        'nik': str(nik or ''),
        'branch': str(branch_code or '').upper()[:10],
        'purpose': purpose,
        'iat': now,
        'exp': now + int(ttl_seconds),
    }
    return _serializer(_SESSION_SALT).dumps(payload)


def verify_session_token(token, purpose='portal', max_age=_SESSION_TTL):
    """Kembalikan payload bersih atau None bila rusak/kedaluwarsa/salah purpose."""
    if not token:
        return None
    try:
        data = _serializer(_SESSION_SALT).loads(token, max_age=int(max_age))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get('purpose') != purpose:
        return None
    if not data.get('nik') or not data.get('branch'):
        return None
    try:
        if int(data.get('exp') or 0) <= _now():
            return None
    except (TypeError, ValueError):
        return None
    return {'nik': data['nik'], 'branch': data['branch'],
            'purpose': data['purpose']}


def issue_card_token(submission_id, ttl_seconds=_CARD_TTL):
    """Terbitkan token unduh kartu untuk satu baris FirstWork."""
    now = _now()
    payload = {'submission_id': int(submission_id), 'purpose': 'card',
               'iat': now, 'exp': now + int(ttl_seconds)}
    return _serializer(_CARD_SALT).dumps(payload)


def verify_card_token(token, purpose='card', max_age=_CARD_TTL):
    """Kembalikan `{submission_id, purpose}` atau None untuk token tidak sah."""
    if not token:
        return None
    try:
        data = _serializer(_CARD_SALT).loads(token, max_age=int(max_age))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('purpose') != purpose:
        return None
    try:
        if int(data.get('exp') or 0) <= _now():
            return None
    except (TypeError, ValueError):
        return None
    return {'submission_id': data.get('submission_id'), 'purpose': purpose}
