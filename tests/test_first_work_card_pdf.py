"""Rilis B Task 3 — cetak kartu BPF dari FirstWork.

Yang diuji:
1. Endpoint `GET /api/first-work/card/<id>.pdf` hanya untuk staf FirstWork/CV,
   menghasilkan PDF (diawali `%PDF`) dengan header attachment & no-cache.
2. Kartu memuat nama, cabang, nomor registrasi, dan NIK **4 digit terakhir
   saja** — NIK lengkap TIDAK boleh bocor (teks maupun QR).
3. QR memakai payload deterministik `BPF-FW:<registration_no>` dan disisipkan
   sebagai gambar di dalam PDF.
4. 13 field demografi tampil bila ada; baris legacy (semua NULL) tetap
   menghasilkan kartu satu halaman tanpa nilai `None`.
5. Posisi x kolom nilai tidak terkliping (pola test_driver_service_pdf_qr.py).
"""
import io
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402
from flask import Flask  # noqa: E402
from PIL import Image  # noqa: E402

from modules import routes_first_work as fw  # noqa: E402
from modules import pdf_generator as pg  # noqa: E402
from tests.pdf_text import pdf_page_count, pdf_text  # noqa: E402

NIK = '3578010101900001'
ROW = {
    'id': 7,
    'registration_no': 'FW-SBY-20261124-0007',
    'branch_code': 'SBY',
    'nama': 'Contoh Pendaftar',
    'nik': NIK,
    'nik_raw': '',
    'fingerprint_no': 'EF_25001',
    'bpf_no': 'EF_8001',
    'tempat_lahir': 'Surabaya',
    'tanggal_lahir': '1995-01-19',
    'jenis_kelamin': 'Laki-laki',
    'golongan_darah': 'O',
    'alamat': 'Jl. Contoh No. 12',
    'rt_rw': '03/04',
    'kel_desa': 'Keputih',
    'kecamatan': 'Sukolilo',
    'agama': 'Islam',
    'status_perkawinan': 'Belum Menikah',
    'pekerjaan': 'Karyawan Swasta',
    'kewarganegaraan': 'WNI',
    'berlaku_hingga': '2030-01-19',
}


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self.rows = []

    def execute(self, sql, params=None):
        q = re.sub(r'\s+', ' ', sql).strip()
        self.rows = self.conn.answer(q, tuple(params or ()))
        return None

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, row=None):
        self.row = dict(row) if row else None

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        pass

    def close(self):
        pass

    def answer(self, q, params):
        if 'FROM first_work_submissions WHERE id=%s' in q:
            if self.row and params and params[0] == self.row['id']:
                return [dict(self.row)]
            return []
        return []  # users / system_config untuk scope admin — tidak dipakai


APP = Flask(__name__)
APP.secret_key = 'uji'
fw.register_first_work_routes(APP)


@pytest.fixture(autouse=True)
def _identity_tanpa_db(monkeypatch):
    """Kop PDF memakai identitas default — pola test_cash_pdf.py (tanpa DB)."""
    from modules.company_identity import IDENTITY_DEFAULTS
    monkeypatch.setattr(pg, 'get_company_identity',
                        lambda *a, **k: dict(IDENTITY_DEFAULTS))


def _card(monkeypatch, role='traineer', row=None, branch='SBY', submission_id=None):
    conn = FakeConn(row if row is not None else ROW)
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    logged = []
    monkeypatch.setattr(fw, 'log_activity_async',
                        lambda *a, **k: logged.append((a, k)))
    sid = submission_id if submission_id is not None else ROW['id']
    with APP.test_client() as client:
        if role is not None:
            with client.session_transaction() as sess:
                sess['user_role'] = role
                sess['user_name'] = 'Uji'
                sess['branch_code'] = branch
        response = client.get(f'/api/first-work/card/{sid}.pdf')
    return response, logged


def _generate(row=None):
    pdf = pg.FirstWorkCardPDF()
    pdf.generate(dict(row) if row is not None else dict(ROW))
    return bytes(pdf.output())


# ================================================================
# Endpoint & role gate
# ================================================================
@pytest.mark.parametrize('role', ['traineer', 'finance', 'ga_hr', 'admin'])
def test_staf_diizinkan(monkeypatch, role):
    response, _ = _card(monkeypatch, role=role)
    assert response.status_code == 200, response.get_data(as_text=True)


@pytest.mark.parametrize('role', [None, 'driver'])
def test_non_staf_ditolak(monkeypatch, role):
    response, _ = _card(monkeypatch, role=role)
    assert response.status_code in (401, 403)


def test_404_baris_tidak_ada(monkeypatch):
    response, _ = _card(monkeypatch, submission_id=999)
    assert response.status_code == 404


def test_403_luar_cabang(monkeypatch):
    legacy = dict(ROW)
    legacy['branch_code'] = 'MLG'
    response, _ = _card(monkeypatch, row=legacy, branch='SBY')
    assert response.status_code == 403


def test_header_pdf_dan_attachment(monkeypatch):
    response, logged = _card(monkeypatch)
    assert response.status_code == 200
    data = response.get_data()
    assert data[:4] == b'%PDF'
    assert 'application/pdf' in response.headers['Content-Type']
    assert response.headers['Content-Disposition'].startswith('attachment;')
    assert ROW['registration_no'] in response.headers['Content-Disposition']
    assert response.headers.get('Cache-Control') == 'no-store'
    # Jejak audit hanya nomor registrasi — bukan NIK.
    assert NIK not in repr(logged)


# ================================================================
# Isi kartu & minimalisasi NIK
# ================================================================
def test_isi_kartu_dan_nik_empat_digit_terakhir():
    text = pdf_text(_generate())
    for expected in ('Contoh Pendaftar', 'SBY', 'FW-SBY-20261124-0007', '0001'):
        assert expected in text, expected
    assert NIK not in text
    assert NIK.encode() not in _generate()  # stream mentah pun tidak mengandung NIK penuh


def test_qr_payload_deterministik_dan_ascii():
    assert pg.fw_qr_payload(ROW['registration_no']) == (
        'BPF-FW:' + ROW['registration_no'])
    assert pg.fw_qr_payload('FW-SBY-20261124-0007 é') == (
        'BPF-FW:FW-SBY-20261124-0007')
    assert pg.fw_qr_payload(ROW['registration_no']).isascii()


def test_render_qr_bytesio_png_dan_deterministik():
    a = pg.render_fw_qr(ROW['registration_no']).getvalue()
    b = pg.render_fw_qr(ROW['registration_no']).getvalue()
    other = pg.render_fw_qr('FW-SBY-20261124-0008').getvalue()
    assert isinstance(pg.render_fw_qr(ROW['registration_no']), io.BytesIO)
    assert a[:8] == b'\x89PNG\r\n\x1a\n'
    assert a == b and other != a
    with Image.open(io.BytesIO(a)) as img:
        assert img.size[0] == img.size[1]


def test_generate_menyisipkan_qr_image(monkeypatch):
    dipanggil = []
    render_asli = pg.render_fw_qr

    def spy(registration_no):
        dipanggil.append(registration_no)
        return render_asli(registration_no)

    monkeypatch.setattr(pg, 'render_fw_qr', spy)
    output = _generate()
    assert dipanggil == [ROW['registration_no']]
    with Image.open(render_asli(ROW['registration_no'])) as img:
        width, height = img.size
    assert b'/Subtype /Image' in output
    assert f'/Columns {width}'.encode('ascii') in output
    assert f'/Rows {height}'.encode('ascii') in output


def test_line_value_mulai_di_awal_kolom_nilai():
    """Nilai tidak boleh mulai di RMARGIN (terkliping di tepi halaman)."""
    pdf = pg.FirstWorkCardPDF()
    pdf.add_page()
    x_sebelum_cell = []
    cell_asli = pdf.cell

    def spy(*args, **kwargs):
        x_sebelum_cell.append(pdf.get_x())
        return cell_asli(*args, **kwargs)

    pdf.cell = spy
    label_w = 42
    pdf._line('Nama', 'Contoh Pendaftar')
    assert len(x_sebelum_cell) == 2
    assert x_sebelum_cell[0] == pytest.approx(pdf.l_margin)
    assert x_sebelum_cell[1] == pytest.approx(pdf.l_margin + label_w)
    assert pdf.w - pdf.r_margin - x_sebelum_cell[1] >= 100


# ================================================================
# Demografi & legacy row
# ================================================================
def test_demografi_lengkap_tampil():
    text = pdf_text(_generate())
    for field, label in pg.FIRST_WORK_CARD_DEMOGRAPHICS:
        assert label in text, label
        assert str(ROW[field]) in text, field


def test_baris_legacy_tetap_satu_halaman_tanpa_nilai_none():
    row = {k: v for k, v in ROW.items()}
    for field, _label in pg.FIRST_WORK_CARD_DEMOGRAPHICS:
        row[field] = None
    row['nik'] = None  # NIK tidak dikenal → tidak boleh menampilkan 'None'
    output = _generate(row)
    assert pdf_page_count(output) == 1
    text = pdf_text(output)
    assert 'None' not in text
    assert '0001' not in text


def test_daftar_demografi_sinkron_dengan_routes():
    fields = tuple(field for field, _label in pg.FIRST_WORK_CARD_DEMOGRAPHICS)
    labels = tuple(label for _field, label in pg.FIRST_WORK_CARD_DEMOGRAPHICS)
    assert fields == fw.DEMOGRAPHIC_FIELDS
    assert labels == tuple(fw.DEMOGRAPHIC_LABELS[f] for f in fields)


@pytest.mark.skipif(shutil.which('pdftoppm') is None,
                    reason='poppler-utils (pdftoppm) tidak terpasang')
def test_render_pdftoppm(tmp_path):
    """Render nyata via poppler — bukan hanya bytes PDF."""
    pdf_path = tmp_path / 'card.pdf'
    pdf_path.write_bytes(_generate())
    result = subprocess.run(
        ['pdftoppm', '-f', '1', '-l', '1', '-r', '72', '-png', '-singlefile',
         str(pdf_path), str(tmp_path / 'card')],
        capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    out = tmp_path / 'card.png'
    assert out.exists() and out.stat().st_size > 1000
    with Image.open(out) as img:
        assert img.size[0] > 400 and img.size[1] > 400
