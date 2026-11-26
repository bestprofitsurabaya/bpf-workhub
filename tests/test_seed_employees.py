"""Seed master karyawan dari FirstWork/unitedw dan In-Out lama (Rilis D — D6)."""
from scripts.seed_employees import seed_employees

NIK = '3573010101900001'
FW_ROW = {'id': 1, 'nik': NIK, 'nama': 'Budi Santoso', 'no_hp': '08123456789',
          'pendidikan': 'S1', 'source': 'form', 'source_uid': 'form-1',
          'submitted_at': '2026-11-25 09:00:00', 'branch_code': 'SBY',
          'tempat_lahir': 'Surabaya', 'tanggal_lahir': '1990-01-01',
          'jenis_kelamin': 'Pria'}


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.lastrowid = 0

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).upper().split())
        p = tuple(params or ())
        self.rows = []
        if 'FROM EMPLOYEES' in text and 'NIK=%S' in text:
            self.rows = [r for r in self.conn.employees if r.get('nik') == p[0]]
        elif 'FROM EMPLOYEES' in text and 'SOURCE_UID=%S' in text:
            self.rows = [r for r in self.conn.employees
                         if r.get('source_uid') == p[0]]
        elif text.startswith('INSERT INTO EMPLOYEES'):
            cols = ['employee_no', 'nik', 'nama', 'nama_norm', 'jabatan',
                    'branch_code', 'tanggal_masuk', 'source', 'source_uid',
                    'case_id', 'needs_nik', 'is_active', 'no_hp',
                    'pendidikan_terakhir', 'tempat_lahir', 'tanggal_lahir',
                    'jenis_kelamin']
            row = dict(zip(cols, p))
            row['id'] = len(self.conn.employees) + 1
            self.conn.employees.append(row)
            self.lastrowid = row['id']
        elif text.startswith('UPDATE EMPLOYEES'):
            self.conn.updates.append((text, p))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.employees = []
        self.updates = []
        self.commits = 0

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def test_seed_mengisi_business_consultant_dari_firstwork():
    conn = _Conn()
    result = seed_employees(conn, [FW_ROW], [], commit=True)
    assert result['inserted'] == 1
    row = conn.employees[0]
    assert row['jabatan'] == 'Business Consultant'
    assert row['source'] == 'firstwork'
    assert row['is_active'] == 1


def test_seed_mempertahankan_sumber_unitedw():
    conn = _Conn()
    seed_employees(conn, [dict(FW_ROW, id=9, source='unitedw',
                               source_uid='FP-9')], [], commit=True)
    assert conn.employees[0]['source'] == 'unitedw'


def test_seed_ulang_tidak_mengaktifkan_kembali():
    conn = _Conn()
    seed_employees(conn, [FW_ROW], [], commit=True)
    conn.employees[0].update({'is_active': 0, 'deactivation_reason': 'keluar'})
    second = seed_employees(conn, [FW_ROW], [], commit=True)
    assert conn.employees[0]['is_active'] == 0
    assert len(conn.employees) == 1
    assert second['inserted'] == 0


def test_nik_invalid_tetap_impor_dengan_needs_nik():
    conn = _Conn()
    result = seed_employees(conn, [dict(FW_ROW, nik='123')], [], commit=True)
    assert result['needs_nik'] == 1
    assert conn.employees[0]['nik'] is None
    assert conn.employees[0]['source_uid'] == 'fw:1'


def test_inout_legacy_menjadi_staf():
    conn = _Conn()
    seed_employees(conn, [], [{'nama': 'Rina', 'branch_code': 'SBY',
                               'jabatan': 'Staf'}], commit=True)
    assert conn.employees[0]['jabatan'] == 'Staf'
    assert conn.employees[0]['source'] == 'inout_legacy'
