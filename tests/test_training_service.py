"""Service absensi training portal: identitas, status hari, dan pencatatan.

Fake cursor meniru query baca (recruitment_cases, training_attendance,
cv_online_submissions, applicants) dan menyimpan efek tulis agar tes bisa
memastikan gating, idempotensi, dan penautan Pelamar.
"""
import re
from datetime import date, datetime

import pytest

NIK = '3509190102960003'
DOB = '1996-02-01'
CASE = 'RC-4f91d973d9b2'
NAMA = 'Bili Darnanto Susilo'
HP = '085334398681'


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.lastrowid = 0

    def execute(self, sql, params=None):
        q = ' '.join(str(sql).upper().split())
        self.conn.statements.append(q)
        params = tuple(params or ())
        self._rows = []
        if 'FROM RECRUITMENT_CASES' in q:
            row = next((r for r in self.conn.cases
                        if str(r['nik']) == str(params[0])), None)
            self._rows = [row] if row else []
        elif 'FROM TRAINING_ATTENDANCE' in q:
            case_id, branch = params[0], params[1]
            self._rows = [r for r in self.conn.attendance
                          if r['case_id'] == case_id
                          and r['branch_code'] == branch]
        elif 'FROM CV_ONLINE_SUBMISSIONS' in q:
            row = next((r for r in self.conn.cv
                        if str(r['nik']) == str(params[0])), None)
            self._rows = [row] if row else []
        elif 'FROM APPLICANTS' in q:
            if 'WHERE ID=' in q:
                row = next((r for r in self.conn.applicants
                            if int(r['id']) == int(params[0])), None)
                self._rows = [row] if row else []
            else:
                name = str(params[0]).upper()
                self._rows = [r for r in self.conn.applicants
                              if str(r['nama_lengkap']).strip().upper() == name]
        elif 'INSERT INTO TRAINING_ATTENDANCE' in q:
            (case_id, nik, branch, day, nama, attended_at,
             applicant_id, link_status, ip, ua) = params
            row = next((r for r in self.conn.attendance
                        if r['case_id'] == case_id
                        and r['branch_code'] == branch
                        and int(r['day']) == int(day)), None)
            if row:
                row.update(attended_at=attended_at, applicant_id=applicant_id,
                           link_status=link_status, ip=ip, user_agent=ua)
            else:
                self.conn.attendance.append({
                    'case_id': case_id, 'nik': nik, 'branch_code': branch,
                    'day': int(day), 'nama': nama, 'attended_at': attended_at,
                    'applicant_id': applicant_id, 'link_status': link_status,
                    'ip': ip, 'user_agent': ua})
        elif 'INSERT INTO APPLICANT_ATTENDANCE' in q:
            applicant_id, stage, attended_at, marked_by, note = params
            self.conn.applicant_attendance.append({
                'applicant_id': applicant_id, 'stage': stage,
                'attended_at': attended_at, 'marked_by': marked_by,
                'note': note})
        elif 'INSERT INTO RECRUITMENT_STEPS' in q:
            self.conn.steps.append(params)
        elif 'UPDATE APPLICANTS SET STATUS' in q:
            self.conn.status_updates.append((params[0], params[1]))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cases=None, attendance=None, cv=None, applicants=None):
        self.cases = cases if cases is not None else [
            {'nik': NIK, 'case_id': CASE, 'nama': NAMA,
             'tanggal_lahir': date(1996, 2, 1)}]
        self.attendance = attendance or []
        self.cv = cv if cv is not None else [
            {'nik': NIK, 'nama': NAMA, 'no_hp_norm': HP}]
        self.applicants = applicants or []
        self.applicant_attendance = []
        self.steps = []
        self.status_updates = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _writes(conn):
    return [s for s in conn.statements
            if s.startswith(('INSERT', 'UPDATE', 'DELETE'))]


def _pelamar(pid=77, nama=NAMA, hp=HP, status='interview'):
    return {'id': pid, 'nama_lengkap': nama, 'no_hp': hp, 'status': status}


def test_nik_unknown_selalu_not_found():
    from modules.training_service import attendance_status
    assert attendance_status(NIK, DOB, 'SBY', conn=_FakeConn(cases=[]))['error'] == 'not_found'


def test_tanggal_lahir_beda_selalu_not_found():
    from modules.training_service import attendance_status
    conn = _FakeConn()
    assert attendance_status(NIK, '1990-01-01', 'SBY', conn=conn)['error'] == 'not_found'
    assert _writes(conn) == []


def test_next_day_1_saat_belum_ada_absensi():
    from modules.training_service import attendance_status
    data = attendance_status(NIK, DOB, 'SBY', conn=_FakeConn())
    assert data['ok'] is True
    assert data['nama'] == NAMA
    assert data['next_day'] == 1
    assert data['days'] == {1: None, 2: None}


def test_next_day_2_setelah_hari_1():
    from modules.training_service import attendance_status
    conn = _FakeConn(attendance=[{
        'case_id': CASE, 'branch_code': 'SBY', 'day': 1,
        'attended_at': datetime(2026, 11, 25, 9, 12),
        'link_status': 'unlinked'}])
    data = attendance_status(NIK, DOB, 'SBY', conn=conn)
    assert data['next_day'] == 2
    assert data['days'][1]['attended_at'] == '2026-11-25 09:12:00'
    assert data['days'][2] is None


def test_next_day_none_setelah_dua_hari():
    from modules.training_service import attendance_status
    conn = _FakeConn(attendance=[
        {'case_id': CASE, 'branch_code': 'SBY', 'day': 1,
         'attended_at': datetime(2026, 11, 25, 9, 0), 'link_status': 'linked'},
        {'case_id': CASE, 'branch_code': 'SBY', 'day': 2,
         'attended_at': datetime(2026, 11, 26, 9, 0), 'link_status': 'linked'},
    ])
    assert attendance_status(NIK, DOB, 'SBY', conn=conn)['next_day'] is None


def test_absensi_cabang_lain_tidak_dihitung():
    from modules.training_service import attendance_status
    conn = _FakeConn(attendance=[{
        'case_id': CASE, 'branch_code': 'BDG', 'day': 1,
        'attended_at': datetime(2026, 11, 25, 9, 0), 'link_status': 'linked'}])
    assert attendance_status(NIK, DOB, 'SBY', conn=conn)['next_day'] == 1


# ------------------------------------------------------------------
# Pencatatan
# ------------------------------------------------------------------

def test_hari_tidak_valid_ditolak_tanpa_tulis():
    from modules.training_service import record_attendance
    conn = _FakeConn()
    assert record_attendance(NIK, DOB, 'SBY', 3, conn=conn)['error'] == 'invalid_day'
    assert _writes(conn) == []


def test_hari_2_ditolak_sebelum_hari_1():
    from modules.training_service import record_attendance
    conn = _FakeConn()
    assert record_attendance(NIK, DOB, 'SBY', 2, conn=conn)['error'] == 'day2_locked'
    assert _writes(conn) == []


def test_submit_ganda_idempoten():
    from modules.training_service import record_attendance
    conn = _FakeConn()
    first = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    second = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert first['ok'] and second['ok']
    assert len(conn.attendance) == 1
    assert conn.attendance[0]['attended_at'].strftime('%Y-%m-%d %H:%M:%S') \
        == second['days'][1]['attended_at']


def test_nama_sama_hp_beda_tidak_tertaut():
    from modules.training_service import record_attendance
    conn = _FakeConn(applicants=[_pelamar(hp='081111111111')])
    data = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert data['link_status'] == 'unlinked'
    assert data['applicant_id'] is None
    assert conn.applicant_attendance == []
    assert conn.status_updates == []


def test_dua_kandidat_jadi_ambiguous():
    from modules.training_service import record_attendance
    conn = _FakeConn(applicants=[_pelamar(77), _pelamar(78)])
    data = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert data['link_status'] == 'ambiguous'
    assert data['applicant_id'] is None
    assert conn.applicant_attendance == []


def test_tertaut_mengisi_attendance_dan_menaikkan_status():
    from modules.training_service import record_attendance
    conn = _FakeConn(applicants=[_pelamar(77)])
    data = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert data['link_status'] == 'linked'
    assert data['applicant_id'] == 77
    assert conn.applicant_attendance[0]['stage'] == 'training_1'
    assert conn.applicant_attendance[0]['marked_by'] == 'Portal Training'
    assert conn.status_updates == [('training_1', 77)]


def test_hari_2_mengisi_training_2():
    from modules.training_service import record_attendance
    conn = _FakeConn(applicants=[_pelamar(77, status='training_1')],
                     attendance=[{'case_id': CASE, 'branch_code': 'SBY',
                                  'day': 1,
                                  'attended_at': datetime(2026, 11, 25, 9, 0),
                                  'link_status': 'linked'}])
    data = record_attendance(NIK, DOB, 'SBY', 2, conn=conn)
    assert data['ok'] is True
    assert conn.applicant_attendance[-1]['stage'] == 'training_2'
    assert conn.status_updates == [('training_2', 77)]


def test_status_terminal_tidak_diubah():
    from modules.training_service import record_attendance
    conn = _FakeConn(applicants=[_pelamar(77, status='lulus')])
    data = record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert data['link_status'] == 'unlinked'
    assert conn.applicant_attendance == []
    assert conn.status_updates == []


def test_langkah_training_pending_lalu_selesai():
    from modules.training_service import record_attendance
    conn = _FakeConn()
    record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    day1 = [s for s in conn.statements if 'INSERT INTO RECRUITMENT_STEPS' in s]
    assert day1
    conn.attendance[0]['day'] = 1
    record_attendance(NIK, DOB, 'SBY', 2, conn=conn)
    assert [row[1] for row in conn.steps] == ['PENDING', 'SELESAI']


def test_submit_ulang_hari_1_tidak_menurunkan_langkah_selesai():
    from modules.training_service import record_attendance
    conn = _FakeConn()
    record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    record_attendance(NIK, DOB, 'SBY', 2, conn=conn)
    record_attendance(NIK, DOB, 'SBY', 1, conn=conn)
    assert conn.steps[-1][1] == 'SELESAI'
