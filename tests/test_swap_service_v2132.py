"""v2.132.0 — logika murni pengajuan ganti kendaraan."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from modules.assignment_swap_service import (
    SwapError, clean_reason, validate_category, normalize_swap_type,
    validate_odometer, request_code, handover_complete, handover_side,
    received_nopol, build_approve_plan, supersede_conflicts,
)


def exchange_req(**over):
    req = {
        'id': 7, 'swap_type': 'exchange', 'status': 'pending',
        'requester_driver': 'A', 'requester_nopol': 'X',
        'target_driver': 'B', 'target_nopol': 'Y',
        'reason': 'tukar',
        'requester_handover_at': None, 'target_handover_at': None,
    }
    req.update(over)
    return req


def move_req(**over):
    req = {
        'id': 8, 'swap_type': 'move', 'status': 'pending',
        'requester_driver': 'A', 'requester_nopol': 'X',
        'target_driver': None, 'target_nopol': 'Z',
        'reason': 'tukar',
        'requester_handover_at': None, 'target_handover_at': None,
    }
    req.update(over)
    return req


def assignment(aid, driver, nopol, vtype='AVANZA', bbm='PERTALITE'):
    return {'id': aid, 'driver_name': driver, 'nopol': nopol,
            'vehicle_type': vtype, 'bbm_type': bbm}


class TestValidation:
    def test_alasan_batas(self):
        assert clean_reason('  1234567890  ') == '1234567890'
        with pytest.raises(SwapError) as e:
            clean_reason('123456789')
        assert e.value.code == 'reason'
        with pytest.raises(SwapError):
            clean_reason('x' * 501)

    def test_kategori_dan_jenis(self):
        assert validate_category(' MUTASI ') == 'mutasi'
        with pytest.raises(SwapError):
            validate_category('nuklir')
        assert normalize_swap_type('') == 'exchange'
        assert normalize_swap_type('MOVE') == 'move'
        with pytest.raises(SwapError):
            normalize_swap_type('jual')

    def test_odometer_batas(self):
        assert validate_odometer('0') == 0
        assert validate_odometer('2000000') == 2_000_000
        for bad in ('-1', '2000001', '', 'abc', None):
            with pytest.raises(SwapError):
                validate_odometer(bad)

    def test_request_code(self):
        assert request_code(7, date(2026, 11, 23)) == 'SWR-20261123-0007'
        assert request_code(12345, date(2026, 1, 2)) == 'SWR-20260102-12345'


class TestHandover:
    def test_exchange_butuh_dua_sisi(self):
        assert handover_complete('exchange', 't', None) is False
        assert handover_complete('exchange', 't', 't') is True

    def test_move_cukup_pengaju(self):
        assert handover_complete('move', 't', None) is True
        assert handover_complete('move', None, None) is False

    def test_side_dan_nopol_diterima(self):
        req = exchange_req()
        assert handover_side(req, 'A') == 'requester'
        assert handover_side(req, 'B') == 'target'
        assert handover_side(req, 'C') is None
        assert received_nopol(req, 'requester') == 'Y'
        assert received_nopol(req, 'target') == 'X'

    def test_move_tidak_punya_sisi_target(self):
        req = move_req()
        assert handover_side(req, 'A') == 'requester'
        assert handover_side(req, 'B') is None


class TestApprovePlanExchange:
    def test_rencana_tukar_dua_arah(self):
        plan = build_approve_plan(
            exchange_req(),
            [assignment(1, 'A', 'X'), assignment(2, 'B', 'Y')])
        assert sorted(plan['close_ids']) == [1, 2]
        assert plan['new_assignments'] == [
            {'driver_name': 'A', 'nopol': 'Y', 'vehicle_type': 'AVANZA',
             'bbm_type': 'PERTALITE', 'driver_notes': 'tukar'},
            {'driver_name': 'B', 'nopol': 'X', 'vehicle_type': 'AVANZA',
             'bbm_type': 'PERTALITE', 'driver_notes': 'tukar'},
        ]
        assert plan['driver_updates'] == [
            {'name': 'A', 'nopol': 'Y', 'vehicle_type': 'AVANZA',
             'bbm_type': 'PERTALITE'},
            {'name': 'B', 'nopol': 'X', 'vehicle_type': 'AVANZA',
             'bbm_type': 'PERTALITE'},
        ]
        assert plan['swap_logs'] == [
            {'nopol': 'X', 'old_driver': 'A', 'new_driver': 'B'},
            {'nopol': 'Y', 'old_driver': 'B', 'new_driver': 'A'},
        ]

    def test_assignment_berubah_ditolak(self):
        with pytest.raises(SwapError) as e:
            build_approve_plan(
                exchange_req(),
                [assignment(1, 'A', 'X'), assignment(2, 'B', 'Z')])
        assert e.value.http_status == 409
        assert e.value.code == 'state_changed'

    def test_nopol_ganda_ditolak(self):
        with pytest.raises(SwapError):
            build_approve_plan(
                exchange_req(),
                [assignment(1, 'A', 'X'), assignment(2, 'B', 'Y'),
                 assignment(3, 'C', 'X')])

    def test_kendaraan_tidak_milik_driver_ditolak(self):
        with pytest.raises(SwapError):
            build_approve_plan(
                exchange_req(),
                [assignment(1, 'C', 'X'), assignment(2, 'B', 'Y')])


class TestApprovePlanMove:
    def test_rencana_pindah_ke_kosong(self):
        plan = build_approve_plan(
            move_req(),
            [assignment(1, 'A', 'X')],
            vehicle={'nopol': 'Z', 'vehicle_type': 'INNOVA',
                     'bbm_default': 'PERTAMAX', 'is_active': 1})
        assert plan['close_ids'] == [1]
        assert plan['new_assignments'] == [
            {'driver_name': 'A', 'nopol': 'Z', 'vehicle_type': 'INNOVA',
             'bbm_type': 'PERTAMAX', 'driver_notes': 'tukar'},
        ]
        assert plan['driver_updates'] == [
            {'name': 'A', 'nopol': 'Z', 'vehicle_type': 'INNOVA',
             'bbm_type': 'PERTAMAX'},
        ]
        assert plan['swap_logs'] == [
            {'nopol': 'X', 'old_driver': 'A', 'new_driver': '- (Pool)'},
            {'nopol': 'Z', 'old_driver': '- (Pool)', 'new_driver': 'A'},
        ]

    def test_pindah_ke_kendaraan_terisi_ditolak(self):
        with pytest.raises(SwapError) as e:
            build_approve_plan(
                move_req(),
                [assignment(1, 'A', 'X'), assignment(2, 'B', 'Z')],
                vehicle={'nopol': 'Z', 'vehicle_type': 'AVANZA',
                         'bbm_default': 'PERTALITE', 'is_active': 1})
        assert e.value.code == 'state_changed'

    def test_pindah_tanpa_data_kendaraan_ditolak(self):
        with pytest.raises(SwapError):
            build_approve_plan(move_req(), [assignment(1, 'A', 'X')], vehicle=None)


class TestConflicts:
    def test_hanya_pengajuan_lain_yang_belum_lengkap(self):
        req = exchange_req(id=9)
        rows = [
            exchange_req(id=1),
            exchange_req(id=2, requester_handover_at='t', target_handover_at='t'),
            exchange_req(id=9),
        ]
        assert supersede_conflicts(rows, req) == [1]
