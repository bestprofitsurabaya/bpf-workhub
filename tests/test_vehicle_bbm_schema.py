"""Regresi v2.131.4 — tabel vehicle_bbm_allowed hilang memblokir klaim BBM.

Insiden 20 Nov 2026: tabel hilang dari DB master (SBY+MALANG) setelah
rekonsiliasi. Semua klaim BBM driver ditolak 400 selama 3 hari.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers, vehicle_bbm_schema  # noqa: E402


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.executed.append(sql.strip())
        if sql.strip().upper().startswith('SELECT COUNT'):
            self._row = (self.conn.count,)
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, count=0):
        self.executed = []
        self.count = count
        self.committed = False
        self.rolled_back = False

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_ddl_tanpa_foreign_key_dan_seed_hanya_saat_kosong():
    conn = _FakeConn(count=0)
    assert vehicle_bbm_schema.ensure_vehicle_bbm_schema(conn) is True

    sql = '\n'.join(conn.executed).upper()
    assert 'CREATE TABLE IF NOT EXISTS VEHICLE_BBM_ALLOWED' in sql
    # Master punya vehicles per-nopol: vehicle_type tidak unik, jadi FK gagal.
    assert 'FOREIGN KEY' not in sql
    assert 'INSERT IGNORE INTO VEHICLE_BBM_ALLOWED' in sql
    assert conn.committed


def test_seed_dilewati_saat_tabel_sudah_berisi():
    conn = _FakeConn(count=4)
    assert vehicle_bbm_schema.ensure_vehicle_bbm_schema(conn) is True

    sql = '\n'.join(conn.executed).upper()
    assert 'CREATE TABLE IF NOT EXISTS VEHICLE_BBM_ALLOWED' in sql
    assert 'INSERT IGNORE' not in sql
    assert conn.committed


class _MissingTableError(Exception):
    errno = 1146


class _ValidateCursor:
    def __init__(self, fail=False, row=None):
        self.fail = fail
        self.row = row
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail:
            self.fail = False
            raise _MissingTableError(
                "1146 (42S02): Table 'bpf_asset_system.vehicle_bbm_allowed' doesn't exist")

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class _ValidateConn:
    def __init__(self):
        self._cursors = [
            _ValidateCursor(fail=True),
            _ValidateCursor(row={
                'min_km_per_liter': 5, 'max_km_per_liter': 18,
                'warning_km_per_liter': 10.5, 'good_km_per_liter': 12.5,
            }),
        ]
        self.closed = False

    def cursor(self, dictionary=False):
        return self._cursors.pop(0)

    def close(self):
        self.closed = True


def test_validator_membuat_tabel_lalu_mengulang_query(monkeypatch):
    conn = _ValidateConn()
    calls = {'ensure': 0}

    def fake_ensure(c=None):
        calls['ensure'] += 1
        assert c is conn
        return True

    monkeypatch.setattr('modules.config.get_db_connection', lambda *a, **k: conn)
    monkeypatch.setattr(vehicle_bbm_schema, 'ensure_vehicle_bbm_schema', fake_ensure)

    result = helpers.validate_bbm_for_vehicle('AVANZA', 'PERTALITE')

    assert result['valid'] is True
    assert result['limits']['good'] == 12.5
    assert calls['ensure'] == 1
    assert conn.closed is True


def test_validator_tetap_menolak_bila_perbaikan_gagal(monkeypatch):
    conn = _ValidateConn()
    monkeypatch.setattr('modules.config.get_db_connection', lambda *a, **k: conn)
    monkeypatch.setattr(vehicle_bbm_schema, 'ensure_vehicle_bbm_schema', lambda c=None: False)

    result = helpers.validate_bbm_for_vehicle('AVANZA', 'PERTALITE')

    assert result['valid'] is False
    assert 'vehicle_bbm_allowed' in result['error']
    assert conn.closed is True
