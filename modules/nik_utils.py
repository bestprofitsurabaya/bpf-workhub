"""Util NIK (Rilis C) — tanggal lahir dan jenis kelamin dari 16 digit NIK.

NIK Indonesia: 6 digit kode wilayah + DDMMYY + 4 digit nomor urut. Tanggal
lahir perempuan ditandai dengan DD + 40 (mis. 41 = tanggal 1 dan seterusnya).
Pivot abad mengikuti tahun berjalan, sama seperti `tkd_core.derive_dob_from_nik`:
`yy > (tahun berjalan % 100)` -> 1900+yy, selain itu 2000+yy.

Modul ini murni: tidak menyentuh DB maupun Flask, dan tidak pernah mencetak
NIK ke log. Pemanggil yang butuh tanggal lahir (CV Online, FirstWork, detail
rekrutmen) cukup memakai `birth_date_from_nik` / `gender_from_nik`.
"""
from datetime import date

from modules.helpers import normalize_nik as _normalize_nik

SELISIH_HARI_PEREMPUAN = 40


def normalize_nik(value):
    """Ambil 16 digit dari input; '' bila tidak valid.

    Memakai satu parser bersama dengan FirstWork dan CV Online, sehingga
    notasi ilmiah/koma dari spreadsheet tetap ditolak.
    """
    return _normalize_nik(value)[0]


def _tidak_valid():
    """Hasil seragam untuk NIK yang tidak dapat diurai."""
    return {
        'valid': False,
        'tanggal_lahir': None,
        'jenis_kelamin': None,
        'kode_wilayah': None,
        'urut': None,
    }


def parse_nik(nik, today=None):
    """Urai NIK menjadi dict; input apa pun tidak pernah melempar error.

    Return `{valid, tanggal_lahir, jenis_kelamin, kode_wilayah, urut}` dengan
    `tanggal_lahir` berformat 'YYYY-MM-DD' dan `jenis_kelamin` 'L'/'P'.
    Tanggal mustahil (bulan 00/13+, hari 00/32+, 30 Februari, dst.) membuat
    seluruh field bernilai None dan `valid=False`. `today` opsional hanya
    untuk tes deterministik.
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
    tahun_pivot = (today or date.today()).year % 100
    tahun = (1900 + tahun_2digit if tahun_2digit > tahun_pivot
             else 2000 + tahun_2digit)

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


def birth_date_from_nik(nik, today=None):
    """Tanggal lahir 'YYYY-MM-DD' dari NIK, atau None bila NIK tidak valid."""
    return parse_nik(nik, today=today)['tanggal_lahir']


def gender_from_nik(nik):
    """Jenis kelamin 'L'/'P' dari NIK, atau None bila NIK tidak valid."""
    return parse_nik(nik)['jenis_kelamin']
