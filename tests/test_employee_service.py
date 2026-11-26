"""Layanan master karyawan (Rilis D — D2)."""
import pytest

NIK = '3573010101900001'


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.lastrowid = 0

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).upper().split())
        p = tuple(params or ())
        self.rows = []
        conn = self.conn
        if 'FROM RECRUITMENT_CASES' in text:
            self.rows = [r for r in conn.cases if str(r.get('case_id')) == str(p[0])]
        elif 'FROM CV_ONLINE_SUBMISSIONS' in text:
            self.rows = [r for r in conn.cv if str(r.get('nik')) == str(p[0])]
        elif 'FROM FIRST_WORK_SUBMISSIONS' in text:
            self.rows = [r for r in conn.fw if str(r.get('nik')) == str(p[0])]
        elif 'FROM EMPLOYEES' in text and 'NIK=%S' in text:
            self.rows = [r for r in conn.employees if r.get('nik') == p[0]]
        elif 'FROM EMPLOYEES' in text and 'ID=%S' in text:
            self.rows = [r for r in conn.employees if r.get('id') == p[0]]
        elif 'FROM EMPLOYEE_COUNTERS' in text:
            self.rows = [{'last_value': conn.counters.get(p[0], 0)}]
        elif text.startswith('SELECT * FROM EMPLOYEE_ATTENDANCE_EVENTS WHERE ID=%S'):
            self.rows = [r for r in conn.attendance
                         if r.get('id') == p[0] and r.get('employee_id') == p[1]]
        elif 'FROM EMPLOYEE_ATTENDANCE_EVENTS' in text:
            rows = [r for r in conn.attendance if r['employee_id'] == p[0]
                    and not r.get('voided_at')]
            self.rows = rows[-1:] if rows else []
        elif text.startswith('UPDATE EMPLOYEE_ATTENDANCE_EVENTS'):
            for row in conn.attendance:
                if row.get('id') == p[-1]:
                    row['voided_at'] = p[0]
                    row['voided_by'] = p[1]
                    row['void_reason'] = p[2]
        elif text.startswith('UPDATE EMPLOYEES'):
            for row in conn.employees:
                if row.get('id') != p[-1]:
                    continue
                if 'IS_ACTIVE=0' in text:
                    row.update(is_active=0, deactivation_reason=p[0],
                               deactivated_by=p[1], deactivated_at=p[2])
                elif 'IS_ACTIVE=1' in text:
                    row.update(is_active=1, deactivation_reason=None,
                               deactivated_by=None, deactivated_at=None)
        elif text.startswith('INSERT INTO EMPLOYEES'):
            row = dict(zip(
                ['employee_no', 'nik', 'nama', 'nama_norm', 'jabatan',
                 'branch_code', 'tanggal_masuk', 'source', 'source_uid',
                 'case_id', 'needs_nik', 'no_hp', 'tanggal_lahir',
                 'jenis_kelamin', 'tempat_lahir', 'pendidikan_terakhir'], p))
            row['id'] = len(conn.employees) + 1
            row['is_active'] = 1
            conn.employees.append(row)
            self.lastrowid = row['id']
        elif text.startswith('INSERT INTO EMPLOYEE_COUNTERS'):
            conn.counters[p[0]] = int(p[1])
        elif text.startswith('INSERT INTO EMPLOYEE_ATTENDANCE_EVENTS'):
            row = dict(zip(
                ['employee_id', 'nik', 'branch_code', 'direction', 'event_at',
                 'actor_username', 'actor_name', 'note', 'source'], p))
            row['id'] = len(conn.attendance) + 1
            row['voided_at'] = None
            conn.attendance.append(row)
            self.lastrowid = row['id']
        elif text.startswith('UPDATE'):
            conn.updates.append((text, p))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.cases = [{'case_id': 'RC-1', 'nik': NIK, 'nama': 'Budi Santoso',
                       'first_branch': 'SBY', 'tanggal_lahir': '1990-01-01',
                       'jenis_kelamin': 'L'}]
        self.cv = [{'nik': NIK, 'nama': 'Budi Santoso', 'no_hp': '08123456789',
                    'tempat_lahir': 'Surabaya', 'tanggal_lahir': '1990-01-01',
                    'jenis_kelamin': 'Pria', 'pendidikan_terakhir': 'S1',
                    'submitted_at': '2026-11-25 09:00:00'}]
        self.fw = [{'nik': NIK, 'registration_no': 'FW-SBY-1',
                    'submitted_at': '2026-11-26 09:00:00'}]
        self.employees = []
        self.attendance = []
        self.counters = {}
        self.updates = []
        self.events = []
        self.commits = 0

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def master(monkeypatch):
    conn = _Conn()
    import modules.employee_service as es
    monkeypatch.setattr(es, 'record_event',
                        lambda case_id, nik, event_type, **kw: (
                            conn.events.append(event_type), True)[1])
    return conn


def test_promosi_mengisi_dari_kasus_cv_dan_firstwork(master):
    from modules.employee_service import promote_to_employee
    result = promote_to_employee('RC-1', conn=master)
    assert result['created'] is True
    row = master.employees[0]
    assert row['nik'] == NIK
    assert row['nama'] == 'Budi Santoso'
    assert row['jabatan'] == 'Business Consultant'
    assert row['no_hp'] == '08123456789'
    assert row['employee_no'].startswith('KRY-SBY-')
    assert 'EMPLOYEE_CREATED' in master.events


def test_promosi_nik_sama_tidak_menduplikasi(master):
    from modules.employee_service import promote_to_employee
    promote_to_employee('RC-1', conn=master)
    result = promote_to_employee('RC-1', conn=master)
    assert result['created'] is False
    assert len(master.employees) == 1


def test_promosi_tanpa_nik_ditolak(master):
    from modules.employee_service import promote_to_employee
    master.cases[0]['nik'] = None
    with pytest.raises(ValueError, match='NIK'):
        promote_to_employee('RC-1', conn=master)


def test_toggle_out_lalu_out_lagi_ditolak(master):
    from modules.employee_service import promote_to_employee, toggle_attendance
    promote_to_employee('RC-1', conn=master)
    toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=master)
    with pytest.raises(ValueError, match='already_out'):
        toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=master)


def test_toggle_mencatat_aktor_dan_waktu(master):
    from modules.employee_service import promote_to_employee, toggle_attendance
    promote_to_employee('RC-1', conn=master)
    result = toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY',
                               note='ke bank', conn=master)
    event = master.attendance[0]
    assert event['direction'] == 'OUT'
    assert event['actor_name'] == 'Rina'
    assert event['note'] == 'ke bank'
    assert result['status'] == 'OUT'


def test_void_koreksi_lalu_arah_baru_diterima(master):
    from modules.employee_service import (promote_to_employee, toggle_attendance,
                                          void_attendance, current_status)
    promote_to_employee('RC-1', conn=master)
    first = toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY', conn=master)
    void_attendance(1, first['event_id'], 'salah tekan', 'ga_hr', conn=master)
    assert current_status(master.cursor(), 1) == 'IN'
    assert toggle_attendance(1, 'OUT', 'resepsionis', 'Rina', 'SBY',
                             conn=master)['status'] == 'OUT'


def test_nonaktif_ambiguous_tanpa_alasan_ditolak(master):
    from modules.employee_service import promote_to_employee, deactivate_employee
    promote_to_employee('RC-1', conn=master)
    with pytest.raises(ValueError, match='alasan'):
        deactivate_employee(1, '', 'ga_hr', conn=master)


def test_deactivate_reactivate(master):
    from modules.employee_service import (promote_to_employee,
                                          deactivate_employee, reactivate_employee)
    promote_to_employee('RC-1', conn=master)
    deactivate_employee(1, 'pindah', 'ga_hr', conn=master)
    assert master.employees[0]['is_active'] == 0
    reactivate_employee(1, 'ga_hr', conn=master)
    assert master.employees[0]['is_active'] == 1
