"""v2.132.0 — uji wiring route pengajuan ganti kendaraan (tanpa DB nyata)."""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_api_assignments as raa  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.conn.sql_log.append((sql.strip(), params))

    def fetchall(self):
        return self.conn.rows

    def fetchone(self):
        return self.conn.one

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None, one=None):
        self.sql_log = []
        self.rows = rows or []
        self.one = one
        self.autocommit = True
        self.commits = 0
        self.closes = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closes += 1


def make_app(role, name='driver_sby', branch='SBY'):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['UPLOAD_FOLDER'] = '/tmp'
    raa.register_assignment_api(app)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_role'] = role
        sess['user_name'] = name
        sess['branch_code'] = branch
        sess['csrf_token'] = 'tok'
    return client


def quiet(monkeypatch):
    monkeypatch.setattr(raa, 'push_driver_notification', lambda *a, **k: None)
    monkeypatch.setattr(raa, 'log_activity_async', lambda *a, **k: None)


class TestContext:
    def test_identitas_dan_cabang_dari_sesi(self, monkeypatch):
        seen = {}

        def fake(conn, me, branch, master_conn=None):
            seen['me'] = me
            seen['branch'] = branch
            return {'me': None, 'free_vehicles': [], 'partners': [],
                    'requests': []}

        monkeypatch.setattr(raa.svc, 'fetch_context', fake)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        r = make_app('driver').get('/api/assignments/swap-context')
        assert r.status_code == 200
        assert seen == {'me': 'DRIVER_SBY', 'branch': 'SBY'}


class TestCreateRoute:
    def test_driver_mengajukan(self, monkeypatch):
        seen = {}
        row = {'id': 3, 'requester_driver': 'DRIVER_SBY', 'target_driver': None,
               'requester_nopol': 'X', 'target_nopol': 'Z',
               'swap_type': 'move', 'request_code': 'SWR-20261123-0003'}

        def fake(conn, me, **kwargs):
            seen['me'] = me
            seen.update(kwargs)
            return row

        monkeypatch.setattr(raa.svc, 'create_request', fake)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        quiet(monkeypatch)
        r = make_app('driver').post('/api/assignments/swap-requests', json={
            'swap_type': 'move', 'target_nopol': 'Z',
            'category': 'driver_request', 'reason': 'butuh unit lebih besar'})
        assert r.status_code == 201
        assert seen['me'] == 'DRIVER_SBY'
        assert seen['branch_code'] == 'SBY'
        assert seen['swap_type'] == 'move'
        assert r.get_json()['request_code'] == 'SWR-20261123-0003'

    def test_ga_tidak_boleh_mengajukan(self, monkeypatch):
        called = []
        monkeypatch.setattr(raa.svc, 'create_request',
                            lambda *a, **k: called.append(1))
        r = make_app('ga').post('/api/assignments/swap-requests', json={})
        assert r.status_code == 403
        assert called == []

    def test_validasi_service_diteruskan(self, monkeypatch):
        def fake(*a, **k):
            raise raa.svc.SwapError(400, 'reason', 'Alasan minimal 10 karakter')

        monkeypatch.setattr(raa.svc, 'create_request', fake)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        r = make_app('driver').post('/api/assignments/swap-requests', json={})
        assert r.status_code == 400
        assert r.get_json()['code'] == 'reason'


class TestApproveRoute:
    def test_ga_name_dari_sesi_dan_ack_diteruskan(self, monkeypatch):
        seen = {}
        row = {'id': 5, 'request_code': 'SWR-20261123-0005',
               'requester_driver': 'A', 'target_driver': 'B',
               'requester_nopol': 'X', 'target_nopol': 'Y',
               'swap_type': 'exchange', 'status': 'approved'}

        def fake(conn, rid, ga_name, acknowledge_supersede=False,
                 master_conn=None):
            seen.update(rid=rid, ga=ga_name, ack=acknowledge_supersede)
            return row

        monkeypatch.setattr(raa.svc, 'approve_request', fake)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        quiet(monkeypatch)
        r = make_app('ga', name='ga_sby').post(
            '/api/assignments/swap-requests/5/approve',
            json={'acknowledge_supersede': True})
        assert r.status_code == 200
        assert seen == {'rid': 5, 'ga': 'ga_sby', 'ack': True}

    def test_konflik_dikembalikan_409(self, monkeypatch):
        def fake(*a, **k):
            raise raa.svc.SwapError(409, 'supersede_required', 'konflik',
                                    {'conflicts': [1, 2]})

        monkeypatch.setattr(raa.svc, 'approve_request', fake)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        quiet(monkeypatch)
        r = make_app('admin').post('/api/assignments/swap-requests/5/approve',
                                   json={})
        assert r.status_code == 409
        assert r.get_json()['conflicts'] == [1, 2]

    def test_finance_tidak_boleh_approve(self):
        r = make_app('finance').post('/api/assignments/swap-requests/5/approve',
                                     json={})
        assert r.status_code == 403


class TestHandoverRoute:
    def test_multipart_memakai_nopol_yang_diterima(self, monkeypatch):
        req = {'id': 5, 'swap_type': 'exchange', 'status': 'approved',
               'requester_driver': 'DRIVER_SBY', 'requester_nopol': 'X',
               'target_driver': 'B', 'target_nopol': 'Y',
               'requester_photo': None, 'target_photo': None}
        seen = {}

        monkeypatch.setattr(raa.svc, 'get_request', lambda conn, rid: req)

        def fake_save(file_obj, prefix, nopol, folder):
            seen['prefix'] = prefix
            seen['nopol'] = nopol
            return 'SWAP_Y.jpg'

        def fake_submit(conn, rid, me, odo, photo):
            seen.update(rid=rid, me=me, odo=odo, photo=photo)
            return {'status': 'approved', 'requester_driver': 'DRIVER_SBY',
                    'target_driver': 'B'}

        monkeypatch.setattr(raa, 'save_file', fake_save)
        monkeypatch.setattr(raa.svc, 'submit_handover', fake_submit)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        quiet(monkeypatch)
        r = make_app('driver').post(
            '/api/assignments/swap-requests/5/handover',
            data={'odometer': '1234',
                  'photo': (io.BytesIO(b'x'), 'odo.jpg')},
            content_type='multipart/form-data')
        assert r.status_code == 200
        assert seen['prefix'] == 'SWAP'
        assert seen['nopol'] == 'Y'
        assert seen['odo'] == '1234'
        assert seen['photo'] == 'SWAP_Y.jpg'

    def test_tanpa_foto_ditolak(self, monkeypatch):
        req = {'id': 5, 'swap_type': 'move', 'status': 'approved',
               'requester_driver': 'DRIVER_SBY', 'requester_nopol': 'X',
               'target_driver': None, 'target_nopol': 'Z',
               'requester_photo': None}
        monkeypatch.setattr(raa.svc, 'get_request', lambda conn, rid: req)
        monkeypatch.setattr(raa, 'save_file', lambda *a, **k: None)
        monkeypatch.setattr(raa, 'get_db_connection', lambda: FakeConn())
        quiet(monkeypatch)
        r = make_app('driver').post(
            '/api/assignments/swap-requests/5/handover',
            data={'odometer': '10'}, content_type='multipart/form-data')
        assert r.status_code == 400
        assert r.get_json()['code'] == 'photo'


class TestPendingAndConfirm:
    def test_pending_menyertakan_handover_request_id(self, monkeypatch):
        conn = FakeConn(rows=[{'nopol': 'Y', 'driver_name': 'DRIVER_SBY'}])
        monkeypatch.setattr(raa, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(raa.svc, 'handover_request_for',
                            lambda c, me, nopol: 12)
        r = make_app('driver').get('/api/assignments/pending')
        assert r.status_code == 200
        assert r.get_json()[0]['handover_request_id'] == 12

    def test_confirm_diblokir_bila_bukti_belum(self, monkeypatch):
        conn = FakeConn()
        monkeypatch.setattr(raa, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(raa.svc, 'handover_request_for',
                            lambda c, me, nopol: 12)
        r = make_app('driver').post('/api/assignments/confirm',
                                    json={'nopol': 'Y'})
        assert r.status_code == 409
        assert r.get_json()['code'] == 'handover_required'
        assert not [sql for sql, _ in conn.sql_log
                    if sql.startswith('UPDATE vehicle_assignments')]

    def test_confirm_biasa_tetap_berjalan(self, monkeypatch):
        conn = FakeConn()
        monkeypatch.setattr(raa, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(raa.svc, 'handover_request_for',
                            lambda c, me, nopol: None)
        r = make_app('driver').post('/api/assignments/confirm',
                                    json={'nopol': 'X'})
        assert r.status_code == 200
        assert [sql for sql, _ in conn.sql_log
                if sql.startswith('UPDATE vehicle_assignments')]
