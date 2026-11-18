"""Kontrol GA/Verifikasi — temuan peta 18 Nov 2026 (v2.121.0).

Mengunci empat perbaikan yang tidak tercakup tes lama:

1. `/api/queue/verify` tidak boleh melewati ACC atasan.
2. Identitas pelaku `handover`/`approve-lpj` dari sesi, bukan body.
3. LPJ ber-flag anomali tidak boleh lolos ke Finance tanpa di-clear GA.
4. Sesi tanpa nama tidak boleh menulis nama audit generik (401).
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask, jsonify

import modules.routes_cash as rc
import modules.routes_spa as rs
from modules.routes_cash import register_cash_routes
from modules.routes_spa import register_spa_routes


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        q = ' '.join(str(sql).split())
        up = q.upper()
        self.conn.queries.append((q, params))
        if up.startswith('SELECT * FROM FUEL_CASH_REQUESTS'):
            self._row = self.conn.cash
            self.rowcount = 0 if self.conn.cash is None else 1
        elif up.startswith('SELECT STATUS, ML_ANOMALY_FLAG, ANOMALY_CLEARED_BY'):
            self._row = self.conn.tx
            self.rowcount = 0 if self.conn.tx is None else 1
        elif up.startswith('UPDATE TRANSACTIONS'):
            if self.conn.tx and self.conn.tx.get('status') == 'pending':
                self.conn.tx['status'] = 'verified_ga'
                self.conn.tx['ga_approved_by'] = (params or ())[0]
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif up.startswith('UPDATE FUEL_CASH_REQUESTS'):
            if self.conn.cash:
                if "STATUS = 'COMPLETED'" in up:
                    self.conn.cash['status'] = 'COMPLETED'
                elif "STATUS = 'FUNDS_WITH_DRIVER'" in up:
                    self.conn.cash['status'] = 'FUNDS_WITH_DRIVER'
            self.rowcount = 1
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, cash=None, tx=None):
        self.cash = cash
        self.tx = tx
        self.queries = []
        self.committed = False
        self.rolled_back = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _app():
    a = Flask(__name__)
    a.secret_key = 'test-secret'
    register_spa_routes(a)
    register_cash_routes(a)
    return a


def _login(client, role='ga', name='GA Satu', grant=True):
    with client.session_transaction() as s:
        s.clear()
        s['user_role'] = role
        s['user_name'] = name
        s['full_name'] = name
        if grant:
            s['stepup_until'] = time.time() + 600


def _cash(**over):
    row = {
        'id': 1, 'display_id': 'CASH-SBY-1', 'driver_name': 'RIVAN',
        'status': 'LPJ_SUBMITTED', 'lpj_transaction_id': 77, 'notes': '',
    }
    row.update(over)
    return row


@pytest.fixture(autouse=True)
def _silence_side_effects(monkeypatch):
    monkeypatch.setattr(rc, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rc, 'push_driver_notification', lambda *a, **k: None, raising=False)


def test_queue_verify_menghormati_acc_atasan(monkeypatch):
    """Temuan #1: verifikasi penuh tidak boleh jadi jalan pintas ACC."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga')

    conn = FakeConn()
    monkeypatch.setattr(rs, 'get_db_connection', lambda: conn)

    def _gate(_conn, _doc, _ref):
        return False, (jsonify({'status': 'error',
                                'code': 'SUPERVISOR_APPROVAL_REQUIRED',
                                'msg': 'Menunggu ACC atasan'}), 409)

    monkeypatch.setattr(rs, 'gate_approval', _gate)

    r = c.post('/api/queue/verify/9', json={'confirm_anomaly': '1'})
    assert r.status_code == 409
    assert r.get_json()['code'] == 'SUPERVISOR_APPROVAL_REQUIRED'
    # Tidak ada UPDATE apa pun — gate berhenti sebelum menyentuh data.
    assert not any(q.upper().startswith('UPDATE') for q, _ in conn.queries)


def test_sesi_tanpa_nama_ditolak_bukan_nama_generik():
    """Temuan #6: jangan menulis 'Admin'/'GA Officer' bila sesi tak punya nama."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='')

    r = c.post('/api/queue/reject/1', json={'reason': 'uji'})
    assert r.status_code == 401
    assert 'login ulang' in r.get_json()['msg'].lower()


def test_handover_memakai_identitas_sesi_bukan_body(monkeypatch):
    """Temuan #2: `ga_name` dari klien tidak boleh dipercaya."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='GA Sesi')

    conn = FakeConn(cash=_cash(status='FINANCE_APPROVED'))
    monkeypatch.setattr(rc, 'get_db_connection', lambda: conn)

    r = c.post('/api/cash/handover/1', json={'ga_name': 'NAMA PALSU'})
    assert r.status_code == 200
    params = [p for q, p in conn.queries if q.upper().startswith('UPDATE FUEL_CASH_REQUESTS')]
    assert params and params[0][0] == 'GA Sesi'
    assert 'NAMA PALSU' not in str(conn.queries)


def test_handover_tanpa_nama_401(monkeypatch):
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='')

    def _boom():
        raise AssertionError('DB tidak boleh dibuka sebelum identitas valid')

    monkeypatch.setattr(rc, 'get_db_connection', _boom)
    r = c.post('/api/cash/handover/1', json={'ga_name': 'X'})
    assert r.status_code == 401


def test_lpj_normal_menyimpan_jejak_ga(monkeypatch):
    """Temuan #4: approve LPJ mencatat aktor + waktu, bukan update buta."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='GA Sesi')

    conn = FakeConn(cash=_cash(), tx={'status': 'pending', 'ml_anomaly_flag': 0,
                                      'anomaly_cleared_by': None})
    monkeypatch.setattr(rc, 'get_db_connection', lambda: conn)

    r = c.post('/api/cash/approve-lpj/1', json={'notes': 'lengkap'})
    assert r.status_code == 200
    assert conn.tx['status'] == 'verified_ga'
    assert conn.tx['ga_approved_by'] == 'GA Sesi'
    assert conn.cash['status'] == 'COMPLETED'
    assert conn.committed
    upd = [q for q, _ in conn.queries if q.upper().startswith('UPDATE TRANSACTIONS')]
    assert upd and 'ga_approved_by' in upd[0] and 'approved_by_user' in upd[0]


def test_lpj_anomali_harus_di_clear_dulu(monkeypatch):
    """Temuan #4: LPJ ber-flag anomali tidak boleh lolos diam-diam."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='GA Sesi')

    conn = FakeConn(cash=_cash(), tx={'status': 'pending', 'ml_anomaly_flag': 1,
                                      'anomaly_cleared_by': None})
    monkeypatch.setattr(rc, 'get_db_connection', lambda: conn)

    r = c.post('/api/cash/approve-lpj/1', json={})
    assert r.status_code == 409
    assert r.get_json()['code'] == 'ANOMALY_NEEDS_CLEAR'
    assert conn.cash['status'] == 'LPJ_SUBMITTED'
    assert not any(q.upper().startswith('UPDATE') for q, _ in conn.queries)


def test_lpj_anomali_sudah_di_clear_boleh_lanjut(monkeypatch):
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='GA Sesi')

    conn = FakeConn(cash=_cash(), tx={'status': 'pending', 'ml_anomaly_flag': 1,
                                      'anomaly_cleared_by': 'GA Penyaksi'})
    monkeypatch.setattr(rc, 'get_db_connection', lambda: conn)

    r = c.post('/api/cash/approve-lpj/1', json={})
    assert r.status_code == 200
    assert conn.cash['status'] == 'COMPLETED'


def test_lpj_sudah_diproses_tidak_dibalas_sukses(monkeypatch):
    """Temuan #4: UPDATE yang tidak mengenai baris tidak boleh dianggap sukses."""
    a = _app()
    c = a.test_client()
    _login(c, 'ga', name='GA Sesi')

    conn = FakeConn(cash=_cash(), tx={'status': 'verified_ga', 'ml_anomaly_flag': 0,
                                      'anomaly_cleared_by': 'GA'})
    monkeypatch.setattr(rc, 'get_db_connection', lambda: conn)

    r = c.post('/api/cash/approve-lpj/1', json={})
    assert r.status_code == 409
    assert conn.cash['status'] == 'LPJ_SUBMITTED'
