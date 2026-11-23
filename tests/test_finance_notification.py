"""Notifikasi realtime Finance — Task 4 (Rilis A).

Klaim yang disetujui GA harus memicu satu event `new_finance_task` di room
`finance_board`, dan hanya saat status benar-benar bertransisi (rowcount > 0).
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

import modules.routes_spa as rs
from modules.realtime import _ROOM_ROLES
from modules.routes_spa import notify_finance_task, register_spa_routes


def test_approve_ga_emit_notifikasi_finance(monkeypatch):
    called = []
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: called.append((a, k)))
    # panggil helper emit yang dibuat di routes_spa
    notify_finance_task({'id': 5, 'display_id': 'BPF-1', 'nominal': 100000})
    assert called[0][0][0] == 'new_finance_task'
    assert called[0][1]['room'] == 'finance_board'


def test_notifikasi_satu_event_per_panggilan(monkeypatch):
    called = []
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: called.append(a))
    notify_finance_task({'id': 5})
    assert len(called) == 1


def test_payload_notifikasi_sesuai_kontrak(monkeypatch):
    called = []
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: called.append((a, k)))
    notify_finance_task({'id': 5, 'display_id': 'BPF-1', 'nominal': 100000})
    assert called[0][0][1] == {
        'id': 5, 'display_id': 'BPF-1', 'nominal': 100000,
    }
    # nominal opsional → None (bukan KeyError)
    notify_finance_task({'id': 6, 'display_id': 'BPF-2'})
    assert called[1][0][1] == {'id': 6, 'display_id': 'BPF-2', 'nominal': None}


def test_room_finance_board_hanya_finance_dan_admin():
    assert _ROOM_ROLES['finance_board'] == ('finance', 'admin')


# --- Hook di endpoint approve GA: hanya setelah transisi berhasil ---------

class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._row = None

    def execute(self, sql, params=None):
        q = ' '.join(str(sql).split()).upper()
        if q.startswith('SELECT ML_ANOMALY_FLAG FROM TRANSACTIONS'):
            self._row = {'ml_anomaly_flag': 0}
        elif q.startswith('UPDATE TRANSACTIONS'):
            self.rowcount = 1 if self.conn.transition_ok else 0
        elif q.startswith('SELECT ID, DISPLAY_ID, NOMINAL FROM TRANSACTIONS'):
            self._row = {'id': 5, 'display_id': 'BPF-1', 'nominal': 100000}
        elif q.startswith('SELECT DRIVER_NAME, DISPLAY_ID FROM TRANSACTIONS'):
            self._row = ('DRIVER SATU', 'BPF-1')
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def close(self):
        pass


class _FakeConn:
    def __init__(self, transition_ok=True):
        self.transition_ok = transition_ok

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        pass

    def close(self):
        pass


def _client():
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_spa_routes(app)
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = 'ga'
        s['user_name'] = 'GA Satu'
        s['full_name'] = 'GA Satu'
        s['stepup_until'] = time.time() + 600
    return c


def _patch_route(monkeypatch, emitted, transition_ok):
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: emitted.append((a, k)))
    monkeypatch.setattr('modules.notifications.push_driver_notification',
                        lambda *a, **k: None)
    monkeypatch.setattr(rs, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rs, 'gate_approval', lambda *a: (True, None))
    monkeypatch.setattr(rs, 'get_db_connection',
                        lambda: _FakeConn(transition_ok))


def test_approve_ga_mengirim_notifikasi_setelah_update_berhasil(monkeypatch):
    emitted = []
    _patch_route(monkeypatch, emitted, transition_ok=True)
    r = _client().post('/api/queue/approve-ga/5')
    assert r.status_code == 200
    assert len(emitted) == 1
    assert emitted[0][0][0] == 'new_finance_task'
    assert emitted[0][0][1] == {
        'id': 5, 'display_id': 'BPF-1', 'nominal': 100000,
    }
    assert emitted[0][1]['room'] == 'finance_board'


def test_approve_ga_gagal_tidak_mengirim_notifikasi(monkeypatch):
    emitted = []
    _patch_route(monkeypatch, emitted, transition_ok=False)
    r = _client().post('/api/queue/approve-ga/5')
    assert r.status_code == 409
    assert emitted == []
