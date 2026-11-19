"""Tes kolom bukti GPS (v2.127.3) — normalisasi waktu & akurasi posisi."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.gps_schema import (  # noqa: E402
    GPS_TABLES, parse_gps_at, parse_gps_accuracy,
)


def test_tabel_bukti_gps_mencakup_transaksi_trip_dan_lembur():
    assert set(GPS_TABLES) == {
        'transactions', 'trip_masters', 'overtime_driver', 'overtime_ob_security'}


def test_waktu_iso_dengan_z_dinormalisasi_ke_waktu_lokal():
    v = parse_gps_at('2026-11-19T10:51:16.949Z')
    assert v and len(v) == 19 and v[4] == '-' and v[10] == ' '


def test_waktu_iso_tanpa_z_dan_format_mysql_diterima():
    assert parse_gps_at('2026-11-19T08:05:00') == '2026-11-19 08:05:00'
    assert parse_gps_at('2026-11-19 08:05:00') == '2026-11-19 08:05:00'
    assert parse_gps_at('19/11/2026 08:05:00') == '2026-11-19 08:05:00'


def test_waktu_kosong_atau_rusak_menjadi_none():
    for bad in ('', None, '   ', 'kemarin', '2026-13-45 99:99:99'):
        assert parse_gps_at(bad) is None


def test_akurasi_dibulatkan_dan_dibatasi():
    assert parse_gps_accuracy('25.4') == 25
    assert parse_gps_accuracy(12) == 12
    assert parse_gps_accuracy('') is None
    assert parse_gps_accuracy(None) is None
    assert parse_gps_accuracy(0) is None
    assert parse_gps_accuracy(-3) is None
    assert parse_gps_accuracy('abc') is None
    assert parse_gps_accuracy(999999) is None
