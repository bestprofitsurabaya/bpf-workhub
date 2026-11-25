"""Skema bukti absensi training portal (2 hari).

Tabel `training_attendance` harus idempoten, tercermin di `init.sql` (sumber
drift check CI), dan dipanggil saat startup.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.statements.append(' '.join(str(sql).split()))
        match = re.search(
            r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)', sql, re.I)
        if match:
            self.conn.created.append(match.group(1).lower())

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.created = []
        self.statements = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def fake_conn():
    return _FakeConn()


def test_ensure_membuat_tabel_training_attendance(fake_conn):
    from modules.training_schema import ensure_training_attendance_schema
    assert ensure_training_attendance_schema(fake_conn) is True
    assert 'training_attendance' in fake_conn.created


def test_ddl_unik_per_kasus_cabang_hari(fake_conn):
    from modules.training_schema import ensure_training_attendance_schema
    ensure_training_attendance_schema(fake_conn)
    ddl = ' '.join(fake_conn.statements)
    assert 'UNIQUE KEY uq_ta_case_branch_day (case_id, branch_code, day)' in ddl
    assert 'day TINYINT' in ddl
    assert "ENUM('linked','unlinked','ambiguous')" in ddl


def test_ddl_juga_ada_di_init_sql():
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    assert re.search(
        r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+training_attendance\b', sql, re.I), \
        'training_attendance hilang dari init.sql'


def test_startup_memanggil_ensure_training():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'ensure_training_attendance_schema' in app
