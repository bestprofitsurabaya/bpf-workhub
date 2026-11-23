"""PDF resmi: CATATAN TAMBAHAN SERVICE MOBIL (v2.131.0).

Mengikuti format formulir Word yang dipakai GA: identitas driver/kendaraan,
catatan keluhan, pernyataan penyerahan, dan dua kolom tanda tangan.

Rilis B: halaman pertama menyisipkan QR verifikasi berisi payload deterministik
yang dipakai GA/Finance untuk pencocokan manual (tanpa halaman verifikasi publik).
"""
import hashlib
import io
import re
import unicodedata

import qrcode

from modules.pdf_generator import BPFBasePDF, INK, GRAY_LABEL, RULE

QR_SIZE_MM = 18  # ukuran QR di pojok kanan atas halaman pertama


def _display_id_ascii(display_id):
    """Samakan display_id ke ASCII agar payload QR selalu dapat discan."""
    text = '' if display_id is None else str(display_id)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', text).strip()


def _tanggal_iso(created_at):
    """Ambil tanggal YYYY-MM-DD dari datetime maupun string ISO."""
    if created_at is None:
        return ''
    if hasattr(created_at, 'strftime'):
        return created_at.strftime('%Y-%m-%d')
    text = str(created_at)
    found = re.search(r'\d{4}-\d{2}-\d{2}', text)
    return found.group(0) if found else text[:10]


def qr_payload(display_id, created_at):
    """Payload QR: BPF-SERVICE:<display_id>:<sha256(display_id + tanggal)>."""
    clean_id = _display_id_ascii(display_id)
    tanggal = _tanggal_iso(created_at)
    digest = hashlib.sha256((clean_id + tanggal).encode('utf-8')).hexdigest()
    return f'BPF-SERVICE:{clean_id}:{digest}'


def render_qr(display_id, created_at):
    """Render PNG QR ke BytesIO in-memory (siap dipakai FPDF.image())."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_payload(display_id, created_at))
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(buf, format='PNG')
    buf.seek(0)
    return buf


class DriverServicePDF(BPFBasePDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)

    def render_qr(self, display_id, created_at):
        """Bungkus render_qr modul agar pemanggil PDF bisa memakai self.render_qr()."""
        return render_qr(display_id, created_at)

    def _line(self, label, value, y=None):
        if y is not None:
            self.set_y(y)
        self.set_font(self._font(), 'B', 10)
        self.cell(42, 7, self.clean_text(str(label)), new_x='RMARGIN', new_y='TOP')
        self.set_font(self._font(), '', 10)
        self.cell(0, 7, self.clean_text(str(value or '-')),
                  new_x='LMARGIN', new_y='NEXT')

    def generate(self, row):
        self.add_page()
        f = self._font()
        self.set_text_color(*INK)

        # QR verifikasi: pojok kanan atas halaman pertama, tepat di bawah kop.
        # Gambar dibuat in-memory (BytesIO) sehingga tidak ada file sementara.
        self.image(
            self.render_qr(row.get('display_id', '-'), row.get('created_at')),
            x=self.w - self.r_margin - QR_SIZE_MM,
            y=self.get_y(),
            w=QR_SIZE_MM,
            h=QR_SIZE_MM,
        )

        self.set_font(f, 'B', 14)
        self.cell(0, 8, 'CATATAN TAMBAHAN SERVICE MOBIL', align='C',
                  new_x='LMARGIN', new_y='NEXT')
        self.set_font(f, '', 9)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 5, f'No. Form: {row.get("display_id", "-")}', align='C',
                  new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*INK)
        self.ln(4)

        tanggal = row.get('created_at')
        if hasattr(tanggal, 'strftime'):
            tanggal = tanggal.strftime('%d/%m/%Y %H:%M')
        self._line('Nama Driver', row.get('driver_display_name') or row.get('driver_name'))
        self._line('Nomor Polisi', row.get('nopol'))
        self._line('Jenis Mobil', row.get('vehicle_type'))
        self._line('KM Kendaraan', row.get('km_kendaraan'))
        self._line('Tanggal', tanggal)
        self.ln(4)

        self.set_font(f, '', 10)
        intro = ('Selamat siang, '
                 'Berikut catatan keluhan kendaraan yang saya rasakan untuk bahan '
                 'pertimbangan service mobil di atas berdasarkan kondisi kendaraan '
                 'yang saya bawa, yaitu :')
        self.multi_cell(0, 5.5, self.clean_text(intro),
                        new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

        # Area catatan keluhan — garis bergaris seperti formulir Word.
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        start_y = self.get_y()
        for _ in range(8):
            self.line(self.l_margin, self.get_y() + 6, self.w - self.r_margin,
                      self.get_y() + 6)
            self.ln(6)
        self.set_y(start_y)
        self.set_font(f, '', 10)
        self.multi_cell(0, 5.5, self.clean_text(row.get('keluhan') or '-'),
                        new_x='LMARGIN', new_y='NEXT')
        self.set_y(max(self.get_y(), start_y + 48) + 3)

        self.set_font(f, '', 10)
        closing = ('Dengan ini saya telah menyampaikan keluhan yang saya rasakan '
                   'untuk bahan pertimbangan service mobil yang akan dilakukan.')
        self.multi_cell(0, 5.5, self.clean_text(closing),
                        new_x='LMARGIN', new_y='NEXT')
        self.cell(0, 6, 'Terima kasih', new_x='LMARGIN', new_y='NEXT')
        self.ln(10)

        # Tanda tangan.
        half = (self.w - self.l_margin - self.r_margin) / 2
        x1 = self.get_x()
        y1 = self.get_y()
        self.set_font(f, '', 9)
        self.cell(half, 5, 'Driver Kendaraan', align='C', new_x='RMARGIN', new_y='TOP')
        self.cell(half, 5, 'G.A Cabang', align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*INK)
        self.line(x1 + 12, y1 + 14, x1 + half - 12, y1 + 14)
        self.line(x1 + half + 12, y1 + 14, x1 + 2 * half - 12, y1 + 14)
        self.set_font(f, '', 8)
        self.set_text_color(*GRAY_LABEL)
        self.cell(half, 5, '( ' + self.clean_text(str(row.get('driver_display_name') or row.get('driver_name') or '')) + ' )',
                  align='C', new_x='RMARGIN', new_y='TOP')
        self.cell(half, 5, '( ................................ )', align='C',
                  new_x='LMARGIN', new_y='NEXT')

        if row.get('ga_note'):
            self.ln(4)
            self.set_text_color(*INK)
            self.set_font(f, 'B', 9)
            self.cell(0, 5, 'Catatan GA:', new_x='LMARGIN', new_y='NEXT')
            self.set_font(f, '', 9)
            self.multi_cell(0, 5, self.clean_text(str(row['ga_note'])),
                            new_x='LMARGIN', new_y='NEXT')
