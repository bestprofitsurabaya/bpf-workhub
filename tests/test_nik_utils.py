"""Regresi util NIK (Rilis C — Task C1b).

NIK 16 digit: 6 digit kode wilayah + DDMMYY + 4 digit urut. Tanggal lahir
perempuan ditandai dengan DD + 40. Tahun 2 digit dipetakan dengan ambang 30
(`yy <= 30` -> 2000+yy, selain itu 1900+yy). Semua fungsi murni: tanpa DB,
Flask, dan tanpa mencetak NIK ke log.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_parse_nik_laki_laki():
    from modules.nik_utils import parse_nik
    data = parse_nik('3573010101900001')
    assert data['valid'] is True
    assert data['tanggal_lahir'] == '1990-01-01'
    assert data['jenis_kelamin'] == 'L'
    assert data['kode_wilayah'] == '357301'
    assert data['urut'] == '0001'


def test_parse_nik_perempuan_tanggal_plus_40():
    from modules.nik_utils import parse_nik
    data = parse_nik('3573014101900001')
    assert data['valid'] is True
    assert data['tanggal_lahir'] == '1990-01-01'
    assert data['jenis_kelamin'] == 'P'
    assert data['kode_wilayah'] == '357301'
    assert data['urut'] == '0001'


def test_parse_nik_tidak_valid():
    from modules.nik_utils import parse_nik
    data = parse_nik('123')
    assert data['valid'] is False
    assert data['tanggal_lahir'] is None
    assert data['jenis_kelamin'] is None
    assert data['kode_wilayah'] is None
    assert data['urut'] is None


def test_birth_date_dan_gender_dari_nik():
    from modules.nik_utils import birth_date_from_nik, gender_from_nik
    assert birth_date_from_nik('3573014101900001') == '1990-01-01'
    assert gender_from_nik('3573014101900001') == 'P'
    assert birth_date_from_nik('3573010101900001') == '1990-01-01'
    assert gender_from_nik('3573010101900001') == 'L'


def test_tanggal_mustahil_menjadi_tidak_valid():
    from modules.nik_utils import birth_date_from_nik, parse_nik
    for nik in (
            '3573019999990001',   # bulan 99
            '3573010012900001',   # bulan 00 (hari 00 juga)
            '3573013201900001',   # hari 32
            '3573013002900001',   # 30 Februari
            '3573013104900001',   # 31 April
            '3573010113900001',   # bulan 13
            '3573012902990001',   # 29 Februari 1999 (bukan kabisat)
            '3573014100900001',   # perempuan 41 -> tanggal 1 bulan 00
    ):
        assert parse_nik(nik)['valid'] is False, nik
        assert birth_date_from_nik(nik) is None, nik


def test_tanggal_kabisat_diterima():
    from modules.nik_utils import birth_date_from_nik
    assert birth_date_from_nik('3573012902000001') == '2000-02-29'
    assert birth_date_from_nik('3573012902240001') == '2024-02-29'
    assert birth_date_from_nik('3573012902290001') is None  # 2029 bukan kabisat
    assert birth_date_from_nik('3573012902990001') is None  # 1999 bukan kabisat


def test_input_bukan_digit_atau_salah_panjang():
    from modules.nik_utils import birth_date_from_nik, gender_from_nik, parse_nik
    for nik in ('', None, '35730101019000AB', '357301010190000', '35730101019000011',
                'bukan-nik', '²' * 16):
        assert parse_nik(nik)['valid'] is False, repr(nik)
        assert birth_date_from_nik(nik) is None, repr(nik)
        assert gender_from_nik(nik) is None, repr(nik)


def test_normalize_nik_membuang_spasi_dan_non_digit():
    from modules.nik_utils import normalize_nik
    assert normalize_nik(' 3573 0101 0190 0001 ') == '3573010101900001'
    assert normalize_nik('3573-0101-0190-0001') == '3573010101900001'
    assert normalize_nik('3573.0101.0190.0001') == '3573010101900001'
    assert normalize_nik('3573010101900001') == '3573010101900001'
    assert normalize_nik(None) == ''
    assert normalize_nik('') == ''
    assert normalize_nik('123') == ''
    assert normalize_nik('35730101019000AB') == ''
    assert normalize_nik('²' * 16) == ''


def test_parse_nik_menerima_nik_berformat():
    from modules.nik_utils import parse_nik
    data = parse_nik('3573 0101 0190 0001')
    assert data['valid'] is True
    assert data['tanggal_lahir'] == '1990-01-01'
    assert data['jenis_kelamin'] == 'L'


def test_ambang_tahun_dua_digit_30():
    from modules.nik_utils import birth_date_from_nik
    assert birth_date_from_nik('3573010101000001') == '2000-01-01'
    assert birth_date_from_nik('3573010101300001') == '2030-01-01'
    assert birth_date_from_nik('3573010101310001') == '1931-01-01'
    assert birth_date_from_nik('3573010101990001') == '1999-01-01'


def test_modul_murni_tanpa_flask_db_dan_tanpa_mencetak_nik(capsys):
    from modules.nik_utils import birth_date_from_nik, gender_from_nik, parse_nik
    source = (ROOT / 'modules' / 'nik_utils.py').read_text(encoding='utf-8')
    imports = [line.strip().lower() for line in source.splitlines()
               if line.strip().startswith(('import ', 'from '))]
    assert not [line for line in imports if 'flask' in line]
    assert not [line for line in imports if 'config' in line]
    assert 'get_db_connection' not in source
    assert 'logging' not in imports

    parse_nik('3573010101900001')
    parse_nik('3573019999990001')
    parse_nik('bukan-nik')
    birth_date_from_nik('3573010101900001')
    gender_from_nik('3573010101900001')
    out = capsys.readouterr()
    assert '3573010101900001' not in out.out
    assert '3573019999990001' not in out.out
    assert '3573010101900001' not in out.err
    assert '3573019999990001' not in out.err
