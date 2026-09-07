"""Unit test — filter rentang tanggal daftar pengajuan air minum (v2.37.4).

Permintaan finance: date range search + filter status; default daftar
menampilkan pengajuan bulan berjalan (awal s/d akhir bulan).

Diuji:
- _month_range       : awal & akhir bulan (termasuk Desember → Januari);
- _parse_ymd         : valid / invalid / None;
- SQL guard          : WHERE memakai parameter (%s) — tidak ada f-string nilai;
- endpoint           : default bulan berjalan, from/to eksplisit, status
                       invalid → all, q → LIKE 3 kolom, OB ter-scope ob_name.

Jalankan: python3 -m pytest tests/test_water_filter.py -v
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

import modules.routes_water as rw
from modules.routes_water import register_water_routes, _month_range, _parse_ymd


# ================================================================
# Pure functions
# ================================================================
class TestMonthRange:
    def test_awal_dan_akhir_bulan(self):
        f, t = _month_range(date(2026, 9, 7))
        assert f == date(2026, 9, 1)
        assert t == date(2026, 10, 1)  # eksklusif

    def test_desember_ke_januari(self):
        f, t = _month_range(date(2026, 12, 31))
        assert f == date(2026, 12, 1)
        assert t == date(2027, 1, 1)

    def test_tanggal_1(self):
        f, t = _month_range(date(2026, 2, 1))
        assert f == date(2026, 2, 1)
        assert t == date(2026, 3, 1)


class TestParseYmd:
    def test_valid(self):
        assert _parse_ymd('2026-09-07') == date(2026, 9, 7)

    def test_dengan_waktu_dipotong(self):
        assert _parse_ymd('2026-09-07T13:00:00') == date(2026, 9, 7)

    def test_invalid(self):
        assert _parse_ymd('07-09-2026') is None
        assert _parse_ymd('bukan-tanggal') is None
        assert _parse_ymd(None) is None
        assert _parse_ymd('') is None


# ================================================================
# Endpoint — fake DB menangkap SQL & params
# ================================================================
class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.executed = []  # (sql, params)
        self._rows = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if 'FROM water_purchases' in sql and 'SELECT wp.*' in sql:
            self._rows = self.store.get('rows', [])
        elif 'water_purchase_items' in sql:
            self._rows = []
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, store):
        self.store = store
        self.cursors = []

    def cursor(self, dictionary=False):
        c = FakeCursor(self.store)
        self.cursors.append(c)
        return c

    def close(self):
        pass


@pytest.fixture()
def env():
    """(client, conns) — conns mengumpulkan FakeConn yang dipakai endpoint."""
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['TESTING'] = True
    register_water_routes(app)
    conns = []
    with app.test_client() as c:
        yield c, conns


def _login(client, role='finance', name='Cynthia Permatasaya', branch='SBY'):
    with client.session_transaction() as s:
        s['user_name'] = name
        s['full_name'] = name
        s['user_role'] = role
        s['branch_code'] = branch


def _main_queries(conns):
    """Semua (sql, params) query utama water_purchases dari conn yang terpakai."""
    out = []
    for conn in conns:
        for cur in conn.cursors:
            for sql, params in cur.executed:
                if 'SELECT wp.*' in sql:
                    out.append((sql, params))
    return out


def test_default_bulan_berjalan(env, monkeypatch):
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client)
    r = client.get('/api/water/purchases')
    assert r.status_code == 200
    d = r.get_json()
    assert set(d.keys()) >= {'purchases', 'range', 'filters'}
    qs = _main_queries(conns)
    assert qs, 'query utama tidak dieksekusi'
    sql, params = qs[0]
    assert 'wp.purchase_date >= %s' in sql and 'wp.purchase_date < %s' in sql
    assert str(params[0]).endswith('-01')  # awal bulan berjalan


def test_from_to_eksplisit_dan_status(env, monkeypatch):
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client)
    r = client.get('/api/water/purchases?from=2026-08-01&to=2026-08-31&status=pending')
    assert r.status_code == 200
    d = r.get_json()
    assert d['range']['from'] == '2026-08-01'
    assert d['filters']['status'] == 'pending'
    qs = _main_queries(conns)
    assert qs
    sql, params = qs[0]
    assert 'wp.status = %s' in sql
    assert '2026-08-01' in [str(p) for p in params]


def test_status_invalid_jadi_all(env, monkeypatch):
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client)
    r = client.get('/api/water/purchases?status=DROP TABLE')
    assert r.status_code == 200
    assert r.get_json()['filters']['status'] == 'all'


def test_q_mencari_display_ob_brand(env, monkeypatch):
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client)
    r = client.get('/api/water/purchases?q=AQUA')
    assert r.status_code == 200
    qs = _main_queries(conns)
    assert qs
    sql, params = qs[0]
    assert 'EXISTS' in sql and 'wpi.brand LIKE %s' in sql
    assert 'wp.display_id LIKE %s' in sql
    assert '%AQUA%' in [str(p) for p in params]


def test_ob_ter_scope_ke_namanya(env, monkeypatch):
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client, role='ob', name='Edwin')
    r = client.get('/api/water/purchases')
    assert r.status_code == 200
    qs = _main_queries(conns)
    assert qs
    sql, params = qs[0]
    assert 'wp.ob_name = %s' in sql
    assert 'Edwin' in [str(p) for p in params]
    assert 'LIMIT 200' in sql


def test_tanpa_parameter_sql_injection_tidak_terjadi(env, monkeypatch):
    """Nilai filter tidak boleh masuk via f-string — hanya via %s."""
    client, conns = env
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conns.append(FakeConn({})) or conns[-1])
    _login(client)
    evil = "2026-09-01' OR '1'='1"
    r = client.get(f'/api/water/purchases?from={evil}')
    assert r.status_code == 200  # tanggal invalid → fallback default, bukan error SQL
    qs = _main_queries(conns)
    assert qs
    sql, _ = qs[0]
    assert "'1'='1" not in sql  # tidak pernah masuk ke string SQL
