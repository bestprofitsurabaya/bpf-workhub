"""Kontrak cakupan cabang laporan & workspace BBM (v2.99.1 — diuji v2.104.0).

Isolasi cabang adalah properti **keamanan** paling sensitif dari meja kerja
BBM: kalau longgar, Finance cabang bisa membaca angka cabang lain lewat
laporan lintas-cabang (`/api/expenses/recap`, `/api/expenses/detail`).

Modul `modules/branch_scope.py` sempat lahir tanpa tes sama sekali — padahal
ia penjaga satu-satunya di jalur laporan lintas-cabang. Tes ini mengunci
fail-closed-nya: sesi yang tidak dikenal tidak boleh melihat apa pun.

Jalankan: python3 -m pytest tests/test_branch_scope.py -v
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session  # noqa: E402

from modules import branch_scope  # noqa: E402

BRANCHES = [
    {'code': 'SBY', 'name': 'Cabang Surabaya'},
    {'code': 'BDG', 'name': 'Cabang Bandung'},
    {'code': 'SMG', 'name': 'Cabang Semarang'},
]


def _app():
    app = Flask(__name__)
    app.secret_key = 'test-branch-scope'
    return app


def _resolve(role=None, user_name=None, branch_code=None, requested=None):
    """resolve_report_scope() dengan sesi Flask buatan."""
    app = _app()
    with app.test_request_context():
        if role:
            session['user_role'] = role
        if user_name:
            session['user_name'] = user_name
        if branch_code:
            session['branch_code'] = branch_code
        return branch_scope.resolve_report_scope(BRANCHES, requested)


# ---------------------------------------------------------------- Finance ---

def test_finance_cabang_default_adalah_cabangnya_sendiri():
    targets, selected, visible, err = _resolve(
        role='finance', user_name='finance_sby', branch_code='SBY')
    assert err is None
    assert selected == 'SBY'
    assert [b['code'] for b in targets] == ['SBY']
    # Pemilih cabang di UI ikut dipersempit — bukan hanya angkanya.
    assert [b['code'] for b in visible] == ['SBY']


def test_finance_cabang_tidak_boleh_membaca_cabang_lain():
    _, _, _, err = _resolve(
        role='finance', user_name='finance_sby', branch_code='SBY', requested='BDG')
    assert err == 'forbidden'


def test_finance_cabang_tidak_boleh_memilih_semua_cabang():
    _, _, _, err = _resolve(
        role='finance', user_name='finance_sby', branch_code='SBY', requested='ALL')
    assert err == 'forbidden'


def test_finance_cabang_tanpa_branch_ditolak_fail_closed():
    _, _, _, err = _resolve(role='finance', user_name='finance_sby')
    assert err == 'forbidden'


def test_finance_hu_boleh_semua_cabang():
    targets, selected, visible, err = _resolve(
        role='finance', user_name='finance_hu', branch_code='SBY')
    assert err is None
    assert selected == 'ALL'
    assert [b['code'] for b in targets] == ['SBY', 'BDG', 'SMG']
    assert len(visible) == 3

    _, selected2, _, err2 = _resolve(
        role='finance', user_name='finance_hu', branch_code='SBY', requested='BDG')
    assert err2 is None
    assert selected2 == 'BDG'


def test_finance_hu_bisa_ditambah_lewat_env():
    monkey = os.environ.get('FINANCE_HO_USERNAMES')
    os.environ['FINANCE_HO_USERNAMES'] = 'finance_consolidator'
    mod = importlib.reload(branch_scope)
    try:
        app = _app()
        with app.test_request_context():
            session['user_role'] = 'finance'
            session['user_name'] = 'finance_consolidator'
            session['branch_code'] = 'SBY'
            targets, selected, _, err = mod.resolve_report_scope(BRANCHES, None)
        assert err is None
        assert selected == 'ALL'
        assert len(targets) == 3
    finally:
        if monkey is None:
            os.environ.pop('FINANCE_HO_USERNAMES', None)
        else:
            os.environ['FINANCE_HO_USERNAMES'] = monkey
        importlib.reload(branch_scope)


# ------------------------------------------------------------------ Admin ---

def test_admin_pusat_boleh_semua_cabang():
    targets, selected, _, err = _resolve(
        role='admin', user_name='admin', branch_code='SBY')
    assert err is None
    assert selected == 'ALL'
    assert len(targets) == 3


def test_admin_cabang_terkunci_ke_cabangnya(monkeypatch):
    monkeypatch.setattr(
        branch_scope, 'admin_branches', lambda *a, **k: (['BDG'], False))
    targets, selected, visible, err = _resolve(
        role='admin', user_name='admin_bdg', branch_code='BDG')
    assert err is None
    assert selected == 'BDG'
    assert [b['code'] for b in targets] == ['BDG']
    assert [b['code'] for b in visible] == ['BDG']

    _, _, _, err_other = _resolve(
        role='admin', user_name='admin_bdg', branch_code='BDG', requested='SBY')
    assert err_other == 'forbidden'

    _, _, _, err_all = _resolve(
        role='admin', user_name='admin_bdg', branch_code='BDG', requested='ALL')
    assert err_all == 'forbidden'


# --------------------------------------------------------------- Fail-safe --

def test_kode_cabang_tidak_dikenal_ditandai_unknown_bukan_forbidden():
    """Salah ketik harus kelihatan sebagai salah ketik (400), bukan 403 —
    supaya tidak disamarkan sebagai masalah izin."""
    _, _, _, err = _resolve(
        role='finance', user_name='finance_sby', branch_code='SBY', requested='ZZZ')
    assert err == 'unknown'


def test_peran_tak_dikenal_tidak_melihat_cabang_apapun():
    targets, selected, visible, err = _resolve(
        role='driver', user_name='driver_sby', branch_code='SBY')
    assert err == 'forbidden'
    assert targets == []
    assert visible == []


def test_sesi_tanpa_peran_juga_ditolak():
    targets, _, visible, err = _resolve(user_name='someone', branch_code='SBY')
    assert err == 'forbidden'
    assert targets == []
    assert visible == []
