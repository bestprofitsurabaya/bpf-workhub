"""Registrasi CV Online (v2.113.0).

Yang diuji (tanpa DB nyata):
1. Validasi isian form publik: field wajib, pilihan baku (User EF 1–8,
   domisili, pendidikan, jenis kelamin), tanggal lahir, dan normalisasi HP.
2. Persetujuan syarat & ketentuan wajib — kiriman tanpa consent ditolak 400
   SEBELUM menyentuh DB.
3. Token form cabang: token salah ditolak, token benar diterima.
4. Nomor registrasi berformat CV-<CABANG>-<YYMMDD>-<urut>.
5. Role yang boleh melihat hanya traineer, ga_hr, dan admin — role lain 403,
   tanpa login 401.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session  # noqa: E402

from modules import helpers as hp  # noqa: E402
from modules import routes_cv_online as cv  # noqa: E402

APP = Flask(__name__)
APP.secret_key = 'test-cv-online'
cv.register_cv_online_routes(APP)

BASE = {
    'sumber_informasi': 'Instagram',
    'diundang_oleh': 'EF 1',
    'user_ef': 'EF 1',
    'kontak_serumah': 'Ibu Siti, 081211112222, IRT, Jl. Contoh 1',
    'kontak_tidak_serumah': 'Budi, 081233334444, Karyawan, Jl. Contoh 2',
    'nama': 'Budi Santoso',
    'tempat_lahir': 'Surabaya',
    'tanggal_lahir': '1995-01-19',
    'jenis_kelamin': 'Pria',
    'domisili': 'JAWA TIMUR',
    'alamat': 'Jl. Contoh No. 1, Surabaya',
    'no_hp': '081234567890',
    'pendidikan_terakhir': 'S1',
}


class TestValidation:
    def test_payload_lengkap_valid(self):
        data, error = cv.validate_payload(BASE)
        assert error == ''
        assert data['nama'] == 'Budi Santoso'
        assert data['no_hp_norm'] == '081234567890'
        assert data['nama_norm'] == 'BUDI SANTOSO'

    def test_field_wajib_kosong_ditolak(self):
        for key in ('sumber_informasi', 'diundang_oleh', 'kontak_serumah',
                    'kontak_tidak_serumah', 'user_ef', 'nama', 'tempat_lahir',
                    'tanggal_lahir', 'jenis_kelamin', 'domisili', 'alamat',
                    'no_hp', 'pendidikan_terakhir'):
            data, error = cv.validate_payload({**BASE, key: ''})
            assert data is None, key
            assert error, key

    def test_nama_terlalu_pendek(self):
        _data, error = cv.validate_payload({**BASE, 'nama': 'Ab'})
        assert 'Nama' in error

    def test_user_di_luar_ef_1_sampai_8_ditolak(self):
        _data, error = cv.validate_payload({**BASE, 'user_ef': 'EF 9'})
        assert error
        _data, error = cv.validate_payload({**BASE, 'user_ef': '<script>'})
        assert error

    def test_pilihan_baku_ditolak_bila_aneh(self):
        for key, value in (('jenis_kelamin', 'Lainnya'),
                           ('domisili', 'ANTARTIKA'),
                           ('pendidikan_terakhir', 'S3')):
            _data, error = cv.validate_payload({**BASE, key: value})
            assert error, key

    def test_tanggal_lahir_masa_depan_ditolak(self):
        _data, error = cv.validate_payload({**BASE, 'tanggal_lahir': '2999-01-01'})
        assert 'masa depan' in error
        _data, error = cv.validate_payload({**BASE, 'tanggal_lahir': '19-01-1995'})
        assert 'tidak valid' in error

    def test_hp_dinormalkan(self):
        for raw, expected in (('+62 812-3456-7890', '081234567890'),
                              ('81234567890', '081234567890'),
                              ('081234567890', '081234567890')):
            data, error = cv.validate_payload({**BASE, 'no_hp': raw})
            assert error == '', raw
            assert data['no_hp_norm'] == expected

    def test_hp_tidak_valid_ditolak(self):
        _data, error = cv.validate_payload({**BASE, 'no_hp': '12345'})
        assert 'Handphone' in error

    def test_pengalaman_opsional(self):
        data, error = cv.validate_payload({**BASE, 'pengalaman_status': '',
                                           'pengalaman_lama': ''})
        assert error == ''
        _data, error = cv.validate_payload({**BASE, 'pengalaman_lama': '10 Tahun'})
        assert error


class TestConsent:
    def test_nilai_persetujuan_afirmatif(self):
        for value in ('1', 'true', 'yes', 'ya', 'on'):
            assert cv._consent_given(value)
        for value in ('', None, '0', 'tidak', 'setuju'):
            assert not cv._consent_given(value)

    def test_submit_tanpa_consent_ditolak_sebelum_db(self):
        hp._get_redis = lambda: None
        hp._counter_mem.clear()
        with APP.test_client() as client:
            response = client.post('/api/cv-online/public', data=BASE)
        assert response.status_code == 400
        assert 'persetujuan' in response.get_json()['msg'].lower()

    def test_isian_tidak_valid_ditolak_sebelum_consent(self):
        hp._get_redis = lambda: None
        hp._counter_mem.clear()
        with APP.test_client() as client:
            response = client.post('/api/cv-online/public',
                                   data={**BASE, 'consent': '1', 'nama': 'A'})
        assert response.status_code == 400
        assert 'nama' in response.get_json()['msg'].lower()


class TestBranchToken:
    def test_token_salah_ditolak(self):
        row = {'form_token': 'token-benar', 'active': 1}
        assert cv._token_error('SBY', 'token-salah', row)
        assert cv._token_error('SBY', '', row)

    def test_token_benar_diterima(self):
        row = {'form_token': 'token-benar', 'active': 1}
        assert cv._token_error('SBY', 'token-benar', row) == ''

    def test_cabang_tanpa_baris_token_tidak_dipaksa(self):
        assert cv._token_error('SBY', 'apa saja', None) == ''

    def test_path_form_membawa_cabang_dan_token(self):
        assert cv._form_path('MLG', 'abc') == '/app/cv-online-form?cabang=MLG&t=abc'


class _FakeCursor:
    def __init__(self, existing=0):
        self.existing = existing
        self.last = None

    def execute(self, sql, params=None):
        if 'COUNT(*)' in sql.upper():
            self.last = {'n': self.existing}
        elif 'SELECT ID' in sql.upper():
            self.last = None

    def fetchone(self):
        return self.last

    def close(self):
        pass


class _FakeConn:
    def __init__(self, existing=0):
        self.existing = existing

    def cursor(self, dictionary=False):
        return _FakeCursor(self.existing)


class TestRegistrationNo:
    def test_format_nomor_registrasi(self):
        from datetime import datetime
        code = cv._next_reg_no(_FakeConn(existing=4), datetime(2026, 1, 2, 9, 0), 'SBY')
        assert code == 'CV-SBY-260102-005'

    def test_nomor_bertambah_per_hari_dan_cabang(self):
        from datetime import datetime
        code = cv._next_reg_no(_FakeConn(existing=0), datetime(2026, 1, 2, 9, 0), 'MLG')
        assert code == 'CV-MLG-260102-001'


class TestRoleGate:
    def test_role_melihat_hanya_traineer_ga_hr_admin(self):
        assert set(cv.VIEW_ROLES) == {'traineer', 'ga_hr', 'admin'}
        assert 'finance' not in cv.VIEW_ROLES

    def test_tanpa_login_ditolak_401(self):
        with APP.test_client() as client:
            response = client.get('/api/cv-online')
        assert response.status_code == 401

    def test_role_lain_ditolak_403(self):
        with APP.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_role'] = 'finance'
                sess['user_name'] = 'finance1'
            response = client.get('/api/cv-online')
        assert response.status_code == 403

    def test_verifikasi_hanya_traineer_dan_admin(self):
        assert set(cv.EDIT_ROLES) == {'traineer', 'admin'}

    def test_role_ga_hr_tidak_bisa_verifikasi(self):
        with APP.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_role'] = 'ga_hr'
                sess['user_name'] = 'ga1'
            response = client.post('/api/cv-online/1/review',
                                   json={'action': 'verify'})
        assert response.status_code == 403
