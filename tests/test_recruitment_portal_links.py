import pytest
from flask import Flask, session
from modules import routes_recruitment as rr

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split())
        self.conn.statements.append((u, tuple(params or ())))
        if 'FROM BRANCHES' in u:
            self._rows = [dict(row) for row in self.conn.branches]
        elif 'FROM CV_ONLINE_BRANCH_FORMS' in u:
            self._rows = [dict(row) for row in self.conn.forms]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self):
        self.branches = [{'code': 'SBY', 'name': 'Surabaya'},
                         {'code': 'MLG', 'name': 'Malang'}]
        self.forms = [{'branch_code': 'SBY', 'form_token': 'tok-sby', 'active': 1},
                      {'branch_code': 'MLG', 'form_token': 'tok-mlg', 'active': 1}]
        self.statements = []
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rr.register_recruitment_routes(a)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(rr, '_portal_scope_branch', lambda conn: 'SBY')
    return a

@pytest.fixture
def app_real_scope(monkeypatch):
    """App yang memakai _portal_scope_branch asli (tanpa monkeypatch)."""
    a = Flask(__name__); a.secret_key = 'x'; rr.register_recruitment_routes(a)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: _Conn())
    return a

def _client(app, role='receptionist'):
    c = app.test_client()
    with c.session_transaction() as s: s['user_role'] = role; s['user_name'] = 'resepsionis'
    return c

def test_satu_link_portal_per_cabang_dalam_scope(app):
    r = _client(app).get('/api/recruitment/portal-links')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data == [{'branch_code': 'SBY', 'branch_name': 'Surabaya',
                     'portal_path': '/app/recruitment-portal?token=tok-sby',
                     'active': True}]

def test_tidak_ada_link_cv_atau_firstwork(app):
    text = _client(app).get('/api/recruitment/portal-links').get_data(as_text=True)
    assert 'cv-online-form' not in text and 'first-work-form' not in text

def test_role_finance_ditolak(app):
    assert _client(app, 'finance').get('/api/recruitment/portal-links').status_code == 403

def test_cabang_sesi_kosong_tidak_membocorkan_token(app_real_scope, monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)

    client = app_real_scope.test_client()
    with client.session_transaction() as s:
        s['user_role'] = 'traineer'
        s['user_name'] = 'petugas'
    r = client.get('/api/recruitment/portal-links')

    text = r.get_data(as_text=True)
    assert r.status_code == 200
    assert r.get_json()['data'] == []
    assert r.get_json()['scope_branch'] == rr._NO_BRANCH
    assert 'tok-sby' not in text and 'tok-mlg' not in text
    branch_queries = [(u, p) for u, p in conn.statements if 'FROM BRANCHES' in u]
    assert branch_queries
    assert all('CODE=%S' in u and p == (rr._NO_BRANCH,)
               for u, p in branch_queries)

def test_flag_aktif_string_zero_tidak_aktif(app, monkeypatch):
    conn = _Conn()
    for row in conn.forms:
        row['active'] = '0'
    monkeypatch.setattr(rr, 'get_master_connection', lambda: conn)

    r = _client(app).get('/api/recruitment/portal-links')

    row = next(c for c in r.get_json()['data'] if c['branch_code'] == 'SBY')
    assert row['active'] is False
    assert row['portal_path'] == ''
    assert 'tok-sby' not in r.get_data(as_text=True)

class TestPortalScopeBranch:
    def test_ho_admin_mendapat_semua_cabang(self, monkeypatch):
        monkeypatch.setattr('modules.admin_scope.is_ho_admin', lambda conn=None: True)
        a = Flask(__name__); a.secret_key = 'x'
        with a.test_request_context('/'):
            session['user_role'] = 'admin'
            session['branch_code'] = 'SBY'
            assert rr._portal_scope_branch(object()) is None

    def test_traineer_memakai_cabang_sesi_huruf_besar(self):
        a = Flask(__name__); a.secret_key = 'x'
        with a.test_request_context('/'):
            session['user_role'] = 'traineer'
            session['branch_code'] = 'sby'
            assert rr._portal_scope_branch(None) == 'SBY'

    def test_traineer_tanpa_cabang_memakai_sentinel(self):
        a = Flask(__name__); a.secret_key = 'x'
        with a.test_request_context('/'):
            session['user_role'] = 'traineer'
            assert rr._portal_scope_branch(None) == rr._NO_BRANCH
