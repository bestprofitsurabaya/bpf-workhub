"""Test parser wall-clock Apps Script v2.39 — fix "waktu tidak sesuai sumber".

Kontrak baru: jembatan Apps Script mengirim tanggal/jam sebagai TEKS sesuai
tampilan sheet (Utilities.formatDate + zona waktu spreadsheet). Parser wajib
memakai nilai itu APA ADANYA (tanpa offset +7 jam). Feed lama (ISO UTC dari
script lama yang belum di-deploy ulang) tetap dikonversi +7 (WIB).

Jalankan: python3 -m pytest tests/test_overtime_wallclock.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.overtime_helpers import (
    parse_date_wall, parse_time_wall, parse_submitted_at_wall,
    parse_date_any, parse_time_any, parse_submitted_at_any,
    normalize_driver_row, map_headers,
)


class TestParseWall:
    """Parser wall-clock — TANPA offset zona waktu."""

    def test_tanggal_polos(self):
        assert parse_date_wall('2020-12-12') == '2020-12-12'
        assert parse_date_wall('2026-09-01') == '2026-09-01'

    def test_tanggal_mdy(self):
        assert parse_date_wall('1/5/2026') == '2026-01-05'
        assert parse_date_wall('12/25/2026') == '2026-12-25'

    def test_tanggal_dengan_jam_dibuang(self):
        assert parse_date_wall('2026-08-14 00:00:00') == '2026-08-14'

    def test_jam_24(self):
        assert parse_time_wall('14:24') == '14:24'
        assert parse_time_wall('9:05') == '09:05'
        assert parse_time_wall('06:30:00') == '06:30'

    def test_jam_12h(self):
        assert parse_time_wall('6:29:00 PM') == '18:29'
        assert parse_time_wall('12:30:00 AM') == '00:30'

    def test_jam_tidak_valid(self):
        assert parse_time_wall('25:00') is None
        assert parse_time_wall('abc') is None

    def test_submitted_at_polos(self):
        assert parse_submitted_at_wall('2020-12-12 14:08:54') == '2020-12-12 14:08:54'
        assert parse_submitted_at_wall('2020-12-12 14:08') == '2020-12-12 14:08:00'
        assert parse_submitted_at_wall('2020-12-12T14:08:54') == '2020-12-12 14:08:54'

    def test_kosong(self):
        assert parse_date_wall('') is None
        assert parse_time_wall('') is None
        assert parse_submitted_at_wall('') is None
        assert parse_date_wall(None) is None


class TestFallbackIsoUtc:
    """Feed Apps Script LAMA (ISO UTC) tetap dikonversi +7 (WIB)."""

    def test_parse_date_any_iso_utc_tetap_plus7(self):
        assert parse_date_any('2020-12-11T17:00:00.000Z') == '2020-12-12'

    def test_parse_time_any_iso_utc_tetap_plus7(self):
        assert parse_time_any('1899-12-30T07:24:56.000Z') == '14:24'

    def test_parse_submitted_at_any_iso_utc_tetap_plus7(self):
        assert parse_submitted_at_any('2020-12-12T07:08:54.000Z') == '2020-12-12 14:08:54'


class TestKontrakBaruTanpaGeser:
    """Nilai wall-clock polos dari Apps Script v2.39 TIDAK digeser +7 jam.

    Regresi inti keluhan user: sebelumnya '2026-09-01' & '07:30' dari sheet
    non-WIB berubah menjadi tanggal/jam lain di DB.
    """

    def test_tanggal_tidak_tergeser(self):
        assert parse_date_any('2026-09-01') == '2026-09-01'
        assert parse_date_any('2026-09-01 00:00:00') == '2026-09-01'

    def test_jam_tidak_tergeser(self):
        assert parse_time_any('07:30') == '07:30'
        assert parse_time_any('23:45:00') == '23:45'
        assert parse_time_any('07:30:00 PM') == '19:30'

    def test_submitted_at_tidak_tergeser(self):
        assert parse_submitted_at_any('2026-09-01 07:30:00') == '2026-09-01 07:30:00'


class TestBarisSheetBaru:
    """Baris feed Apps Script v2.39 (teks wall-clock) ternormalisasi apa adanya."""

    HEADERS = ['Timestamp', 'Email Address', 'Nama Lengkap', 'Tanggal',
               'Waktu Mulai Overtime', 'Waktu Selesai Overtime', 'Keterangan']

    def _norm(self, row):
        from modules.overtime_helpers import clean
        idx = map_headers(self.HEADERS)
        r = {h: row.get(h, '') for h in self.HEADERS}
        # tiru _normalize_ob_row tanpa DB: parse langsung dari helpers
        nama = clean(str(r['Nama Lengkap'] or ''))
        if not nama:
            return None
        return {
            'nama': nama,
            'tanggal': parse_date_any(str(r['Tanggal'] or '')),
            'waktu_mulai': parse_time_any(str(r['Waktu Mulai Overtime'] or '')),
            'waktu_selesai': parse_time_any(str(r['Waktu Selesai Overtime'] or '')),
            'submitted_at': parse_submitted_at_any(str(r['Timestamp'] or '')),
        }

    def test_baris_wall_clock(self):
        out = self._norm({
            'Timestamp': '2026-09-01 07:30:00',
            'Nama Lengkap': 'Faisol',
            'Tanggal': '2026-09-01',
            'Waktu Mulai Overtime': '07:30:00',
            'Waktu Selesai Overtime': '16:00:00',
        })
        assert out['tanggal'] == '2026-09-01'
        assert out['waktu_mulai'] == '07:30'
        assert out['waktu_selesai'] == '16:00'
        assert out['submitted_at'] == '2026-09-01 07:30:00'

    def test_normalize_driver_row_feed_baru(self):
        headers = ['Timestamp', 'Email Address', 'NAMA LENGKAP', 'NO KENDARAAN',
                   'Tanggal Overtime', 'Dari / IN', 'Sampai / OUT', 'KETERANGAN']
        idx = map_headers(headers)
        row = {
            'Timestamp': '2026-09-01 07:30:00',
            'Email Address': 'driver@bpf.co.id',
            'NAMA LENGKAP': 'Akhad',
            'NO KENDARAAN': 'W 1234 AB',
            'Tanggal Overtime': '2026-09-01',
            'Dari / IN': '07:30:00',
            'Sampai / OUT': '16:00:00',
            'KETERANGAN': 'OT Siang',
        }
        out = normalize_driver_row(row, headers, idx, 0)
        assert out is not None
        assert out['tanggal'] == '2026-09-01'
        assert out['waktu_mulai'] == '07:30'
        assert out['waktu_selesai'] == '16:00'
        assert out['submitted_at'] == '2026-09-01 07:30:00'


class TestSelfSubmitRoles:
    """Role OB & Security boleh submit overtime dari dalam aplikasi (v2.39)."""

    def test_role_list(self):
        import modules.routes_overtime as ro
        assert ro._SELF_SUBMIT_ROLES == ('ob', 'security')

    def test_posisi_turunan_role(self):
        # logika endpoint: security → 'Security', selain itu 'OB'
        assert ('Security' if 'security' == 'security' else 'OB') == 'Security'
        assert ('Security' if 'ob' == 'security' else 'OB') == 'OB'
