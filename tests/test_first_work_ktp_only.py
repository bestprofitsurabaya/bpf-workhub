"""FirstWork: KTP saja + profil dari CV + submit idempoten (Rilis C — C7)."""
import io

import pytest

from modules import routes_first_work as fw
from modules.portal_token import issue_card_token, issue_session_token
from tests.test_first_work_demographics import (  # noqa: F401
    APP, FakeConn, FakeCursor, _VALID,
)

NIK = '3573010101900001'
BRANCH_TOKEN = 'tok-SBY'
CV_ROW = {
    'id': 4, 'nik': NIK, 'nama': 'Budi Santoso',
    'pendidikan_terakhir': 'S1', 'no_hp': '081234567890',
    'tempat_lahir': 'Surabaya', 'tanggal_lahir': '1990-01-01',
    'jenis_kelamin': 'Pria', 'alamat': 'Jl. Contoh 1',
    'domisili': 'JAWA TIMUR', 'submitted_at': '2026-11-25 09:00:00',
}


class _Cursor(FakeCursor):
    @property
    def lastrowid(self):
        return self.conn.lastrowid

    @lastrowid.setter
    def lastrowid(self, value):
        pass


class Master(FakeConn):
    def __init__(self, cv_done=True, cv_row=None, existing=False):
        super().__init__()
        self.cv_done = cv_done
        self.cv_row = dict(cv_row or CV_ROW)
        self.existing = existing
        self.events = []

    def cursor(self, dictionary=False):
        return _Cursor(self, dictionary)

    def answer(self, q, params):
        upper = ' '.join(q.upper().split())
        if 'FROM RECRUITMENT_CASES' in upper:
            return [{'case_id': 'RC-1'}] if self.cv_row.get('nik') == params[0] else []
        if 'FROM RECRUITMENT_STEPS' in upper and 'CV' in upper:
            return [{'id': 1}] if self.cv_done else []
        if 'FROM CV_ONLINE_SUBMISSIONS' in upper:
            return [self.cv_row]
        if 'FROM FIRST_WORK_SUBMISSIONS WHERE NIK=%S' in upper:
            return ([{'id': 9, 'registration_no': 'FW-SBY-LAMA'}]
                    if self.existing else [])
        if 'INSERT INTO FIRST_WORK_EVENTS' in upper:
            self.events.append(params)
            return []
        return super().answer(q, params)


def _session(nik=NIK, branch='SBY'):
    with APP.test_request_context('/'):
        return issue_session_token(nik, branch)


def _submit(monkeypatch, conn, s=None, extra=None):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(fw, 'record_event', lambda *a, **k: True)
    monkeypatch.setattr(fw, 'upsert_case_step', lambda *a, **k: 'RC-1')
    monkeypatch.setattr(fw, 'save_file', lambda *a, **k: 'ktp-uji.jpg')
    monkeypatch.setattr(fw, '_ensure_ktp_scan', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_flag_reuse_signals', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_rate_ok', lambda ip: True)
    data = {'token': BRANCH_TOKEN, 'consent': '1'}
    if s:
        data['s'] = s
    data.update(extra or {})
    data['ktp'] = (io.BytesIO(b'\xff\xd8\xff\xe0' + b'x' * 16), 'ktp.jpg')
    with APP.test_client() as client:
        return client.post('/api/first-work/public?cabang=SBY&t=' + BRANCH_TOKEN,
                           data=data, content_type='multipart/form-data')


def test_firstwork_ditolak_bila_cv_belum_selesai(monkeypatch):
    conn = Master(cv_done=False)
    res = _submit(monkeypatch, conn, s=_session())
    assert res.status_code == 409
    assert 'CV' in res.get_json()['msg']


def test_nama_dan_pendidikan_diambil_dari_cv(monkeypatch):
    conn = Master()
    res = _submit(monkeypatch, conn, s=_session())
    assert res.status_code == 200, res.get_json()
    row = conn.submissions[-1]
    assert row['nik'] == NIK
    assert row['nama'] == CV_ROW['nama']
    assert row['pendidikan_raw'] == CV_ROW['pendidikan_terakhir']
    assert row['no_hp_norm'] == '081234567890'
    body = res.get_json()
    assert body.get('card_token')
    assert body.get('card_url')


def test_submit_idempoten_tanpa_baris_baru(monkeypatch):
    conn = Master(existing=True)
    res = _submit(monkeypatch, conn, s=_session())
    assert res.status_code == 200, res.get_json()
    assert res.get_json().get('already_exists') is True
    assert conn.submissions == []


def test_sesi_cabang_lain_ditolak(monkeypatch):
    conn = Master()
    res = _submit(monkeypatch, conn, s=_session(branch='JKT'))
    assert res.status_code == 403


def test_dob_dari_form_diabaikan_saat_sesi_aktif(monkeypatch):
    conn = Master()
    res = _submit(monkeypatch, conn, s=_session(),
                  extra={'tanggal_lahir': '1970-01-01'})
    assert res.status_code == 200, res.get_json()
    assert str(conn.submissions[-1].get('tanggal_lahir'))[:10] == CV_ROW['tanggal_lahir']
