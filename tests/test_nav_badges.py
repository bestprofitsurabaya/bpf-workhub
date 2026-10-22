"""Unit tests — GET /api/nav/badges (P1 UI/UX sidebar).

DB di-fake; fokus pada pemetaan role → angka yang dikembalikan dan
pemanggilan query yang tidak relevan (mis. admin tidak menghitung ACC).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._one = None
        self._rows = []

    def execute(self, sql, params=None):
        s = sql or ''
        self.conn.queries.append(s)
        self._one = None
        self._rows = []
        if 'approval_requests' in s:
            self._rows = self.conn.approvals
        elif 'vehicle_assignments' in s:
            self._one = {'c': self.conn.counts['assignments_pending']}
        elif 'water_purchases' in s:
            self._one = {'c': self.conn.counts['water_pending']}
        elif 'fuel_cash_requests' in s:
            key = 'cash_lpj' if 'LPJ_SUBMITTED' in s else 'cash_finance'
            self._one = {'c': self.conn.counts[key]}
        elif 'os_finance' in s:
            self._one = {'c': self.conn.counts['finance_pending']}
        elif 'transactions' in s:
            self._one = {'c': self.conn.counts['ga_pending']}
        else:
            self._one = {'c': 0}

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.counts = {
            'ga_pending': 3, 'finance_pending': 2, 'water_pending': 4,
            'assignments_pending': 1, 'cash_lpj': 1, 'cash_finance': 2,
        }
        self.approvals = [{'show': True}, {'show': False}]
        self.queries = []
        self.closed = False

    def cursor(self, dictionary=True):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def _client(monkeypatch, role, username):
    import modules.routes_nav as rn
    conn = FakeConn()
    monkeypatch.setattr(rn, 'get_db_connection', lambda: conn)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rn.register_nav_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = 'SBY'
    return client, conn


def _allow_first_approval(monkeypatch):
    import modules.approvals as approvals
    monkeypatch.setattr(approvals, 'decision_allowed',
                        lambda row, actor, role: bool(row.get('show')))


class TestNavBadges:
    def test_admin_mendapat_badge_operasional_tanpa_acc(self, monkeypatch):
        client, conn = _client(monkeypatch, 'admin', 'admin')
        r = client.get('/api/nav/badges')
        assert r.status_code == 200
        assert r.get_json()['badges'] == {
            'ga_pending': 3,
            'assignments_pending': 1,
            'finance_pending': 2,
            'water_pending': 4,
            'cash_pending': 3,
        }
        assert not any('approval_requests' in q for q in conn.queries)
        assert conn.closed is True

    def test_ga_hanya_antrean_ga_dan_cash_lpj(self, monkeypatch):
        _allow_first_approval(monkeypatch)
        client, conn = _client(monkeypatch, 'ga', 'ga_sby')
        r = client.get('/api/nav/badges')
        assert r.status_code == 200
        assert r.get_json()['badges'] == {
            'ga_pending': 3,
            'assignments_pending': 1,
            'cash_pending': 1,
            'approvals_pending': 1,
        }
        assert not any('os_finance' in q for q in conn.queries)
        assert not any('water_purchases' in q for q in conn.queries)

    def test_finance_hanya_antrean_finance_air_dan_cash(self, monkeypatch):
        _allow_first_approval(monkeypatch)
        client, _ = _client(monkeypatch, 'finance', 'finance_sby')
        r = client.get('/api/nav/badges')
        assert r.status_code == 200
        assert r.get_json()['badges'] == {
            'finance_pending': 2,
            'water_pending': 4,
            'cash_pending': 2,
            'approvals_pending': 1,
        }

    def test_chief_driver_hanya_acc(self, monkeypatch):
        _allow_first_approval(monkeypatch)
        client, conn = _client(monkeypatch, 'chief_driver', 'chief_sby')
        r = client.get('/api/nav/badges')
        assert r.status_code == 200
        assert r.get_json()['badges'] == {'approvals_pending': 1}
        assert all('approval_requests' in q for q in conn.queries)
