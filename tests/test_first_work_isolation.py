"""Isolasi cabang & perlindungan data pribadi FirstWork (v2.82.0).

Yang diuji (murni fungsi — tanpa DB):
1. Cabang form publik TIDAK pernah "diam-diam" jatuh ke SBY saat disebut salah.
2. Token form per cabang: token cabang lain / tanpa token untuk cabang
   non-default ditolak.
3. Nomor registrasi memuat kode cabang & berbeda antar cabang.
4. Referrer cabang lain tidak boleh menempel pada isian cabang ini.
5. NIK disamarkan saat diekspor oleh role yang tidak memverifikasi identitas.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

from modules import routes_first_work as fw

BRANCHES = [
    {'code': 'SBY', 'name': 'Cabang Surabaya'},
    {'code': 'MLG', 'name': 'Cabang Malang'},
]
TOKENS = {
    'SBY': {'form_token': 'tok-sby', 'active': 1},
    'MLG': {'form_token': 'tok-mlg', 'active': 1},
}

APP = Flask(__name__)


def _resolve(query='', value=None):
    with APP.test_request_context('/form' + query):
        return fw._resolve_form_branch(None, branches=BRANCHES, value=value)


class TestBranchResolution:
    def test_explicit_valid_branch(self):
        assert _resolve('?cabang=MLG') == ('MLG', '')

    def test_unknown_branch_rejected_instead_of_silent_sby(self):
        """Alasan utama v2.82.0: salah ketik dulu berakhir di antrean SBY."""
        code, err = _resolve('?cabang=MLGG')
        assert code is None
        assert 'tidak dikenal' in err

    def test_inactive_branch_rejected(self):
        code, err = fw._resolve_form_branch(None, branches=[{'code': 'SBY'}], value='MLG')
        assert code is None
        assert err

    def test_no_branch_keeps_legacy_default(self):
        assert _resolve('') == ('SBY', '')

    def test_branch_from_post_field(self):
        with APP.test_request_context('/form', method='POST', data={'branch': 'mlg'}):
            assert fw._resolve_form_branch(None, branches=BRANCHES) == ('MLG', '')


class TestBranchToken:
    def test_token_of_other_branch_rejected(self):
        assert fw._token_error('MLG', 'tok-sby', TOKENS['MLG'], 'SBY')

    def test_own_token_accepted(self):
        assert fw._token_error('MLG', 'tok-mlg', TOKENS['MLG'], 'SBY') == ''

    def test_non_default_branch_requires_token(self):
        assert fw._token_error('MLG', '', TOKENS['MLG'], 'SBY')

    def test_default_branch_without_token_rejected_v284(self):
        """v2.84.0: kompatibilitas tautan lama dicabut — semua cabang wajib
        tautan ber-token agar isian antar cabang terpembedakan sempurna."""
        assert fw._token_error('SBY', '', TOKENS['SBY'], 'SBY')

    def test_all_branches_reject_missing_token(self):
        for code in ('SBY', 'MLG'):
            assert fw._token_error(code, '', TOKENS[code], 'SBY')

    def test_wrong_token_on_default_branch_still_rejected(self):
        assert fw._token_error('SBY', 'tok-mlg', TOKENS['SBY'], 'SBY')

    def test_token_read_from_link(self):
        with APP.test_request_context('/form?t=abc123'):
            assert fw._form_token_from_request() == 'abc123'

    def test_token_read_from_body(self):
        with APP.test_request_context('/form', method='POST', data={'t': 'from-body'}):
            assert fw._form_token_from_request() == 'from-body'


class TestFormLinkPerBranch:
    def test_form_path_differs_per_branch(self):
        sby = fw._form_path('SBY', 'tok-sby')
        mlg = fw._form_path('MLG', 'tok-mlg')
        assert sby != mlg
        assert 'cabang=MLG' in mlg
        assert 't=tok-mlg' in mlg

    def test_form_path_without_token(self):
        assert fw._form_path('SBY') == '/app/first-work-form?cabang=SBY'


class TestBranchScopedNumbering:
    def test_registration_no_contains_branch(self):
        stamp = datetime(2026, 11, 11, 9, 0, 0)
        assert fw.format_reg_no('SBY', stamp, 7) == 'FW-SBY-20261111-0007'
        assert fw.format_reg_no('MLG', stamp, 1) == 'FW-MLG-20261111-0001'

    def test_same_date_never_shares_number_across_branches(self):
        stamp = datetime(2026, 11, 11)
        assert fw.format_reg_no('SBY', stamp, 1) != fw.format_reg_no('MLG', stamp, 1)


class TestReferrerIsolation:
    def test_referrer_of_other_branch_rejected(self):
        assert not fw._referrer_in_branch({'branch_code': 'SBY'}, 'MLG')

    def test_referrer_of_same_branch_accepted(self):
        assert fw._referrer_in_branch({'branch_code': 'MLG'}, 'MLG')

    def test_legacy_null_belongs_to_default_branch_only(self):
        assert fw._referrer_in_branch({'branch_code': None}, 'SBY')
        assert not fw._referrer_in_branch({'branch_code': None}, 'MLG')


class TestNikMinimisation:
    def test_mask_keeps_only_edges(self):
        assert fw._mask_nik('3578010101900001') == '357801\u2022\u2022\u2022\u20220001'

    def test_export_masks_for_non_verifying_roles(self):
        row = {'nik': '3578010101900001', 'nik_raw': ''}
        assert fw._nik_for_export(row, True) == '3578010101900001'
        assert fw._nik_for_export(row, False) == '357801\u2022\u2022\u2022\u20220001'

    def test_invalid_nik_is_not_invented(self):
        assert fw._mask_nik('123') == '123'


class _TokenCursor:
    """Cursor palsu: dua tabel token cabang dengan isi berbeda."""

    def __init__(self, sql=''):
        self.sql = sql

    def execute(self, sql, params=None):
        self.sql = ' '.join(str(sql).split())

    def fetchall(self):
        if 'cv_online_branch_forms' in self.sql:
            return [
                {'branch_code': 'SBY', 'form_token': 'portal-sby', 'active': 1},
                {'branch_code': 'MLG', 'form_token': 'portal-mlg', 'active': 1},
            ]
        if 'first_work_branch_forms' in self.sql:
            return [
                {'branch_code': 'SBY', 'form_token': 'fw-sby', 'active': 1},
                {'branch_code': 'MLG', 'form_token': 'fw-mlg', 'active': 1},
            ]
        return []

    def close(self):
        pass


class _TokenConn:
    def cursor(self, dictionary=False):
        return _TokenCursor()


def _enforce(query):
    with APP.test_request_context('/form' + query):
        return fw._enforce_branch_token(_TokenConn(), 'SBY', branches=BRANCHES)


class TestPortalTokenDariTautanRekrutmen:
    """Portal rekrutmen hanya membawa satu token cabang (token CV Online).

    Klik kartu FirstWork dari portal harus tetap membuka form yang sama,
    tanpa melemahkan isolasi cabang.
    """

    def test_token_portal_cabang_sama_diterima(self):
        assert _enforce('?cabang=SBY&t=portal-sby') == ''

    def test_token_portal_cabang_lain_ditolak(self):
        assert _enforce('?cabang=SBY&t=portal-mlg')

    def test_token_firstwork_lama_tetap_diterima(self):
        assert _enforce('?cabang=SBY&t=fw-sby') == ''

    def test_token_asing_tetap_ditolak(self):
        assert _enforce('?cabang=SBY&t=token-ngawur')


class TestCabangDariTokenPortal:
    """Tautan portal hanya membawa token, tanpa parameter cabang.

    Server harus mengenali cabang dari token portal yang sah, bukan jatuh
    diam-diam ke cabang default.
    """

    def _resolve(self, query):
        with APP.test_request_context('/form' + query):
            return fw._resolve_form_branch(_TokenConn(), branches=BRANCHES)

    def test_token_portal_menentukan_cabang(self):
        assert self._resolve('?t=portal-mlg') == ('MLG', '')

    def test_token_firstwork_lama_tetap_menentukan_cabang(self):
        assert self._resolve('?t=fw-mlg') == ('MLG', '')

    def test_cabang_eksplisit_tetap_dihormati(self):
        assert self._resolve('?cabang=SBY&t=portal-sby') == ('SBY', '')

    def test_token_asing_tetap_jatuh_ke_default_lalu_ditolak(self):
        code, error = self._resolve('?t=token-ngawur')
        assert code == 'SBY' and error == ''
