"""Regression v2.110.0 — image OCR wajib memakai tessdata_best.

Laporan lapangan: OCR KTP payah. Penyebabnya sebagian model bawaan
`tesseract-ocr-ind` yang berisi tessdata_fast. Image harus mengunduh model
`tessdata_best` untuk `ind` dan `eng`; tes ini mencegah regresi diam-diam.

Jalankan:
    python3 -m pytest tests/test_ktp_ocr_model.py -v
"""

import os

ROOT = os.path.join(os.path.dirname(__file__), '..')
DOCKERFILE = os.path.join(ROOT, 'Dockerfile')


def _dockerfile_text():
    with open(DOCKERFILE, encoding='utf-8') as handle:
        return handle.read()


def test_tessdata_best_untuk_ind_dan_eng():
    text = _dockerfile_text()
    assert 'tessdata_best/main/ind.traineddata' in text, (
        'Model ind tidak lagi tessdata_best — akurasi OCR KTP akan turun.')
    assert 'tessdata_best/main/eng.traineddata' in text, (
        'Model eng tidak lagi tessdata_best — akurasi OCR KTP akan turun.')


def test_modul_ocr_memakai_voting_varian():
    """Modul OCR harus membaca beberapa varian praproses (bukan satu jalur)."""
    source = open(os.path.join(ROOT, 'modules', 'ktp_ocr.py'),
                  encoding='utf-8').read()
    for token in ('sharp', 'bin', 'plain', 'VARIANT_WEIGHT'):
        assert token in source, f'{token} hilang dari modules/ktp_ocr.py'
