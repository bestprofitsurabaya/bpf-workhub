"""Generator laporan resmi rekap pengajuan air minum (v2.37.6).

Dua format, dipanggil dari GET /api/water/purchases/export:
- generate_water_report_excel(rows, meta) → bytes .xlsx (openpyxl, landscape)
- generate_water_report_pdf(rows, meta)   → bytes .pdf  (fpdf2, landscape)

v2.37.6 — perbaikan tata letak baris:
- PDF : grid digambar manual per baris (rect + garis kolom) sehingga semua
        kolom rata walau teks multi-baris; tinggi baris diukur dari SEMUA
        kolom (bukan 3 kolom), header tabel diulang tiap halaman, teks
        vertikal center pada sel satu baris, blok TTD dgn tempat/tanggal.
- Excel: tinggi baris mengikuti konten wrap, zebra fill, warna status,
         garis tanda tangan di ATAS nama, freeze panes header.
- Kop : identitas mengikuti cabang sesi (meta['company'] dari tabel
        branches) — bukan selalu Kantor Pusat.

TTD default dua pihak: Finance (Dibuat oleh) & Kepala Cabang (Mengetahui).
"""
from io import BytesIO

STATUS_LABEL = {'pending': 'Menunggu Verifikasi',
                'verified': 'Terverifikasi',
                'rejected': 'Ditolak'}

STATUS_COLOR = {'pending': 'B45309',     # amber-700
                'verified': '15803D',    # green-700
                'rejected': 'B91C1C'}    # red-700


def _fmt_date(v):
    from datetime import datetime, date
    if isinstance(v, (datetime, date)):
        return v.strftime('%d/%m/%Y')
    s = str(v or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s[:10], fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return s if s else '-'


def _items_text(p):
    items = p.get('items') or []
    if not items:
        return '-'
    return '; '.join(f"{i.get('brand', '-')} {i.get('drink_type', '')} "
                     f"{i.get('quantity', '')} {i.get('satuan', '')}".strip()
                     for i in items)


def _totals(rows):
    t = {'pending': 0, 'verified': 0, 'rejected': 0, 'qty': 0}
    for r in rows:
        t[r.get('status', 'pending')] = t.get(r.get('status'), 0) + 1
        for it in (r.get('items') or []):
            t['qty'] += int(it.get('quantity') or 0)
    return t


def _signatures(meta):
    """(nama_kepala, nama_finance) — fallback label bila belum diset."""
    head = (meta.get('head_name') or '').strip() or 'Kepala Cabang'
    fin = (meta.get('finance_name') or '').strip() or 'Finance'
    return head, fin


def _row_values(rows):
    """Bangun nilai kolom per baris data (dipakai Excel & PDF — satu sumber)."""
    out = []
    for i, p in enumerate(rows, 1):
        out.append([
            str(i),
            p.get('display_id') or '-',
            _fmt_date(p.get('purchase_date')),
            p.get('ob_name') or '-',
            _items_text(p),
            str(sum(int(it.get('quantity') or 0) for it in (p.get('items') or []))),
            STATUS_LABEL.get(p.get('status'), p.get('status') or '-'),
            p.get('remark') or '-',
            p.get('note') or '-',
        ])
    return out


# ============================================================
# EXCEL (openpyxl) — landscape A4
# ============================================================
def generate_water_report_excel(rows, meta):
    """rows = list dict pengajuan (dengan items); meta = dict filter & TTD."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

    head_name, fin_name = _signatures(meta)
    t = _totals(rows)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Rekap Air Minum'

    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    zebra_fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')
    summary_fill = PatternFill(start_color='EEF2FF', end_color='EEF2FF', fill_type='solid')
    title_font = Font(name='Arial', bold=True, size=14, color='1E293B')
    subtitle_font = Font(name='Arial', size=10, color='475569')
    contact_font = Font(name='Arial', size=8.5, color='64748B')
    header_font = Font(name='Arial', bold=True, size=9, color='FFFFFF')
    normal_font = Font(name='Arial', size=9)
    bold_font = Font(name='Arial', bold=True, size=9)

    # A No | B No Dokumen | C Tanggal | D OB | E Rincian | F Total Qty | G Status | H Remark | I Catatan
    widths = {'A': 5, 'B': 22, 'C': 12, 'D': 18, 'E': 46, 'F': 10, 'G': 18, 'H': 34, 'I': 34}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    last_col = 'I'

    ws.merge_cells(f'A1:{last_col}1')
    ws['A1'] = 'LAPORAN REKAP PENGAJUAN AIR MINUM'
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells(f'A2:{last_col}2')
    ident = meta.get('company') or {}
    ws['A2'] = (f"{ident.get('company_name', 'PT BESTPROFIT FUTURES')} — "
                f"{ident.get('company_subtitle', 'Cabang')}"
                f"  •  Periode {_fmt_date(meta.get('from'))} s/d {_fmt_date(meta.get('to'))}")
    ws['A2'].font = subtitle_font
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells(f'A3:{last_col}3')
    addr = (ident.get('company_address') or '').strip()
    phone = (ident.get('company_phone') or '').strip()
    contact = ' | '.join(x for x in (addr, f'Telp: {phone}' if phone else '') if x)
    ws['A3'] = contact if contact else ' '
    ws['A3'].font = contact_font
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.merge_cells(f'A4:{last_col}4')
    ftxt = meta.get('filters_text') or ''
    ws['A4'] = f'Filter: {ftxt}' if ftxt else 'Filter: Semua status'
    ws['A4'].font = Font(name='Arial', italic=True, size=9, color='64748B')
    ws['A4'].alignment = Alignment(horizontal='center')

    headers = ['No', 'No. Dokumen', 'Tanggal', 'OB', 'Rincian Item', 'Total Qty',
               'Status', 'Remark Verifikasi', 'Catatan']
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=5, column=ci, value=h)
        c.font = header_font
        c.fill = header_fill
        c.border = thin
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[5].height = 18
    ws.freeze_panes = 'A6'
    ws.print_title_rows = '5:5'

    def _xl_lines(text, width):
        import math
        per = max(int(width * 1.05), 8)
        s = str(text or '-')
        return max(1, math.ceil(len(s) / per))

    wrap_w = {2: widths['B'], 4: widths['D'], 5: widths['E'], 8: widths['H'], 9: widths['I']}
    r0 = 6
    for i, vals in enumerate(_row_values(rows)):
        row = r0 + i
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=ci, value=v)
            c.font = normal_font
            c.border = thin
            if ci in (1, 3, 6, 7):
                c.alignment = Alignment(horizontal='center', vertical='center',
                                        wrap_text=(ci == 7))
            else:
                c.alignment = Alignment(horizontal='left', vertical='center',
                                        wrap_text=True)
            if ci == 6:
                c.number_format = '0'
            if ci == 7:
                color = STATUS_COLOR.get(
                    next((k for k, lbl in STATUS_LABEL.items() if lbl == v), ''), '334155')
                c.font = Font(name='Arial', size=9, bold=True, color=color)
            if i % 2 == 0:
                c.fill = zebra_fill
        # tinggi baris mengikuti konten wrap (kolom teks terpanjang)
        lines = max(_xl_lines(vals[ci - 1], w) for ci, w in wrap_w.items())
        ws.row_dimensions[row].height = max(15, lines * 12.5 + 3)

    # Ringkasan
    sr = r0 + len(rows) + 1
    ws.merge_cells(f'A{sr}:{last_col}{sr}')
    ws[f'A{sr}'] = (f"RINGKASAN: Total {len(rows)} pengajuan | Menunggu {t['pending']} | "
                    f"Terverifikasi {t['verified']} | Ditolak {t['rejected']} | "
                    f"Total Qty {t['qty']}")
    ws[f'A{sr}'].font = bold_font
    ws[f'A{sr}'].fill = summary_fill
    ws[f'A{sr}'].alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[sr].height = 18

    # Blok TTD dua pihak — garis tanda tangan di ATAS nama
    sr2 = sr + 3                      # baris label "Dibuat oleh," / "Mengetahui,"
    left_c, right_c = 'C', 'G'
    ws[f'{left_c}{sr2}'] = 'Dibuat oleh,'
    ws[f'{right_c}{sr2}'] = 'Mengetahui,'
    for col in (left_c, right_c):
        ws[f'{col}{sr2}'].font = normal_font
    sr3_line = sr2 + 4                # baris kosong = garis tanda tangan
    sr3 = sr2 + 5                     # baris nama
    ws[f'{left_c}{sr3_line}'].border = Border(bottom=Side(style='thin'))
    ws[f'{right_c}{sr3_line}'].border = Border(bottom=Side(style='thin'))
    ws[f'{left_c}{sr3}'] = fin_name.upper()
    ws[f'{right_c}{sr3}'] = head_name.upper()
    for col in (left_c, right_c):
        ws[f'{col}{sr3}'].font = bold_font
    sr4 = sr3 + 1
    ws[f'{left_c}{sr4}'] = 'Finance'
    ws[f'{right_c}{sr4}'] = 'Kepala Cabang'
    for col in (left_c, right_c):
        ws[f'{col}{sr4}'].font = Font(name='Arial', italic=True, size=8, color='64748B')
    sr5 = sr4 + 1
    ws[f'{left_c}{sr5}'] = f"Tanggal: {_fmt_date(meta.get('to'))}"
    ws[f'{left_c}{sr5}'].font = Font(name='Arial', italic=True, size=8, color='64748B')

    # Print setup: landscape, fit to width
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================
# PDF (fpdf2) — landscape A4, kop identitas cabang
# ============================================================
class WaterReportPDF:
    """Laporan PDF landscape di atas BPFBasePDF (kop & footer standar BPF)."""

    def __init__(self, identity=None):
        from modules import pdf_generator as _pg
        from modules.pdf_generator import BPFBasePDF
        self._pg = _pg
        self._identity_override = identity
        self.pdf = BPFBasePDF(orientation='L', unit='mm', format='A4')
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.pdf.set_margins(10, 7, 10)

    @property
    def INK(self): return self._pg.INK

    @property
    def GRAY_LABEL(self): return self._pg.GRAY_LABEL

    @property
    def RULE(self): return self._pg.RULE

    # kolom: No | No Dokumen | Tanggal | OB | Rincian | Qty | Status | Remark | Catatan
    WIDTHS = [10, 32, 19, 30, 64, 13, 26, 50, 52]   # total 296 mm < 297 (A4 landscape)
    HEADERS = ['No', 'No. Dokumen', 'Tanggal', 'OB', 'Rincian Item', 'Qty',
               'Status', 'Remark Verifikasi', 'Catatan']
    ALIGNS = ['C', 'L', 'C', 'L', 'L', 'C', 'C', 'L', 'L']
    WRAP_COLS = {1, 3, 4, 6, 7, 8}                  # index kolom teks bebas

    def generate(self, rows, meta):
        p = self.pdf
        # Kop mengikuti identitas cabang (meta) — override cache identitas
        # BPFBasePDF SEBELUM add_page() agar header() memakai kop cabang.
        base = dict(self._pg.IDENTITY_DEFAULTS)
        try:
            base.update(self._pg.get_company_identity())
        except Exception:
            pass
        base.update({k: v for k, v in (self._identity_override or {}).items() if v})
        # v2.37.6b: kop mengikuti cabang sesi — meta['company'] dibangun dari
        # tabel branches di _export_meta() (kunci = nama field identity).
        # Diterapkan di sini agar routes tak perlu pass identity eksplisit.
        base.update({k: v for k, v in (meta.get('company') or {}).items() if v})
        p._identity = base

        head_name, fin_name = _signatures(meta)
        t = _totals(rows)
        p.add_page()
        self._title(meta)
        self._table(rows)
        self._summary(t)
        self._signatures(head_name, fin_name, meta)
        out = p.output()  # fpdf2 ≥2.7: bytearray
        return bytes(out) if isinstance(out, (bytearray, memoryview)) else str(out).encode('latin-1', errors='replace')

    def _title(self, meta):
        p = self.pdf
        ident = meta.get('company') or {}
        p.set_font(p._font(), 'B', 13)
        p.set_text_color(*self.INK)
        p.cell(0, 7, 'LAPORAN REKAP PENGAJUAN AIR MINUM', align='C',
               new_x='LMARGIN', new_y='NEXT')
        p.set_font(p._font(), '', 8.5)
        p.set_text_color(*self.GRAY_LABEL)
        sub = (f"{ident.get('company_name', 'PT BESTPROFIT FUTURES')} — "
               f"{ident.get('company_subtitle', 'Cabang')}"
               f"  •  Periode {_fmt_date(meta.get('from'))} s/d {_fmt_date(meta.get('to'))}")
        p.cell(0, 5, p.clean_text(sub), align='C', new_x='LMARGIN', new_y='NEXT')
        ftxt = meta.get('filters_text') or 'Semua status'
        p.set_font(p._font(), 'I', 7.5)
        p.cell(0, 4.5, p.clean_text(f'Filter: {ftxt}'), align='C',
               new_x='LMARGIN', new_y='NEXT')
        p.ln(3)
        p.set_text_color(*self.INK)

    # ---- ukuran baris ----
    LINE_H = 3.2      # tinggi 1 baris teks wrap (mm)
    PAD_V = 1.2       # padding vertikal atas/bawah sel

    def _row_h(self, vals):
        """Tinggi baris = max jumlah baris wrap dari SEMUA kolom."""
        p = self.pdf
        p.set_font(p._font(), '', 7)
        max_lines = 1
        for ci, (w, v) in enumerate(zip(self.WIDTHS, vals)):
            txt = p.clean_text(str(v if v not in (None, '') else '-'))
            if ci in self.WRAP_COLS:
                n = len(p.multi_cell(w - 2, self.LINE_H, txt,
                                     dry_run=True, output='LINES'))
            else:
                n = 1 if p.get_string_width(txt) <= (w - 2) else 2
            max_lines = max(max_lines, n)
        return max_lines * self.LINE_H + 2 * self.PAD_V

    # ---- header tabel (dipakai halaman pertama & lanjutan) ----
    def _table_header(self):
        p = self.pdf
        p.set_draw_color(*self.RULE)
        p.set_line_width(0.2)
        p.set_fill_color(29, 78, 216)
        p.set_text_color(255, 255, 255)
        p.set_font(p._font(), 'B', 7.5)
        x = p.l_margin
        for w, h in zip(self.WIDTHS, self.HEADERS):
            p.set_xy(x, p.get_y())
            p.cell(w, 7, h, border=1, align='C', fill=True)
            x += w
        p.set_xy(p.l_margin, p.get_y() + 7)
        p.set_text_color(*self.INK)

    # ---- satu baris data: fill → teks → grid, semua relatif y0 ----
    def _row(self, vals, fill):
        p = self.pdf
        h = self._row_h(vals)
        if p.get_y() + h > p.h - p.b_margin - 2:
            p.add_page()
            self._table_header()
        y0 = p.get_y()
        x0 = p.l_margin
        total_w = sum(self.WIDTHS)
        p.set_font(p._font(), '', 7)
        p.set_text_color(*self.INK)
        # 1) fill zebra satu blok penuh
        if fill:
            p.set_fill_color(241, 245, 249)
            p.rect(x0, y0, total_w, h, style='F')
        # 2) teks per kolom (tanpa border/fill)
        x = x0
        for ci, (w, v) in enumerate(zip(self.WIDTHS, vals)):
            txt = p.clean_text(str(v if v not in (None, '') else '-'))
            if ci in self.WRAP_COLS:
                p.set_xy(x + 1, y0 + self.PAD_V)
                p.multi_cell(w - 2, self.LINE_H, txt, align=self.ALIGNS[ci])
            else:
                p.set_xy(x + 1, y0)
                p.cell(w - 2, h, txt, align=self.ALIGNS[ci])
            x += w
        # 3) grid: rect luar + garis kolom (selalu rata walau teks multi-baris)
        p.set_draw_color(*self.RULE)
        p.set_line_width(0.2)
        p.rect(x0, y0, total_w, h, style='D')
        xsep = x0
        for w in self.WIDTHS[:-1]:
            xsep += w
            p.line(xsep, y0, xsep, y0 + h)
        p.set_xy(x0, y0 + h)

    def _table(self, rows):
        self._table_header()
        fill = False
        for vals in _row_values(rows):
            self._row(vals, fill)
            fill = not fill

    def _summary(self, t):
        p = self.pdf
        p.ln(2)
        p.set_font(p._font(), 'B', 8)
        p.cell(0, 5, p.clean_text(
            f"RINGKASAN: Total {t['pending'] + t['verified'] + t['rejected']} pengajuan  |  "
            f"Menunggu {t['pending']}  |  Terverifikasi {t['verified']}  |  "
            f"Ditolak {t['rejected']}  |  Total Qty {t['qty']}"),
            new_x='LMARGIN', new_y='NEXT')

    def _signatures(self, head_name, fin_name, meta):
        p = self.pdf
        need = 48
        if p.get_y() + need > p.h - p.b_margin:
            p.add_page()
        p.ln(4)
        y0 = p.get_y()
        city = (meta.get('city') or '').strip()
        place = f"{city}, {_fmt_date(meta.get('to'))}" if city else _fmt_date(meta.get('to'))
        p.set_font(p._font(), '', 8)
        p.set_text_color(*self.INK)
        p.set_xy(p.l_margin, y0)
        p.cell(0, 5, p.clean_text(place), align='R')

        col_w = 80
        usable = p.w - p.l_margin - p.r_margin
        gap = (usable - 2 * col_w) / 2
        y_label = y0 + 8
        p.set_xy(p.l_margin, y_label)
        p.cell(col_w, 5, 'Dibuat oleh,', align='C')
        p.set_xy(p.l_margin + col_w + gap, y_label)
        p.cell(col_w, 5, 'Mengetahui,', align='C')

        y_line = y_label + 20
        p.set_draw_color(*self.GRAY_LABEL)
        p.set_line_width(0.3)
        p.line(p.l_margin + 8, y_line, p.l_margin + col_w - 8, y_line)
        p.line(p.l_margin + col_w + gap + 8, y_line,
               p.l_margin + col_w + gap + col_w - 8, y_line)

        p.set_font(p._font(), 'B', 9)
        p.set_xy(p.l_margin, y_line + 2)
        p.cell(col_w, 5, p.clean_text(fin_name).upper(), align='C')
        p.set_xy(p.l_margin + col_w + gap, y_line + 2)
        p.cell(col_w, 5, p.clean_text(head_name).upper(), align='C')

        p.set_font(p._font(), 'I', 7)
        p.set_text_color(*self.GRAY_LABEL)
        p.set_xy(p.l_margin, y_line + 8)
        p.cell(col_w, 4, 'Finance', align='C')
        p.set_xy(p.l_margin + col_w + gap, y_line + 8)
        p.cell(col_w, 4, 'Kepala Cabang', align='C')
        p.set_y(y_line + 14)
