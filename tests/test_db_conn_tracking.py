"""Regresi v2.47.1 — koneksi DB request tidak boleh bocor dari pool.

Latar: route yang `return jsonify(error), 500` tanpa close() membuat pool
habis (gejala produksi "⚠ Pool exhausted"). Penjaringnya ada di
`release_request_connections()` (dipanggil teardown_request app.py).
"""
import pytest
from flask import Flask, g

from modules.config import _is_pooled_open, release_request_connections


class FakePooledConn:
    """Meniru PooledMySQLConnection: ._cnx dikosongkan saat close()."""

    def __init__(self):
        self._cnx = object()
        self.closed = 0

    def close(self):
        self.closed += 1
        self._cnx = None


class FakePlainConn:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class ExplodingConn:
    def close(self):
        raise RuntimeError('reset_session gagal')


@pytest.fixture()
def app_ctx():
    app = Flask(__name__)
    with app.test_request_context('/'):
        yield app


def test_release_closes_untouched_connection(app_ctx):
    conn = FakePooledConn()
    g._db_conns = [conn]
    release_request_connections()
    assert conn.closed == 1
    # g dibersihkan → teardown kedua tidak menutup ulang
    release_request_connections()
    assert conn.closed == 1


def test_release_skips_already_closed_pooled_conn(app_ctx):
    """close() kedua pada PooledMySQLConnection akan memasukkan None ke pool."""
    conn = FakePooledConn()
    conn.close()                      # route sudah menutup sendiri
    g._db_conns = [conn]
    release_request_connections()
    assert conn.closed == 1           # tidak dobel
    assert _is_pooled_open(conn) is False


def test_release_closes_non_pooled_fallback(app_ctx):
    conn = FakePlainConn()
    g._db_conns = [conn]
    release_request_connections()
    assert conn.closed == 1
    assert _is_pooled_open(conn) is True   # non-pool aman di-close ulang


def test_release_survives_broken_connection(app_ctx):
    good = FakePooledConn()
    g._db_conns = [ExplodingConn(), good]
    release_request_connections()          # tidak boleh raise
    assert good.closed == 1


def test_release_outside_request_context_is_noop():
    release_request_connections()          # tidak boleh raise / menyentuh appctx


def test_is_pooled_open_true_before_close():
    assert _is_pooled_open(FakePooledConn()) is True
