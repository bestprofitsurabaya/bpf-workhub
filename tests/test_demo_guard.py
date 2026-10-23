"""Guard anti-baris-demo (wave-15 fase-3).

Memastikan endpoint statistik & badge nav TIDAK menghitung baris demo
(`is_dummy=1`) — guard regressi setelah pembersihan baris demo produksi
(transactions BPF-DEMO-P1/P2, kasbon CASH-DEMO-D1/D2/G1, trip demo).

DB di-fake; fokus pada SQL yang dikirim: setiap query yang menyentuh
`tabel transaksi wajib membawa filter `(is_dummy=0 OR is_dummy IS NULL)`.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

# Tabel yang pernah diisi baris demo dan dihapus dari produksi.
DEMO_TABLES = ('transactions',)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.queries.append(sql or '')

    def fetchone(self):
        # Cukup untuk api_stats: baris utama {'c': n}, baris hari ini {'c','n'}.
        return {'c': 5, 'n': 125000}

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.queries = []
        self.closed = False

    def cursor(self, dictionary=True):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def _stats_client(monkeypatch, role='admin'):
    import modules.routes_api_transactions as rat
    conn = FakeConn()
    monkeypatch.setattr(rat, 'get_db_connection', lambda: conn)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rat.register_transaction_api(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'guard_test'
        s['branch_code'] = 'SBY'
    return client, conn


class TestApiStatsDemoFilter:
    def test_semua_query_transaksi_terfilter_is_dummy(self, monkeypatch):
        client, conn = _stats_client(monkeypatch)
        r = client.get('/api/stats')
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        sql_tx = [q for q in conn.queries if 'FROM transactions' in q]
        assert sql_tx, 'api_stats harus mem-query transactions'
        assert conn.closed is True
        for q in sql_tx:
            assert 'is_dummy' in q, (
                'REGRESI: query api_stats menyentuh transactions tanpa '
                'filter baris demo -> %s' % q)
            assert '(is_dummy=0 OR is_dummy IS NULL)' in q

    def test_total_dan_ringkasan_hari_ini_terfilter(self, monkeypatch):
        """Dua query yang pernah bocor (total & ringkasan hari ini)."""
        client, conn = _stats_client(monkeypatch)
        assert client.get('/api/stats').status_code == 200
        total_q = [q for q in conn.queries
                   if q.startswith('SELECT COUNT(*) as c FROM transactions')]
        assert total_q and all(
            'is_dummy' in q for q in total_q), 'total harus terfilter dummy'
        today_q = [q for q in conn.queries if 'CURDATE()' in q]
        assert today_q and all(
            'is_dummy' in q for q in today_q), 'ringkasan hari ini harus terfilter dummy'


class TestNavBadgesDemoFilter:
    def test_badge_transaksi_terfilter_is_dummy(self, monkeypatch):
        import modules.routes_nav as rn
        conn = FakeConn()
        monkeypatch.setattr(rn, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        rn.register_nav_routes(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
            s['user_name'] = 'guard_test'
            s['branch_code'] = 'SBY'
        r = client.get('/api/nav/badges')
        assert r.status_code == 200
        for q in conn.queries:
            if any(t in q for t in DEMO_TABLES):
                assert 'is_dummy' in q, (
                    'REGRESI: badge nav menghitung transactions tanpa filter '
                    'baris demo -> %s' % q)
