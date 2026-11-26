"""Daftar orang rekrutmen & linimasa (Rilis C — C9)."""
import pytest
from flask import Flask

from modules import routes_recruitment as rr
from modules.portal_token import issue_card_token

NIK = '3573010101900001'
CASE = 'RC-1'


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        table = next((t for t in self.conn.tables if f'FROM {t.upper()}' in upper
                      or f'FROM {t.upper()} ' in upper), None)
        self.rows = list(self.conn.tables.get(table or '', []))
        if table == 'applicants':
            self.rows = [r for r in self.rows
                         if not r.get('nik') or r.get('link_status') != 'linked']

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Conn:
    def __init__(self, tables):
        self.tables = tables

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def close(self):
        pass


@pytest.fixture
def master():
    return _Conn({
        'recruitment_cases': [
            {'case_id': CASE, 'nik': NIK, 'nama': 'Budi Santoso',
             'first_branch': 'SBY', 'status': 'AKTIF'}],
        'recruitment_steps': [
            {'case_id': CASE, 'step_type': 'CV', 'status': 'SELESAI',
             'branch_code': 'JKT', 'completed_at': '2026-11-25 09:00:00'}],
        'case_branch_history': [
            {'case_id': CASE, 'branch_code': 'SBY'},
            {'case_id': CASE, 'branch_code': 'JKT'}],
        'recruitment_events': [
            {'id': 1, 'event_type': 'CV_SUBMITTED', 'event_at': '2026-11-25 09:00:00',
             'branch_code': 'JKT', 'actor_role': 'public', 'actor_name': '',
             'source_module': 'cv', 'note': '', 'metadata_json': '{}'}],
        'cv_online_submissions': [
            {'id': 2, 'nik': NIK, 'nama': 'Budi Santoso',
             'submitted_at': '2026-11-25 09:00:00'}],
        'first_work_submissions': [
            {'id': 7, 'nik': NIK, 'registration_no': 'FW-SBY-1',
             'submitted_at': '2026-11-26 09:00:00'}],
        'training_attendance': [],
        'branches': [{'code': 'SBY'}, {'code': 'JKT'}],
    })


@pytest.fixture
def branches():
    return {
        'SBY': _Conn({'applicants': [
            {'id': 7, 'display_id': 'PLM-SBY-7', 'nik': None,
             'nama_lengkap': 'Rina', 'link_status': 'unlinked',
             'status': 'interview'}]}),
        'JKT': _Conn({'applicants': []}),
    }


@pytest.fixture
def app(master, branches, monkeypatch):
    monkeypatch.setattr(rr, 'get_master_connection', lambda: master)
    monkeypatch.setattr(rr, 'get_db_connection',
                        lambda branch_code=None, **kw: branches.get(branch_code))
    app = Flask(__name__)
    app.secret_key = 'people-test'
    rr.register_recruitment_routes(app)
    return app


def _client(app, role='ga_hr', branch='SBY'):
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'staff'
        s['branch_code'] = branch
    return client


def test_people_menggabungkan_kasus_dan_pelamar_belum_tertaut(app):
    data = _client(app).get('/api/recruitment/people').get_json()['data']
    assert {row['case_id'] for row in data} >= {CASE, None}
    assert next(r for r in data if r['case_id'] is None)['link_status'] == 'unlinked'


def test_people_masking_nik_untuk_resepsionis(app):
    row = _client(app, role='receptionist').get(
        '/api/recruitment/people').get_json()['data'][0]
    assert row['nik_masked'] == '****0001'
    assert 'nik' not in row


def test_people_ga_hr_mendapat_nik_lengkap_dan_semua_cabang(app):
    data = _client(app, role='ga_hr').get('/api/recruitment/people').get_json()['data']
    assert any(r.get('nik') == NIK for r in data)
    assert {r['branch_code'] for r in data} == {'SBY', 'JKT'}


def test_people_resepsionis_hanya_cabangnya(app):
    data = _client(app, role='receptionist').get('/api/recruitment/people').get_json()['data']
    assert {r['branch_code'] for r in data} == {'SBY'}


def test_people_finance_hanya_view_firstwork(app):
    client = _client(app, role='finance')
    assert client.get('/api/recruitment/people').status_code == 403
    assert client.get('/api/recruitment/people',
                      query_string={'view': 'firstwork'}).status_code == 200


def test_detail_dan_timeline(app):
    client = _client(app)
    detail = client.get(f'/api/recruitment/people/{CASE}')
    assert detail.status_code == 200
    body = detail.get_json()['data']
    assert body['card_token']
    assert body['steps'][0]['step_type'] == 'CV'
    timeline = client.get(f'/api/recruitment/people/{CASE}/timeline')
    assert timeline.status_code == 200
    assert timeline.get_json()['data'][0]['event_type'] == 'CV_SUBMITTED'
    alias = client.get(f'/api/recruitment/cases/{CASE}/timeline')
    assert alias.get_json() == timeline.get_json()
