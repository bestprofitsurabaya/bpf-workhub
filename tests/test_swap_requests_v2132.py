"""v2.132.0 — Driver mengajukan ganti kendaraan (tukar / pindah)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import modules.routes_api_assignments as raa


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        self.conn.sql_log.append((sql.strip(), params))
        self._sql = sql
        self.conn._last_query = sql

    def fetchone(self):
        if 'information_schema.COLUMNS' in self._sql:
            return {'n': 1 if self.conn.column_exists else 0}
        return self.conn.one

    def fetchall(self):
        return self.conn.many

    def close(self):
        pass


class FakeConn:
    def __init__(self, one=None, many=None, column_exists=False):
        self.sql_log = []
        self.one = one
        self.many = many or []
        self.column_exists = column_exists
        self.closes = 0
        self.commits = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closes += 1


class TestEnsureSwapRequests:
    def test_ensure_membuat_tabel_pengajuan(self):
        conn = FakeConn()
        assert raa.ensure_assignment_tables(conn) is True
        ddl = [sql for sql, _ in conn.sql_log
               if 'CREATE TABLE' in sql and 'assignment_swap_requests' in sql]
        assert len(ddl) == 1
        for col in ('swap_type', 'requester_driver', 'requester_nopol',
                    'target_driver', 'target_nopol', 'category', 'reason',
                    'status', 'requester_odo', 'requester_photo',
                    'target_odo', 'target_photo', 'request_code'):
            assert col in ddl[0], col
        assert 'uq_swap_request_code' in ddl[0]
        assert conn.closes == 0

    def test_ensure_menambah_request_id_bila_belum_ada(self):
        conn = FakeConn(column_exists=False)
        assert raa.ensure_assignment_tables(conn) is True
        alters = [sql for sql, _ in conn.sql_log
                  if 'ALTER TABLE assignment_swaps' in sql]
        assert len(alters) == 1
        assert 'request_id' in alters[0]
        assert 'idx_swap_request' in alters[0]

    def test_ensure_tidak_alter_bila_kolom_ada(self):
        conn = FakeConn(column_exists=True)
        assert raa.ensure_assignment_tables(conn) is True
        alters = [sql for sql, _ in conn.sql_log
                  if 'ALTER TABLE assignment_swaps' in sql]
        assert alters == []

    def test_ensure_db_tidak_tersedia_gagal_bersih(self, monkeypatch):
        monkeypatch.setattr(raa, 'get_db_connection', lambda: None)
        assert raa.ensure_assignment_tables() is False
