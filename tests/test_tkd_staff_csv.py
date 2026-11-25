import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules.tkd_core import CSV_COLUMNS

CSV_TEXT = ('code,category,type,prompt,option_a,option_b,option_c,option_d,option_e,'
            'correct,tolerance,points,modal_tier,active\n'
            'NEW-1,PRODUK,MCQ,Pertanyaan,A,B,,, ,a,,1,,1\n'
            'OLD-1,PRODUK,MCQ,Pertanyaan,A,B,,, ,a,,1,,1\n')
DRAFT_ROW = 'DRAFT-1,PRODUK,MCQ,Pertanyaan,A,B,,, ,a,,1,,0\n'

class _Cursor:
    def __init__(self, conn): self.conn = conn; self._rows = []
    def execute(self, sql, params=None):
        u = ' '.join(str(sql).upper().split()); self.conn.statements.append((u, params))
        if 'FROM TKD_QUESTIONS' in u and u.startswith('SELECT'):
            self._rows = [{'code': 'OLD-1', 'active': 1},
                          {'code': 'DRAFT-1', 'active': 0}]
        else:
            self._rows = []
    def fetchall(self): return list(self._rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def close(self): pass

class _Conn:
    def __init__(self): self.statements = []
    def cursor(self, dictionary=False): return _Cursor(self)
    def commit(self): pass
    def close(self): pass

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__); a.secret_key = 'x'; rt.register_tkd_routes(a)
    conn = _Conn(); a.conn = conn; a.audits = []
    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rt, 'log_activity_async',
                        lambda *args, **kwargs: a.audits.append((args, kwargs)))
    return a

def _client(app, role='traineer'):
    c = app.test_client()
    with c.session_transaction() as s: s['user_role'] = role; s['user_name'] = 'petugas'
    return c

def test_impor_menyisipkan_draft_dan_melewati_kode_aktif(app):
    r = _client(app).post('/api/recruitment/tkd/questions/import',
                          json={'csv': CSV_TEXT, 'update_drafts': False})
    assert r.status_code == 200
    body = r.get_json()
    assert body['inserted'] == 1 and body['skipped'] == 1 and body['updated'] == 0
    assert not any(u.startswith('UPDATE TKD_QUESTIONS')
                   for u, _ in app.conn.statements)

def test_impor_menolak_csv_kosong_dan_baris_berlebih(app):
    empty = _client(app).post('/api/recruitment/tkd/questions/import', json={})
    assert empty.status_code == 400
    assert empty.get_json()['status'] == 'error' and empty.get_json()['msg']
    too_many = CSV_TEXT + ''.join(
        f'X-{i},PRODUK,MCQ,P,A,B,,,,a,,1,,0\n' for i in range(500))
    r = _client(app).post('/api/recruitment/tkd/questions/import', json={'csv': too_many})
    assert r.status_code == 400
    assert r.get_json()['status'] == 'error' and r.get_json()['msg']

def test_impor_menolak_kode_duplikat_tanpa_insert(app):
    header, new_row, _old_row = CSV_TEXT.splitlines()
    dup = '\n'.join((header, new_row, new_row)) + '\n'  # NEW-1 dua kali (baris 3)
    r = _client(app).post('/api/recruitment/tkd/questions/import', json={'csv': dup})
    assert r.status_code == 400
    body = r.get_json()
    assert body['status'] == 'error'
    assert 'baris 3' in body['msg'] and 'NEW-1' in body['msg']
    assert not any(u.startswith('INSERT INTO TKD_QUESTIONS')
                   for u, _ in app.conn.statements)

def test_impor_update_draft_saja_dan_audit_hitungan(app):
    r = _client(app).post('/api/recruitment/tkd/questions/import',
                          json={'csv': CSV_TEXT + DRAFT_ROW, 'update_drafts': True})
    assert r.status_code == 200
    assert r.get_json() == {'inserted': 1, 'updated': 1, 'skipped': 1, 'errors': []}
    updates = [(u, p) for u, p in app.conn.statements
               if u.startswith('UPDATE TKD_QUESTIONS')]
    assert len(updates) == 1
    assert 'WHERE CODE=%S AND ACTIVE=0' in updates[0][0]
    assert updates[0][1][-1] == 'DRAFT-1'  # kode adalah parameter terakhir
    assert len(app.audits) == 1
    args, kwargs = app.audits[0]
    assert args[1] == 'tkd_questions_import'
    assert kwargs['new_data'] == {'inserted': 1, 'updated': 1, 'skipped': 1}
    assert 'nik' not in repr(kwargs).lower()

def test_ekspor_csv_memakai_header_lengkap(app):
    r = _client(app).get('/api/recruitment/tkd/questions/export.csv')
    assert r.status_code == 200
    assert r.mimetype == 'text/csv'
    assert r.get_data(as_text=True).splitlines()[0] == ','.join(CSV_COLUMNS)
    assert 'attachment' in r.headers['Content-Disposition']

def test_role_finance_tidak_boleh_impor(app):
    assert _client(app, 'finance').post('/api/recruitment/tkd/questions/import',
                                        json={'csv': CSV_TEXT}).status_code == 403
