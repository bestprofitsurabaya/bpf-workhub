"""Sistem Overtime (v2.22) — GA HR: Driver (sinkronisasi Google Sheet)
+ OB/Security (migrasi penuh & form publik).

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_overtime.py -v
"""
import io
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.overtime_helpers import (clean, norm_key, map_headers,
                                      parse_date_mdy, parse_time_12h,
                                      parse_submitted_at, normalize_name,
                                      guess_position, parse_iso_dt,
                                      parse_date_any, parse_time_any,
                                      parse_submitted_at_any,
                                      normalize_driver_row)
from modules.helpers import home_for_role, ROLE_HOME


# ============================================================
# Parser kolom Google Sheet
# ============================================================
class TestHeaderMapping:
    """Header form Google Form asli (sheet OB/Security) dipetakan benar."""

    def test_headers_ob_security(self):
        m = map_headers([
            'Timestamp', 'Email Address', 'Nama Lengkap', 'Tanggal',
            'Waktu Mulai Overtime', 'Waktu Selesai Overtime', 'Keterangan',
            'Upload Foto Mulai OT menggunakan Timestamp. ',
            'Upload Foto Selesai OT menggunakan Timestamp. ',
        ])
        assert m['submitted_at'] == 0
        assert m['email'] == 1
        assert m['nama'] == 2
        assert m['tanggal'] == 3
        assert m['waktu_mulai'] == 4
        assert m['waktu_selesai'] == 5
        assert m['keterangan'] == 6
        assert m['foto_mulai'] == 7
        assert m['foto_selesai'] == 8

    def test_headers_sederhana(self):
        m = map_headers(['Nama', 'Tanggal', 'Mulai', 'Selesai', 'Catatan'])
        assert m['nama'] == 0 and m['tanggal'] == 1
        assert m['waktu_mulai'] == 2 and m['waktu_selesai'] == 3
        assert m['keterangan'] == 4

    def test_header_tidak_dikenal_diabaikan(self):
        m = map_headers(['Score', 'Foo Bar', 'Nama Lengkap'])
        assert m['nama'] == 2
        assert 'score' not in m

    def test_headers_driver_sheet(self):
        """Header asli sheet DRIVER (Google Form lama, v2.22.1)."""
        m = map_headers([
            'Timestamp', 'NO FORM', 'Email Address', 'NAMA LENGKAP',
            'NO KENDARAAN', 'Tanggal Overtime', 'Dari / IN', 'Sampai / OUT',
            'Nama Broker / Marketing', 'Nama Manager / Team leader',
            'KETERANGAN', 'FOTO SELFIE @OFFICE', 'FOTO DI TUJUAN',
            'photoid1', 'photoid2',
            'Merged Doc ID - OT DRIVER', 'Merged Doc URL - OT DRIVER',
            'Link to merged Doc - OT DRIVER', 'Document Merge Status - OT DRIVER',
        ])
        assert m['submitted_at'] == 0
        assert m['email'] == 2
        assert m['nama'] == 3
        assert m['no_kendaraan'] == 4
        assert m['tanggal'] == 5
        assert m['waktu_mulai'] == 6
        assert m['waktu_selesai'] == 7
        assert m['broker'] == 8
        assert m['manager'] == 9
        assert m['keterangan'] == 10
        assert m['foto_mulai'] == 11
        assert m['foto_selesai'] == 12
        assert m['doc_url'] == 16
        assert 'noform' not in m
        assert 'photoid1' not in m


class TestDateParsing:
    def test_parse_date_mdy(self):
        assert parse_date_mdy('1/5/2026') == '2026-01-05'
        assert parse_date_mdy('12/25/2026') == '2026-12-25'
        assert parse_date_mdy('1/5/2026 20:32:44') == '2026-01-05'
        assert parse_date_mdy('') is None
        assert parse_date_mdy('abc') is None

    def test_parse_time_12h(self):
        assert parse_time_12h('6:29:00 PM') == '18:29'
        assert parse_time_12h('8:32:00 PM') == '20:32'
        assert parse_time_12h('6:30:00 AM') == '06:30'
        assert parse_time_12h('12:00:00 PM') == '12:00'
        assert parse_time_12h('12:30:00 AM') == '00:30'
        assert parse_time_12h('') is None
        assert parse_time_12h('n/a') is None

    def test_parse_submitted_at(self):
        assert parse_submitted_at('1/5/2026 20:32:44') == '2026-01-05 20:32:44'
        assert parse_submitted_at('') is None

    def test_parse_iso_dt_utc_ke_wib(self):
        """Apps Script mengirim ISO UTC; sheet WIB => +7 jam."""
        dt = parse_iso_dt('2020-12-12T07:08:54.000Z')
        assert dt is not None
        assert dt.strftime('%Y-%m-%d %H:%M:%S') == '2020-12-12 14:08:54'
        # Tanggal overtime tengah malam WIB = 17:00 UTC hari sebelumnya
        dt2 = parse_iso_dt('2020-12-11T17:00:00.000Z')
        assert dt2.strftime('%Y-%m-%d') == '2020-12-12'
        # Nilai waktu murni (epoch Google Sheets)
        dt3 = parse_iso_dt('1899-12-30T07:24:56.000Z')
        assert dt3.strftime('%H:%M') == '14:24'
        assert parse_iso_dt('') is None
        assert parse_iso_dt('abc') is None

    def test_parse_date_any(self):
        assert parse_date_any('2020-12-11T17:00:00.000Z') == '2020-12-12'
        assert parse_date_any('1/5/2026') == '2026-01-05'
        assert parse_date_any('2026-08-14') == '2026-08-14'
        assert parse_date_any('') is None

    def test_parse_time_any(self):
        assert parse_time_any('1899-12-30T07:24:56.000Z') == '14:24'
        assert parse_time_any('6:29:00 PM') == '18:29'
        assert parse_time_any('') is None

    def test_parse_submitted_at_any(self):
        assert parse_submitted_at_any('2020-12-12T07:08:54.000Z') == '2020-12-12 14:08:54'
        assert parse_submitted_at_any('1/5/2026 20:32:44') == '2026-01-05 20:32:44'
        assert parse_submitted_at_any('') is None


# ============================================================
# Normalisasi nama & posisi (data sheet lama banyak typo)
# ============================================================
class TestNormalizeName:
    def test_nama_baku(self):
        assert normalize_name('Edwin P') == 'Edwin P'
        assert normalize_name('Muhajir') == 'Muhajir'

    def test_typo_dibakukan(self):
        assert normalize_name('Edwin p') == 'Edwin P'
        assert normalize_name('Febru') == 'Febri'
        assert normalize_name('Febrj') == 'Febri'
        assert normalize_name('Faissol') == 'Faisol'
        assert normalize_name('Faisool') == 'Faisol'
        assert normalize_name('Fasol') == 'Faisol'

    def test_kosong(self):
        assert normalize_name('') == ''
        assert normalize_name('  ') == ''


class TestGuessPosition:
    def test_muhajir_security(self):
        assert guess_position('Muhajir') == 'Security'
        assert guess_position('muhajir') == 'Security'

    def test_sisanya_ob(self):
        assert guess_position('Edwin P') == 'OB'
        assert guess_position('Febri') == 'OB'
        assert guess_position('Faisol') == 'OB'


# ============================================================
# Role GA HR — halaman sendiri
# ============================================================
class TestGaHrRole:
    def test_home_for_role(self):
        assert ROLE_HOME['ga_hr'] == '/app/ga-hr'
        assert home_for_role('ga_hr') == '/app/ga-hr'


# ============================================================
# Fetch sumber sheet: CSV publik & JSON Apps Script Web App
# ============================================================
class TestFetchSheetRows:
    def _fake_get(self, body, url='https://example.test/x', is_json=False):
        import modules.routes_overtime as ro

        class FakeResp:
            def __init__(self, url_):
                self.url = url_
                self.content = body.encode('utf-8-sig')
                self._json = is_json
            def raise_for_status(self):
                pass
            def json(self):
                import json as _j
                return _j.loads(body)

        def fake_get(url_, timeout=30, headers=None, **kwargs):
            assert url_ == url
            return FakeResp(url_)

        import modules.routes_overtime as ro
        ro.requests.get = fake_get
        return ro

    def test_fetch_csv(self):
        ro = self._fake_get(
            '"Timestamp","Nama Lengkap","Tanggal","Waktu Mulai Overtime","Waktu Selesai Overtime"\n'
            '"1/5/2026 20:32:44","Muhajir","1/5/2026","6:29:00 PM","8:32:00 PM"\n')
        rows = ro._fetch_sheet_rows('https://example.test/x')
        assert len(rows) == 1
        assert rows[0]['Nama Lengkap'] == 'Muhajir'

    def test_fetch_json_apps_script(self):
        ro = self._fake_get(
            '{"rows": [{"Nama Lengkap": "Edwin P", "Tanggal": "1/5/2026", "Waktu Mulai Overtime": "6:00:00 PM"}]}',
            is_json=True)
        rows = ro._fetch_sheet_rows('https://example.test/x')
        assert len(rows) == 1
        assert rows[0]['Nama Lengkap'] == 'Edwin P'

    def test_fetch_kosong(self):
        ro = self._fake_get('{"rows": []}', is_json=True)
        assert ro._fetch_sheet_rows('https://example.test/x') == []

    def test_fetch_mengikuti_redirect(self):
        """Regresi 1963283: allow_redirects=False membuat body kosong karena
        Google Apps Script /exec selalu 302 dulu — refresh jadi 0 baris diam-
        diam. Fetch harus memakai default (redirect diikuti)."""
        import modules.routes_overtime as ro

        class FakeResp:
            url = 'https://example.test/final'
            content = b'{"rows": [{"Nama Lengkap": "X"}]}'
            def raise_for_status(self):
                pass
            def json(self):
                import json as _j
                return _j.loads('{"rows": [{"Nama Lengkap": "X"}]}')

        captured = {}
        def fake_get(url_, timeout=30, headers=None, **kwargs):
            captured['allow_redirects'] = kwargs.get('allow_redirects')
            return FakeResp()

        ro.requests.get = fake_get
        rows = ro._fetch_sheet_rows('https://example.test/x')
        assert len(rows) == 1
        # allow_redirects harus False-tidak-dipaksakan (default requests = True)
        assert captured.get('allow_redirects') is not False
        assert captured.get('allow_redirects') is None or captured['allow_redirects'] is True


# ============================================================
# Logika migrasi sheet lama (unit — tanpa DB)
# ============================================================
class TestMigrationLogic:
    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'migrate_ot', os.path.join(os.path.dirname(__file__), '..',
                                       'scripts', 'migrate_overtime_ob_security.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_uid_berbeda_per_baris(self):
        m = self._load()
        r1 = {'Timestamp': '1/5/2026 20:32:44', 'Nama Lengkap': 'Muhajir'}
        r2 = {'Timestamp': '1/6/2026 22:01:18', 'Nama Lengkap': 'Muhajir'}
        assert m._uid(r1, 0) != m._uid(r2, 1)

    def test_uid_sama_untuk_baris_identik(self):
        m = self._load()
        r = {'Timestamp': '1/5/2026 20:32:44', 'Nama Lengkap': 'Muhajir'}
        assert m._uid(r, 0) == m._uid(dict(r), 0)


class TestClean:
    def test_normalisasi_spasi(self):
        assert clean('  Edwin   P  ') == 'Edwin P'
        assert clean('') == ''


# ============================================================
# Auto-refresh saat login/logout (v2.22.1)
# ============================================================
class TestAutoRefresh:
    def test_hanya_role_ga_hr_dan_admin(self):
        import modules.routes_overtime as ro
        submitted = []
        ro._last_auto_refresh['ts'] = 0.0

        def fake_submit(fn):
            submitted.append(fn)
        ro.production_pool_executor.submit = fake_submit

        ro.trigger_driver_refresh_async('driver', 'Andi')
        ro.trigger_driver_refresh_async('ob', 'Budi')
        assert submitted == []  # role lain tidak memicu refresh

        ro.trigger_driver_refresh_async('ga_hr', 'GA HR')
        ro.trigger_driver_refresh_async('admin', 'Admin')
        assert len(submitted) == 1  # debounce: hanya 1x dalam 30 detik

    def test_debounce_ulang_setelah_interval(self):
        import modules.routes_overtime as ro
        submitted = []
        ro._last_auto_refresh['ts'] = 0.0

        def fake_submit(fn):
            submitted.append(fn)
        ro.production_pool_executor.submit = fake_submit

        ro.trigger_driver_refresh_async('admin', 'Admin')
        assert len(submitted) == 1
        # Simulasi sudah lewat 30 detik -> boleh refresh lagi
        ro._last_auto_refresh['ts'] = 0.0
        ro.trigger_driver_refresh_async('admin', 'Admin')
        assert len(submitted) == 2

    def test_do_refresh_driver_url_kosong_raise(self):
        """Tanpa URL sumber, _do_refresh_driver menolak dengan ValueError."""
        import modules.routes_overtime as ro
        import pytest

        class FakeCursor:
            def __init__(self, val):
                self._val = val
            def execute(self, *a, **k):
                pass
            def fetchone(self):
                return {'config_value': self._val}
            def close(self):
                pass

        class FakeConn:
            def cursor(self, *a, **k):
                return FakeCursor('')
            def close(self):
                pass

        ro.get_db_connection = lambda: FakeConn()
        with pytest.raises(ValueError):
            ro._do_refresh_driver()


# ============================================================
# Edit & hapus data overtime (v2.22.1)
# ============================================================
class TestOvertimeCrud:
    def test_modul_valid(self):
        import modules.routes_overtime as ro
        assert set(ro._OT_TABLES) == {'driver', 'ob'}
        assert ro._OT_TABLES['driver'] == 'overtime_driver'
        assert ro._OT_TABLES['ob'] == 'overtime_ob_security'

    def test_kolom_driver_dan_ob(self):
        import modules.routes_overtime as ro
        assert 'no_kendaraan' in ro._OT_COLUMNS['driver']
        assert 'broker' in ro._OT_COLUMNS['driver']
        assert 'manager' in ro._OT_COLUMNS['driver']
        assert 'posisi' in ro._OT_COLUMNS['ob']
        assert 'no_kendaraan' not in ro._OT_COLUMNS['ob']

    def test_posisi_hanya_ob_security(self):
        """Posisi selain OB/Security ditolak (validasi server)."""
        assert ('OB' in __import__('modules.routes_overtime', fromlist=['POSITIONS']).POSITIONS)
        assert ('Security' in __import__('modules.routes_overtime', fromlist=['POSITIONS']).POSITIONS)
        assert 'Manager' not in __import__('modules.routes_overtime', fromlist=['POSITIONS']).POSITIONS


# ============================================================
# Normalisasi baris sheet DRIVER -> dict DB (v2.22.1)
# ============================================================
class TestNormalizeDriverRow:
    HEADERS = ['Timestamp', 'NO FORM', 'Email Address', 'NAMA LENGKAP',
               'NO KENDARAAN', 'Tanggal Overtime', 'Dari / IN', 'Sampai / OUT',
               'Nama Broker / Marketing', 'Nama Manager / Team leader',
               'KETERANGAN', 'Merged Doc URL - OT DRIVER']

    def _norm(self, row, n=0):
        idx = map_headers(self.HEADERS)
        return normalize_driver_row(row, self.HEADERS, idx, n)

    def test_baris_lengkap(self):
        row = {
            'Timestamp': '2020-12-12T07:08:54.000Z',
            'NO FORM': 3,
            'Email Address': 'mahesta45@gmail.com',
            'NAMA LENGKAP': 'Mandar mahesta prasetya',
            'NO KENDARAAN': 'W 6283 TV',
            'Tanggal Overtime': '2020-12-11T17:00:00.000Z',
            'Dari / IN': '1899-12-30T07:24:56.000Z',
            'Sampai / OUT': '1899-12-30T10:47:56.000Z',
            'Nama Broker / Marketing': 'Silva',
            'Nama Manager / Team leader': 'Derry',
            'KETERANGAN': 'Edukasi',
            'Merged Doc URL - OT DRIVER': 'https://drive.google.com/file/d/1W6c/view',
        }
        out = self._norm(row)
        assert out is not None
        assert out['sheet_row'] == 2
        assert out['submitted_at'] == '2020-12-12 14:08:54'
        assert out['nama'] == 'Mandar mahesta prasetya'
        assert out['no_kendaraan'] == 'W 6283 TV'
        assert out['tanggal'] == '2020-12-12'
        assert out['waktu_mulai'] == '14:24'
        assert out['waktu_selesai'] == '17:47'
        assert out['broker'] == 'Silva'
        assert out['manager'] == 'Derry'
        assert out['keterangan'] == 'Edukasi'
        assert out['doc_url'] == 'https://drive.google.com/file/d/1W6c/view'

    def test_baris_kosong_dilewati(self):
        assert self._norm({'NAMA LENGKAP': ''}) is None

    def test_sheet_row_urut(self):
        out = self._norm({'NAMA LENGKAP': 'Andi'}, n=4)
        assert out['sheet_row'] == 6


# ============================================================
# Kop per cabang (v2.37.7) — set_identity(branch_code=...)
# ============================================================
class TestKopPerCabang:
    def _fake_branch_conn(self, row):
        class _Cur:
            _sql = ''

            def execute(self, sql, params=None):
                self._sql = sql

            def fetchone(self):
                return row if 'FROM branches' in self._sql else None

            def fetchall(self):
                return []

            def close(self):
                pass

        class _Conn:
            def cursor(self, dictionary=False):
                return _Cur()

            def close(self):
                pass
        return _Conn()

    def test_overtime_report_kop_mengikuti_cabang(self, monkeypatch):
        """v2.37.7: OvertimeReportPDF + set_identity('MDN') — kop memakai
        alamat cabang Medan, alamat HO tidak ikut."""
        import modules.config as cfg
        row = {'company_name': 'PT BESTPROFIT FUTURES',
               'company_subtitle': 'Cabang Medan',
               'address': 'Ruko Jati Junction, Jl. Perintis Kemerdekaan No. P9A-10A, Medan 20218',
               'phone': '061-80501610', 'city': 'Medan'}
        monkeypatch.setattr(cfg, 'get_db_connection',
                            lambda branch_code=None, master=False: self._fake_branch_conn(row))
        from tests.pdf_text import _pdf_text
        from modules.pdf_generator import OvertimeReportPDF
        pdf = OvertimeReportPDF()
        pdf.set_identity(branch_code='MDN')
        pdf.generate([], modul='driver', date_label='2026-09-01 s/d 2026-09-08',
                     filters={}, generated_by='GA HR Officer')
        buf = io.BytesIO()
        pdf.output(buf)
        text = _pdf_text(buf.getvalue())
        assert 'Perintis Kemerdekaan' in text
        assert 'Equity Tower' not in text


# ============================================================
# Laporan PDF Overtime (berlogo, TTD GA HR)
# ============================================================
class TestOvertimePDF:
    def _mk_pdf(self, rows, modul='driver'):
        import io
        from modules.pdf_generator import OvertimeReportPDF
        pdf = OvertimeReportPDF()
        pdf.generate(rows, modul=modul, date_label='2026-08-01 s/d 2026-08-14',
                     filters={'Posisi': 'OB'}, generated_by='GA HR Officer')
        buf = io.BytesIO()
        pdf.output(buf)
        return buf.getvalue()

    def test_generate_empty_rows(self):
        from tests.pdf_text import _pdf_text
        data = self._mk_pdf([])
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        assert 'LAPORAN OVERTIME' in _pdf_text(data)

    def test_generate_driver(self):
        from tests.pdf_text import _pdf_text
        rows = [{
            'tanggal': date(2026, 8, 13), 'nama': 'Andi Driver',
            'waktu_mulai': '18:00', 'waktu_selesai': '21:00',
            'keterangan': 'OT malam', 'email': 'andi@mail.com',
        }]
        data = self._mk_pdf(rows, 'driver')
        txt = _pdf_text(data)
        assert 'LAPORAN OVERTIME' in txt
        assert 'ANDI DRIVER' in txt.upper() or 'Andi' in txt
        assert 'OT MALAM' in txt.upper() or 'OT malam' in txt
        assert 'GA HR' in txt.upper()

    def test_generate_ob_security(self):
        from tests.pdf_text import _pdf_text
        rows = [{
            'tanggal': date(2026, 8, 13), 'nama': 'Muhajir',
            'posisi': 'Security', 'waktu_mulai': '18:30', 'waktu_selesai': '22:00',
            'keterangan': 'Keamanan kantor',
        }]
        data = self._mk_pdf(rows, 'ob')
        txt = _pdf_text(data)
        assert 'OB & SECURITY' in txt.upper() or 'Overtime OB' in txt
        assert 'SECURITY' in txt.upper()
        assert 'MUHAJIR' in txt.upper()


# ============================================================
# Form PDF Overtime — blok tanda tangan (v2.39.6)
# TTD MANAGER hanya utk modul driver; OB/Security tanpa kolom MANAGER.
# ============================================================
class TestOvertimeFormPDFSignatures:
    def _form_pdf_text(self, modul):
        from modules.pdf_generator import OvertimeFormPDF
        from tests.pdf_text import _pdf_text
        row = {
            'display_id': 'OTX-001', 'email': 'user@mail.com',
            'nama': 'Budi Santoso', 'tanggal': date(2026, 9, 13),
            'waktu_mulai': '18:00', 'waktu_selesai': '21:00',
            'keterangan': 'OT malam',
        }
        if modul == 'driver':
            row.update({'no_kendaraan': 'B 1234 XYZ', 'broker': 'Broker A',
                        'manager': 'Pak Manajer'})
        else:
            row['posisi'] = 'Security'
        pdf = OvertimeFormPDF()
        pdf.generate(row, modul=modul)
        buf = io.BytesIO()
        pdf.output(buf)
        return _pdf_text(buf.getvalue())

    def test_driver_form_has_manager_signature(self):
        txt = self._form_pdf_text('driver').upper()
        assert 'MANAGER' in txt          # blok TTD + field NAMA MANAGER
        assert 'FINANCE' in txt
        assert 'GA HR' in txt
        assert 'KEPALA CABANG' in txt

    def test_ob_security_form_has_no_manager_signature(self):
        txt = self._form_pdf_text('ob').upper()
        assert 'FINANCE' in txt
        assert 'GA HR' in txt
        assert 'KEPALA CABANG' in txt
        assert 'MANAGER' not in txt      # kolom MANAGER dihapus utk OB/Security

    def test_direct_signature_blocks_default_is_driver(self):
        """Tanpa argumen (pemanggil lama), blok TTD tetap memuat MANAGER."""
        from modules.pdf_generator import OvertimeFormPDF
        from tests.pdf_text import _pdf_text
        pdf = OvertimeFormPDF()
        pdf.add_page()
        pdf._signature_blocks()
        buf = io.BytesIO()
        pdf.output(buf)
        assert 'MANAGER' in _pdf_text(buf.getvalue()).upper()
