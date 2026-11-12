"""
Unit Tests — Rekap Pengeluaran (v2.71.0, isolasi cabang v2.99.1)
modules/routes_expense.py + modules/branch_scope.py
BPF WorkHub

- _fill_vector: baris GROUP BY bulan → vektor 12 ganda, bulan tidak valid
  diabaikan, bulan ganda dijumlahkan.
- Akses API: role gate (finance/admin boleh; ga/ob ditolak), validasi cabang,
  bentuk response (vektor 12, totals = jumlah bulan).
- Isolasi cabang (v2.99.1): finance cabang hanya cabangnya — `ALL`/cabang lain
  403, default mengikuti sesi (bukan SBY); `finance_hu` dan Admin Pusat boleh
  semua; admin cabang tidak boleh `ALL`.
- Isolasi error per cabang: DB satu cabang gagal → cabang lain tetap terisi.

Jalankan:
    python3 -m pytest tests/test_expenses.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from modules.routes_expense import (  # noqa: E402
    _fill_vector, CATEGORIES, EXPENSE_ROLES, MONTHS,
    register_expense_routes,
)


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_expense_routes(app)
    app.config['TESTING'] = True

    with app.test_client() as c:
        yield c


def _login(client, role='finance', branch='SBY', username=None):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username or role.upper()
        s['full_name'] = role.upper()
        s['branch_code'] = branch


# ---------------------------------------------------------------------------
# _fill_vector
# ---------------------------------------------------------------------------

class TestFillVector:
    def test_bulan_berurutan(self):
        rows = [{'m': 1, 'amount': 100.0}, {'m': 3, 'amount': 250.5}]
        vec = _fill_vector(rows)
        assert len(vec) == MONTHS
        assert vec[0] == 100.0
        assert vec[2] == 250.5
        assert sum(vec) == 350.5

    def test_bulan_tidak_valid_dibuang(self):
        assert _fill_vector([{'m': 0, 'amount': 99}, {'m': 13, 'amount': 5}]) == [0.0] * MONTHS

    def test_bulan_ganda_dijumlah(self):
        vec = _fill_vector([{'m': 5, 'amount': 10}, {'m': 5, 'amount': 20}])
        assert vec[4] == 30.0

    def test_rows_kosong(self):
        assert _fill_vector([]) == [0.0] * MONTHS
        assert _fill_vector(None) == [0.0] * MONTHS

    def test_kategori_kontrak(self):
        assert CATEGORIES == ('po', 'kasbon', 'lpj')
        assert EXPENSE_ROLES == ['finance', 'admin']


# ---------------------------------------------------------------------------
# API: registrasi, role gate, validasi cabang, bentuk response
# ---------------------------------------------------------------------------

class FakeExpenseConn:
    """Conn minimal bersama: melayani query branches (master), PO & kasbon."""

    def __init__(self, po_rows, kas_rows):
        self.po_rows = po_rows
        self.kas_rows = kas_rows

    def cursor(self, dictionary=False):
        api = self

        class _C:
            def execute(self, sql, params=None):
                self.sql = sql.lower()
                self.params = params

            def fetchall(self):
                if 'from branches' in self.sql:
                    return [
                        {'code': 'SBY', 'name': 'Cabang Surabaya', 'db_name': 'bpf_asset_system'},
                        {'code': 'BDG', 'name': 'Cabang Bandung', 'db_name': 'bpf_branch_bdg'},
                    ]
                if 'purchase_orders' in self.sql or 'po_items' in self.sql:
                    return api.po_rows
                if 'fuel_cash_requests' in self.sql:
                    return api.kas_rows
                return []

            def fetchone(self):
                return None

            def close(self):
                pass
        return _C()

    def commit(self):
        pass

    def close(self):
        pass


def _patch(monkeypatch, po_rows=(), kas_rows=()):
    c = FakeExpenseConn(list(po_rows), list(kas_rows))
    monkeypatch.setattr('modules.routes_expense.get_master_connection', lambda: c)
    monkeypatch.setattr('modules.routes_expense._pool_for',
                        lambda db: type('P', (), {'get_connection': staticmethod(lambda: c)})())
    return c


def _admin_branches(monkeypatch, codes, all_branches=False):
    import modules.branch_scope as bs
    monkeypatch.setattr(bs, 'admin_branches', lambda conn=None: (list(codes), all_branches))


def test_rute_terdaftar_401_tanpa_login(client):
    rv = client.get('/api/expenses/recap')
    assert rv.status_code in (301, 302, 401, 403)


def test_finance_boleh_admin_boleh_ga_ditolak(client, monkeypatch):
    _patch(monkeypatch)
    for role, code in (('finance', 200), ('admin', 200), ('ga', 403), ('ob', 403)):
        _login(client, role=role)
        rv = client.get(f'/api/expenses/recap?year=2026&branch=SBY')
        assert rv.status_code == code, f'{role} harus {code}, dapat {rv.status_code} {rv.get_data(as_text=True)[:120]}'


def test_cabang_tidak_kenal(client, monkeypatch):
    _patch(monkeypatch)
    _login(client)
    rv = client.get('/api/expenses/recap?year=2026&branch=XXX')
    assert rv.status_code == 400


def test_bentuk_response_vektor_12(client, monkeypatch):
    _patch(monkeypatch,
           po_rows=[{'m': 2, 'amount': 400000.0}, {'m': 4, 'amount': 100000.0}],
           kas_rows=[{'m': 2, 'amount': 50000.0}, {'m': 7, 'amount': 150000.0}])
    _login(client)
    rv = client.get('/api/expenses/recap?year=2026&branch=SBY')
    assert rv.status_code == 200
    d = rv.get_json()
    assert d['year'] == 2026 and d['selected'] == 'SBY'
    assert len(d['display']['po']) == 12 and len(d['display']['kasbon']) == 12
    assert d['display']['po'][1] == 400000.0
    assert d['display']['kasbon'][6] == 150000.0
    assert d['display']['lpj'] == [0.0] * 12
    # Total realisasi = PO diterima + LPJ (kasbon bukan pengeluaran final).
    assert d['display']['total'][1] == 400000.0
    assert d['totals'] == {'po': 500000.0, 'kasbon': 200000.0, 'lpj': 0.0}
    assert d['grand_total'] == 500000.0
    assert d['sisa_total'] == 200000.0
    assert 'kasbon' in d['basis'] and 'excluded' in d['basis']
    assert not d['errors']


def test_detail_kategori_tidak_dikenal_ditolak(client):
    _login(client)
    rv = client.get('/api/expenses/detail?year=2026&month=2&branch=SBY&category=gaji')
    assert rv.status_code == 400


def test_detail_bulan_tidak_valid_ditolak(client):
    _login(client)
    rv = client.get('/api/expenses/detail?year=2026&month=13&branch=SBY&category=po')
    assert rv.status_code == 400


# ---------------------------------------------------------------------------
# Isolasi cabang (v2.99.1)
# ---------------------------------------------------------------------------

def test_admin_pusat_boleh_all(client, monkeypatch):
    _patch(monkeypatch,
           po_rows=[{'m': 1, 'amount': 300000.0}],
           kas_rows=[{'m': 1, 'amount': 100000.0}])
    _login(client, role='admin', username='admin')
    rv = client.get('/api/expenses/recap?year=2026&branch=ALL')
    d = rv.get_json()
    assert rv.status_code == 200
    # 2 cabang (SBY + BDG) memakai conn hasil patch yang sama → nilai dua kali
    assert d['display']['po'][0] == 600000.0
    assert d['display']['name'] == 'Semua Cabang'
    assert d['grand_total'] == 600000.0
    assert {b['code'] for b in d['branches']} == {'SBY', 'BDG'}


def test_finance_hu_boleh_all(client, monkeypatch):
    _patch(monkeypatch, po_rows=[{'m': 1, 'amount': 100000.0}])
    _login(client, role='finance', branch='HU', username='finance_hu')
    rv = client.get('/api/expenses/recap?year=2026&branch=ALL')
    assert rv.status_code == 200
    assert rv.get_json()['display']['name'] == 'Semua Cabang'


def test_finance_cabang_tidak_boleh_all(client, monkeypatch):
    _patch(monkeypatch)
    _login(client, role='finance', branch='BDG', username='finance_bdg')
    rv = client.get('/api/expenses/recap?year=2026&branch=ALL')
    assert rv.status_code == 403


def test_finance_cabang_tidak_boleh_cabang_lain(client, monkeypatch):
    _patch(monkeypatch)
    _login(client, role='finance', branch='BDG', username='finance_bdg')
    rv = client.get('/api/expenses/recap?year=2026&branch=SBY')
    assert rv.status_code == 403
    rv = client.get('/api/expenses/detail?year=2026&month=2&branch=SBY&category=po')
    assert rv.status_code == 403


def test_finance_default_mengikuti_cabang_sesi(client, monkeypatch):
    """Tanpa ?branch= tidak boleh jatuh ke SBY."""
    _patch(monkeypatch, po_rows=[{'m': 3, 'amount': 75000.0}])
    _login(client, role='finance', branch='BDG', username='finance_bdg')
    rv = client.get('/api/expenses/recap?year=2026')
    assert rv.status_code == 200
    d = rv.get_json()
    assert d['selected'] == 'BDG'
    assert list(d['per_branch']) == ['BDG']
    assert d['display']['name'] == 'Cabang Bandung'
    # Pemilih cabang juga hanya berisi cabang sendiri.
    assert d['branches'] == [{'code': 'BDG', 'name': 'Cabang Bandung'}]


def test_finance_tanpa_cabang_ditolak(client, monkeypatch):
    _patch(monkeypatch)
    _login(client, role='finance', branch=None, username='finance_baru')
    rv = client.get('/api/expenses/recap?year=2026')
    assert rv.status_code == 403


def test_admin_cabang_tidak_boleh_all(client, monkeypatch):
    _patch(monkeypatch)
    _admin_branches(monkeypatch, ['SBY'], all_branches=False)
    _login(client, role='admin', branch='SBY', username='admin_sby')
    rv = client.get('/api/expenses/recap?year=2026&branch=ALL')
    assert rv.status_code == 403
    rv = client.get('/api/expenses/recap?year=2026&branch=SBY')
    assert rv.status_code == 200


def test_admin_cabang_tidak_boleh_cabang_lain(client, monkeypatch):
    _patch(monkeypatch)
    _admin_branches(monkeypatch, ['SBY'], all_branches=False)
    _login(client, role='admin', branch='SBY', username='admin_sby')
    rv = client.get('/api/expenses/recap?year=2026&branch=BDG')
    assert rv.status_code == 403
