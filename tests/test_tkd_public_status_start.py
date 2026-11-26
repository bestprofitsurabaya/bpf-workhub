# tests/test_tkd_public_status_start.py
from datetime import datetime, timedelta
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules import tkd_service as svc

CASE = {'case_id': 'RC-1', 'nik': '3573010101990001', 'nama': 'Andi',
        'tanggal_lahir': '1999-01-01', 'first_branch': 'SBY',
        'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
SETTINGS = {'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
            'max_attempts': 2, 'active': 1, 'shuffle_options': 0,
            'quota': {'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 3}}

class _NoopConn:
    def cursor(self, dictionary=False): return _NoopCursor()
    def commit(self): pass
    def close(self): pass

class _NoopCursor:
    def execute(self, sql, params=None): pass
    def fetchone(self): return None
    def fetchall(self): return []
    def close(self): pass

class _CommitConn(_NoopConn):
    """Koneksi tiruan yang mencatat commit dan urutannya terhadap finalisasi."""
    def __init__(self):
        self.events = []
    def cursor(self, dictionary=False): return _CommitCursor(self)
    def commit(self): self.events.append('commit')

class _CommitCursor(_NoopCursor):
    def __init__(self, conn): self.conn = conn

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'tkd-test'
    rt.register_tkd_routes(a)
    monkeypatch.setattr(rt, 'get_master_connection', lambda: _NoopConn())
    monkeypatch.setattr(svc, 'resolve_branch_token', lambda cur, tok: 'SBY' if tok == 'tok' else '')
    monkeypatch.setattr(svc, 'load_settings', lambda cur: dict(SETTINGS))
    monkeypatch.setattr(svc, 'fetch_active_questions', lambda cur: [{'id': 1}] * 31)
    monkeypatch.setattr(rt, 'readiness', lambda q, s: {'ready': True, 'reasons': []})
    monkeypatch.setattr(svc, 'verify_identity', lambda cur, nik: dict(CASE) if nik == CASE['nik'] else None)
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik, for_update=False: dict(CASE))
    monkeypatch.setattr(svc, 'finalize_expired', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'fetch_tkd_steps', lambda cur, cid: [])
    monkeypatch.setattr(rt, 'redis_rate_hit', lambda *a, **k: True)
    return a

def _post(app, path, body):
    return app.test_client().post(path, json=body)

def test_status_sukses_menyimpan_sesi_tanpa_nik(app):
    client = app.test_client()
    r = client.post('/api/recruitment/tkd/status',
                    json={'nik': CASE['nik'], 'token': 'tok'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['state'] == 'BELUM' and data['can_start'] is True
    assert r.headers['Cache-Control'] == 'no-store'
    with client.session_transaction() as s:
        assert s['tkd_case_id'] == 'RC-1' and 'nik' not in s and s['tkd_branch'] == 'SBY'

def test_status_nik_tidak_dikenal_ditolak_generik_tanpa_data(app):
    r = _post(app, '/api/recruitment/tkd/status',
              {'nik': '3573010101999999', 'token': 'tok'})
    assert r.status_code == 403
    body = r.get_json()
    assert body['status'] == 'error'
    assert 'Andi' not in r.get_data(as_text=True)
    assert 'tkd_score' not in r.get_data(as_text=True)

def test_token_salah_dan_input_invalid(app):
    assert _post(app, '/api/recruitment/tkd/status',
                 {'nik': CASE['nik'], 'token': 'x'}).status_code == 400
    assert _post(app, '/api/recruitment/tkd/status',
                 {'nik': '123', 'token': 'tok'}).status_code == 400

def test_start_menolak_tier_tidak_dikenal_dan_bank_belum_aktif(app, monkeypatch):
    bad = _post(app, '/api/recruitment/tkd/start',
                {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '20k'})
    assert bad.status_code == 400

    monkeypatch.setattr(svc, 'load_settings', lambda cur: dict(SETTINGS, active=0))
    off = _post(app, '/api/recruitment/tkd/start',
                {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '30k'})
    assert off.status_code == 409

def test_start_mengembalikan_soal_tanpa_kunci(app, monkeypatch):
    monkeypatch.setattr(svc, 'create_attempt', lambda *a, **k: {
        'attempt': {'id': 'TKD-1', 'attempt_no': 1, 'expires_at': datetime(2026, 11, 24, 10, 25)},
        'items': [{'position': 1, 'snapshot': {'type': 'MCQ', 'prompt': 'P',
                    'options': [{'id': 'a', 'text': 'A'}], 'answer': {'option': 'a'},
                    'points': 1, 'category': 'REGULASI'}, 'answer': None}]})
    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '30k'})
    assert r.status_code == 200
    body = r.get_json()['data']
    q = body['questions'][0]
    assert 'answer' not in q and 'points' not in q
    assert body['attempt_id'] == 'TKD-1'

def _track_finalize(conn):
    def _finalize(cur, case_id):
        conn.events.append('finalize')
        return []
    return _finalize

def test_status_commit_setelah_finalisasi_attempt_kedaluwarsa(app, monkeypatch):
    conn = _CommitConn()
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(svc, 'finalize_expired', _track_finalize(conn))
    r = _post(app, '/api/recruitment/tkd/status',
              {'nik': CASE['nik'], 'token': 'tok'})
    assert r.status_code == 200
    # Tanpa commit, UPDATE finalisasi dirollback saat koneksi ditutup.
    assert conn.events == ['finalize', 'commit']

def test_start_resume_commit_setelah_finalisasi(app, monkeypatch):
    conn = _CommitConn()
    active = {'id': 'TKD-aktif', 'case_id': 'RC-1', 'status': 'BERLANGSUNG',
              'modal_tier': '30k', 'attempt_no': 1,
              'expires_at': datetime.now() + timedelta(minutes=20),
              'settings_snapshot': '{"duration_minutes": 25}'}
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(svc, 'finalize_expired', _track_finalize(conn))
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [active])
    monkeypatch.setattr(svc, 'fetch_attempt_items', lambda cur, aid: [])
    def _must_not_create(*a, **k):
        conn.events.append('create')
        raise AssertionError('resume tidak boleh membuat attempt baru')
    monkeypatch.setattr(svc, 'create_attempt', _must_not_create)

    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '30k'})
    assert r.status_code == 200
    assert r.get_json()['data']['attempt_id'] == 'TKD-aktif'
    assert conn.events == ['finalize', 'commit']

def test_start_blokir_setelah_finalisasi_juga_commit(app, monkeypatch):
    conn = _CommitConn()
    spent = [{'id': f'TKD-{n}', 'case_id': 'RC-1', 'status': 'SELESAI',
              'score': 50, 'submitted_at': datetime(2026, 11, 24, 10, 0)}
             for n in (1, 2)]
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(svc, 'finalize_expired', _track_finalize(conn))
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: spent)
    def _must_not_create(*a, **k):
        conn.events.append('create')
        raise AssertionError('state HABIS tidak boleh membuat attempt baru')
    monkeypatch.setattr(svc, 'create_attempt', _must_not_create)

    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '30k'})
    assert r.status_code == 409
    assert conn.events == ['finalize', 'commit']

def test_status_token_cabang_lain_ditolak_generik(app, monkeypatch):
    monkeypatch.setattr(svc, 'resolve_branch_token',
                        lambda cur, tok: 'BDG' if tok == 'tok-bdg' else '')
    client = app.test_client()
    r = client.post('/api/recruitment/tkd/status',
                    json={'nik': CASE['nik'], 'token': 'tok-bdg'})
    assert r.status_code == 403
    body = r.get_data(as_text=True)
    assert 'Andi' not in body and 'SBY' not in body and 'BDG' not in body
    with client.session_transaction() as s:
        assert 'tkd_case_id' not in s

def test_start_token_cabang_lain_tidak_membuat_attempt(app, monkeypatch):
    monkeypatch.setattr(svc, 'resolve_branch_token',
                        lambda cur, tok: 'BDG' if tok == 'tok-bdg' else '')
    created = []
    monkeypatch.setattr(svc, 'create_attempt',
                        lambda *a, **k: created.append(a) or {})
    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'token': 'tok-bdg', 'modal_tier': '30k'})
    assert r.status_code == 403
    assert created == []
    assert 'SBY' not in r.get_data(as_text=True)

def test_start_sukses_mempertahankan_kunci_sampai_attempt_dibuat(app, monkeypatch):
    conn = _CommitConn()
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(svc, 'finalize_expired', _track_finalize(conn))
    def _create(cur, case, branch, tier, settings, questions, *a, **k):
        conn.events.append('create')
        return {'attempt': {'id': 'TKD-baru', 'attempt_no': 1,
                            'modal_tier': tier,
                            'expires_at': datetime.now() + timedelta(minutes=25)},
                'items': []}
    monkeypatch.setattr(svc, 'create_attempt', _create)

    r = _post(app, '/api/recruitment/tkd/start',
              {'nik': CASE['nik'], 'token': 'tok', 'modal_tier': '30k'})
    assert r.status_code == 200
    assert r.get_json()['data']['attempt_id'] == 'TKD-baru'
    # SELECT ... FOR UPDATE harus masih mengunci baris kasus saat create dihitung.
    assert conn.events == ['finalize', 'create', 'commit']
    assert conn.events.index('create') < conn.events.index('commit')
    assert 'commit' not in conn.events[:conn.events.index('create')]
