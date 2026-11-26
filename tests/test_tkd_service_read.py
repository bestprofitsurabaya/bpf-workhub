import json
from datetime import date, datetime
import pytest
from modules import tkd_service as svc

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if 'FROM CV_ONLINE_BRANCH_FORMS' in upper:
            self._rows = [r for r in self.conn.tokens
                          if r['form_token'] == params[0] and r['active']]
        elif 'FROM RECRUITMENT_CASES' in upper and 'WHERE NIK=%S' in upper:
            self._rows = [r for r in self.conn.cases if r['nik'] == params[0]]
        elif 'FROM TKD_SETTINGS' in upper:
            self._rows = [self.conn.settings] if self.conn.settings else []
        elif 'FROM TKD_ATTEMPTS' in upper:
            self._rows = list(self.conn.attempts)
        elif 'FROM RECRUITMENT_STEPS' in upper:
            self._rows = list(self.conn.steps)
        elif 'FROM TKD_QUESTIONS' in upper:
            self._rows = list(self.conn.questions)
        elif 'FROM TKD_ATTEMPT_ITEMS' in upper:
            self._rows = list(self.conn.items)
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []
        self.tokens = [{'form_token': 'tok-sby', 'branch_code': 'SBY', 'active': 1}]
        self.cases = [
            {'case_id': 'RC-1', 'nik': '3573010101990001', 'nama': 'Andi',
             'tanggal_lahir': date(1999, 1, 1), 'first_branch': 'SBY',
             'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None},
            {'case_id': 'RC-2', 'nik': '3573014101990002', 'nama': 'Dian',
             'tanggal_lahir': None, 'first_branch': 'MLG',
             'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None},
        ]
        self.settings = {'id': 1, 'question_count': 20, 'duration_minutes': 25,
                         'pass_score': 70, 'max_attempts': 2, 'active': 0,
                         'quota': json.dumps({'REGULASI': 7, 'PERUSAHAAN': 4,
                                              'PRODUK': 6, 'HITUNG': 3})}
        self.attempts, self.steps, self.questions, self.items = [], [], [], []
    def cursor(self, dictionary=False): return _Cursor(self)

def test_token_aktif_dan_tidak_aktif():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.resolve_branch_token(cur, 'tok-sby') == 'SBY'
    assert svc.resolve_branch_token(cur, 'tok-salah') == ''
    conn.tokens[0]['active'] = 0
    assert svc.resolve_branch_token(cur, 'tok-sby') == ''

def test_load_settings_parse_kuota_dan_default():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    s = svc.load_settings(cur)
    assert s['quota'] == {'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 3}
    conn.settings = None
    s = svc.load_settings(cur)
    assert s['question_count'] == 20 and s['pass_score'] == 70

def test_identitas_ditekan_berdasarkan_nik_saja():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.verify_identity(cur, '3573010101990001')['case_id'] == 'RC-1'

def test_identitas_null_memakai_turunan_nik():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    # NIK perempuan: 41 -> 01, YY 99 -> 1999
    assert svc.verify_identity(cur, '3573014101990002')['case_id'] == 'RC-2'

def test_identitas_nik_tidak_dikenal_atau_nik_invalid():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    assert svc.verify_identity(cur, '3573010101999999') is None
    assert svc.verify_identity(cur, '123') is None


# Tambahan cakupan kontrak Task 5 (pembacaan attempt & helper konversi).

def test_fetch_case_by_nik_mengunci_baris_bila_diminta():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    row = svc.fetch_case_by_nik(cur, '3573010101990001')
    assert row['case_id'] == 'RC-1'
    assert 'FOR UPDATE' not in conn.statements[-1][0]
    svc.fetch_case_by_nik(cur, '3573010101990001', for_update=True)
    assert 'FOR UPDATE' in conn.statements[-1][0]
    assert svc.fetch_case_by_nik(cur, '3573010101999999') is None

def test_helper_konversi_tanggal_dan_angka():
    from decimal import Decimal
    assert svc._as_iso(None) is None
    assert svc._as_iso(date(1999, 1, 1)) == '1999-01-01'
    assert svc._as_iso(datetime(2026, 11, 24, 10, 25)) == '2026-11-24 10:25:00'
    assert svc._as_float(None) is None
    assert svc._as_float(Decimal('70.50')) == 70.5
    assert svc._as_float('1,5') is None
    assert svc._as_float('70.5') == 70.5

def test_pembacaan_attempt_langkah_soal_dan_item():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.attempts = [{'id': 'TKD-1', 'case_id': 'RC-1', 'attempt_no': 1},
                     {'id': 'TKD-2', 'case_id': 'RC-1', 'attempt_no': 2}]
    conn.steps = [{'id': 9, 'step_type': 'TKD', 'status': 'SELESAI'}]
    conn.questions = [{'id': 1, 'code': 'REG-1', 'active': 1}]
    conn.items = [{'id': 1, 'attempt_id': 'TKD-1', 'position': 1},
                  {'id': 2, 'attempt_id': 'TKD-1', 'position': 2}]
    assert [a['id'] for a in svc.fetch_attempts(cur, 'RC-1')] == ['TKD-1', 'TKD-2']
    assert 'ORDER BY ATTEMPT_NO' in conn.statements[-1][0]
    assert svc.fetch_attempt(cur, 'TKD-1')['id'] == 'TKD-1'
    svc.fetch_attempt(cur, 'TKD-1', for_update=True)
    assert 'FOR UPDATE' in conn.statements[-1][0]
    assert [s['id'] for s in svc.fetch_tkd_steps(cur, 'RC-1')] == [9]
    assert [q['id'] for q in svc.fetch_active_questions(cur)] == [1]
    assert 'ORDER BY CATEGORY, SORT_ORDER, ID' in conn.statements[-1][0]
    assert [i['id'] for i in svc.fetch_attempt_items(cur, 'TKD-1')] == [1, 2]
    assert 'ORDER BY POSITION' in conn.statements[-1][0]
