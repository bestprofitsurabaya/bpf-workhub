"""
Unit Tests — Integritas Dokumen (document_registry) v2.35.0 (Tahap 6/6 ISO).

- ensure_document_registry  → DDL idempoten
- register_pdf / lookup_pdf → hash SHA-256 konsisten; DB down tidak fatal
- POST /api/documents/verify  → valid (found) / tidak terdaftar (not found) /
                                 validasi (bukan PDF / kosong)
- GET  /api/admin/documents   → list registri (admin only)

Pola: DB di-fake (monkeypatch modules.config.get_master_connection).
"""

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import hashlib  # noqa: E402

from flask import Flask  # noqa: E402

import modules.config as cfg  # noqa: E402
import modules.doc_integrity as di  # noqa: E402
import modules.routes_documents as rd  # noqa: E402


class FakeCursor:
    def __init__(self, rows=None, rowcount=0, dictionary=True):
        self.rows = rows or []
        self.rowcount = rowcount
        self.dictionary = dictionary
        self.log = []

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))
        return None

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None, rowcount=0):
        self.cur = FakeCursor(rows, rowcount)
        self.commits = 0

    def cursor(self, dictionary=True):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


PDF_BYTES = b'%PDF-1.4 fake dokumen tanda terima \x00\x01\x02'


def _fake_master(monkeypatch, conn):
    monkeypatch.setattr(cfg, 'get_master_connection', lambda: conn)


# ================================================================
# Logika murni
# ================================================================
class TestEnsure:
    def test_ddl_idempoten(self):
        conn = FakeConn()
        assert di.ensure_document_registry(conn=conn) is True
        assert di.ensure_document_registry(conn=conn) is True
        creates = [sql for sql, _ in conn.cur.log if 'CREATE TABLE' in sql]
        assert len(creates) == 2  # dipanggil dua kali, dua-duanya jalan

    def test_tanpa_koneksi(self, monkeypatch):
        _fake_master(monkeypatch, None)
        assert di.ensure_document_registry() is False


class TestRegisterLookup:
    def test_register_menyimpan_sha256(self, monkeypatch):
        conn = FakeConn()
        _fake_master(monkeypatch, conn)
        res = di.register_pdf('water_receipt', 'WTR-SBY-20260905-0001', PDF_BYTES,
                              signer_name='Finance Officer', signer_role='finance',
                              branch_code='SBY', filename='TandaTerima.pdf')
        assert res is not None
        sha = hashlib.sha256(PDF_BYTES).hexdigest()
        assert res['sha256'] == sha
        sql, params = conn.cur.log[0]
        assert 'INSERT INTO document_registry' in sql
        assert params[0] == 'water_receipt'
        assert params[2] == 'SBY'
        assert params[3] == sha
        assert params[6] == 'Finance Officer'

    def test_register_pdf_kosong(self, monkeypatch):
        _fake_master(monkeypatch, FakeConn())
        assert di.register_pdf('x', 'y', b'') is None

    def test_register_db_error_tidak_fatal(self, monkeypatch):
        class Boom:
            def cursor(self, dictionary=True):
                raise Exception('db down')

        _fake_master(monkeypatch, Boom())
        assert di.register_pdf('ot_form_driver', 'OTL-1', PDF_BYTES) is None

    def test_lookup_cocok(self, monkeypatch):
        sha = hashlib.sha256(PDF_BYTES).hexdigest()
        row = {'id': 1, 'doc_type': 'water_receipt', 'doc_no': 'WTR-1',
               'branch_code': 'SBY', 'sha256': sha, 'bytes_size': len(PDF_BYTES),
               'filename': 'TandaTerima.pdf', 'signer_name': 'Finance Officer',
               'signer_role': 'finance', 'meta': None,
               'created_at': '2026-09-05 21:00:00'}
        _fake_master(monkeypatch, FakeConn(rows=[row]))
        got = di.lookup_pdf(PDF_BYTES)
        assert got is not None and got['doc_no'] == 'WTR-1'
        assert got['sha256'] == sha

    def test_lookup_tidak_terdaftar(self, monkeypatch):
        _fake_master(monkeypatch, FakeConn(rows=[]))
        assert di.lookup_pdf(b'%PDF-1.4 lain') is None

    def test_row_to_dict_meta_json_string(self):
        r = {'id': 1, 'doc_type': 'a', 'doc_no': 'b', 'branch_code': 'SBY',
             'sha256': 'x' * 64, 'bytes_size': 10, 'filename': 'f.pdf',
             'signer_name': 'n', 'signer_role': 'r',
             'meta': '{"k": 1}', 'created_at': '2026-09-05 21:00:00'}
        d = di._row_to_dict(r)
        assert d['meta'] == {'k': 1}
        assert d['bytes_size'] == 10


# ================================================================
# Routes
# ================================================================
def _client(monkeypatch, role='admin'):
    monkeypatch.setattr(rd, 'log_activity_async', lambda *a, **k: None)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rd.register_document_routes(app)
    client = app.test_client()
    if role:
        with client.session_transaction() as s:
            s['user_role'] = role
            s['full_name'] = 'Admin Test'
    return client


class TestVerifyRoute:
    def test_valid_terdaftar(self, monkeypatch):
        sha = hashlib.sha256(PDF_BYTES).hexdigest()
        row = {'id': 1, 'doc_type': 'water_receipt', 'doc_no': 'WTR-SBY-1',
               'branch_code': 'SBY', 'sha256': sha, 'bytes_size': len(PDF_BYTES),
               'filename': 'TandaTerima.pdf', 'signer_name': 'Finance Officer',
               'signer_role': 'finance', 'meta': None,
               'created_at': '2026-09-05 21:00:00'}
        monkeypatch.setattr(di, 'lookup_pdf', lambda b: row)
        c = _client(monkeypatch, role='finance')
        r = c.post('/api/documents/verify',
                   data={'file': (io.BytesIO(PDF_BYTES), 'TandaTerima.pdf')},
                   content_type='multipart/form-data')
        assert r.status_code == 200
        d = r.get_json()
        assert d['found'] is True
        assert d['document']['doc_no'] == 'WTR-SBY-1'
        assert d['document']['signer_name'] == 'Finance Officer'

    def test_tidak_terdaftar(self, monkeypatch):
        monkeypatch.setattr(di, 'lookup_pdf', lambda b: None)
        c = _client(monkeypatch, role='admin')
        r = c.post('/api/documents/verify',
                   data={'file': (io.BytesIO(PDF_BYTES), 'x.pdf')},
                   content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.get_json()['found'] is False

    def test_bukan_pdf_ditolak(self, monkeypatch):
        c = _client(monkeypatch)
        r = c.post('/api/documents/verify',
                   data={'file': (io.BytesIO(b'hello'), 'x.txt')},
                   content_type='multipart/form-data')
        assert r.status_code == 400

    def test_tanpa_file(self, monkeypatch):
        c = _client(monkeypatch)
        assert c.post('/api/documents/verify').status_code == 400

    def test_butuh_login(self):
        # tanpa sesi → 401 (role_required)
        app = Flask(__name__)
        app.secret_key = 'x'
        rd.register_document_routes(app)
        r = app.test_client().post('/api/documents/verify')
        assert r.status_code in (401, 302)

    def test_verify_tanpa_db_aman(self, monkeypatch):
        _fake_master(monkeypatch, None)
        c = _client(monkeypatch, role='ga')
        r = c.post('/api/documents/verify',
                   data={'file': (io.BytesIO(PDF_BYTES), 'x.pdf')},
                   content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.get_json()['found'] is False


class TestAdminListRoute:
    def test_admin_bisa_list(self, monkeypatch):
        rows = [{'id': 1, 'doc_type': 'water_receipt', 'doc_no': 'WTR-1',
                 'branch_code': 'SBY', 'sha256': 'a' * 64, 'bytes_size': 10,
                 'filename': 'f.pdf', 'signer_name': 'Finance',
                 'signer_role': 'finance', 'meta': None,
                 'created_at': '2026-09-05 21:00:00'}]
        _fake_master(monkeypatch, FakeConn(rows=rows))
        c = _client(monkeypatch, role='admin')
        r = c.get('/api/admin/documents')
        assert r.status_code == 200
        d = r.get_json()
        assert d['count'] == 1
        assert d['documents'][0]['doc_no'] == 'WTR-1'

    def test_non_admin_ditolak(self, monkeypatch):
        c = _client(monkeypatch, role='ga')
        assert c.get('/api/admin/documents').status_code == 403

    def test_tanpa_login(self):
        app = Flask(__name__)
        app.secret_key = 'x'
        rd.register_document_routes(app)
        assert app.test_client().get('/api/admin/documents').status_code in (401, 302)
