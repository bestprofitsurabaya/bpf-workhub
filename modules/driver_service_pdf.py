"""PDF resmi: CATATAN TAMBAHAN SERVICE MOBIL (v2.131.0).

Mengikuti format formulir Word yang dipakai GA: identitas driver/kendaraan,
catatan keluhan, pernyataan penyerahan, dan dua kolom tanda tangan.
"""
from modules.pdf_generator import BPFBasePDF, INK, GRAY_LABEL, RULE


class DriverServicePDF(BPFBasePDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)

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
