import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split())
        m = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', text, re.I)
        if m:
            self.conn.created.append(m.group(1).lower())
        if text.upper().startswith('SELECT COLUMN_NAME'):
            self.conn.queried_columns = True
        if text.upper().startswith('ALTER TABLE RECRUITMENT_CASES'):
            self.conn.alters.append(text)
        if 'INSERT IGNORE INTO TKD_SETTINGS' in text.upper():
            self.conn.seeded_settings = True
    def fetchall(self):
        return [{'COLUMN_NAME': c} for c in self.conn.existing_columns]
    def fetchone(self):
        return None
    def close(self):
        pass

class _FakeConn:
    def __init__(self, existing_columns=()):
        self.created, self.alters = [], []
        self.existing_columns = set(existing_columns)
        self.seeded_settings = False
        self.queried_columns = False
        self.commits = 0
    def cursor(self, dictionary=False):
        return _FakeCursor(self)
    def commit(self):
        self.commits += 1
    def close(self):
        pass

def test_membuat_empat_tabel_dan_seed_settings():
    from modules.tkd_schema import ensure_tkd_schema, TKD_TABLES
    conn = _FakeConn()
    assert ensure_tkd_schema(conn) is True
    assert set(TKD_TABLES) <= set(conn.created)
    assert conn.seeded_settings is True

def test_menambah_tujuh_kolom_skor_bila_belum_ada():
    from modules.tkd_schema import ensure_tkd_schema
    conn = _FakeConn()
    assert ensure_tkd_schema(conn) is True
    assert len(conn.alters) == 7

def test_idempoten_tidak_alter_kolom_yang_sudah_ada():
    from modules.tkd_schema import ensure_tkd_schema, CASE_SCORE_COLUMNS
    conn = _FakeConn(existing_columns=[c for c, _ in CASE_SCORE_COLUMNS])
    assert ensure_tkd_schema(conn) is True
    assert conn.alters == []

def test_init_sql_memuat_tabel_dan_kolom_untuk_drift_check():
    from scripts.check_schema_drift import parse_init_sql
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    parsed = parse_init_sql(sql)
    for table in ('tkd_questions', 'tkd_settings', 'tkd_attempts', 'tkd_attempt_items'):
        assert table in parsed
    assert {'tkd_score', 'tkd_score_source', 'tkd_score_note',
            'tkd_score_updated_by', 'tkd_score_updated_at',
            'tkd_best_attempt_id', 'tkd_passed'} <= set(parsed['recruitment_cases'])

def test_startup_memanggil_setelah_recruitment():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'from modules.tkd_schema import ensure_tkd_schema' in app
    assert app.index('ensure_tkd_schema()') > app.index('ensure_recruitment_schema()')
