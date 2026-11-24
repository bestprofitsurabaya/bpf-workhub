"""Regresi skema kasus rekrutmen lintas cabang (Rilis A).

Tabel baru dibuat di DB master dan harus idempoten (CREATE TABLE IF NOT EXISTS).
Selain itu DDL harus tercermin di init.sql (sumber kebenaran drift check CI)
dan dipanggil saat startup tepat setelah ensure_appointments_schema().
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
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


def test_ensure_membuat_tiga_tabel(fake_conn):
    from modules.recruitment_schema import ensure_recruitment_schema
    assert ensure_recruitment_schema(fake_conn) is True
    assert {'recruitment_cases', 'recruitment_steps', 'case_branch_history'} <= set(fake_conn.created)


def test_ddl_juga_ada_di_init_sql():
    """init.sql dipakai checkpoint drift CI — tabel baru wajib ada di sana."""
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    for table in ('recruitment_cases', 'recruitment_steps', 'case_branch_history'):
        assert re.search(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+' + table + r'\b', sql, re.I), \
            f'{table} hilang dari init.sql'


def test_startup_memanggil_ensure_setelah_appointments():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'from modules.recruitment_schema import ensure_recruitment_schema' in app
    idx_appointments = app.index('ensure_appointments_schema()')
    idx_recruitment = app.index('ensure_recruitment_schema()', idx_appointments)
    assert idx_recruitment > idx_appointments


def test_ensure_tidak_menutup_koneksi_yang_diberikan(fake_conn):
    """conn injected tidak boleh ditutup oleh fungsi ensure (pattern modul lain)."""
    from modules.recruitment_schema import ensure_recruitment_schema
    closed = []
    fake_conn.close = lambda: closed.append(True)
    assert ensure_recruitment_schema(fake_conn) is True
    assert closed == []
