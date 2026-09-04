"""
Unit Tests untuk Sistem Appointment (Marketing -> Chief Driver -> Log Perjalanan)
BPF WorkHub v1.2

Jalankan:
    python3 -m pytest tests/test_appointments.py -v
"""

import sys
import os
import re

# Tambahkan parent directory ke path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.helpers import (
    detect_area,
    sesi_info,
    sesi_time,
    normalize_visit_time,
    SESI_TIME_RANGE,
    validate_appointment_input,
    generate_appointment_display_id,
    VALID_SESI,
)


# ================================================================
# TEST 1: Deteksi Area dari Alamat
# ================================================================
class TestDetectArea:
    def test_surabaya_barat_darmo(self):
        assert detect_area('Jl. Raya Darmo Permai 45, Surabaya') == 'Surabaya Barat'

    def test_surabaya_timur_rungkut(self):
        assert detect_area('Jl. Rungkut Industri Raya, Surabaya') == 'Surabaya Timur'

    def test_sidoarjo(self):
        assert detect_area('Jl. Pahlawan 12, Sidoarjo') == 'Sidoarjo'

    def test_case_insensitive(self):
        assert detect_area('DARMOKALI SURABAYA') == 'Surabaya Barat'

    def test_unknown_area(self):
        assert detect_area('Jl. Melati, Kota Malang') == 'Lainnya'

    def test_empty_alamat(self):
        assert detect_area('') == 'Lainnya'
        assert detect_area(None) == 'Lainnya'


# ================================================================
# TEST 2: Sesi Appointment (1 = 08.30, 2 = 14.30)
# ================================================================
class TestSesi:
    def test_valid_sesi_values(self):
        assert VALID_SESI == ('1', '2')

    def test_sesi1_waktu(self):
        assert sesi_time('1') == '08:30'
        info = sesi_info('1')
        assert info['label'] == 'Sesi 1'
        assert info['display'] == '08.30'

    def test_sesi2_waktu(self):
        assert sesi_time('2') == '14:30'
        info = sesi_info('2')
        assert info['label'] == 'Sesi 2'
        assert info['display'] == '14.30'

    def test_sesi_invalid(self):
        assert sesi_time('3') is None
        assert sesi_info('X') is None
        assert sesi_time('') is None


# ================================================================
# TEST 3: Validasi Input Appointment
# ================================================================
class TestValidasiInput:
    def test_valid_input(self):
        ok, errs, norm = validate_appointment_input({
            'nasabah_name': 'Budi Santoso',
            'marketing_member': 'Icang',
            'nasabah_phone': '08123456789',
            'alamat': 'Jl. Darmo 10, Surabaya',
            'sesi': '1',
            'appointment_date': '2026-08-08',
            'notes': 'Nasabah lama',
        })
        assert ok, errs
        assert norm['nasabah_name'] == 'Budi Santoso'
        assert norm['marketing_member'] == 'Icang'
        assert norm['sesi'] == '1'
        assert norm['appointment_date'] == '2026-08-08'

    def test_missing_marketing_member(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'A', 'alamat': 'Jl. A', 'sesi': '1',
            'appointment_date': '2026-08-08',
        })
        assert not ok
        assert 'marketing_member' in errs

    def test_missing_nama(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': '', 'marketing_member': 'Icang', 'alamat': 'Jl. A',
            'sesi': '1', 'appointment_date': '2026-08-08',
        })
        assert not ok
        assert 'nasabah_name' in errs

    def test_missing_alamat(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'A', 'marketing_member': 'Icang', 'alamat': '   ',
            'sesi': '1', 'appointment_date': '2026-08-08',
        })
        assert not ok
        assert 'alamat' in errs

    def test_missing_sesi(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'A', 'marketing_member': 'Icang', 'alamat': 'Jl. A',
            'sesi': '', 'appointment_date': '2026-08-08',
        })
        assert not ok
        assert 'sesi' in errs

    def test_sesi_invalid(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'A', 'marketing_member': 'Icang', 'alamat': 'Jl. A',
            'sesi': '3', 'appointment_date': '2026-08-08',
        })
        assert not ok
        assert 'sesi' in errs

    def test_missing_date(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'A', 'marketing_member': 'Icang', 'alamat': 'Jl. A',
            'sesi': '2',
        })
        assert not ok
        assert 'appointment_date' in errs

    def test_trims_whitespace(self):
        ok, errs, norm = validate_appointment_input({
            'nasabah_name': '  Andi  ',
            'marketing_member': '  Icang  ',
            'alamat': '  Jl. Rungkut  ',
            'sesi': '2',
            'appointment_date': '2026-08-08',
        })
        assert ok, errs
        assert norm['nasabah_name'] == 'Andi'
        assert norm['marketing_member'] == 'Icang'
        assert norm['alamat'] == 'Jl. Rungkut'


# ================================================================
# TEST 3b: Jam Kunjungan Bebas dalam Rentang Sesi (v2.15)
# ================================================================
class TestVisitTime:
    def test_default_ke_jam_mulai_sesi(self):
        t, err = normalize_visit_time('', '1')
        assert err is None
        assert t == '08:30'
        t, err = normalize_visit_time('', '2')
        assert err is None
        assert t == '14:30'

    def test_valid_dalam_rentang(self):
        assert normalize_visit_time('09:15', '1') == ('09:15', None)
        assert normalize_visit_time('16:00', '2') == ('16:00', None)

    def test_format_salah(self):
        t, err = normalize_visit_time('09-30', '1')
        assert err is not None
        assert 'HH:MM' in err
        t, err = normalize_visit_time('25:00', '1')
        assert err is not None
        t, err = normalize_visit_time('09:75', '1')
        assert err is not None
        t, err = normalize_visit_time('', '3')
        assert err is not None

    def test_jam_satu_digit_dinormalisasi(self):
        # '9:30' diterima & dinormalisasi ke '09:30' (mudah bagi user)
        t, err = normalize_visit_time('9:30', '1')
        assert err is None
        assert t == '09:30'

    def test_diluar_rentang_sesi(self):
        lo, hi = SESI_TIME_RANGE['1']
        t, err = normalize_visit_time('13:00', '1')  # sudah masuk Sesi 2
        assert err is not None
        assert 'rentang' in err
        t, err = normalize_visit_time(hi, '1')
        assert err is None
        t, err = normalize_visit_time(lo, '1')
        assert err is None
        t, err = normalize_visit_time('12:59', '2')
        assert err is not None

    def test_visit_time_ikut_tervalidasi_input(self):
        ok, errs, norm = validate_appointment_input({
            'nasabah_name': 'Budi', 'marketing_member': 'Icang', 'alamat': 'Jl. Darmo 1',
            'sesi': '1', 'appointment_date': '2026-08-08', 'visit_time': '10:00',
        })
        assert ok, errs
        assert norm['visit_time'] == '10:00'

    def test_visit_time_invalid_ditolak(self):
        ok, errs, _ = validate_appointment_input({
            'nasabah_name': 'Budi', 'marketing_member': 'Icang', 'alamat': 'Jl. Darmo 1',
            'sesi': '1', 'appointment_date': '2026-08-08', 'visit_time': '15:00',
        })
        assert not ok
        assert 'visit_time' in errs

    def test_visit_time_kosong_default_sesi(self):
        ok, errs, norm = validate_appointment_input({
            'nasabah_name': 'Budi', 'marketing_member': 'Icang', 'alamat': 'Jl. Darmo 1',
            'sesi': '2', 'appointment_date': '2026-08-08', 'visit_time': '',
        })
        assert ok, errs
        assert norm['visit_time'] == '14:30'


# ================================================================
# TEST 4: Display ID Appointment
# ================================================================
class TestDisplayId:
    def test_format(self):
        display_id = generate_appointment_display_id()
        assert display_id.startswith('APP-'), f"Harus APP-: {display_id}"
        parts = display_id.split('-')
        assert len(parts) == 4, f"Harus 4 bagian: {display_id}"
        assert parts[1] and parts[1].isupper(), "Cabang uppercase"
        assert re.match(r'^\d{8}$', parts[2]), "Bagian tanggal 8 digit"
        assert re.match(r'^\d{4}$', parts[3]), "Bagian urut 4 digit"

    def test_unique(self):
        ids = {generate_appointment_display_id() for _ in range(50)}
        assert len(ids) == 50, "Display ID harus unik"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])
