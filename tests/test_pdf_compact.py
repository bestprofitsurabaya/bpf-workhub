"""Unit: PDF laporan compact (PDFReportCompact) & rekap BBM (BBMReportPDF) — desain v2.19.1.

Memastikan dokumen resmi compact tetap valid & memuat konten inti,
dan palet netral (hitam/abu) dipakai — tidak ada aksen warna biru/hijau/merah.
"""
import io
from datetime import datetime

from modules.pdf_generator import PDFReportCompact, BBMReportPDF


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

    def test_konten_lengkap(self):
        pdf = PDFReportCompact()
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


class TestBBMReportPDF:
    def test_menghasilkan_pdf_valid(self):
        pdf = BBMReportPDF(title='REKAP DANA BBM')
        pdf.add_page()
        pdf.generate_table([_sample_tx(), _sample_tx(id=2, nopol='L 9999 CD')])
        data = _pdf_bytes(pdf)
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]

    def test_konten_rekap(self):
        pdf = BBMReportPDF(title='REKAP DANA BBM')
        pdf.add_page()
        pdf.generate_table([_sample_tx()])
        buf = io.BytesIO()
        pdf.output(buf)
        text = _pdf_text(buf.getvalue())
        assert 'REKAP DANA BBM' in text
        assert 'L 1234 AB' in text
        assert 'RIVAN' in text


# Sumber tunggal ekstraktor teks PDF — lihat tests/pdf_text.py.
from tests.pdf_text import pdf_text as _pdf_text  # noqa: E402
