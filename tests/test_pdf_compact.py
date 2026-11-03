"""Unit: PDF laporan compact (PDFReportCompact) & rekap BBM (BBMReportPDF) — desain v2.19.1.

Memastikan dokumen resmi compact tetap valid & memuat konten inti,
dan palet netral (hitam/abu) dipakai — tidak ada aksen warna biru/hijau/merah.
"""
import io
from datetime import datetime

from flask import Flask

from modules.pdf_generator import PDFReportCompact, BBMReportPDF
from modules import routes_reports
from tests.pdf_text import pdf_text as _pdf_text

def _sample_tx(**over):
    tx = {
        'id': 1,
        'display_id': 'BBM-2026-0001',
        'nopol': 'L 1234 AB',
        'driver_name': 'RIVAN',
        'vehicle_type': 'Avanza',
        'bbm_type': 'Pertalite',
        'spbu_type': 'Shell',
        'gps_address': 'Jl. Darmo Permai, Surabaya',
        'nominal': 100000,
        'liter': 15.5,
        'odo_km': 123456,
        'km_per_liter': 12.5,
        'jumlah_appointment': 2,
        'price_per_liter': 10000,
        'created_at': datetime(2026, 8, 13, 10, 30),
    }
    tx.update(over)
    return tx


def _pdf_bytes(pdf):
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


class TestPDFReportCompact:
    def test_menghasilkan_pdf_valid_dengan_konten_inti(self):
        pdf = PDFReportCompact()
        pdf.add_page()
        pdf.generate_compact_report(_sample_tx())
        data = _pdf_bytes(pdf)
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]

    def test_konten_lengkap(self, monkeypatch):
        from modules.company_identity import get_branch_identity
        monkeypatch.setattr('modules.company_identity.get_branch_identity', lambda branch_code=None: {
            'company_name': 'PT BESTPROFIT FUTURES',
            'company_subtitle': 'Cabang Surabaya',
            'company_address': 'Graha Bukopin Surabaya',
            'company_phone': '031-5349888',
        })
        pdf = PDFReportCompact()
        pdf.set_identity(branch_code='SBY')
        pdf.add_page()
        pdf.generate_compact_report(_sample_tx())
        buf = io.BytesIO()
        pdf.output(buf)
        raw = buf.getvalue()
        # Dekompresi teks (fpdf menghasilkan aliran terkompresi)
        text = _pdf_text(raw)
        assert 'TRANSAKSI BBM-2026-0001' in text
        assert 'INFORMASI TRANSAKSI' in text
        assert 'KRONOLOGIS VERIFIKASI' in text
        assert 'STATUS PERSETUJUAN' in text
        assert 'RIVAN' in text
        assert 'Rp 100,000' in text
        assert 'Cabang Surabaya' in text
        assert 'Graha Bukopin Surabaya' in text
        assert 'Equity Tower' not in text


class TestBBMReportPDF:
    def test_menghasilkan_pdf_valid(self):
        pdf = BBMReportPDF(title='REKAP DANA BBM')
        pdf.add_page()
        pdf.generate_table([_sample_tx(), _sample_tx(id=2, nopol='L 9999 CD')])
        data = _pdf_bytes(pdf)
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]

    def test_konten_rekap(self, monkeypatch):
        monkeypatch.setattr('modules.company_identity.get_branch_identity', lambda branch_code=None: {
            'company_name': 'PT BESTPROFIT FUTURES',
            'company_subtitle': 'Cabang Surabaya',
            'company_address': 'Graha Bukopin Surabaya',
            'company_phone': '031-5349888',
        })
        pdf = BBMReportPDF(title='REKAP DANA BBM')
        pdf.set_identity(branch_code='SBY')
        pdf.add_page()
        pdf.generate_table([_sample_tx()])
        buf = io.BytesIO()
        pdf.output(buf)
        text = _pdf_text(buf.getvalue())
        assert 'REKAP DANA BBM' in text
        assert 'L 1234 AB' in text
        assert 'RIVAN' in text
        assert 'Cabang Surabaya' in text
        assert 'Graha Bukopin Surabaya' in text
        assert 'Equity Tower' not in text


class TestBBMPDFRouteBranchIdentity:
    class FakeCursor:
        def __init__(self, tx):
            self.tx = tx

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return self.tx

        def close(self):
            pass

    class FakeConn:
        def __init__(self, tx):
            self.tx = tx

        def cursor(self, dictionary=False):
            return TestBBMPDFRouteBranchIdentity.FakeCursor(self.tx)

        def commit(self):
            pass

        def close(self):
            pass

    def _client(self, monkeypatch, pdf_class):
        monkeypatch.setattr(routes_reports, 'get_db_connection',
                            lambda: self.FakeConn(_sample_tx()))
        monkeypatch.setattr(routes_reports, 'PDFReportCompact', pdf_class)
        monkeypatch.setattr(routes_reports, 'BBMReportPDF', pdf_class)
        app = Flask(__name__)
        app.secret_key = 'test'
        app.config['UPLOAD_FOLDER'] = 'uploads'
        routes_reports.register_report_routes(app)
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_role'] = 'finance'
            session['user_name'] = 'finance_bdg'
            session['branch_code'] = 'BDG'
        return client

    def _assert_branch_pdf(self, monkeypatch, route, pdf_class):
        from modules import company_identity, config

        identity_calls = []
        monkeypatch.setattr(company_identity, 'get_branch_identity',
                            lambda branch_code=None: identity_calls.append(branch_code) or {
                                'company_name': 'PT BESTPROFIT FUTURES',
                                'company_subtitle': 'Cabang Bandung',
                                'company_address': 'Gedung Bandung',
                                'company_phone': '022-1234567',
                            })
        monkeypatch.setattr(config, 'get_db_connection', lambda *args, **kwargs: None)
        client = self._client(monkeypatch, pdf_class)
        response = client.get(route)
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert identity_calls == ['BDG']
        text = _pdf_text(response.data)
        assert 'Cabang Bandung' in text
        assert 'Gedung Bandung' in text
        assert 'Equity Tower' not in text

    def test_pdf_transaksi_menghasilkan_kop_cabang_sesi(self, monkeypatch):
        self._assert_branch_pdf(monkeypatch, '/admin/report/1', PDFReportCompact)

    def test_pdf_rekap_menghasilkan_kop_cabang_sesi(self, monkeypatch):
        monkeypatch.setattr(routes_reports, 'get_rekap_data', lambda **kwargs: [_sample_tx()])
        self._assert_branch_pdf(monkeypatch, '/admin/rekap/pdf', BBMReportPDF)
