"""Regresi skema NIK pelamar (Rilis C — Task C1).

Yang diuji (tanpa DB nyata):
1. Helper menambah 4 kolom NIK + unique/index di `applicants` DB cabang.
2. DDL idempoten: pemanggilan kedua tidak mengulang ALTER.
3. `ensure_applicant_nik_schema_all` memanggil setiap koneksi cabang dan
   mengembalikan status per cabang; satu cabang gagal tidak menghentikan
   cabang lain.
4. DDL tercermin di init.sql dan startup memanggil helper setelah master siap.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.statements = []
        self._last = None
        self._last_sql = ''

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self._last_sql = ' '.join(sql.split())
        low = self._last_sql.lower()
        if 'information_schema.columns' in low:
            name = str((params or (None, None))[1] or '').lower()
            self._last = (1 if name in self.conn.columns else 0,)
            return
        if 'information_schema.statistics' in low:
            name = str((params or (None, None))[1] or '').lower()
            self._last = (1 if name in self.conn.indexes else 0,)
            return
        if 'from branches' in low:
            self._last = list(self.conn.branch_rows)
            return
        self._last = None
        match = re.search(r'add column (\w+)', low)
        if match:
            self.conn.columns.add(match.group(1))
        match = re.search(r'add (?:unique )?key (\w+)', low)
        if match:
            self.conn.indexes.add(match.group(1))

    def fetchone(self):
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return self._last

    def fetchall(self):
        return self._last if isinstance(self._last, list) else []

    def close(self):
        pass


class _FakeConn:
    def __init__(self, branch_rows=None, cursor_cls=_FakeCursor):
        self.columns = set()
        self.indexes = set()
        self.branch_rows = branch_rows or []
        self.cursor_cls = cursor_cls
        self.cursors = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        cur = self.cursor_cls(self)
        self.cursors.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class _BrokenIndexCursor(_FakeCursor):
    """Gagal saat membuat unique index dengan pesan berisi NIK lengkap."""

    def execute(self, sql, params=None):
        super().execute(sql, params)
        low = ' '.join(sql.split()).lower()
        if 'add unique key' in low:
            raise RuntimeError(
                "Duplicate entry '3573010101990001' for key 'uq_applicants_nik'")


def _table_body(sql, table):
    match = re.search(
        r'CREATE TABLE IF NOT EXISTS ' + table + r'\s*\((.*?)\n\)[^;]*;',
        sql, re.I | re.S)
    assert match, f'tabel {table} hilang dari init.sql'
    return match.group(1)


def test_menambah_kolom_nik_dan_index():
    from modules.applicant_nik_schema import ensure_applicant_nik_schema
    conn = _FakeConn()
    assert ensure_applicant_nik_schema(conn) is True
    sql = ' '.join(conn.cursors[-1].statements)
    assert 'ADD COLUMN nik CHAR(16) NULL' in sql
    assert 'ADD COLUMN nik_source VARCHAR(20)' in sql
    assert 'ADD COLUMN linked_at DATETIME NULL' in sql
    assert 'ADD COLUMN link_status ENUM' in sql
    assert 'UNIQUE KEY uq_applicants_nik (nik)' in sql
    assert 'KEY idx_applicants_link_status (link_status)' in sql


def test_ddl_idempoten_tidak_mengulang_alter():
    from modules.applicant_nik_schema import ensure_applicant_nik_schema
    conn = _FakeConn()
    assert ensure_applicant_nik_schema(conn) is True
    assert ensure_applicant_nik_schema(conn) is True
    second = ' '.join(conn.cursors[-1].statements)
    assert 'ALTER TABLE' not in second.upper()
    assert {'nik', 'nik_source', 'linked_at', 'link_status'} <= conn.columns
    assert {'uq_applicants_nik', 'idx_applicants_link_status'} <= conn.indexes


def test_koneksi_none_mengembalikan_false():
    from modules.applicant_nik_schema import ensure_applicant_nik_schema
    assert ensure_applicant_nik_schema(None) is False


def test_koneksi_injected_tidak_ditutup():
    from modules.applicant_nik_schema import ensure_applicant_nik_schema
    conn = _FakeConn()
    assert ensure_applicant_nik_schema(conn) is True
    assert conn.closed is False


def test_error_ddl_tidak_mencetak_nik_lengkap(capsys):
    from modules.applicant_nik_schema import ensure_applicant_nik_schema
    conn = _FakeConn(cursor_cls=_BrokenIndexCursor)
    assert ensure_applicant_nik_schema(conn) is False
    out = capsys.readouterr().out
    assert '3573010101990001' not in out
    assert '****0001' in out


def test_semua_cabang_dipanggil_dan_hasil_per_cabang(monkeypatch):
    from modules import applicant_nik_schema as schema
    conns = {'SBY': _FakeConn(), 'JKT': _FakeConn()}
    calls = []

    def fake_get(branch_code=None, master=False):
        calls.append(branch_code)
        return conns[branch_code]

    monkeypatch.setattr(schema, 'get_db_connection', fake_get)
    result = schema.ensure_applicant_nik_schema_all(['SBY', 'JKT'])
    assert result == {'SBY': True, 'JKT': True}
    assert calls == ['SBY', 'JKT']
    assert all(conn.closed for conn in conns.values())


def test_satu_cabang_gagal_tidak_menghentikan_cabang_lain(monkeypatch, capsys):
    from modules import applicant_nik_schema as schema
    conns = {'JKT': _FakeConn()}
    calls = []

    def fake_get(branch_code=None, master=False):
        calls.append(branch_code)
        if branch_code == 'SBY':
            raise RuntimeError('db cabang mati')
        return conns[branch_code]

    monkeypatch.setattr(schema, 'get_db_connection', fake_get)
    result = schema.ensure_applicant_nik_schema_all(['SBY', 'JKT'])
    assert result == {'SBY': False, 'JKT': True}
    assert calls == ['SBY', 'JKT']
    assert 'SBY' in capsys.readouterr().out


def test_daftar_cabang_aktif_dibaca_dari_master(monkeypatch):
    from modules import applicant_nik_schema as schema
    master = _FakeConn(branch_rows=[('sby',), ('JKT',)])
    conns = {'SBY': _FakeConn(), 'JKT': _FakeConn()}

    monkeypatch.setattr(schema, 'get_master_connection', lambda: master)
    monkeypatch.setattr(schema, 'get_db_connection',
                        lambda branch_code=None, master=False: conns[branch_code])
    result = schema.ensure_applicant_nik_schema_all()
    assert result == {'SBY': True, 'JKT': True}
    assert 'SELECT code FROM branches WHERE is_active=1' in ' '.join(
        master.cursors[0].statements)
    assert master.closed is True


def test_ddl_tercermin_di_init_sql():
    sql = (ROOT / 'init.sql').read_text(encoding='utf-8')
    body = _table_body(sql, 'applicants')
    for column in ('nik', 'nik_source', 'linked_at', 'link_status'):
        assert re.search(rf'^\s*{column}\s+', body, re.I | re.M), \
            f'applicants.{column} hilang dari init.sql'
    assert re.search(r'UNIQUE KEY uq_applicants_nik \(nik\)', body, re.I)
    assert re.search(r'KEY idx_applicants_link_status \(link_status\)', body, re.I)


def test_startup_memanggil_helper_setelah_master_siap():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert ('from modules.applicant_nik_schema import '
            'ensure_applicant_nik_schema_all') in app
    idx_master = app.index('ensure_recruitment_schema()')
    idx_nik = app.index('ensure_applicant_nik_schema_all()', idx_master)
    assert idx_nik > idx_master
