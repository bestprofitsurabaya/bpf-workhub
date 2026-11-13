"""Voucher BBM rekanan (v2.107.0) — skema, konfigurasi, verifikasi, tagihan.

Yang dikunci tes ini:
1. Voucher BUKAN jenis transaksi baru: baris tetap `CLAIM`, hanya berlabel
   SPBU rekanan + kolom voucher terisi (`voucher_value > 0`).
2. Nilai tagihan = nilai voucher cabang + kode harian (server yang menghitung).
3. Tagihan periode mengunci voucher (`settlement_id`, status `archived`) supaya
   tidak bisa ditagih dua kali; pembayaran tagihan bukan beban BBM baru.
4. PDF bukti pemakaian & berita acara tagihan tetap tersedia.

Jalankan: python3 -m pytest tests/test_voucher.py -v
"""
import pytest
from flask import Flask

import modules.doc_integrity as di
import modules.pdf_generator as pg
import modules.routes_voucher as rv
from modules.company_identity import IDENTITY_DEFAULTS

TX = {
    'id': 9,
    'display_id': 'BBM-SBY-20261113-0001',
    'transaction_type': 'CLAIM',
    'driver_name': 'BUDI',
    'nopol': 'L 1234 AB',
    'vehicle_type': 'AVANZA',
    'bbm_type': 'PERTALITE',
    'nominal': 130700,
    'liter': 12.5,
    'price_per_liter': 10000,
    'voucher_value': 130000,
    'daily_code': 700,
    'voucher_partner': 'SPBU 54.601.01',
    'nota_no': 'INV-001',
    'odo_km': 1000,
    'status': 'verified_ga',
    'gps_address': 'Jl. Contoh',
    'foto_odo_sebelum': None,
    'foto_nota_odo_sesudah': None,
    'foto_struk': None,
    'status_ga': None,
    'ga_approved_by': 'GA SBY',
    'created_at': '2026-11-13 09:00:00',
}

SETTLEMENT = {
    'id': 501,
    'display_id': 'VST-SBY-20261113-0001',
    'period_start': '2026-11-01',
    'period_end': '2026-11-13',
    'partner': 'SPBU 54.601.01',
    'invoice_no': 'INV/SPBU/XI/2026/001',
    'voucher_count': 2,
    'total_amount': 261400,
    'status': 'draft',
    'paid_at': None,
    'paid_by': None,
    'created_by': 'FINANCE SBY',
    'notes': '',
    'created_at': '2026-11-13 10:00:00',
}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.lastrowid = None
        self.rowcount = 0
        self.sql = ''
        self._one = None
        self._all = []

    def execute(self, sql, params=None):
        self.sql = ' '.join(str(sql).split())
        self.conn.queries.append((self.sql, list(params or [])))
        q = self.sql
        self._one, self._all = self.conn.select(q)
        if q.startswith('INSERT INTO voucher_settlements'):
            self.lastrowid = 501
        if q.startswith('UPDATE transactions') or q.startswith('UPDATE voucher_settlements'):
            self.rowcount = self.conn.update_rowcount
        if q.startswith('INSERT INTO system_config'):
            self.rowcount = 1

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.update_rowcount = 1
        self.config_rows = [
            {'config_key': 'voucher_default_value', 'config_value': '130000'},
            {'config_key': 'voucher_partner_name', 'config_value': 'SPBU 54.601.01'},
        ]
        self.pending_rows = [dict(TX, status='pending', id=1)]
        self.unsettled_rows = [TX]
        self.settlement_rows = [SETTLEMENT]
        self.detail_head = SETTLEMENT
        self.detail_items = [TX]
        self.settlement_txs = [
            dict(TX, id=1, display_id='V-1', nominal=130700),
            dict(TX, id=2, display_id='V-2', nominal=130700),
        ]
        self.verify_row = {'status': 'pending', 'ml_anomaly_flag': 0}
        self.cancel_row = {'status': 'draft'}
        self.summary_row = {
            'pending_count': 1, 'pending_amount': 130700,
            'open_count': 1, 'open_amount': 130700,
            'settled_count': 2, 'settled_amount': 261400,
        }
        self.tx = TX

    def select(self, q):
        if 'FROM system_config' in q:
            return None, self.config_rows
        if 'FROM daily_unique_codes' in q:
            return {'unique_code': 700}, []
        if 'SUM(CASE' in q:
            return self.summary_row, []
        if q.startswith('SELECT status, ml_anomaly_flag'):
            return self.verify_row, []
        if q.startswith('SELECT status FROM voucher_settlements'):
            return self.cancel_row, []
        if q.startswith('SELECT * FROM voucher_settlements WHERE id=%s'):
            return self.detail_head, []
        if 'FROM voucher_settlements' in q:
            return None, self.settlement_rows
        if q.startswith('SELECT * FROM transactions WHERE id=%s AND transaction_type'):
            return self.tx, []
        if 'SELECT id, display_id, nominal, voucher_value' in q:
            return None, self.settlement_txs
        if 'WHERE settlement_id=%s' in q:
            return None, self.detail_items
        if "status IN ('pending','modified')" in q:
            return None, self.pending_rows
        if 'settlement_id IS NULL' in q:
            return None, self.unsettled_rows
        if 'FROM transactions' in q:
            return None, [self.tx]
        return None, []

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test'
    conn = FakeConn()
    monkeypatch.setattr(rv, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(rv, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rv, 'stepup_required', lambda fn: fn)
    monkeypatch.setattr(rv, 'generate_display_id', lambda *a, **k: 'VST-SBY-20261113-0001')
    monkeypatch.setattr(pg, 'get_company_identity', lambda *a, **k: dict(IDENTITY_DEFAULTS))
    monkeypatch.setattr(di, 'register_pdf', lambda *a, **k: None)
    rv.register_voucher_routes(app)
    with app.test_client() as c:
        c.conn = conn
        yield c


def login(client, role='finance', name='FINANCE SBY', branch='SBY'):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = name
        s['full_name'] = name
        s['branch_code'] = branch


def test_config_wajib_login(client):
    assert client.get('/api/voucher/config').status_code == 401


def test_driver_mendapat_nilai_voucher_dan_kode_harian(client):
    login(client, 'driver', 'BUDI')
    r = client.get('/api/voucher/config')
    assert r.status_code == 200
    d = r.get_json()
    assert d['value'] == 130000.0
    assert d['daily_code'] == 700
    assert d['nominal'] == 130700.0
    assert d['partner'] == 'SPBU 54.601.01'


def test_simpan_config_menolak_nilai_tidak_valid(client):
    login(client)
    assert client.post('/api/voucher/config', json={'value': 0}).status_code == 400
    assert client.post('/api/voucher/config', json={'value': 'abc'}).status_code == 400


def test_simpan_config_hanya_finance_admin(client):
    login(client, 'ga', 'GA SBY')
    assert client.post('/api/voucher/config', json={'value': 150000}).status_code == 403


def test_simpan_config_upsert_dan_audit(client):
    login(client)
    r = client.post('/api/voucher/config', json={'value': 150000, 'partner': 'SPBU BARU'})
    assert r.status_code == 200
    assert r.get_json()['value'] == 150000
    sqls = [q for q, _ in client.conn.queries]
    assert any(q.startswith('INSERT INTO system_config') for q in sqls)
    assert client.conn.commits >= 1


def test_summary_memisahkan_belum_verifikasi_belum_ditagih_dan_sudah(client):
    login(client, 'ga', 'GA SBY')
    r = client.get('/api/voucher/summary')
    assert r.status_code == 200
    d = r.get_json()
    assert d['pending'] == {'count': 1, 'amount': 130700.0}
    assert d['open'] == {'count': 1, 'amount': 130700.0}
    assert d['settled'] == {'count': 2, 'amount': 261400.0}


def test_ga_memverifikasi_voucher_pending(client):
    login(client, 'ga', 'GA SBY')
    r = client.post('/api/voucher/verify/1')
    assert r.status_code == 200
    update = [q for q, p in client.conn.queries if q.startswith('UPDATE transactions SET status=')]
    assert update and "status='verified_ga'" in update[0]


def test_voucher_anomali_tidak_bisa_diverifikasi_cepat(client):
    client.conn.verify_row = {'status': 'pending', 'ml_anomaly_flag': 1}
    login(client, 'ga', 'GA SBY')
    assert client.post('/api/voucher/verify/1').status_code == 409


def test_buat_tagihan_menolak_daftar_kosong(client):
    login(client)
    r = client.post('/api/voucher/settlements', json={'period_start': '2026-11-01',
                                                      'period_end': '2026-11-13',
                                                      'tx_ids': []})
    assert r.status_code == 400


def test_buat_tagihan_menolak_transaksi_bukan_voucher(client):
    client.conn.settlement_txs = [dict(TX, id=1, transaction_type='CLAIM', voucher_value=0)]
    login(client)
    r = client.post('/api/voucher/settlements', json={'period_start': '2026-11-01',
                                                      'period_end': '2026-11-13',
                                                      'tx_ids': [1]})
    assert r.status_code == 400


def test_buat_tagihan_mengunci_voucher_dan_menghitung_total(client):
    client.conn.update_rowcount = 2
    login(client)
    r = client.post('/api/voucher/settlements', json={
        'period_start': '2026-11-01', 'period_end': '2026-11-13',
        'invoice_no': 'INV/SPBU/XI/2026/001', 'tx_ids': [1, 2],
    })
    assert r.status_code == 200
    d = r.get_json()
    assert d['count'] == 2 and d['total'] == 261400.0
    inserts = [q for q, _ in client.conn.queries if q.startswith('INSERT INTO voucher_settlements')]
    assert inserts
    lock = [(q, p) for q, p in client.conn.queries
            if q.startswith('UPDATE transactions SET settlement_id=%s')]
    assert lock and "status='archived'" in lock[0][0]
    assert client.conn.commits >= 1


def test_buat_tagihan_menolak_voucher_sudah_terkunci(client):
    client.conn.settlement_txs = [dict(TX, id=1, settlement_id=99)]
    login(client)
    r = client.post('/api/voucher/settlements', json={'period_start': '2026-11-01',
                                                      'period_end': '2026-11-13',
                                                      'tx_ids': [1]})
    assert r.status_code == 409


def test_tagihan_dibayar_bukan_beban_bbm_baru(client):
    login(client)
    r = client.post('/api/voucher/settlements/501/pay')
    assert r.status_code == 200
    updates = [q for q, _ in client.conn.queries if q.startswith('UPDATE voucher_settlements SET status=')]
    assert updates and "status='paid'" in updates[0]
    # Pembayaran hanya menandai tagihan; tidak ada UPDATE nominal transaksi.
    assert not any(q.startswith('UPDATE transactions SET nominal') for q, _ in client.conn.queries)


def test_batal_tagihan_mengembalikan_voucher_ke_belum_ditagih(client):
    login(client)
    r = client.post('/api/voucher/settlements/501/cancel')
    assert r.status_code == 200
    release = [q for q, _ in client.conn.queries if q.startswith('UPDATE transactions SET settlement_id=NULL')]
    assert release and "status='verified_ga'" in release[0]


def test_pdf_bukti_pemakaian_voucher(client):
    login(client)
    r = client.get('/api/voucher/9/pdf')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    assert r.data.startswith(b'%PDF')
    assert 'Voucher_BBM-SBY-20261113-0001.pdf' in r.headers['Content-Disposition']


def test_pdf_berita_acara_tagihan(client):
    login(client)
    r = client.get('/api/voucher/settlements/501/pdf')
    assert r.status_code == 200
    assert r.data.startswith(b'%PDF')
    assert 'BeritaAcara_Voucher_VST-SBY-20261113-0001.pdf' in r.headers['Content-Disposition']
