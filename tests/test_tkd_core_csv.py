# tests/test_tkd_core_csv.py
from pathlib import Path
import csv
import io
import json
import pytest
from modules.tkd_core import (CSV_COLUMNS, validate_question, normalize_question,
                              csv_to_question_rows, import_rows,
                              question_row_to_csv)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'docs' / 'seed' / 'tkd_bank_v1.csv'

def test_csv_seed_berisi_31_soal_dan_valid():
    rows, errors = csv_to_question_rows(SEED.read_text(encoding='utf-8'))
    assert errors == []
    assert len(rows) == 31
    assert sum(1 for r in rows if r['category'] == 'REGULASI') == 8
    assert sum(1 for r in rows if r['category'] == 'PERUSAHAAN') == 5
    assert sum(1 for r in rows if r['category'] == 'PRODUK') == 7
    assert sum(1 for r in rows if r['category'] == 'HITUNG') == 10
    assert sum(1 for r in rows if r['category'] == 'PROFIL') == 1
    assert all(r['active'] == 0 for r in rows)

def test_kunci_hitung_penting_terbaca():
    rows, _ = csv_to_question_rows(SEED.read_text(encoding='utf-8'))
    by_code = {r['code']: r for r in rows}
    assert by_code['HIT-01']['answer']['value'] == pytest.approx(1866.8)
    assert by_code['HIT-30-01']['answer']['value'] == pytest.approx(56400.3)
    assert by_code['HIT-50-01']['answer']['value'] == pytest.approx(97000.5)
    assert by_code['HIT-100-01']['answer']['value'] == pytest.approx(159501.0)

def test_validasi_soal_mcq_dan_profile():
    mcq = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
           'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
           'answer': {'option': 'a'}, 'points': 1, 'active': 0}
    assert validate_question(mcq) == []
    assert validate_question(dict(mcq, answer={'option': 'z'}))
    profile = {'code': 'P-1', 'category': 'PROFIL', 'type': 'PROFILE_TEXT',
               'prompt': 'Motivasi?', 'answer': None, 'points': 0, 'active': 0}
    assert validate_question(profile) == []

def test_import_melewati_kode_aktif_dan_hanya_update_draft():
    existing = {'A': {'id': 1, 'active': 1}, 'B': {'id': 2, 'active': 0}}
    rows = [{'code': 'A'}, {'code': 'B'}, {'code': 'C'}]
    plan = import_rows(existing, rows, update_drafts=False)
    assert plan['insert'] == ['C'] and plan['skip'] == ['A', 'B'] and plan['update'] == []

    plan = import_rows(existing, rows, update_drafts=True)
    assert plan['insert'] == ['C'] and plan['skip'] == ['A'] and plan['update'] == ['B']

def test_round_trip_baris_csv():
    row = {'code': 'REG-01', 'category': 'REGULASI', 'type': 'MCQ',
           'prompt': 'Pertanyaan, dengan koma', 'options': [{'id': 'a', 'text': 'A'}],
           'answer': {'option': 'a'}, 'points': 1, 'modal_tier': None,
           'active': 1, 'sort_order': 1}
    values = question_row_to_csv(row)
    assert len(values) == len(CSV_COLUMNS)
    assert values[CSV_COLUMNS.index('prompt')] == 'Pertanyaan, dengan koma'


# --- Cakupan tambahan untuk aturan validasi dan bentuk data -----------------

def test_validasi_menolak_opsi_dan_kunci_kosong():
    base = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer': {'option': 'a'}, 'points': 1, 'active': 0}
    assert validate_question(dict(base, options=[
        {'id': 'a', 'text': '   '}, {'id': 'b', 'text': 'B'}]))
    assert validate_question(dict(base, options=[
        {'id': '  ', 'text': 'A'}, {'id': 'b', 'text': 'B'}]))
    assert validate_question(dict(base, answer={'option': '   '}))
    assert validate_question(dict(base, answer={'option': ''}))
    assert validate_question(dict(base, answer={}))

def test_validasi_numeric_short_text_dan_profile():
    numeric = {'code': 'HIT-1', 'category': 'HITUNG', 'type': 'NUMERIC',
               'prompt': 'Hitung', 'answer': {'value': 60, 'tolerance': 0.5},
               'points': 1, 'modal_tier': '30k', 'active': 0}
    assert validate_question(numeric) == []
    assert validate_question(dict(numeric, answer={'value': 'abc'}))
    assert validate_question(dict(numeric, answer={'value': 60, 'tolerance': -1}))
    assert validate_question(dict(numeric, modal_tier='30k', category='PRODUK'))

    short = {'code': 'REG-05', 'category': 'REGULASI', 'type': 'SHORT_TEXT',
             'prompt': 'Izin?', 'answer': {'aliases': ['499/BAPPEBTI/SI/X/2004']},
             'points': 1, 'active': 0}
    assert validate_question(short) == []
    assert validate_question(dict(short, answer={'aliases': ['  ']}))

    profile = {'code': 'P-1', 'category': 'PROFIL', 'type': 'PROFILE_TEXT',
               'prompt': 'Motivasi?', 'answer': None, 'points': 0}
    assert validate_question(dict(profile, points=1))
    assert validate_question(dict(profile, category='PRODUK'))
    assert validate_question(dict(profile, answer={'text': 'jawaban'}))

def test_normalize_question_menghasilkan_json_string():
    data = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer': {'option': 'a'}, 'points': 1}
    row = normalize_question(data)
    assert validate_question(dict(row, options=json.loads(row['options']),
                                  answer=json.loads(row['answer']))) == []
    assert json.loads(row['options'])[0]['text'] == 'A'
    assert json.loads(row['answer']) == {'option': 'a'}
    assert row['active'] == 0 and row['modal_tier'] in (None, '')

def test_csv_error_menyebut_nomor_baris():
    header = ','.join(CSV_COLUMNS)
    bad = 'BAD-1,PRODUK,MCQ,P,a,A,, ,z,,1,,,0'
    rows, errors = csv_to_question_rows(header + '\n' + bad + '\n')
    assert rows == []
    assert errors and all(e.startswith('baris 2') for e in errors)

def test_round_trip_numeric_dan_short_text_memakai_get():
    numeric = {'code': 'HIT-01', 'category': 'HITUNG', 'type': 'NUMERIC',
               'prompt': 'Hitung', 'answer': {'value': 1866.8, 'tolerance': 0.5},
               'points': 1, 'modal_tier': '', 'active': 0}
    values = question_row_to_csv(numeric)
    assert values[CSV_COLUMNS.index('correct')] == '1866.8'
    assert values[CSV_COLUMNS.index('tolerance')] == '0.5'

    short = {'code': 'REG-05', 'category': 'REGULASI', 'type': 'SHORT_TEXT',
             'prompt': 'Izin?', 'answer': {'aliases': ['499/BAPPEBTI/SI/X/2004', '499 SI']},
             'points': 1, 'active': 0}
    values = question_row_to_csv(short)
    assert values[CSV_COLUMNS.index('correct')] == '499/BAPPEBTI/SI/X/2004|499 SI'

    assert len(question_row_to_csv({})) == len(CSV_COLUMNS)

def test_validasi_menolak_enam_opsi_mcq():
    options = [{'id': option_id, 'text': f'Opsi {option_id.upper()}'}
               for option_id in 'abcdef']
    question = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ', 'prompt': 'P',
                'options': options, 'answer': {'option': 'e'},
                'points': 1, 'active': 0}
    errors = validate_question(question)
    assert errors
    assert any('2–5' in error or 'a–e' in error for error in errors)

def test_round_trip_mcq_mempertahankan_semua_opsi_dan_kunci():
    options = [{'id': option_id, 'text': f'Teks opsi {option_id.upper()}'}
               for option_id in 'abcde']
    question = {'code': 'X-1', 'category': 'PRODUK', 'type': 'MCQ',
                'prompt': 'Pilih satu', 'options': options,
                'answer': {'option': 'c'}, 'points': 1, 'modal_tier': None,
                'active': 1, 'sort_order': 1}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(question_row_to_csv(question))

    rows, errors = csv_to_question_rows(buffer.getvalue())
    assert errors == [] and len(rows) == 1
    assert rows[0]['options'] == options
    assert rows[0]['answer'] == {'option': 'c'}
