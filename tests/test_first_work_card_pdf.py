"""Kartu Business Consultant A6 landscape + unduhan publik bertoken (C8)."""
import io

import pytest
from flask import Flask

from modules import routes_first_work as fw
from modules.portal_token import issue_card_token
from tests.pdf_text import pdf_text

NIK = '3573010101900001'
ROW = {'id': 7, 'nik': NIK, 'nama': 'Budi Santoso', 'branch_code': 'SBY',
       'registration_no': 'FW-SBY-1'}


def test_kartu_business_consultant_a6_tanpa_nik_lengkap():
    from modules.pdf_generator import BusinessConsultantCardPDF
    pdf = BusinessConsultantCardPDF()
    pdf.generate(ROW)
    buf = io.BytesIO()
    pdf.output(buf)
    text = pdf_text(buf.getvalue())
    assert 'Business Consultant' in text
    assert NIK not in text
    assert pdf.w > pdf.h  # A6 landscape (148 × 105 mm)


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).upper().split())
        if 'FROM FIRST_WORK_SUBMISSIONS WHERE ID=%S' in text:
            self.rows = [dict(ROW)] if params[0] == ROW['id'] else []
        elif 'INSERT INTO FIRST_WORK_EVENTS' in text:
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Conn:
    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: _Conn())
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_row_allowed', lambda row, conn: True)
    app = Flask(__name__)
    app.secret_key = 'card-test'
    fw.register_first_work_routes(app)
    return app.test_client()


def test_kartu_publik_dengan_token_sah(client):
    with client.application.test_request_context('/'):
        token = issue_card_token(ROW['id'])
    res = client.get(f"/api/first-work/card/{ROW['id']}.pdf?t={token}")
    assert res.status_code == 200
    assert res.headers['Content-Type'] == 'application/pdf'
    assert res.headers['Cache-Control'] == 'no-store'
    assert NIK.encode() not in res.get_data()


def test_kartu_token_untuk_id_lain_ditolak(client):
    with client.application.test_request_context('/'):
        token = issue_card_token(ROW['id'] + 1)
    res = client.get(f"/api/first-work/card/{ROW['id']}.pdf?t={token}")
    assert res.status_code == 403


def test_kartu_tanpa_token_tanpa_sesi_ditolak(client):
    assert client.get(f"/api/first-work/card/{ROW['id']}.pdf").status_code in (401, 403)
