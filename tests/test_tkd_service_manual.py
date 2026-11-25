from datetime import datetime
import pytest
from modules import tkd_service as svc

class _Cursor:
    def __init__(self, conn):
        self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [self.conn.case]
        elif 'FROM CASE_BRANCH_HISTORY' in upper:
            self._rows = [{'branch_code': 'MLG'}]
        else:
            self._rows = []
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []
        self.case = {'case_id': 'RC-1', 'first_branch': 'SBY',
                     'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0}
    def cursor(self, dictionary=False): return _Cursor(self)

def test_koreksi_manual_menulis_skor_alasan_dan_status_lulus():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 75, 'Koreksi hasil', 'traineer1', 70)
    assert out['old_score'] == 60 and out['score'] == 75 and out['passed'] is True
    sql = ' '.join(s[0] for s in conn.statements)
    assert "TKD_SCORE_SOURCE='MANUAL'" in sql
    assert 'TKD_SCORE_NOTE=%S' in sql
    assert 'TKD_PASSED=%S' in sql

def test_koreksi_tanpa_baris_tkd_memakai_cabang_terakhir():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 80, 'Tes manual', 'ga_hr1', 70)
    assert out['branch_code'] == 'MLG'
    assert any('INSERT IGNORE INTO RECRUITMENT_STEPS' in s[0] for s in conn.statements)

def test_koreksi_manual_lebih_rendah_tetap_menang():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 50, 'Koreksi turun', 'traineer1', 70)
    assert out['score'] == 50 and out['passed'] is False and out['source'] == 'MANUAL'

def test_koreksi_tidak_mengubah_attempt():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    svc.set_manual_score(cur, 'RC-1', 50, 'Salah input', 'admin1', 70)
    assert not any('UPDATE TKD_ATTEMPTS' in s[0] for s in conn.statements)


# Cakupan tambahan untuk kontrak Task 7 yang tidak ada di contoh tes brief.

class _LiveCursor:
    """Cursor tiruan yang menerapkan UPDATE ke baris yang terpengaruh."""
    def __init__(self, conn):
        self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [self.conn.case] if self.conn.case else []
        elif 'FROM CASE_BRANCH_HISTORY' in upper:
            self._rows = [{'branch_code': 'MLG'}] if self.conn.history else []
        elif 'FROM TKD_ATTEMPTS' in upper:
            self._rows = list(self.conn.attempts)
        elif upper.startswith('UPDATE RECRUITMENT_CASES'):
            self._rows = []
            self.conn.case.update(tkd_score=params[0], tkd_score_source='MANUAL',
                                  tkd_score_note=params[1],
                                  tkd_score_updated_by=params[2], tkd_passed=params[3])
        elif upper.startswith('UPDATE RECRUITMENT_STEPS'):
            self._rows = []
            for step in self.conn.steps:
                if (step['case_id'] == params[-1] and step['step_type'] == 'TKD'
                        and step['status'] != 'DIKECUALIKAN'):
                    step['status'] = ('SELESAI' if "STATUS='SELESAI'" in upper
                                      else 'PENDING')
                    step['completed_at'] = ('NOW()' if 'COMPLETED_AT=NOW()' in upper
                                            else None)
                    step['evidence_type'] = 'manual_score'
                    step['evidence_id'] = ''
                    step['actor'] = params[0]
        else:
            self._rows = []
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def close(self): pass

class _LiveConn:
    def __init__(self):
        self.statements = []
        self.case = {'case_id': 'RC-1', 'nik': '3573010101990001',
                     'first_branch': 'SBY', 'tkd_score': 60,
                     'tkd_score_source': 'AUTO', 'tkd_passed': 0}
        self.history = True
        self.attempts = []
        self.steps = []
    def cursor(self, dictionary=False): return _LiveCursor(self)

@pytest.mark.parametrize('bad', [-1, 101, 'abc', None, True, float('nan')])
def test_koreksi_menolak_skor_invalid_tanpa_menulis(bad):
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    with pytest.raises(ValueError):
        svc.set_manual_score(cur, 'RC-1', bad, 'Koreksi', 'admin1', 70)
    assert conn.statements == []

def test_koreksi_memangkas_alasan_aktor_dan_menulis_audit():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 75, '  Koreksi hasil  ',
                               '  traineer1  ', 70)
    update = next(s for s in conn.statements
                  if s[0].startswith('UPDATE RECRUITMENT_CASES'))
    sql, params = update
    assert params == (75, 'Koreksi hasil', 'traineer1', True, 'RC-1')
    assert "TKD_SCORE_SOURCE='MANUAL'" in sql
    assert 'TKD_SCORE_UPDATED_AT=NOW()' in sql
    assert 'TKD_BEST_ATTEMPT_ID=NULL' in sql
    assert out == {'old_score': 60, 'score': 75, 'passed': True,
                   'source': 'MANUAL', 'branch_code': 'MLG'}

def test_koreksi_kasus_tidak_ditemukan():
    conn = _LiveConn(); cur = conn.cursor(dictionary=True)
    conn.case = None
    with pytest.raises(ValueError, match='Kasus tidak ditemukan'):
        svc.set_manual_score(cur, 'RC-1', 75, 'Koreksi', 'admin1', 70)
    assert not any(s[0].startswith('UPDATE ') for s in conn.statements)

def test_koreksi_cabang_eksplisit_tanpa_melihat_riwayat():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.set_manual_score(cur, 'RC-1', 75, 'Koreksi', 'admin1', 70, 'JKT')
    assert out['branch_code'] == 'JKT'
    assert not any('FROM CASE_BRANCH_HISTORY' in s[0] for s in conn.statements)
    insert = next(s for s in conn.statements
                  if s[0].startswith('INSERT IGNORE INTO RECRUITMENT_STEPS'))
    assert insert[1] == ('RC-1', 'JKT')

def test_koreksi_ulang_dan_sync_auto_tidak_menimpa_manual():
    conn = _LiveConn(); cur = conn.cursor(dictionary=True)
    first = svc.set_manual_score(cur, 'RC-1', 75, 'Pertama', 'traineer1', 70)
    second = svc.set_manual_score(cur, 'RC-1', 50, 'Turun', 'traineer1', 70)
    assert first['old_score'] == 60 and second['old_score'] == 75
    assert conn.case['tkd_score'] == 50 and conn.case['tkd_passed'] == 0
    conn.attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 90,
                      'passed': 1, 'submitted_at': datetime(2026, 11, 24, 10, 0)}]
    conn.statements.clear()
    auto = svc.sync_case_score(cur, 'RC-1', 70)
    assert auto['score'] == 50 and auto['source'] == 'MANUAL'
    assert conn.case['tkd_score'] == 50
    assert not any(s[0].startswith('UPDATE RECRUITMENT_CASES')
                   for s in conn.statements)
    assert not any('3573010101990001' in str(s) for s in conn.statements)

def test_langkah_dikecualikan_tidak_disentuh_dan_evidence_manual():
    conn = _LiveConn(); cur = conn.cursor(dictionary=True)
    normal = {'id': 1, 'case_id': 'RC-1', 'step_type': 'TKD',
              'status': 'PENDING', 'branch_code': 'SBY'}
    excluded = {'id': 2, 'case_id': 'RC-1', 'step_type': 'TKD',
                'status': 'DIKECUALIKAN', 'branch_code': 'SBY',
                'evidence_type': 'lama', 'evidence_id': 'X', 'actor': 'lama'}
    conn.steps = [normal, excluded]
    svc.set_manual_score(cur, 'RC-1', 75, 'Naik', 'admin1', 70)
    assert normal['status'] == 'SELESAI' and normal['completed_at'] == 'NOW()'
    assert normal['evidence_type'] == 'manual_score' and normal['evidence_id'] == ''
    assert normal['actor'] == 'admin1'
    svc.set_manual_score(cur, 'RC-1', 50, 'Turun', 'admin1', 70)
    assert normal['status'] == 'PENDING' and normal['completed_at'] is None
    assert normal['evidence_type'] == 'manual_score' and normal['actor'] == 'admin1'
    assert excluded == {'id': 2, 'case_id': 'RC-1', 'step_type': 'TKD',
                        'status': 'DIKECUALIKAN', 'branch_code': 'SBY',
                        'evidence_type': 'lama', 'evidence_id': 'X',
                        'actor': 'lama'}
