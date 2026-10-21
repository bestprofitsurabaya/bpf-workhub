"""Regresi v2.47.2 — kegagalan WordPress TIDAK boleh memakai HTTP 401.

Insiden: selesai scrape → lanjut halaman upload → tiba-tiba kembali ke
/login. Penyebabnya bukan sesi, tapi endpoint scraper mengembalikan **401**
ketika kredensial/login WordPress ditolak (`_upload_articles_to_site` dan
endpoint duplikat/hapus). SPA (`frontend/src/api.js`) memperlakukan SEMUA
respons 401 sebagai "sesi kedaluwarsa" lalu memicu `bpf:unauthorized` →
App.vue membuang sesi & redirect ke /login.

Kontrak: kegagalan upstream memakai `WP_FAIL_STATUS` (502 Bad Gateway);
401 hanya untuk sesi aplikasi yang benar-benar tidak ada.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402

import modules.news_scraper.routes as routes  # noqa: E402
from modules.news_scraper.routes import WP_FAIL_STATUS  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _FailingWPClient:
    """WP client yang selalu gagal login (kredensial ditolak)."""

    def login(self):
        return False, 'Kredensial ditolak WordPress (HTTP 401)'

    def request(self, *a, **k):
        raise AssertionError('tidak boleh memanggil API WP setelah login gagal')


class _StubLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


SITE = {'wp_url': 'https://contoh.invalid/wp-json/wp/v2/posts',
        'username': 'it_bpf_surabaya', 'app_password': 'xxxx-xxxx-xxxx-xxxx'}


@pytest.fixture()
def client(monkeypatch):
    from app import app
    app.config['TESTING'] = True
    app.config['SESSION_COOKIE_SECURE'] = False

    monkeypatch.setattr(routes, '_load_json',
                        lambda path, default: {'BPF Surabaya': dict(SITE)})
    monkeypatch.setattr(routes, '_make_wp_client', lambda site: _FailingWPClient())
    monkeypatch.setattr(routes, '_sl', _StubLogger())
    # jangan menulis file log scraper (di CI/host lokal bisa read-only)
    monkeypatch.setattr(routes, '_log_scraper', lambda *a, **k: None)

    with app.test_client() as c:
        with c.session_transaction() as s:
            s['user_role'] = 'it_sby'
            s['user_name'] = 'it_sby'
            s['full_name'] = 'IT Surabaya'
            s['branch_code'] = 'SBY'
            s['csrf_token'] = 'test-csrf-token'
        yield c


def _post(client, path, payload):
    return client.post(path, json=payload, headers={'X-CSRF-Token': 'test-csrf-token'})


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def test_status_kontrak():
    """502 = upstream gagal; 401 khusus sesi aplikasi."""
    assert WP_FAIL_STATUS == 502
    assert WP_FAIL_STATUS != 401


def test_upload_wp_login_gagal_bukan_401(client):
    r = _post(client, '/api/scraper/upload',
              {'site_name': 'BPF Surabaya',
               'articles': [{'title': 'Judul', 'content': '<p>isi</p>'}]})
    assert r.status_code == WP_FAIL_STATUS, \
        'login WP gagal harus 502, bukan 401 (401 = logout di SPA)'
    data = r.get_json()
    assert data['ok'] is False
    assert 'WordPress login gagal' in data['error']


def test_upload_multi_wp_login_gagal_bukan_401(client):
    r = _post(client, '/api/scraper/upload-multi',
              {'site_names': ['BPF Surabaya'],
               'articles': [{'title': 'Judul', 'content': '<p>isi</p>'}]})
    assert r.status_code != 401
    data = r.get_json()
    # v2.47.2: laporan multi-upload tidak boleh "ok" bila semua site gagal
    assert data['ok'] is False
    assert data['sites_ok'] == 0
    assert any('login gagal' in e.lower() for e in data['errors']), data['errors']


def test_check_duplicates_wp_login_gagal_bukan_401(client):
    r = _post(client, '/api/scraper/duplicates', {'site_name': 'BPF Surabaya'})
    assert r.status_code == WP_FAIL_STATUS, \
        'cek duplikat harus 502 saat login WP gagal'
    assert r.get_json()['ok'] is False


def test_duplicate_delete_wp_login_gagal_bukan_401(client):
    r = _post(client, '/api/scraper/duplicates/delete',
              {'site_name': 'BPF Surabaya', 'post_ids': [1, 2], 'keep_ids': []})
    assert r.status_code == WP_FAIL_STATUS
    assert r.get_json()['ok'] is False


def test_tidak_ada_route_scraper_yang_kembalikan_401_untuk_wp():
    """Pengawas: sumber route scraper tidak boleh lagi memakai 401 untuk WP."""
    src = open(routes.__file__, encoding='utf-8').read()
    assert "'status': 401" not in src
    # sisa `), 401` yang mengandung pesan 'Login gagal' = bug kambuh
    assert "Login gagal: {nonce_or_err}', 'deleted': 0}), 401" not in src
    assert "Login gagal: {nonce_or_err}', 'duplicates'" not in src or '), 401' not in src.split(
        "Login gagal: {nonce_or_err}', 'duplicates'")[1][:120]


def test_kredensial_pending_tetap_400_bukan_401(client, monkeypatch):
    """Site tanpa kredensial → 400 (input tidak lengkap), bukan 401."""
    monkeypatch.setattr(routes, '_load_json',
                        lambda path, default: {'BPF Baru': {'wp_url': 'x',
                                                            'username': 'PENDING',
                                                            'app_password': 'PENDING'}})
    r = _post(client, '/api/scraper/upload',
              {'site_name': 'BPF Baru', 'articles': [{'title': 'T'}]})
    assert r.status_code == 400


def test_site_tidak_dikenal_404(client):
    r = _post(client, '/api/scraper/upload',
              {'site_name': 'Tidak Ada', 'articles': [{'title': 'T'}]})
    assert r.status_code == 404
