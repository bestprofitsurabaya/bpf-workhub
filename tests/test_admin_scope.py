"""Unit tests — modul admin_scope (v2.37.0): Admin Pusat vs Admin cabang.

Pola fake-DB sama dengan test_docseq_admin / test_users_sync.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session  # noqa: E402

import modules.admin_scope as admin_scope  # noqa: E402


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.log = []

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))
        return None

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None):
        self.cur = FakeCursor(rows)
        self.commits = 0

    def cursor(self, dictionary=True):
        return self.cur

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _app_session(role='admin', username='admin', branch='SBY'):
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    with app.test_request_context():
        session['user_role'] = role
        session['user_name'] = username
        session['branch_code'] = branch
        yield app


class TestHoAdmin:
    def test_admin_legacy_pusat(self):
        for _ in _app_session('admin', 'admin', 'SBY'):
            assert admin_scope.is_ho_admin() is True

    def test_admin_sby_bukan_pusat(self):
        for _ in _app_session('admin', 'admin_sby', 'SBY'):
            assert admin_scope.is_ho_admin() is False

    def test_admin_suffix_tak_dikenal_tetap_cabang(self):
        # Fail-closed: username ber-suffix = Admin cabang (suffix = kode cabang).
        for _ in _app_session('admin', 'admin_ho', 'SBY'):
            assert admin_scope.is_ho_admin() is False

    def test_flag_all_branches_menaikkan_jadi_pusat(self):
        for _ in _app_session('admin', 'admin_sby', 'SBY'):
            monkey = lambda conn=None: {'admin_all_branches': 1,
                                        'managed_branches': ''}
            import modules.admin_scope as asc
            asc._admin_row_orig = asc._admin_row
            asc._admin_row = monkey
            try:
                assert asc.is_ho_admin() is True
            finally:
                asc._admin_row = asc._admin_row_orig

    def test_role_non_admin_bukan_pusat(self):
        for _ in _app_session('finance', 'finance_sby', 'SBY'):
            assert admin_scope.is_ho_admin() is False

    def test_tanpa_db_admin_sby_tetap_cabang(self):
        # DB mati: flag tak bisa dibaca → fail-closed ke Admin cabang.
        for _ in _app_session('admin', 'admin_sby', 'SBY'):
            assert admin_scope.is_ho_admin() is False


class TestAdminBranches:
    def test_admin_cabang_scope_suffix(self):
        for _ in _app_session('admin', 'admin_bdg', 'BDG'):
            codes, all_b = admin_scope.admin_branches()
            assert all_b is False
            assert codes == ['BDG']

    def test_admin_cabang_managed_tambahan(self, monkeypatch):
        for _ in _app_session('admin', 'admin_sby', 'SBY'):
            monkeypatch.setattr(admin_scope, 'admin_managed_branches',
                                lambda conn=None: ['MLG'])
            codes, all_b = admin_scope.admin_branches()
            assert codes == ['SBY', 'MLG']
            assert all_b is False


class TestHoOnly:
    def test_ho_only_lolos_untuk_pusat(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'

        @app.route('/x')
        @admin_scope.ho_only
        def x():
            return 'ok'

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['user_role'] = 'admin'
                s['user_name'] = 'admin'
                s['branch_code'] = 'SBY'
            assert c.get('/x').status_code == 200

    def test_ho_only_tolak_admin_cabang(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'

        @app.route('/x')
        @admin_scope.ho_only
        def x():
            return 'ok'

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['user_role'] = 'admin'
                s['user_name'] = 'admin_sby'
                s['branch_code'] = 'SBY'
            r = c.get('/x')
            assert r.status_code == 403

    def test_ho_only_tolak_role_lain_dan_anonim(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'

        @app.route('/x')
        @admin_scope.ho_only
        def x():
            return 'ok'

        with app.test_client() as c:
            assert c.get('/x').status_code == 401
            with c.session_transaction() as s:
                s['user_role'] = 'finance'
                s['user_name'] = 'finance_sby'
                s['branch_code'] = 'SBY'
            assert c.get('/x').status_code == 403


class TestEnsureColumns:
    def test_ensure_idempoten(self):
        conn = FakeConn()
        assert admin_scope.ensure_branch_admin_columns(conn) is True
        alters = [sql for sql, _ in conn.cur.log if 'ALTER TABLE users' in sql]
        assert len(alters) == 2
        assert conn.commits >= 1

    def test_ensure_tanpa_db(self, monkeypatch):
        import modules.config as cfg
        monkeypatch.setattr(cfg, 'get_master_connection', lambda: None)
        assert admin_scope.ensure_branch_admin_columns() is False
