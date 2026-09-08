"""Unit test — get_branch_identity() (v2.37.7).

Identitas kop dokumen per cabang dari tabel `branches` DB master,
dengan fallback berlapis ke identitas global:
- kolom kosong di baris cabang → identitas global
- branch_code kosong / baris tak ada / DB master mati → identitas global
- kunci kembali = nama field identity (company_name/company_subtitle/
  company_address/company_phone) — siap di-merge ke BPFBasePDF / meta.

Jalankan: python3 -m pytest tests/test_branch_identity.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from modules.company_identity import (get_branch_identity,
                                      get_company_identity,
                                      IDENTITY_DEFAULTS)


class FakeCursor:
    """Cursor palsu: cocokkan berdasarkan SQL — query branches → baris
    cabang; query lain (system_config) → tanpa baris (pakai default)."""

    def __init__(self, row):
        self.row = row
        self._sql = ''

    def execute(self, sql, params=None):
        self._sql = sql
        if 'FROM branches' in sql:
            assert 'code=%s' in sql, sql

    def fetchone(self):
        return self.row if 'FROM branches' in self._sql else None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, row):
        self._cursor = FakeCursor(row)
        self.closed = False

    def cursor(self, dictionary=False):
        # SATU cursor dipakai ulang — penghitung query tidak ter-reset per call
        return self._cursor

    def close(self):
        self.closed = True


def _global_identity():
    return get_company_identity(conn=FakeConn(None))


# ================================================================
# Sumber: tabel branches
# ================================================================
class TestDariBranches:
    def test_alamat_dan_telepon_cabang(self):
        row = {'company_name': 'PT BESTPROFIT FUTURES',
               'company_subtitle': 'Cabang Surabaya',
               'address': 'Graha Bukopin, Lantai 11, Surabaya',
               'phone': '031-5349888', 'city': 'Surabaya'}
        ident = get_branch_identity('SBY', conn=FakeConn(row))
        assert ident['company_address'] == 'Graha Bukopin, Lantai 11, Surabaya'
        assert ident['company_phone'] == '031-5349888'
        assert ident['company_subtitle'] == 'Cabang Surabaya'

    def test_kode_branch_lowercase_dinormalisasi(self):
        row = {'company_name': '', 'company_subtitle': '', 'address': 'A',
               'phone': '', 'city': 'Bandung'}
        ident = get_branch_identity('bdg', conn=FakeConn(row))
        assert ident['company_address'] == 'A'
        # subtitle kosong → fallback dari city
        assert ident['company_subtitle'] == 'Cabang Bandung'

    def test_subtitle_kosong_fallback_city(self):
        row = {'company_name': '', 'company_subtitle': '', 'address': '',
               'phone': '', 'city': 'Medan'}
        ident = get_branch_identity('MDN', conn=FakeConn(row))
        assert ident['company_subtitle'] == 'Cabang Medan'

    def test_kolom_kosong_fallback_global(self):
        """Kolom cabang yang kosong diisi dari identitas global, bukan ''.``"""
        ho = dict(IDENTITY_DEFAULTS)
        row = {'company_name': 'PT BESTPROFIT FUTURES',
               'company_subtitle': '', 'address': '', 'phone': '',
               'city': 'Semarang'}
        ident = get_branch_identity('SMG', conn=FakeConn(row))
        assert ident['company_name'] == ho['company_name']
        assert ident['company_address'] == ho['company_address']
        assert ident['company_phone'] == ho['company_phone']
        assert ident['company_subtitle'] == 'Cabang Semarang'


# ================================================================
# Fallback identitas global
# ================================================================
class TestFallback:
    def test_branch_code_kosong(self):
        ident = get_branch_identity('', conn=FakeConn(None))
        assert ident == get_company_identity(conn=FakeConn(None))

    def test_baris_tidak_ada(self):
        ident = get_branch_identity('XXX', conn=FakeConn(None))
        assert ident == get_company_identity(conn=FakeConn(None))

    def test_conn_none_db_tak_terjangkau(self, monkeypatch):
        """conn=None + DB tak terjangkau: get_db_connection melempar →
        helper tetap mengembalikan identitas default (tidak error)."""
        import modules.company_identity as ci

        def _boom(master=False):
            raise RuntimeError('db unreachable')
        monkeypatch.setattr('modules.config.get_db_connection', _boom)
        ident = get_branch_identity('SBY', conn=None)
        assert ident['company_name'] == IDENTITY_DEFAULTS['company_name']

    def test_conn_none_db_mengembalikan_none(self, monkeypatch):
        monkeypatch.setattr('modules.config.get_db_connection',
                            lambda master=False: None)
        ident = get_branch_identity('SBY', conn=None)
        assert ident['company_name'] == IDENTITY_DEFAULTS['company_name']

    def test_query_error_fail_open(self):
        class BoomConn:
            def cursor(self, dictionary=False):
                raise RuntimeError('db down')
        ident = get_branch_identity('SBY', conn=BoomConn())
        assert ident['company_name'] == IDENTITY_DEFAULTS['company_name']

    def test_koneksi_ditutup(self, monkeypatch):
        """Koneksi yang DIBUKA helper sendiri ditutup setelah dipakai."""
        import modules.config as cfg
        conn = FakeConn({'company_name': '', 'company_subtitle': '',
                         'address': 'X', 'phone': '', 'city': ''})
        monkeypatch.setattr(cfg, 'get_db_connection',
                            lambda branch_code=None, master=False: conn)
        get_branch_identity('SBY', conn=None)
        assert conn.closed

    def test_koneksi_pemanggil_tidak_ditutup(self):
        """Conn milik pemanggil jangan ditutup helper (pemanggil yang bertanggung jawab)."""
        conn = FakeConn({'company_name': '', 'company_subtitle': '',
                         'address': 'X', 'phone': '', 'city': ''})
        get_branch_identity('SBY', conn=conn)
        assert not conn.closed
