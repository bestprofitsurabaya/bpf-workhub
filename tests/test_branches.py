"""
Unit Tests — Multi-Cabang (v2.19.2)

- POST /api/branches/save | switch | activate/deactivate (admin)
- Login: session['branch_code'] dari users.branch_code; cabang nonaktif ditolak
- Routing DB: resolve_db_name memakai branch_code sesi

Pola sama dengan test_water / test_bulk_accounts_manual_route (DB di-fake).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask


# ---------------------------------------------------------------------------
# Sumber tunggal ekstraktor teks PDF — lihat tests/pdf_text.py.
from tests.pdf_text import pdf_text as _pdf_text  # noqa: E402


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.lastrowid = 1
        self.log = []

    def execute(self, sql, params=None):
        sql = sql or ''
        params = params or ()
        self.log.append((sql, params))
        up = sql.lstrip().upper()
        if up.startswith('INSERT'):
            self.rowcount = 1
            self.lastrowid += 1
        elif up.startswith('UPDATE'):
            self.rowcount = 1
        elif up.startswith('DELETE'):
            self.rowcount = 1
        else:
            self.rowcount = 0
        return None

    def fetchall(self):
        s = self.log[-1][0] if self.log else ''
        if 'COUNT(*)' in s and 'FROM users' in s:
            from collections import Counter
            cnt = Counter((u.get('branch_code') or 'SBY') for u in self.db.get('users', {}).values())
            return [{'bc': k, 'c': v} for k, v in cnt.items()]
        if 'FROM branches' in s:
            return [dict(b) for b in self.db.get('branches', {}).values()]
        if 'FROM users' in s:
            return [dict(u) for u in self.db.get('users', {}).values()]
        return []

    def fetchone(self):
        if not self.log:
            return None
        s, params = self.log[-1]
        if 'COUNT(*)' in s:
            if 'FROM transactions' in s:
                return {'c': len(self.db.get('dummy_tx', []))}
            if 'FROM appointments' in s:
                return {'c': sum(1 for a in self.db['appts']
                                 if str(a.get('display_id', '')).startswith('DEMO-'))}
            return {'c': 0}
        if 'FROM users' in s:
            if 'marketing_yusie_sby' in s:
                return {'id': 1}
            if params:
                u = self.db.get('users', {}).get(params[0])
                return dict(u) if u else None
        if 'FROM appointments' in s and params:
            for a in self.db.get('appts', []):
                if a.get('display_id') == params[0]:
                    return {'id': a['id']}
            return None
        if 'FROM branches' in s and params:
            b = self.db.get('branches', {}).get(params[0])
            return dict(b) if b else None
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


def _db():
    return {
        'users': {
            'admin': {'username': 'admin', 'full_name': 'Administrator', 'role': 'admin',
                      'branch_code': 'SBY', 'is_active': 1},
            'wicak': {'username': 'wicak', 'full_name': 'Wicak', 'role': 'driver',
                      'branch_code': 'SBY', 'is_active': 1},
            'eko': {'username': 'eko', 'full_name': 'Eko', 'role': 'driver',
                    'branch_code': 'MLG', 'is_active': 1},
        },
        'branches': {
            'SBY': {'code': 'SBY', 'name': 'Cabang Surabaya', 'db_name': 'bpf_asset_system',
                    'is_active': 1},
            'MLG': {'code': 'MLG', 'name': 'Cabang Malang', 'db_name': 'bpf_branch_malang',
                    'is_active': 1},
        },
    }


def _patch_branch_api(monkeypatch, db):
    import modules.routes_branches as rb
    import modules.branch_manager as bm
    import modules.config as mc
    conn = FakeConn(db)
    monkeypatch.setattr(bm, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rb, 'log_activity_async', lambda *a, **k: None)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rb.register_branch_routes(app)
    client = app.test_client()
    return client, conn


class TestBranchAPI:
    def test_list_branches_admin(self, monkeypatch):
        client, _ = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
        r = client.get('/api/branches')
        assert r.status_code == 200
        codes = [b['code'] for b in r.get_json()['branches']]
        assert codes == ['SBY', 'MLG']

    def test_save_branch_baru(self, monkeypatch):
        client, conn = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
        r = client.post('/api/branches/save', json={
            'code': 'BDG', 'name': 'Cabang Bandung', 'db_name': 'bpf_branch_bandung',
            'city': 'Bandung', 'company_name': 'PT BESTPROFIT FUTURES', 'ensure_db': False,
        })
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['branch']['code'] == 'BDG'
        inserts = [sql for sql, _ in conn.cursors[0].log if 'INSERT INTO branches' in sql]
        assert len(inserts) == 1

    def test_save_branch_validasi(self, monkeypatch):
        client, _ = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
        assert client.post('/api/branches/save', json={'code': 'X', 'name': '', 'db_name': ''}).status_code == 400
        assert client.post('/api/branches/save', json={'code': 'X', 'name': 'X', 'db_name': 'bad name!'}).status_code == 400

    def test_switch_branch_menyetel_sesi(self, monkeypatch):
        client, _ = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
            s['user_name'] = 'admin'  # v2.37.0: Admin Pusat boleh ganti cabang
        r = client.post('/api/branches/switch', json={'code': 'MLG'})
        assert r.status_code == 200
        with client.session_transaction() as s:
            assert s['branch_code'] == 'MLG'
            assert s['branch_name'] == 'Cabang Malang'

    def test_switch_cabang_nonaktif_ditolak(self, monkeypatch):
        db = _db()
        db['branches']['MLG']['is_active'] = 0
        client, _ = _patch_branch_api(monkeypatch, db)
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
            s['user_name'] = 'admin'
        assert client.post('/api/branches/switch', json={'code': 'MLG'}).status_code == 404

    def test_switch_admin_cabang_ditolak(self, monkeypatch):
        # v2.37.0: admin_<kode> tidak boleh mengganti cabang kerja.
        client, _ = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
            s['user_name'] = 'admin_sby'
            s['branch_code'] = 'SBY'
        assert client.post('/api/branches/switch', json={'code': 'MLG'}).status_code == 403

    def test_non_admin_ditolak_403(self, monkeypatch):
        client, _ = _patch_branch_api(monkeypatch, _db())
        with client.session_transaction() as s:
            s['user_role'] = 'ga'
        assert client.get('/api/branches').status_code == 403
        assert client.post('/api/branches/save', json={}).status_code == 403
        assert client.post('/api/branches/switch', json={'code': 'MLG'}).status_code == 403


class TestLoginBranchScope:
    def _register(self, monkeypatch, db):
        import modules.routes_spa as rsp
        import modules.branch_manager as bm
        conn = FakeConn(db)
        monkeypatch.setattr(rsp, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(rsp, 'log_activity_async', lambda *a, **k: None)
        monkeypatch.setattr(bm, 'get_master_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        rsp.register_spa_routes(app)
        return app.test_client()

    def test_login_menyetel_branch_code(self, monkeypatch):
        client = self._register(monkeypatch, _db())
        r = client.post('/api/auth/login', json={'username': 'eko', 'pin': '123456'})
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['user']['branch_code'] == 'MLG'
        assert d['user']['branch_name'] == 'Cabang Malang'

    def test_login_tanpa_branch_kode_pakai_default(self, monkeypatch):
        db = _db()
        db['users']['wicak'] = {'username': 'wicak', 'full_name': 'Wicak', 'role': 'driver',
                                'branch_code': None, 'is_active': 1}
        client = self._register(monkeypatch, db)
        r = client.post('/api/auth/login', json={'username': 'wicak', 'pin': '123456'})
        assert r.status_code == 200
        assert r.get_json()['user']['branch_code'] == 'SBY'

    def test_login_cabang_nonaktif_ditolak(self, monkeypatch):
        db = _db()
        db['branches']['MLG']['is_active'] = 0
        client = self._register(monkeypatch, db)
        r = client.post('/api/auth/login', json={'username': 'eko', 'pin': '123456'})
        assert r.status_code == 403
        assert 'Cabang tidak aktif' in r.get_json()['msg']


class TestDbRouting:
    def test_resolve_db_name_dari_sesi(self, monkeypatch):
        import modules.config as mc
        monkeypatch.setattr(mc, 'DB_CONFIG', {**mc.DB_CONFIG, 'database': 'bpf_asset_system'})
        monkeypatch.setattr(
            'modules.branch_manager.get_branch_db_name',
            lambda code: 'bpf_branch_malang' if code == 'MLG' else None)
        app = Flask(__name__)
        app.secret_key = 'x'
        with app.test_request_context('/'):
            from flask import session
            session['branch_code'] = 'MLG'
            assert mc.resolve_db_name() == 'bpf_branch_malang'
        with app.test_request_context('/'):
            from flask import session
            session['branch_code'] = 'SBY'
            # SBY memakai DB master → resolve kembali ke default
            assert mc.resolve_db_name() == 'bpf_asset_system'
        with app.test_request_context('/'):
            assert mc.resolve_db_name() == 'bpf_asset_system'  # tanpa sesi


class TestAuditBranchCode:
    def test_log_activity_mencatat_branch_code(self, monkeypatch):
        """log_activity_async menangkap branch_code dari sesi saat dipanggil."""
        import modules.helpers as h
        db = {'users': {}, 'branches': {}, 'appts': [], 'dummy_tx': [], 'config': {}}
        conn = FakeConn(db)
        captured = {}

        class _SyncExecutor:
            def submit(self, fn, *a, **k):
                captured['insert'] = None
                fn()
                return None

        import modules.config as mc
        monkeypatch.setattr(h, 'production_pool_executor', _SyncExecutor())
        monkeypatch.setattr(mc, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'x'
        with app.test_request_context('/'):
            from flask import session
            session['branch_code'] = 'MLG'
            session['user_name'] = 'admin'
            h.log_activity_async(0, 'branch_switch', 'admin', 'Administrator', ip='1.2.3.4')
        inserts = [entry for entry in conn.cursors[0].log if 'INSERT INTO activity_logs' in entry[0]]
        assert len(inserts) == 1
        sql, params = inserts[0]
        assert 'branch_code' in sql
        # (log_tx_id, action, user_type, user_name, old, new, ip, ua, branch_code)
        assert params[8] == 'MLG'
        assert params[0] is None          # tx_id 0 → NULL (tanpa FK)

    def test_log_activity_tanpa_sesi_branch_none(self, monkeypatch):
        import modules.helpers as h
        db = {'users': {}, 'branches': {}, 'appts': [], 'dummy_tx': [], 'config': {}}
        conn = FakeConn(db)
        class _SyncExecutor:
            def submit(self, fn, *a, **k):
                fn()
                return None
        import modules.config as mc
        monkeypatch.setattr(h, 'production_pool_executor', _SyncExecutor())
        monkeypatch.setattr(mc, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'x'
        with app.test_request_context('/'):
            h.log_activity_async(5, 'login', 'user', 'admin')
        inserts = [entry for entry in conn.cursors[0].log if 'INSERT INTO activity_logs' in entry[0]]
        assert len(inserts) == 1
        assert inserts[0][1][8] is None   # tanpa sesi → branch None
        assert inserts[0][1][0] == 5      # tx_id valid diteruskan


class TestBranchSeedDemo:
    def test_seed_demo_ke_cabang_tertentu(self, monkeypatch):
        import modules.routes_branches as rb
        import modules.branch_manager as bm
        db = {
            'users': {'marketing_yusie_sby': {'username': 'marketing_yusie_sby', 'branch_code': 'SBY'}},
            'branches': {
                'MLG': {'code': 'MLG', 'name': 'Cabang Malang', 'db_name': 'bpf_branch_malang', 'is_active': 1},
            },
            'appts': [],
            'dummy_tx': [],
            'config': {},
        }
        import modules.config as mc
        conn = FakeConn(db)
        monkeypatch.setattr(bm, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(mc, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(rb, 'get_db_connection', lambda branch_code=None: conn)
        monkeypatch.setattr(rb, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        rb.register_branch_routes(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
        r = client.post('/api/branches/MLG/seed-demo')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()
        assert d['status'] == 'success'
        assert d['msg'].startswith('Data demo cabang MLG')
        # 20 rute DEMO dibuat + transaksi dummy di INSERT (periksa SEMUA cursor)
        all_log = [e for cur in conn.cursors for e in cur.log]
        inserts = [sql for sql, _ in all_log if 'INSERT INTO appointments' in sql]
        assert len(inserts) == 20
        tx = [sql for sql, _ in all_log if 'INSERT IGNORE INTO transactions' in sql]
        assert len(tx) == 1

    def test_seed_demo_cabang_nonaktif_ditolak(self, monkeypatch):
        import modules.routes_branches as rb
        import modules.branch_manager as bm
        db = {
            'users': {},
            'branches': {'MLG': {'code': 'MLG', 'name': 'Cabang Malang', 'db_name': 'bpf_branch_malang', 'is_active': 0}},
            'appts': [], 'dummy_tx': [], 'config': {},
        }
        conn = FakeConn(db)
        monkeypatch.setattr(bm, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(rb, 'log_activity_async', lambda *a, **k: None)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        rb.register_branch_routes(app)
        client = app.test_client()
        with client.session_transaction() as s:
            s['user_role'] = 'admin'
        assert client.post('/api/branches/MLG/seed-demo').status_code == 404


class TestBranchStats:
    def test_branch_stats_utama(self, monkeypatch):
        """branch_stats: cabang utama dihitung dari master; user per branch_code."""
        import modules.branch_manager as bm
        db = {
            'users': {
                'admin': {'username': 'admin', 'branch_code': 'SBY'},
                'eko': {'username': 'eko', 'branch_code': 'MLG'},
            },
            'branches': {
                'SBY': {'code': 'SBY', 'name': 'Cabang Surabaya',
                        'db_name': 'bpf_asset_system', 'is_active': 1},
                'MLG': {'code': 'MLG', 'name': 'Cabang Malang',
                        'db_name': 'bpf_branch_malang', 'is_active': 1},
            },
            'appts': [{'id': 1, 'display_id': 'DEMO-R01', 'status': 'scheduled'}],
            'dummy_tx': [{'id': 9}],
            'config': {},
        }
        conn = FakeConn(db)
        monkeypatch.setattr(bm, 'get_master_connection', lambda: conn)
        monkeypatch.setattr(bm, 'DB_CONFIG', {**bm.DB_CONFIG, 'database': 'bpf_asset_system'})
        # Cabang MLG punya DB terpisah → di branch_stats memakai _pool_for
        # (diimpor dari modules.config di dalam fungsi). Mock agar gagal → 0.
        import modules.config as mc
        monkeypatch.setattr(mc, '_pool_for', lambda db_name: None)
        stats = bm.branch_stats(conn=conn)
        by_code = {s['code']: s for s in stats}
        assert by_code['SBY']['transactions'] == 1        # dari dummy_tx count query
        assert by_code['SBY']['appointments_today'] == 1  # DEMO-R01 terhitung (fake: semua demo)
        assert by_code['SBY']['users'] == 1              # admin (SBY)
        assert by_code['MLG']['users'] == 1              # eko (MLG)
        assert by_code['MLG']['transactions'] == 0       # DB MLG tidak tersedia


def test_consolidated_pdf_renders(monkeypatch):
    """ConsolidatedReportPDF: statistik + transaksi terbaru per cabang."""
    from datetime import datetime
    from modules.pdf_generator import ConsolidatedReportPDF

    stats = [
        {'code': 'SBY', 'name': 'Cabang Surabaya', 'db_name': 'bpf_asset_system',
         'transactions': 10, 'appointments_today': 3, 'users': 5, 'is_active': True},
        {'code': 'MLG', 'name': 'Cabang Malang', 'db_name': 'bpf_branch_malang',
         'transactions': 2, 'appointments_today': 1, 'users': 2, 'is_active': True},
    ]
    latest = {
        'SBY': [{'display_id': 'TX-1', 'driver_name': 'Wicak', 'nopol': 'N 1 AB',
                 'bbm_type': 'Pertalite', 'nominal': 100000, 'liter': 10.0,
                 'created_at': datetime.now()}],
        'MLG': [],
    }
    pdf = ConsolidatedReportPDF()
    pdf.add_page()
    pdf.generate(stats, latest, generated_by='Admin')
    raw = pdf.output()
    text = _pdf_text(raw)
    assert 'LAPORAN KONSOLIDASI' in text
    assert 'RINGKASAN PER CABANG' in text
    assert 'Cabang Malang' in text
    assert 'Wicak' in text


def test_consolidated_endpoint_admin_only(monkeypatch):
    """Endpoint konsolidasi: role admin (non-admin → 403)."""
    import modules.routes_branches as rb
    conn = FakeConn({'branches': []})
    monkeypatch.setattr(rb, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(rb, 'log_activity_async', lambda *a, **k: None)

    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rb.register_branch_routes(app)
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_role'] = 'ga'
        s['user_name'] = 'ga1'
    r = c.get('/api/branches/consolidated')
    assert r.status_code == 403


if __name__ == '__main__':
    import pytest

    pytest.main([__file__, '-v'])
