"""Test — Integrasi Subsidi Tepat v2.68.0 ("satukan" agen).

Cakupan:
- POST /api/subsidy/auto-match : bulk advisory nopol+tanggal+volume,
  klaim yang sudah dijodohkan (subsidy_tx_id) dilewati, hasil match/close
  ditulis ke subsidy_match TANPA menaut subsidy_tx_id;
  auth: sesi finance/admin ATAU X-SUBSIDY-TOKEN (agen host/cron).
- POST /api/subsidy/import     : pulled_at tingkat payload dipakai bila
  baris tidak punya timestamp tarikan sendiri (MAX(pulled_at) bukan NULL).
- GET  /api/subsidy/status     : coverage klaim terbuka ikut tampil.

Jalankan: python3 -m pytest tests/test_subsidy_match.py -v
"""
import sys
import os
from collections import deque
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

import modules.routes_subsidy as rs
import modules.branch_manager as bm


# ------------------------------------------------------------------
# Fake DB — satu FakeConn per koneksi; tiap cursor punya "spec" berisi
# baris-hasil berurutan (fetchall/fetchone = pop urut dari spec).
# ------------------------------------------------------------------
class FakeCursor:
    def __init__(self, conn, spec):
        self.conn = conn
        self.spec = list(spec)
        self.executed = []
        self.rowcount = 0
        conn.cursors.append(self)

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.spec.pop(0) if self.spec else None

    def fetchall(self):
        return self.spec.pop(0) if self.spec else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor_specs=None):
        self.cursors = []
        self._specs = [list(s) for s in (cursor_specs or [])]
        self.commits = 0

    def cursor(self, dictionary=False):
        spec = self._specs.pop(0) if self._specs else []
        return FakeCursor(self, spec)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def env(monkeypatch):
    """(client, branch_specs, master_specs, branch_made, master_made)."""
    branch_specs, master_specs = deque(), deque()
    branch_made, master_made = [], []
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['TESTING'] = True

    def _branch():
        c = FakeConn(branch_specs.popleft() if branch_specs else [])
        branch_made.append(c)
        return c

    def _master():
        c = FakeConn(master_specs.popleft() if master_specs else [])
        master_made.append(c)
        return c

    monkeypatch.setattr(rs, 'get_db_connection', _branch)
    monkeypatch.setattr(rs, 'get_master_connection', _master)
    # startup-thread register tanpa menyentuh DB sungguhan
    monkeypatch.setattr(rs, 'ensure_subsidy_schema', lambda *a, **k: True)
    monkeypatch.setattr(rs, 'ensure_attestation_schema', lambda *a, **k: None)
    monkeypatch.setattr(bm, 'list_branches', lambda: [])
    monkeypatch.setattr(rs, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setenv('SUBSIDY_IMPORT_TOKEN', 'tok-test')

    rs.register_subsidy_routes(app)
    with app.test_client() as c:
        yield c, branch_specs, master_specs, branch_made, master_made


def _login(client, role='finance'):
    with client.session_transaction() as s:
        s['user_name'] = 'finance_sby'
        s['full_name'] = 'Cynthia Permatasari'
        s['user_role'] = role


CLAIM_ROW = {
    'id': 7, 'display_id': 'BPF-SBY-20261023-0001', 'nopol': 'B 2628 SRP',
    'liter': 13.04, 'nominal': 130400.0,
    'created_at': datetime(2026, 10, 23, 9, 0, 0),
    'subsidy_tx_id': None,
}
LINKED_CLAIM = {**CLAIM_ROW, 'id': 8, 'subsidy_tx_id': 55}
SPBU_MATCH = {'volume': 13.04, 'amount': 130400.0}


def _all_executed(conns):
    return [e for conn in conns for cur in conn.cursors for e in cur.executed]


# ------------------------------------------------------------------
# auto-match — inti advisory
# ------------------------------------------------------------------
def test_automatch_match_advisory_tanpa_menaut(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    _login(client)
    branch_specs.append([[[CLAIM_ROW]]])             # conn → cursor → fetchall rows
    master_specs.append([[[SPBU_MATCH]]])
    r = client.post('/api/subsidy/auto-match')
    assert r.status_code == 200
    d = r.get_json()
    assert d['status'] == 'success'
    assert d['checked'] == 1 and d['skipped_linked'] == 0
    assert d['match'] == 1 and d['close'] == 0 and d['no_record'] == 0
    updates = [e for e in _all_executed(branch_made)
               if 'UPDATE transactions SET subsidy_match' in e[0]]
    assert updates, 'klaim match harus di-update advisory'
    sql, params = updates[0]
    assert 'subsidy_tx_id' not in sql                # sifat ADVISORY: tidak menaut
    assert params[0] == 'match'


def test_automatch_klaim_tertaut_dilewati(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    _login(client)
    branch_specs.append([[[LINKED_CLAIM]]])
    master_specs.append([[[SPBU_MATCH]]])
    d = client.post('/api/subsidy/auto-match').get_json()
    assert d['skipped_linked'] == 1 and d['match'] == 0
    for e in _all_executed(branch_made):
        if 'UPDATE transactions SET subsidy_match' in e[0]:
            assert str(e[1][1]) != '8'               # klaim #8 tidak disentuh


def test_automatch_tanpa_kandidat_no_record(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    _login(client)
    branch_specs.append([[[CLAIM_ROW]]])
    master_specs.append([[[]]])                      # tidak ada row SPBU
    d = client.post('/api/subsidy/auto-match').get_json()
    assert d['no_record'] == 1 and d['match'] == 0


# ------------------------------------------------------------------
# auth auto-match — sesi finance/admin ATAU token agen (cron)
# ------------------------------------------------------------------
def test_automatch_token_agen_disetujui_tanpa_sesi(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    branch_specs.append([[[CLAIM_ROW]]])
    master_specs.append([[[SPBU_MATCH]]])
    r = client.post('/api/subsidy/auto-match', headers={'X-SUBSIDY-TOKEN': 'tok-test'})
    assert r.status_code == 200


def test_automatch_token_salah_401(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    r = client.post('/api/subsidy/auto-match', headers={'X-SUBSIDY-TOKEN': 'ngawur'})
    assert r.status_code == 401


def test_automatch_role_non_finance_403(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    _login(client, role='driver')
    r = client.post('/api/subsidy/auto-match')
    assert r.status_code == 403


# ------------------------------------------------------------------
# import — pulled_at tingkat payload (agen pull.mjs {pulledAt})
# ------------------------------------------------------------------
def _tx_row(**over):
    base = {
        'transactionId': 'P0001-SPBU-1', 'transactionDate': '2026-10-23 07:15:00',
        'vehicleLicenseNumber': 'B 2628 SRP', 'product': 'PERTALITE',
        'volumeTransaction': 13.04, 'totalAmount': 130400,
        'spbuId': '5460179', 'city': 'SURABAYA', 'witel': 'SBY',
        'verificationType': 'QR', 'businessType': '', 'customerType': '',
    }
    base.update(over)
    return base


def test_import_pulled_at_dari_payload(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    master_specs.append([])                          # INSERT tanpa hasil
    r = client.post('/api/subsidy/import',
                    headers={'X-SUBSIDY-TOKEN': 'tok-test'},
                    json={'rows': [_tx_row()], 'pulledAt': '2026-10-23 06:15:00'})
    assert r.status_code == 200, r.get_json()
    inserts = [e for e in _all_executed(master_made)
               if 'INSERT INTO subsidy_transactions' in e[0]]
    assert inserts, 'baris harus di-INSERT'
    params = inserts[0][1]
    pulled = params[-2]                              # (..., raw_json, pulled_at, actor)
    assert pulled == datetime(2026, 10, 23, 6, 15, 0)


def test_import_baris_punya_pulledat_sendiri(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    master_specs.append([])
    row = _tx_row(transactionId='P0002-SPBU-2', pulledAt='2026-10-23 05:00:00')
    r = client.post('/api/subsidy/import',
                    headers={'X-SUBSIDY-TOKEN': 'tok-test'},
                    json={'rows': [row], 'pulledAt': '2026-10-23 06:15:00'})
    assert r.status_code == 200
    inserts = [e for e in _all_executed(master_made)
               if 'INSERT INTO subsidy_transactions' in e[0]]
    assert inserts[0][1][-2] == datetime(2026, 10, 23, 5, 0, 0)


# ------------------------------------------------------------------
# status — coverage klaim terbuka
# ------------------------------------------------------------------
def test_status_sertakan_coverage(env):
    client, branch_specs, master_specs, branch_made, master_made = env
    _login(client)
    # master cursor 1: fetchone ringkasan
    master_specs.append([[{'c': 138, 'last_pull': datetime(2026, 10, 23, 6, 15),
                           'oldest': datetime(2026, 9, 22),
                           'newest': datetime(2026, 10, 22)}]])
    # branch cursor: fetchall GROUP BY (kosong) lalu fetchone COUNT (6,)
    branch_specs.append([[[], (6,)]])
    d = client.get('/api/subsidy/status').get_json()
    assert d['count'] == 138
    assert d['coverage']['terbuka'] == 6


# ------------------------------------------------------------------
# v2.69.0 — OTP login ulang agen langsung dari Finance (gate dir)
# ------------------------------------------------------------------
@pytest.fixture
def gate(env, tmp_path, monkeypatch):
    """gate dir palsu — env-var SUBSIDY_GATE_DIR diarahkan ke tmp_path."""
    monkeypatch.setenv('SUBSIDY_GATE_DIR', str(tmp_path))
    return tmp_path


def test_otp_request_menulis_gate_file(env, gate):
    client, *rest = env
    _login(client)
    d = client.post('/api/subsidy/otp/request').get_json()
    assert d['status'] == 'success' and d['state'] == 'starting'
    req = (gate / 'otp_request.json').read_text()
    assert 'finance_sby' in req


def test_otp_request_tolak_saat_proses_409(env, gate):
    client, *rest = env
    _login(client)
    (gate / 'agent_state.json').write_text('{"state": "verifying"}')
    r = client.post('/api/subsidy/otp/request')
    assert r.status_code == 409


def test_otp_status_baca_agent_state(env, gate):
    client, *rest = env
    _login(client)
    (gate / 'agent_state.json').write_text(
        '{"state": "waiting_otp", "msg": "OTP dikirim ke email akun"}')
    d = client.get('/api/subsidy/otp/status').get_json()
    assert d['state'] == 'waiting_otp'


def test_otp_submit_menulis_kode_ke_gate(env, gate):
    client, *rest = env
    _login(client)
    (gate / 'agent_state.json').write_text('{"state": "waiting_otp"}')
    d = client.post('/api/subsidy/otp/submit', json={'code': '123456'}).get_json()
    assert d['status'] == 'success' and d['state'] == 'verifying'
    body = (gate / 'otp_submit.json').read_text()
    assert '"123456"' in body


def test_otp_submit_blokir_kode_salah_format(env, gate):
    client, *rest = env
    _login(client)
    (gate / 'agent_state.json').write_text('{"state": "waiting_otp"}')
    r = client.post('/api/subsidy/otp/submit', json={'code': '12a45'})
    assert r.status_code == 400
    assert not (gate / 'otp_submit.json').exists()


def test_otp_submit_tolak_bila_belum_login_409(env, gate):
    client, *rest = env
    _login(client)
    r = client.post('/api/subsidy/otp/submit', json={'code': '123456'})
    assert r.status_code == 409


def test_otp_role_non_finance_403(env, gate):
    client, *rest = env
    _login(client, role='driver')
    r = client.post('/api/subsidy/otp/request')
    assert r.status_code == 403
