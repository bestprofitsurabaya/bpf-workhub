"""Unit tests — Profil Saya (ganti nama & PIN sendiri, semua role/cabang)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

from modules.pin_security import hash_pin, is_pin_hash, verify_pin  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._one = None

    def execute(self, sql, params=None):
        s = ' '.join((sql or '').split())
        self.conn.queries.append(s)
        self._one = None
        if s.startswith('SELECT id, username'):
            self._one = dict(self.conn.user)
        elif s.startswith('UPDATE users SET'):
            self.conn.updates.append((s, params))
            # Petakan nilai sesuai urutan kolom SET (nama dulu, lalu pin).
            columns = [a.split('=')[0].strip() for a in s.split('SET ', 1)[1].split(' WHERE ')[0].split(',')]
            for column, value in zip(columns, params):
                self.conn.user[column] = value

    def fetchone(self):
        return self._one

    def close(self):
        pass


class FakeConn:
    def __init__(self, user):
        self.user = user
        self.queries = []
        self.updates = []
        self.committed = False
        self.closed = False

    def cursor(self, dictionary=True):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _client(monkeypatch, role='finance', username='finance_smg', pin='604128',
            full_name='Finance Semarang', authenticated=True):
    import modules.routes_profile as rp
    conn = FakeConn({
        'id': 42, 'username': username, 'full_name': full_name, 'role': role,
        'branch_code': 'SMG', 'pin': hash_pin(pin), 'last_login': '2026-11-11 08:00:00',
    })
    events = []
    monkeypatch.setattr(rp, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rp, 'log_activity_async',
                        lambda *a, **k: events.append({'args': a, 'kwargs': k}))
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rp.register_profile_routes(app)
    client = app.test_client()
    if authenticated:
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = username
            s['full_name'] = full_name
            s['branch_code'] = 'SMG'
            s['branch_name'] = 'Cabang Semarang'
    return client, conn, events


class TestProfile:
    def test_wajib_login(self, monkeypatch):
        client, _, _ = _client(monkeypatch, authenticated=False)
        assert client.get('/api/profile').status_code == 401
        assert client.patch('/api/profile', json={'full_name': 'X Y'}).status_code == 401

    def test_get_mengembalikan_akun_sendiri_tanpa_pin(self, monkeypatch):
        client, _, _ = _client(monkeypatch)
        r = client.get('/api/profile')
        assert r.status_code == 200
        user = r.get_json()['user']
        assert user['username'] == 'finance_smg'
        assert user['full_name'] == 'Finance Semarang'
        assert user['branch_name'] == 'Cabang Semarang'
        assert 'pin' not in user

    def test_ganti_nama_tersimpan_dan_diaudit(self, monkeypatch):
        client, conn, events = _client(monkeypatch)
        r = client.patch('/api/profile', json={'full_name': '  Rina   Wati  '})
        assert r.status_code == 200
        assert r.get_json()['user']['full_name'] == 'Rina Wati'
        assert conn.user['full_name'] == 'Rina Wati'
        assert conn.committed is True
        assert any(e['args'][1] == 'profile_update' for e in events)
        with client.session_transaction() as s:
            assert s['full_name'] == 'Rina Wati'

    def test_nama_terlalu_pendek_ditolak(self, monkeypatch):
        client, conn, _ = _client(monkeypatch)
        assert client.patch('/api/profile', json={'full_name': ' A '}).status_code == 400
        assert conn.updates == []

    def test_pin_saat_ini_salah_ditolak(self, monkeypatch):
        client, conn, events = _client(monkeypatch)
        r = client.patch('/api/profile', json={'current_pin': '999999', 'new_pin': '731845'})
        assert r.status_code == 400
        assert 'PIN saat ini salah' in r.get_json()['msg']
        assert conn.updates == []
        assert any(e['args'][1] == 'profile_pin_change_failed' for e in events)

    def test_pin_lemah_ditolak(self, monkeypatch):
        client, conn, _ = _client(monkeypatch)
        r = client.patch('/api/profile', json={'current_pin': '604128', 'new_pin': '123456'})
        assert r.status_code == 400
        assert 'lemah' in r.get_json()['msg'].lower()
        assert conn.updates == []

    def test_ganti_pin_disimpan_sebagai_hash_tanpa_ke_audit(self, monkeypatch):
        client, conn, events = _client(monkeypatch)
        r = client.patch('/api/profile', json={'current_pin': '604128', 'new_pin': '731845'})
        assert r.status_code == 200
        stored = conn.user['pin']
        assert is_pin_hash(stored) and verify_pin(stored, '731845')
        assert '731845' not in str(stored)
        pin_events = [e for e in events if e['args'][1] == 'profile_pin_change']
        assert pin_events and '731845' not in str(pin_events[0])

    def test_pin_baru_harus_berbeda(self, monkeypatch):
        client, conn, _ = _client(monkeypatch)
        r = client.patch('/api/profile', json={'current_pin': '604128', 'new_pin': '604128'})
        assert r.status_code == 400
        assert conn.updates == []

    def test_semua_role_bisa_memakai_profil(self, monkeypatch):
        for role in ('driver', 'ob', 'security', 'traineer', 'ga_hr', 'receptionist', 'admin', 'finance'):
            client, _, _ = _client(monkeypatch, role=role, username=f'{role}_smg')
            assert client.get('/api/profile').status_code == 200
