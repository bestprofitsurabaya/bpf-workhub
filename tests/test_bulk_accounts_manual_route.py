"""
Unit Tests — Buat Akun Sekaligus (v2.19) & Atur Rute Manual (v2.19)

- POST /api/users/bulk-create            (admin) — akun driver + marketing member
- POST /api/appointments/route-manual/apply (chief_driver) — penugasan manual

Mengikuti pola test_water.py: DB di-fake (monkeypatch get_db_connection pada
modul routes), sehingga tidak butuh MariaDB saat dijalankan.

Jalankan:
    python3 -m pytest tests/test_bulk_accounts_manual_route.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask


# ================================================================
# Fake DB — cukup untuk menguji logika endpoint (bukan SQL server)
# ================================================================
class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.log = []  # (sql, params) — SEMUA eksekusi, bukan hanya query terakhir

    def execute(self, sql, params=None):
        sql = sql or ''
        params = params or ()
        self.log.append((sql, params))
        up = sql.lstrip().upper()
        if up.startswith('DELETE'):
            if 'FROM appointments' in sql:
                self.rowcount = sum(1 for a in self.db['appts']
                                    if str(a.get('display_id', '')).startswith('DEMO-'))
            elif 'FROM transactions' in sql:
                self.rowcount = len(self.db.get('dummy_tx', []))
            else:
                self.rowcount = 1
        elif up.startswith(('UPDATE', 'INSERT')):
            self.rowcount = 1
        else:
            self.rowcount = 0
        return None

    def fetchall(self):
        s = self.log[-1][0] if self.log else ''
        if 'COUNT(*)' in s:
            if 'FROM appointments' in s:
                n = sum(1 for a in self.db['appts']
                        if str(a.get('display_id', '')).startswith('DEMO-'))
                return [{'c': n}]
            if 'FROM transactions' in s:
                return [{'c': len(self.db.get('dummy_tx', []))}]
            return [{'c': 0}]
        if 'FROM system_config' in s:
            return [{'config_key': k, 'config_value': v}
                    for k, v in self.db.get('config', {}).items()]
        if 'FROM drivers' in s:
            return [{'name': n} for n in self.db['drivers']]
        if 'FROM marketing_members' in s:
            return [{'member_name': m, 'team_name': t} for m, t in self.db['members']]
        if 'FROM appointments' in s:
            return [dict(a) for a in self.db['appts']]
        return []

    def fetchone(self):
        if not self.log:
            return None
        s, params = self.log[-1]
        if 'COUNT(*)' in s:
            if 'FROM appointments' in s:
                return {'c': sum(1 for a in self.db['appts']
                                 if str(a.get('display_id', '')).startswith('DEMO-'))}
            if 'FROM transactions' in s:
                return {'c': len(self.db.get('dummy_tx', []))}
            return {'c': 0}
        if 'FROM users' in s:
            if 'marketing_yusie_sby' in s:
                return {'id': 1}
            if params and params[0] in self.db['existing']:
                return {'id': 1}
        if 'FROM appointments' in s and params:
            for a in self.db['appts']:
                if a.get('display_id') == params[0]:
                    return {'id': a['id']}
            return None
        return None

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.cursors = []

    def cursor(self, dictionary=True):
        c = FakeCursor(self.db)
        self.cursors.append(c)
        return c

    def commit(self):
        pass

    def close(self):
        pass


def _all_log(conn):
    """Semua (sql, params) yang dieksekusi pada semua cursor koneksi."""
    return [entry for cur in conn.cursors for entry in cur.log]


# ================================================================
# BUAT AKUN SEKALIGUS
# ================================================================
class TestBulkCreateAccounts:
    def _register(self, monkeypatch, db, role='admin'):
        import modules.routes_api_master as ram
        conn = FakeConn(db)
        monkeypatch.setattr(ram, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(ram, 'get_master_connection', lambda: conn)
        import modules.config as mc
        monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(ram, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ram.register_master_api(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = 'admin'
        return client, conn

    def test_buat_akun_driver_dan_marketing(self, monkeypatch):
        db = {
            'drivers': ['WICAK', 'GURUH', 'RIVAN'],
            'members': [('Icang', 'Yusie')],
            'existing': {'rivan'},   # RIVAN sudah punya akun (username rapi 'rivan') → dilewati
            'appts': [],
        }
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/users/bulk-create', json={'scope': 'all', 'pin': '123456'})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()
        assert data['status'] == 'success'
        usernames = [c['username'] for c in data['created']]
        # v2.19.2: username dirapikan (huruf kecil, tanpa spasi)
        assert set(usernames) == {'wicak', 'guruh', 'icang'}
        assert any(c['role'] == 'driver' for c in data['created'])
        icang = next(c for c in data['created'] if c['username'] == 'icang')
        assert icang['role'] == 'marketing' and icang['team'] == 'Yusie'
        assert [s['name'] for s in data['skipped']] == ['rivan']

        # INSERT akun dieksekusi ke tabel users (3: WICAK, GURUH, Icang)
        inserts = [(sql, params) for sql, params in _all_log(conn) if 'INSERT INTO users' in sql]
        assert len(inserts) == 3
        pins = [params[3] for _, params in inserts]
        assert pins == ['123456'] * 3
        roles = [params[2] for _, params in inserts]
        assert sorted(roles) == ['driver', 'driver', 'marketing']
        # full_name memakai title-case
        names = [params[1] for _, params in inserts]
        assert set(names) == {'Wicak', 'Guruh', 'Icang'}
        # branch_code ikut diset (cabang sesi / default)
        bcodes = {params[5] for _, params in inserts}
        assert bcodes == {'SBY'}

    def test_scope_driver_saja(self, monkeypatch):
        db = {'drivers': ['WICAK'], 'members': [('Icang', 'Yusie')], 'existing': set(), 'appts': []}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/bulk-create', json={'scope': 'driver'})
        assert r.status_code == 200
        data = r.get_json()
        assert [c['username'] for c in data['created']] == ['wicak']
        assert 'icang' not in [c['username'] for c in data['created']]

    def test_scope_marketing_saja(self, monkeypatch):
        db = {'drivers': ['WICAK'], 'members': [('Icang', 'Yusie')], 'existing': set(), 'appts': []}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/bulk-create', json={'scope': 'marketing'})
        assert r.status_code == 200
        data = r.get_json()
        assert [c['username'] for c in data['created']] == ['icang']

    def test_scope_tidak_valid_ditolak(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': []}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/bulk-create', json={'scope': 'hacker'})
        assert r.status_code == 400

    def test_pin_bukan_6_digit_ditolak(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': []}
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/users/bulk-create', json={'scope': 'all', 'pin': '12'})
        assert r.status_code == 400

    def test_non_admin_ditolak_403(self, monkeypatch):
        db = {'drivers': ['WICAK'], 'members': [], 'existing': set(), 'appts': []}
        client, _ = self._register(monkeypatch, db, role='ga')
        r = client.post('/api/users/bulk-create', json={'scope': 'all'})
        assert r.status_code == 403


# ================================================================
# ATUR RUTE MANUAL (chief driver)
# ================================================================
class TestManualRoute:
    def _register(self, monkeypatch, db, role='chief_driver'):
        import modules.routes_appointments as ra
        import modules.notifications as notif
        conn = FakeConn(db)
        monkeypatch.setattr(ra, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(ra, 'log_activity_async', lambda *a, **k: None)
        monkeypatch.setattr(ra, 'emit_event', lambda *a, **k: None)
        monkeypatch.setattr(notif, 'push_driver_notification', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ra.register_appointment_routes(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = 'CD'
            s['full_name'] = 'Chief Driver'
        return client, conn

    def _default_db(self):
        return {
            'drivers': ['RIVAN', 'AKHAD'],
            'members': [],
            'existing': set(),
            'appts': [
                {'id': 1, 'display_id': 'APP-1', 'status': 'scheduled'},
                {'id': 2, 'display_id': 'APP-2', 'status': 'assigned'},
                {'id': 3, 'display_id': 'APP-3', 'status': 'completed'},  # tidak plannable
            ],
        }

    def test_terapkan_penugasan_manual(self, monkeypatch):
        db = self._default_db()
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/appointments/route-manual/apply', json={
            'date': '2026-08-13',
            'assignments': [
                {'id': 1, 'driver_name': 'RIVAN', 'order': 2},
                {'id': 2, 'driver_name': 'akhad', 'order': 1},  # case di-upper-kan
            ],
        })
        assert r.status_code == 200, r.get_json()
        data = r.get_json()
        assert data['status'] == 'success'
        assert data['assigned'] == 2

        updates = [(sql, params) for sql, params in _all_log(conn) if 'UPDATE appointments' in sql]
        assert len(updates) == 2
        # urutan penugasan: RIVAN order 2, AKHAD order 1
        driver0, order0, id0 = updates[0][1][:3]
        assert (driver0, int(order0), id0) == ('RIVAN', 2, 1)
        driver1, order1, id1 = updates[1][1][:3]
        assert (driver1, int(order1), id1) == ('AKHAD', 1, 2)

    def test_driver_tidak_aktif_dilewati(self, monkeypatch):
        db = self._default_db()
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/appointments/route-manual/apply', json={
            'date': '2026-08-13',
            'assignments': [
                {'id': 1, 'driver_name': 'ORANG_TIDAK_ADA', 'order': 1},
                {'id': 2, 'driver_name': 'RIVAN', 'order': 1},
            ],
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['assigned'] == 1
        assert len(data['errors']) == 1
        assert 'tidak aktif/terdaftar' in data['errors'][0]['msg']

    def test_appointment_diluar_tanggal_dilewati(self, monkeypatch):
        db = self._default_db()
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/appointments/route-manual/apply', json={
            'date': '2026-08-13',
            'assignments': [
                {'id': 999, 'driver_name': 'RIVAN', 'order': 1},
            ],
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['assigned'] == 0
        assert len(data['errors']) == 1
        assert 'tidak ditemukan' in data['errors'][0]['msg']

    def test_tanpa_penugasan_ditolak(self, monkeypatch):
        db = self._default_db()
        client, _ = self._register(monkeypatch, db)
        r = client.post('/api/appointments/route-manual/apply', json={'date': '2026-08-13', 'assignments': []})
        assert r.status_code == 400

    def test_hanya_chief_driver(self, monkeypatch):
        db = self._default_db()
        client, _ = self._register(monkeypatch, db, role='ga')
        r = client.post('/api/appointments/route-manual/apply', json={
            'date': '2026-08-13',
            'assignments': [{'id': 1, 'driver_name': 'RIVAN', 'order': 1}],
        })
        assert r.status_code == 403


# ================================================================
# DATA DEMO (v2.19.2) — dibuat & dibersihkan Admin
# ================================================================
class TestDemoData:
    def _register(self, monkeypatch, db, role='admin'):
        import modules.routes_api_master as ram
        conn = FakeConn(db)
        monkeypatch.setattr(ram, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(ram, 'get_master_connection', lambda: conn)
        import modules.config as mc
        monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(ram, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ram.register_master_api(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = 'admin'
        return client, conn

    def _db(self):
        return {
            'drivers': ['WICAK'],
            'members': [],
            'existing': set(),
            'appts': [
                {'id': 1, 'display_id': 'DEMO-R01', 'status': 'scheduled'},
                {'id': 2, 'display_id': 'APP-REAL-1', 'status': 'scheduled'},
            ],
            'dummy_tx': [{'id': 9}],
            'config': {},
        }

    def test_status_menghitung_demo(self, monkeypatch):
        client, _ = self._register(monkeypatch, self._db())
        r = client.get('/api/demo/status')
        assert r.status_code == 200
        d = r.get_json()
        assert d['demo_appointments'] == 1      # hanya DEMO-R01, bukan APP-REAL-1
        assert d['demo_transactions'] == 1

    def test_clean_hanya_menghapus_demo(self, monkeypatch):
        client, conn = self._register(monkeypatch, self._db())
        r = client.post('/api/demo/clean', json={'scope': 'all'})
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['summary']['routes'] == 1      # DEMO-R01 dihapus, APP-REAL-1 aman
        assert d['summary']['transactions'] == 1
        deletes = [sql for sql, _ in _all_log(conn) if sql.lstrip().upper().startswith('DELETE')]
        assert any('FROM appointments' in sql for sql in deletes)
        assert any('FROM transactions' in sql for sql in deletes)

    def test_seed_routes_idempoten(self, monkeypatch):
        db = self._db()
        db['appts'] = [{'id': 1, 'display_id': 'DEMO-R01', 'status': 'scheduled'}]
        client, conn = self._register(monkeypatch, db)
        r = client.post('/api/demo/seed', json={'scope': 'routes'})
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        # 1 sudah ada (DEMO-R01) → 19 dibuat dari 20 daftar demo
        assert d['summary']['routes'] == 19
        assert d['summary']['skipped_routes'] == 1
        inserts = [sql for sql, _ in _all_log(conn) if 'INSERT INTO appointments' in sql]
        assert len(inserts) == 19

    def test_scope_tidak_valid_ditolak(self, monkeypatch):
        client, _ = self._register(monkeypatch, self._db())
        assert client.post('/api/demo/seed', json={'scope': 'hacker'}).status_code == 400
        assert client.post('/api/demo/clean', json={'scope': 'hacker'}).status_code == 400

    def test_non_admin_ditolak_403(self, monkeypatch):
        client, _ = self._register(monkeypatch, self._db(), role='ga')
        assert client.post('/api/demo/seed', json={'scope': 'all'}).status_code == 403
        assert client.post('/api/demo/clean', json={'scope': 'all'}).status_code == 403
        assert client.get('/api/demo/status').status_code == 403


# ================================================================
# IDENTITAS PERUSAHAAN / CABANG (v2.19.2) — multi-cabang
# ================================================================
class TestCompanyIdentity:
    def _register(self, monkeypatch, db, role='admin'):
        import modules.routes_api_master as ram
        import modules.config as mc
        conn = FakeConn(db)
        monkeypatch.setattr(ram, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(ram, 'log_activity_async', lambda *a, **k: None)
        # get_company_identity / save_company_identity mengimpor get_db_connection
        # dari modules.config saat dipanggil → patch di sumbernya
        monkeypatch.setattr(mc, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        ram.register_master_api(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = 'admin'
        return client, conn

    def test_get_publik_mengembalikan_default_dan_tersimpan(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': [], 'dummy_tx': [],
              'config': {'company_name': 'PT CABANG SURABAYA', 'system_name': 'WorkHub Cabang'}}
        client, _ = self._register(monkeypatch, db)
        r = client.get('/api/system-config/identity')
        assert r.status_code == 200
        d = r.get_json()
        assert d['company_name'] == 'PT CABANG SURABAYA'      # dari system_config
        assert d['system_name'] == 'WorkHub Cabang'
        assert d['company_subtitle']                          # fallback default
        assert d['system_version']

    def test_put_menyimpan_identitas(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': [], 'dummy_tx': [], 'config': {}}
        client, conn = self._register(monkeypatch, db)
        r = client.put('/api/system-config/identity', json={
            'company_name': 'PT CABANG MALANG',
            'company_subtitle': 'Sistem Operasional | Malang',
            'system_name': 'WorkHub Malang',
            'system_version': 'v1.0.0',
        })
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['identity']['company_name'] == 'PT CABANG MALANG'
        upserts = [sql for sql, _ in _all_log(conn) if 'INTO system_config' in sql]
        assert len(upserts) == 4

    def test_put_key_tidak_dikenal_ditolak(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': [], 'dummy_tx': [], 'config': {}}
        client, _ = self._register(monkeypatch, db)
        r = client.put('/api/system-config/identity', json={'hack_key': 'x'})
        assert r.status_code == 400

    def test_put_non_admin_ditolak_403(self, monkeypatch):
        db = {'drivers': [], 'members': [], 'existing': set(), 'appts': [], 'dummy_tx': [], 'config': {}}
        client, _ = self._register(monkeypatch, db, role='ga')
        r = client.put('/api/system-config/identity', json={'company_name': 'X'})
        assert r.status_code == 403


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])
