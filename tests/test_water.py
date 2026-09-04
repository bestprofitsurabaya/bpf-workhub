"""
Unit Tests — Tanda Terima Pembelian Air Minum (v2.6)
BPF WorkHub

- WaterReceiptPDF: dokumen PDF untuk status verified / rejected.
- _get_ttd_names: nama TTD Finance/GA dari system_config (mock DB).
- home_for_role('ob') → /app/water (halaman OB).

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_water.py -v
"""

import sys
import os
import re
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session
from modules.helpers import home_for_role, ROLE_HOME


# Sumber tunggal ekstraktor teks PDF (lihat tests/pdf_text.py).
# Alias lama dipertahankan agar file test lain yang meng-import dari sini tetap jalan.
from tests.pdf_text import pdf_text as _pdf_text  # noqa: E402


app = Flask(__name__)
app.secret_key = 'test-secret'
app.config['UPLOAD_FOLDER'] = 'uploads'


def _sample_purchase(status='verified'):
    return {
        'id': 1,
        'display_id': 'WTR-20260812-0001',
        'ob_name': 'BUDI',
        'purchase_date': date(2026, 8, 12),
        'created_at': datetime(2026, 8, 12, 9, 30),
        'status': status,
        'remark': 'Barang diterima sesuai pesanan',
        'note': 'Galon ditukar 2 unit kosong',
        'rejection_reason': 'Foto sebelum & sesudah identik',
        'verified_by': 'RINA',
        'verified_at': datetime(2026, 8, 12, 10, 0),
        'foto_before': None,
        'foto_after': None,
    }


def _sample_items():
    return [
        {'drink_type': 'Galon', 'brand': 'AQUA', 'satuan': 'galon', 'quantity': 3},
        {'drink_type': 'Botol', 'brand': 'Le Minerale', 'satuan': 'dus', 'quantity': 2},
    ]


class TestWaterReceiptPDF:
    def test_generate_verified_menghasilkan_pdf(self):
        """PDF terverifikasi berisi tabel item, remark, note, dan nama TTD."""
        from modules.pdf_generator import WaterReceiptPDF
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(_sample_purchase('verified'), _sample_items(),
                     ga_name='ANDI', finance_name='RINA')
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        assert pdf_bytes[:4] == b'%PDF'
        text = _pdf_text(pdf_bytes)
        # Judul resmi dokumen (bukan varian lama 'SERAH TERIMA')
        assert 'TANDA TERIMA AIR MINUM' in text
        assert 'SERAH TERIMA AIR MINUM' not in text
        # Seksi informasi memakai istilah Pengiriman (v2.29.4)
        assert 'INFORMASI PENGIRIMAN' in text
        assert 'INFORMASI PENGAJUAN' not in text
        assert 'AQUA' in text
        assert 'Le Minerale' in text
        # Label tanggal pengiriman (bukan 'Tanggal Pembelian')
        assert 'Tanggal Pengiriman' in text
        assert 'Tanggal Pembelian' not in text
        # 'Diajukan pada' tidak lagi ditulis di dokumen
        assert 'Diajukan pada' not in text
        # Nama penandatangan
        assert 'RINA' in text
        assert 'ANDI' in text
        # Status verifikasi & remark
        assert 'TERVERIFIKASI' in text
        assert 'Barang diterima sesuai pesanan' in text

    def test_generate_foto_ob_terlampir(self, tmp_path):
        """Foto yang diunggah OB (sebelum/sesudah) terlampir di dokumen PDF."""
        from PIL import Image
        from modules.pdf_generator import WaterReceiptPDF
        # Buat dua gambar bukti dummy
        before_path = tmp_path / 'wtr_before.jpg'
        after_path = tmp_path / 'wtr_after.jpg'
        Image.new('RGB', (120, 80), (200, 60, 60)).save(before_path, 'JPEG')
        Image.new('RGB', (120, 80), (60, 120, 200)).save(after_path, 'JPEG')
        p = _sample_purchase('verified')
        p['foto_before'] = before_path.name
        p['foto_after'] = after_path.name
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(p, _sample_items(), ga_name='ANDI', finance_name='RINA',
                     upload_folder=str(tmp_path))
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        # Foto benar-benar disematkan sebagai gambar XObject di PDF
        assert b'/Subtype /Image' in pdf_bytes
        text = _pdf_text(pdf_bytes)
        assert 'LAMPIRAN FOTO' in text
        assert 'SEBELUM' in text and 'SESUDAH' in text

    def test_generate_rejected_menampilkan_alasan(self):
        """PDF berstatus ditolak menampilkan alasan penolakan."""
        from modules.pdf_generator import WaterReceiptPDF
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(_sample_purchase('rejected'), _sample_items(),
                     ga_name='ANDI', finance_name='RINA')
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        assert pdf_bytes[:4] == b'%PDF'
        text = _pdf_text(pdf_bytes)
        assert 'DITOLAK' in text
        assert 'Foto sebelum & sesudah identik' in text

    def test_generate_pending_menampilkan_menunggu(self):
        """PDF status pending menampilkan keterangan menunggu verifikasi."""
        from modules.pdf_generator import WaterReceiptPDF
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(_sample_purchase('pending'), _sample_items())
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        text = _pdf_text(pdf_bytes)
        assert 'Menunggu verifikasi Finance' in text

    def test_urutan_seksi_sesuai_format_finance(self, tmp_path):
        """Urutan dokumen (v2.29.4): Informasi Pengiriman → Rincian Barang →
        Verifikasi/Remark → Lampiran Foto (sebelum/sesudah dari form OB) →
        Tanda Tangan."""
        from PIL import Image
        from modules.pdf_generator import WaterReceiptPDF
        before_path = tmp_path / 'wtr_before.jpg'
        after_path = tmp_path / 'wtr_after.jpg'
        Image.new('RGB', (120, 80), (200, 60, 60)).save(before_path, 'JPEG')
        Image.new('RGB', (120, 80), (60, 120, 200)).save(after_path, 'JPEG')
        p = _sample_purchase('verified')
        p['foto_before'] = before_path.name
        p['foto_after'] = after_path.name
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(p, _sample_items(), ga_name='ANDI', finance_name='RINA',
                     upload_folder=str(tmp_path))
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        text = _pdf_text(pdf_bytes)
        marks = ['INFORMASI PENGIRIMAN', 'RINCIAN BARANG',
                 'HASIL VERIFIKASI FINANCE', 'LAMPIRAN FOTO (TIMESTAMP)',
                 'TANDA TANGAN']
        positions = [text.find(m) for m in marks]
        assert all(i >= 0 for i in positions), f'section hilang: {[m for m, i in zip(marks, positions) if i < 0]}'
        # Foto bukti OB tampil SEBELUM blok TTD
        assert positions == sorted(positions), 'urutan seksi tidak sesuai format Finance'
        assert 'Foto SEBELUM diisi' in text and 'Foto SESUDAH diisi' in text

    @staticmethod
    def _pages_of(pdf_bytes):
        """Pisahkan teks PDF per halaman (footer 'Page x/y' sebagai pemisah)."""
        return re.split(r'Page \d+/\d+', _pdf_text(pdf_bytes))

    def test_konten_panjang_judul_seksi_tidak_orphan(self, tmp_path):
        """Dokumen panjang (banyak item + foto): judul seksi harus satu halaman
        dengan konten pertamanya — tidak boleh tertinggal (orphan) di dasar
        halaman sebelumnya saat blok TTD/lampiran pindah ke halaman baru."""
        from PIL import Image
        from modules.pdf_generator import WaterReceiptPDF
        before_path = tmp_path / 'wtr_long_before.jpg'
        after_path = tmp_path / 'wtr_long_after.jpg'
        Image.new('RGB', (120, 80), (200, 60, 60)).save(before_path, 'JPEG')
        Image.new('RGB', (120, 80), (60, 120, 200)).save(after_path, 'JPEG')
        p = _sample_purchase('verified')
        p['remark'] = 'Dicek: ' + 'galon tersegel, merk sesuai nota supplier, ' * 6
        p['foto_before'] = before_path.name
        p['foto_after'] = after_path.name
        items = [{'drink_type': 'Galon', 'brand': f'Brand {i}',
                  'satuan': 'galon', 'quantity': i} for i in range(1, 26)]
        pdf = WaterReceiptPDF()
        pdf.add_page()
        pdf.generate(p, items, ga_name='ANDI', finance_name='RINA',
                     upload_folder=str(tmp_path))
        raw = pdf.output(dest='S')
        pdf_bytes = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
        pages = self._pages_of(pdf_bytes)
        assert len(pages) >= 2  # pastikan skenario benar-benar multi-halaman

        def page_of(needle):
            for i, pg in enumerate(pages):
                if needle in pg:
                    return i
            return -1

        for heading, anchor in [
            ('HASIL VERIFIKASI FINANCE', 'TERVERIFIKASI'),
            ('TANDA TANGAN', 'Menyerahkan'),
            ('LAMPIRAN FOTO (TIMESTAMP)', 'Foto SEBELUM diisi'),
        ]:
            assert page_of(heading) != -1, f'judul tidak ditemukan: {heading}'
            assert page_of(heading) == page_of(anchor), \
                f'judul orphan: "{heading}" di halaman {page_of(heading)}, ' \
                f'kontennya di halaman {page_of(anchor)}'


class TestGetTtdNames:
    def test_ttd_names_dari_system_config(self, monkeypatch):
        """Nama TTD diambil dari system_config (di-set admin di /app/settings)."""
        import modules.routes_water as rw

        class FakeCursor:
            def execute(self, q, params=None):
                self._rows = [
                    {'config_key': 'water_ga_name', 'config_value': 'Andi Prasetyo'},
                    {'config_key': 'water_finance_name', 'config_value': 'Rina Wijaya'},
                ]
            def fetchall(self):
                return self._rows
            def close(self):
                pass

        class FakeConn:
            def cursor(self, dictionary=True):
                return FakeCursor()
            def close(self):
                pass

        def fake_get_db_connection():
            return FakeConn()

        monkeypatch.setattr(rw, 'get_db_connection', fake_get_db_connection)
        ga, finance = rw._get_ttd_names()
        assert ga == 'Andi Prasetyo'
        assert finance == 'Rina Wijaya'

    def test_ttd_names_kosong_saat_tidak_diset(self, monkeypatch):
        """Tanpa konfigurasi → string kosong (PDF memakai default label)."""
        import modules.routes_water as rw

        class FakeCursor:
            def execute(self, q, params=None):
                self._rows = []
            def fetchall(self):
                return self._rows
            def close(self):
                pass

        class FakeConn:
            def cursor(self, dictionary=True):
                return FakeCursor()
            def close(self):
                pass

        monkeypatch.setattr(rw, 'get_db_connection', lambda: FakeConn())
        ga, finance = rw._get_ttd_names()
        assert ga == ''
        assert finance == ''


class TestWaterRecap:
    """Agregasi rekap dashboard Finance (murni, tanpa DB)."""

    def _rows(self):
        return [
            {'id': 1, 'display_id': 'WTR-1', 'ob_name': 'OB 1', 'purchase_date': date(2026, 8, 12),
             'status': 'pending', 'remark': '', 'created_at': datetime(2026, 8, 12, 9, 0)},
            {'id': 2, 'display_id': 'WTR-2', 'ob_name': 'OB 1', 'purchase_date': date(2026, 8, 12),
             'status': 'verified', 'remark': 'OK', 'created_at': datetime(2026, 8, 12, 10, 0)},
            {'id': 3, 'display_id': 'WTR-3', 'ob_name': 'OB 2', 'purchase_date': date(2026, 8, 13),
             'status': 'rejected', 'remark': '', 'created_at': datetime(2026, 8, 13, 9, 0)},
        ]

    def _items(self):
        return {
            1: [{'drink_type': 'Galon', 'brand': 'AQUA', 'satuan': 'galon', 'quantity': 3}],
            2: [{'drink_type': 'Botol', 'brand': 'Le Minerale', 'satuan': 'dus', 'quantity': 2}],
            3: [{'drink_type': 'Gelas', 'brand': 'Club', 'satuan': 'gelas', 'quantity': 48}],
        }

    def test_agregasi_ringkasan_dan_per_ob(self):
        import modules.routes_water as rw
        kas = {'waiting_approve_count': 2, 'waiting_approve_nominal': 250000,
               'waiting_lpj_count': 1}
        d = rw._aggregate_water_recap(self._rows(), self._items(), kas)
        assert d['summary'] == {'total': 3, 'pending': 1, 'verified': 1, 'rejected': 1, 'qty': 53}
        assert len(d['per_ob']) == 2
        ob1 = d['per_ob'][0]
        assert ob1['ob_name'] == 'OB 1' and ob1['total'] == 2 and ob1['qty'] == 5
        assert d['kasbon']['waiting_approve']['count'] == 2
        assert d['kasbon']['waiting_approve']['nominal'] == 250000
        assert d['kasbon']['waiting_lpj']['count'] == 1

    def test_agregasi_per_jenis_merk_dan_antrean(self):
        import modules.routes_water as rw
        d = rw._aggregate_water_recap(self._rows(), self._items(), {})
        by_type = {t['name']: t for t in d['per_type']}
        assert by_type['Galon']['qty'] == 3
        assert by_type['Gelas']['qty'] == 48
        by_brand = {b['name']: b for b in d['per_brand']}
        assert by_brand['AQUA']['purchases'] == 1
        assert len(d['queue']) == 1 and d['queue'][0]['display_id'] == 'WTR-1'
        assert d['queue'][0]['item_count'] == 1

    def test_csv_export_berisi_bom_header_dan_baris(self):
        import modules.routes_water as rw
        csv_text = rw._build_water_csv(self._rows(), self._items())
        assert csv_text.startswith('\ufeff')
        assert 'Tanggal,Nomor,OB,Status,Jenis,Merk,Satuan,Kuantitas,Remark' in csv_text
        assert 'WTR-1' in csv_text and 'AQUA' in csv_text
        assert 'Menunggu Verifikasi' in csv_text and 'Terverifikasi' in csv_text
        # 3 pengajuan -> 3 baris item
        assert csv_text.count('WTR-') == 3


class TestHomeForRoleOB:
    def test_role_ob_memiliki_halaman_sendiri(self):
        """OB login → diarahkan ke SPA /app/water (bukan dashboard back-office)."""
        assert ROLE_HOME.get('ob') == '/app/water'
        assert home_for_role('ob') == '/app/water'

    def test_role_finance_memiliki_dashboard_sendiri(self):
        """v2.7/2.8: finance & ga punya dashboard khusus; admin tetap dashboard."""
        assert home_for_role('finance') == '/app/finance'
        assert home_for_role('ga') == '/app/ga'
        assert home_for_role('admin') == '/app/dashboard'
