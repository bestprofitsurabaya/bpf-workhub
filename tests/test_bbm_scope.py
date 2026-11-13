"""Kontrak definisi BBM/kasbon/LPJ (v2.100.1 — Fase 2).

Mengunci tiga hal yang dulu membuat angka antarhalaman berbeda:

1. Kasbon cair memakai `handover_at` (dana benar-benar keluar), bukan hanya
   status COMPLETED — dana yang masih di driver wajib terhitung.
2. LPJ sah hanya `verified_ga`/`archived`, bukan semua yang non-rejected.
3. Identitas: kasbon.cair = kasbon.selesai + kasbon.outstanding.

Jalankan: python3 -m pytest tests/test_bbm_scope.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import bbm_scope  # noqa: E402


class FakeConn:
    """Conn minimal yang menjawab per bentuk query (tanpa DB)."""

    def cursor(self, dictionary=False):
        class Cur:
            def execute(self, sql, params=None):
                self.sql = ' '.join(str(sql).split())
                self.params = list(params or [])

            def fetchone(self):
                q, p = self.sql, self.params
                if 'FROM transactions' in q:
                    if p and p[0] == 'CASH_LPJ':
                        # LPJ sah menyertakan verified_ga; yang diajukan tidak.
                        if 'verified_ga' in p:
                            return {'count': 2, 'amount': 200.0, 'liter': 20.0}
                        return {'count': 1, 'amount': 50.0, 'liter': 5.0}
                    return {'count': 1, 'amount': 100.0, 'liter': 10.0}
                if 'FROM fuel_cash_requests' in q:
                    if "status = 'COMPLETED'" in q:
                        return {'count': 1, 'amount': 100.0}
                    if 'status IN (%s, %s)' in q:
                        return {'count': 2, 'amount': 150.0}
                    return {'count': 3, 'amount': 250.0}
                return {}

            def fetchall(self):
                return []

            def close(self):
                pass

        return Cur()

    def close(self):
        pass


def test_definisi_status_terkunci():
    assert bbm_scope.LPJ_VALID_STATUSES == ('verified_ga', 'archived')
    assert bbm_scope.CASH_OPEN_STATUSES == ('FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED')
    assert 'rejected' not in bbm_scope.LPJ_VALID_STATUSES


def test_default_period_inklusif():
    start, end = bbm_scope.default_period(7, today=__import__('datetime').date(2026, 11, 12))
    assert (start, end) == ('2026-11-06', '2026-11-12')


def test_kasbon_cair_memakai_handover_bukan_completed():
    c = FakeConn()
    cur = c.cursor()
    assert bbm_scope.monthly_cash_rows(c, 2026) == []
    # Query dijalankan oleh fungsi; periksa bentuk SQL-nya lewat cursor baru.
    c2 = FakeConn()
    captured = {}
    orig = c2.cursor

    def cursor(dictionary=False):
        k = orig(dictionary)
        real_execute = k.execute

        def execute(sql, params=None):
            captured['sql'] = ' '.join(str(sql).split())
            return real_execute(sql, params)

        k.execute = execute
        return k
    c2.cursor = cursor
    bbm_scope.monthly_cash_rows(c2, 2026)
    assert 'handover_at IS NOT NULL' in captured['sql']
    assert 'COMPLETED' not in captured['sql']


def test_lpj_sah_memakai_status_verified():
    captured = {}

    class Conn(FakeConn):
        def cursor(self, dictionary=False):
            k = super().cursor(dictionary)
            real_execute = k.execute

            def execute(sql, params=None):
                captured['sql'] = ' '.join(str(sql).split())
                captured['params'] = list(params or [])
                return real_execute(sql, params)

            k.execute = execute
            return k

    bbm_scope.monthly_lpj_rows(Conn(), 2026)
    assert 'verified_ga' in captured['params']
    assert 'archived' in captured['params']
    assert 'rejected' not in captured['sql']


def test_cash_totals_identitas_cair_selesai_outstanding():
    cash = bbm_scope.cash_totals(FakeConn())
    assert cash['cair']['amount'] == 250.0
    assert cash['selesai']['amount'] == 100.0
    assert cash['outstanding']['amount'] == 150.0
    # Kontrak: dana yang keluar = yang sudah selesai + yang masih di driver.
    assert cash['cair']['amount'] == cash['selesai']['amount'] + cash['outstanding']['amount']


def test_voucher_sah_dihitung_sekali_dan_masuk_rekap():
    """Voucher rekanan = beban BBM sekali saat pemakaian sah, bukan klaim/kasbon."""
    assert bbm_scope.VOUCHER_OPEN_STATUSES == ('pending', 'modified')
    assert bbm_scope.VOUCHER_VALID_STATUSES == ('verified_ga', 'archived')
    sql = bbm_scope.rekap_scope_sql()
    assert 'voucher_value' in sql


def test_rekap_scope_menyatukan_klaim_dibayar_dan_lpj_sah():
    """Rekap = klaim dibayar + LPJ sah, bukan hanya baris `archived`."""
    sql = bbm_scope.rekap_scope_sql()
    assert "'os_finance'" in sql and "'archived'" in sql
    assert "'verified_ga'" in sql
    assert 'rejected' not in sql
    assert 'pending' not in sql
    aliased = bbm_scope.rekap_scope_sql('t')
    assert 't.status' in aliased and 't.transaction_type' in aliased


def test_summary_memakai_definisi_yang_sama():
    data = bbm_scope.summary(FakeConn(), '2026-11-01', '2026-11-30')
    assert data['period'] == {'start': '2026-11-01', 'end': '2026-11-30'}
    assert data['claims']['lpj_sah']['amount'] == 200.0
    assert data['claims']['lpj_diajukan']['amount'] == 50.0
    assert data['kasbon']['cair']['amount'] == 250.0
    assert data['kasbon']['outstanding']['amount'] == 150.0
    assert data['realisasi']['lpj_sah'] == 200.0
    assert data['realisasi']['klaim_dibayar'] == 100.0
    assert data['claims']['voucher_sah']['amount'] == 100.0
    assert data['realisasi']['voucher_sah'] == 100.0
    assert data['realisasi']['total'] == 400.0
    assert data['meta']['basis_version'] == 'bbm-scope-2'
    assert 'outstanding' in data['meta']['basis']
    assert 'voucher' in data['meta']['basis']
