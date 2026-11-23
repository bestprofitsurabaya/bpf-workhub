"""Unit Tests — QR verifikasi pada PDF service (Rilis B)."""
import hashlib
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import modules.driver_service_pdf as pdf_module  # noqa: E402
from modules.driver_service_pdf import DriverServicePDF, qr_payload  # noqa: E402


ROW = {
    'display_id': 'SRV-SBY-20261123-0001',
    'created_at': datetime(2026, 11, 23, 9, 30),
    'driver_display_name': 'Rivan',
    'nopol': 'B 1126 DFC',
    'vehicle_type': 'AVANZA',
    'km_kendaraan': 12500,
    'keluhan': 'Rem berbunyi saat pengereman.',
}


def test_qr_payload_deterministik():
    assert qr_payload('SRV-001', '2026-11-23') == (
        'BPF-SERVICE:SRV-001:' + hashlib.sha256(b'SRV-0012026-11-23').hexdigest())


def test_qr_payload_hash_penuh_tanpa_trungkasi():
    payload = qr_payload('SRV-001', '2026-11-23')
    digest = payload.split(':')[-1]
    assert len(digest) == 64
    assert digest == hashlib.sha256(b'SRV-0012026-11-23').hexdigest()


def test_qr_payload_terima_datetime():
    assert qr_payload('SRV-001', datetime(2026, 11, 23, 14, 7, 3)) == qr_payload(
        'SRV-001', '2026-11-23')


def test_qr_payload_sanitasi_non_ascii():
    payload = qr_payload('SRV-001é', '2026-11-23')
    assert payload.startswith('BPF-SERVICE:')
    assert payload.isascii()
    assert 'SRV-001' in payload


def test_render_qr_mengembalikan_bytesio_png():
    from PIL import Image

    buf = DriverServicePDF().render_qr('SRV-001', '2026-11-23')
    assert isinstance(buf, io.BytesIO)
    assert buf.getvalue()[:8] == b'\x89PNG\r\n\x1a\n'
    with Image.open(buf) as img:
        assert img.size[0] == img.size[1]


def test_render_qr_deterministik():
    pdf = DriverServicePDF()
    a = pdf.render_qr('SRV-001', '2026-11-23').getvalue()
    b = pdf.render_qr('SRV-001', '2026-11-23').getvalue()
    other = pdf.render_qr('SRV-002', '2026-11-23').getvalue()
    assert a == b
    assert other != a


def test_line_value_mulai_di_awal_kolom_nilai():
    """Nilai tidak boleh mulai di RMARGIN (terkliping di tepi halaman)."""
    pdf = DriverServicePDF()
    pdf.add_page()
    x_sebelum_cell = []
    cell_asli = pdf.cell

    def spy(*args, **kwargs):
        x_sebelum_cell.append(pdf.get_x())
        return cell_asli(*args, **kwargs)

    pdf.cell = spy
    pdf._line('Nama Driver', 'Rivan')

    assert len(x_sebelum_cell) == 2
    assert x_sebelum_cell[0] == pytest.approx(pdf.l_margin)
    assert x_sebelum_cell[1] == pytest.approx(pdf.l_margin + 42)
    # cell(0) membentang dari x sampai margin kanan — harus punya ruang cukup.
    assert pdf.w - pdf.r_margin - x_sebelum_cell[1] >= 100


def test_generate_menyisipkan_image_qr_di_pdf(monkeypatch):
    from PIL import Image

    dipanggil = []
    render_asli = pdf_module.render_qr

    def spy(display_id, created_at):
        dipanggil.append((display_id, created_at))
        return render_asli(display_id, created_at)

    monkeypatch.setattr(pdf_module, 'render_qr', spy)

    pdf = DriverServicePDF()
    pdf.generate(dict(ROW))
    output = bytes(pdf.output())

    assert dipanggil == [(ROW['display_id'], ROW['created_at'])]
    with Image.open(pdf.render_qr(ROW['display_id'], ROW['created_at'])) as img:
        width, height = img.size
    assert b'/Subtype /Image' in output
    assert f'/Columns {width}'.encode('ascii') in output
    assert f'/Rows {height}'.encode('ascii') in output
