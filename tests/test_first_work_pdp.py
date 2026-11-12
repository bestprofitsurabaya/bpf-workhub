"""Persetujuan & rate limit FirstWork (v2.85.0 — UU PDP).

Yang diuji (murni fungsi — tanpa DB):
1. Persetujuan afirmatif: hanya nilai yang jelas menyetujui yang lolos;
   kosong/nilain aneh = ditolak (diam bukan berarti setuju).
2. `POST /api/first-work/public` tanpa consent ditolak 400 SEBELUM DB/sentuh.
3. Counter kuota request: fallback memori (tanpa Redis) tetap menegakkan
   limit dan kadaluarsa window — tidak ada blokir selamanya.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

from modules import helpers as hp
from modules import routes_first_work as fw

APP = Flask(__name__)
fw.register_first_work_routes(APP)

_VALID_BODY = {
    'nik': '3578010101900001',
    'nama': 'Contoh Pendaftar',
    'pendidikan': 'SMA',
    'no_hp': '081234567890',
    'referensi_text': 'Uji',
    'branch': 'SBY',
}


class TestConsentExplicit:
    def test_affirmative_values_accepted(self):
        for value in ('1', 'true', 'yes', 'ya'):
            assert fw._consent_given(value)

    def test_silence_is_not_consent(self):
        for value in ('', None, '0', 'false', 'no', 'tidak', 'setuju'):
            assert not fw._consent_given(value)

    def test_public_submit_without_consent_rejected_before_db(self):
        hp._get_redis = lambda: None
        hp._counter_mem.clear()
        with APP.test_client() as client:
            response = client.post('/api/first-work/public', data=_VALID_BODY)
        assert response.status_code == 400
        assert 'persetujuan' in response.get_json()['msg'].lower()

    def test_consent_only_does_not_pass_other_checks(self):
        """Consent centang saja tidak melewati validasi field wajib."""
        hp._get_redis = lambda: None
        hp._counter_mem.clear()
        with APP.test_client() as client:
            response = client.post('/api/first-work/public',
                                   data={**_VALID_BODY, 'consent': '1',
                                         'nama': 'A'})
        assert response.status_code == 400
        assert 'nama' in response.get_json()['msg'].lower()


class TestRedisRateHitFallback:
    def setup_method(self):
        hp._get_redis = lambda: None
        hp._counter_mem.clear()

    def test_enforces_limit(self):
        assert hp.redis_rate_hit('uji', 2, 600, prefix='t')
        assert hp.redis_rate_hit('uji', 2, 600, prefix='t')
        assert not hp.redis_rate_hit('uji', 2, 600, prefix='t')

    def test_window_expiry_unblocks(self):
        hp._counter_mem['uji'] = [time.time() - 700, time.time() - 700]
        assert hp.redis_rate_hit('uji', 2, 600, prefix='t')

    def test_keys_are_independent(self):
        assert hp.redis_rate_hit('a', 1, 600, prefix='t')
        assert hp.redis_rate_hit('b', 1, 600, prefix='t')
        assert not hp.redis_rate_hit('a', 1, 600, prefix='t')
