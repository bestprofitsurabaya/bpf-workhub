"""Unit tests — ringkasan lintas cabang "Pusat" (v2.114.0).

Fokus: kegagalan satu DB/sinyal tidak mematikan panel, cabang nonaktif tidak
dibaca, Admin cabang hanya melihat kode miliknya, dan cache 60 detik benar
(tidak menembak 12 DB tiap muat dashboard).
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import branch_overview as ov  # noqa: E402


class FakeConn:
    def __init__(self, name='master'):
        self.name = name
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeCursor:
    """Cursor yang menjawab berdasarkan nama tabel di SQL."""

    def __init__(self, conn):
        self.conn = conn
        self._one = None
        self._rows = []

    def execute(self, sql, params=None):
        s = ' '.join(str(sql).split())
        self._one, self._rows = None, []
        if 'cv_online_submissions' in s:
            self._rows = [{'branch_code': 'SBY', 'n': 2},
                          {'branch_code': 'MLG', 'n': 1}]
        elif 'first_work_submissions' in s:
            self._rows = [{'branch_code': 'SBY', 'n': 3}]
        elif 'water_purchases' in s:
            if self.conn.name == 'BROKEN':
                raise RuntimeError('Table water_purchases tidak ada')
            self._one = {'n': 4}
        elif 'fuel_cash_requests' in s:
            self._one = {'n': 2, 'amount': 1500000}
        elif 'subsidy_match' in s:
            self._one = {'n': 1}
        elif 'verified_ga' in s:
            self._one = {'n': 5}
        elif 'transactions' in s:
            self._one = {'n': 3}
        else:
            self._one = {'n': 0}

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def close(self):
        pass


BRANCHES = [
    {'code': 'SBY', 'name': 'Surabaya', 'db_name': 'bpf_branch_sby', 'is_active': 1},
    {'code': 'MLG', 'name': 'Malang', 'db_name': 'bpf_branch_mlg', 'is_active': 1},
    {'code': 'OFF', 'name': 'Nonaktif', 'db_name': 'bpf_branch_off', 'is_active': 0},
]


def _patch(monkeypatch, master_name='master', connect_raises=None):
    import modules.config as config
    master = FakeConn(master_name)

    monkeypatch.setattr(config, 'get_master_connection', lambda: master)
    monkeypatch.setattr(ov.bm, 'list_branches',
                        lambda conn=None: [dict(b) for b in BRANCHES])

    def fake_connect(db_name):
        if connect_raises and db_name in connect_raises:
            raise RuntimeError('connection refused')
        return FakeConn('BROKEN' if db_name.endswith('_mlg') else db_name)

    monkeypatch.setattr(ov, '_connect_db', fake_connect)
    return master


def test_cache_key_normalises_codes():
    assert ov._cache_key(None) == '*'
    assert ov._cache_key(['mlg', 'SBY', ' ']) == 'MLG|SBY'
    # Urutan input tidak mengubah kunci → satu cache untuk scope yang sama.
    assert ov._cache_key(['SBY', 'MLG']) == ov._cache_key(['MLG', 'SBY'])


def test_build_marks_partial_branch_and_keeps_others(monkeypatch):
    _patch(monkeypatch)
    data = ov._build(now=datetime(2026, 11, 18, 8, 0, 0))
    by_code = {b['code']: b for b in data['branches']}

    # SBY normal: master + DB cabang terbaca.
    assert by_code['SBY']['status'] == 'ok'
    assert by_code['SBY']['signals']['cv_new'] == 2
    assert by_code['SBY']['signals']['first_work_new'] == 3
    assert by_code['SBY']['signals']['bbm_pending'] == 3
    assert by_code['SBY']['signals']['water_pending'] == 4
    assert by_code['SBY']['amounts']['kasbon_driver'] == 1500000

    # MLG: kolom/tabel air minum hilang → partial, sinyal lain tetap ada.
    assert by_code['MLG']['status'] == 'partial'
    assert any(e['signal'] == 'water_pending' for e in by_code['MLG']['errors'])
    assert by_code['MLG']['signals']['bbm_pending'] == 3

    # Cabang nonaktif tidak dibaca sama sekali.
    assert by_code['OFF']['status'] == 'inactive'
    assert by_code['OFF']['signals']['bbm_pending'] is None

    # Urutan: perhatian terbanyak dulu.
    assert data['branches'][0]['code'] in ('SBY', 'MLG')
    assert data['summary']['branches_total'] == 3
    assert data['summary']['branches_attention'] == 2


def test_admin_cabang_scope_only_reads_own_branch(monkeypatch):
    _patch(monkeypatch)
    data = ov._build(codes=['MLG'])
    assert [b['code'] for b in data['branches']] == ['MLG']
    assert data['summary']['branches_total'] == 1


def test_db_mati_ditandai_error_tanpa_menggagalkan_panel(monkeypatch):
    _patch(monkeypatch, connect_raises={'bpf_branch_mlg'})
    data = ov._build()
    by_code = {b['code']: b for b in data['branches']}
    assert by_code['MLG']['status'] == 'error'
    assert by_code['MLG']['signals']['bbm_pending'] is None
    assert by_code['SBY']['status'] == 'ok'


def test_overview_cache_60_detik(monkeypatch):
    calls = {'n': 0}

    def fake_build(codes=None, now=None):
        calls['n'] += 1
        return {'branches': [], 'totals': {}, 'amounts': {},
                'summary': {}, 'errors': [], 'cache_ttl': 60,
                'generated_at': 'x'}

    monkeypatch.setattr(ov, '_build', fake_build)
    ov.invalidate_cache()

    first = ov.overview(now=datetime(2026, 11, 18, 8, 0, 0))
    second = ov.overview(now=datetime(2026, 11, 18, 8, 0, 30))
    third = ov.overview(now=datetime(2026, 11, 18, 8, 1, 1))

    assert calls['n'] == 2          # panggilan ke-2 dilayani cache
    assert first['cached'] is False
    assert second['cached'] is True
    assert third['cached'] is False


def test_force_refresh_melewati_cache(monkeypatch):
    calls = {'n': 0}

    def fake_build(codes=None, now=None):
        calls['n'] += 1
        return {'branches': [], 'totals': {}, 'amounts': {},
                'summary': {}, 'errors': [], 'cache_ttl': 60,
                'generated_at': 'x'}

    monkeypatch.setattr(ov, '_build', fake_build)
    ov.invalidate_cache()
    now = datetime(2026, 11, 18, 8, 0, 0)
    ov.overview(now=now)
    ov.overview(now=now + timedelta(seconds=5), force=True)
    assert calls['n'] == 2
