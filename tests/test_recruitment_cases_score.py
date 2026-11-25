import pytest
from flask import Flask
from modules import routes_recruitment as rr

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split())
        self.conn.statements.append((u, params))
        if u.startswith('SELECT ID, CASE_ID, STEP_TYPE, STATUS') and 'RECRUITMENT_STEPS' in u:
            self._rows = [{'id': 13, 'case_id': 'RC-1', 'step_type': 'TKD',
                           'status': 'PENDING', 'branch_code': 'SBY'}]
        elif 'FROM RECRUITMENT_CASES' in u:
            self._rows = [{'case_id': 'RC-1', 'first_branch': 'SBY'}]
        else:
            self._rows = []
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []; self.commits = 0
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): self.commits += 1
    def rollback(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'
    rr.register_recruitment_routes(a)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(rr, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rr, 'load_settings', lambda cur: {'pass_score': 70})
    return a

def _client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = 'traineer'; s['user_name'] = 'petugas'
    return c

def test_bukti_tkd_dengan_skor_menulis_manual(app, monkeypatch):
    called = {}
    def _fake(cur, cid, score, reason, actor, pass_score, branch_code=''):
        called.update(case_id=cid, score=score, reason=reason, actor=actor,
                      pass_score=pass_score, branch_code=branch_code)
        return {'score': score, 'passed': True, 'source': 'MANUAL',
                'branch_code': branch_code}
    monkeypatch.setattr(rr, 'set_manual_score', _fake)
    r = _client(app).post('/api/recruitment/steps/13/evidence',
                          json={'date': '2026-11-24', 'note': 'Tes manual',
                                'score': '80'})
    assert r.status_code == 200
    assert called == {'case_id': 'RC-1', 'score': 80.0, 'reason': 'Tes manual',
                      'actor': 'petugas', 'pass_score': 70,
                      'branch_code': 'SBY'}

@pytest.mark.parametrize('bad', ['101', 'abc', '-1'])
def test_bukti_tkd_skor_invalid_ditolak(app, monkeypatch, bad):
    called = []
    monkeypatch.setattr(rr, 'set_manual_score', lambda *a, **k: called.append(1))
    r = _client(app).post('/api/recruitment/steps/13/evidence',
                          json={'date': '2026-11-24', 'note': 'x', 'score': bad})
    assert r.status_code == 400
    assert called == []

def test_bukti_tkd_tidak_menulis_status_sendiri(app, monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rr, 'set_manual_score', lambda *a, **k: {
        'score': 80.0, 'passed': False, 'source': 'MANUAL'})

    r = _client(app).post('/api/recruitment/steps/13/evidence',
                          json={'date': '2026-11-24', 'score': '80'})

    assert r.status_code == 200
    assert not any('UPDATE RECRUITMENT_STEPS' in s
                   for s, _ in conn.statements)

def test_bukti_tkd_skor_invalid_tidak_membuat_langkah(app, monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)
    called = []
    monkeypatch.setattr(rr, 'set_manual_score', lambda *a, **k: called.append(1))

    r = _client(app).post('/api/recruitment/steps/0/evidence',
                          json={'date': '2026-11-24', 'case_id': 'RC-1',
                                'step_type': 'TKD', 'score': 'abc'})

    assert r.status_code == 400
    assert called == []
    assert not any(s.startswith('INSERT') for s, _ in conn.statements)
