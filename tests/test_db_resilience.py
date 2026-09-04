"""
Unit Tests — Ketahanan Koneksi DB (v2.14.1)

Dua perbaikan kritis yang dilindungi di sini:

1. `get_db_connection()` fallback NON-POOL saat pool MySQL habis.
   Sebelumnya fallback memanggil `mysql.connector.connect()` yang (di
   mysql-connector 8.2.0) masih me-routing ke pool global yang sama karena
   `fallback_config` menyisakan `pool_reset_session` (salah satu CNX_POOL_ARGS)
   → sistem tak pernah pulih tanpa restart. Kini argumen pool dibuang total
   dan koneksi langsung dibuat via `MySQLConnection(...)`.

2. `log_activity_async()` menutup koneksi di `finally` — koneksi yang bocor
   saat query audit-log gagal akan menghabiskan pool dan melumpuhkan aplikasi.

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_db_resilience.py -v
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mysql.connector.errors import PoolError

from modules import config, helpers


# ============================================================
# 1. get_db_connection — jalur pool & fallback non-pool
# ============================================================

def test_pool_dipakai_saat_tersedia(monkeypatch):
    sentinel = object()

    class _PoolOK:
        def get_connection(self):
            return sentinel

    monkeypatch.setattr(config, 'db_pool', _PoolOK())
    assert config.get_db_connection() is sentinel


def test_fallback_non_pool_saat_pool_exhausted(monkeypatch):
    """Pool habis → fallback harus membuat koneksi langsung TANPA argumen pool."""

    class _PoolHabis:
        def get_connection(self):
            raise PoolError('Failed getting connection; pool exhausted')

    calls = {}

    class _FakeMySQLConnection:
        def __init__(self, **kwargs):
            calls['kwargs'] = kwargs

    monkeypatch.setattr(config, 'db_pool', _PoolHabis())
    monkeypatch.setattr(config, 'MySQLConnection', _FakeMySQLConnection)

    conn = config.get_db_connection()
    assert conn is not None

    # Semua argumen pool (CNX_POOL_ARGS) wajib dibuang — bila tersisa,
    # mysql.connector akan me-routing kembali ke pool yang sama.
    for banned in ('pool_name', 'pool_size', 'pool_reset_session'):
        assert banned not in calls['kwargs'], f'{banned} tidak boleh diteruskan ke fallback'


def test_fallback_juga_dipakai_saat_pool_tidak_ada(monkeypatch):
    """db_pool = None (mis. pool gagal init) → tetap bisa ambil koneksi."""

    calls = {}

    class _FakeMySQLConnection:
        def __init__(self, **kwargs):
            calls['kwargs'] = kwargs

    monkeypatch.setattr(config, 'db_pool', None)
    monkeypatch.setattr(config, 'MySQLConnection', _FakeMySQLConnection)

    conn = config.get_db_connection()
    assert conn is not None
    assert 'pool_name' not in calls['kwargs']


def test_fallback_retry_lalu_raise_saat_db_matipun(monkeypatch):
    """DB benar-benar mati → fallback me-retry lalu melempar (bukan None diam-diam)."""

    class _PoolHabis:
        def get_connection(self):
            raise PoolError('pool exhausted')

    class _SelaluGagal:
        def __init__(self, **kwargs):
            raise RuntimeError('connection refused')

    monkeypatch.setattr(config, 'db_pool', _PoolHabis())
    monkeypatch.setattr(config, 'MySQLConnection', _SelaluGagal)
    monkeypatch.setattr(time, 'sleep', lambda s: None)  # percepat retry

    import pytest
    with pytest.raises(RuntimeError):
        config.get_db_connection()


# ============================================================
# 2. log_activity_async — koneksi selalu dikembalikan ke pool
# ============================================================

class _FakeCursorGagal:
    def execute(self, *a, **k):
        raise RuntimeError('insert gagal')


class _FakeCursorSukses:
    def execute(self, *a, **k):
        pass


class _FakeConn:
    def __init__(self, cursor_factory):
        self._cursor = cursor_factory()
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        self.closed = True


def _wait_closed(fake, timeout=3.0):
    """Tunggu task async menutup koneksi (polling)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fake.closed:
            return True
        time.sleep(0.02)
    return fake.closed


# log_activity_async mengimpor get_db_connection secara lokal dari modules.config
# → monkeypatch cukup di config.get_db_connection


def test_log_async_tutup_koneksi_saat_query_gagal(monkeypatch):
    """Query audit-log error → koneksi TETAP ditutup (finally) — tidak bocor."""
    fake = _FakeConn(_FakeCursorGagal)
    monkeypatch.setattr(config, 'get_db_connection', lambda: fake)

    helpers.log_activity_async(None, 'login', 'user', 'admin')
    assert _wait_closed(fake), 'koneksi harus ditutup walau query gagal'


def test_log_async_tutup_koneksi_saat_sukses(monkeypatch):
    """Jalur sukses: commit lalu tutup (perilaku lama dipertahankan)."""
    fake = _FakeConn(_FakeCursorSukses)
    monkeypatch.setattr(config, 'get_db_connection', lambda: fake)

    helpers.log_activity_async(None, 'login', 'user', 'admin')
    assert _wait_closed(fake), 'koneksi harus ditutup setelah commit'


def test_log_async_aman_saat_koneksi_none(monkeypatch):
    """get_db_connection() mengembalikan None → tidak boleh crash."""
    monkeypatch.setattr(config, 'get_db_connection', lambda: None)

    helpers.log_activity_async(None, 'login', 'user', 'admin')  # tidak boleh raise
    time.sleep(0.1)  # beri waktu task async selesai


# ============================================================
# 3. E2E — pemulihan saat pool habis (simulasi skenario nyata)
# ============================================================

def _fake_user_cursor(rows):
    class _Cur:
        def __init__(self):
            self._rows = rows
            self._pos = 0
        def execute(self, q, params=None):
            return None
        def fetchone(self):
            if self._pos < len(self._rows):
                r = self._rows[self._pos]
                self._pos += 1
                return r
            return None
        def close(self):
            pass
    return _Cur()


def test_e2e_login_tetap_berhasil_saat_pool_habis(monkeypatch):
    """Simulasi skenario nyata: pool 10 koneksi habis total → login tetap 200.

    - db_pool.get_connection() SELALU melempar PoolError (pool exhausted).
    - Fallback MySQLConnection (non-pool) yang dikembalikan dapat menjawab
      query login → user ditemukan → sesi terbentuk (HTTP 200).
    - Ini membuktikan aplikasi TIDAK mati saat pool penuh (fail-open).
    """
    from flask import Flask

    class _PoolHabis:
        def get_connection(self):
            raise PoolError('Failed getting connection; pool exhausted')

    class _FakeConn:
        def cursor(self, dictionary=True):
            return _fake_user_cursor([{
                'role': 'admin', 'username': 'admin', 'full_name': 'Admin Utama',
            }])
        def commit(self):
            pass  # dipakai log_activity_async (thread async)
        def close(self):
            pass

    monkeypatch.setattr(config, 'db_pool', _PoolHabis())
    monkeypatch.setattr(config, 'MySQLConnection', lambda **kw: _FakeConn())

    # Multi-cabang: user tanpa branch_code → cabang default; stub lookup cabang
    # (fokus test ini adalah fail-open saat pool habis, bukan logika cabang).
    import modules.branch_manager as bm
    monkeypatch.setattr(bm, 'get_branch', lambda code: {
        'code': 'SBY', 'name': 'Cabang Surabaya', 'is_active': 1,
        'db_name': 'bpf_asset_system'})

    from modules.routes_spa import register_spa_routes
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_spa_routes(app)
    client = app.test_client()

    resp = client.post('/api/auth/login', json={'username': 'admin', 'pin': '123456'})
    assert resp.status_code == 200, f'login harus tetap berhasil walau pool habis: {resp.status_code}'
    data = resp.get_json()
    assert data['status'] == 'success'
    assert data['user']['role'] == 'admin'


def test_e2e_login_pool_habis_pin_salah_tetap_401(monkeypatch):
    """Saat pool habis, login PIN salah tetap ditolak 401 (tidak bocor status)."""
    from flask import Flask

    class _PoolHabis:
        def get_connection(self):
            raise PoolError('pool exhausted')

    class _FakeConn:
        def cursor(self, dictionary=True):
            return _fake_user_cursor([])  # tidak ada user → PIN salah
        def commit(self):
            pass
        def close(self):
            pass

    monkeypatch.setattr(config, 'db_pool', _PoolHabis())
    monkeypatch.setattr(config, 'MySQLConnection', lambda **kw: _FakeConn())

    from modules.routes_spa import register_spa_routes
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_spa_routes(app)
    client = app.test_client()

    resp = client.post('/api/auth/login', json={'username': 'admin', 'pin': '000000'})
    assert resp.status_code == 401
    assert resp.get_json()['status'] == 'error'
