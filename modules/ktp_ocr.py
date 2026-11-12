"""OCR KTP FirstWork (v2.89.0 — P5).

Fungsi: membantu mengisi NIK & nama dari foto KTP. Sifatnya BANTUAN —
keputusan verifikasi tetap manusia, dan pengguna wajib memeriksa hasilnya.

Catatan riset: Tesseract `ind` pada KTP mentah akurasinya rendah (~40%),
tetapi naik ke ~65–90% setelah grayscale + kontras (CLAHE/threshold).
Karena itu modul ini selalu melakukan praproses, dan hanya mengembalikan
NIK bila 16 digitnya lolos validasi tanggal lahir.
"""
import os
import re
import subprocess
import tempfile

from PIL import Image, ImageOps

MAX_SIDE = 1600
OCR_TIMEOUT = 20

_NIK_LINE = re.compile(r'(?i)\bnik\b')
_NIK_DIGITS = re.compile(r'\d{16}')
_NAMA_PREFIX = re.compile(r'(?i)^\s*nama\b')
_NAMA_CLEAN = re.compile(r"[^A-Za-z .'\-]")


def _tesseract_available():
    try:
        subprocess.run(['tesseract', '--version'], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _preprocess(src_path, out_path):
    with Image.open(src_path) as raw:
        img = ImageOps.exif_transpose(raw).convert('L')
        img = ImageOps.autocontrast(img)
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        img.save(out_path, 'PNG')


def _run_tesseract(path):
    proc = subprocess.run(
        ['tesseract', path, 'stdout', '-l', 'ind',
         '--oem', '1', '--psm', '6', 'tsv'],
        capture_output=True, text=True, timeout=OCR_TIMEOUT)
    if proc.returncode != 0:
        message = (proc.stderr or '').strip().splitlines()
        raise RuntimeError(message[-1][:200] if message else 'Tesseract gagal')
    return proc.stdout


def _lines_from_tsv(tsv):
    """Gabungkan kata (level 5) menjadi baris + rata-rata keyakinan."""
    grouped = {}
    for row in (tsv or '').splitlines()[1:]:
        cols = row.split('\t')
        if len(cols) < 12 or cols[0] != '5':
            continue
        text = cols[11].strip()
        if not text:
            continue
        key = (cols[2], cols[3], cols[4])
        entry = grouped.setdefault(
            key, {'words': [], 'confs': [], 'top': int(cols[7] or 0)})
        entry['words'].append(text)
        try:
            conf = float(cols[10])
        except ValueError:
            conf = -1
        if conf >= 0:
            entry['confs'].append(conf)
    lines = []
    for key in sorted(grouped):
        entry = grouped[key]
        conf = (sum(entry['confs']) / len(entry['confs'])) if entry['confs'] else 0
        lines.append({'text': ' '.join(entry['words']),
                      'conf': conf, 'top': entry['top']})
    return lines


def _nik_date_valid(nik):
    try:
        day = int(nik[6:8])
        month = int(nik[8:10])
    except (TypeError, ValueError):
        return False
    if month > 40:  # perempuan: tanggal + 40
        month -= 40
    return 1 <= day <= 31 and 1 <= month <= 12


def _pick_nik(lines):
    """Pilih satu NIK paling meyakinkan; None bila tidak ada yang valid."""
    candidates = []
    for line in lines:
        text = line['text']
        digits = re.sub(r'\D', '', text)
        # Format lazim: "NIK : 3171 0101 0190 0001" (spasi/titik).
        if _NIK_LINE.search(text) and len(digits) >= 16:
            for match in _NIK_DIGITS.finditer(digits):
                candidates.append({'nik': match.group(0),
                                   'conf': line['conf'], 'labelled': True})
        for match in _NIK_DIGITS.finditer(digits):
            candidates.append({'nik': match.group(0),
                               'conf': line['conf'], 'labelled': False})
    if not candidates:
        return None
    # Prioritaskan baris berlabel NIK & tanggal lahir yang masuk akal.
    candidates.sort(key=lambda c: (c['labelled'], _nik_date_valid(c['nik']),
                                   c['conf']), reverse=True)
    best = candidates[0]
    if not _nik_date_valid(best['nik']):
        return None
    return best


def _pick_nama(lines):
    for line in lines:
        text = line['text'].strip()
        if not _NAMA_PREFIX.search(text):
            continue
        value = _NAMA_PREFIX.sub('', text)
        value = value.lstrip(' :.-')
        value = _NAMA_CLEAN.sub(' ', value)
        value = re.sub(r'\s+', ' ', value).strip(" .-'")
        if len(value) >= 3 and re.search(r'[A-Za-z]{3}', value):
            return {'nama': value, 'conf': line['conf']}
    return None


def extract_ktp(src_path):
    """Baca NIK & nama dari foto KTP.

    Return {'nik', 'nama', 'confidence', 'lines'}; nilai kosong bila tidak
    ditemukan. Raise RuntimeError bila mesin OCR tidak tersedia.
    """
    if not src_path or not os.path.isfile(src_path):
        return {'nik': '', 'nama': '', 'confidence': 0, 'lines': 0}
    if not _tesseract_available():
        raise RuntimeError('Mesin OCR belum tersedia di server ini.')
    handle, prepared = tempfile.mkstemp(suffix='.png', prefix='ktpocr_')
    os.close(handle)
    try:
        _preprocess(src_path, prepared)
        lines = _lines_from_tsv(_run_tesseract(prepared))
    finally:
        try:
            os.remove(prepared)
        except OSError:
            pass
    nik = _pick_nik(lines) or {}
    nama = _pick_nama(lines) or {}
    confidence = max(float(nik.get('conf') or 0), float(nama.get('conf') or 0))
    return {
        'nik': nik.get('nik') or '',
        'nama': nama.get('nama') or '',
        'confidence': int(round(confidence)),
        'lines': len(lines),
    }
