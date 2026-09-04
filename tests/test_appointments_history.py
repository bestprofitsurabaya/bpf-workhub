"""
Unit Tests — /api/appointments/history (v2.29.8): Riwayat appointment selesai
untuk dashboard Marketing.

Endpoint khusus /completed milik driver (PWA tanpa sesi, scope driver_name)
sehingga TIDAK cocok untuk marketing login. /history men-scope
marketing_username ke sesi login, mengembalikan status completed lintas
tanggal (terbaru dulu) dengan batas jumlah baris.

DB di-fake (monkeypatch get_db_connection pada modul routes) — pola sama
dengan test_users_sync.py — tidak butuh MariaDB.

Jalankan:
    python3 -m pytest tests/test_appointments_history.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.log = []  # (sql, params)
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))

    def fetchone(self):
        return None

    def fetchall(self):
        if self.log and 'FROM appointments' in self.log[-1][0]:
            return self.db.get('rows', [])
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.cursors = []

    def cursor(self, dictionary=True):
        c = FakeCursor(self.db)
        self.cursors.append(c)
        return c

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _last_select(conn):
    for cur in conn.cursors:
        for sql, params in cur.log:
            if sql.lstrip().upper().startswith('SELECT'):
                return sql, params
    return '', ()


class TestAppointmentHistory:
    def _register(self, monkeypatch, db, role='marketing', username='marketing_yusie_sby'):
        import modules.routes_appointments as ra
        conn = FakeConn(db)
        monkeypatch.setattr(ra, 'get_db_connection', lambda: conn)
        import modules.config as mc
        monkeypatch.setattr(mc, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ra.register_appointment_routes(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = username
            s['full_name'] = 'Marketing Yusie'
        return client, conn

    def _rows(self):
        return [{
            'id': 1, 'display_id': 'APP-1', 'nasabah_name': 'Nasabah Lama',
            'marketing_member': 'Yusie', 'nasabah_phone': '0811', 'alamat': 'Jl. A',
            'area': 'Surabaya Barat', 'sesi': '1', 'visit_time': None,
            'appointment_date': '2026-09-01', 'status': 'completed',
            'driver_name': 'Akhad', 'visit_result': 'ditemui', 'notes': '',
        }]

    def test_marketing_hanya_melihat_riwayat_own(self, monkeypatch):
        """Marketing → SQL berisi marketing_username = sesi login (anti bocor data user lain)."""
        db = {'rows': self._rows()}
        client, conn = self._register(monkeypatch, db,
                                      role='marketing', username='marketing_yusie_sby')
        r = client.get('/api/appointments/history?limit=50')
        assert r.status_code == 200, r.get_json()
        assert len(r.get_json()['data']) == 1
        sql, params = _last_select(conn)
        assert 'marketing_username = %s' in sql
        assert params[0] == 'marketing_yusie_sby'
        assert 'status = \'completed\'' in sql

    def test_urutan_terbaru_dulu_dan_limit(self, monkeypatch):
        """Riwayat diurut completed_at DESC dan dibatasi jumlah baris."""
        db = {'rows': self._rows()}
        client, conn = self._register(monkeypatch, db)
        r = client.get('/api/appointments/history?limit=25')
        assert r.status_code == 200
        sql, _ = _last_select(conn)
        assert 'COALESCE(completed_at' in sql
        assert 'LIMIT 25' in sql

    def test_ga_admin_melihat_semua_tanpa_filter_marketing(self, monkeypatch):
        """GA/admin (non-marketing) → tanpa filter marketing_username."""
        db = {'rows': self._rows()}
        client, conn = self._register(monkeypatch, db, role='ga', username='ga_sby')
        r = client.get('/api/appointments/history')
        assert r.status_code == 200, r.get_json()
        sql, _ = _last_select(conn)
        assert 'marketing_username' not in sql

    def test_role_non_marketing_admin_ditolak_403(self, monkeypatch):
        """Role di luar whitelist (mis. ob) tidak boleh akses riwayat."""
        db = {'rows': []}
        client, _ = self._register(monkeypatch, db, role='ob', username='ob_faisol_sby')
        r = client.get('/api/appointments/history')
        assert r.status_code == 403

    def test_limit_invalid_fallback_50(self, monkeypatch):
        """limit non-angka → fallback 50 (bukan error 500)."""
        db = {'rows': self._rows()}
        client, _ = self._register(monkeypatch, db)
        r = client.get('/api/appointments/history?limit=abc')
        assert r.status_code == 200, r.get_json()
        assert len(r.get_json()['data']) == 1


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])
