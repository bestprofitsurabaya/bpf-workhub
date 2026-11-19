"""Tes identitas — motto halaman login (v2.129.0).

Motto disimpan sebagai key `company_motto` di `system_config` (sama seperti
identitas lain) sehingga Admin dapat mengubahnya di /app/settings tanpa
menyentuh kode. Halaman login memakai nilai server; konstanta di frontend
hanya cadangan bila API belum termuat.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.company_identity import (  # noqa: E402
    IDENTITY_DEFAULTS, IDENTITY_KEYS, save_company_identity,
)


class FakeCursor:
    def __init__(self):
        self.params = []

    def execute(self, sql, params=None):
        self.params.append(params)

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.cur = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_motto_terdaftar_di_identitas():
    assert 'company_motto' in IDENTITY_KEYS
    assert IDENTITY_DEFAULTS['company_motto'] == 'Satu Platform, Semua Operasional'


def test_simpan_motto_menulis_system_config():
    conn = FakeConn()
    saved = save_company_identity(
        {'company_motto': '  Aman, Terpadu, Terpercaya  ', 'tidak_dikenal': 'x'},
        conn=conn,
    )
    assert saved == {'company_motto': 'Aman, Terpadu, Terpercaya'}
    assert conn.committed is True
    keys = [p[0] for p in conn.cur.params if p]
    assert 'company_motto' in keys
    assert 'tidak_dikenal' not in keys


def test_motto_boleh_dikosongkan_untuk_kembali_ke_default():
    """Nilai kosong disimpan; pembaca mengabaikan kosong → default dipakai."""
    conn = FakeConn()
    saved = save_company_identity({'company_motto': '   '}, conn=conn)
    assert saved == {'company_motto': ''}
