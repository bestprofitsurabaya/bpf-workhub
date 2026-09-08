"""PDF Generation Classes - BPF WorkHub"""
import os
import re
import io
from datetime import datetime, date
from fpdf import FPDF
from modules.company_identity import get_company_identity, IDENTITY_DEFAULTS  # noqa: F401

# ============================================================
# CONSTANTS (fallback bila identitas belum diset di system_config)
# ============================================================
COMPANY_NAME = 'PT BESTPROFIT FUTURES'
COMPANY_SUBTITLE = 'Kantor Pusat | Jakarta'
SYSTEM_VERSION = 'BPF WorkHub v2.37.8'
LOGO_FILENAMES = ['icon-512.png', 'icon-192.png']
PHOTO_FIELDS = [
    ('foto_odo_sebelum', 'ODO Sebelum'),
    ('foto_nota_odo_sesudah', 'Nota + ODO'),
    ('foto_struk', 'Struk BBM'),
    ('foto_struk_dispenser', 'Dispenser'),
]
HEALTH_BENCHMARK = 14  # KM/L ideal
MAX_IMAGE_WIDTH = 800
JPEG_QUALITY = 85
GRID_CELL_HEIGHT = 52
GRID_GAP = 3

# ============================================================
# PALETTE DOKUMEN RESMI (compact — minimal warna: hitam/abu/putih)
# Sesuai standar surat/dokumen resmi: teks hitam, garis tegas, tanpa blok warna.
# ============================================================
INK = (15, 23, 42)               # teks utama (hampir hitam)
INK_SOFT = (51, 65, 85)          # teks isi narasi
GRAY_LABEL = (100, 116, 139)     # label / keterangan
GRAY_MUTED = (148, 163, 184)     # teks redup (footer / placeholder)
BORDER = (203, 213, 225)         # garis tabel / kotak
HEADER_FILL = (241, 245, 249)    # isian header tabel & kotak selesai
ZEBRA_FILL = (248, 250, 252)     # strip zebra sangat tipis
RULE = (71, 85, 105)             # garis kop surat / underlining

# ============================================================
# BASE PDF CLASS
# ============================================================
class BPFBasePDF(FPDF):
    """Base PDF with standard BPF letterhead and footer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_fonts()
        self._identity = None

    def _company_identity(self):
        """Identitas perusahaan/cabang dari system_config (cache per PDF).

        Aman tanpa DB: bila DB tidak tersedia (mis. saat tes) mengembalikan
        nilai default konstan.
        """
        if self._identity is None:
            try:
                self._identity = get_company_identity()
            except Exception:
                # DB tidak tersedia (tes/script offline): fallback identitas
                # default penuh (nama, subjudul, alamat, kontak) — bukan {}.
                self._identity = dict(IDENTITY_DEFAULTS)
        return self._identity

    def set_identity(self, identity=None, branch_code=None):
        """Set identitas kop SEBELUM add_page() (v2.37.7).

        Dua cara pakai:
        - set_identity(dict)  : merge dict ke identitas global (kunci kosong
                                diabaikan — field yang tidak dikirim tetap
                                memakai nilai global).
        - set_identity(branch_code='SBY') : ambil identitas cabang dari
                                tabel branches (get_branch_identity) — kop
                                mengikuti cabang, alamat HO tidak ikut.

        Harus dipanggil sebelum halaman pertama digambar; header() memakai
        nilai ini untuk kop tiap halaman.
        """
        if branch_code:
            try:
                from modules.company_identity import get_branch_identity
                self._identity = get_branch_identity(branch_code=branch_code)
                return self._identity
            except Exception:
                pass  # jatuh ke merge dict / identitas global
        if identity:
            base = self._company_identity()
            base.update({k: v for k, v in identity.items() if v})
            self._identity = base
        return self._identity

    # ---- Font Setup ----
    def _register_fonts(self):
        font_dir = os.path.join(os.path.dirname(__file__), '..', 'fonts')
        os.makedirs(font_dir, exist_ok=True)
        regular = os.path.join(font_dir, 'DejaVuSans.ttf')
        bold = os.path.join(font_dir, 'DejaVuSans-Bold.ttf')
        italic = os.path.join(font_dir, 'DejaVuSans-Oblique.ttf')
        if os.path.exists(regular):
            self.add_font('DejaVu', '', regular, uni=True)
            self.add_font('DejaVu', 'B', bold if os.path.exists(bold) else regular, uni=True)
            self.add_font('DejaVu', 'I', italic if os.path.exists(italic) else regular, uni=True)
            self._use_unicode = True
        else:
            self._use_unicode = False

    def _font(self, style=''):
        return 'DejaVu' if getattr(self, '_use_unicode', False) else 'helvetica'

    # ---- Letterhead ----
    def header(self):
        # Kop surat resmi: logo kecil + nama hitam + garis tegas (tanpa warna)
        # Nama perusahaan & subjudul mengikuti identitas system_config (multi-cabang).
        identity = self._company_identity()
        company = identity.get('company_name') or COMPANY_NAME
        subtitle = identity.get('company_subtitle') or COMPANY_SUBTITLE
        address = identity.get('company_address') or ''
        phone = identity.get('company_phone') or ''
        logo = self._find_logo()
        if logo:
            try:
                self.image(logo, x=self.l_margin, y=5, w=11)
            except Exception:
                pass
        # Teks kop diratakan ke tengah LEBAR HALAMAN (bukan sisa area setelah
        # logo) supaya header simetris: logo di kiri, nama perusahaan tepat di
        # tengah halaman. r_margin ditahan sementara agar cell() membentang
        # penuh 0..w; posisi x di-reset ke l_margin oleh new_x="LMARGIN".
        r_margin_old = self.r_margin
        self.r_margin = 0
        self.set_x(0)
        self.set_font(self._font(), 'B', 13)
        self.set_text_color(*INK)
        self.cell(0, 6, company, align="C", new_x="LMARGIN", new_y="NEXT")
        # set_x(0) lagi tiap baris: new_x="LMARGIN" mengembalikan x ke margin
        # kiri, dan dengan r_margin=0 kotak cell jadi asimetris (kiri = margin,
        # kanan = 0) — teks yang diratakan tengah akan bergeser ke kanan.
        self.set_x(0)
        self.set_font(self._font(), '', 8)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        if address or phone:
            contact = ' | '.join(x for x in (address, 'Telp: ' + phone if phone else '') if x)
            self.set_x(0)
            self.cell(0, 3.6, self.clean_text(contact)[:110], align="C", new_x="LMARGIN", new_y="NEXT")
        self.r_margin = r_margin_old
        self.set_draw_color(*RULE)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
        self.ln(5)
        self.set_text_color(*INK)

    def footer(self):
        identity = self._company_identity()
        sys_name = identity.get('system_name') or 'BPF WorkHub'
        sys_version = identity.get('system_version') or 'v1'
        self.set_y(-16)
        self.set_draw_color(*BORDER)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-13)
        self.set_font(self._font(), 'I', 6)
        self.set_text_color(*GRAY_MUTED)
        now = datetime.now().strftime("%d-%m-%Y %H:%M")
        self.cell(0, 4, f'{sys_name} {sys_version} | Generated: {now} | Page {self.page_no()}/{{nb}}', align="C")
        self.set_text_color(*INK)

    def _find_logo(self):
        for name in LOGO_FILENAMES:
            for base in ['static', os.path.join(os.path.dirname(__file__), '..', 'static')]:
                path = os.path.join(base, name)
                if os.path.exists(path):
                    return path
        return None

    # ---- UI Helpers ----
    def section_title(self, title):
        # Sub-judul resmi: teks tebal hitam + garis bawah tipis (bukan blok berwarna)
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        self.cell(0, 5, '  ' + title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y() + 0.4, self.w - self.r_margin, self.get_y() + 0.4)
        self.ln(2.6)

    def info_row(self, label, value, x, y, w_label=30, w_value=50):
        self.set_xy(x, y)
        self.set_font(self._font(), '', 7.5)
        self.set_text_color(*GRAY_LABEL)
        self.cell(w_label, 4.6, label + ':', align="R")
        self.set_text_color(*INK)
        self.set_font(self._font(), 'B', 7.5)
        self.cell(w_value, 4.6, str(value) if value is not None else '-')
        self.set_text_color(*INK)

    def _empty_cell(self, x, y, w, h, text=''):
        self.set_draw_color(*BORDER)
        self.set_line_width(0.25)
        self.rect(x, y, w, h)
        # Label di tengah
        self.set_xy(x, y + h/2 - 4)
        self.set_font(self._font(), 'I', 7)
        self.set_text_color(*GRAY_MUTED)
        self.cell(w, 5, text, align='C')
        self.set_text_color(*INK)

    # ---- Tabel generik (header hitam + zebra tipis) ----
    def _table_header(self, headers, widths, font_size=7, row_h=7):
        """Baris header tabel resmi: blok hitam pekat + teks putih.

        Header multi-baris ('TANGGAL\\nTIMESTAMP') diratakan jadi satu baris:
        cell() tidak menangani '\\n' (glyph hilang → peringatan font & teks
        menyatu/terpotong antar kolom).
        """
        self.set_font(self._font(), 'B', font_size)
        self.set_fill_color(*INK)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            label = re.sub(r'\s+', ' ', str(h).replace('\n', ' ')).strip()
            self.cell(widths[i], row_h, label, border=1, align='C', fill=True)
        self.ln()
        self.set_font(self._font(), '', font_size)
        self.set_text_color(*INK)

    def _table_row(self, values, widths, aligns=None, row_h=6, fill=False):
        """Satu baris data dengan zebra ultra-tipis (fill dipakai bergantian)."""
        aligns = aligns or ['L'] * len(values)
        self.set_fill_color(*(ZEBRA_FILL if fill else (255, 255, 255)))
        for i, v in enumerate(values):
            self.cell(widths[i], row_h, self.clean_text(str(v)), border=1, fill=True, align=aligns[i])
        self.ln()

    def _signature_block(self, generated_by, role_label='Administrator', role=None):
        """Blok TTD kanan-bawah: 'Mengetahui,' + garis + nama + jabatan."""
        if self.get_y() + 35 > self.h - 25:
            self.add_page()
        col_w = 70
        x_ttd = self.w - self.r_margin - col_w
        self.set_xy(x_ttd, self.get_y())
        self.set_font(self._font(), '', 8)
        self.set_text_color(*RULE)
        self.cell(col_w, 5, 'Mengetahui,', align='C')
        self.ln(16)
        self.set_draw_color(*GRAY_LABEL)
        self.set_line_width(0.3)
        self.set_xy(x_ttd + 8, self.get_y())
        self.line(x_ttd + 8, self.get_y(), self.w - self.r_margin - 8, self.get_y())
        self.ln(2)
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        self.set_xy(x_ttd + 8, self.get_y())
        self.cell(col_w - 16, 5, self.clean_text(str(generated_by or role or role_label)).upper(), align='C')
        self.ln(5)
        self.set_font(self._font(), 'I', 7)
        self.set_text_color(*GRAY_LABEL)
        self.set_xy(x_ttd + 8, self.get_y())
        self.cell(col_w - 16, 4, role_label, align='C')

    # ---- Photo Grid 2x2 ----
    def add_photo_grid(self, photos, upload_folder='uploads'):
        """Render up to 4 photos in a 2x2 grid with labels."""
        if not photos:
            self.set_font(self._font(), 'I', 8)
            self.cell(0, 5, '(Tidak ada foto)', align='C')
            return
        margin = self.l_margin
        page_w = self.w - self.l_margin - self.r_margin
        cell_w = page_w / 2 - GRID_GAP
        cell_h = GRID_CELL_HEIGHT
        y_start = self.get_y()
        max_y = y_start
        grid_idx = 0
        for idx, photo in enumerate(photos):
            col, row = grid_idx % 2, grid_idx // 2
            x = margin + col * (cell_w + GRID_GAP)
            y = y_start + row * (cell_h + 12)

            # Jika foto tidak muat, buat halaman baru dan reset posisi grid
            if y + cell_h > self.h - 25:
                self.add_page()
                y_start = self.get_y()
                max_y = y_start
                grid_idx = 0
                col, row = grid_idx % 2, grid_idx // 2
                x = margin + col * (cell_w + GRID_GAP)
                y = y_start + row * (cell_h + 12)

            self.set_draw_color(*BORDER)
            self.set_line_width(0.3)
            self.rect(x, y, cell_w, cell_h)

            if photo.get('path'):
                filepath = os.path.join(upload_folder, photo['path'])
                if os.path.exists(filepath):
                    self._place_image(filepath, x, y, cell_w, cell_h)

            self.set_xy(x, y + cell_h + 1)
            self.set_font(self._font(), 'B', 6)
            self.set_text_color(*GRAY_LABEL)
            self.cell(cell_w, 4, photo.get('label', ''), align='C')
            self.set_text_color(*INK)

            if y + cell_h > max_y:
                max_y = y + cell_h + 12

            grid_idx += 1  # Lanjut ke slot berikutnya di halaman ini

        self.set_y(max_y + 4)

    def _place_image(self, filepath, x, y, cell_w, cell_h):
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                img_w, img_h = img.size
            ratio = min(cell_w / img_w, cell_h / img_h)
            new_w, new_h = img_w * ratio, img_h * ratio
            img_x = x + (cell_w - new_w) / 2
            img_y = y + (cell_h - new_h) / 2
            with Image.open(filepath) as img:
                if img_w > MAX_IMAGE_WIDTH:
                    r = MAX_IMAGE_WIDTH / img_w
                    img = img.resize((MAX_IMAGE_WIDTH, int(img_h * r)), Image.LANCZOS)
                buf = io.BytesIO()
                img.convert('RGB').save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
                buf.seek(0)
                self.image(buf, x=img_x, y=img_y, w=new_w, h=new_h)
        except Exception:
            self.set_draw_color(*BORDER)
            self.rect(x, y, cell_w, cell_h)
            try:
                self.image(filepath, x=x + 2, y=y + 2, w=cell_w - 4, h=cell_h - 4)
            except Exception:
                pass

    @staticmethod
    def extract_photos(tx):
        return [{'path': tx[f], 'label': l} for f, l in PHOTO_FIELDS if tx.get(f)]

    @staticmethod
    def clean_text(text):
        if not text:
            return ''
        return re.sub(r'[^\x20-\x7E\n\r\t]', '', str(text)).strip()

    def _fmt_dt(self, v):
        if v and hasattr(v, 'strftime'):
            return v.strftime('%d-%m-%Y')
        v = str(v or '-')
        return v[:10] if len(v) > 10 else v

    def _fmt_money(self, v):
        try:
            f = float(v or 0)
            return 'Rp {:,.0f}'.format(f) if f else '-'
        except (TypeError, ValueError):
            return '-'


# ============================================================
# SINGLE TRANSACTION REPORT
# ============================================================
class PDFReportCompact(BPFBasePDF):
    """Compact single-transaction PDF report with photo grid."""

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=7)
        self.set_margins(7, 7, 7)

    def generate_compact_report(self, tx, upload_folder='uploads'):
        self._draw_transaction_header(tx)
        self._draw_info_grid(tx)
        self._draw_narrative(tx)
        self._draw_cross_check(tx)
        self._draw_approval_bar(tx)
        self._draw_photos(tx, upload_folder)

    # ---- Private Methods ----
    def _draw_transaction_header(self, tx):
        nopol = self.clean_text(str(tx.get('nopol', '-')).upper())
        display_id = tx.get('display_id', f'#{tx["id"]}')
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 7, f'TRANSAKSI {display_id} | {nopol}', align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def _draw_info_grid(self, tx):
        self.section_title('INFORMASI TRANSAKSI')
        nopol = self.clean_text(str(tx.get('nopol', '-')).upper())
        driver = self.clean_text(str(tx.get('driver_name', '-')).upper())
        vehicle = self.clean_text(str(tx.get('vehicle_type', '-')))
        bbm = self.clean_text(str(tx.get('bbm_type', '-')))
        spbu = self.clean_text(str(tx.get('spbu_type', '-')).replace('_', ' ').title())
        gps = self.clean_text(str(tx.get('gps_address', '') or 'Tidak tersedia'))
        nominal = f'Rp {float(tx["nominal"]):,.0f}'
        liter = f'{float(tx["liter"]):.1f} L'
        odo = f'{int(tx["odo_km"]):,} km'
        kml = f'{float(tx.get("km_per_liter", 0)):.1f}'
        appt = f'{tx.get("jumlah_appointment", 0) or 0}x'
        price = f'Rp {float(tx.get("price_per_liter", 0)):,.0f}'
        rows = [
            [('ID', tx.get('display_id', f'#{tx["id"]}')), ('Tanggal', tx['created_at'].strftime('%d-%m-%Y %H:%M') if tx.get('created_at') else '-')],
            [('Nopol', nopol), ('Driver', driver)],
            [('Kendaraan', vehicle), ('BBM', bbm)],
            [('Nominal', nominal), ('Volume', liter)],
            [('Harga/L', price), ('ODO', odo)],
            [('KM/L', kml), ('Appointment', appt)],
            [('SPBU', spbu), ('GPS', gps[:60])],
        ]
        col1_x, col2_x = self.l_margin, self.w / 2 + 5
        y_start = self.get_y()
        for i, row in enumerate(rows):
            y = y_start + (i * 5.1)
            self.info_row(row[0][0], row[0][1], col1_x, y)
            self.info_row(row[1][0], row[1][1], col2_x, y)
        self.set_y(y_start + len(rows) * 5.1 + 1.5)

    def _draw_narrative(self, tx):
        self.section_title('KRONOLOGIS VERIFIKASI')
        nopol = self.clean_text(str(tx.get('nopol', '-')).upper())
        driver = self.clean_text(str(tx.get('driver_name', 'Driver')).upper())
        bbm = self.clean_text(str(tx.get('bbm_type', '-')))
        spbu = self.clean_text(str(tx.get('spbu_type', '-')).replace('_', ' ').title())
        gps = self.clean_text(str(tx.get('gps_address', '') or 'lokasi tidak terdeteksi'))
        tgl = tx['created_at'].strftime('%d %B %Y pukul %H:%M') if tx.get('created_at') else '-'
        narrative = (
            f'Pada hari {tgl}, {driver} selaku driver kendaraan {nopol} '
            f'melakukan pengisian {bbm} sebanyak {tx["liter"]} Liter '
            f'dengan total Rp {float(tx["nominal"]):,.0f} di SPBU {spbu}. '
            f'Pengisian dilakukan pada ODO {int(tx["odo_km"]):,} km. '
            f'Lokasi: {gps}. '
        )
        appt = tx.get('jumlah_appointment', 0) or 0
        if appt > 0:
            narrative += f'Driver memiliki {appt} janji temu. '
        ga = self.clean_text(str(tx.get('ga_approved_by') or tx.get('approved_by_user') or ''))
        fin = self.clean_text(str(tx.get('finance_payout_by') or tx.get('payout_by_user') or ''))
        arc = self.clean_text(str(tx.get('archived_by') or tx.get('archived_by_user') or ''))
        if ga: narrative += f'Disetujui GA: {ga}. '
        if fin: narrative += f'Dana dicairkan Finance: {fin}. '
        if arc: narrative += f'Diarsipkan: {arc}. '
        narrative += 'Klaim dinyatakan SAH sesuai prosedur PT. Bestprofit Futures.'
        self.set_font(self._font(), '', 6.8)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(0, 3.8, narrative, align='J')
        self.ln(1.5)

    def _draw_cross_check(self, tx):
        self.section_title('CROSS-CHECK VERIFIKASI')
        try:
            from modules.config import get_db_connection
            conn = get_db_connection()
            if not conn:
                raise Exception('DB not available')
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT odo_km, created_at FROM transactions WHERE nopol=%s AND status='archived' AND id<%s ORDER BY id DESC LIMIT 1", (tx['nopol'], tx['id']))
            prev = cur.fetchone()
            cur.execute("SELECT ROUND(AVG(NULLIF(km_per_liter,0)),2) as avg_kml, COUNT(*) as cnt FROM transactions WHERE nopol=%s AND status='archived' AND km_per_liter>0", (tx['nopol'],))
            health = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(nominal),0) as total FROM transactions WHERE driver_name=%s AND MONTH(created_at)=MONTH(CURDATE())", (tx['driver_name'],))
            monthly = cur.fetchone()
            cur.execute("SELECT driver_notes FROM vehicle_assignments WHERE nopol=%s ORDER BY id DESC LIMIT 1", (tx['nopol'],))
            notes = cur.fetchone()
            cur.close(); conn.close()
            avg_kml = float(health['avg_kml']) if health and health['avg_kml'] else 10
            health_score = min(100, int((avg_kml / HEALTH_BENCHMARK) * 100))
            col_w = (self.w - self.l_margin - self.r_margin) / 2
            y = self.get_y()
            self.set_xy(self.l_margin, y)
            self.set_font(self._font(), 'B', 7)
            self.set_text_color(*INK)
            self.cell(col_w, 5, f'Health Score: {health_score}/100')
            self.set_xy(self.l_margin, y + 4.4)
            self.set_font(self._font(), '', 6)
            self.set_text_color(*GRAY_LABEL)
            self.cell(col_w, 4, f'Rata-rata KM/L: {avg_kml:.1f} ({health["cnt"]} tx)' if health else 'N/A')
            if prev:
                odo_diff = int(tx['odo_km']) - int(prev['odo_km'])
                self.set_xy(self.l_margin, y + 8.4)
                self.set_font(self._font(), '', 6)
                self.cell(col_w, 4, f'ODO Sebelumnya: {int(prev["odo_km"]):,} km (selisih {odo_diff:+d} km)')
            self.set_xy(self.l_margin + col_w, y)
            self.set_font(self._font(), 'B', 7)
            self.set_text_color(*INK)
            self.cell(col_w, 5, 'Budget Bulanan')
            self.set_xy(self.l_margin + col_w, y + 4.4)
            self.set_font(self._font(), '', 6)
            self.set_text_color(*GRAY_LABEL)
            self.cell(col_w, 4, f'Rp {float(monthly["total"]):,.0f}' if monthly else 'N/A')
            if notes and notes['driver_notes']:
                self.set_xy(self.l_margin, y + 12.4)
                self.set_font(self._font(), 'I', 6)
                self.set_text_color(*INK_SOFT)
                self.cell(0, 4, 'Catatan GA: ' + notes['driver_notes'])
            self.set_text_color(*INK_SOFT)
            self.ln(15)
        except Exception:
            self.ln(5)
            self.set_font(self._font(), 'I', 6)
            self.cell(0, 4, 'Data cross-check tidak tersedia', border=0)
            self.ln(5)

    def _draw_approval_bar(self, tx):
        self.section_title('STATUS PERSETUJUAN')
        ga = self.clean_text(str(tx.get('ga_approved_by') or tx.get('approved_by_user') or ''))
        fin = self.clean_text(str(tx.get('finance_payout_by') or tx.get('payout_by_user') or ''))
        arc = self.clean_text(str(tx.get('archived_by') or tx.get('archived_by_user') or ''))
        statuses = [
            ('GA APPROVAL', ga if ga else None),
            ('FINANCE PAYOUT', fin if fin else None),
            ('DRIVER TTD', 'Driver' if arc else None),
            ('ARCHIVED', arc if arc else None),
        ]
        bar_w = (self.w - self.l_margin - self.r_margin - 12) / 4
        x, y = self.l_margin, self.get_y() + 2
        self.set_draw_color(*BORDER)
        self.set_line_width(0.25)
        for label, who in statuses:
            done = bool(who)
            self.set_xy(x, y)
            self.set_font(self._font(), 'B', 5.5)
            if done:
                self.set_fill_color(*HEADER_FILL)
                self.set_text_color(*INK)
                self.cell(bar_w, 4.5, '✓ ' + label, border=1, fill=True, align='C')
            else:
                self.set_text_color(*GRAY_MUTED)
                self.cell(bar_w, 4.5, label, border=1, align='C')
            if who:
                self.set_xy(x, y + 5.2)
                self.set_font(self._font(), '', 4.5)
                self.set_text_color(*GRAY_LABEL)
                self.cell(bar_w, 3, who, align='C')
            x += bar_w + 4
        self.set_text_color(*INK)
        self.set_y(y + 10.5)

    def _draw_photos(self, tx, upload_folder):
        photos = self.extract_photos(tx)
        if photos:
            self.section_title('BUKTI VISUAL')
            self.add_photo_grid(photos, upload_folder)


# ============================================================
# TANDA TERIMA AIR MINUM (v2.6)
# Diisi OB -> diverifikasi Finance -> PDF TTD Finance (penyerah) & GA (penerima)
# ============================================================
class WaterReceiptPDF(BPFBasePDF):
    """Tanda terima air minum (gelas/botol/galon)."""

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=7)
        self.set_margins(10, 7, 10)

    def generate(self, p, items, ga_name='', finance_name='', upload_folder='uploads'):
        """p = dict pengajuan; items = list rincian.
        finance_name = nama user yang memverifikasi (fallback ke nama TTD
        system_config di route). upload_folder dipakai untuk melampirkan foto
        bukti OB (default 'uploads').
        Urutan (sesuai format Finance v2.29.4): Informasi Pengiriman → Rincian
        Barang → Hasil Verifikasi (Remark) → Lampiran Foto → Tanda Tangan."""
        self._draw_title(p)
        self._draw_info(p)
        self._draw_items_table(items)
        self._draw_verification(p)
        self._draw_photos(p, upload_folder)
        self._draw_signatures(p, ga_name, finance_name)

    # ---- Judul ----
    def _draw_title(self, p):
        self.set_font(self._font(), 'B', 12.5)
        self.set_text_color(*INK)
        self.cell(0, 7, 'TANDA TERIMA AIR MINUM', align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font(self._font(), '', 8)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4, f'No. {p.get("display_id", "-")}', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_text_color(*INK)

    # ---- Info pengiriman ----
    def _draw_info(self, p):
        self.section_title('INFORMASI PENGIRIMAN')
        rows = [
            ('Nomor', p.get('display_id', '-')),
            ('Tanggal Pengiriman', (p.get('purchase_date') or '').strftime('%d-%m-%Y') if getattr(p.get('purchase_date'), 'strftime', None) else p.get('purchase_date') or '-'),
            ('Diajukan oleh (OB)', self.clean_text(str(p.get('ob_name', '-')).upper())),
        ]
        col1_x, col2_x = self.l_margin, self.w / 2 + 5
        y_start = self.get_y()
        for i, (label, val) in enumerate(rows):
            y = y_start + (i * 5.1)
            self.info_row(label, val, col1_x, y)
        self.set_y(y_start + len(rows) * 5.1 + 1.5)

    # ---- Tabel item ----
    def _draw_items_table(self, items):
        self.section_title('RINCIAN BARANG')
        headers = ['NO', 'JENIS', 'MERK', 'SATUAN', 'KUANTITAS']
        widths = [10, 30, 70, 30, 30]
        self.set_draw_color(*BORDER)
        self.set_line_width(0.2)
        self._table_header(headers, widths, font_size=8, row_h=6.4)
        fill = False
        for idx, it in enumerate(items, 1):
            self._table_row(
                [idx, it.get('drink_type', '-'), it.get('brand', '-'), it.get('satuan', 'pcs'), it.get('quantity', 1)],
                widths, aligns=['C', 'C', 'L', 'C', 'C'], row_h=5.6, fill=fill)
            fill = not fill
        self.ln(3)

    # ---- Hasil verifikasi ----
    def _draw_verification(self, p):
        self.section_title('HASIL VERIFIKASI FINANCE')
        status = p.get('status', '')
        if status == 'verified':
            remark = self.clean_text(str(p.get('remark', '') or ''))
            note = self.clean_text(str(p.get('note', '') or ''))
            self.set_font(self._font(), 'B', 8)
            self.set_text_color(*INK)
            self.cell(0, 5, '✔ TERVERIFIKASI', new_x="LMARGIN", new_y="NEXT")
            self.set_font(self._font(), '', 8)
            self.multi_cell(0, 4.5, f'Remark: {remark or "-"}', new_x="LMARGIN", new_y="NEXT")
            if note:
                self.multi_cell(0, 4.5, f'Catatan tambahan: {note}', new_x="LMARGIN", new_y="NEXT")
            ver = self.clean_text(str(p.get('verified_by', '') or ''))
            if ver:
                self.set_font(self._font(), 'I', 7)
                self.set_text_color(*GRAY_LABEL)
                self.cell(0, 4.5, f'Diverifikasi oleh: {ver}', new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(*INK)
        elif status == 'rejected':
            self.set_font(self._font(), 'B', 8)
            self.set_text_color(*INK)
            self.cell(0, 5, '✘ DITOLAK', new_x="LMARGIN", new_y="NEXT")
            self.set_font(self._font(), '', 8)
            self.multi_cell(0, 4.5, f'Alasan: {self.clean_text(str(p.get("rejection_reason", "-") or "-"))}', new_x="LMARGIN", new_y="NEXT")
        else:
            self.set_font(self._font(), 'I', 8)
            self.set_text_color(*GRAY_MUTED)
            self.cell(0, 5, 'Menunggu verifikasi Finance...', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    # ---- Tanda tangan ----
    def _draw_signatures(self, p, ga_name, finance_name):
        # Blok TTD memakai posisi absolut (set_xy) yang tidak memicu page-break —
        # paksa pindah halaman dulu bila sisa ruang tidak cukup agar TTD tidak
        # terpotong/terpecah di antara dua halaman. Cek dilakukan SEBELUM judul
        # seksi digambar supaya judul 'TANDA TANGAN' tidak terpisah (orphan) di
        # dasar halaman sebelumnya (+12 mm = tinggi judul seksi + jarak ln 4).
        if self.get_y() + 45 + 12 > self.h - 25:
            self.add_page()
        self.section_title('TANDA TANGAN')
        self.ln(4)
        col_w = (self.w - self.l_margin - self.r_margin) / 2
        self.set_font(self._font(), 'B', 8)
        self.set_text_color(*INK)
        self.set_xy(self.l_margin, self.get_y())
        self.cell(col_w, 5, 'Menyerahkan,', align='C')
        self.set_xy(self.l_margin + col_w, self.get_y())
        self.cell(col_w, 5, 'Menerima,', align='C')
        self.ln(26)
        self.set_draw_color(*GRAY_LABEL)
        self.set_line_width(0.3)
        self.set_xy(self.l_margin + 6, self.get_y())
        self.line(self.l_margin + 6, self.get_y(), self.l_margin + col_w - 6, self.get_y())
        self.set_xy(self.l_margin + col_w + 6, self.get_y())
        self.line(self.l_margin + col_w + 6, self.get_y(), self.w - self.r_margin - 6, self.get_y())
        self.ln(2)
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        self.set_xy(self.l_margin + 6, self.get_y())
        self.cell(col_w - 12, 5, self.clean_text(str(finance_name or 'FINANCE')).upper(), align='C')
        self.set_xy(self.l_margin + col_w + 6, self.get_y())
        self.cell(col_w - 12, 5, self.clean_text(str(ga_name or 'GA')).upper(), align='C')
        self.ln(5)
        self.set_font(self._font(), 'I', 7)
        self.set_text_color(*GRAY_LABEL)
        self.set_xy(self.l_margin + 6, self.get_y())
        self.cell(col_w - 12, 4, 'Finance', align='C')
        self.set_xy(self.l_margin + col_w + 6, self.get_y())
        self.cell(col_w - 12, 4, 'GA Officer', align='C')
        self.set_text_color(*INK)
        self.ln(8)

    # ---- Lampiran foto (bukti unggahan OB) ----
    def _draw_photos(self, p, upload_folder='uploads'):
        photos = []
        if p.get('foto_before'):
            photos.append({'path': p['foto_before'], 'label': 'Foto SEBELUM diisi'})
        if p.get('foto_after'):
            photos.append({'path': p['foto_after'], 'label': 'Foto SESUDAH diisi'})
        if not photos:
            return

        # v2.29.7: foto bukti diperbesar — tinggi sel foto mengikuti ruang kosong
        # yang tersedia di halaman (ruang blok TTD dicadangkan ±60 mm) sehingga
        # foto lebih tinggi & lebih lebar, dan tanda tangan terdorong ke bawah.
        # Judul seksi digambar SETELAH cek ruang agar tidak orphan di dasar halaman.
        bottom = self.h - 25
        photo_chrome = 16    # judul seksi (8) + label foto & jarak bawah (8)
        sig_reserve = 60     # tinggi blok TTD (cek serupa di _draw_signatures: 57)

        def _fit_height():
            return min(max((bottom - self.get_y()) - photo_chrome - sig_reserve, 60), 130)

        cell_h = _fit_height()
        if self.get_y() + photo_chrome + cell_h > bottom:
            self.add_page()
            cell_h = _fit_height()

        self.section_title('LAMPIRAN FOTO (TIMESTAMP)')
        margin = self.l_margin
        page_w = self.w - self.l_margin - self.r_margin
        n = len(photos)
        gap = 4
        cell_w = (page_w - gap * (n - 1)) / n
        y = self.get_y()
        for i, ph in enumerate(photos):
            x = margin + i * (cell_w + gap)
            self.set_draw_color(*BORDER)
            self.set_line_width(0.3)
            self.rect(x, y, cell_w, cell_h)
            if ph.get('path'):
                filepath = os.path.join(upload_folder, ph['path'])
                if os.path.exists(filepath):
                    self._place_image(filepath, x, y, cell_w, cell_h)
            self.set_xy(x, y + cell_h + 1)
            self.set_font(self._font(), 'B', 6.5)
            self.set_text_color(*GRAY_LABEL)
            self.cell(cell_w, 4, ph.get('label', ''), align='C')
            self.set_text_color(*INK)
        self.set_y(y + cell_h + 8)


class BBMReportPDF(BPFBasePDF):
    """Landscape multi-transaction recap PDF."""

    def __init__(self, title="REKAP DANA BBM"):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self.title), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def generate_table(self, data):
        if not data:
            self.set_font(self._font(), 'I', 12)
            self.cell(0, 10, "Tidak ada data", align="C")
            return
        headers = ['NO', 'TANGGAL', 'NO POLISI', 'DRIVER', 'AMOUNT', 'LITER', 'KM ISI BBM', 'KM/L', 'TIPE', 'HEALTH']
        widths = [8, 22, 22, 30, 24, 14, 20, 14, 14, 14]
        aligns = ['C', 'C', 'C', 'L', 'R', 'C', 'C', 'C', 'C', 'C']
        self._table_header(headers, widths)
        fill = False
        for idx, tx in enumerate(data, 1):
            health = 'N/A'
            try:
                kml = float(tx.get('km_per_liter', 0) or 0)
                if kml > 0:
                    health = str(min(100, int((kml / HEALTH_BENCHMARK) * 100)))
            except Exception:
                kml = 0
            tx_type = tx.get('transaction_type', 'CLAIM')
            self._table_row([
                idx,
                tx['created_at'].strftime('%d/%m/%y %H:%M') if tx.get('created_at') else '-',
                tx['nopol'],
                str(tx.get('driver_name', '-')).upper(),
                f"Rp {float(tx['nominal']):,.0f}" if tx.get('nominal') else 'Rp 0',
                f"{float(tx.get('liter', 0)):.1f}L",
                f"{int(tx.get('odo_km', 0)):,}",
                f"{kml:.1f}" if tx.get('km_per_liter') else '-',
                '💰 Kasbon' if tx_type == 'CASH_LPJ' else '-',
                health,
            ], widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(4)


# ============================================================
# RINGKASAN CABANG (v2.20.2) — multi-cabang
# Laporan statistik per cabang: transaksi, kunjungan hari ini, user
# ============================================================
class BranchSummaryPDF(BPFBasePDF):
    """Ringkasan per cabang untuk dashboard Admin (kop & logo resmi)."""

    def __init__(self, title='RINGKASAN CABANG'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, stats, generated_by=''):
        self.cell(0, 4.5, f'Periode: {date.today().isoformat()}', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        if not stats:
            self.set_font(self._font(), 'I', 10)
            self.cell(0, 8, 'Belum ada cabang terdaftar.', align='C', new_x='LMARGIN', new_y='NEXT')
        else:
            headers = ['KODE', 'NAMA CABANG', 'DATABASE', 'TRANSAKSI', 'KUNJUNGAN HARI INI', 'USER', 'STATUS']
            widths = [18, 62, 48, 24, 38, 18, 20]
            aligns = ['C', 'L', 'L', 'C', 'C', 'C', 'C']
            self._table_header(headers, widths)
            fill = False
            for b in stats:
                self._table_row([
                    b.get('code', '-'), b.get('name', '-'), b.get('db_name', '-'),
                    b.get('transactions', 0), b.get('appointments_today', 0), b.get('users', 0),
                    'Aktif' if b.get('is_active') else 'Nonaktif',
                ], widths, aligns=aligns, fill=fill)
                fill = not fill
        self.ln(4)
        self._signature_block(generated_by, 'Administrator', role='ADMIN')


# ============================================================
# LAPORAN KEHADIRAN PELAMAR KERJA (v2.16)
# Interview + Training Hari 1-4 — laporan resmi berlogo BPF
# ============================================================
class ApplicantReportPDF(BPFBasePDF):
    """Laporan kehadiran pelamar kerja (per tahap) dengan kop resmi & logo.

    Dipakai Receptionist: satu laporan per tahap (interview / training H1-H4)
    dalam rentang tanggal, opsional difilter upline/user — lalu TTD Receptionist.
    """

    def __init__(self, title='LAPORAN KEHADIRAN PELAMAR KERJA'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, rows, stage_label='', date_label='', filters=None, generated_by=''):
        self.add_page()  # halaman pertama (header/kop resmi otomatis via add_page)
        # Info laporan
        self.set_font(self._font(), 'B', 8)
        self.set_text_color(*INK)
        self.cell(0, 5, f'Tahap: {self.clean_text(stage_label or "-")}', new_x='LMARGIN', new_y='NEXT')
        self.cell(0, 5, f'Periode: {self.clean_text(date_label or "-")}', new_x='LMARGIN', new_y='NEXT')
        if filters:
            for k, v in filters.items():
                if v:
                    self.set_font(self._font(), '', 7)
                    self.set_text_color(*GRAY_LABEL)
                    self.cell(0, 4.5, f'{k}: {self.clean_text(str(v))}', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        self.set_text_color(*INK)

        self._draw_table(rows)

        # Ringkasan + TTD
        if self.get_y() + 40 > self.h - 25:
            self.add_page()
        self.ln(4)
        self.set_font(self._font(), '', 8)
        self.set_text_color(*INK_SOFT)
        self.cell(0, 5, f'Total pelamar pada laporan ini: {len(rows)} orang', new_x='LMARGIN', new_y='NEXT')
        self.ln(10)
        self._signature_block(generated_by, 'Receptionist', role='RECEPTIONIST')
        self.set_text_color(*INK)

    def _draw_table(self, rows):
        if not rows:
            self.set_font(self._font(), 'I', 10)
            self.cell(0, 8, 'Tidak ada data pada periode ini.', align='C', new_x='LMARGIN', new_y='NEXT')
            return
        headers = ['NO', 'NAMA LENGKAP', 'NO. HP', 'POSISI', 'UPLINE', 'USER', 'WAKTU KEHADIRAN']
        widths = [8, 55, 32, 40, 40, 32, 42]
        aligns = ['C', 'L', 'C', 'L', 'L', 'L', 'C']
        self._table_header(headers, widths)
        fill = False
        for idx, r in enumerate(rows, 1):
            at = r.get('attended_at')
            self._table_row([
                idx, r.get('nama_lengkap', '-'), r.get('no_hp', '-'), r.get('posisi', '-'),
                r.get('upline', '-'), r.get('user_field', '-'),
                at.strftime('%d-%m-%Y %H:%M') if hasattr(at, 'strftime') else (at or '-'),
            ], widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(3)


class AssetReportPDF(BPFBasePDF):
    """Laporan Aset & Pemeliharaan (v2.18) — AC kantor atau kendaraan.

    Dipakai GA/Admin: daftar aset + log servis terakhir per unit,
    kop & logo resmi BPF WorkHub.
    """

    def __init__(self, kind='ac'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._kind = kind
        self._title = 'LAPORAN ASET AC KANTOR' if kind == 'ac' else 'LAPORAN ASET KENDARAAN'
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, rows, generated_by=''):
        self.add_page()
        self.set_font(self._font(), '', 7)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4.5, f'Periode laporan: {self.clean_text(str(date.today().isoformat()))}', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        self.set_text_color(*INK)
        if not rows:
            self.set_font(self._font(), 'I', 10)
            self.cell(0, 8, 'Tidak ada data aset.', align='C', new_x='LMARGIN', new_y='NEXT')
        else:
            self._draw_assets(rows)
        # Ringkasan + TTD
        if self.get_y() + 40 > self.h - 25:
            self.add_page()
        self.ln(4)
        self.set_font(self._font(), '', 8)
        self.set_text_color(*INK_SOFT)
        self.cell(0, 5, f'Total aset pada laporan ini: {len(rows)} unit', new_x='LMARGIN', new_y='NEXT')
        self.ln(10)
        self._signature_block(generated_by, 'General Affairs (Pemeliharaan Aset)', role='GA')
        self.set_text_color(*INK)

    def _draw_assets(self, rows):
        if self._kind == 'ac':
            headers = ['NO', 'ASSET ID', 'MERK', 'TIPE', 'KAPASITAS', 'LOKASI',
                       'STATUS', 'SERVIS TERAKHIR', 'HEALTH', 'BIAYA SPAREPART']
            widths = [8, 45, 25, 25, 30, 50, 25, 32, 20, 32]
        else:
            headers = ['NO', 'NOPOL', 'TIPE', 'MERK', 'TAHUN', 'ODOMETER',
                       'STATUS', 'SERVIS TERAKHIR', 'KOMPONEN', 'BIAYA']
            widths = [8, 35, 30, 25, 20, 30, 25, 32, 40, 30]
        aligns = ['C'] + ['L'] * (len(widths) - 1)
        self._table_header(headers, widths)
        fill = False
        for idx, r in enumerate(rows, 1):
            if self._kind == 'ac':
                last = (r.get('logs') or [{}])[0]
                vals = [idx, r.get('asset_id', '-'), r.get('merk', '-'),
                        r.get('tipe', '-'), r.get('kapasitas', '-'), r.get('lokasi', '-'),
                        r.get('status', '-'), self._fmt_dt(last.get('tanggal')),
                        str(last.get('health_score', '-') if last.get('health_score') is not None else '-'),
                        self._fmt_money(last.get('sparepart_cost'))]
            else:
                last = (r.get('services') or [{}])[0]
                vals = [idx, r.get('nopol', '-'), r.get('vehicle_type', '-'),
                        r.get('brand', '-'), str(r.get('year', '-') or '-'),
                        str(r.get('last_odometer', 0) or 0), r.get('status', '-'),
                        self._fmt_dt(last.get('service_date')),
                        last.get('component_name', '-'), self._fmt_money(last.get('cost'))]
            self._table_row(vals, widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(3)



# ============================================================
# LAPORAN KONSOLIDASI LINTAS CABANG (v2.21)
# Agregasi semua DB cabang + master dalam satu dokumen resmi
# ============================================================
class ConsolidatedReportPDF(BPFBasePDF):
    """Konsolidasi statistik & transaksi terbaru dari SEMUA cabang.

    Berguna untuk HQ/multi-cabang: satu PDF berisi ringkasan per cabang
    (transaksi, kunjungan, user, nominal BBM) + baris transaksi terbaru
    dari tiap DB cabang — kop surat & identitas mengikuti cabang aktif.
    """

    def __init__(self, title='LAPORAN KONSOLIDASI CABANG'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, branches, latest_by_branch, generated_by=''):
        """branches: hasil branch_stats(); latest_by_branch: {code: [tx...]}."""
        self.cell(0, 4.5, f'Periode: {date.today().isoformat()}', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        self._draw_summary(branches)
        self._draw_latest(latest_by_branch)
        self._signature_block(generated_by, 'Administrator', role='ADMIN')

    def _draw_summary(self, branches):
        self.section_title('RINGKASAN PER CABANG')
        if not branches:
            self.set_font(self._font(), 'I', 10)
            self.cell(0, 8, 'Belum ada cabang terdaftar.', align='C', new_x='LMARGIN', new_y='NEXT')
            return
        headers = ['KODE', 'CABANG', 'TRANSAKSI', 'KUNJUNGAN HARI INI', 'USER', 'STATUS']
        widths = [16, 70, 26, 40, 20, 22]
        aligns = ['C', 'L', 'C', 'C', 'C', 'C']
        self._table_header(headers, widths)
        fill = False
        for b in branches:
            self._table_row([
                b.get('code', '-'), b.get('name', '-'), b.get('transactions', 0),
                b.get('appointments_today', 0), b.get('users', 0),
                'Aktif' if b.get('is_active') else 'Nonaktif',
            ], widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(3)

    def _draw_latest(self, latest_by_branch):
        self.section_title('TRANSAKSI BBM TERBARU (maks. 5 per cabang)')
        headers = ['CABANG', 'ID', 'DRIVER', 'NOPOL', 'BBM', 'NOMINAL', 'LITER', 'TANGGAL']
        widths = [16, 30, 34, 22, 18, 28, 14, 34]
        aligns = ['C', 'C', 'L', 'C', 'C', 'R', 'C', 'C']
        self._table_header(headers, widths)
        fill = False
        any_row = False
        for code, txs in (latest_by_branch or {}).items():
            for t in (txs or [])[:5]:
                any_row = True
                self._table_row([
                    code, t.get('display_id', '-'), t.get('driver_name', '-'),
                    t.get('nopol', '-'), t.get('bbm_type', '-'),
                    self._fmt_money(t.get('nominal')),
                    f"{float(t.get('liter', 0)):.1f}L",
                    t.get('created_at', '').strftime('%d-%m-%Y %H:%M') if hasattr(t.get('created_at'), 'strftime') else t.get('created_at', '-'),
                ], widths, aligns=aligns, fill=fill)
                fill = not fill
        if not any_row:
            self.set_font(self._font(), 'I', 9)
            self.cell(0, 8, 'Belum ada transaksi BBM terarsip.', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)


class OvertimeReportPDF(BPFBasePDF):
    """Laporan Overtime (v2.22) — GA HR: Driver atau OB/Security.

    Satu laporan resmi berlogo BPF untuk satu modul (driver / ob_security)
    dalam rentang tanggal, opsional difilter posisi/nama — TTD GA HR.
    """

    def __init__(self, title='LAPORAN OVERTIME'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 11)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, rows, modul='driver', date_label='', filters=None, generated_by=''):
        """rows: dict rows dari tabel overtime_driver / overtime_ob_security."""
        self.add_page()
        modul_label = 'Overtime DRIVER' if modul == 'driver' else 'Overtime OB & SECURITY'
        self.set_font(self._font(), 'B', 8)
        self.set_text_color(*INK)
        self.cell(0, 5, f'Modul: {modul_label}', new_x='LMARGIN', new_y='NEXT')
        self.cell(0, 5, f'Periode: {self.clean_text(date_label or "-")}', new_x='LMARGIN', new_y='NEXT')
        if filters:
            for k, v in filters.items():
                if v:
                    self.set_font(self._font(), '', 7)
                    self.set_text_color(*GRAY_LABEL)
                    self.cell(0, 4.5, f'{k}: {self.clean_text(str(v))}', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        self.set_text_color(*INK)

        if modul == 'driver':
            self._draw_driver(rows)
        else:
            self._draw_ob_security(rows)

        if self.get_y() + 40 > self.h - 25:
            self.add_page()
        self.ln(4)
        self.set_font(self._font(), '', 8)
        self.set_text_color(*INK_SOFT)
        self.cell(0, 5, f'Total catatan pada laporan ini: {len(rows)}', new_x='LMARGIN', new_y='NEXT')
        self.ln(10)
        self._signature_block(generated_by, 'General Affairs HR', role='GA HR')
        self.set_text_color(*INK)

    def _draw_driver(self, rows):
        headers = ['NO', 'TANGGAL', 'NAMA', 'NO. KENDARAAN', 'WAKTU', 'KETERANGAN', 'SUMBER']
        # WAKTU 34→42 agar '18:30 – 20:00' tidak terpotong (ambil dari KETERANGAN)
        widths = [8, 24, 45, 30, 42, 92, 25]
        aligns = ['C', 'C', 'L', 'C', 'C', 'L', 'C']
        self._table_header(headers, widths)
        fill = False
        for idx, r in enumerate(rows, 1):
            source_label = 'Sheet' if r.get('source') == 'sheet' else 'Aplikasi'
            self._table_row([
                idx, self._fmt_dt(r.get('tanggal')), r.get('nama', '-'),
                r.get('no_kendaraan', '-'), self._waktu(r),
                r.get('keterangan', '-'), source_label,
            ], widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(3)

    def _draw_ob_security(self, rows):
        headers = ['NO', 'TANGGAL', 'NAMA', 'POSISI', 'WAKTU', 'KETERANGAN', 'SUMBER']
        # WAKTU 36→46 agar '18:30 – 20:00' tidak terpotong (ambil dari KETERANGAN)
        widths = [8, 26, 50, 28, 46, 90, 28]
        aligns = ['C', 'C', 'L', 'C', 'C', 'L', 'C']
        self._table_header(headers, widths)
        fill = False
        for idx, r in enumerate(rows, 1):
            source_label = 'Sheet' if r.get('source') == 'sheet' else 'Aplikasi'
            self._table_row([
                idx, self._fmt_dt(r.get('tanggal')), r.get('nama', '-'),
                r.get('posisi', '-'), self._waktu(r), r.get('keterangan', '-'),
                source_label,
            ], widths, aligns=aligns, fill=fill)
            fill = not fill
        self.ln(3)

    def _waktu(self, r):
        a = r.get('waktu_mulai') or '-'
        b = r.get('waktu_selesai') or ''
        # Pakai tanda hubung ASCII: clean_text() menghapus non-ASCII (en dash
        # '–' hilang dari output PDF).
        return f'{a} - {b}' if b else a


class OvertimeDetailReportPDF(BPFBasePDF):
    """Report Detail Overtime per Driver — format File 2.

    Landscape A4 — semua kolom lebar & profesional.
    Satu halaman per driver, berisi:
    - Info: Nama, Jabatan, Periode
    - Tabel: No, Timestamp, No. Form, Nama, Plat, Tanggal, Jam Mulai, Jam Selesai,
             Keterangan, Lokasi, Biaya
    - Biaya kolom kosong (untuk diisi GA HR)
    """

    def __init__(self, title='LAPORAN OVERTIME'):
        super().__init__(orientation='L', unit='mm', format='A4')
        self._title = title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        super().header()
        self.set_font(self._font(), 'B', 13)
        self.set_text_color(*INK)
        self.cell(0, 7, self.clean_text(self._title), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def generate(self, rows, driver_name='', driver_role='DRIVER', date_label='', generated_by='', modul='driver'):
        """rows: list of overtime records for ONE driver/OB.
        Landscape A4: 297mm - 2*15mm margin = 267mm usable.
        modul: 'driver' or 'ob' — affects column layout (Plat vs Posisi).
        """
        self.add_page()

        # Driver info block — 3 kolom sejajar
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        col_w = 80
        x0 = self.l_margin
        # Baris 1: NAMA + JABATAN
        self.set_xy(x0, self.get_y())
        self.cell(20, 6, 'NAMA :', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 9)
        self.cell(col_w - 20, 6, self.clean_text(driver_name), new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), 'B', 9)
        self.cell(22, 6, 'JABATAN :', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 9)
        self.cell(col_w - 22, 6, self.clean_text(driver_role), new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), 'B', 9)
        self.cell(22, 6, 'PERIODE :', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 9)
        self.cell(0, 6, self.clean_text(date_label), new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

        # Table — Landscape widths (total = 267mm)
        if modul == 'ob':
            # OB/Security: ganti PLAT KENDARAAN → POSISI
            headers = ['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'POSISI', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA']
            # NO. FORM 20→26 (id OTL-SH-… panjang); ambil dari KETERANGAN 45→39
            widths = [8, 32, 26, 35, 22, 22, 18, 18, 39, 30, 17]
            aligns = ['C', 'C', 'C', 'L', 'C', 'C', 'C', 'C', 'L', 'L', 'R']
        else:
            headers = ['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'PLAT KENDARAAN', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA']
            widths = [8, 32, 26, 32, 22, 22, 18, 18, 39, 30, 20]
            aligns = ['C', 'C', 'C', 'L', 'C', 'C', 'C', 'C', 'L', 'L', 'R']

        self._table_header(headers, widths, font_size=7, row_h=8)
        fill = False
        for idx, r in enumerate(rows, 1):
            timestamp = ''
            if r.get('submitted_at'):
                try:
                    dt = r['submitted_at'] if isinstance(r['submitted_at'], datetime) else datetime.strptime(str(r['submitted_at']), '%Y-%m-%d %H:%M:%S')
                    timestamp = dt.strftime('%d/%m/%Y %H:%M')
                except Exception:
                    timestamp = str(r['submitted_at'])[:16]

            tanggal_ot = ''
            if r.get('tanggal'):
                try:
                    if isinstance(r['tanggal'], date):
                        tanggal_ot = r['tanggal'].strftime('%d/%m/%Y')
                    else:
                        tanggal_ot = str(r['tanggal'])
                except Exception:
                    tanggal_ot = str(r['tanggal'])

            # Lokasi dari GPS detail
            lokasi_parts = []
            for field in ('gps_kelurahan', 'gps_kecamatan', 'gps_kota'):
                val = r.get(field, '')
                if val and val != '-':
                    lokasi_parts.append(str(val))
            lokasi = ', '.join(lokasi_parts) if lokasi_parts else (r.get('gps_address', '') or '-')
            if len(lokasi) > 40:
                lokasi = lokasi[:37] + '...'

            col5 = r.get('posisi', '-') if modul == 'ob' else r.get('no_kendaraan', '-')
            self._table_row([
                str(idx),
                timestamp,
                r.get('display_id', '-'),
                r.get('nama', '-'),
                col5,
                tanggal_ot,
                r.get('waktu_mulai', '-'),
                r.get('waktu_selesai', '-'),
                r.get('keterangan', '-'),
                lokasi,
                '',  # Biaya — kosong untuk diisi GA HR
            ], widths, aligns=aligns, fill=fill)
            fill = not fill

        self.ln(3)
        self.set_font(self._font(), '', 7)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4, '* Kolom Biaya diisi oleh GA HR setelah verifikasi', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)
        self.set_text_color(*INK)
        self.set_font(self._font(), '', 8)
        self.cell(0, 5, f'Total catatan: {len(rows)}', new_x='LMARGIN', new_y='NEXT')
        self.ln(8)
        self._signature_block(generated_by, 'General Affairs HR', role='GA HR')
        self.set_text_color(*INK)


def generate_overtime_detail_excel(rows, driver_name='', driver_role='DRIVER', date_label='', modul='driver'):
    """Generate Excel (.xlsx) for overtime detail report.
    Landscape-style: 11 kolom.
    modul: 'driver' (Plat) or 'ob' (Posisi).
    Biaya column is empty for GA HR to fill in."""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
    except ImportError:
        # Fallback: simple CSV
        return _generate_overtime_detail_csv(rows, driver_name, driver_role, date_label)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'OT {driver_name[:20]}'

    # Landscape orientation
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    # Styles
    header_font = Font(name='Calibri', bold=True, size=10)
    title_font = Font(name='Calibri', bold=True, size=13)
    normal_font = Font(name='Calibri', size=10)
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    header_font_white = Font(name='Calibri', bold=True, size=10, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)
    right_align = Alignment(horizontal='right', vertical='center')
    rupiah_format = '#,##0'

    # Title
    ws.merge_cells('A1:K1')
    ws['A1'] = f'OVERTIME PERIODE {date_label}'
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    # Driver info — sejajar
    ws['A3'] = 'NAMA :'
    ws['A3'].font = header_font
    ws['B3'] = driver_name
    ws['B3'].font = normal_font

    ws['D3'] = 'JABATAN :'
    ws['D3'].font = header_font
    ws['E3'] = driver_role
    ws['E3'].font = normal_font

    ws['G3'] = 'PERIODE :'
    ws['G3'].font = header_font
    ws['H3'] = date_label
    ws['H3'].font = normal_font

    # Headers
    if modul == 'ob':
        headers = ['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'POSISI', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA']
    else:
        headers = ['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'PLAT KENDARAAN', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = center_align

    # Data rows
    for idx, r in enumerate(rows):
        row_num = idx + 6
        timestamp = ''
        if r.get('submitted_at'):
            try:
                dt = r['submitted_at'] if isinstance(r['submitted_at'], datetime) else datetime.strptime(str(r['submitted_at']), '%Y-%m-%d %H:%M:%S')
                timestamp = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                timestamp = str(r['submitted_at'])[:16]

        tanggal_ot = ''
        if r.get('tanggal'):
            try:
                if isinstance(r['tanggal'], date):
                    tanggal_ot = r['tanggal'].strftime('%d/%m/%Y')
                else:
                    tanggal_ot = str(r['tanggal'])
            except Exception:
                tanggal_ot = str(r['tanggal'])

        # Lokasi dari GPS detail
        lokasi_parts = []
        for field in ('gps_kelurahan', 'gps_kecamatan', 'gps_kota'):
            val = r.get(field, '')
            if val and val != '-':
                lokasi_parts.append(str(val))
        lokasi = ', '.join(lokasi_parts) if lokasi_parts else (r.get('gps_address', '') or '-')

        col5_val = r.get('posisi', '-') if modul == 'ob' else r.get('no_kendaraan', '-')
        data = [
            idx + 1,
            timestamp,
            r.get('display_id', '-'),
            r.get('nama', '-'),
            col5_val,
            tanggal_ot,
            r.get('waktu_mulai', '-'),
            r.get('waktu_selesai', '-'),
            r.get('keterangan', '-'),
            lokasi,
            None,  # Biaya — kosong
        ]
        for col, val in enumerate(data, 1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.font = normal_font
            cell.border = thin_border
            if col in (1, 6, 7, 8):  # No, TglOT, JamMulai, JamSelesai
                cell.alignment = center_align
            elif col in (9, 10):  # Keterangan, Lokasi
                cell.alignment = left_align
            elif col == 11:  # Biaya
                cell.alignment = right_align
                if val is not None:
                    cell.number_format = rupiah_format
            else:
                cell.alignment = center_align

    # Column widths — landscape (A-K)
    col_widths = {'A': 5, 'B': 22, 'C': 14, 'D': 22, 'E': 16, 'F': 16, 'G': 12, 'H': 12, 'I': 28, 'J': 28, 'K': 14}
    for col_letter, w in col_widths.items():
        ws.column_dimensions[col_letter].width = w

    # Footer note
    footer_row = len(rows) + 7
    ws.cell(row=footer_row, column=1, value='* Kolom Biaya diisi oleh GA HR setelah verifikasi').font = Font(name='Calibri', italic=True, size=9, color='888888')
    ws.cell(row=footer_row + 1, column=1, value=f'Total catatan: {len(rows)}').font = normal_font

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _generate_overtime_detail_csv(rows, driver_name='', driver_role='DRIVER', date_label='', modul='driver'):
    """Fallback CSV export if openpyxl not available."""
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f'OVERTIME PERIODE {date_label}'])
    writer.writerow([f'NAMA: {driver_name}', f'JABATAN: {driver_role}'])
    writer.writerow([])
    if modul == 'ob':
        writer.writerow(['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'POSISI', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA'])
    else:
        writer.writerow(['NO', 'TANGGAL TIMESTAMP', 'NO. FORM', 'NAMA', 'PLAT KENDARAAN', 'TANGGAL OVERTIME', 'JAM MULAI', 'JAM SELESAI', 'KETERANGAN', 'LOKASI', 'BIAYA'])
    for idx, r in enumerate(rows, 1):
        timestamp = ''
        if r.get('submitted_at'):
            try:
                dt = r['submitted_at'] if isinstance(r['submitted_at'], datetime) else datetime.strptime(str(r['submitted_at']), '%Y-%m-%d %H:%M:%S')
                timestamp = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                timestamp = str(r['submitted_at'])[:16]
        # Lokasi dari GPS detail
        lokasi_parts = []
        for field in ('gps_kelurahan', 'gps_kecamatan', 'gps_kota'):
            val = r.get(field, '')
            if val and val != '-':
                lokasi_parts.append(str(val))
        lokasi = ', '.join(lokasi_parts) if lokasi_parts else (r.get('gps_address', '') or '-')
        col5 = r.get('posisi', '-') if modul == 'ob' else r.get('no_kendaraan', '-')
        writer.writerow([
            idx, timestamp, r.get('display_id', '-'), r.get('nama', '-'),
            col5, str(r.get('tanggal', '-')),
            r.get('waktu_mulai', '-'), r.get('waktu_selesai', '-'),
            r.get('keterangan', '-'), lokasi, '',  # Biaya kosong
        ])
    buf = io.BytesIO()
    buf.write(output.getvalue().encode('utf-8-sig'))
    buf.seek(0)
    return buf


class OvertimeFormPDF(BPFBasePDF):
    """Formulir Permohonan Overtime — dicetak oleh GA HR.

    Mendukung modul driver dan ob/security (parameter modul).
    Format: Portrait A4
    Isi: ID Form, Email, Nama, Detail OT (Tanggal, Jam S/D, Keterangan),
          H+1 (bila OT lewat tengah malam), Kolom Rupiah,
          Blok TTD, Link Foto, Footer ISO 27001.
    """

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)

    def _calc_h1(self, row):
        """Hitung durasi H+1 (jam lewat tengah malam) dari waktu_selesai.
        Bila waktu_selesai < waktu_mulai → OT lewat tengah malam.
        H+1 dihitung dari jam 00:00 s/d waktu_selesai.
        """
        mulai = row.get('waktu_mulai', '')
        selesai = row.get('waktu_selesai', '')
        if not mulai or not selesai:
            return None
        try:
            # Parse HH:MM atau HH:MM:SS
            m_parts = str(mulai).split(':')
            s_parts = str(selesai).split(':')
            m_h, m_m = int(m_parts[0]), int(m_parts[1])
            s_h, s_s = int(s_parts[0]), int(s_parts[1])
            m_min = m_h * 60 + m_m
            s_min = s_h * 60 + s_s
            if s_min < m_min:
                # Lewat tengah malam — H+1 dari 00:00 s/d waktu_selesai
                h1_menit = s_min  # jam dari 00:00
                return round(h1_menit / 60, 2)
            return None  # Tidak lewat tengah malam
        except (ValueError, IndexError):
            return None

    def generate(self, row, photos=None, modul='driver'):
        """row: dict dari tabel overtime_driver / overtime_ob_security.
        photos: dict { 'foto_mulai': url, 'foto_selesai': url }
        modul: 'driver' atau 'ob'
        """
        is_driver = (modul == 'driver')
        self.add_page()

        # Header: ID Form + Email
        self.set_font(self._font(), '', 9)
        self.set_text_color(*INK)
        display_id = row.get('display_id', '-')
        email = row.get('email', '-')
        self.cell(0, 5, f'ID FORM : {display_id} , USED EMAIL : {email}', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

        # Title
        self.set_font(self._font(), 'B', 13)
        if is_driver:
            self.cell(0, 8, 'FORMULIR PERMOHONAN OVERTIME – DRIVER', align='C', new_x='LMARGIN', new_y='NEXT')
        else:
            posisi = row.get('posisi', '-')
            self.cell(0, 8, f'FORMULIR PERMOHONAN OVERTIME – {posisi.upper()}', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

        # Info nama
        self.set_font(self._font(), 'B', 10)
        label_nama = 'NAMA PENGEMUDI' if is_driver else 'NAMA KARYAWAN'
        self.cell(45, 6, label_nama, new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        self.cell(0, 6, f': {self.clean_text(row.get("nama", "-"))}', new_x='LMARGIN', new_y='NEXT')

        if is_driver:
            self.set_font(self._font(), 'B', 10)
            self.cell(45, 6, 'NO KENDARAAN', new_x='RIGHT', new_y='TOP')
            self.set_font(self._font(), '', 10)
            self.cell(0, 6, f': {self.clean_text(row.get("no_kendaraan", "-"))}', new_x='LMARGIN', new_y='NEXT')
        else:
            self.set_font(self._font(), 'B', 10)
            self.cell(45, 6, 'POSISI', new_x='RIGHT', new_y='TOP')
            self.set_font(self._font(), '', 10)
            self.cell(0, 6, f': {self.clean_text(row.get("posisi", "-"))}', new_x='LMARGIN', new_y='NEXT')

        self.set_font(self._font(), 'B', 10)
        self.cell(45, 6, 'TANGGAL FORM', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        submitted = ''
        if row.get('submitted_at'):
            try:
                dt = row['submitted_at'] if isinstance(row['submitted_at'], datetime) else datetime.strptime(str(row['submitted_at']), '%Y-%m-%d %H:%M:%S')
                submitted = dt.strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                submitted = str(row['submitted_at'])[:19]
        elif row.get('created_at'):
            try:
                dt = row['created_at'] if isinstance(row['created_at'], datetime) else datetime.strptime(str(row['created_at']), '%Y-%m-%d %H:%M:%S')
                submitted = dt.strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                submitted = str(row['created_at'])[:19]
        self.cell(0, 6, f': {submitted}', new_x='LMARGIN', new_y='NEXT')
        self.ln(6)

        # Detail Overtime
        self.set_font(self._font(), 'B', 10)
        self.cell(35, 6, 'TANGGAL', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        tanggal = ''
        if row.get('tanggal'):
            try:
                if isinstance(row['tanggal'], date):
                    tanggal = row['tanggal'].strftime('%d/%m/%Y')
                else:
                    tanggal = str(row['tanggal'])
            except Exception:
                tanggal = str(row['tanggal'])
        self.cell(0, 6, f': {tanggal}', new_x='LMARGIN', new_y='NEXT')

        self.set_font(self._font(), 'B', 10)
        self.cell(35, 6, 'OVERTIME', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        waktu = f'{row.get("waktu_mulai", "-")} S/D {row.get("waktu_selesai", "-")}'
        self.cell(0, 6, f': {waktu}', new_x='LMARGIN', new_y='NEXT')

        # H+1 — bila OT lewat tengah malam
        h1 = self._calc_h1(row)
        if h1 is not None and h1 > 0:
            self.set_font(self._font(), 'B', 10)
            self.set_text_color(180, 30, 30)
            self.cell(35, 6, 'H+1', new_x='RIGHT', new_y='TOP')
            self.set_font(self._font(), '', 10)
            # Maksimal H+1 dihitung dari jam terakhir selesai OT
            h1_jam = int(h1)
            h1_menit = round((h1 - h1_jam) * 60)
            h1_str = f'{h1_jam} jam {h1_menit} menit (maksimal s/d {row.get("waktu_selesai", "-")})'
            self.cell(0, 6, f': {h1_str}', new_x='LMARGIN', new_y='NEXT')
            self.set_text_color(*INK)

        if is_driver:
            self.set_font(self._font(), 'B', 10)
            self.cell(35, 6, 'NAMA BROKER', new_x='RIGHT', new_y='TOP')
            self.set_font(self._font(), '', 10)
            self.cell(0, 6, f': {self.clean_text(row.get("broker", "-"))}', new_x='LMARGIN', new_y='NEXT')

            self.set_font(self._font(), 'B', 10)
            self.cell(35, 6, 'NAMA MANAGER', new_x='RIGHT', new_y='TOP')
            self.set_font(self._font(), '', 10)
            self.cell(0, 6, f': {self.clean_text(row.get("manager", "-"))}', new_x='LMARGIN', new_y='NEXT')

        self.set_font(self._font(), 'B', 10)
        self.cell(35, 6, 'KETERANGAN', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        self.cell(0, 6, f': {self.clean_text(row.get("keterangan", "-"))}', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

        # Kolom Rupiah
        self.set_font(self._font(), 'B', 10)
        self.cell(35, 6, 'RUPIAH', new_x='RIGHT', new_y='TOP')
        self.set_font(self._font(), '', 10)
        self.cell(0, 6, ': ', new_x='LMARGIN', new_y='NEXT')
        self.ln(8)

        # Blok TTD
        self._signature_blocks()
        self.ln(6)

        # Foto links
        self._photo_links(row, photos)
        self.ln(6)

        # Footer
        self.set_font(self._font(), 'I', 7)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4, 'PENTING: Dokumen ini wajib disimpan dan dipelihara kerahasiaannya sesuai dengan Standar ISO 27001:2022', align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*INK)

    def _signature_blocks(self):
        """Blok TTD: Manager, Finance, GA HR, Chief Driver, Kepala Cabang."""
        labels = ['MANAGER', 'FINANCE', 'GA HR', 'Checked Chief Driver', 'KEPALA CABANG']
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        self.cell(0, 5, 'TANDA TANGAN', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

        col_w = 170 / len(labels)
        for label in labels:
            self.set_font(self._font(), '', 8)
            self.cell(col_w, 5, label, align='C', new_x='RIGHT', new_y='TOP')
        self.ln(12)
        # Garis tanda tangan
        x_start = self.l_margin
        for i, label in enumerate(labels):
            self.set_draw_color(*INK)
            self.line(x_start + i * col_w + 5, self.get_y(), x_start + (i + 1) * col_w - 5, self.get_y())
        self.ln(2)

    # Max dimensi foto tersemat di Form PDF (mm)
    _PHOTO_MAX_W = 170
    _PHOTO_MAX_H = 60

    def _photo_links(self, row, photos=None):
        """Lampiran foto: disematkan sebagai GAMBAR bila tersedia (file lokal
        /uploads/... atau URL http publik), fallback tautan klik bila gagal.
        Otomatis pindah halaman bila ruang tidak cukup."""
        photos = photos or {}
        foto_tujuan = photos.get('foto_selesai') or row.get('foto_selesai', '')
        foto_selfie = photos.get('foto_mulai') or row.get('foto_mulai', '')
        for label, ref in (('FOTO DI TUJUAN', foto_tujuan),
                           ('FOTO SELFIE @OFFICE', foto_selfie)):
            self._photo_block(label, ref)
        self.ln(2)

    def _photo_block(self, label, ref):
        ref = str(ref or '').strip()
        if not ref:
            self.set_font(self._font(), 'B', 9)
            self.set_text_color(*INK)
            self.cell(0, 5, f'{label}: Tidak tersedia', new_x='LMARGIN', new_y='NEXT')
            self.ln(2)
            return
        img = self._load_photo_image(ref)
        needed = 8 + (img[1] if img else 4) + 6
        if self.get_y() + needed > self.h - 15:
            self.add_page()
        self.set_font(self._font(), 'B', 9)
        self.set_text_color(*INK)
        self.cell(0, 5, label, new_x='LMARGIN', new_y='NEXT')
        if img is None:
            self.set_font(self._font(), '', 8)
            self.set_text_color(0, 102, 204)
            self.cell(0, 5, f'Klik untuk lihat foto: {ref}', link=ref, new_x='LMARGIN', new_y='NEXT')
            self.set_text_color(*INK)
            self.ln(3)
            return
        buf, w_mm, h_mm = img
        x = self.l_margin + (self.w - self.l_margin - self.r_margin - w_mm) / 2
        self.image(buf, x=x, y=self.get_y(), w=w_mm, h=h_mm)
        self.set_y(self.get_y() + h_mm)
        self.ln(1)
        self.set_font(self._font(), 'I', 6)
        self.set_text_color(0, 102, 204)
        self.cell(0, 4, f'Sumber foto: {ref}', align='C', link=ref, new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*INK)
        self.ln(3)

    @staticmethod
    def _load_photo_image(ref):
        """Ambil gambar foto → (BytesIO JPEG, w_mm, h_mm) atau None bila gagal.

        Mendukung file lokal (`/uploads/...` = jalur relatif root project) dan
        URL http(s) publik (mis. tautan Google Drive). Ukuran dibatasi & format
        divalidasi via PIL; kesalahan apa pun → None (caller fallback link).
        """
        try:
            data = None
            if ref.startswith('/') and not ref.startswith('//'):
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                path = os.path.join(base, ref.lstrip('/'))
                if not os.path.exists(path):
                    return None
                with open(path, 'rb') as f:
                    data = f.read()
            elif ref.startswith('http://') or ref.startswith('https://'):
                import requests as _requests
                resp = _requests.get(ref, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code != 200:
                    return None
                ctype = (resp.headers.get('Content-Type') or '').lower()
                if 'image' not in ctype:
                    return None
                data = resp.content
            else:
                return None
            if not data or len(data) > 8 * 1024 * 1024:
                return None
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            w_px, h_px = img.size
            if w_px <= 0 or h_px <= 0:
                return None
            ratio = min(OvertimeFormPDF._PHOTO_MAX_W / w_px,
                        OvertimeFormPDF._PHOTO_MAX_H / h_px)
            w_mm, h_mm = w_px * ratio, h_px * ratio
            if img.width > MAX_IMAGE_WIDTH:
                r = MAX_IMAGE_WIDTH / img.width
                img = img.resize((MAX_IMAGE_WIDTH, int(img.height * r)), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
            buf.seek(0)
            return (buf, w_mm, h_mm)
        except Exception:
            return None
