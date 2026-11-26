"""Regresi tabel linimasa event rekrutmen (Rilis C — Task C1).

Tabel `recruitment_events` ada di DB master, idempoten, dan DDL-nya
tercermin di init.sql (sumber kebenaran drift check CI) serta dipanggil
saat startup tepat setelah ensure_recruitment_schema().
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _FakeCursor:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.cursors = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        cur = _FakeCursor()
        self.cursors.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_membuat_tabel_event_dengan_kunci_idempoten():
    from modules.recruitment_events_schema import ensure_recruitment_events_schema
    conn = _FakeConn()
    assert ensure_recruitment_events_schema(conn) is True
    sql = ' '.join(conn.cursors[-1].statements)
    assert 'CREATE TABLE IF NOT EXISTS recruitment_events' in sql
    assert ('UNIQUE KEY uq_re_event '
            '(source_module, branch_code, source_id, event_type)') in sql


def test_kolom_dan_index_timeline_lengkap():
    from modules.recruitment_events_schema import ensure_recruitment_events_schema
    conn = _FakeConn()
    assert ensure_recruitment_events_schema(conn) is True
    sql = ' '.join(conn.cursors[-1].statements)
    for column in ('case_id', 'nik', 'event_type', 'event_at', 'branch_code',
                   'actor_role', 'actor_name', 'source_module', 'source_id',
                   'note', 'metadata_json', 'created_at'):
        assert column in sql, f'kolom {column} hilang dari DDL event'
    assert 'KEY idx_re_case_event (case_id, event_at)' in sql
    assert 'KEY idx_re_nik_event (nik, event_at)' in sql
    assert 'KEY idx_re_branch_event (branch_code, event_at)' in sql


def test_koneksi_injected_tidak_ditutup():
    from modules.recruitment_events_schema import ensure_recruitment_events_schema
    conn = _FakeConn()
    assert ensure_recruitment_events_schema(conn) is True
    assert conn.closed is False


def test_ddl_identik_di_init_sql():
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    match = re.search(
        r'CREATE TABLE IF NOT EXISTS recruitment_events\s*\((.*?)\n\)[^;]*;',
        sql, re.I | re.S)
    assert match, 'recruitment_events hilang dari init.sql'
    body = match.group(1)
    for column in ('case_id', 'nik', 'event_type', 'event_at', 'branch_code',
                   'actor_role', 'actor_name', 'source_module', 'source_id',
                   'note', 'metadata_json', 'created_at'):
        assert re.search(rf'^\s*{column}\s+', body, re.I | re.M), \
            f'recruitment_events.{column} hilang dari init.sql'
    assert ('UNIQUE KEY uq_re_event '
            '(source_module, branch_code, source_id, event_type)') in body
    assert 'KEY idx_re_case_event (case_id, event_at)' in body
    assert 'KEY idx_re_nik_event (nik, event_at)' in body
    assert 'KEY idx_re_branch_event (branch_code, event_at)' in body


def test_startup_retry_lima_kali_setelah_recruitment_schema():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    idx_import = app.index(
        'from modules.recruitment_events_schema import '
        'ensure_recruitment_events_schema')
    block = app[idx_import:idx_import + 400]
    assert 'for _attempt in range(5):' in block
    assert 'if ensure_recruitment_events_schema():' in block
    assert 'ensure_applicant_nik_schema_all()' in app
