"""Scoping counter ID FirstWork per cabang (v2.97.1).

Regresi yang dijaga:
1. `GET /api/first-work/id-config` hanya mengirim cabang milik sesi — dulu
   seluruh cabang (beserta counter-nya) tampil di traineer cabang mana pun.
2. Traineer tidak bisa mengubah pengaturan counter global maupun counter
   cabang (role admin wajib).
3. Admin cabang hanya bisa mengatur counter cabangnya sendiri (+ managed);
   Admin Pusat (HO) bisa semua cabang.
4. Sesi tanpa cabang tidak mendapat daftar cabang (fail-closed), bukan semua.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session  # noqa: E402

from modules import routes_first_work as fw  # noqa: E402

BRANCHES = ['SBY', 'MLG']
CFG = json.dumps({'fingerprint_series': 'B', 'bpf_series': 'C'})


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self._rows = []

    def execute(self, sql, params=None):
        q = re.sub(r'\s+', ' ', sql).strip()
        self._rows = self.conn.answer(q, tuple(params or ()))
        return None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeConn:
    """DB master tiruan: cukup untuk _id_state + endpoint counter cabang."""

    def __init__(self, ho_flag=0, branches=None):
        self.ho_flag = ho_flag
        self.branch_codes = list(branches or BRANCHES)
        self.config = CFG
        self.counters = {'B': 25000, 'C': 8000}
        self.branch_counters = {
            ('SBY', 'B'): 500, ('SBY', 'C'): 50,
            ('MLG', 'B'): 900, ('MLG', 'C'): 90,
        }
        self.usage = {
            'SBY': {'max_fp': 499, 'max_bp': 49, 'missing_fp': 1,
                    'missing_bp': 2, 'total': 500},
            'MLG': {'max_fp': 899, 'max_bp': 89, 'missing_fp': 3,
                    'missing_bp': 0, 'total': 900},
        }
        self.writes = []

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        pass

    def close(self):
        pass

    def answer(self, q, params):
        if 'FROM users' in q:
            return [{'admin_all_branches': self.ho_flag, 'managed_branches': ''}]
        if 'system_config' in q:
            if q.startswith('INSERT'):
                self.writes.append(('config', params))
                return []
            return [{'config_value': self.config}]
        if 'INSERT INTO first_work_id_counters' in q:
            self.writes.append(('id_counter', params))
            return []
        if 'FROM first_work_id_counters' in q:
            return [{'series': s, 'last_value': v}
                    for s, v in self.counters.items()]
        if 'INSERT INTO first_work_branch_counters' in q:
            branch, series, value = params
            self.branch_counters[(branch, series)] = int(value)
            self.writes.append(('branch_counter', params))
            return []
        if 'WHERE branch_code=%s AND series=%s' in q:
            branch, series = params
            value = self.branch_counters.get((branch, series))
            return [(value,)] if value is not None else []
        if 'FROM first_work_branch_counters' in q:
            codes = set(params) if 'WHERE branch_code IN' in q else None
            return [{'branch_code': c, 'series': s, 'last_value': v}
                    for (c, s), v in self.branch_counters.items()
                    if codes is None or c in codes]
        if 'COUNT(*) AS total' in q:
            if 'WHERE 1=0' in q:
                codes = set()
            elif 'WHERE branch_code IN' in q:
                codes = set(params)
            else:
                codes = set(self.usage)
            rows = [u for c, u in self.usage.items() if c in codes]
            return [{
                'max_fingerprint': max((r['max_fp'] for r in rows), default=None),
                'max_bpf': max((r['max_bp'] for r in rows), default=None),
                'missing_fingerprint': sum(r['missing_fp'] for r in rows),
                'missing_bpf': sum(r['missing_bp'] for r in rows),
                'total': sum(r['total'] for r in rows),
            }]
        if 'AS used' in q:
            branch = params[0]
            column = 'max_fp' if 'MAX(fingerprint_no)' in q else 'max_bp'
            return [{'used': (self.usage.get(branch) or {}).get(column)}]
        if 'GROUP BY branch_code' in q:
            codes = (set(params) if 'WHERE branch_code IN' in q
                     else set(self.usage))
            return [{'branch_code': c, 'max_fp': u['max_fp'],
                     'max_bp': u['max_bp']}
                    for c, u in self.usage.items() if c in codes]
        if 'SELECT code FROM branches WHERE code=%s' in q:
            return [{'code': params[0]}] if params[0] in self.branch_codes else []
        if 'FROM branches' in q:
            return [{'code': c, 'name': c, 'city': c} for c in self.branch_codes]
        return []


APP = Flask(__name__)
APP.secret_key = 'uji'
fw.register_first_work_routes(APP)


def _client(monkeypatch, conn, role='admin', username='admin_sby',
            branch='SBY'):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    client = APP.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = branch
        s['full_name'] = 'Uji Scope'
    return client


def _state(conn, role, username, branch):
    """Panggil _id_state dengan sesi tiruan (tanpa HTTP)."""
    with APP.test_request_context('/'):
        session['user_role'] = role
        session['user_name'] = username
        session['branch_code'] = branch
        return fw._id_state(conn, fw._counter_branch_scope(conn))


# ================================================================
# Scope baca: _id_state / _counter_branch_scope
# ================================================================
class TestStateScope:
    def test_traineer_only_gets_own_branch(self):
        """Dulu semua cabang ikut terkirim ke traineer — ini regresinya."""
        state = _state(FakeConn(), 'traineer', 'traineer_sby', 'SBY')
        assert state['branch_scope'] == ['SBY']
        assert [b['branch_code'] for b in state['branches']] == ['SBY']
        assert state['next_fingerprint'] == 501   # counter cabang SBY
        assert state['next_bpf'] == 51
        assert state['max_fingerprint'] == 499
        assert state['total'] == 500             # pemakaian cabang sendiri

    def test_branch_admin_scope_follows_username(self):
        conn = FakeConn(ho_flag=0)
        state = _state(conn, 'admin', 'admin_sby', 'MLG')
        assert state['branch_scope'] == ['SBY']
        assert [b['branch_code'] for b in state['branches']] == ['SBY']

    def test_ho_admin_sees_every_branch(self):
        conn = FakeConn(ho_flag=1)
        state = _state(conn, 'admin', 'admin_master', 'SBY')
        assert state['branch_scope'] is None
        assert [b['branch_code'] for b in state['branches']] == BRANCHES
        assert state['total'] == 1400

    def test_session_without_branch_gets_nothing(self):
        state = _state(FakeConn(), 'traineer', 'traineer_baru', '')
        assert state['branch_scope'] == []
        assert state['branches'] == []
        assert state['total'] == 0
        assert state['next_fingerprint'] == 0   # angka global tidak dibocorkan

    def test_branch_following_global_counter_falls_back(self):
        conn = FakeConn()
        conn.branch_counters.pop(('SBY', 'B'))
        state = _state(conn, 'traineer', 'traineer_sby', 'SBY')
        assert state['next_fingerprint'] == 25001  # counter global
        assert state['branches'][0]['has_counter'] is True  # BPF masih punya


# ================================================================
# Endpoint
# ================================================================
class TestEndpointScope:
    def test_get_scoped_to_session_branch(self, monkeypatch):
        client = _client(monkeypatch, FakeConn(), role='traineer',
                         username='traineer_sby', branch='SBY')
        r = client.get('/api/first-work/id-config')
        assert r.status_code == 200
        data = r.get_json()
        assert data['branch_scope'] == ['SBY']
        assert [b['branch_code'] for b in data['branches']] == ['SBY']
        assert 'MLG' not in json.dumps(data['branches'])

    def test_traineer_cannot_change_global_config(self, monkeypatch):
        client = _client(monkeypatch, FakeConn(), role='traineer',
                         username='traineer_sby', branch='SBY')
        r = client.put('/api/first-work/id-config',
                       json={'fingerprint_series': 'B', 'bpf_series': 'C'})
        assert r.status_code == 403

    def test_traineer_cannot_set_branch_counter(self, monkeypatch):
        client = _client(monkeypatch, FakeConn(), role='traineer',
                         username='traineer_sby', branch='SBY')
        r = client.put('/api/first-work/id-config/branch/SBY',
                       json={'start_fingerprint': 600})
        assert r.status_code == 403

    def test_branch_admin_cannot_change_global_config(self, monkeypatch):
        """Counter global berlaku lintas cabang → hanya Admin Pusat."""
        client = _client(monkeypatch, FakeConn(ho_flag=0), role='admin',
                         username='admin_sby', branch='SBY')
        r = client.put('/api/first-work/id-config',
                       json={'fingerprint_series': 'B', 'bpf_series': 'C'})
        assert r.status_code == 403

    def test_branch_admin_cannot_set_other_branch(self, monkeypatch):
        conn = FakeConn(ho_flag=0)
        client = _client(monkeypatch, conn, role='admin',
                         username='admin_sby', branch='SBY')
        r = client.put('/api/first-work/id-config/branch/MLG',
                       json={'start_fingerprint': 1000})
        assert r.status_code == 403
        assert conn.branch_counters[('MLG', 'B')] == 900

    def test_branch_admin_can_set_own_branch(self, monkeypatch):
        conn = FakeConn(ho_flag=0)
        client = _client(monkeypatch, conn, role='admin',
                         username='admin_sby', branch='SBY')
        r = client.put('/api/first-work/id-config/branch/SBY',
                       json={'start_fingerprint': 600})
        assert r.status_code == 200
        assert conn.branch_counters[('SBY', 'B')] == 599
        assert [b['branch_code'] for b in r.get_json()['data']['branches']] == ['SBY']

    def test_ho_admin_can_set_any_branch(self, monkeypatch):
        conn = FakeConn(ho_flag=1)
        client = _client(monkeypatch, conn, role='admin',
                         username='admin_master', branch='SBY')
        r = client.put('/api/first-work/id-config/branch/MLG',
                       json={'start_fingerprint': 1000})
        assert r.status_code == 200
        assert conn.branch_counters[('MLG', 'B')] == 999

    def test_ho_admin_can_change_global_config(self, monkeypatch):
        client = _client(monkeypatch, FakeConn(ho_flag=1), role='admin',
                         username='admin_master', branch='SBY')
        r = client.put('/api/first-work/id-config',
                       json={'fingerprint_series': 'C', 'bpf_series': 'B'})
        assert r.status_code == 200
