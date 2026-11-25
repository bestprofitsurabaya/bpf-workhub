# tests/test_tkd_core_grading.py
from datetime import date
import pytest
from modules.tkd_core import (derive_dob_from_nik, parse_numeric,
                              normalize_short_text, grade_answer, compute_score)

def test_tanggal_lahir_dari_nik_laki_laki():
    assert derive_dob_from_nik('3573010101990001') == date(1999, 1, 1)

def test_tanggal_lahir_dari_nik_perempuan_dan_pivot_abad():
    assert derive_dob_from_nik('3573014101990001') == date(1999, 1, 1)
    assert derive_dob_from_nik('3573010101270001', today=date(2026, 11, 24)) == date(1927, 1, 1)
    assert derive_dob_from_nik('3573010101260001', today=date(2026, 11, 24)) == date(2026, 1, 1)

@pytest.mark.parametrize('nik', ['', '123', '357301010199000X', '3573013201990001', '3573010113990001'])
def test_tanggal_lahir_tidak_valid_mengembalikan_none(nik):
    assert derive_dob_from_nik(nik) is None

@pytest.mark.parametrize('raw,expected', [
    ('1.866,8', 1866.8), ('$1866,8', 1866.8), ('1866.8', 1866.8),
    (' 1 866,8 ', 1866.8), ('159.501', 159501.0), (60, 60.0),
])
def test_parse_numeric_menerima_format_indonesia(raw, expected):
    assert parse_numeric(raw) == pytest.approx(expected)

@pytest.mark.parametrize('raw', ['', 'abc', '1,2,3', None, float('nan')])
def test_parse_numeric_menolak_sampah(raw):
    assert parse_numeric(raw) is None

def test_normalize_short_text_mengabaikan_huruf_besar_dan_tanda_baca():
    assert normalize_short_text(' 499/BAPPEBTI/SI/X/2004 ') == normalize_short_text('499 bappebti si x 2004')

def test_mcq_dinilai_dari_kunci_snapshot():
    q = {'type': 'MCQ', 'answer': {'option': 'b'}, 'points': 1}
    assert grade_answer(q, {'option': 'b'}) == (True, 1.0)
    assert grade_answer(q, {'option': 'a'}) == (False, 0.0)

def test_numeric_memakai_toleransi():
    q = {'type': 'NUMERIC', 'answer': {'value': 1866.8, 'tolerance': 0.5}, 'points': 1}
    assert grade_answer(q, 1866.4) == (True, 1.0)
    assert grade_answer(q, 1867.5) == (False, 0.0)

def test_short_text_menerima_alias():
    q = {'type': 'SHORT_TEXT', 'answer': {'aliases': ['499/BAPPEBTI/SI/X/2004']}, 'points': 1}
    assert grade_answer(q, {'text': '499 Bappebti SI X 2004'}) == (True, 1.0)

def test_profile_tidak_dinilai():
    q = {'type': 'PROFILE_TEXT', 'answer': None, 'points': 0}
    assert grade_answer(q, {'text': 'apa saja'}) == (None, 0.0)

def test_skor_14_dari_20_lulus_70():
    items = [{'is_correct': True, 'points_awarded': 1, 'points': 1}] * 14
    items += [{'is_correct': False, 'points_awarded': 0, 'points': 1}] * 6
    assert compute_score(items, 70) == {
        'score': 70.0, 'total_points': 20.0, 'awarded': 14.0,
        'correct_count': 14, 'passed': True}

def test_nik_non_ascii_ditolak_tanpa_exception():
    assert derive_dob_from_nik('²' * 16) is None

def test_mcq_kunci_kosong_tidak_dianggap_benar():
    q = {'type': 'MCQ', 'answer': {'option': ''}, 'points': 1}
    assert grade_answer(q, {'option': ''}) == (False, 0.0)
