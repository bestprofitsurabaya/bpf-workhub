"""Wave v2.73.0 — Assignment Konfirmasi & Swap.

Menjamin:
- ensure_assignment_tables membuat tabel assignment_swaps secara idempoten
  di DB yang dituju (dipanggil app.py di startup — pola ensure approvals),
  TIDAK menutup koneksi yang diberikan dari luar.
- DB tanpa koneksi → ensure gagal bersih (False, bukan crash).
- Endpoint riwayat swap (/api/assignments/swap-history) mengembalikan baris
  dari tabel yang sama (fitur tukar driver yang dulu terbenam).
- Cleanup legacy: /api/verify-pin & /api/vehicle_bbm sudah dihapus
  (lihat test_hardening_v247.py) — di sini diuji jalur penggantinya.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_api_assignments as raa  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        self.conn.sql_log.append((sql.strip(), params))

    def fetchall(self):
        return self.conn._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None):
        self.sql_log = []
        self._rows = rows or []
        self.closes = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.commits = getattr(self, 'commits', 0) + 1

    def close(self):
        self.closes += 1


class TestEnsureAssignmentTables:
    def test_buat_tabel_idempoten_tanpa_tutup_conn(self):
        conn = FakeConn()
        ok = raa.ensure_assignment_tables(conn)
        assert ok is True
        create = [sql for sql, _ in conn.sql_log
                  if 'CREATE TABLE' in sql and 'assignment_swaps' in sql]
        assert len(create) == 1
        assert 'IF NOT EXISTS' in create[0]
        # kolom inti yang dipakai INSERT swap/release & SELECT riwayat
        for col in ('nopol', 'old_driver', 'new_driver', 'category',
                    'reason', 'ga_name', 'created_at'):
            assert col in create[0], col
        assert conn.closes == 0  # conn luar TIDAK ditutup ensure

    def test_db_tidak_tersedia_gagal_bersih(self, monkeypatch):
        monkeypatch.setattr(raa, 'get_db_connection', lambda: None)
        assert raa.ensure_assignment_tables() is False

    def test_ensure_sendiri_menutup_koneksi_buatan_sendiri(self, monkeypatch):
        conn = FakeConn()
        monkeypatch.setattr(raa, 'get_db_connection', lambda: conn)
        assert raa.ensure_assignment_tables() is True
        assert conn.closes == 1  # koneksi milik ensure ditutup


class TestSwapHistory:
    def test_riwayat_swap_dari_tabel_assignment_swaps(self, monkeypatch):
        app = Flask(__name__)
        app.secret_key = 'test'
        raa.register_assignment_api(app)
        c = app.test_client()
        # v2.74.0 (pentest hardening): riwayat swap wajib sesi back-office.
        with c.session_transaction() as s:
            s['user_role'] = 'ga'
            s['user_name'] = 'ga_sby'
        rows = [{'id': 1, 'nopol': 'L 1 AB', 'old_driver': 'BUDI',
                 'new_driver': 'RIVAN', 'category': 'driver_request',
                 'reason': 'cuti panjang', 'ga_name': 'GA Officer',
                 'created_at': '2026-10-20 08:00:00'}]
        conn = FakeConn(rows=rows)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: conn)
        r = c.get('/api/assignments/swap-history')
        assert r.status_code == 200
        data = r.get_json()
        assert data[0]['new_driver'] == 'RIVAN'
        assert 'assignment_swaps' in conn.sql_log[0][0]
