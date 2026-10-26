"""Unit Tests — BBMReportPDF v2.72.0 (restorasi fitur multifill engine).

Latar: perombakan template rekap dulu menenggelamkan hasil deteksi multifill
(km_awal/km_akhir/total_km/rata_rata/is_multifill) dari get_rekap_data, dan
emoji 💰 kolom TIPE diam-diam dilucuti bersih oleh clean_text sehingga TIPE
hambar. v2.72.0 menghidupkannya kembali + STATUS DITOLAK tegas (kewenangan
reject Finance adalah fitur sah, bukan data sampah).

Teknik: spy instance-level pada _table_row/_table_header sehingga asersi
dilakukan di data Python yang diteruskan renderer — bukan byte mentah PDF
(stream TTF di-encode jadi glyph hex, tidak bisa dipindai teks).

Jalankan:
    python3 -m pytest tests/test_pdf_rekap_bbm.py -v
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.pdf_generator import BBMReportPDF, PDFReportCompact


def _row(**over):
    base = {
        'created_at': datetime.datetime(2026, 10, 26, 9, 0),
        'nopol': 'B 1234 XYZ', 'driver_name': 'budi',
        'nominal': 150000, 'liter': 20.0,
        'km_per_liter': 9.5, 'odo_km': 43200,
        'transaction_type': 'CLAIM', 'status': 'archived',
    }
    base.update(over)
    return base


def _render(rows):
    """Render rekap; kembalikan (headers, rows) persis seperti dipakai renderer."""
    capture = {'headers': None, 'rows': [], 'colors': []}

    class SpyPDF(BBMReportPDF):
        def _table_header(self, headers, widths, font_size=7, row_h=7):
            capture['headers'] = [str(h) for h in headers]
            return super()._table_header(headers, widths, font_size=font_size, row_h=row_h)

        def _table_row(self, values, widths, aligns=None, row_h=6, fill=False, colors=None):
            capture['rows'].append([str(v) for v in values])
            capture['colors'].append(list(colors) if colors else [])
            return super()._table_row(values, widths, aligns=aligns, row_h=row_h, fill=fill, colors=colors)

    pdf = SpyPDF(title='REKAP DANA BBM - UNIT TEST')
    pdf.add_page()
    pdf.generate_table(rows)
    return capture


class TestGenerateTableV2720:
    def test_header_kolom_multifill_hadir(self):
        """Header memuat KM ISI/AKHIR/JARAK/M-FILL/STATUS — fitur engine tampil."""
        cap = _render([_row()])
        assert cap['headers'] == [
            'NO', 'TANGGAL', 'NO POLISI', 'DRIVER', 'STATUS',
            'AMOUNT', 'LITER', 'KM ISI', 'KM AKHIR', 'JARAK KM',
            'KM/L', 'M-FILL', 'TIPE', 'HEALTH',
        ]

    def test_multifill_menggunakan_hasil_engine(self):
        """Baris engine (km_awal/km_akhir/total_km/rata_rata) terlihat di sel."""
        cap = _render([_row(km_awal=43000, km_akhir=43200, total_km=200,
                            rata_rata=10.0, is_multifill=False)])
        row = cap['rows'][0]
        assert row[7] == '43,000', f'KM ISI: {row[7]!r}'
        assert row[8] == '43,200', f'KM AKHIR: {row[8]!r}'
        assert row[9] == '200', f'JARAK: {row[9]!r}'
        assert row[10] == '10.0', f'KM/L rata_rata: {row[10]!r}'
        assert row[11] == '-', 'baris normal tak boleh mark M-FILL'
        assert 'YA' not in row

    def test_marker_multifill_ya(self):
        """Pengisian beruntun (dist < threshold) ditandai M-FILL = YA + warna."""
        cap = _render([_row(km_awal=43150, km_akhir=43200, total_km=30,
                            rata_rata=0.0, is_multifill=True)])
        row = cap['rows'][0]
        assert row[11] == 'YA', f'M-FILL: {row[11]!r}'
        colors = cap['colors'][0]
        assert colors[11] == (180, 83, 9), f'warna amber marker: {colors[11]!r}'

    def test_km_l_multifill_dicoret_rata_rata_nol(self):
        """Baris multifill punya rata_rata=0 → KM/L '-' (dikumulatif ke isi lama)."""
        cap = _render([_row(km_awal=43200, km_akhir=43225, total_km=25,
                            rata_rata=0.0, is_multifill=True)])
        assert cap['rows'][0][10] == '-'

    def test_status_ditolak_tampil_berwarna(self):
        """Klaim rejected tetap tampil dengan label DITOLAK merah — bukan dihapus."""
        cap = _render([_row(status='rejected'), _row(status='archived')])
        rows, colors = cap['rows'], cap['colors']
        assert rows[0][4] == 'DITOLAK', f'status rejected: {rows[0][4]!r}'
        assert rows[1][4] == 'ARSIP'
        assert colors[0][4] == (185, 28, 28), f'warna DITOLAK: {colors[0][4]!r}'

    def test_status_mapping_lengkap(self):
        for status, label in [('pending', 'PENDING'), ('verified', 'VERIF'),
                              ('verified_ga', 'VERIF GA'), ('os_finance', 'OS FINANCE'),
                              ('archived', 'ARSIP'), ('rejected', 'DITOLAK'),
                              ('aneh', '-')]:
            cap = _render([_row(status=status)])
            assert cap['rows'][0][4] == label, f'{status} → {cap["rows"][0][4]!r}'

    def test_tipe_teks_polos_tanpa_emoji(self):
        """TIPE harus teks KASBON/KLAIM polos — emoji 💰 tidak pernah ter-render."""
        cap = _render([
            _row(transaction_type='CASH_LPJ'),
            _row(),
        ])
        rows = cap['rows']
        assert rows[0][12] == 'KASBON', f'{rows[0][12]!r}'
        assert rows[1][12] == 'KLAIM', f'{rows[1][12]!r}'
        for row in rows:
            assert not any('💰' in sel or '\u26fd' in sel for sel in row), 'emoji bocor'
        # dan byte stream PDF bersih dari emoji (utf-8 💰 == f0 9f 92 b0)
        pdf = BBMReportPDF(title='X')
        pdf.add_page()
        pdf.generate_table([_row(transaction_type='CASH_LPJ')])
        raw = pdf.output(dest='R')
        raw = bytes(raw) if not isinstance(raw, str) else raw.encode('latin-1')
        assert b'\xf0\x9f\x92\xb0' not in raw

    def test_row_mentah_fallback_jalan(self):
        """Baris tanpa hasil engine fallback ke km_per_liter/ODO, tidak crash."""
        cap = _render([_row()])
        row = cap['rows'][0]
        assert row[7] == '43,200' and row[8] == '43,200', f'{row[7]!r}/{row[8]!r}'
        assert row[9] == '0', f'JARAK fallback: {row[9]!r}'
        assert row[10] == '9.5', f'fallback km_per_liter: {row[10]!r}'
        assert row[11] == '-', 'fallback tak boleh M-FILL YA'
        assert row[13] == '67', 'health tetap dirender (9.5/14*100)'


class TestFilterTypeV2720:
    def test_engine_menerapkan_tx_type(self):
        """get_rekap_data membangun query dengan AND transaction_type = %s."""
        import inspect
        from modules import engine
        src = inspect.getsource(engine.get_rekap_data)
        assert 't.transaction_type = %s' in src, 'filter tx_type tetap mati'
        assert "tx_type in ('CLAIM', 'CASH_LPJ')" in src

    def test_route_membaca_param_type(self):
        """rekap_pdf funnel ?type=... ke engine — tidak lagi dead param."""
        import inspect
        from modules import routes_reports
        src = inspect.getsource(routes_reports)
        assert "request.args.get('type'" in src
        assert 'tx_type=filters[' in src


class TestBudgetDihapus:
    def test_budget_bulanan_tidak_lama_dirender(self):
        """'Budget Bulanan' tidak lagi keta render di PDF per-transaksi."""
        tx = {
            'id': 1, 'display_id': '#B-0001', 'nopol': 'B 1234 XYZ',
            'driver_name': 'budi', 'nominal': 100000, 'liter': 20.0,
            'odo_km': 5000, 'created_at': datetime.datetime(2026, 10, 26),
            'bbm_type': 'Pertalite', 'spbu_type': 'pusat',
        }
        pdf = PDFReportCompact()
        pdf.add_page()
        # tanpa DB: cross-check jatuh ke cabang except — tidak crash
        pdf.generate_compact_report(tx, upload_folder='/tmp/opencode')
        data = pdf.output(dest='R')
        raw = bytes(data) if not isinstance(data, str) else data.encode('latin-1')
        assert b'Budget Bulanan' not in raw, 'Budget Bulanan masih dirender'
        # Catatan GA tetap ada di source (jangan ikut terhapus bersama budget)
        pdf2 = PDFReportCompact()
        pdf2.add_page()
        pdf2._draw_cross_check(tx)
        data2 = pdf2.output(dest='R')
        raw2 = bytes(data2) if not isinstance(data2, str) else data2.encode('latin-1')
        assert b'Catatan GA' not in raw2 or b'Data cross-check tidak tersedia' in raw2, \
            'tanpa DB, catatan GA lewat jalur fallback — tidak crash'

    def test_kuery_budget_sudah_dihapus(self):
        import inspect
        from modules import pdf_generator
        src = inspect.getsource(pdf_generator.PDFReportCompact)
        assert 'MONTH(created_at)=MONTH(CURDATE())' not in src, 'kuery budget salah hitung masih ada'
        assert "cell(col_w, 5, 'Budget Bulanan'" not in src, 'render budget masih ada'

    def test_catatan_ga_tetap_ada(self):
        """Catatan GA (vehicle_assignments) tetap dirender — pindah kolom kanan."""
        import inspect
        from modules import pdf_generator
        src = inspect.getsource(pdf_generator.PDFReportCompact)
        assert 'Catatan GA' in src and 'vehicle_assignments' in src
