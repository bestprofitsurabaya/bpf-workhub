"""
Unit Tests — Approval Berjenjang (v2.36.0).

ACC atasan sebelum diproses back-office:
- build_chain       : rantai default per role + override users.manager_username;
- create_approval   : upsert jurnal (re-submit me-reset ke langkah 1);
- decide            : urutan langkah, tolak final, anti self-approval,
                      langkah ber-role cocok utk pemegang role yang sama;
- gate_allows       : pending/rejected → 409 SUPERVISOR_APPROVAL_REQUIRED,
                      tanpa baris / approved / DB down → lolos (fail-open);
- endpoint          : /api/approvals (daftar), decision (ACC/tolak), 401/403;
- endpoint produksi : submit kasbon mencatat jurnal; approve-ga kasbon
                      terblokir 409 saat masih pending ACC atasan.

DB di-fake (pola test_stepup / test_docseq_admin) — tidak butuh MariaDB.

Jalankan:
    python3 -m pytest tests/test_approvals.py -v
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

import modules.approvals as am
from modules.approvals import (APPROVAL_CODE, build_chain, create_approval,
                               approval_status, decide, gate_allows,
                               decision_allowed, register_approval_routes,
                               gate_approval)


# ================================================================
# Fake DB: approval_requests + users in-memory
# ================================================================
class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rows = []
        self.rowcount = 0
        self.lastrowid = 0

    def _appr_row(self, doc_type, doc_ref):
        return self.store['appr'].get((doc_type, int(doc_ref)))

    def execute(self, sql, params=None):
        sql = sql or ''
        up = ' '.join(sql.split()).upper()
        self.rows = []
        if 'FROM APPROVAL_REQUESTS' in up and up.startswith('SELECT'):
            if params:
                row = self._appr_row(params[0], params[1])
                self.rows = [dict(row)] if row else []
            else:
                self.rows = [dict(r) for r in self.store['appr'].values()
                             if r.get('status') == 'pending']
            self.rowcount = len(self.rows)
        elif 'FROM USERS' in up and up.startswith('SELECT'):
            # _lookup_supervisor: JOIN users u2 (manager aktif)
            uname = params[0]
            u = self.store['users'].get(uname)
            mgr = u.get('manager_username') if u else None
            if mgr and self.store['users'].get(mgr, {}).get('is_active', False):
                self.rows = [{'manager': mgr}]
            self.rowcount = len(self.rows)
        elif up.startswith('INSERT INTO APPROVAL_REQUESTS'):
            (doc_type, doc_ref, display_id, requested_by, requester_role,
             branch_code, chain) = params[:7]
            key = (doc_type, int(doc_ref))
            if key in self.store['appr']:
                # ON DUPLICATE KEY UPDATE → reset ke langkah 1 pending
                row = self.store['appr'][key]
                row.update(step=1, status='pending', decided_by='',
                           decided_at=None, note='')
                self.rowcount = 2
            else:
                self.store['appr'][key] = {
                    'id': len(self.store['appr']) + 1, 'doc_type': doc_type,
                    'doc_ref': int(doc_ref), 'display_id': display_id,
                    'requested_by': requested_by,
                    'requester_role': requester_role,
                    'branch_code': branch_code, 'chain': chain, 'step': 1,
                    'status': 'pending', 'decided_by': '',
                    'decided_at': None, 'note': '',
                }
                self.lastrowid = self.store['appr'][key]['id']
                self.rowcount = 1
        elif up.startswith('UPDATE APPROVAL_REQUESTS'):
            row = next((r for r in self.store['appr'].values()
                        if r['id'] == params[-1]), None)
            if row:
                if 'SET STATUS' in up:
                    row['status'] = 'rejected' if 'REJECTED' in up else 'approved'
                    row['decided_by'] = params[0]
                    row['note'] = params[1]
                else:  # SET step=%s → maju langkah
                    row['step'] = params[0]
                    row['decided_by'] = params[1]
                    row['note'] = params[2]
            self.rowcount = 1 if row else 0
        elif up.startswith('INSERT INTO FUEL_CASH_REQUESTS'):
            self.lastrowid = 1
            self.rowcount = 1
        # SQL lain (fallback display id, dsb.) → diabaikan diam-diam

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self, dictionary=True):
        return FakeCursor(self.store)

    def commit(self):
        self.store['commits'] = self.store.get('commits', 0) + 1

    def rollback(self):
        self.store['rollbacks'] = self.store.get('rollbacks', 0) + 1

    def close(self):
        pass


@pytest.fixture
def store():
    return {
        'appr': {},
        'users': {
            'Budi Driver': {'username': 'budi', 'full_name': 'Budi Driver',
                            'is_active': True, 'manager_username': None},
            'chief': {'username': 'chief', 'full_name': 'Chief Satu',
                      'is_active': True, 'manager_username': None},
        },
    }


def _conn(store):
    return FakeConn(store)


# jsonify (respons 409 gate) butuh application context — dipakai tes langsung.
_APP = Flask(__name__)


# ================================================================
# build_chain
# ================================================================
class TestBuildChain:
    def test_default_driver_chief_lalu_ga(self, store):
        chain = build_chain(_conn(store), 'bbm', 'Budi Driver', 'driver')
        assert [s['role'] for s in chain] == ['chief_driver', 'ga']
        assert all(s['approver'] for s in chain)

    def test_default_ob_ga_hr_lalu_admin(self, store):
        chain = build_chain(_conn(store), 'overtime_ob', 'Ob Satu', 'ob')
        assert [s['role'] for s in chain] == ['ga_hr', 'admin']

    def test_override_manager_username(self, store):
        store['users']['Budi Driver']['manager_username'] = 'chief'
        chain = build_chain(_conn(store), 'cash', 'Budi Driver', 'driver')
        assert chain[0] == {'approver': 'chief', 'role': None}
        assert chain[1]['role'] == 'ga'

    def test_override_tak_aktif_diabaikan(self, store):
        store['users']['chief']['is_active'] = False
        store['users']['Budi Driver']['manager_username'] = 'chief'
        chain = build_chain(_conn(store), 'cash', 'Budi Driver', 'driver')
        assert chain[0]['role'] == 'chief_driver'

    def test_role_tak_dikenal_pakai_langkah_pertama_default(self, store):
        chain = build_chain(None, 'cash', 'Orang', 'receptionist')
        assert chain[0]['role'] == 'chief_driver'
        assert chain[1]['role'] == 'ga'


# ================================================================
# create_approval + status
# ================================================================
class TestCreateApproval:
    def test_create_pending_langkah_1(self, store):
        assert create_approval(_conn(store), 'cash', 5, display_id='CASH-X',
                               requested_by='Budi', requester_role='driver')
        status, row = approval_status(_conn(store), 'cash', 5)
        assert status == 'pending'
        assert row['step'] == 1

    def test_doc_type_tak_kenal_ditolak(self, store):
        assert not create_approval(_conn(store), ' trips', 1)
        assert not create_approval(_conn(store), 'cash', 0)

    def test_conn_none_aman(self):
        assert not create_approval(None, 'cash', 1)

    def test_resubmit_reset_ke_langkah_1(self, store):
        conn = _conn(store)
        create_approval(conn, 'cash', 5)
        decide(conn, 'cash', 5, 'approved', 'chief1', 'chief_driver')
        create_approval(conn, 'cash', 5)  # draft dikirim ulang
        status, row = approval_status(conn, 'cash', 5)
        assert status == 'pending' and row['step'] == 1


# ================================================================
# decide (urutan langkah, self-approval, tolak)
# ================================================================
def _pending(store, doc_type='cash', doc_ref=5, requested_by='Budi Driver',
             requester_role='driver'):
    conn = _conn(store)
    create_approval(conn, doc_type, doc_ref, requested_by=requested_by,
                    requester_role=requester_role)
    return conn


class TestDecide:
    def test_acc_langkah_salah_ditolak(self, store):
        conn = _pending(store)
        ok, msg = decide(conn, 'cash', 5, 'approved', 'ga_andi', 'ga')
        assert not ok
        assert 'Menunggu persetujuan' in msg

    def test_acc_berjenjang_sampai_final(self, store):
        conn = _pending(store)
        ok, _ = decide(conn, 'cash', 5, 'approved', 'chief1', 'chief_driver')
        assert ok
        status, row = approval_status(conn, 'cash', 5)
        assert status == 'pending' and row['step'] == 2
        ok, _ = decide(conn, 'cash', 5, 'approved', 'ga_andi', 'ga')
        assert ok
        status, _ = approval_status(conn, 'cash', 5)
        assert status == 'approved'

    def test_langkah_ber_role_cocok_utk_pemegang_role_sama(self, store):
        """Chief Driver cadangan (username beda) tetap bisa memutus."""
        conn = _pending(store)
        ok, msg = decide(conn, 'cash', 5, 'approved', 'chief_cadangan',
                         'chief_driver')
        assert ok, msg

    def test_langkah_ber_nama_hanya_user_tersebut(self, store):
        store['users']['Budi Driver']['manager_username'] = 'chief'
        conn = _pending(store)
        ok, _ = decide(conn, 'cash', 5, 'approved', 'chief_lain',
                       'chief_driver')
        assert not ok  # langkah ber-nama 'chief', bukan 'chief_lain'
        ok, _ = decide(conn, 'cash', 5, 'approved', 'chief', 'chief_driver')
        assert ok

    def test_tolak_final_dengan_alasan(self, store):
        conn = _pending(store)
        ok, msg = decide(conn, 'cash', 5, 'rejected', 'chief1',
                         'chief_driver', note='Nominal berlebihan')
        assert ok and 'ditolak' in msg
        status, row = approval_status(conn, 'cash', 5)
        assert status == 'rejected' and row['note'] == 'Nominal berlebihan'

    def test_tolak_tanpa_alasan_ditolak_endpoint(self):
        """Endpoint menolak penolakan tanpa catatan (400)."""
        a = Flask(__name__)
        a.secret_key = 'k'
        register_approval_routes(a)
        c = a.test_client()
        with c.session_transaction() as s:
            s['user_role'] = 'chief_driver'
            s['user_name'] = 'chief'
        r = c.post('/api/approvals/cash/1/decision', json={'decision': 'rejected'})
        assert r.status_code == 400

    def test_self_approval_diblok(self, store):
        conn = _pending(store, requested_by='Chief Satu',
                        requester_role='chief_driver')
        ok, msg = decide(conn, 'cash', 5, 'approved', 'Chief Satu',
                         'chief_driver')
        assert not ok
        assert 'sendiri' in msg

    def test_decision_tidak_valid(self, store):
        conn = _pending(store)
        ok, _ = decide(conn, 'cash', 5, 'maybe', 'chief1', 'chief_driver')
        assert not ok

    def test_tanpa_baris(self, store):
        ok, msg = decide(_conn(store), 'cash', 99, 'approved', 'c',
                         'chief_driver')
        assert not ok and 'tidak ditemukan' in msg

    def test_sudah_final(self, store):
        conn = _pending(store)
        decide(conn, 'cash', 5, 'rejected', 'chief1', 'chief_driver', note='x')
        ok, msg = decide(conn, 'cash', 5, 'approved', 'ga1', 'ga')
        assert not ok and 'sudah diproses' in msg

    def test_overtime_chain_ga_hr_lalu_admin(self, store):
        conn = _pending(store, doc_type='overtime_driver',
                        requested_by='Budi', requester_role='driver')
        ok, _ = decide(conn, 'overtime_driver', 5, 'approved', 'hr', 'ga_hr')
        assert ok
        ok, _ = decide(conn, 'overtime_driver', 5, 'approved', 'root', 'admin')
        assert ok
        assert approval_status(conn, 'overtime_driver', 5)[0] == 'approved'

    def test_decision_allowed_tanpa_langkah_aktif(self, store):
        conn = _pending(store)
        decide(conn, 'cash', 5, 'rejected', 'chief1', 'chief_driver', note='x')
        status, row = approval_status(conn, 'cash', 5)
        assert not decision_allowed(row, 'chief1', 'chief_driver')


# ================================================================
# gate_allows / gate_approval (fail-open)
# ================================================================
class TestGate:
    def test_pending_memblokir_409(self, store):
        _pending(store)
        with _APP.app_context():
            ok, resp = gate_allows(_conn(store), 'cash', 5)
        assert not ok and resp[1] == 409
        body = resp[0].get_json()
        assert body['code'] == APPROVAL_CODE
        assert body['pending_at']

    def test_rejected_memblokir(self, store):
        conn = _pending(store)
        decide(conn, 'cash', 5, 'rejected', 'chief1', 'chief_driver', note='x')
        with _APP.app_context():
            ok, resp = gate_allows(_conn(store), 'cash', 5)
        assert not ok and resp[1] == 409

    def test_approved_lolos(self, store):
        conn = _pending(store)
        decide(conn, 'cash', 5, 'approved', 'c1', 'chief_driver')
        decide(conn, 'cash', 5, 'approved', 'g1', 'ga')
        ok, resp = gate_allows(_conn(store), 'cash', 5)
        assert ok and resp is None

    def test_tanpa_baris_lolos(self, store):
        ok, resp = gate_allows(_conn(store), 'bbm', 123)
        assert ok and resp is None

    def test_conn_none_lolos(self):
        ok, resp = gate_allows(None, 'cash', 1)
        assert ok and resp is None

    def test_gate_approval_exception_fail_open(self, monkeypatch):
        def boom(conn, t, r):
            raise RuntimeError('DB mati')
        monkeypatch.setattr(am, 'gate_allows', boom)
        ok, resp = gate_approval(object(), 'cash', 1)
        assert ok and resp is None


# ================================================================
# Endpoint: daftar & keputusan (401/403/200)
# ================================================================
def _api_app(store, monkeypatch):
    """App dgn endpoint approvals + fake DB (master & cabang sama)."""
    import modules.config as mc
    import modules.helpers as mh
    conn = _conn(store)

    a = Flask(__name__)
    a.secret_key = 'k'
    monkeypatch.setattr(am, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
    # Endpoint membaca DB cabang via config.get_db_connection
    # (di-import di dalam fungsi → patch namespace config).
    monkeypatch.setattr(mc, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(am, 'log_activity_async', lambda *a2, **k: None)
    register_approval_routes(a)
    return a, conn


def _login(c, role, username):
    with c.session_transaction() as s:
        s.clear()
        s['user_role'] = role
        s['user_name'] = username
        s['full_name'] = username


class TestEndpoints:
    def test_tanpa_login_401(self, store, monkeypatch):
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        r = c.get('/api/approvals')
        assert r.status_code == 401

    def test_role_luar_403(self, store, monkeypatch):
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'driver', 'budi')
        r = c.get('/api/approvals')
        assert r.status_code == 403

    def test_daftar_hanya_pending_langkah_sendiri(self, store, monkeypatch):
        _pending(store)
        _pending(store, doc_type='bbm', doc_ref=9)
        # Sudah final → tidak tampil di daftar
        conn = _conn(store)
        decide(conn, 'bbm', 9, 'approved', 'c1', 'chief_driver')
        decide(conn, 'bbm', 9, 'approved', 'g1', 'ga')
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'chief_driver', 'chief1')
        r = c.get('/api/approvals')
        data = r.get_json()['data']
        assert r.status_code == 200
        assert len(data) == 1  # hanya cash yang masih pending
        assert data[0]['pending_at']

    def test_daftar_admin_semua_langkah(self, store, monkeypatch):
        conn = _pending(store)
        decide(conn, 'cash', 5, 'approved', 'c1', 'chief_driver')  # ke langkah 2
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'admin', 'root')
        data = c.get('/api/approvals').get_json()['data']
        assert len(data) == 1 and data[0]['step'] == 2

    def test_daftar_chain_json_sudah_dict(self, store, monkeypatch):
        _pending(store)
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'admin', 'root')
        data = c.get('/api/approvals').get_json()['data']
        assert isinstance(data[0]['chain'], list)

    def test_keputusan_acc_maju_langkah(self, store, monkeypatch):
        _pending(store)
        a, conn = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'chief_driver', 'chief1')
        r = c.post('/api/approvals/cash/5/decision',
                   json={'decision': 'approve'})
        body = r.get_json()
        assert r.status_code == 200 and body['status'] == 'success'
        assert approval_status(conn, 'cash', 5)[1]['step'] == 2

    def test_keputusan_doc_type_tak_kenal_404(self, store, monkeypatch):
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'admin', 'root')
        r = c.post('/api/approvals/trip/1/decision',
                   json={'decision': 'approve'})
        assert r.status_code == 404

    def test_status_endpoint(self, store, monkeypatch):
        _pending(store)
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'ga', 'ga1')
        r = c.get('/api/approvals/cash/5')
        assert r.status_code == 200
        assert r.get_json()['approval']['status'] == 'pending'

    def test_status_endpoint_tanpa_baris(self, store, monkeypatch):
        a, _ = _api_app(store, monkeypatch)
        c = a.test_client()
        _login(c, 'ga', 'ga1')
        r = c.get('/api/approvals/cash/424242')
        assert r.status_code == 200 and r.get_json()['approval'] is None


# ================================================================
# Endpoint produksi: submit kasbon mencatat jurnal, approve-ga digate
# ================================================================
class TestEndpointProduksi:
    def test_cash_approve_ga_terblokir_409_saat_pending(self, store, monkeypatch):
        import modules.routes_cash as rc
        _pending(store)
        a = Flask(__name__)
        a.secret_key = 'k'
        monkeypatch.setattr(rc, 'stepup_required', lambda f: f)
        monkeypatch.setattr(rc, 'get_db_connection', lambda: _conn(store))
        monkeypatch.setattr(rc, 'push_driver_notification',
                            lambda *a2, **k: None)
        monkeypatch.setattr(rc, 'log_activity_async', lambda *a2, **k: None)
        rc.register_cash_routes(a)
        c = a.test_client()
        _login(c, 'ga', 'ga1')
        r = c.post('/api/cash/approve-ga/5')
        assert r.status_code == 409
        assert r.get_json()['code'] == APPROVAL_CODE

    def test_cash_approve_ga_lolos_setelah_full_acc(self, store, monkeypatch):
        import modules.routes_cash as rc
        conn = _pending(store)
        decide(conn, 'cash', 5, 'approved', 'c1', 'chief_driver')
        decide(conn, 'cash', 5, 'approved', 'g1', 'ga')
        a = Flask(__name__)
        a.secret_key = 'k'
        monkeypatch.setattr(rc, 'stepup_required', lambda f: f)
        monkeypatch.setattr(rc, 'get_db_connection', lambda: _conn(store))
        # Approve butuh baris ber-status DRAFT → 404 (data uji tak ada),
        # PENTINGNYA: bukan 409 ACC — gate tidak lagi memblokir.
        monkeypatch.setattr(rc, 'push_driver_notification',
                            lambda *a2, **k: None)
        monkeypatch.setattr(rc, 'log_activity_async', lambda *a2, **k: None)
        rc.register_cash_routes(a)
        c = a.test_client()
        _login(c, 'ga', 'ga1')
        r = c.post('/api/cash/approve-ga/5', json={})
        assert r.status_code == 404  # lewat gate, berhenti di data uji

    def test_submit_kasbon_mencatat_jurnal(self, store, monkeypatch):
        """Submit kasbon nyata (endpoint asli) → jurnal ACC pending."""
        import modules.routes_cash as rc
        a = Flask(__name__)
        a.secret_key = 'k'
        monkeypatch.setattr(rc, 'get_db_connection', lambda: _conn(store))
        monkeypatch.setattr(rc, 'session_driver_name', lambda: 'Budi Driver')
        monkeypatch.setattr(rc, 'generate_display_id',
                            lambda *a2, **k: 'CASH-SBY-20260906-0001')
        monkeypatch.setattr(rc, 'log_activity_async', lambda *a2, **k: None)
        rc.register_cash_routes(a)
        c = a.test_client()
        with c.session_transaction() as s:
            s['user_role'] = 'driver'
            s['user_name'] = 'budi'
            s['full_name'] = 'Budi Driver'
            s['branch_code'] = 'SBY'
        r = c.post('/api/cash/request', json={
            'nopol': 'L 1234 AB', 'base_amount': 100000})
        assert r.status_code == 200, r.get_json()
        status, row = approval_status(_conn(store), 'cash', 1)
        assert status == 'pending'
        assert row['requested_by'] == 'Budi Driver'
        assert row['requester_role'] == 'driver'
        assert row['branch_code'] == 'SBY'
        chain = json.loads(row['chain'])
        assert chain[0]['role'] == 'chief_driver'
        assert chain[1]['role'] == 'ga'
