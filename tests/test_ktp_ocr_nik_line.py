"""Regression v2.111.1 — label NIK tidak boleh merusak digit.

Dua bug yang pernah membuat NIK salah 1–3 digit:

1. Label `NIK` ikut melewati peta kekeliruan karakter (`I`→`1`), sehingga
   baris `NIK : 3379 6327 4393 5797` menjadi 17 digit dan NIK yang benar
   tidak pernah menjadi kandidat.
2. Pipeline berhenti setelah varian praproses pertama; baris NIK yang
   disetujui beberapa varian tidak sempat dibandingkan.

Jalankan:
    python3 -m pytest tests/test_ktp_ocr_nik_line.py -v
"""

import importlib.util
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')
SPEC = importlib.util.spec_from_file_location(
    'ktp_ocr_regression', os.path.join(ROOT, 'modules', 'ktp_ocr.py'))
OCR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OCR)


def test_label_nik_tidak_menjadi_digit():
    text = 'NIK : 3379 6327 4393 5797'
    assert OCR._digits_only(text, strip_labels=True) == '3379632743935797'


def test_baris_nik_berlabel_menjadi_kandidat():
    candidates = OCR._nik_candidates(
        [{'text': 'NIK : 3379 6327 4393 5797', 'conf': 91}], variant='sharp')
    assert any(c['nik'] == '3379632743935797' and c['labelled']
               for c in candidates), 'Baris NIK yang benar tidak masuk kandidat'


def test_baris_tiga_varian_mengalahkan_token_satu_varian():
    candidates = [
        {'nik': '3532652651956486', 'conf': 80,
         'labelled': True, 'variant': 'gray'},
        {'nik': '3532652651956486', 'conf': 82,
         'labelled': True, 'variant': 'bin'},
        {'nik': '3532652651956486', 'conf': 78,
         'labelled': True, 'variant': 'plain'},
        {'nik': '3532652051956480', 'conf': 96,
         'roi': True, 'token': True, 'variant': 'sharp'},
    ]
    picked = OCR._pick_nik_best(candidates)
    assert picked['nik'] == '3532652651956486', (
        'Baris yang disetujui tiga varian harus mengalahkan crop token.')


def test_dua_varian_belum_cukup_mengalahkan_token():
    """KTP nyata: gray+plain sama-sama salah nomor seri, token benar."""
    candidates = [
        {'nik': '3509190102960000', 'conf': 48,
         'labelled': True, 'variant': 'gray'},
        {'nik': '3509190102960000', 'conf': 48,
         'labelled': True, 'variant': 'plain'},
        {'nik': '3509190102950003', 'conf': 70,
         'roi': True, 'token': True, 'variant': 'sharp'},
    ]
    picked = OCR._pick_nik_best(candidates)
    assert picked['nik'] == '3509190102950003', (
        'Dua varian bersaudara tidak boleh membajak token yang lebih kuat.')
