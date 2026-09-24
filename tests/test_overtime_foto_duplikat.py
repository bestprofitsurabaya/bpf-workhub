"""v2.42.1 — anti foto-duplikat overtime (slot mulai vs selesai).

Latar: insiden Sep 2026 — baris form tersimpan dengan kedua slot foto
berisi foto yang sama (identik byte maupun piksel). Validasi baru wajib
menolak payload duplikat.
"""
import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image

from modules.overtime_shared import (
    validate_overtime_data, fotos_b64_sama, annotate_foto_issue,
    group_foto_issue_users,
)


def _jpeg_bytes(color, size=(64, 64)) -> bytes:
    """Buat JPEG kecil berwarna solid untuk pengujian."""
    im = Image.new('RGB', size, color)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=90)
    return buf.getvalue()


def _data_url(b: bytes) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(b).decode()


def _payload(foto_mulai=None, foto_selesai=None):
    data = {
        'nama': 'Budi', 'posisi': 'OB', 'tanggal': '2026-09-23',
        'waktu_mulai': '08:00', 'waktu_selesai': '17:00',
    }
    if foto_mulai is not None:
        data['foto_mulai'] = foto_mulai
    if foto_selesai is not None:
        data['foto_selesai'] = foto_selesai
    return data


class TestFotosB64Sama:
    def test_bytes_identik(self):
        b = _jpeg_bytes((200, 10, 10))
        assert fotos_b64_sama(_data_url(b), _data_url(b)) is True

    def test_piksel_identik_byte_beda(self):
        # Foto sama, re-encode JPEG (byte beda, piksel sama)
        im = Image.new('RGB', (64, 64), (30, 144, 255))
        b1, b2 = io.BytesIO(), io.BytesIO()
        im.save(b1, format='JPEG', quality=95)
        im.save(b2, format='JPEG', quality=60)
        assert fotos_b64_sama(_data_url(b1.getvalue()),
                              _data_url(b2.getvalue())) is True

    def test_foto_beda(self):
        assert fotos_b64_sama(_data_url(_jpeg_bytes((0, 0, 0))),
                              _data_url(_jpeg_bytes((255, 255, 255)))) is False

    def test_ukuran_beda_dianggap_beda(self):
        assert fotos_b64_sama(_data_url(_jpeg_bytes((5, 5, 5), (64, 64))),
                              _data_url(_jpeg_bytes((5, 5, 5), (128, 128)))) is False

    def test_input_kosong(self):
        assert fotos_b64_sama('', '') is False
        assert fotos_b64_sama(None, _data_url(_jpeg_bytes((1, 2, 3)))) is False
        assert fotos_b64_sama('bukan-data-url', 'bukan-data-url') is False


class TestValidateOvertimeDataFotoDuplikat:
    def test_duplikat_ditolak(self):
        b = _jpeg_bytes((120, 120, 120))
        is_valid, errors, _ = validate_overtime_data(
            _payload(_data_url(b), _data_url(b)), modul='ob')
        assert not is_valid
        assert 'foto_selesai' in errors

    def test_piksel_identik_ditolak(self):
        im = Image.new('RGB', (64, 64), (10, 200, 100))
        b1, b2 = io.BytesIO(), io.BytesIO()
        im.save(b1, format='JPEG', quality=92)
        im.save(b2, format='JPEG', quality=55)
        is_valid, errors, _ = validate_overtime_data(
            _payload(_data_url(b1.getvalue()), _data_url(b2.getvalue())), modul='ob')
        assert not is_valid
        assert 'foto_selesai' in errors

    def test_dua_foto_berbeda_diterima(self):
        is_valid, errors, cleaned = validate_overtime_data(
            _payload(_data_url(_jpeg_bytes((250, 0, 0))),
                     _data_url(_jpeg_bytes((0, 0, 250)))), modul='ob')
        assert is_valid, errors
        assert cleaned['foto_mulai_b64'].startswith('data:image/jpeg')
        assert cleaned['foto_selesai_b64'].startswith('data:image/jpeg')

    def test_satu_foto_saja_tetap_diterima(self):
        is_valid, errors, _ = validate_overtime_data(
            _payload(foto_mulai=_data_url(_jpeg_bytes((9, 9, 9)))), modul='ob')
        assert is_valid, errors


class TestAnnotateFotoIssue:
    def test_baris_identik_ditandai(self, tmp_path):
        # File A: byte-identik (pola timpa insiden) → issue True
        ba = _jpeg_bytes((120, 120, 120))
        (tmp_path / 'A_mulai.jpg').write_bytes(ba)
        (tmp_path / 'A_selesai.jpg').write_bytes(ba)
        # File B: foto beda ukuran jauh → issue False (cukup stat, murah)
        (tmp_path / 'B_mulai.jpg').write_bytes(_jpeg_bytes((10, 10, 10)))
        (tmp_path / 'B_selesai.jpg').write_bytes(_jpeg_bytes((10, 10, 10), (300, 300)))
        # File C: foto sama, re-encode (ukuran nyaris sama) → issue True via piksel
        im = Image.new('RGB', (64, 64), (10, 200, 100))
        c1, c2 = io.BytesIO(), io.BytesIO()
        im.save(c1, format='JPEG', quality=92)
        im.save(c2, format='JPEG', quality=55)
        (tmp_path / 'C_mulai.jpg').write_bytes(c1.getvalue())
        (tmp_path / 'C_selesai.jpg').write_bytes(c2.getvalue())

        rows = [{'foto_mulai': '/uploads/overtime/A_mulai.jpg',
                 'foto_selesai': '/uploads/overtime/A_selesai.jpg'},
                {'foto_mulai': '/uploads/overtime/B_mulai.jpg',
                 'foto_selesai': '/uploads/overtime/B_selesai.jpg'},
                {'foto_mulai': '/uploads/overtime/C_mulai.jpg',
                 'foto_selesai': '/uploads/overtime/C_selesai.jpg'},
                {'foto_mulai': '', 'foto_selesai': ''}]
        annotate_foto_issue(rows, foto_dir=str(tmp_path))
        assert rows[0]['foto_issue'] is True   # byte identik
        assert rows[1]['foto_issue'] is False  # foto benar-benar beda
        assert rows[2]['foto_issue'] is True   # piksel identik (re-encode)
        assert rows[3]['foto_issue'] is False  # kosong


class TestGroupFotoIssueUsers:
    def _row(self, nama, posisi='OB', **kw):
        r = {'nama': nama, 'posisi': posisi, 'foto_issue': True}
        r.update(kw)
        return r

    def test_grouping_per_user_terurut(self):
        rows = [self._row('Edwin', display_id='A'), self._row('Edwin', display_id='B'),
                self._row('Febri', display_id='C'), self._row('Budi', display_id='D'),
                self._row('Budi', display_id='E'), self._row('Budi', display_id='F')]
        out = group_foto_issue_users(rows)
        assert [u['nama'] for u in out] == ['Budi', 'Edwin', 'Febri']
        assert [u['total'] for u in out] == [3, 2, 1]
        assert out[0]['records'][0]['display_id'] == 'D'

    def test_baris_non_issue_diabaikan(self):
        rows = [self._row('Edwin'), {'nama': 'Bersih', 'posisi': 'OB', 'foto_issue': False}]
        out = group_foto_issue_users(rows)
        assert len(out) == 1 and out[0]['nama'] == 'Edwin'

    def test_tanpa_nama_dikelompokkan(self):
        out = group_foto_issue_users([{'nama': '', 'posisi': 'OB', 'foto_issue': True}])
        assert out[0]['nama'] == '(tanpa nama)'


class TestOvertimeFormPDFLayout:
    """v2.43.1 — Form PDF OT: label foto seragam & muat 1 halaman."""

    def _generate(self, row, photos=None):
        from modules.pdf_generator import OvertimeFormPDF
        from tests.pdf_text import _pdf_text
        pdf = OvertimeFormPDF()
        pdf.generate(row, photos=photos, modul='ob')
        buf = io.BytesIO()
        pdf.output(buf)
        return pdf, _pdf_text(buf.getvalue())

    def test_label_foto_seragam_dengan_watermark(self):
        row = {'display_id': 'OTX-002', 'email': 'ob@mail.com', 'posisi': 'OB',
               'nama': 'Budi', 'tanggal': '2026-09-23', 'waktu_mulai': '08:00',
               'waktu_selesai': '17:00', 'keterangan': 'OT',
               'foto_mulai': '/uploads/overtime/xxx_mulai.jpg',
               'foto_selesai': '/uploads/overtime/xxx_selesai.jpg'}
        _, txt = self._generate(row)
        up = txt.upper()
        assert 'FOTO MULAI OT' in up and 'FOTO SELESAI OT' in up
        assert 'SELFIE' not in up and 'DI TUJUAN' not in up

    def test_form_1_halaman_dengan_dua_foto(self, tmp_path):
        """Dua foto besar (portrait & landscape) tetap 1 halaman — foto
        berdampingan dgn tinggi adaptif sisa ruang."""
        from modules.pdf_generator import OvertimeFormPDF
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        f1 = os.path.join(base, 'uploads', '_test_foto_a.jpg')
        f2 = os.path.join(base, 'uploads', '_test_foto_b.jpg')
        Image.new('RGB', (1200, 1600), (180, 30, 30)).save(f1, format='JPEG')  # portrait
        Image.new('RGB', (1600, 1200), (30, 30, 180)).save(f2, format='JPEG')  # landscape
        try:
            row = {'display_id': 'OTX-003', 'email': 'ob@mail.com', 'posisi': 'OB',
                   'nama': 'Budi', 'tanggal': '2026-09-23', 'waktu_mulai': '08:00',
                   'waktu_selesai': '17:00', 'keterangan': 'OT malam panjang'
                   * 1}
            pdf = OvertimeFormPDF()
            pdf.generate(row, photos={'foto_mulai': '/uploads/_test_foto_a.jpg',
                                      'foto_selesai': '/uploads/_test_foto_b.jpg'},
                         modul='ob')
            assert pdf.page == 1, f'Form meluber ke {pdf.page} halaman'
        finally:
            for f in (f1, f2):
                if os.path.exists(f):
                    os.remove(f)

    def test_form_1_halaman_tanpa_foto(self):
        row = {'display_id': 'OTX-004', 'email': 'ob@mail.com', 'posisi': 'Security',
               'nama': 'Budi', 'tanggal': '2026-09-23', 'waktu_mulai': '22:00',
               'waktu_selesai': '05:00', 'keterangan': 'OT lewat tengah malam (H+1)'}
        pdf, _ = self._generate(row)
        assert pdf.page == 1


class TestDetailExcelKolomFoto:
    """v2.43.2 — detail report Excel: kolom FOTO MULAI OT / FOTO SELESAI OT
    (hyperlink bukti) — label seragam dengan watermark & viewer admin."""

    def _rows(self):
        return [{
            'display_id': 'OTL-SBY-20260922-0001', 'nama': 'Edwin', 'posisi': 'OB',
            'tanggal': '2026-09-21', 'waktu_mulai': '18:30', 'waktu_selesai': '20:30',
            'keterangan': 'OT', 'gps_address': 'Jl. Contoh',
            'foto_mulai': '/uploads/overtime/OTL-SBY-20260922-0001_mulai.jpg',
            'foto_selesai': '/uploads/overtime/OTL-SBY-20260922-0001_selesai.jpg',
        }]

    def _workbook(self, modul='ob'):
        from modules.pdf_generator import generate_overtime_detail_excel
        buf = generate_overtime_detail_excel(
            self._rows(), driver_name='Edwin', driver_role='OB',
            date_label='2026-09-01 s/d 2026-09-30', modul=modul)
        from openpyxl import load_workbook
        return load_workbook(io.BytesIO(buf.getvalue())).active

    def test_header_kolom_foto(self):
        ws = self._workbook()
        assert ws.cell(row=5, column=12).value == 'FOTO MULAI OT'
        assert ws.cell(row=5, column=13).value == 'FOTO SELESAI OT'

    def test_hyperlink_bukti_foto(self):
        ws = self._workbook()
        c12, c13 = ws.cell(row=6, column=12), ws.cell(row=6, column=13)
        assert c12.value == 'Lihat bukti' and c12.hyperlink.target.endswith('_mulai.jpg')
        assert c13.value == 'Lihat bukti' and c13.hyperlink.target.endswith('_selesai.jpg')

    def test_tanpa_foto_tampil_strip(self):
        rows = self._rows()
        rows[0]['foto_mulai'] = ''
        rows[0]['foto_selesai'] = ''
        from modules.pdf_generator import generate_overtime_detail_excel
        buf = generate_overtime_detail_excel(rows, driver_name='Edwin',
                                             driver_role='OB', date_label='x', modul='ob')
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(buf.getvalue())).active
        assert ws.cell(row=6, column=12).value == '-'
        assert ws.cell(row=6, column=13).value == '-'
