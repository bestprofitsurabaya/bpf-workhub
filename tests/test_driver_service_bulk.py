"""Unit Tests — Filter & bulk review catatan service driver → GA (Task 3)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

from modules.routes_driver_service import register_driver_service_routes


BASE_ROWS = {
    11: {
        'id': 11, 'display_id': 'SRV-SBY-20261123-0001',
        'driver_name': 'DRIVERSBY_RIVAN', 'driver_display_name': 'Rivan',
        'nopol': 'B 1126 DFC', 'vehicle_type': 'AVANZA', 'km_kendaraan': 131900,
        'keluhan': 'Rem depan berbunyi', 'status': 'SUBMITTED', 'ga_note': '',
        'created_at': '2026-11-23 08:00:00', 'updated_at': '2026-11-23 08:00:00',
    },
    12: {
        'id': 12, 'display_id': 'SRV-SBY-20261123-0002',
        'driver_name': 'DRIVERSBY_BUDI', 'driver_display_name': 'Budi',
        'nopol': 'B 7777 XYZ', 'vehicle_type': 'INNOVA', 'km_kendaraan': 90000,
        'keluhan': 'AC kurang dingin', 'status': 'REVIEWED', 'ga_note': 'sudah dicek',
        'created_at': '2026-11-20 08:00:00', 'updated_at': '2026-11-21 08:00:00',
    },
    99: {
        'id': 99, 'display_id': 'SRV-SBY-20261123-0099',
        'driver_name': 'DRIVERSBY_RIVAN', 'driver_display_name': 'Rivan',
        'nopol': 'B 9999 DFC', 'vehicle_type': 'AVANZA', 'km_kendaraan': 1000,
        'keluhan': 'Sudah diproses', 'status': 'REVIEWED', 'ga_note': 'lama',
        'created_at': '2026-11-01 08:00:00', 'updated_at': '2026-11-02 08:00:00',
    },
}


class FakeCursor:
    def __init__(self, api):
        self.api = api
        self.rowcount = 0
        self.lastrowid = 11
        self.sql = ''
        self.params = []
        self._rows = []

    def execute(self, sql, params=None):
        self.sql = str(sql).lower()
        self.params = list(params or [])
        if 'select id, status from driver_service_reports' in self.sql:
            # bulk-review pra-cek status
            self._rows = [dict(self.api.rows[i])
                          for i in self.params if i in self.api.rows]
        elif 'update driver_service_reports' in self.sql:
            # params: status, ga_note, actor, <ids...>
            ids = self.params[3:]
            updated = 0
            for rid in ids:
                row = self.api.rows.get(rid)
                if row and row.get('status') == 'SUBMITTED':
                    row['status'] = self.params[0]
                    row['ga_note'] = self.params[1]
                    updated += 1
            self.rowcount = updated
            self.api.last_updated = updated
        elif 'from driver_service_reports' in self.sql:
            self._rows = self.api.filtered_rows(self.sql, self.params)
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.rows = {k: dict(v) for k, v in BASE_ROWS.items()}
        self.last_updated = None
        self.committed = 0
        self.rolled_back = 0
        self.close_count = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.close_count += 1

    def filtered_rows(self, sql, params):
        rows = [dict(r) for r in self.rows.values()]
        p = list(params)
        if 'status=%s' in sql and p:
            st = p.pop(0)
            rows = [r for r in rows if r.get('status') == st]
        if 'date(created_at) >= %s' in sql and p:
            frm = p.pop(0)
            rows = [r for r in rows if str(r.get('created_at', ''))[:10] >= frm]
        if 'date(created_at) <= %s' in sql and p:
            to = p.pop(0)
            rows = [r for r in rows if str(r.get('created_at', ''))[:10] <= to]
        if 'like' in sql and p:
            needle = str(p.pop(0)).strip('%').lower()
            rows = [r for r in rows
                    if any(needle in str(r.get(k, '')).lower()
                           for k in ('display_id', 'nopol', 'keluhan'))]
        return rows


@pytest.fixture()
def client(monkeypatch):
    conn = FakeConn()
    logged = []
    monkeypatch.setattr('modules.routes_driver_service.get_db_connection', lambda: conn)
    monkeypatch.setattr('modules.routes_driver_service.log_activity_async',
                        lambda *a, **k: logged.append((a, k)))
    app = Flask(__name__)
    app.secret_key = 'test'
    register_driver_service_routes(app)
    app.config['TESTING'] = True
    return app.test_client(), conn, logged


def login(c, role):
    with c.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'GA_SBY' if role != 'driver' else 'DRIVERSBY_RIVAN'
        s['branch_code'] = 'SBY'


# --- 3 test dari brief/plan (verbatim) ------------------------------------

def test_bulk_review_menolak_status_invalid(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11], 'status': 'ARCHIVED'})
    assert rv.status_code == 400


def test_bulk_review_tidak_mengubah_baris_sudah_diproses(client):
    c, conn, _ = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [99], 'status': 'REVIEWED'})
    assert rv.status_code == 409
    assert conn.rows[99]['status'] == 'REVIEWED'
    assert conn.committed == 0


def test_filter_tanggal_terbalik_ditolak(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.get('/api/ga/service-reports?from=2026-11-30&to=2026-11-01')
    assert rv.status_code == 400


# --- Tambahan: kontrak bulk ------------------------------------------------

def test_bulk_review_sukses_update_dan_audit_per_id(client):
    c, conn, logged = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11], 'status': 'REVIEWED'})
    assert rv.status_code == 200
    assert rv.get_json() == {'status': 'success', 'updated': 1}
    assert conn.rows[11]['status'] == 'REVIEWED'
    assert conn.committed == 1
    assert len(logged) == 1
    assert logged[0][0][1] == 'driver_service_bulk'
    assert logged[0][0][2] == 'ga'
    # ID laporan service bukan transactions.id (FK activity_logs) → NULL.
    assert logged[0][0][0] is None
    assert logged[0][1]['new_data']['status'] == 'REVIEWED'


def test_bulk_review_reject_wajib_ga_note(client):
    c, conn, _ = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11], 'status': 'REJECTED'})
    assert rv.status_code == 400
    assert conn.rows[11]['status'] == 'SUBMITTED'


def test_bulk_review_reject_dengan_note(client):
    c, conn, logged = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11], 'status': 'REJECTED', 'ga_note': 'Foto tidak sesuai'})
    assert rv.status_code == 200
    assert conn.rows[11]['status'] == 'REJECTED'
    assert conn.rows[11]['ga_note'] == 'Foto tidak sesuai'
    assert logged[0][0][0] is None
    assert logged[0][1]['new_data']['ga_note'] == 'Foto tidak sesuai'


def test_bulk_review_batasi_50_ids(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': list(range(1, 52)), 'status': 'REVIEWED'})
    assert rv.status_code == 400


def test_bulk_review_tolak_ids_kosong_dan_non_int(client):
    c, _, _ = client
    login(c, 'ga')
    assert c.post('/api/ga/service-reports/bulk-review',
                  json={'ids': [], 'status': 'REVIEWED'}).status_code == 400
    assert c.post('/api/ga/service-reports/bulk-review',
                  json={'ids': ['11'], 'status': 'REVIEWED'}).status_code == 400


def test_driver_tidak_bisa_bulk_review(client):
    c, _, _ = client
    login(c, 'driver')
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11], 'status': 'REVIEWED'})
    assert rv.status_code in (301, 302, 401, 403)


def test_bulk_review_semua_submitted_baru_diubah(client):
    c, conn, _ = client
    login(c, 'ga')
    # 11 SUBMITTED, 99 sudah REVIEWED → seluruh batch ditolak (all-or-nothing)
    rv = c.post('/api/ga/service-reports/bulk-review',
                json={'ids': [11, 99], 'status': 'REVIEWED'})
    assert rv.status_code == 409
    assert conn.rows[11]['status'] == 'SUBMITTED'


# --- Tambahan: filter GET --------------------------------------------------

def test_filter_status_dan_q(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.get('/api/ga/service-reports?status=SUBMITTED&q=rem')
    assert rv.status_code == 200
    data = rv.get_json()['data']
    assert [r['id'] for r in data] == [11]


def test_filter_q_nopol(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.get('/api/ga/service-reports?q=7777')
    assert rv.status_code == 200
    assert [r['id'] for r in rv.get_json()['data']] == [12]


def test_filter_rentang_tanggal_valid(client):
    c, _, _ = client
    login(c, 'ga')
    rv = c.get('/api/ga/service-reports?from=2026-11-20&to=2026-11-30')
    assert rv.status_code == 200
    assert [r['id'] for r in rv.get_json()['data']] == [11, 12]


def test_filter_tanggal_format_invalid_ditolak(client):
    c, _, _ = client
    login(c, 'ga')
    assert c.get('/api/ga/service-reports?from=23-11-2026').status_code == 400
