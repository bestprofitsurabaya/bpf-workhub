"""Unit test — scripts/forensic_overtime_tz.py (v2.39.3).

Verifikasi overtime (zona feed, paritas feed↔DB, simulasi transisi
ISO→wall-clock) harus tetap terlindungi CI. Skrip forensik diuji sebagai
modul (DB di-mock — tidak ada jaringan/DB nyata di CI):

- classify()         : klasifikasi format nilai waktu feed
- census_feed()      : verdict script LAMA (ISO-UTC) vs script v2 (wall-clock)
- _norm_val()        : normalisasi nilai DB (datetime termasuk 00:00:00)
- bandingkan_db()    : paritas per kunci desain upsert (driver & ob) —
                       duplikat pengajuan OB di-dedup, baris terakhir menang
- simulasi_transisi  : source_uid stabil 100% saat feed pindah ke wall-clock

Fallback +7 WIB parser ISO-UTC sendiri sudah dikunci di
tests/test_overtime_wallclock.py — di sini diuji lapisan forensiknya.

Jalankan: python3 -m pytest tests/test_overtime_forensic.py -v
"""
import importlib.util
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_FORENSIC = os.path.join(os.path.dirname(__file__), '..',
                         'scripts', 'forensic_overtime_tz.py')
_spec = importlib.util.spec_from_file_location('forensic_overtime_tz', _FORENSIC)
forensic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(forensic)

from modules.overtime_helpers import map_headers, normalize_driver_row  # noqa: E402

DRIVER_HEADERS = ['Timestamp', 'Email Address', 'Nama Lengkap',
                  'Tanggal Overtime', 'Dari / IN', 'Sampai / OUT',
                  'Keterangan', 'No. Kendaraan']

OB_HEADERS = ['Timestamp', 'Nama Lengkap', 'Posisi', 'Tanggal',
              'Waktu Mulai Overtime', 'Waktu Selesai Overtime', 'Keterangan']

ISO_ROW = {
    'Timestamp': '2020-12-12T07:08:54.000Z',
    'Email Address': 'budi@contoh.id',
    'Nama Lengkap': 'Budi',
    'Tanggal Overtime': '2020-12-11T17:00:00.000Z',
    'Dari / IN': '1899-12-30T07:24:56.000Z',
    'Sampai / OUT': '1899-12-30T10:47:56.000Z',
    'Keterangan': 'cover shift',
    'No. Kendaraan': 'B 1234 XYZ',
}

WALL_ROW = {
    'Timestamp': '2020-12-12 14:08:54',
    'Email Address': 'budi@contoh.id',
    'Nama Lengkap': 'Budi',
    'Tanggal Overtime': '2020-12-12',
    'Dari / IN': '07:24:56',
    'Sampai / OUT': '10:47:56',
    'Keterangan': 'cover shift',
    'No. Kendaraan': 'B 1234 XYZ',
}

OB_ROW = {
    'Timestamp': '2026-01-05T13:32:44.000Z',
    'Nama Lengkap': 'Faisol',
    'Posisi': 'OB',
    'Tanggal': '2026-01-04T17:00:00.000Z',
    'Waktu Mulai Overtime': '1899-12-30T16:29:00.000Z',
    'Waktu Selesai Overtime': '1899-12-30T18:32:00.000Z',
    'Keterangan': 'gledek',
}


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self, dictionary=True):
        return _FakeCursor(self._rows)

    def close(self):
        pass


# ============================================================
# classify — klasifikasi format nilai waktu
# ============================================================
class TestClassify:
    def test_format_dikenal_semua(self):
        assert forensic.classify('2020-12-12T07:08:54.000Z') == 'iso_utc'
        assert forensic.classify('2020-12-12 14:08:54') == 'wall_clock'
        assert forensic.classify('2020-12-12') == 'tanggal_wall'
        assert forensic.classify('14:08') == 'jam_wall'
        assert forensic.classify('14:08:54') == 'jam_wall'
        assert forensic.classify('1899-12-30T07:24:56.000Z') == 'iso_utc'
        assert forensic.classify('') == 'kosong'
        assert forensic.classify('6:29 PM') == 'lain'

    def test_iso_menang_atas_epoch_1899(self):
        # Sel jam Google Sheets = epoch 1899 — tetap ISO-UTC (script lama).
        assert forensic.classify('1899-12-30T11:47:56.000Z') == 'iso_utc'


# ============================================================
# _norm_val — normalisasi nilai DB utk pembanding
# ============================================================
class TestNormVal:
    def test_datetime_dan_tengah_malam(self):
        assert forensic._norm_val(datetime(2026, 1, 5, 13, 32, 44)) == \
            '2026-01-05 13:32:44'
        # Regresi: datetime 00:00:00 TIDAK boleh diformat tanggal saja
        assert forensic._norm_val(datetime(2026, 1, 5, 0, 0, 0)) == \
            '2026-01-05 00:00:00'

    def test_date_murni_dan_lainnya(self):
        assert forensic._norm_val(date(2026, 1, 5)) == '2026-01-05'
        assert forensic._norm_val(None) == ''
        assert forensic._norm_val('  x ') == 'x'


# ============================================================
# census_feed — verdict feed script lama vs v2
# ============================================================
class TestCensusFeed:
    def test_feed_script_lama(self):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        census, contoh, verdict = forensic.census_feed([ISO_ROW], headers, idx)
        assert verdict == 'SCRIPT_LAMA_ISO_UTC'
        assert census['submitted_at']['iso_utc'] == 1
        assert 'Timestamp=2020-12-12T07:08:54.000Z' in (contoh['submitted_at'] or '')

    def test_feed_script_v2_wallclock(self):
        headers = list(WALL_ROW.keys())
        idx = map_headers(headers)
        census, contoh, verdict = forensic.census_feed([WALL_ROW], headers, idx)
        assert verdict == 'SCRIPT_V2_WALLCLOCK'
        assert census['submitted_at']['wall_clock'] == 1

    def test_feed_kosong_tidak_jelas(self):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        _, _, verdict = forensic.census_feed(
            [{k: '' for k in headers}], headers, idx)
        assert verdict == 'TIDAK_JELAS'


# ============================================================
# bandingkan_db — paritas per kunci desain upsert (DB di-mock)
# ============================================================
def _db_rows_dari_normalisasi(mod, feed_rows, headers, idx):
    """Bangun baris DB PERSIS seperti hasil upsert produksi (fungsi
    normalisasi yang sama) — DB side test mencerminkan pipeline nyata."""
    rows = []
    for n, r in enumerate(feed_rows):
        row = (normalize_driver_row(r, headers, idx, n) if mod == 'driver'
               else forensic._normalize_ob_row(r, headers, idx, n))
        if not row:
            continue
        ts = row.get('submitted_at')
        rows.append({
            'nama': row['nama'],
            'submitted_at': (datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                             if ts else None),
            'tanggal': row.get('tanggal', ''),
            'waktu_mulai': row.get('waktu_mulai', ''),
            'waktu_selesai': row.get('waktu_selesai', ''),
        })
    return rows


class TestBandingkanDb:
    def test_driver_paritas_ok(self, monkeypatch):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        db_rows = _db_rows_dari_normalisasi('driver', [ISO_ROW], headers, idx)
        monkeypatch.setattr(forensic, 'get_db_connection',
                            lambda: _FakeConn(db_rows))
        hasil = forensic.bandingkan_db('driver', [ISO_ROW], headers, idx)
        assert hasil['paritas'] == 'OK'
        assert hasil['cocok_kunci'] == 1
        assert hasil['selisih_field'] == 0
        assert hasil['hilang_di_db'] == 0 and hasil['extra_di_db'] == 0

    def test_driver_selisih_jam_terdeteksi(self, monkeypatch):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        db_rows = _db_rows_dari_normalisasi('driver', [ISO_ROW], headers, idx)
        db_rows[0]['waktu_mulai'] = '99:99'  # jam di DB beda dari sheet
        monkeypatch.setattr(forensic, 'get_db_connection',
                            lambda: _FakeConn(db_rows))
        hasil = forensic.bandingkan_db('driver', [ISO_ROW], headers, idx)
        assert hasil['paritas'] == 'PERIKSA'
        assert hasil['selisih_field'] == 1

    def test_ob_duplikat_dedup_by_design(self, monkeypatch):
        # Dua pengajuan ganda (nama|tanggal|jam-mulai sama, Timestamp beda):
        # kunci desain upsert OB → dedup, baris TERAKHIR sheet menang.
        r1 = dict(OB_ROW, Timestamp='2026-01-05T13:32:44.000Z')
        r2 = dict(OB_ROW, Timestamp='2026-01-05T14:32:44.000Z')
        headers = list(OB_HEADERS)
        idx = map_headers(headers)
        db_rows = _db_rows_dari_normalisasi('ob', [r2], headers, idx)
        monkeypatch.setattr(forensic, 'get_db_connection',
                            lambda: _FakeConn(db_rows))
        hasil = forensic.bandingkan_db('ob', [r1, r2], headers, idx)
        assert hasil['paritas'] == 'OK', hasil
        assert hasil['hilang_di_db'] == 0  # duplikat BUKAN data hilang
        # Yang menang = Timestamp terakhir (14:32 → +7 = 21:32)
        assert db_rows[0]['submitted_at'] == datetime(2026, 1, 5, 21, 32, 44)

    def test_ob_baris_feed_belum_tersync_terdeteksi(self, monkeypatch):
        headers = list(OB_HEADERS)
        idx = map_headers(headers)
        db_rows = _db_rows_dari_normalisasi('ob', [OB_ROW], headers, idx)[1:]
        monkeypatch.setattr(forensic, 'get_db_connection',
                            lambda: _FakeConn(db_rows))
        hasil = forensic.bandingkan_db('ob', [OB_ROW], headers, idx)
        assert hasil['paritas'] == 'PERIKSA'
        assert hasil['hilang_di_db'] == 1

    def test_db_mati_fail_clear(self, monkeypatch):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        monkeypatch.setattr(forensic, 'get_db_connection', lambda: None)
        hasil = forensic.bandingkan_db('driver', [ISO_ROW], headers, idx)
        assert hasil['error'] == 'DB tidak terjangkau'


# ============================================================
# simulasi_transisi — UID stabil saat feed pindah ke wall-clock
# ============================================================
class TestSimulasiTransisi:
    def test_uid_stabil_iso_ke_wallclock(self):
        headers = list(ISO_ROW.keys())
        idx = map_headers(headers)
        rows = [dict(ISO_ROW, **{'Nama Lengkap': f'Karyawan {i}'})
                for i in range(3)]
        hasil = forensic.simulasi_transisi_iso_ke_wallclock(rows, headers, idx)
        assert hasil['ok'] is True
        assert hasil['uid_stabil'] == hasil['diuji'] == 3
        assert hasil['contoh_gagal'] is None

    def test_feed_wallclock_tidak_diuji(self):
        headers = list(WALL_ROW.keys())
        idx = map_headers(headers)
        hasil = forensic.simulasi_transisi_iso_ke_wallclock(
            [WALL_ROW], headers, idx)
        assert hasil['ok'] is False
        assert hasil['diuji'] == 0

    def test_alias_timestamp_tak_ada(self):
        headers = ['Nama Lengkap']
        idx = map_headers(headers)
        hasil = forensic.simulasi_transisi_iso_ke_wallclock(
            [{'Nama Lengkap': 'Budi'}], headers, idx)
        assert 'error' in hasil


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
