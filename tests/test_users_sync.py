"""
Unit Tests — /api/users/sync (v2.29.7): Admin bisa edit SEMUA detail user.

- branch_code kini benar-benar tersimpan (sebelumnya diabaikan backend).
- Username bisa diganti saat edit (update by-id; username = kunci login, bukan PK).
- Toggle aktif/nonaktif & bulk action TIDAK menghapus branch_code/PIN (eksplisit-saja).
- Username baru yang sudah dipakai user lain → ditolak 400 dengan pesan jelas.

DB di-fake (monkeypatch get_master_connection pada modul routes), pola sama
dengan test_bulk_accounts_manual_route.py — tidak butuh MariaDB.

Jalankan:
    python3 -m pytest tests/test_users_sync.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask


class FakeCursor:
    """Cursor palsu: mencatat SEMUA eksekusi SQL + simulasi row users."""

    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.log = []  # (sql, params)

    def execute(self, sql, params=None):
        sql = sql or ''
        self.log.append((sql, params or ()))
        up = sql.lstrip().upper()
        if up.startswith('UPDATE'):
            on_update = self.db.get('on_update')
            if on_update:
                on_update(sql, params)
            self.rowcount = self.db.get('update_rowcount', 1)
        elif up.startswith('INSERT'):
            self.rowcount = 1
        else:
            self.rowcount = 0

    def fetchone(self):
        if not self.log:
            return None
        sql = self.log[-1][0]
        if 'FROM users' in sql:
            return self.db.get('existing_row')  # None → user baru
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.cursors = []
        self.rolled_back = False

    def cursor(self, dictionary=True):
        c = FakeCursor(self.db)
        self.cursors.append(c)
        return c

    def commit(self):
        pass

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _all_log(conn):
    return [entry for cur in conn.cursors for entry in cur.log]


class TestUsersSync:
    def _register(self, monkeypatch, db, role='admin'):
        import modules.routes_api_master as ram
        conn = FakeConn(db)
        monkeypatch.setattr(ram, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(ram, 'get_master_connection', lambda: conn)
        import modules.config as mc
        monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(ram, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ram.register_master_api(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = 'admin'
        return client, conn

    def _existing(self, team='Tim A', pin='123456', branch='SBY'):
        return (team, pin, branch)  # SELECT team_name, pin, branch_code

    def test_edit_user_menyimpan_branch_code_dan_username_baru(self, monkeypatch):
        """Edit dengan id: UPDATE by-id memuat username baru + branch_code."""
        db = {'existing_row': self._existing()}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'id': 5, 'username': 'ga_baru', 'full_name': 'GA Baru', 'role': 'ga',
            'pin': '', 'team_name': 'Tim A', 'branch_code': 'BDG', 'is_active': True,
        })
        assert r.status_code == 200, r.get_json()
        updates = [(sql, params) for sql, params in _all_log(conn) if sql.lstrip().upper().startswith('UPDATE')]
        assert len(updates) == 1
        sql, params = updates[0]
        assert 'branch_code' in sql
        # (username, full_name, role, pin, team, branch_code, is_active, id)
        assert params[0] == 'ga_baru'
        assert params[4] == 'Tim A'
        assert params[5] == 'BDG'
        assert params[6] == 1
        assert params[7] == 5

    def test_edit_tanpa_pin_mempertahankan_pin_lama(self, monkeypatch):
        """PIN dikosongkan → PIN existing dipertahankan (tidak ditimpa)."""
        db = {'existing_row': self._existing(pin='777333')}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'id': 5, 'username': 'ga_satu', 'full_name': 'GA Satu', 'role': 'ga',
            'pin': '', 'team_name': 'Tim A', 'branch_code': 'SBY', 'is_active': True,
        })
        assert r.status_code == 200, r.get_json()
        updates = [(sql, params) for sql, params in _all_log(conn) if sql.lstrip().upper().startswith('UPDATE')]
        assert updates[0][1][3] == '777333'

    def test_toggle_tanpa_branch_dan_pin_mempertahankan_keduanya(self, monkeypatch):
        """Toggle nonaktif (tanpa id/branch/pin) → INSERT upsert memakai
        branch_code & PIN dari DB (tidak menghapus cabang user)."""
        db = {'existing_row': self._existing(team='Tim A', pin='555111', branch='MDN')}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'fin1', 'full_name': 'FIN Satu', 'role': 'finance',
            'is_active': False,
        })
        assert r.status_code == 200, r.get_json()
        inserts = [(sql, params) for sql, params in _all_log(conn)
                   if sql.lstrip().upper().startswith('INSERT')]
        assert len(inserts) == 1
        sql, params = inserts[0]
        assert 'branch_code' in sql
        # (username, full_name, role, pin, team, branch_code, is_active)
        assert params[3] == '555111'   # PIN dipertahankan
        assert params[4] == 'Tim A'    # team dipertahankan
        assert params[5] == 'MDN'      # branch_code dipertahankan
        assert params[6] == 0

    def test_tambah_user_baru_branch_kosong(self, monkeypatch):
        """User baru (tidak ada row) tanpa branch → NULL (cabang pusat)."""
        db = {'existing_row': None}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'ob_baru', 'full_name': 'OB Baru', 'role': 'ob',
            'pin': '123456', 'team_name': '', 'branch_code': '', 'is_active': True,
        })
        assert r.status_code == 200, r.get_json()
        inserts = [(sql, params) for sql, params in _all_log(conn)
                   if sql.lstrip().upper().startswith('INSERT')]
        assert len(inserts) == 1
        assert inserts[0][1][5] is None

    def test_username_duplikat_ditolak_400(self, monkeypatch):
        """Ganti username ke nama yang sudah dipakai user lain → 400 + rollback."""
        from mysql.connector import IntegrityError

        def boom(sql, params):
            raise IntegrityError('Duplicate entry')

        db = {'existing_row': self._existing(), 'on_update': boom}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'id': 5, 'username': 'ga_sby', 'full_name': 'GA Satu', 'role': 'ga',
            'team_name': 'Tim A', 'branch_code': 'SBY', 'is_active': True,
        })
        assert r.status_code == 400
        assert 'sudah dipakai' in r.get_json()['msg']
        assert conn.rolled_back

    def test_id_tidak_ditemukan_ditolak_404(self, monkeypatch):
        db = {'existing_row': self._existing(), 'update_rowcount': 0}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'id': 999, 'username': 'ga_ghost', 'full_name': 'Hantu', 'role': 'ga',
            'team_name': '', 'branch_code': '', 'is_active': True,
        })
        assert r.status_code == 404

    # ------------------------------------------------------------
    # v2.29.9: username wajib diawali token divisi (konvensi {divisi}_{cabang})
    # ------------------------------------------------------------
    def test_role_marketing_username_tanpa_awalan_ditolak_400(self, monkeypatch):
        """User BARU role marketing harus diawali marketing_ (mis. dewi → ditolak)."""
        db = {'existing_row': None}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'dewi', 'full_name': 'Dewi', 'role': 'marketing',
            'pin': '123456', 'team_name': 'Tim Dewi', 'branch_code': 'MLG', 'is_active': True,
        })
        assert r.status_code == 400
        assert 'marketing_' in r.get_json()['msg']

    def test_role_finance_username_tanpa_awalan_ditolak_400(self, monkeypatch):
        """User BARU role finance harus diawali finance_ (mis. uang → ditolak)."""
        db = {'existing_row': None}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'uang', 'full_name': 'Keuangan', 'role': 'finance',
            'pin': '123456', 'team_name': '', 'branch_code': 'SBY', 'is_active': True,
        })
        assert r.status_code == 400
        assert 'finance_' in r.get_json()['msg']

    def test_akun_lama_nonkonform_masih_bisa_disimpan(self, monkeypatch):
        """Akun lama (username+role sama sudah ada) tetap boleh di-save/toggle
        tanpa rename — mis. hasil bulk-create marketing lama bernama orang."""
        db = {'existing_row': self._existing()}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'dewi', 'full_name': 'Dewi', 'role': 'marketing',
            'is_active': False,
        })
        assert r.status_code == 200, r.get_json()
        upserts = [sql for sql, _ in _all_log(conn)
                   if sql.lstrip().upper().startswith('INSERT')]
        assert len(upserts) == 1

    def test_username_legacy_qa_diperbolehkan(self, monkeypatch):
        """Akun sistem lama (qa, test_check, e2e_driver) tetap bisa dibuat/simpan."""
        db = {'existing_row': None}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'qa', 'full_name': 'QA System', 'role': 'ga',
            'pin': '123456', 'team_name': '', 'branch_code': '', 'is_active': True,
        })
        assert r.status_code == 200, r.get_json()

    def test_username_driver_dan_it_bebas_awalan(self, monkeypatch):
        """Driver (username = nama orang) & role it_* bebas dari aturan awalan."""
        db = {'existing_row': None}
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'akhad', 'full_name': 'Akhad', 'role': 'driver',
            'pin': '123456', 'team_name': '', 'branch_code': 'SBY', 'is_active': True,
        })
        assert r.status_code == 200, r.get_json()
        inserts = [sql for sql, _ in _all_log(conn)
                   if sql.lstrip().upper().startswith('INSERT')]
        assert len(inserts) == 1
        # role it per-cabang: username = role (it_sby …) — bebas
        db2 = {'existing_row': None}
        client2, _ = self._register(monkeypatch, db2)
        r2 = client2.post('/api/users/sync', json={
            'username': 'it_bdg', 'full_name': 'IT Bandung', 'role': 'it_bdg',
            'pin': '123456', 'team_name': '', 'branch_code': 'BDG', 'is_active': True,
        })
        assert r2.status_code == 200, r2.get_json()

    def test_non_admin_ditolak_403(self, monkeypatch):
        db = {'existing_row': None}
        client, _ = self._register(monkeypatch, db, role='ga')
        r = client.post('/api/users/sync', json={
            'username': 'x', 'full_name': 'X', 'role': 'ga', 'is_active': True,
        })
        assert r.status_code == 403

    def test_role_tidak_valid_ditolak_400(self, monkeypatch):
        db = {'existing_row': None}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/sync', json={
            'username': 'x', 'full_name': 'X', 'role': 'hacker', 'is_active': True,
        })
        assert r.status_code == 400


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])