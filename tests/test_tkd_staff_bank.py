import json
import pytest
from flask import Flask
from modules import routes_tkd as rt

QUESTION = {'id': 1, 'code': 'REG-01', 'category': 'REGULASI', 'type': 'MCQ',
            'prompt': 'P', 'options': json.dumps([{'id': 'a', 'text': 'A'}]),
            'answer': json.dumps({'option': 'a'}), 'points': 1,
            'modal_tier': None, 'active': 0, 'sort_order': 0}

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split()); self.conn.statements.append((u, params))
        if u.startswith('SELECT') and 'FROM TKD_QUESTIONS' in u:
            self._rows = [dict(QUESTION)]
        elif u.startswith('INSERT INTO TKD_QUESTIONS'):
            self.conn.inserted = params; self.lastrowid = 7
        elif u.startswith('UPDATE TKD_QUESTIONS'):
            self.conn.updated = params
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []; self.inserted = None; self.updated = None
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    conn = _Conn()
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rt, 'log_activity_async', lambda *a, **k: None)
    a.conn = conn
    return a

def _client(app, role='traineer'):
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = role; s['user_name'] = 'petugas'
    return c

def test_daftar_soal_staff_memuat_kunci(app):
    r = _client(app).get('/api/recruitment/tkd/questions')
    assert r.status_code == 200
    row = r.get_json()['data'][0]
    assert row['answer'] == {'option': 'a'} and row['options'] == [{'id': 'a', 'text': 'A'}]

def test_role_lain_ditolak(app):
    assert _client(app, 'finance').get('/api/recruitment/tkd/questions').status_code == 403

def test_tambah_soal_valid_dan_invalid(app):
    body = {'code': 'NEW-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer': {'option': 'a'}, 'points': 1}
    ok = _client(app).post('/api/recruitment/tkd/questions', json=body)
    assert ok.status_code == 201 and ok.get_json()['data']['id'] == 7
    bad = _client(app).post('/api/recruitment/tkd/questions', json=dict(body, answer={'option': 'z'}))
    assert bad.status_code == 400

def test_toggle_membalik_status(app):
    r = _client(app).post('/api/recruitment/tkd/questions/1/toggle')
    assert r.status_code == 200
    assert any('UPDATE TKD_QUESTIONS SET ACTIVE' in s[0] for s in app.conn.statements)
