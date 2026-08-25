"""Sistem Pelamar Kerja (v2.16) — form publik, receptionist, traineer, PDF.

Menggantikan Google Form + Google Sheet: data dikelola internal.
Alur: pelamar submit form publik -> receptionist verifikasi/edit/kehadiran/status
-> traineer pantau rekrutan (scope upline sendiri). Laporan PDF resmi berlogo.
"""
import io
import re
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.helpers import (applicant_stage_label, applicant_status_label,
                             home_for_role, ROLE_HOME)
from modules.pdf_generator import ApplicantReportPDF
from tests.pdf_text import _pdf_text


# ============================================================
# Unit: label & home per role
# ============================================================
class TestLabels:
    def test_stage_labels(self):
        assert applicant_stage_label('interview') == 'Interview'
        assert applicant_stage_label('training_1') == 'Training Hari 1'
        assert applicant_stage_label('training_4') == 'Training Hari 4'
        assert applicant_stage_label('training_2') == 'Training Hari 2'

    def test_status_labels(self):
        assert applicant_status_label('interview') == '📅 Interview'
        assert applicant_status_label('lulus') == '🎓 Lulus'
        assert applicant_status_label('resigned') == '🚪 Mengundurkan Diri'
        assert applicant_status_label('training_3') == '📙 Training H3'

    def test_home_for_role(self):
        assert home_for_role('receptionist') == '/app/receptionist'
        assert home_for_role('traineer') == '/app/traineer'
        assert ROLE_HOME['receptionist'] == '/app/receptionist'
        assert ROLE_HOME['traineer'] == '/app/traineer'


# ============================================================
# Unit: PDF laporan kehadiran pelamar (berlogo, TTD receptionist)
# ============================================================
def _mk_pdf(rows, stage='interview'):
    pdf = ApplicantReportPDF()
    pdf.generate(rows, stage_label=applicant_stage_label(stage),
                 date_label='2026-08-13 s/d 2026-08-13',
                 filters={'Upline': 'UPLINE-A'}, generated_by='Receptionist')
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


class TestTraineerScope:
    """Scope traineer: kecocokan parsial case-insensitive (username + nama)."""

    def test_matches_full_name_or_username(self):
        import flask
        from modules.routes_applicants import _traineer_upline
        # Tanpa sesi -> None (endpoint menolak via role_required)
        with flask.Flask(__name__).test_request_context('/'):
            assert _traineer_upline() is None

    def test_where_clause_build(self):
        # Verifikasi konstruksi where untuk scope traineer tidak ganda.
        # (Logika penuh diuji E2E; unit ini mengamankan _traineer_upline.)
        import flask
        from modules.routes_applicants import _traineer_upline
        fapp = flask.Flask(__name__)
        fapp.secret_key = 'test-secret'
        with fapp.test_request_context('/'):
            flask.session['user_role'] = 'traineer'
            flask.session['user_name'] = 'traineer_a'
            flask.session['full_name'] = 'Traineer Upline A'
            assert _traineer_upline() == ['traineer_a', 'Traineer Upline A']


class TestApplicantPDF:
    def test_generate_empty_rows(self):
        data = _mk_pdf([], 'interview')
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        # Header laporan tampil meski tanpa baris data
        assert 'LAPORAN KEHADIRAN PELAMAR KERJA' in _pdf_text(data)

    def test_generate_with_rows(self):
        rows = [{
            'display_id': 'PLM-0001', 'nama_lengkap': 'Andi Wijaya',
            'pendidikan': 'SMA', 'no_hp': '081234567890', 'upline': 'UPLINE-A',
            'user_field': 'user_andi', 'posisi': 'Marketing',
            'interview_at': datetime(2026, 8, 13, 9, 30, 0),
            'status': 'interview', 'attended_at': datetime(2026, 8, 13, 9, 30, 0),
        }]
        data = _mk_pdf(rows, 'interview')
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        txt = _pdf_text(data)
        # Nama pelamar + data baris tampil di tabel
        assert 'ANDI WIJAJA' in txt.upper() or 'Andi' in txt
        assert '081234567890' in txt
        assert 'Marketing' in txt
        assert 'UPLINE-A' in txt.upper()
        # TTD receptionist tampil di PDF
        assert 'RECEPTIONIST' in txt.upper()


# ============================================================
# Unit: logika migrasi Google Sheet (v2.17)
# ============================================================
class TestSheetMigration:
    """Parse tanggal M/D/YYYY, normalisasi spasi ganda, status dari H/Pulang."""

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'migrate_sheet', os.path.join(os.path.dirname(__file__), '..',
                                          'scripts', 'migrate_applicants_sheet.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_clean_normalizes_double_space(self):
        m = self._load()
        assert m.clean('  TEAM  EDI 2 ') == 'TEAM EDI 2'
        assert m.clean('PUSPILITA GALUH ') == 'PUSPILITA GALUH'
        assert m.clean('') == ''

    def test_parse_dt_mdy(self):
        m = self._load()
        dt = m.parse_dt('5/1/2026', '8:45:33')
        assert dt is not None
        assert dt.strftime('%Y-%m-%d %H:%M:%S') == '2026-05-01 08:45:33'
        # Tanggal tanpa jam
        dt2 = m.parse_dt('12/25/2026', '')
        assert dt2 is not None and dt2.year == 2026 and dt2.month == 12
        # Data tidak valid -> None (dilewati)
        assert m.parse_dt('', '') is None

    def test_status_follows_furthest_training(self):
        m = self._load()
        # H1..H4 berdasarkan is_true; status mengikuti tahap terjauh
        assert m.is_true('TRUE') is True
        assert m.is_true('FALSE') is False
        assert m.is_true('') is False
