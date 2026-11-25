# tests/test_tkd_staff_results.py
import json
from datetime import datetime
import pytest
from flask import Flask, session
from modules import routes_tkd as rt
from modules import tkd_service as svc

# Fungsi asli ditangkap sebelum fixture brief menggantinya; dipakai tes real
# di bawah supaya helper/endpoint yang diuji tidak di-stub.
_REAL_SCOPE_BRANCH = rt._scope_branch if hasattr(rt, '_scope_branch') else None
_REAL_FETCH_ROWS = rt._fetch_attempt_rows if hasattr(rt, '_fetch_attempt_rows') else None
_REAL_FINALIZE_ALL = rt.finalize_expired_all
_REAL_FETCH_REVIEW = rt._fetch_review if hasattr(rt, '_fetch_review') else None
_NIK = '3573010101990001'

CASE = {'case_id': 'RC-1', 'nama': 'Andi', 'nik': '3573010101990001',
        'first_branch': 'SBY', 'tkd_score': 60, 'tkd_score_source': 'AUTO',
        'tkd_passed': 0, 'tkd_score_note': None}

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    class _Conn:
        def cursor(self, dictionary=False): return object()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(rt, 'get_master_connection', _Conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rt, '_scope_branch', lambda conn: 'SBY')
    monkeypatch.setattr(rt, '_fetch_attempt_rows', lambda cur, scope, q: [{
        'id': 'TKD-1', 'case_id': 'RC-1', 'nama': 'Andi',
        'nik': '3573010101990001', 'branch_code': 'SBY', 'attempt_no': 1,
        'status': 'SELESAI', 'score': 60, 'passed': 0,
        'started_at': datetime(2026, 11, 24, 10, 0),
        'submitted_at': datetime(2026, 11, 24, 10, 20),
        'score_source': 'AUTO'}])
    monkeypatch.setattr(svc, 'set_manual_score', lambda *a, **k: {
        'old_score': 60, 'score': 75, 'passed': True, 'source': 'MANUAL', 'branch_code': 'SBY'})
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik: dict(CASE))
    monkeypatch.setattr(svc, 'load_settings', lambda cur: {
        'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
        'max_attempts': 2, 'quota': {'REGULASI': 7, 'PERUSAHAAN': 4,
                                     'PRODUK': 6, 'HITUNG': 3},
        'shuffle_options': 0, 'active': 1})
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [{'id': i} for i in range(30)])
    monkeypatch.setattr(rt, 'readiness', lambda q, s: {
        'ready': True, 'active_valued': 30, 'quota_ok': {}, 'tier_ok': {},
        'reasons': []})
    monkeypatch.setattr(rt, '_case_in_scope', lambda cur, cid, scope: True)
    monkeypatch.setattr(rt, 'finalize_expired_all', lambda cur, scope: [])
    return a

def _client(app, role='traineer', branch='SBY'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = role; s['user_name'] = 'petugas'; s['branch_code'] = branch
    return c

def test_daftar_hasil_memasker_nik(app):
    r = _client(app).get('/api/recruitment/tkd/attempts')
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert '****0001' in text and '3573010101990001' not in text

def test_review_hanya_staff_dan_memuat_kunci(app, monkeypatch):
    monkeypatch.setattr(rt, '_fetch_review', lambda cur, aid, scope: {
        'attempt': {'id': 'TKD-1'}, 'case': {'nama': 'Andi'},
        'items': [{'position': 1, 'answer': {'option': 'a'}, 'is_correct': 1, 'points_awarded': 1,
                   'snapshot': {'prompt': 'P', 'answer': {'option': 'a'}, 'points': 1}}]})
    r = _client(app).get('/api/recruitment/tkd/review/TKD-1')
    assert r.status_code == 200
    assert r.get_json()['data']['items'][0]['snapshot']['answer'] == {'option': 'a'}
    assert _client(app, 'finance').get('/api/recruitment/tkd/review/TKD-1').status_code == 403

def test_koreksi_skor_wajib_alasan_dan_rentang_0_100(app):
    c = _client(app)
    assert c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 75}).status_code == 400
    assert c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 101, 'reason': 'x'}).status_code == 400
    ok = c.post('/api/recruitment/tkd/score', json={'case_id': 'RC-1', 'score': 75, 'reason': 'Koreksi'})
    assert ok.status_code == 200 and ok.get_json()['data']['score'] == 75

def test_pengaturan_hanya_admin_boleh_ubah(app):
    assert _client(app, 'traineer').put('/api/recruitment/tkd/settings', json={}).status_code == 403
    assert _client(app, 'admin').get('/api/recruitment/tkd/settings').status_code == 200


# ---------------------------------------------------------------------------
# Tes lanjutan: fungsi/endpoint yang diuji TIDAK di-stub.
# ---------------------------------------------------------------------------
class _RecordingCursor:
    """Cursor tiruan yang mencatat SQL dan menyajikan baris sesuai marker."""

    def __init__(self, conn, responses=None):
        self.conn = conn
        self.responses = responses or {}
        self._rows = []

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).upper().split())
        self.conn.statements.append((text, params))
        self.conn.events.append('sql')
        self._rows = []
        for marker, rows in self.responses.items():
            if marker.upper() in text:
                if isinstance(rows, (list, tuple)):
                    self._rows = list(rows)
                elif rows is not None:
                    self._rows = [rows]
                break

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        self.conn.events.append('cursor_close')


class _RecordingConn:
    def __init__(self, responses=None):
        self.statements = []
        self.events = []
        self.responses = responses or {}

    def cursor(self, dictionary=False):
        return _RecordingCursor(self, self.responses)

    def commit(self):
        self.events.append('commit')

    def rollback(self):
        self.events.append('rollback')

    def close(self):
        self.events.append('close')


@pytest.fixture
def real_app():
    a = Flask(__name__)
    a.secret_key = 'x-real'
    rt.register_tkd_routes(a)
    return a


def _valid_settings_body(active=True):
    return {
        'question_count': 1, 'duration_minutes': 25, 'pass_score': 70,
        'max_attempts': 2,
        'quota': {'REGULASI': 1, 'PERUSAHAAN': 0, 'PRODUK': 0, 'HITUNG': 0},
        'shuffle_options': 0, 'active': int(active),
    }


def test_scope_branch_asli(real_app):
    with real_app.test_request_context('/'):
        session.update(user_role='admin', user_name='admin', branch_code='sby')
        assert _REAL_SCOPE_BRANCH(None) is None
    with real_app.test_request_context('/'):
        session.update(user_role='traineer', user_name='petugas', branch_code='sby')
        assert _REAL_SCOPE_BRANCH(None) == 'SBY'
    with real_app.test_request_context('/'):
        session.update(user_role='traineer', user_name='petugas', branch_code='')
        assert _REAL_SCOPE_BRANCH(None) == rt._NO_BRANCH
        assert _REAL_SCOPE_BRANCH(None) is not None


def test_attempts_memakai_scope_dan_filter_nik_asli(real_app, monkeypatch):
    conn = _RecordingConn({
        'SELECT DISTINCT A.CASE_ID': [],
        'FROM TKD_ATTEMPTS A JOIN': [{
            'id': 'TKD-1', 'case_id': 'RC-1', 'nama': 'Andi', 'nik': _NIK,
            'branch_code': 'SBY', 'attempt_no': 1, 'status': 'SELESAI',
            'score': 60, 'passed': 0, 'score_source': 'AUTO',
            'official_score': 60,
            'started_at': datetime(2026, 11, 24, 10, 0),
            'submitted_at': datetime(2026, 11, 24, 10, 20),
        }],
    })
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)

    def _finalize_spy(cursor, scope):
        conn.events.append('finalize')
        return _REAL_FINALIZE_ALL(cursor, scope)
    monkeypatch.setattr(rt, 'finalize_expired_all', _finalize_spy)

    r = _client(real_app).get('/api/recruitment/tkd/attempts?q=' + _NIK)
    assert r.status_code == 200
    row = r.get_json()['data'][0]
    assert row['nik_masked'] == '****0001' and 'nik' not in row
    assert row['official_score'] == 60
    assert _NIK not in r.get_data(as_text=True)
    sql, params = next((s, p) for s, p in conn.statements
                       if 'FROM TKD_ATTEMPTS A JOIN' in s)
    assert 'A.BRANCH_CODE=%S' in sql and 'SBY' in params
    assert 'C.NIK=%S' in sql and _NIK in params
    assert conn.events.index('finalize') < conn.events.index('commit')


def test_finalize_expired_all_satu_clock_dan_filter_cabang(monkeypatch):
    conn = _RecordingConn({'SELECT DISTINCT A.CASE_ID': [
        {'case_id': 'RC-1'}, {'case_id': 'RC-2'}]})
    calls = []

    def _finalize(cursor, case_id, now=None):
        calls.append((case_id, now))
        return [{'id': case_id}]
    monkeypatch.setattr(svc, 'finalize_expired', _finalize)

    done = rt.finalize_expired_all(conn.cursor(), 'SBY')
    sql, params = conn.statements[0]
    assert 'SELECT DISTINCT A.CASE_ID' in sql
    assert 'A.EXPIRES_AT < %S' in sql and isinstance(params[0], datetime)
    assert 'A.BRANCH_CODE=%S' in sql and params[1] == 'SBY'
    assert 'LIMIT 200' in sql
    assert [case_id for case_id, _ in calls] == ['RC-1', 'RC-2']
    assert calls[0][1] is params[0] and len(done) == 2

    conn_all = _RecordingConn({'SELECT DISTINCT A.CASE_ID': [
        {'case_id': 'RC-3'}]})
    rt.finalize_expired_all(conn_all.cursor(), None)
    assert 'A.BRANCH_CODE' not in conn_all.statements[0][0]


def test_review_memakai_cabang_attempt_bukan_cabang_kasus(real_app, monkeypatch):
    monkeypatch.setattr(rt, '_fetch_review', _REAL_FETCH_REVIEW)

    def _tidak_boleh(cur, case_id, scope):
        raise AssertionError('_case_in_scope tidak boleh dipakai review')
    monkeypatch.setattr(rt, '_case_in_scope', _tidak_boleh)

    conn = _RecordingConn({
        'FROM RECRUITMENT_CASES WHERE CASE_ID': {
            'case_id': 'RC-1', 'nama': 'Andi', 'nik': _NIK,
            'first_branch': 'MLG'},
        'FROM TKD_ATTEMPT_ITEMS': [],
    })
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(svc, 'fetch_attempt', lambda cur, aid: {
        'id': aid, 'case_id': 'RC-1', 'branch_code': 'SBY', 'score': 60,
        'passed': 0, 'settings_snapshot': '{"duration_minutes":25}',
        'internal_secret': 'jangan-dikirim'})
    monkeypatch.setattr(svc, 'fetch_attempt_items', lambda cur, aid: [])

    r = _client(real_app).get('/api/recruitment/tkd/review/TKD-1')
    assert r.status_code == 200
    body = r.get_json()['data']
    assert body['case']['nik_masked'] == '****0001' and 'nik' not in body['case']
    assert body['attempt']['id'] == 'TKD-1'
    assert body['attempt']['settings_snapshot'] == {'duration_minutes': 25}
    assert 'internal_secret' not in body['attempt']
    assert not any('CASE_BRANCH_HISTORY' in s or 'FROM RECRUITMENT_STEPS' in s
                   for s, _ in conn.statements)


def test_settings_put_peran_validasi_gate_dan_update(real_app, monkeypatch):
    conn = _RecordingConn()
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    audits = []
    monkeypatch.setattr(rt, 'log_activity_async',
                        lambda *a, **k: audits.append((a, k)))
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [])

    assert _client(real_app, 'traineer').put(
        '/api/recruitment/tkd/settings', json={}).status_code == 403
    assert _client(real_app, 'admin').put(
        '/api/recruitment/tkd/settings', json={}).status_code == 400
    assert not conn.statements

    conflict = _client(real_app, 'admin').put(
        '/api/recruitment/tkd/settings', json=_valid_settings_body(True))
    assert conflict.status_code == 409 and conflict.get_json()['reasons']
    assert not any(s.startswith('UPDATE TKD_SETTINGS')
                   for s, _ in conn.statements)

    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [
        {'active': 1, 'category': 'REGULASI', 'type': 'MCQ', 'points': 1},
        {'active': 1, 'category': 'PROFIL', 'type': 'PROFILE_TEXT', 'points': 0}])
    ok = _client(real_app, 'admin').put(
        '/api/recruitment/tkd/settings', json=_valid_settings_body(True))
    assert ok.status_code == 200 and ok.get_json()['data']['active'] is True
    assert any(s.startswith('UPDATE TKD_SETTINGS') for s, _ in conn.statements)
    assert audits[-1][0][1] == 'tkd_settings_update'


def test_score_cabang_dan_audit_tanpa_nik(real_app, monkeypatch):
    conn = _RecordingConn({
        'FROM RECRUITMENT_CASES WHERE CASE_ID': {'first_branch': 'MLG'},
        'FROM CASE_BRANCH_HISTORY': [],
        'FROM RECRUITMENT_STEPS': [],
    })
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    audits = []
    monkeypatch.setattr(rt, 'log_activity_async',
                        lambda *a, **k: audits.append((a, k)))
    calls = []

    def _set_manual_score(*args, **kwargs):
        calls.append((args, kwargs))
        return {'old_score': 60, 'score': 75, 'passed': True,
                'source': 'MANUAL', 'branch_code': 'SBY'}
    monkeypatch.setattr(svc, 'set_manual_score', _set_manual_score)
    monkeypatch.setattr(svc, 'load_settings', lambda cur: {'pass_score': 70})

    body = {'case_id': 'RC-1', 'score': 75, 'reason': 'Koreksi'}
    denied = _client(real_app).post('/api/recruitment/tkd/score', json=body)
    assert denied.status_code == 403 and not calls and not audits

    conn_ok = _RecordingConn({
        'FROM RECRUITMENT_CASES WHERE CASE_ID': {'first_branch': 'SBY'}})
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn_ok)
    ok = _client(real_app).post('/api/recruitment/tkd/score', json=body)
    assert ok.status_code == 200 and calls[-1][0][1] == 'RC-1'
    data = audits[-1][1]['new_data']
    assert data['case_id'] == 'RC-1' and data['score'] == 75
    assert data['reason'] == 'Koreksi' and data['actor'] == 'petugas'
    assert 'nik' not in data and _NIK not in json.dumps(audits)
