"""Unit tests — Edit & Hapus transaksi air minum (v2.37.0).

Cakupan:
- get/set_water_edit_enabled (system_config, fake DB)
- _normalize_water_items (validasi bersama create & edit)
- _water_edit_gate (fitur nonaktif → 403)
- Route produksi nyata: PUT/DELETE /api/water/purchases/<id>
  (fitur nonaktif 403, non-finance 403, langkah step-up 428, sukses)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_water as rw  # noqa: E402


class FakeCursor:
    """Cursor fake dengan tabel sederhana utk SELECT/UPDATE/DELETE/INSERT."""

    def __init__(self, conn, dictionary=True):
        self.conn = conn
        self.dictionary = dictionary
        self.log = []
        self._rows = []

    def execute(self, sql, params=None):
        self.log.append((' '.join(sql.split()), params or ()))
        c = self.conn
        low = ' '.join(sql.split()).lower()
        if low.startswith('select config_value from system_config'):
            row = c.config.get((params or ('',))[0])
            self._rows = [{'config_value': row}] if row is not None else []
        elif low.startswith('select * from water_purchases where id='):
            pid = (params or (0,))[0]
            p = c.purchases.get(pid)
            self._rows = [dict(p)] if p else []
        elif low.startswith('select drink_type'):
            pid = (params or (0,))[0]
            self._rows = [dict(i) for i in c.items_by.get(pid, [])]
        elif low.startswith('update water_purchases'):
            pid = (params or (0,))[-1]
            if pid in c.purchases:
                c.updated[pid] = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif low.startswith('delete from water_purchase_items'):
            pid = (params or (0,))[0]
            c.deleted_items.append(pid)
            self.rowcount = len(c.items_by.get(pid, []))
        elif low.startswith('delete from water_purchases'):
            pid = (params or (0,))[0]
            c.deleted_purchases.append(pid)
            self.rowcount = 1 if pid in c.purchases else 0
        elif low.startswith('insert into system_config'):
            key, val = params
            c.config[key] = val
            self.rowcount = 1
        elif low.startswith('insert into water_purchase_items'):
            self.rowcount = 1
        else:
            self.rowcount = 0
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, purchases=None, items_by=None, config=None):
        self.purchases = purchases or {}
        self.items_by = items_by or {}
        self.config = config or {}
        self.updated = {}
        self.deleted_items = []
        self.deleted_purchases = []
        self.commits = 0
        self.closed = False

    def cursor(self, dictionary=True):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


PURCHASE = {
    'id': 7, 'display_id': 'WTR-SBY-20260907-0001', 'ob_name': 'FAISOL',
    'purchase_date': '2026-09-07', 'status': 'verified', 'remark': 'OK',
    'note': '', 'rejection_reason': '', 'verified_by': 'RINA',
    'verified_at': None, 'edited_by': '', 'edited_at': None, 'edit_count': 0,
    'foto_before': 'WTR_BEFORE_x.jpg', 'foto_after': 'WTR_AFTER_x.jpg',
}

ITEMS = [{'purchase_id': 7, 'drink_type': 'Galon', 'brand': 'AQUA',
          'satuan': 'galon', 'quantity': 3}]


def _make_app(monkeypatch, role='finance', enabled=True, conn=None):
    monkeypatch.setattr(rw, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rw, 'get_db_connection', lambda: conn)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['UPLOAD_FOLDER'] = 'uploads'
    rw.register_water_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'finance_sby'
        s['full_name'] = 'Finance SBY'
        s['branch_code'] = 'SBY'
        s['stepup_until'] = 9_999_999_999  # grant step-up aktif
        s['csrf_token'] = 'x'
    return client


BODY = {'purchase_date': '2026-09-08',
        'items': [{'drink_type': 'Galon', 'brand': 'AQUA', 'satuan': 'galon',
                   'quantity': 5}],
        'remark': 'Koreksi qty', 'note': ''}


class TestToggle:
    def test_default_off_tanpa_db(self, monkeypatch):
        # Deterministik: paksa jalur "tanpa DB" walau test host punya DB.
        monkeypatch.setattr(rw, 'get_db_connection', lambda: None)
        assert rw.get_water_edit_enabled(None) is False

    def test_get_dari_config(self):
        conn = FakeConn(config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        assert rw.get_water_edit_enabled(conn) is True

    def test_set_true_false(self):
        conn = FakeConn()
        assert rw.set_water_edit_enabled(True, conn) is True
        assert conn.config[rw.WATER_EDIT_CONFIG_KEY] == 'true'
        assert rw.set_water_edit_enabled(False, conn) is True
        assert conn.config[rw.WATER_EDIT_CONFIG_KEY] == 'false'


class TestNormalize:
    def test_valid(self):
        items, err = rw._normalize_water_items(
            [{'drink_type': ' Botol ', 'brand': 'AQUA', 'satuan': 'DUS', 'quantity': '2'}])
        assert err is None
        assert items == [{'drink_type': 'Botol', 'brand': 'AQUA',
                          'satuan': 'dus', 'quantity': 2}]

    def test_kosong_dan_kelebihan(self):
        assert rw._normalize_water_items([])[1] == 'Minimal satu item wajib diisi'
        assert rw._normalize_water_items([{}] * 21)[1].startswith('Maksimal')

    def test_qty_tak_valid(self):
        assert rw._normalize_water_items(
            [{'drink_type': 'Galon', 'brand': 'AQUA', 'quantity': 0}])[1] is not None


class TestEditRoute:
    def test_fitur_nonaktif_403(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'false'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        r = c.put('/api/water/purchases/7', json=BODY)
        assert r.status_code == 403
        assert 'nonaktif' in r.get_json()['msg'].lower()

    def test_role_ob_ditolak(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='ob', conn=conn)
        assert c.put('/api/water/purchases/7', json=BODY).status_code == 403

    def test_stepup_wajib(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        with c.session_transaction() as s:
            s.pop('stepup_until', None)
        r = c.put('/api/water/purchases/7', json=BODY)
        assert r.status_code == 428
        assert r.get_json()['code'] == 'STEPUP_REQUIRED'

    def test_edit_sukses_verified(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        r = c.put('/api/water/purchases/7', json=BODY)
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'
        # Item lama dihapus & di-insert ulang; purchase di-update.
        assert conn.deleted_items == [7]
        assert 7 in conn.updated

    def test_edit_rejected_ditolak(self, monkeypatch):
        p = dict(PURCHASE, status='rejected')
        conn = FakeConn(purchases={7: p}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        assert c.put('/api/water/purchases/7', json=BODY).status_code == 400

    def test_edit_id_tak_ada_404(self, monkeypatch):
        conn = FakeConn(purchases={}, items_by={},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        assert c.put('/api/water/purchases/99', json=BODY).status_code == 404


class TestDeleteRoute:
    def test_fitur_nonaktif_403(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'false'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        assert c.delete('/api/water/purchases/7').status_code == 403

    def test_stepup_wajib(self, monkeypatch):
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        with c.session_transaction() as s:
            s.pop('stepup_until', None)
        assert c.delete('/api/water/purchases/7').status_code == 428

    def test_delete_sukses(self, monkeypatch, tmp_path):
        foto = tmp_path / 'WTR_BEFORE_x.jpg'
        foto.write_bytes(b'jpg')
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        monkeypatch.setattr(rw.os.path, 'isfile',
                            lambda p: str(p).endswith('.jpg') and str(p).startswith(str(tmp_path)))
        removed = []
        monkeypatch.setattr(rw.os, 'remove', lambda p: removed.append(p))
        c = _make_app(monkeypatch, role='admin', conn=conn)
        with c.session_transaction() as s:
            s['branch_code'] = 'SBY'
        r = c.delete('/api/water/purchases/7')
        assert r.status_code == 200
        assert conn.deleted_purchases == [7]
        assert conn.deleted_items == [7]

    def test_admin_cabang_lain_ditolak(self, monkeypatch):
        # Skenario desync (defense-in-depth): akun admin_bdg tapi sesi menunjuk
        # cabang SBY → baris DB SBY di luar cakupannya.
        conn = FakeConn(purchases={7: dict(PURCHASE)}, items_by={7: ITEMS},
                        config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='admin', conn=conn)
        with c.session_transaction() as s:
            s['user_name'] = 'admin_bdg'
            s['branch_code'] = 'SBY'
        r = c.delete('/api/water/purchases/7')
        assert r.status_code == 403


class TestToggleRoute:
    def test_get_status(self, monkeypatch):
        conn = FakeConn(config={rw.WATER_EDIT_CONFIG_KEY: 'true'})
        c = _make_app(monkeypatch, role='finance', conn=conn)
        r = c.get('/api/water/edit-enabled')
        assert r.status_code == 200
        assert r.get_json()['enabled'] is True

    def test_put_admin_only(self, monkeypatch):
        conn = FakeConn()
        c = _make_app(monkeypatch, role='finance', conn=conn)
        assert c.put('/api/water/edit-enabled',
                     json={'enabled': True}).status_code == 403

    def test_put_admin_sukses(self, monkeypatch):
        conn = FakeConn()
        c = _make_app(monkeypatch, role='admin', conn=conn)
        r = c.put('/api/water/edit-enabled', json={'enabled': True})
        assert r.status_code == 200
        assert conn.config[rw.WATER_EDIT_CONFIG_KEY] == 'true'
