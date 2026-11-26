"""Token sesi portal dan token kartu (Rilis C — Task C4).

Token ditandatangani, berumur pendek, purpose-bound, dan hanya berisi NIK +
cabang + purpose. Tidak ada nama, HP, DOB, atau data pribadi lain di payload.
"""
import pytest
from flask import Flask

NIK = '3573010101900001'


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = 'portal-token-test'
    return app


def test_token_bolak_balik_dan_purpose_terkunci(app):
    from modules.portal_token import issue_session_token, verify_session_token
    with app.test_request_context('/'):
        token = issue_session_token(NIK, 'SBY')
        assert verify_session_token(token) == {
            'nik': NIK, 'branch': 'SBY', 'purpose': 'portal'}
        assert verify_session_token(token, purpose='card') is None


def test_token_kedaluwarsa_ditolak(app, monkeypatch):
    import modules.portal_token as pt
    with app.test_request_context('/'):
        token = pt.issue_session_token(NIK, 'SBY', ttl_seconds=1)
        monkeypatch.setattr(pt, '_now', lambda: 10**12)
        assert pt.verify_session_token(token, max_age=1) is None


def test_token_rusak_dan_token_kosong_ditolak(app):
    from modules.portal_token import verify_session_token
    with app.test_request_context('/'):
        assert verify_session_token('bukan-token') is None
        assert verify_session_token('') is None
        assert verify_session_token(None) is None


def test_token_tidak_mengandung_data_pribadi_lain(app):
    from modules.portal_token import issue_session_token
    with app.test_request_context('/'):
        token = issue_session_token(NIK, 'SBY')
        assert 'Budi' not in token
        assert '0812' not in token
        assert '1990' not in token


def test_kartu_token_terkunci_ke_submission(app):
    from modules.portal_token import issue_card_token, verify_card_token
    with app.test_request_context('/'):
        token = issue_card_token(7, ttl_seconds=60)
        assert verify_card_token(token) == {'submission_id': 7,
                                            'purpose': 'card'}
        assert verify_card_token(token, purpose='portal') is None
