"""Regresi intake pelamar berbasis NIK (Rilis C — Task C3).

Yang diuji: NIK wajib 16 digit di intake manual, duplikat NIK cabang ditolak,
kasus master dibuat sekali untuk NIK yang sama, tautan NIK untuk baris lama,
dan alasan `resigned` selalu wajib beserta event linimasa.
"""
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import modules.routes_applicants as ap  # noqa: E402
import modules.routes_receptionist as rr  # noqa: E402

NIK = '3573010101900001'


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.lastrowid = 0

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split())
        upper = text.upper()
        p = tuple(params or ())
        if upper.startswith('SELECT ID, DISPLAY_ID FROM APPLICANTS WHERE NIK=%S'):
            self.rows = [{'id': r['id'], 'display_id': r['display_id']}
                         for r in self.conn.applicants
                         if r.get('nik') == p[0]
                         and (len(p) < 2 or r.get('id') != p[1])]
            return
        if upper.startswith('SELECT ID, DISPLAY_ID, NAMA_LENGKAP FROM APPLICANTS WHERE ID=%S'):
            found = [dict(r) for r in self.conn.applicants if r.get('id') == p[0]]
            self.rows = [{'id': r['id'], 'display_id': r['display_id'],
                          'nama_lengkap': r.get('nama_lengkap', '')} for r in found]
            return
        if upper.startswith('SELECT * FROM APPLICANTS WHERE ID=%S') or \
                upper.startswith('SELECT DISPLAY_ID FROM APPLICANTS WHERE ID=%S'):
            found = [dict(r) for r in self.conn.applicants if r.get('id') == p[0]]
            if upper.startswith('SELECT DISPLAY_ID'):
                self.rows = [{'display_id': r['display_id']} for r in found]
            else:
                self.rows = found
            return
        if upper.startswith('SELECT DISPLAY_ID, NIK FROM APPLICANTS WHERE ID=%S'):
            self.rows = [{'display_id': r['display_id'], 'nik': r.get('nik')}
                         for r in self.conn.applicants if r.get('id') == p[0]]
            return
        if upper.startswith('SELECT COUNT(*)') and 'APPLICANT_ATTENDANCE' in upper:
            n = sum(1 for r in self.conn.attendance if r.get('applicant_id') == p[0])
            self.rows = [{'c': n}]
            return
        if upper.startswith('INSERT INTO APPLICANTS'):
            match = re.search(r'\(([^)]*)\)\s*VALUES', text)
            cols = [c.strip() for c in match.group(1).split(',')]
            row = {c: None for c in cols}
            row.update(dict(zip(cols, p)))
            self.conn.counter += 1
            row['id'] = self.conn.counter
            self.conn.applicants.append(row)
            self.lastrowid = row['id']
            self.conn.lastrowid = row['id']
            return
        if upper.startswith('UPDATE APPLICANTS SET'):
            # `text` mempertahankan huruf asli nilai literal ('linked', 'resigned').
            match = re.search(r'SET\s+(.*?)\s+WHERE\s+ID=%S', text, re.I)
            if match:
                changes = {}
                param_index = 0
                for part in match.group(1).split(','):
                    name, _, value = part.strip().partition('=')
                    name = name.strip().lower()
                    if re.search(r'%s', value, re.I):
                        changes[name] = p[param_index]
                        param_index += 1
                    elif 'NOW()' in value:
                        changes[name] = datetime.now()
                    else:
                        changes[name] = value.strip("'")
                for row in self.conn.applicants:
                    if row.get('id') == p[-1]:
                        row.update(changes)
            return
        if upper.startswith('INSERT INTO APPLICANT_ATTENDANCE'):
            self.conn.attendance.append({'applicant_id': p[0], 'stage': p[1]})
            return
        if upper.startswith('INSERT IGNORE INTO APPLICANT_USER_OPTIONS'):
            return
        if upper.startswith('SELECT ID FROM EMPLOYEE_INOUT'):
            self.rows = []
            return

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.applicants = []
        self.attendance = []
        self.counter = 0
        self.lastrowid = 0
        self.commits = 0

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def branch_db():
    return _FakeConn()


@pytest.fixture
def master():
    return SimpleNamespace(case_rows=[], branch_history=[], events=[])


def _client(monkeypatch, branch_db, master, branch='SBY', role='receptionist',
            db_getter=None):
    getter = db_getter or (lambda: branch_db)
    for module in (rr, ap):
        monkeypatch.setattr(module, 'get_db_connection', getter)
        monkeypatch.setattr(module, 'log_activity_async', lambda *a, **k: None)

    def _ensure_case(nik, nama=None, branch_code='', dob=None,
                     source='manual', conn=None):
        row = next((r for r in master.case_rows if r['nik'] == nik), None)
        if row is None:
            row = {'nik': nik, 'nama': nama, 'branch_code': branch_code,
                   'source': source}
            master.case_rows.append(row)
        if branch_code not in master.branch_history:
            master.branch_history.append(branch_code)
        return 'RC-1'

    def _record(case_id, nik, event_type, **kwargs):
        master.events.append({'event_type': event_type, 'nik': nik,
                              'case_id': case_id, **kwargs})
        return True

    for module in (rr, ap):
        monkeypatch.setattr(module, 'ensure_case', _ensure_case, raising=False)
        monkeypatch.setattr(module, 'record_event', _record, raising=False)

    app = Flask(__name__)
    app.secret_key = 'test-applicants-nik'
    rr.register_receptionist_routes(app)
    ap.register_applicant_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'resepsionis'
        s['full_name'] = 'Rina'
        s['branch_code'] = branch
        s['stepup_until'] = 9_999_999_999
    return client


def _add_row(db, **overrides):
    row = {'id': db.counter + 1, 'display_id': f'PLM-SBY-{db.counter + 1}',
           'nik': None, 'nama_lengkap': 'Budi', 'no_hp': '081234567890',
           'status': 'interview', 'verified_at': None, 'resign_reason': '',
           'created_at': datetime(2026, 11, 1)}
    row.update(overrides)
    db.counter += 1
    db.applicants.append(row)
    return row


def test_manual_wajib_nik_16_digit(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    r = client.post('/api/applicants/manual', json={'nama_lengkap': 'Budi'})
    assert r.status_code == 400
    assert 'NIK' in r.get_json()['msg']


def test_manual_nik_ganda_ditolak_409(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    _add_row(branch_db, nik=NIK, display_id='PLM-SBY-1')
    r = client.post('/api/applicants/manual',
                    json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert r.status_code == 409
    assert 'PLM-SBY-1' in r.get_json()['msg']


def test_manual_membuat_kasus_dan_event(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    r = client.post('/api/applicants/manual',
                    json={'nama_lengkap': 'Budi', 'nik': NIK})
    assert r.status_code == 200, r.get_json()
    assert master.case_rows[0]['nik'] == NIK
    assert any(e['event_type'] == 'RECEPTIONIST_CREATED' for e in master.events)
    row = branch_db.applicants[-1]
    assert row['nik'] == NIK
    assert row['link_status'] == 'linked'
    assert row.get('verified_at') is None
    assert not any(e['event_type'] == 'VERIFIED' for e in master.events)


def test_manual_dengan_verify_menulis_event_verified(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    r = client.post('/api/applicants/manual',
                    json={'nama_lengkap': 'Budi', 'nik': NIK, 'verify': True})
    assert r.status_code == 200
    assert any(e['event_type'] == 'VERIFIED' for e in master.events)


def test_nik_sama_di_cabang_lain_memakai_kasus_sama(monkeypatch, master):
    db_sby, db_jkt = _FakeConn(), _FakeConn()

    def _db_by_session():
        return db_jkt if session.get('branch_code') == 'JKT' else db_sby

    sby = _client(monkeypatch, db_sby, master, branch='SBY', db_getter=_db_by_session)
    jkt = _client(monkeypatch, db_jkt, master, branch='JKT', db_getter=_db_by_session)
    assert sby.post('/api/applicants/manual',
                    json={'nama_lengkap': 'Budi', 'nik': NIK}).status_code == 200
    assert jkt.post('/api/applicants/manual',
                    json={'nama_lengkap': 'Budi', 'nik': NIK}).status_code == 200
    assert len(master.case_rows) == 1
    assert set(master.branch_history) == {'SBY', 'JKT'}


def test_link_nik_menautkan_baris_lama(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    row = _add_row(branch_db, nik=None, link_status='unlinked')
    r = client.post(f'/api/applicants/{row["id"]}/link-nik', json={'nik': NIK})
    assert r.status_code == 200, r.get_json()
    assert row['nik'] == NIK
    assert row['link_status'] == 'linked'
    assert master.events[-1]['event_type'] == 'NIK_LINKED'


def test_resigned_selalu_wajib_alasan(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    row = _add_row(branch_db)
    r = client.post(f'/api/applicants/{row["id"]}/status',
                    json={'status': 'resigned'})
    assert r.status_code == 400
    assert 'alasan' in r.get_json()['msg'].lower()


def test_resigned_dengan_alasan_menulis_event(monkeypatch, branch_db, master):
    client = _client(monkeypatch, branch_db, master)
    row = _add_row(branch_db, status='training_1')
    r = client.post(f'/api/applicants/{row["id"]}/status',
                    json={'status': 'resigned', 'reason': 'pindah kerja'})
    assert r.status_code == 200, r.get_json()
    assert row['status'] == 'resigned'
    assert row['resign_reason'] == 'pindah kerja'
    assert master.events[-1]['event_type'] == 'RESIGNED'


class _MasterCursor:
    def __init__(self, nik):
        self.nik = nik
        self.rows = []

    def execute(self, sql, params=None):
        self.rows = ([{'nik': self.nik}]
                     if 'CV_ONLINE_SUBMISSIONS' in str(sql).upper() else [])

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


def _patch_sync(monkeypatch, branch_db, master, sheet_rows, cv_nik=NIK):
    monkeypatch.setattr(rr, 'get_db_connection', lambda: branch_db)
    monkeypatch.setattr(rr, '_get_sheet_url', lambda conn, key: 'url')
    monkeypatch.setattr(rr, '_fetch_sheet_rows', lambda url: sheet_rows)
    master_db = SimpleNamespace(
        cursor=lambda dictionary=False: _MasterCursor(cv_nik),
        close=lambda: None)
    monkeypatch.setattr(rr, 'get_master_connection', lambda: master_db,
                        raising=False)

    def _ensure_case(nik, nama=None, branch_code='', dob=None,
                     source='manual', conn=None):
        if not any(r['nik'] == nik for r in master.case_rows):
            master.case_rows.append({'nik': nik, 'nama': nama, 'source': source})
        return 'RC-1'

    def _record(case_id, nik, event_type, **kwargs):
        master.events.append({'event_type': event_type, 'nik': nik})

    monkeypatch.setattr(rr, 'ensure_case', _ensure_case)
    monkeypatch.setattr(rr, 'record_event', _record)


_SHEET_ROW = {
    'Tanggal Interview': '11/1/2026',
    'Jam': '10:00',
    'Nama Lengkap': 'Budi',
    'Pendidikan Terakhir': 'S1',
    'Nomor Telepon/HP': '081234567890',
}


def test_sync_sheet_menautkan_nik_dari_sheet(monkeypatch, branch_db, master):
    _patch_sync(monkeypatch, branch_db, master,
                [{**_SHEET_ROW, 'NIK': NIK}])
    result = rr._do_sync_applicants()
    assert result['added'] == 1
    row = branch_db.applicants[-1]
    assert row['nik'] == NIK
    assert row['link_status'] == 'linked'
    assert any(e['event_type'] == 'NIK_LINKED' for e in master.events)


def test_sync_sheet_tanpa_nik_memakai_cv_terbaru(monkeypatch, branch_db, master):
    _patch_sync(monkeypatch, branch_db, master, [_SHEET_ROW], cv_nik=NIK)
    result = rr._do_sync_applicants()
    assert result['added'] == 1
    assert branch_db.applicants[-1]['nik'] == NIK
    assert branch_db.applicants[-1]['nik_source'] == 'cv_match'
