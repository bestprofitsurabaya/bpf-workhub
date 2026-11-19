"""Tes normalisasi rute trip (v2.127.2).

Regresi insiden 19 Nov 2026: `pukul_berangkat[]` kosong dari UI membuat
INSERT NULL ke kolom NOT NULL → HTTP 500 + pesan SQL mentah. Sekarang jam
rute diisi default jam keberangkatan dan validasi mengembalikan 400.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.routes_driver import _trip_at, _trip_km, _trip_pukul  # noqa: E402


def test_pukul_kosong_memakai_jam_keberangkatan():
    assert _trip_pukul('', '08:00', 'Pukul berangkat rute 1') == '08:00'
    assert _trip_pukul(None, '08:00', 'Pukul berangkat rute 1') == '08:00'
    assert _trip_pukul('   ', '08:00', 'Pukul berangkat rute 1') == '08:00'


def test_pukul_valid_dipertahankan():
    assert _trip_pukul('09:15', '08:00', 'Pukul tujuan rute 1') == '09:15'


@pytest.mark.parametrize('bad', ['25:00', '08:60', '8', 'pagi', '08.00'])
def test_pukul_tidak_valid_menghasilkan_pesan_manusiawi(bad):
    with pytest.raises(ValueError) as exc:
        _trip_pukul(bad, '08:00', 'Pukul berangkat rute 2')
    assert 'Pukul berangkat rute 2' in str(exc.value)
    assert 'HH:MM' in str(exc.value)


def test_km_kosong_nol_dan_desimal_dibulatkan():
    assert _trip_km('', 'KM rute 1') == 0
    assert _trip_km(None, 'KM rute 1') == 0
    assert _trip_km('12.7', 'KM rute 1') == 12
    assert _trip_km('-5', 'KM rute 1') == 0


def test_km_bukan_angka_ditolak():
    with pytest.raises(ValueError) as exc:
        _trip_km('abc', 'KM tujuan rute 1')
    assert 'KM tujuan rute 1 harus angka' in str(exc.value)


def test_trip_at_aman_untuk_list_pendek():
    assert _trip_at(['a', 'b'], 1) == 'b'
    assert _trip_at(['a'], 3) == ''
    assert _trip_at([], 0) == ''
