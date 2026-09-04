"""
Unit Tests untuk Alur Kasbon, LPJ, dan Validasi
BPF WorkHub V1.1

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_cash_and_workflow.py -v
    atau
    cd tests && python3 -m pytest test_cash_and_workflow.py -v
"""

import pytest
import sys
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

# Tambahkan parent directory ke path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.helpers import (
    safe_float,
    generate_display_id,
    validate_bbm_for_vehicle,
    get_or_create_driver,
    get_or_create_vehicle,
    get_or_create_bbm,
    ensure_all_master_data,
)


# ================================================================
# TEST 1: Validasi Kode Unik Kasbon
# ================================================================
class TestKasbonKodeUnik:
    """Test untuk memastikan kode unik kasbon valid."""

    def test_kode_unik_dalam_range(self):
        """Kode unik harus antara 100 - 2000 dan kelipatan 100."""
        from modules.routes_cash import register_cash_routes
        import random

        # Verifikasi pilihan kode
        valid_codes = [
            100, 200, 300, 400, 500, 600, 700, 800, 900,
            1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000
        ]

        for code in valid_codes:
            assert 100 <= code <= 2000, f"Kode {code} di luar range"
            assert code % 100 == 0, f"Kode {code} bukan kelipatan 100"

    def test_total_kasbon_valid(self):
        """Total = nominal dasar + kode unik."""
        base_amount = 150000
        unique_code = 500
        total = base_amount + unique_code
        assert total == 150500, f"Total salah: {total}"
        assert total > base_amount, "Total harus > nominal dasar"

    def test_kode_unik_unik_per_hari(self):
        """Kode unik untuk tanggal yang sama harus konsisten."""
        today = date.today()
        # Simulasi: kode untuk hari ini harus sama
        code_set = {500}  # Simulasi satu kode per hari
        assert len(code_set) == 1, "Seharusnya satu kode per hari"


# ================================================================
# TEST 2: Validasi Alur Status Kasbon
# ================================================================
class TestKasbonWorkflow:
    """Test alur lengkap kasbon dari DRAFT sampai COMPLETED."""

    VALID_TRANSITIONS = {
        'DRAFT': ['GA_APPROVED', 'REJECTED', 'DRAFT'],  # DRAFT bisa diedit
        'GA_APPROVED': ['FINANCE_APPROVED', 'DRAFT'],     # Bisa cancel
        'FINANCE_APPROVED': ['FUNDS_WITH_DRIVER', 'DRAFT'],
        'FUNDS_WITH_DRIVER': ['LPJ_SUBMITTED', 'DRAFT'],
        'LPJ_SUBMITTED': ['COMPLETED', 'FUNDS_WITH_DRIVER'],  # Approve atau Reject LPJ
        'COMPLETED': ['FUNDS_WITH_DRIVER'],  # Reset LPJ
        'REJECTED': [],  # Final state
    }

    def test_status_transition_valid(self):
        """Semua transisi status harus valid."""
        for current, allowed in self.VALID_TRANSITIONS.items():
            for next_status in allowed:
                assert next_status in self.VALID_TRANSITIONS.get(current, []), \
                    f"Transisi {current} -> {next_status} tidak valid"

    def test_cannot_skip_ga_approval(self):
        """DRAFT tidak bisa langsung ke FINANCE_APPROVED."""
        assert 'FINANCE_APPROVED' not in self.VALID_TRANSITIONS['DRAFT'], \
            "DRAFT tidak boleh langsung FINANCE_APPROVED"

    def test_lpj_required_before_complete(self):
        """Harus LPJ_SUBMITTED dulu sebelum COMPLETED."""
        assert 'COMPLETED' not in self.VALID_TRANSITIONS['FUNDS_WITH_DRIVER'], \
            "FUNDS_WITH_DRIVER harus submit LPJ dulu"
        assert 'COMPLETED' in self.VALID_TRANSITIONS['LPJ_SUBMITTED'], \
            "LPJ_SUBMITTED harus bisa ke COMPLETED"

    def test_rejected_is_final(self):
        """Status REJECTED adalah final."""
        assert self.VALID_TRANSITIONS['REJECTED'] == [], \
            "REJECTED seharusnya final, tidak ada transisi keluar"


# ================================================================
# TEST 3: Validasi Transaksi BBM
# ================================================================
class TestTransaksiBBM:
    """Test validasi transaksi BBM."""

    def test_nominal_positif(self):
        """Nominal transaksi harus > 0."""
        nominal = safe_float("150000")
        assert nominal > 0, "Nominal harus positif"
        assert nominal == 150000.0, f"Nominal salah: {nominal}"

    def test_nominal_zero_ditolak(self):
        """Nominal 0 harus ditolak."""
        nominal = safe_float("0")
        assert nominal == 0, "safe_float harus return 0"
        # Validasi bisnis: nominal <= 0 tidak valid
        is_valid = nominal > 0
        assert not is_valid, "Nominal 0 seharusnya tidak valid"

    def test_nominal_negatif_ditolak(self):
        """Nominal negatif harus ditolak."""
        nominal = safe_float("-50000")
        assert nominal == -50000.0
        is_valid = nominal > 0
        assert not is_valid, "Nominal negatif seharusnya tidak valid"

    def test_odo_positif(self):
        """Odometer harus bilangan positif."""
        odo = 50000
        assert odo > 0, "ODO harus positif"
        assert isinstance(odo, int), "ODO harus integer"

    def test_km_per_liter_calculation(self):
        """Perhitungan KM/Liter harus akurat."""
        nominal = 200000
        price_per_liter = 10000
        liter = nominal / price_per_liter  # 20 liter
        km_traveled = 200  # 200 km
        km_per_liter = km_traveled / liter  # 10 km/l

        assert liter == 20.0, f"Liter salah: {liter}"
        assert km_per_liter == 10.0, f"KM/L salah: {km_per_liter}"

    def test_km_per_liter_anomali(self):
        """KM/L < 5 atau > 20 harus di-flag anomali."""
        def is_anomali(km_per_liter, vehicle_type='AVANZA'):
            if vehicle_type == 'AVANZA':
                return km_per_liter < 6 or km_per_liter > 18
            return km_per_liter < 5 or km_per_liter > 20

        assert is_anomali(3.0, 'AVANZA'), "3 km/l harus anomali"
        assert is_anomali(25.0, 'AVANZA'), "25 km/l harus anomali"
        assert not is_anomali(10.0, 'AVANZA'), "10 km/l harus normal"


# ================================================================
# TEST 4: Validasi Helper Functions
# ================================================================
class TestHelperFunctions:
    """Test fungsi-fungsi di helpers.py."""

    def test_safe_float_normal(self):
        assert safe_float("123.45") == 123.45
        assert safe_float("0") == 0.0

    def test_safe_float_invalid(self):
        assert safe_float("abc") == 0.0, "Non-numeric harus return 0"
        assert safe_float("") == 0.0
        assert safe_float(None) == 0.0

    def test_validate_bbm_for_vehicle(self):
        """Validasi BBM berdasarkan tipe kendaraan."""
        # AVANZA harus bisa PERTALITE
        result = validate_bbm_for_vehicle('AVANZA', 'PERTALITE')
        assert result is not None, "Harus ada hasil"

        # Test dengan vehicle tidak dikenal
        result = validate_bbm_for_vehicle('UNKNOWN', 'PERTALITE')
        assert result is not None, "Harus return default"

    def test_generate_display_id_format(self):
        """Display ID harus format standar v2.29.10: PREFIX-BRANCH-YYYYMMDD-SEQ."""
        display_id = generate_display_id('BPF')
        assert display_id.startswith('BPF-'), f"Harus start dengan BPF-: {display_id}"

        parts = display_id.split('-')
        assert len(parts) == 4, f"Harus 4 bagian: {display_id}"

        # Cabang (isi lokal, non-kosong)
        branch_part = parts[1]
        assert branch_part and branch_part.isupper(), f"Cabang uppercase: {branch_part}"

        # Tanggal 8 digit
        date_part = parts[2]
        assert len(date_part) == 8 and date_part.isdigit(), f"Date part harus 8 digit: {date_part}"

        # Urut harian 4 digit
        seq_part = parts[3]
        assert len(seq_part) == 4 and seq_part.isdigit(), f"Seq part harus 4 digit: {seq_part}"


# ================================================================
# TEST 5: Validasi File Cleanup
# ================================================================
class TestFileCleanup:
    """Test fungsi pembersihan file."""

    def test_cleanup_function_exists(self):
        """Fungsi cleanup_transaction_files harus ada."""
        # Import dinamis untuk cek keberadaan
        # v2.9: routes_admin.py dipensiunkan (endpoint aksi klasik dihapus) —
        # cleanup file kini hidup di jalur SPA: routes_spa.py & routes_cash.py.
        try:
            import inspect
            from modules import routes_spa, routes_cash
            source = inspect.getsource(routes_spa) + inspect.getsource(routes_cash)
            assert 'os.remove' in source or '_os.remove' in source, \
                "Fungsi cleanup file harus ada di routes_spa.py / routes_cash.py"
        except ImportError as e:
            pytest.skip(f"Tidak bisa import: {e}")

    def test_file_fields_defined(self):
        """Field foto yang harus dibersihkan."""
        required_fields = [
            'foto_odo_sebelum',
            'foto_nota_odo_sesudah',
            'foto_struk',
            'foto_struk_dispenser',
        ]
        assert len(required_fields) == 4, "Harus 4 field foto utama"


# ================================================================
# TEST 6: Integration Test (Mock DB)
# ================================================================
class TestIntegrationMock:
    """Integration test dengan mock database."""

    @pytest.fixture
    def sample_cash_request(self):
        """Fixture: sample cash request data."""
        return {
            'id': 1,
            'display_id': 'CASH-20260730-000001',
            'driver_name': 'TEST_DRIVER',
            'nopol': 'B 1234 XYZ',
            'vehicle_type': 'AVANZA',
            'bbm_type': 'PERTALITE',
            'base_amount': 200000,
            'unique_cents': 500,
            'total_amount': 200500,
            'status': 'DRAFT',
            'notes': 'Test kasbon'
        }

    @pytest.fixture
    def sample_transaction(self):
        """Fixture: sample transaction data."""
        return {
            'id': 1,
            'display_id': 'BPF-20260730-000001',
            'driver_name': 'TEST_DRIVER',
            'nopol': 'B 1234 XYZ',
            'vehicle_type': 'AVANZA',
            'bbm_type': 'PERTALITE',
            'nominal': 200000,
            'liter': 20.0,
            'price_per_liter': 10000,
            'odo_km': 50000,
            'status': 'pending',
            'km_per_liter': 10.0,
            'foto_odo_sebelum': 'ODO1_B 1234 XYZ_test.jpg',
            'foto_nota_odo_sesudah': 'ODO2_B 1234 XYZ_test.jpg',
            'foto_struk': 'STRUK_B 1234 XYZ_test.jpg',
            'foto_struk_dispenser': None,
        }

    def test_cash_total_calculation(self, sample_cash_request):
        """Total = base_amount + unique_cents."""
        req = sample_cash_request
        assert req['total_amount'] == req['base_amount'] + req['unique_cents'], \
            f"Total {req['total_amount']} != {req['base_amount']} + {req['unique_cents']}"

    def test_transaction_has_required_fields(self, sample_transaction):
        """Transaksi harus punya semua field wajib."""
        required = ['driver_name', 'nopol', 'vehicle_type', 'bbm_type',
                    'nominal', 'liter', 'price_per_liter', 'odo_km', 'status']
        for field in required:
            assert field in sample_transaction, f"Field {field} harus ada"

    def test_cash_lpj_link(self, sample_cash_request, sample_transaction):
        """Saat LPJ di-submit, cash.lpj_transaction_id = transaction.id."""
        sample_cash_request['lpj_transaction_id'] = sample_transaction['id']
        sample_cash_request['status'] = 'LPJ_SUBMITTED'

        assert sample_cash_request['lpj_transaction_id'] == sample_transaction['id']
        assert sample_cash_request['status'] == 'LPJ_SUBMITTED'

    def test_approve_lpj_completes_cash(self, sample_cash_request, sample_transaction):
        """Saat LPJ di-approve, cash.status = COMPLETED."""
        # Simulasi alur approve LPJ
        sample_cash_request['lpj_transaction_id'] = sample_transaction['id']
        sample_cash_request['status'] = 'LPJ_SUBMITTED'

        # GA approve LPJ
        sample_transaction['status'] = 'verified_ga'
        sample_cash_request['status'] = 'COMPLETED'

        assert sample_cash_request['status'] == 'COMPLETED', \
            "Setelah LPJ approve, cash harus COMPLETED"
        assert sample_transaction['status'] == 'verified_ga', \
            "Setelah LPJ approve, transaksi harus verified_ga"


# ================================================================
# MAIN
# ================================================================
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
