"""Regression: kop surat PDF harus benar-benar simetris (v2.29.10).

Latar belakang: baris subjudul & alamat di header sempat bergeser ke kanan
~5 mm karena `new_x="LMARGIN"` mengembalikan x ke margin kiri sementara
`r_margin` diset 0 — kotak cell jadi asimetris sehingga teks rata-tengah
tidak berada di tengah halaman. Perbaikan: `set_x(0)` sebelum tiap baris kop.

Test ini mengukur posisi kata via `pdftotext -bbox` (poppler) di tipe PDF
portrait & landscape dan memastikan 3 baris kop pertama (nama perusahaan,
subjudul, alamat/kontak) tepat di tengah halaman (toleransi < 1.5 pt).
Bila `pdftotext` tidak tersedia, test di-skip (bukan gagal).
"""
import re
import shutil
import subprocess

import pytest

from modules.pdf_generator import (
    WaterReceiptPDF, PDFReportCompact, BBMReportPDF, BranchSummaryPDF,
    OvertimeReportPDF, ApplicantReportPDF, AssetReportPDF, ConsolidatedReportPDF,
)

# (kelas, orientasi) — semua menurunkan header() kop yang sama.
PDF_CASES = [
    (WaterReceiptPDF, 'portrait'),
    (PDFReportCompact, 'portrait'),
    (BBMReportPDF, 'landscape'),
    (BranchSummaryPDF, 'landscape'),
    (OvertimeReportPDF, 'landscape'),
    (ApplicantReportPDF, 'landscape'),
    (AssetReportPDF, 'landscape'),
    (ConsolidatedReportPDF, 'landscape'),
]

TOLERANCE_PT = 1.5


def _pdf_bytes(pdf):
    raw = pdf.output(dest='S')
    return raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)


def _word_rows(html_path):
    """Cluster kata per baris teks (berdasarkan y-mid). Return list (y, list words)."""
    html = open(html_path, encoding='utf-8', errors='ignore').read()
    words = []
    for m in re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', html, re.S):
        words.append((float(m[0]), float(m[1]), float(m[2]), float(m[3]), m[4]))
    rows = []
    for x0, y0, x1, y1, text in words:
        ym = (y0 + y1) / 2
        for rr in rows:
            if abs(rr[0] - ym) < 5:
                rr[1].append((x0, x1, text))
                break
        else:
            rows.append([ym, [(x0, x1, text)]])
    rows.sort(key=lambda z: z[0])
    return rows


@pytest.mark.parametrize('pdf_cls,orientation', PDF_CASES, ids=[c.__name__ for c, _ in PDF_CASES])
def test_letterhead_lines_centered(pdf_cls, orientation, tmp_path):
    if shutil.which('pdftotext') is None:
        pytest.skip('pdftotext (poppler-utils) tidak tersedia — skip cek geometri kop')
    pdf = pdf_cls()
    pdf.add_page()  # header() otomatis digambar (kop 3 baris + garis)
    raw = _pdf_bytes(pdf)
    assert raw.startswith(b'%PDF'), 'output bukan PDF'

    pdf_file = tmp_path / 'out.pdf'
    pdf_file.write_bytes(raw)
    html_file = tmp_path / 'out.html'
    subprocess.run(['pdftotext', '-bbox', str(pdf_file), str(html_file)], check=True)

    rows = _word_rows(str(html_file))
    # 3 baris pertama = kop: nama perusahaan, subjudul, alamat/kontak.
    assert len(rows) >= 3, 'kop harus punya minimal 3 baris (nama, subjudul, alamat)'

    center = pdf.w_pt / 2.0
    for idx, (y, wlist) in enumerate(rows[:3]):
        texts = [t for _, _, t in wlist]
        assert texts, f'baris kop #{idx + 1} tidak punya teks'
        minx = min(a for a, _, _ in wlist)
        maxx = max(b for _, b, _ in wlist)
        delta = (minx + maxx) / 2.0 - center
        assert abs(delta) < TOLERANCE_PT, (
            f'{pdf_cls.__name__} baris kop #{idx + 1} tidak di tengah '
            f'(delta {delta:+.1f} pt vs toleransi ±{TOLERANCE_PT} pt): '
            f'{" ".join(texts)[:70]!r}'
        )


def test_letterhead_subtitle_and_address_present(tmp_path):
    """Tanpa DB (fallback default) kop tetap memuat subjudul & alamat HO Jakarta."""
    if shutil.which('pdftotext') is None:
        pytest.skip('pdftotext (poppler-utils) tidak tersedia — skip')
    pdf = WaterReceiptPDF()
    pdf.add_page()
    pdf_file = tmp_path / 'w.pdf'
    pdf_file.write_bytes(_pdf_bytes(pdf))
    html_file = tmp_path / 'w.html'
    subprocess.run(['pdftotext', '-bbox', str(pdf_file), str(html_file)], check=True)
    rows = _word_rows(str(html_file))
    top = ' '.join(t for _, wl in rows[:3] for _, _, t in wl)
    assert 'Kantor Pusat' in top and 'Jakarta' in top, 'subjudul HO Jakarta hilang'
    assert 'Equity Tower' in top, 'alamat HO Jakarta hilang di kop'
