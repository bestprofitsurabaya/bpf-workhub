"""CV Online memakai token sesi portal (Rilis C — Task C5).

NIK dan DOB tidak diambil dari form bila `s` sah: NIK berasal dari token,
tanggal lahir dan jenis kelamin diturunkan dari NIK. Tanpa `s`, perilaku lama
tetap dipertahankan sebagai fallback tautan langsung.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import routes_cv_online as cv  # noqa: E402
from modules.portal_token import issue_session_token  # noqa: E402
from tests.test_recruitment_service import (  # noqa: F401
    CV_BASE, NIK, _tanpa_rate_limit, cv_app,
)

BRANCH_TOKEN = 'tok-jkt-4'


def _split_values(text):
    parts, current, quoted = [], '', False
    for char in text:
        if char == "'":
            quoted = not quoted
        if char == ',' and not quoted:
            parts.append(current.strip())
            current = ''
        else:
            current += char
    parts.append(current.strip())
    return parts


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.lastrowid = 0

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split())
        upper = text.upper()
        p = tuple(params or ())
        self.rows = []
        if upper.startswith('SELECT'):
            table = next((t for t in self.conn.tables
                          if t.upper() in upper and t != 'cv_online_events'), None)
            if table == 'cv_online_branch_forms':
                self.rows = [r for r in self.conn.tables[table]
                             if str(r.get('form_token')) == str(p[0])
                             and int(r.get('active') or 0) == 1]
            elif table in ('branches', 'recruitment_cases', 'recruitment_steps',
                           'cv_online_submissions'):
                rows = self.conn.tables[table]
                if 'COUNT(*)' in upper:
                    self.rows = {'n': len(rows)}
                else:
                    self.rows = list(rows)
            return
        if upper.startswith('INSERT INTO'):
            match = re.match(r'INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES\s*(.*)',
                             text, re.I)
            assert match, text
            table = match.group(1).lower()
            cols = [c.strip().lower() for c in match.group(2).split(',')]
            values = _split_values(match.group(3))
            row, index = {}, 0
            for col, token in zip(cols, values):
                if '%s' in token.lower():
                    row[col] = p[index]
                    index += 1
                else:
                    row[col] = token.strip("'")
            if table not in self.conn.tables:
                self.conn.tables[table] = []
            self.conn.tables[table].append(row)
            self.lastrowid = len(self.conn.tables[table])
            self.conn.lastrowid = self.lastrowid
            return
        if upper.startswith('UPDATE'):
            self.conn.updates.append((text, p))

    def fetchone(self):
        if isinstance(self.rows, list):
            return self.rows[0] if self.rows else None
        return self.rows

    def fetchall(self):
        return self.rows if isinstance(self.rows, list) else []

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.tables = {
            'branches': [{'code': 'JKT', 'name': 'Jakarta'}],
            'cv_online_branch_forms': [
                {'branch_code': 'JKT', 'form_token': BRANCH_TOKEN, 'active': 1}],
            'recruitment_cases': [],
            'recruitment_steps': [],
            'case_branch_history': [],
            'cv_online_submissions': [],
            'cv_online_events': [],
        }
        self.updates = []
        self.commits = 0
        self.closed = False
        self.lastrowid = 0

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def db(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(cv, 'get_master_connection', lambda: conn)
    return conn


def _session(app, nik=NIK, branch='JKT'):
    with app.test_request_context('/'):
        return issue_session_token(nik, branch)


def _post(cv_app, payload, token=BRANCH_TOKEN):
    return cv_app.test_client().post(
        f'/api/cv-online/public?cabang=JKT&t={token}',
        data={**payload, 'consent': '1'})


def test_cv_meta_dengan_sesi_tidak_mengirim_nik_lengkap(cv_app, db):
    db.tables['recruitment_cases'].append(
        {'case_id': 'RC-1', 'nik': NIK, 'nama': 'Budi Santoso'})
    s = _session(cv_app)
    res = cv_app.test_client().get(
        '/api/cv-online/form-meta', query_string={'s': s, 't': BRANCH_TOKEN})
    data = res.get_json()
    assert res.status_code == 200
    assert data['nik_masked'] == '****0001'
    assert data['nama'] == 'Budi Santoso'
    assert NIK not in str(data)


def test_cv_submit_memakai_nik_dari_token(cv_app, db):
    s = _session(cv_app)
    payload = {k: v for k, v in CV_BASE.items() if k != 'nik'}
    res = _post(cv_app, {**payload, 's': s})
    assert res.status_code == 200, res.get_json()
    assert db.tables['cv_online_submissions'][-1]['nik'] == NIK


def test_cv_submit_menurunkan_dob_dari_nik(cv_app, db):
    nik = '3573014101900001'
    s = _session(cv_app, nik=nik)
    payload = {k: v for k, v in CV_BASE.items()
               if k not in ('nik', 'tanggal_lahir', 'jenis_kelamin')}
    res = _post(cv_app, {**payload, 's': s})
    assert res.status_code == 200, res.get_json()
    row = db.tables['cv_online_submissions'][-1]
    assert row['nik'] == nik
    assert str(row['tanggal_lahir'])[:10] == '1990-01-01'
    assert row['jenis_kelamin'] == 'Wanita'


def test_cv_submit_menolak_dob_manual_yang_bertentangan(cv_app, db):
    s = _session(cv_app)
    res = _post(cv_app, {**CV_BASE, 's': s, 'tanggal_lahir': '1985-05-05'})
    assert res.status_code == 200, res.get_json()
    assert str(db.tables['cv_online_submissions'][-1]['tanggal_lahir'])[:10] == '1999-01-01'


def test_cv_submit_menolak_sesi_dari_cabang_lain(cv_app, db):
    s = _session(cv_app, nik=NIK, branch='SBY')
    res = _post(cv_app, {**CV_BASE, 's': s})
    assert res.status_code == 403


def test_cv_submit_tanpa_sesi_masih_menerima_nik_form(cv_app, db):
    res = _post(cv_app, CV_BASE)
    assert res.status_code == 200, res.get_json()
    assert db.tables['cv_online_submissions'][-1]['nik'] == NIK
