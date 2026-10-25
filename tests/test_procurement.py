"""
Unit Tests — Modul Pengadaan / Purchase Order (v2.70.0)
BPF WorkHub

- Normalisasi item PO (deskripsi/qty/satuan/harga).
- Rute terdaftar & ter-auth role_required (401 tanpa login; 403 role tak sesuai).
- Rekonsiliasi status _recompute_status: open → partial → closed.

Jalankan:
    python3 -m pytest tests/test_procurement.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from modules.routes_procurement import (  # noqa: E402
    _norm_items, _recompute_status, VALID_SATUAN,
    register_procurement_routes,
)


# ---------------------------------------------------------------------------
# Fixture klien Flask dgn rute pengadaan + login tersimulasi
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_procurement_routes(app)
    app.config['TESTING'] = True

    with app.test_client() as c:
        yield c


def _login(client, role='finance', name='RINA'):
    """Set sesi seperti login (role_required membaca session)."""
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = name
        s['full_name'] = name
        s['branch_code'] = 'SBY'


# ---------------------------------------------------------------------------
# Normalisasi item
# ---------------------------------------------------------------------------

class TestNormItems:
    def test_semua_item_valid(self):
        items, err = _norm_items([
            {'description': 'Tinta Printer', 'qty': 4, 'satuan': 'pcs', 'price': 100000},
        ])
        assert err is None
        assert items == [{'description': 'Tinta Printer', 'qty': 4,
                          'satuan': 'pcs', 'price': 100000.0}]

    def test_kosong_ditolak(self):
        assert _norm_items([])[1]
        assert _norm_items(None)[1]

    def test_deskripsi_wajib(self):
        assert _norm_items([{'description': '', 'qty': 1}])[1]

    def test_qty_negatif_ditolak(self):
        assert _norm_items([{'description': 'X', 'qty': -3}])[1]

    def test_satuan_tidak_kenal(self):
        assert _norm_items([{'description': 'X', 'qty': 1, 'satuan': 'kubik'}])[1]

    def test_harga_negatif_ditolak(self):
        assert _norm_items([{'description': 'X', 'qty': 1, 'price': -5}])[1]

    def test_satuan_valid_lengkap(self):
        assert VALID_SATUAN >= {'unit', 'dus', 'galon', 'kg', 'liter'}


# ---------------------------------------------------------------------------
# Status PO dihitung dari penerimaan (fetchall heuristik per SQL)
# ---------------------------------------------------------------------------

class _OffsetCursor:
    """Cursor minimal: mengingat SQL terakhir, mengembalikan baris sesuai skenario."""

    def __init__(self, rows):
        self.rows = rows      # baris untuk query po_items

    def execute(self, sql, params=None):
        self.sql = sql.lower()

    def fetchall(self):
        if 'from po_items' in self.sql:
            return self.rows
        return []

    def close(self):
        pass


def test_recompute_status_partial():
    cur = _OffsetCursor([{'qty': 10, 'received': 10}, {'qty': 5, 'received': 0}])
    assert _recompute_status(cur, 1) == 'partial'


def test_recompute_status_semua_terima():
    cur = _OffsetCursor([{'qty': 10, 'received': 10}, {'qty': 5, 'received': 5}])
    assert _recompute_status(cur, 1) == 'closed'


def test_recompute_status_belum_terima():
    cur = _OffsetCursor([{'qty': 10, 'received': 0}])
    assert _recompute_status(cur, 1) == 'open'


# ---------------------------------------------------------------------------
# Rute: registrasi & Auth
# ---------------------------------------------------------------------------

ROUTES = ['/api/procurement/suppliers', '/api/procurement/orders']


def test_rute_terdaftar(client):
    for r in ROUTES:
        resp = client.get(r)
        assert resp.status_code in (301, 302, 401, 403), f'{r} tak terdaftar'


@pytest.mark.parametrize('path', ['/api/procurement/suppliers', '/api/procurement/orders'])
def test_semua_role_modul_kesimpulan(client, monkeypatch, path):
    """ga/finance/admin boleh GET daftar; ob ditolak 403."""
    class _C:
        def __init__(self):
            self.tables = {'suppliers': [], 'purchase_orders': []}

        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return {'n': 0}

        def close(self):
            pass

    class _Conn:
        def cursor(self, dictionary=False):
            return _C()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr('modules.routes_procurement.get_db_connection',
                        lambda *a, **k: _Conn())

    for role in ('ga', 'finance', 'admin'):
        _login(client, role=role)
        rv = client.get(path)
        assert rv.status_code == 200, f'{role} wajib boleh GET {path}: {rv.get_json()}'

    _login(client, role='ob')
    assert client.get(path).status_code == 403
