"""Pensiunan form pendaftaran publik lama /api/applicants (Rilis C — C10)."""
import pytest
from flask import Flask

import modules.routes_applicants as ap


class _FakeBranch:
    def __init__(self):
        self.applicants = []

    def cursor(self, dictionary=False):
        raise AssertionError('DB tidak boleh disentuh untuk submit publik lama')

    def commit(self):
        raise AssertionError('DB tidak boleh ditulis untuk submit publik lama')

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    branch = _FakeBranch()
    monkeypatch.setattr(ap, 'get_db_connection', lambda: branch)
    monkeypatch.setattr(ap, 'log_activity_async', lambda *a, **k: None)
    app = Flask(__name__)
    app.secret_key = 'apply-retired'
    ap.register_applicant_routes(app)
    return app.test_client(), branch


def test_apply_publik_dimatikan_tanpa_menulis_db(client):
    api, branch = client
    before = len(branch.applicants)
    res = api.post('/api/applicants', json={'nama_lengkap': 'Budi', 'no_hp': '0812'})
    assert res.status_code == 410
    assert 'portal rekrutmen' in res.get_json()['msg']
    assert len(branch.applicants) == before


def test_endpoint_baca_staff_tetap_ada(client):
    api, _branch = client
    assert api.get('/api/applicants').status_code in (200, 401, 403)
