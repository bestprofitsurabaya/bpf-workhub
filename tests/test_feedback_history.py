"""Unit Tests — Riwayat feedback km/L driver (Task 5)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

from modules.routes_api_transactions import register_transaction_api


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.sql = ''

    def execute(self, sql, params=None):
        self.sql = str(sql).lower()
        self.state['calls'].append((self.sql, tuple(params or ())))

    def fetchall(self):
        rows = self.state['rows']
        if 'limit 5' in self.sql:
            return [dict(r) for r in rows[:5]]
        return [dict(r) for r in rows]

    def fetchone(self):
        return None

    def close(self):
        pass


class FakeConn:
    def __init__(self, state):
        self.state = state

    def cursor(self, dictionary=False):
        return FakeCursor(self.state)

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    state = {'rows': [], 'calls': []}
    monkeypatch.setattr(
        'modules.routes_api_transactions.get_db_connection',
        lambda: FakeConn(state))
    app = Flask(__name__)
    app.secret_key = 'test'
    register_transaction_api(app)
    app.config['TESTING'] = True
    return app.test_client(), state


def login(c, role='driver'):
    with c.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'DRIVERSBY_RIVAN'
        s['branch_code'] = 'SBY'


def test_feedback_history_kosong_tanpa_nopol(client):
    c, _ = client
    login(c, 'driver')
    rv = c.get('/api/driver/feedback-history')
    assert rv.status_code == 200
    assert rv.get_json()['data'] == []


def test_feedback_history_nopol_kosong_tidak_query_db(client):
    c, state = client
    login(c)
    rv = c.get('/api/driver/feedback-history?nopol=%20%20')
    assert rv.status_code == 200
    assert rv.get_json() == {'data': []}
    assert state['calls'] == []


def test_feedback_history_lima_terbaru_terurut_dan_berlabel(client):
    c, state = client
    login(c)
    state['rows'] = [
        {'date': '2026-11-23', 'km_per_liter': '12.50'},  # HEMAT
        {'date': '2026-11-20', 'km_per_liter': '9.50'},   # CUKUP
        {'date': '2026-11-18', 'km_per_liter': '7.20'},   # BOROS
        {'date': '2026-11-15', 'km_per_liter': '8.00'},   # CUKUP (batas)
        {'date': '2026-11-12', 'km_per_liter': '10.00'},  # HEMAT (batas)
        {'date': '2026-11-10', 'km_per_liter': '11.00'},  # terpotong LIMIT 5
    ]
    rv = c.get('/api/driver/feedback-history?nopol=L1413CBI')
    assert rv.status_code == 200
    data = rv.get_json()['data']
    assert len(data) == 5
    assert [r['date'] for r in data] == [
        '2026-11-23', '2026-11-20', '2026-11-18', '2026-11-15', '2026-11-12']
    assert [r['km_per_liter'] for r in data] == [12.5, 9.5, 7.2, 8.0, 10.0]
    assert all(isinstance(r['km_per_liter'], float) for r in data)
    assert [r['performa'] for r in data] == [
        'HEMAT', 'CUKUP', 'BOROS', 'CUKUP', 'HEMAT']
    assert all(set(r) == {'date', 'km_per_liter', 'performa'} for r in data)


def test_feedback_history_normalisasi_nopol_dan_scope(client):
    c, state = client
    login(c)
    rv = c.get('/api/driver/feedback-history?nopol=l%201413.cbi')
    assert rv.status_code == 200
    sql, params = state['calls'][0]
    assert "replace(replace(upper(nopol), ' ', ''), '.', '')" in sql
    assert params[0] == 'L1413CBI'
    assert 'km_per_liter > 0' in sql
    assert 'status in (%s,%s)' in sql
    assert 'verified_ga' in params and 'archived' in params
    assert 'is_dummy=0 or is_dummy is null' in sql
    assert 'order by created_at desc' in sql
    assert 'limit 5' in sql
