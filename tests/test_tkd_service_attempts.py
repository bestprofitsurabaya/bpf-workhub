import json
from datetime import datetime, timedelta
import pytest
from modules import tkd_service as svc
from modules.tkd_core import DEFAULT_QUOTA

class _Cursor:
    def __init__(self, conn):
        self.conn = conn; self._rows = []; self.lastrowid = 0
    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        self.conn.statements.append((upper, params))
        if upper.startswith('INSERT INTO TKD_ATTEMPTS'):
            self.conn.inserted_attempt = params
        elif upper.startswith('INSERT INTO TKD_ATTEMPT_ITEMS'):
            self.conn.items.append({'attempt_id': params[0], 'question_id': params[1],
                                    'position': params[2], 'snapshot': params[3],
                                    'answer': None, 'is_correct': None,
                                    'points_awarded': None})
        elif 'FROM TKD_ATTEMPT_ITEMS' in upper:
            self._rows = list(self.conn.items)
        elif 'FROM TKD_ATTEMPTS' in upper and 'CASE_ID=%S' in upper:
            self._rows = list(self.conn.attempts)
        elif 'FROM RECRUITMENT_CASES' in upper:
            self._rows = [self.conn.case]
        elif 'FROM TKD_SETTINGS' in upper:
            self._rows = [self.conn.settings]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self):
        self.statements = []; self.inserted_attempt = None
        self.case = {'case_id': 'RC-1', 'first_branch': 'SBY', 'tkd_score': None,
                     'tkd_score_source': None, 'tkd_passed': None,
                     'tkd_score_note': None, 'tkd_best_attempt_id': None}
        self.settings = {'question_count': 20, 'duration_minutes': 25,
                         'pass_score': 70, 'max_attempts': 2, 'active': 1,
                         'shuffle_options': 0,
                         'quota': dict(DEFAULT_QUOTA)}
        self.attempts, self.items = [], []
    def cursor(self, dictionary=False): return _Cursor(self)

def _questions():
    rows = []
    for cat, n in (('REGULASI', 8), ('PERUSAHAAN', 5), ('PRODUK', 7)):
        for i in range(n):
            rows.append({'id': len(rows) + 1, 'code': f'{cat}-{i}', 'category': cat,
                         'type': 'MCQ', 'prompt': f'{cat} {i}',
                         'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
                         'answer': {'option': 'a'}, 'points': 1,
                         'modal_tier': None, 'active': 1, 'sort_order': i})
    for i in range(4):
        rows.append({'id': len(rows) + 1, 'code': f'HIT-G-{i}', 'category': 'HITUNG',
                     'type': 'NUMERIC', 'prompt': 'H', 'options': [],
                     'answer': {'value': 10, 'tolerance': 0.5}, 'points': 1,
                     'modal_tier': None, 'active': 1, 'sort_order': i})
    for tier in ('30k', '50k', '100k'):
        for i in range(2):
            rows.append({'id': len(rows) + 1, 'code': f'HIT-{tier}-{i}',
                         'category': 'HITUNG', 'type': 'NUMERIC', 'prompt': 'H',
                         'options': [], 'answer': {'value': 10, 'tolerance': 0.5},
                         'points': 1, 'modal_tier': tier, 'active': 1, 'sort_order': i})
    rows.append({'id': len(rows) + 1, 'code': 'PROF-1', 'category': 'PROFIL',
                 'type': 'PROFILE_TEXT', 'prompt': 'Motivasi?', 'options': [],
                 'answer': None, 'points': 0, 'modal_tier': None,
                 'active': 1, 'sort_order': 0})
    return rows

def test_create_attempt_membuat_21_item_dan_snapshot_berkunci():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings,
                             _questions(), now=datetime(2026, 11, 24, 10, 0))
    assert out['attempt']['attempt_no'] == 1
    assert out['attempt']['expires_at'] == datetime(2026, 11, 24, 10, 25)
    assert len(out['items']) == 21
    mcq = [i for i in out['items']
           if json.loads(i['snapshot'])['type'] == 'MCQ']
    assert json.loads(mcq[0]['snapshot'])['answer'] == {'option': 'a'}

def test_finalize_menilai_dan_menyinkronkan_skor_kasus():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings, _questions())
    for item in out['items'][:14]:
        snap = json.loads(item['snapshot'])
        if snap['type'] == 'MCQ':
            item['answer'] = json.dumps({'option': snap['answer']['option']})
        else:
            item['answer'] = json.dumps({'value': snap['answer']['value']})
    attempt = {'id': out['attempt']['id'], 'case_id': 'RC-1', 'status': 'BERLANGSUNG',
               'pass_score_snapshot': 70, 'branch_code': 'SBY',
               'started_at': datetime(2026, 11, 24, 10, 0),
               'expires_at': datetime(2026, 11, 24, 10, 25), 'submitted_at': None,
               'score': None, 'passed': None, 'attempt_no': 1}
    conn.attempts = [attempt]
    result = svc.finalize_attempt(cur, attempt, 'SELESAI')
    assert result['score'] == 70.0 and result['passed'] is True

def test_edit_bank_setelah_attempt_tidak_mengubah_snapshot():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    questions = _questions()
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings, questions)
    idx = next(i for i, item in enumerate(out['items'])
               if json.loads(item['snapshot'])['type'] == 'MCQ')
    snapshot_before = out['items'][idx]['snapshot']
    # Edit bank soal setelah attempt dibuat: snapshot attempt harus beku.
    questions[0]['prompt'] = 'DIUBAH'
    questions[0]['answer'] = {'option': 'b'}
    assert out['items'][idx]['snapshot'] == snapshot_before
    assert json.loads(out['items'][idx]['snapshot'])['answer'] == {'option': 'a'}

def test_attempt_kedaluwarsa_tetap_menghabiskan_kesempatan():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    old = {'id': 'TKD-old', 'case_id': 'RC-1', 'status': 'BERLANGSUNG',
           'expires_at': datetime(2026, 11, 24, 9, 0), 'pass_score_snapshot': 70,
           'branch_code': 'SBY', 'attempt_no': 1, 'score': None, 'passed': None}
    conn.attempts = [old]
    done = svc.finalize_expired(cur, 'RC-1', now=datetime(2026, 11, 24, 10, 0))
    assert done and done[0]['status'] == 'KEDALUWARSA'

def test_sync_tidak_menimpa_manual():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.case.update(tkd_score=75, tkd_score_source='MANUAL', tkd_passed=1)
    conn.attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 90,
                       'passed': 1, 'submitted_at': datetime(2026, 11, 24, 10, 0)}]
    out = svc.sync_case_score(cur, 'RC-1', 70)
    assert out['score'] == 75 and out['source'] == 'MANUAL'
    assert not any(s[0].startswith('UPDATE RECRUITMENT_CASES') for s in conn.statements)


# Cakupan tambahan untuk kontrak Task 6 yang tidak ada di contoh tes brief.

def test_attempt_kedua_mendapat_nomor_berikutnya():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.attempts = [{'id': 'TKD-1', 'attempt_no': 1},
                     {'id': 'TKD-2', 'attempt_no': 2}]
    out = svc.create_attempt(cur, conn.case, 'SBY', '30k', conn.settings,
                             _questions())
    assert out['attempt']['attempt_no'] == 3

def test_finalize_idempoten_tanpa_menulis_ulang():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    attempt = {'id': 'TKD-1', 'case_id': 'RC-1', 'status': 'SELESAI',
               'score': 80.0, 'passed': 1, 'attempt_no': 1}
    conn.attempts = [attempt]
    result = svc.finalize_attempt(cur, attempt, 'KEDALUWARSA')
    assert result is attempt and result['status'] == 'SELESAI'
    assert not any(s[0].startswith('UPDATE TKD_ATTEMPTS') for s in conn.statements)

def test_sync_auto_memilih_terbaik_dan_menulis_skor_resmi():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.attempts = [
        {'id': 'TKD-1', 'status': 'SELESAI', 'score': 60, 'passed': 0,
         'submitted_at': datetime(2026, 11, 24, 10, 0)},
        {'id': 'TKD-2', 'status': 'KEDALUWARSA', 'score': 80, 'passed': 1,
         'submitted_at': datetime(2026, 11, 24, 11, 0)},
    ]
    out = svc.sync_case_score(cur, 'RC-1', 70, 'MLG')
    assert out == {'score': 80.0, 'source': 'AUTO', 'passed': True,
                   'best_attempt_id': 'TKD-2'}
    sql = ' '.join(s[0] for s in conn.statements)
    assert "TKD_SCORE_SOURCE='AUTO'" in sql
    assert 'INSERT IGNORE INTO RECRUITMENT_STEPS' in sql
    assert 'UPDATE RECRUITMENT_STEPS' in sql

def test_attempt_result_hanya_memuat_data_publik():
    conn = _Conn(); cur = conn.cursor(dictionary=True)
    conn.case.update(tkd_score=75, tkd_score_source='AUTO', tkd_passed=1)
    conn.attempts = [{'id': 'TKD-1', 'case_id': 'RC-1', 'attempt_no': 1,
                      'status': 'SELESAI', 'score': 75, 'passed': 1,
                      'submitted_at': datetime(2026, 11, 24, 10, 0)}]
    attempt = conn.attempts[0]
    settings = dict(conn.settings, active=1)
    out = svc.attempt_result(cur, attempt, settings)
    assert out['score'] == 75 and out['passed'] is True
    assert out['official_score'] == 75 and out['official_passed'] is True
    assert out['best_score'] == 75 and out['attempts_used'] == 1
    assert out['max_attempts'] == 2 and out['state'] == 'LULUS'
    assert not {'answer', 'points', 'is_correct', 'snapshot'} & set(out)
