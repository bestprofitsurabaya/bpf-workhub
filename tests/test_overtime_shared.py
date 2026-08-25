"""Unit tests for modules/overtime_shared.py"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.overtime_shared import (
    validate_overtime_data, build_insert_sql, build_insert_params,
    serialize_overtime_row, get_display_prefix, make_source_uid, POSITIONS
)


class TestValidateOvertimeData(unittest.TestCase):
    """Test shared overtime validation."""

    def test_valid_ob_data(self):
        """Valid OB data should pass validation."""
        data = {
            'nama': 'Budi Santoso',
            'posisi': 'OB',
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
            'waktu_selesai': '17:00',
            'keterangan': 'Lembur proyek',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertTrue(is_valid)
        self.assertEqual(errors, {})
        self.assertEqual(cleaned['nama'], 'Budi Santoso')
        self.assertEqual(cleaned['posisi'], 'OB')
        self.assertEqual(cleaned['tanggal'], '2026-08-25')

    def test_valid_driver_data(self):
        """Valid Driver data should pass validation."""
        data = {
            'nama': 'Rivan Ahmad',
            'tanggal': '08/25/2026',
            'waktu_mulai': '6:00 AM',
            'waktu_selesai': '6:00 PM',
            'keterangan': 'Kunjungan client',
            'no_kendaraan': 'L 1234 ABC',
            'broker': 'Marketing ABC',
            'manager': 'Manager XYZ',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='driver')
        self.assertTrue(is_valid)
        self.assertEqual(cleaned['nama'], 'Rivan Ahmad')
        self.assertEqual(cleaned['no_kendaraan'], 'L 1234 ABC')
        self.assertEqual(cleaned['tanggal'], '2026-08-25')

    def test_missing_nama(self):
        """Missing nama should fail validation."""
        data = {
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertFalse(is_valid)
        self.assertIn('nama', errors)

    def test_missing_tanggal(self):
        """Missing tanggal should fail validation."""
        data = {
            'nama': 'Test User',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertFalse(is_valid)
        self.assertIn('tanggal', errors)

    def test_invalid_tanggal_format(self):
        """Invalid tanggal format should fail validation."""
        data = {
            'nama': 'Test User',
            'tanggal': '25-08-2026',  # Wrong format
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertFalse(is_valid)
        self.assertIn('tanggal', errors)

    def test_invalid_posisi(self):
        """Invalid posisi should fail validation."""
        data = {
            'nama': 'Test User',
            'posisi': 'Manager',
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertFalse(is_valid)
        self.assertIn('posisi', errors)

    def test_ob_requires_posisi(self):
        """OB modul should require posisi field."""
        data = {
            'nama': 'Test User',
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertFalse(is_valid)
        self.assertIn('posisi', errors)

    def test_driver_does_not_require_posisi(self):
        """Driver modul should NOT require posisi field."""
        data = {
            'nama': 'Test Driver',
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='driver')
        # Should pass (driver doesn't need posisi)
        self.assertNotIn('posisi', errors)

    def test_gps_fields_truncated(self):
        """GPS fields should be truncated to safe lengths."""
        data = {
            'nama': 'Test User',
            'posisi': 'OB',
            'tanggal': '2026-08-25',
            'waktu_mulai': '08:00',
            'gps_lat': '1.1234567890123456789012345',
            'gps_lon': '2.1234567890123456789012345',
            'gps_address': 'Jl. Test ' * 100,  # Very long
            'gps_kode_pos': '12345678901234',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertTrue(is_valid)
        self.assertEqual(len(cleaned['gps_lat']), 20)
        self.assertEqual(len(cleaned['gps_lon']), 20)
        self.assertEqual(len(cleaned['gps_address']), 500)
        self.assertEqual(len(cleaned['gps_kode_pos']), 10)

    def test_12h_time_parsing(self):
        """12-hour time format should be parsed correctly."""
        data = {
            'nama': 'Test User',
            'posisi': 'OB',
            'tanggal': '2026-08-25',
            'waktu_mulai': '6:30 PM',
            'waktu_selesai': '10:00 PM',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertTrue(is_valid)
        self.assertEqual(cleaned['waktu_mulai'], '18:30')
        self.assertEqual(cleaned['waktu_selesai'], '22:00')

    def test_mdy_date_parsing(self):
        """M/D/YYYY date format should be parsed correctly."""
        data = {
            'nama': 'Test User',
            'posisi': 'OB',
            'tanggal': '8/25/2026',
            'waktu_mulai': '08:00',
        }
        is_valid, errors, cleaned = validate_overtime_data(data, modul='ob')
        self.assertTrue(is_valid)
        self.assertEqual(cleaned['tanggal'], '2026-08-25')


class TestBuildInsertSQL(unittest.TestCase):
    """Test SQL builder for INSERT."""

    def test_build_ob_sql(self):
        """OB SQL should have correct columns."""
        sql, cols = build_insert_sql('ob')
        self.assertIn('overtime_ob_security', sql)
        self.assertIn('posisi', cols)
        self.assertIn('display_id', cols)

    def test_build_driver_sql(self):
        """Driver SQL should have correct columns.
        sheet_row is hardcoded as literal 0, so it should NOT be in cols
        (cols maps 1:1 with the params tuple)."""
        sql, cols = build_insert_sql('driver')
        self.assertIn('overtime_driver', sql)
        self.assertIn('no_kendaraan', cols)
        self.assertNotIn('sheet_row', cols)

    def test_invalid_modul_raises(self):
        """Invalid modul should raise ValueError."""
        with self.assertRaises(ValueError):
            build_insert_sql('invalid')


class TestBuildInsertParams(unittest.TestCase):
    """Test params builder for INSERT."""

    def test_ob_params_count(self):
        """OB params should match SQL placeholders."""
        sql, _ = build_insert_sql('ob')
        placeholder_count = sql.count('%s')
        cleaned = {
            'nama': 'Test', 'tanggal': '2026-08-25', 'waktu_mulai': '08:00',
            'waktu_selesai': '17:00', 'keterangan': '', 'email': '',
            'foto_mulai': '', 'foto_selesai': '',
            'posisi': 'OB',
            'gps_lat': '', 'gps_lon': '', 'gps_address': '',
            'gps_kelurahan': '', 'gps_kecamatan': '', 'gps_kota': '',
            'gps_provinsi': '', 'gps_kode_pos': '',
        }
        params = build_insert_params('OTL-001', cleaned, modul='ob')
        self.assertEqual(len(params), placeholder_count)

    def test_driver_params_count(self):
        """Driver params should match SQL placeholders."""
        sql, _ = build_insert_sql('driver')
        placeholder_count = sql.count('%s')
        cleaned = {
            'nama': 'Test', 'tanggal': '2026-08-25', 'waktu_mulai': '08:00',
            'waktu_selesai': '17:00', 'keterangan': '',
            'no_kendaraan': 'L 1234', 'broker': '', 'manager': '',
            'foto_mulai': '', 'foto_selesai': '',
            'gps_lat': '', 'gps_lon': '', 'gps_address': '',
            'gps_kelurahan': '', 'gps_kecamatan': '', 'gps_kota': '',
            'gps_provinsi': '', 'gps_kode_pos': '',
        }
        params = build_insert_params('OTD-001', cleaned, modul='driver')
        self.assertEqual(len(params), placeholder_count)


class TestHelpers(unittest.TestCase):
    """Test helper functions."""

    def test_display_prefix(self):
        """Display prefix should return correct values."""
        self.assertEqual(get_display_prefix('ob'), 'OTL')
        self.assertEqual(get_display_prefix('driver'), 'OTD')

    def test_source_uid_format(self):
        """Source UID should be consistent format."""
        uid1 = make_source_uid('OTL-001', 'Budi', 'OB')
        uid2 = make_source_uid('OTL-001', 'Budi', 'OB')
        uid3 = make_source_uid('OTL-001', 'Budi', 'Security')
        self.assertEqual(uid1, uid2)  # Same input = same UID
        self.assertNotEqual(uid1, uid3)  # Different input = different UID
        self.assertEqual(len(uid1), 24)  # Fixed length

    def test_serialize_row(self):
        """serialize_overtime_row should handle dict input."""
        row = {
            'id': 1, 'nama': 'Test', 'tanggal': '2026-08-25',
            'waktu_mulai': '08:00', 'waktu_selesai': '17:00',
            'posisi': 'OB',  # OB field present
        }
        result = serialize_overtime_row(row)
        self.assertEqual(result['modul'], 'ob')

    def test_serialize_driver_row(self):
        """serialize_overtime_row should detect driver modul."""
        row = {
            'id': 1, 'nama': 'Test', 'tanggal': '2026-08-25',
            'no_kendaraan': 'L 1234',  # Driver field present
        }
        result = serialize_overtime_row(row)
        self.assertEqual(result['modul'], 'driver')


if __name__ == '__main__':
    unittest.main()
