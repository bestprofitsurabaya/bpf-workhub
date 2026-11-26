"""Util NIK (Rilis C) — tanggal lahir dan jenis kelamin dari 16 digit NIK.

NIK Indonesia: 6 digit kode wilayah + DDMMYY + 4 digit nomor urut. Tanggal
lahir perempuan ditandai dengan DD + 40 (mis. 41 = tanggal 1 dan seterusnya).
Tahun 2 digit dipetakan dengan ambang 30: `yy <= 30` -> 2000+yy, selain itu
1900+yy.

Modul ini murni: tidak menyentuh DB maupun Flask, dan tidak pernah mencetak
NIK ke log. Pemanggil yang butuh tanggal lahir (CV Online, FirstWork, detail
rekrutmen) cukup memakai `birth_date_from_nik` / `gender_from_nik`.
"""
from datetime import date

AMBANG_TAHUN = 30
SELISIH_HARI_PEREMPUAN = 40


def normalize_nik(value):
    """Ambil 16 digit dari input apa pun; '' bila jumlah digit bukan 16.

    Spasi dan pemisah lain dibuang sehingga NIK berformat
    '3573 0101 0190 0001' tetap diterima. Digit non-ASCII (mis. '²') dan
    notasi ilmiah spreadsheet tidak lolos karena hasilnya bukan 16 digit.
    """
    if value is None:
        return ''
    digits = ''.join(
        ch for ch in str(value) if ch.isascii() and ch.isdigit())
    return digits if len(digits) == 16 else ''


def _tidak_valid():
    """Hasil seragam untuk NIK yang tidak dapat diurai."""
    return {
        'valid': False,
        'tanggal_lahir': None,
        'jenis_kelamin': None,
        'kode_wilayah': None,
        'urut': None,
    }


def parse_nik(nik):
    """Urai NIK menjadi dict; input apa pun tidak pernah melempar error.

    Return `{valid, tanggal_lahir, jenis_kelamin, kode_wilayah, urut}` dengan
    `tanggal_lahir` berformat 'YYYY-MM-DD' dan `jenis_kelamin` 'L'/'P'.
    Tanggal mustahil (bulan 00/13+, hari 00/32+, 30 Februari, dst.) membuat
    seluruh field bernilai None dan `valid=False`.
    """
    digits = normalize_nik(nik)
    if not digits:
        return _tidak_valid()

    kode_wilayah = digits[:6]
    urut = digits[12:]
    hari = int(digits[6:8])
    bulan = int(digits[8:10])
    tahun_2digit = int(digits[10:12])

    jenis_kelamin = 'P' if hari > SELISIH_HARI_PEREMPUAN else 'L'
    if jenis_kelamin == 'P':
        hari -= SELISIH_HARI_PEREMPUAN
    tahun = (2000 + tahun_2digit if tahun_2digit <= AMBANG_TAHUN
             else 1900 + tahun_2digit)

    try:
        tanggal_lahir = date(tahun, bulan, hari).isoformat()
    except ValueError:
        return _tidak_valid()

    return {
        'valid': True,
        'tanggal_lahir': tanggal_lahir,
        'jenis_kelamin': jenis_kelamin,
        'kode_wilayah': kode_wilayah,
        'urut': urut,
    }


def birth_date_from_nik(nik):
    """Tanggal lahir 'YYYY-MM-DD' dari NIK, atau None bila NIK tidak valid."""
    return parse_nik(nik)['tanggal_lahir']


def gender_from_nik(nik):
    """Jenis kelamin 'L'/'P' dari NIK, atau None bila NIK tidak valid."""
    return parse_nik(nik)['jenis_kelamin']
