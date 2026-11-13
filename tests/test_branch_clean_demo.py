"""Data demo per cabang: seed idempoten + clean-demo (v2.108.2).

Regresi yang dijaga:

1. `POST /api/branches/<code>/seed-demo` **idempoten** — dulu memakai
   `INSERT IGNORE` tanpa kunci unik, sehingga setiap klik "Buat Data Demo"
   menambah 2 transaksi dummy lagi (MLG pernah sampai 4 baris).
2. `POST /api/branches/<code>/clean-demo` ada dan simetris dengan seed:
   sebelumnya penanaman bisa per cabang tetapi pembersihan hanya untuk cabang
   sesi, jadi Admin Pusat bisa menanam demo ke MLG tanpa bisa membersihkannya.
3. Pembersihan hanya menyentuh baris demo (`DEMO-*`, `is_dummy=1`).
4. Hanya Admin Pusat (HO) yang boleh; admin cabang ditolak 403.
5. Cabang tidak dikenal / nonaktif -> 404; DB cabang tak tersedia -> 400.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

from modules import routes_branches as rb  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self.lastrowid = 0

    def execute(self, sql, params=None):
        q = re.sub(r'\s+', ' ', sql or '').strip().upper()
        params = tuple(params or ())
        self.rowcount = 0
        if q.startswith('INSERT INTO TRANSACTIONS'):
            driver, nopol = params[0], params[1]
            exists = any(t['driver_name'] == driver and t['nopol'] == nopol
                         for t in self.conn.dummy_tx)
            if not exists:
                self.conn.dummy_tx.append({'driver_name': driver,
                                           'nopol': nopol})
                self.rowcount = 1
        elif q.startswith('DELETE FROM TRANSACTIONS WHERE IS_DUMMY=1'):
            self.rowcount = len(self.conn.dummy_tx)
            self.conn.dummy_tx.clear()
        elif q.startswith('INSERT INTO SYSTEM_CONFIG'):
            self.rowcount = 1
        elif q.startswith('DELETE FROM APPOINTMENTS'):
            self.rowcount = 0
        return None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, dummy_tx=None):
        self.dummy_tx = list(dummy_tx or [])
        self.commits = 0
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


BRANCHES = {
    'MLG': {'code': 'MLG', 'name': 'Cabang Malang', 'is_active': 1},
    'OFF': {'code': 'OFF', 'name': 'Cabang Nonaktif', 'is_active': 0},
}


def _setup(monkeypatch, conn=None, ho=True):
    import modules.admin_scope as scope

    logs = []
    monkeypatch.setattr(rb.bm, 'get_branch', lambda code: BRANCHES.get(code))
    monkeypatch.setattr(rb, 'get_db_connection',
                        lambda branch_code=None: conn)
    monkeypatch.setattr(rb, 'log_activity_async',
                        lambda *a, **k: logs.append({'args': a, 'kwargs': k}))
    monkeypatch.setattr(scope, '_admin_row',
                        lambda conn=None: {'admin_all_branches': 1 if ho else 0,
                                           'managed_branches': ''})
    app = Flask(__name__)
    app.secret_key = 'uji-demo'
    rb.register_branch_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = 'admin'
        s['user_name'] = 'admin_master' if ho else 'admin_mlg'
        s['branch_code'] = 'SBY'
        s['full_name'] = 'Admin Uji'
    return client, logs


def _seed(client, code='MLG'):
    return client.post(f'/api/branches/{code}/seed-demo')


def _clean(client, code='MLG'):
    return client.post(f'/api/branches/{code}/clean-demo')


# ================================================================
# Seed idempoten
# ================================================================
class TestSeedIdempoten:
    def test_seed_dua_kali_tetap_dua_transaksi(self, monkeypatch):
        import scripts.seed_demo_routes as seed

        monkeypatch.setattr(seed, 'seed_demo_appointments',
                            lambda conn=None, commit=True: {
                                'created': 0, 'skipped': 20, 'error': None})
        conn = FakeConn()
        client, _ = _setup(monkeypatch, conn)

        assert _seed(client).status_code == 200
        assert len(conn.dummy_tx) == 2
        assert _seed(client).status_code == 200
        assert len(conn.dummy_tx) == 2, 'seed harus idempoten'

    def test_sql_tidak_lagi_insert_ignore(self):
        sql = rb._DUMMY_TX_SQL.upper()
        assert 'INSERT IGNORE' not in sql
        assert 'NOT EXISTS' in sql

    def test_seed_cabang_nonaktif_404(self, monkeypatch):
        client, _ = _setup(monkeypatch, FakeConn())
        assert _seed(client, 'OFF').status_code == 404
        assert _seed(client, 'XXX').status_code == 404

    def test_seed_db_tidak_tersedia_400(self, monkeypatch):
        client, _ = _setup(monkeypatch, None)
        assert _seed(client).status_code == 400


# ================================================================
# Clean-demo per cabang
# ================================================================
class TestCleanDemo:
    def test_clean_menghapus_transaksi_dummy(self, monkeypatch):
        import scripts.seed_demo_routes as seed

        calls = []
        monkeypatch.setattr(seed, 'clean_demo_appointments',
                            lambda conn=None, commit=True: calls.append(commit)
                            or {'deleted': 20, 'error': None})
        conn = FakeConn(dummy_tx=[{'driver_name': 'AKHAD', 'nopol': 'L 1413 CBI'},
                                  {'driver_name': 'AHMAT', 'nopol': 'B 2628 SRP'}])
        client, logs = _setup(monkeypatch, conn)

        rv = _clean(client)
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['status'] == 'success'
        assert '2 transaksi' in body['msg']
        assert conn.dummy_tx == []
        assert calls == [False], 'clean_demo_appointments harus commit=False'
        assert conn.commits == 1
        assert logs and logs[0]['args'][1] == 'branch_clean_demo'

    def test_clean_tanpa_data_tetap_sukses(self, monkeypatch):
        import scripts.seed_demo_routes as seed

        monkeypatch.setattr(seed, 'clean_demo_appointments',
                            lambda conn=None, commit=True: {
                                'deleted': 0, 'error': None})
        conn = FakeConn()
        client, _ = _setup(monkeypatch, conn)
        rv = _clean(client)
        assert rv.status_code == 200
        assert '0 transaksi' in rv.get_json()['msg']

    def test_clean_cabang_nonaktif_404(self, monkeypatch):
        client, _ = _setup(monkeypatch, FakeConn())
        assert _clean(client, 'OFF').status_code == 404
        assert _clean(client, 'XXX').status_code == 404

    def test_clean_db_tidak_tersedia_400(self, monkeypatch):
        client, _ = _setup(monkeypatch, None)
        assert _clean(client).status_code == 400


# ================================================================
# Hak akses
# ================================================================
class TestHakAkses:
    def test_admin_cabang_ditolak_403(self, monkeypatch):
        import scripts.seed_demo_routes as seed

        monkeypatch.setattr(seed, 'clean_demo_appointments',
                            lambda conn=None, commit=True: {
                                'deleted': 0, 'error': None})
        conn = FakeConn(dummy_tx=[{'driver_name': 'AKHAD', 'nopol': 'L 1413 CBI'}])
        client, _ = _setup(monkeypatch, conn, ho=False)

        assert _clean(client).status_code == 403
        assert len(conn.dummy_tx) == 1, 'admin cabang tidak boleh menghapus'
        assert _seed(client).status_code == 403

    def test_bukan_admin_ditolak(self, monkeypatch):
        client, _ = _setup(monkeypatch, FakeConn())
        with client.session_transaction() as s:
            s['user_role'] = 'traineer'
        assert _clean(client).status_code == 403
