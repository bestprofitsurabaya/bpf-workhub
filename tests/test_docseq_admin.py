"""
Unit Tests — Admin Nomor Dokumen (doc_sequences) v2.29.11.

- GET  /api/admin/doc-sequences          → daftar counter per cabang (admin only)
- POST /api/admin/doc-sequences/reset    → reset counter (cabang, prefix[, tanggal])
- parse_seq_key / read_sequences / reset_sequences (logika DB di-fake)

Pola sama dengan test_branches (DB di-fake, sesi lewat test client).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_docseq as rd  # noqa: E402


# ================================================================
# Fake conn/cursor untuk logika DB (read_sequences / reset_sequences)
# ================================================================
class FakeCursor:
    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount
        self.log = []

    def execute(self, sql, params=None):
        self.log.append((sql, params or ()))
        return None

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return None

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

    def close(self):
        pass


BRANCHES = [
    {'code': 'SBY', 'name': 'Cabang Surabaya', 'db_name': 'bpf_asset_system', 'is_active': 1},
    {'code': 'MLG', 'name': 'Cabang Malang', 'db_name': 'bpf_branch_malang', 'is_active': 1},
]


def _make_client(monkeypatch, role='admin'):
    monkeypatch.setattr(rd, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rd.bm, 'list_branches', lambda: [dict(b) for b in BRANCHES])
    monkeypatch.setattr(rd.bm, 'get_branch',
                        lambda code: next((b for b in BRANCHES if b['code'] == code), None))
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rd.register_docseq_routes(app)
    client = app.test_client()
    if role:
        with client.session_transaction() as s:
            s['user_role'] = role
            # v2.37.0: scoping admin membaca username sesi — sesi admin nyata
            # selalu punya user_name (akun pusat 'admin').
            s['user_name'] = 'admin'
            s['branch_code'] = 'SBY'
    return client


# ================================================================
# Logika murni
# ================================================================
class TestParseSeqKey:
    def test_format_standar(self):
        assert rd.parse_seq_key('SBY|WTR|20260905') == ('SBY', 'WTR', '20260905')

    def test_format_2_bagian(self):
        assert rd.parse_seq_key('SBY|WTR') == ('SBY', 'WTR', '')

    def test_tahan_format_tak_dikenal(self):
        assert rd.parse_seq_key('') == ('', '', '')
        assert rd.parse_seq_key('xxx') == ('xxx', '', '')


class TestReadSequences:
    def test_parse_dan_urut(self, monkeypatch):
        conn = FakeConn(rows=[
            {'seq_key': 'SBY|WTR|20260905', 'seq': 3},
            {'seq_key': 'SBY|OTL|20260904', 'seq': 1},
        ])
        monkeypatch.setattr(rd, '_branch_conn', lambda branch: conn)
        rows = rd.read_sequences({'code': 'SBY', 'db_name': 'bpf_asset_system'})
        assert rows[0]['branch'] == 'SBY'
        assert rows[0]['prefix'] == 'WTR'
        assert rows[0]['prefix_label'] == 'Tanda Terima Air Minum'
        assert rows[0]['date'] == '20260905'
        assert rows[0]['seq'] == 3
        assert rows[1]['seq_key'] == 'SBY|OTL|20260904'

    def test_db_tidak_tersedia(self, monkeypatch):
        monkeypatch.setattr(rd, '_branch_conn', lambda branch: None)
        assert rd.read_sequences({'code': 'X'}) == []


class TestResetSequences:
    def _run(self, monkeypatch, conn, date):
        monkeypatch.setattr(rd, '_branch_conn', lambda branch: conn)
        n = rd.reset_sequences({'code': 'SBY'}, 'WTR', date)
        return n, conn

    def test_reset_satu_tanggal(self, monkeypatch):
        n, conn = self._run(monkeypatch, FakeConn(rowcount=2), '20260905')
        assert n == 2
        sql, params = conn.cur.log[0]
        assert 'DELETE FROM doc_sequences' in sql
        assert 'seq_key=%s' in sql
        assert params == ('SBY|WTR|20260905',)
        assert conn.commits == 1

    def test_reset_semua_tanggal(self, monkeypatch):
        n, conn = self._run(monkeypatch, FakeConn(rowcount=1), '')
        assert n == 1
        sql, params = conn.cur.log[0]
        assert 'LIKE' in sql
        assert params == ('SBY|WTR|%',)


# ================================================================
# Route API
# ================================================================
class TestDocSeqAPI:
    def test_list_wajib_admin(self, monkeypatch):
        c = _make_client(monkeypatch, role='ga')
        assert c.get('/api/admin/doc-sequences').status_code == 403
        c2 = _make_client(monkeypatch, role=None)
        assert c2.get('/api/admin/doc-sequences').status_code == 401

    def test_list_ok(self, monkeypatch):
        monkeypatch.setattr(rd, 'read_sequences', lambda branch: [{
            'seq_key': f"{branch['code']}|WTR|20260905",
            'branch': branch['code'], 'prefix': 'WTR',
            'prefix_label': 'Tanda Terima Air Minum', 'date': '20260905', 'seq': 3,
        }])
        c = _make_client(monkeypatch)
        r = c.get('/api/admin/doc-sequences')
        assert r.status_code == 200
        data = r.get_json()['branches']
        assert [b['code'] for b in data] == ['SBY', 'MLG']
        assert data[0]['sequences'][0]['seq'] == 3

    def test_list_cabang_nonaktif_kosong(self, monkeypatch):
        def _fake_read(branch):
            return [{'seq_key': f"{branch['code']}|WTR|20260905", 'branch': branch['code'],
                     'prefix': 'WTR', 'prefix_label': 'x', 'date': '20260905', 'seq': 1}]
        monkeypatch.setattr(rd, 'read_sequences', _fake_read)
        c = _make_client(monkeypatch)
        # read_sequences hanya dipanggil utk cabang aktif — nonaktif → []
        called = []
        def _wrap(branch):
            if branch.get('is_active'):
                called.append(branch['code'])
                return _fake_read(branch)
            return []
        monkeypatch.setattr(rd, 'read_sequences', _wrap)
        r = c.get('/api/admin/doc-sequences')
        assert r.status_code == 200
        assert called == ['SBY', 'MLG']

    def test_reset_ok(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rd, 'reset_sequences',
                            lambda branch, prefix, date='': seen.update(
                                branch=branch['code'], prefix=prefix, date=date) or 2)
        c = _make_client(monkeypatch)
        r = c.post('/api/admin/doc-sequences/reset',
                   json={'branch_code': 'SBY', 'prefix': 'WTR', 'date': '20260905'})
        assert r.status_code == 200
        d = r.get_json()
        assert d['status'] == 'success'
        assert '0001' in d['msg']
        assert seen == {'branch': 'SBY', 'prefix': 'WTR', 'date': '20260905'}

    def test_reset_validasi(self, monkeypatch):
        c = _make_client(monkeypatch)
        assert c.post('/api/admin/doc-sequences/reset',
                      json={'branch_code': 'SBY'}).status_code == 400
        assert c.post('/api/admin/doc-sequences/reset',
                      json={'branch_code': 'SBY', 'prefix': 'WTR',
                            'date': '2026-09-05'}).status_code == 400
        assert c.post('/api/admin/doc-sequences/reset',
                      json={'branch_code': 'ZZZ', 'prefix': 'WTR',
                            'date': '20260905'}).status_code == 404

    def test_reset_wajib_admin(self, monkeypatch):
        c = _make_client(monkeypatch, role='finance')
        assert c.post('/api/admin/doc-sequences/reset',
                      json={'branch_code': 'SBY', 'prefix': 'WTR'}).status_code == 403