"""Unit tests — laporan bulanan Pusat (v2.118.0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_monthly as mr  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self._one = None
        self._rows = []

    def execute(self, sql, params=None):
        s = ' '.join(str(sql).split())
        self.conn.queries.append((s, list(params or [])))
        if 'FROM transactions' in s:
            self._one = {'n': 3, 'amount': 450000, 'archived': 2}
        elif 'FROM fuel_cash_requests' in s:
            self._one = {'n': 2, 'amount': 1000000}
        elif 'FROM water_purchases' in s:
            self._one = {'n': 5, 'v': 4}
        elif 'FROM system_config' in s:
            self._rows = [{'config_key': 'monthly_report_downloaded_2026-10',
                           'config_value': '2026-11-01 10:00:00|Admin'}]
            self._one = None
        else:
            self._one = {'n': 0}
        if self.conn.name == 'BROKEN':
            raise RuntimeError('DB mati')

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, name='master'):
        self.name = name
        self.queries = []
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        pass

    def close(self):
        self.closed = True


BRANCHES = [
    {'code': 'SBY', 'name': 'Surabaya', 'db_name': 'db_sby', 'is_active': 1},
    {'code': 'MLG', 'name': 'Malang', 'db_name': 'db_mlg', 'is_active': 1},
    {'code': 'OFF', 'name': 'Nonaktif', 'db_name': 'db_off', 'is_active': 0},
]


def _patch(monkeypatch, broken=False):
    master = FakeConn('master')
    monkeypatch.setattr(mr, 'get_master_connection', lambda: master)
    monkeypatch.setattr(mr.bm, 'list_branches', lambda conn=None: list(BRANCHES))
    monkeypatch.setattr(mr, '_connect_db',
                        lambda db: FakeConn('BROKEN') if (broken and db == 'db_mlg')
                        else FakeConn(db))
    monkeypatch.setattr(mr, '_master_month', lambda month: (
        {'cv_new': {'SBY': 7, 'MLG': 2}, 'first_work_new': {'SBY': 11}},
        []))
    return master


def _client(monkeypatch, role='admin', username='admin'):
    app = Flask(__name__)
    app.secret_key = 'uji-monthly'
    mr.register_monthly_report_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = 'SBY'
        s['full_name'] = 'Uji Bulanan'
    return client


def test_laporan_menjumlahkan_semua_cabang_aktif(monkeypatch):
    _patch(monkeypatch)
    data = mr.build_report('2026-10')
    assert data['month'] == '2026-10'
    # Cabang nonaktif tidak ikut.
    assert [b['code'] for b in data['branches']] == ['SBY', 'MLG']
    # cv_new per cabang diambil dari master, bukan diulang total.
    assert data['branches'][0]['cv_new'] == 7
    assert data['branches'][1]['cv_new'] == 2
    assert data['totals']['bbm_count'] == 6
    assert data['totals']['bbm_amount'] == 900000
    assert data['totals']['kasbon_amount'] == 2000000
    assert data['totals']['water_verified'] == 8
    assert data['totals']['first_work_new'] == 11
    assert data['summary']['branches'] == 2


def test_db_cabang_mati_ditandai_tanpa_menghentikan_laporan(monkeypatch):
    _patch(monkeypatch, broken=True)
    data = mr.build_report('2026-10')
    sby = next(b for b in data['branches'] if b['code'] == 'SBY')
    mlg = next(b for b in data['branches'] if b['code'] == 'MLG')
    assert sby['status'] == 'ok'
    assert mlg['status'] == 'partial'
    assert data['summary']['errors'] == 1
    assert data['errors'][0]['branch'] == 'MLG'


def test_csv_memuat_total_dan_bulan(monkeypatch):
    _patch(monkeypatch)
    report = mr.build_report('2026-10')
    text = mr._csv(report)
    assert text.startswith('\ufeff')
    assert 'Laporan' not in text
    assert 'TOTAL' in text
    assert '2026-10' in text
    assert 'SBY' in text and 'Surabaya' in text


def test_bulan_tidak_valid_mengembalikan_none_dan_400(monkeypatch):
    now = mr.datetime.now().strftime('%Y-%m')
    assert mr._month('2026-13') is None
    assert mr._month('') == now
    assert mr._month('2026-02') == '2026-02'

    _patch(monkeypatch)
    client = _client(monkeypatch)
    assert client.get('/api/admin/monthly-report?month=2026-13').status_code == 400
    assert client.get('/api/admin/monthly-report/export?month=abc').status_code == 400


def test_endpoint_menolak_admin_cabang(monkeypatch):
    _patch(monkeypatch)
    client = _client(monkeypatch, username='admin_sby')
    assert client.get('/api/admin/monthly-report').status_code == 403


def test_export_csv_dan_catat_unduhan(monkeypatch):
    _patch(monkeypatch)
    recorded = []
    monkeypatch.setattr(mr, '_record', lambda k, v: recorded.append((k, v)))
    monkeypatch.setattr(mr, 'log_activity_async', lambda *a, **k: None)
    client = _client(monkeypatch)
    r = client.get('/api/admin/monthly-report/export?month=2026-10')
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('text/csv')
    assert 'Laporan_Bulanan_Pusat_2026-10.csv' in r.headers['Content-Disposition']
    assert recorded[0][0] == 'monthly_report_downloaded_2026-10'


def test_email_belum_dikonfigurasi_503(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.delenv('SMTP_HOST', raising=False)
    client = _client(monkeypatch)
    r = client.post('/api/admin/monthly-report/email',
                    json={'month': '2026-10', 'to': 'admin@contoh.id'})
    assert r.status_code == 503
    assert r.get_json()['code'] == 'EMAIL_NOT_CONFIGURED'


def test_email_alamat_tidak_valid_400(monkeypatch):
    _patch(monkeypatch)
    client = _client(monkeypatch)
    r = client.post('/api/admin/monthly-report/email',
                    json={'month': '2026-10', 'to': 'bukan-email'})
    assert r.status_code == 400


def test_status_melihat_jejak_unduhan(monkeypatch):
    _patch(monkeypatch)
    client = _client(monkeypatch)
    r = client.get('/api/admin/monthly-report/status?month=2026-10')
    assert r.status_code == 200
    data = r.get_json()
    assert data['due'] is False
    assert '2026-11-01' in data['downloaded_at']
