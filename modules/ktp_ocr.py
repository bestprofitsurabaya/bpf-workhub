"""OCR KTP FirstWork (v2.91.0 — P5 lanjutan).

Membantu mengisi NIK & nama dari foto KTP. Sifatnya BANTUAN — keputusan
verifikasi tetap manusia, dan pengguna wajib memeriksa hasilnya.

v2.91.0 — dua jalur (dual-pipeline), mengikuti temuan riset bahwa Tesseract
pada KTP mentah hanya ~40–65% dan naik bila teks dicari per area:
1. Halaman penuh (`--psm 6`) untuk konteks baris.
2. ROI: cari kata kunci "NIK"/"Nama" dari kotak kata Tesseract, potong area
   di kanannya, lalu baca ulang (`--psm 7`) — NIK dengan whitelist angka.
3. Jika NIK belum ditemukan, ulangi halaman penuh dengan `--psm 11` (sparse).
Kandidat digabung, difilter tanggal-lahir valid, lalu dipilih dengan voting
(frekuensi) dan keyakinan Tesseract.
"""
import os
import re
import subprocess
import tempfile
from collections import Counter

from PIL import Image, ImageOps

MAX_SIDE = 1600
OCR_TIMEOUT = 25
MIN_WIDTH = 900

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


def _prepare(src_path, out_path):
    """Grayscale + autocontrast + upscale gambar kecil (KTP sering <900 px)."""
    with Image.open(src_path) as raw:
        img = ImageOps.exif_transpose(raw).convert('L')
        if img.width < MIN_WIDTH:
            factor = min(3.0, MIN_WIDTH / float(max(1, img.width)))
            img = img.resize((max(1, int(img.width * factor)),
                              max(1, int(img.height * factor))), Image.LANCZOS)
        img = ImageOps.autocontrast(img)
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        img.save(out_path, 'PNG')
        return img


def _ocr_tsv(path, psm='6', whitelist=None):
    cmd = ['tesseract', path, 'stdout', '-l', 'ind', '--oem', '1', '--psm', psm]
    if whitelist:
        cmd += ['-c', f'tessedit_char_whitelist={whitelist}']
    cmd.append('tsv')
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=OCR_TIMEOUT)
    if proc.returncode != 0:
        message = (proc.stderr or '').strip().splitlines()
        raise RuntimeError(message[-1][:200] if message else 'Tesseract gagal')
    return proc.stdout


def _words_from_tsv(tsv):
    words = []
    for row in (tsv or '').splitlines()[1:]:
        cols = row.split('\t')
        if len(cols) < 12 or cols[0] != '5':
            continue
        text = cols[11].strip()
        if not text:
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            conf = -1
        words.append({'text': text, 'conf': conf,
                      'left': int(cols[6] or 0), 'top': int(cols[7] or 0),
                      'width': int(cols[8] or 0), 'height': int(cols[9] or 0)})
    return words


def _lines_from_tsv(tsv):
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


def _nik_candidates(lines):
    candidates = []
    for line in lines:
        text = line['text']
        digits = re.sub(r'\D', '', text)
        labelled = bool(_NIK_LINE.search(text))
        for match in _NIK_DIGITS.finditer(digits):
            candidates.append({'nik': match.group(0), 'conf': line['conf'],
                               'labelled': labelled})
    return candidates


def _pick_nik(candidates):
    """Pilih NIK: filter tanggal valid dulu, lalu voting + keyakinan."""
    valid = [c for c in candidates
             if len(str(c.get('nik') or '')) == 16 and _nik_date_valid(c['nik'])]
    if not valid:
        return None
    counts = Counter(c['nik'] for c in valid)

    def score(candidate):
        # Label NIK dari ROI/halaman lebih dipercaya daripada kebetulan
        # 16 digit di alamat; frekuensi hanya penguat kecil.
        return (float(candidate.get('conf') or 0)
                + (30.0 if candidate.get('labelled') else 0.0)
                + 2.0 * counts[candidate['nik']])

    return max(valid, key=score)


def _clean_name(value):
    text = _NAMA_CLEAN.sub(' ', str(value or ''))
    text = re.sub(r'\s+', ' ', text).strip(" .-'")
    if len(text) >= 3 and re.search(r'[A-Za-z]{3}', text):
        return text
    return ''


def _nama_candidates(lines):
    candidates = []
    for line in lines:
        text = line['text'].strip()
        if not _NAMA_PREFIX.search(text):
            continue
        value = _clean_name(_NAMA_PREFIX.sub('', text).lstrip(' :.-'))
        if value:
            candidates.append({'nama': value, 'conf': line['conf'],
                               'labelled': True})
    return candidates


def _pick_nama(candidates):
    usable = [c for c in candidates if c.get('nama')]
    if not usable:
        return None
    usable.sort(key=lambda c: (bool(c.get('labelled')),
                               float(c.get('conf') or 0),
                               len(c['nama'])), reverse=True)
    return usable[0]


def _find_anchor(words, keyword):
    found = None
    for word in words:
        letters = re.sub(r'[^A-Z]', '', word['text'].upper())
        if letters.startswith(keyword):
            if found is None or word['conf'] > found['conf']:
                found = word
    return found


def _right_box(anchor, img, width_frac):
    x0 = min(img.width - 8, anchor['left'] + anchor['width'] + 3)
    y0 = max(0, anchor['top'] - int(anchor['height'] * 0.8))
    x1 = min(img.width, anchor['left'] + int(img.width * width_frac))
    y1 = min(img.height, anchor['top'] + int(anchor['height'] * 1.9))
    if x1 - x0 < 20 or y1 - y0 < 12:
        return None
    return (x0, y0, x1, y1)


def _region_ocr(img, box, whitelist=None):
    """Baca satu area kecil dengan psm 7; kembalikan teks + keyakinan."""
    if not box:
        return None
    crop = img.crop(box)
    canvas = Image.new('L', (crop.width + 16, crop.height + 16), 255)
    canvas.paste(crop, (8, 8))
    if canvas.width < 760:
        factor = 2
        canvas = canvas.resize((canvas.width * factor, canvas.height * factor),
                               Image.LANCZOS)
    handle, path = tempfile.mkstemp(suffix='.png', prefix='ktpocr_roi_')
    os.close(handle)
    try:
        canvas.save(path, 'PNG')
        words = [w for w in _words_from_tsv(_ocr_tsv(path, '7', whitelist))
                 if w['text'].strip()]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not words:
        return None
    confs = [w['conf'] for w in words if w['conf'] >= 0]
    return {'text': ' '.join(w['text'] for w in words),
            'conf': (sum(confs) / len(confs)) if confs else 0}


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
        img = _prepare(src_path, prepared)
        tsv = _ocr_tsv(prepared, '6')
        words = _words_from_tsv(tsv)
        lines = _lines_from_tsv(tsv)

        nik_candidates = _nik_candidates(lines)
        nama_candidates = _nama_candidates(lines)

        nik_anchor = _find_anchor(words, 'NIK')
        if nik_anchor:
            region = _region_ocr(img, _right_box(nik_anchor, img, 0.62), '0123456789')
            if region:
                digits = re.sub(r'\D', '', region['text'])
                for match in _NIK_DIGITS.finditer(digits):
                    nik_candidates.append({'nik': match.group(0),
                                           'conf': region['conf'],
                                           'labelled': True})

        nama_anchor = _find_anchor(words, 'NAMA')
        if nama_anchor:
            region = _region_ocr(img, _right_box(nama_anchor, img, 0.68))
            if region:
                value = _clean_name(region['text'])
                if value:
                    nama_candidates.append({'nama': value,
                                            'conf': region['conf'],
                                            'labelled': True})

        if not _pick_nik(nik_candidates):
            sparse = _lines_from_tsv(_ocr_tsv(prepared, '11'))
            nik_candidates.extend(_nik_candidates(sparse))
            nama_candidates.extend(_nama_candidates(sparse))

        nik = _pick_nik(nik_candidates) or {}
        nama = _pick_nama(nama_candidates) or {}
        confidence = max(float(nik.get('conf') or 0), float(nama.get('conf') or 0))
        return {
            'nik': nik.get('nik') or '',
            'nama': nama.get('nama') or '',
            'confidence': int(round(confidence)),
            'lines': len(lines),
        }
    finally:
        try:
            os.remove(prepared)
        except OSError:
            pass
