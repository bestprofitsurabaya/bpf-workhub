"""Skema master karyawan (Rilis D — D1): aditif dan idempoten."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(' '.join(str(sql).upper().split()))

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.closed = False

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        pass

    def close(self):
        self.closed = True


def _conn(cur):
    class C:
        def cursor(self, dictionary=False):
            return cur
        def commit(self):
            pass
        def close(self):
            pass
    return C()


def test_membuat_tabel_employees_dan_event_absensi():
    from modules.employee_schema import ensure_employee_schema
    cur = _Cursor(_Conn())
    assert ensure_employee_schema(_conn(cur)) is True
    sql = ' '.join(cur.statements).upper()
    assert 'CREATE TABLE IF NOT EXISTS EMPLOYEES' in sql
    assert 'UNIQUE KEY UQ_EMP_NIK (NIK)' in sql
    assert 'UNIQUE KEY UQ_EMP_SOURCE (SOURCE, SOURCE_UID)' in sql
    assert 'CREATE TABLE IF NOT EXISTS EMPLOYEE_ATTENDANCE_EVENTS' in sql
    assert "ENUM('OUT','IN')" in sql
    assert 'CREATE TABLE IF NOT EXISTS EMPLOYEE_COUNTERS' in sql


def test_koneksi_none_mengembalikan_false(monkeypatch):
    import modules.employee_schema as es
    monkeypatch.setattr(es, 'get_master_connection', lambda: None)
    assert es.ensure_employee_schema(None) is False


def test_init_sql_memuat_ddl_yang_sama():
    source = (ROOT / 'init.sql').read_text(encoding='utf-8')
    ddl = (ROOT / 'modules' / 'employee_schema.py').read_text(encoding='utf-8')
    for table in ('employees', 'employee_attendance_events', 'employee_counters'):
        assert f'CREATE TABLE IF NOT EXISTS {table}' in source
        assert f'CREATE TABLE IF NOT EXISTS {table}' in ddl
    assert 'uq_emp_nik' in source
    assert 'uq_emp_source' in source
