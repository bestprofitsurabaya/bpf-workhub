"""OCR KTP FirstWork (v2.111.0).

Membantu mengisi NIK & nama dari foto KTP. Sifatnya BANTUAN — keputusan
verifikasi tetap manusia, dan pengguna wajib memeriksa hasilnya.

v2.89.0 — jalur ROI berbasis kata kunci NIK/Nama.
v2.91.0 — dua jalur (halaman penuh + ROI), voting sederhana.
v2.111.0 — model tessdata_best + voting berbobot lintas varian praproses.

Empat varian gambar dibaca berurutan (berhenti begitu NIK & nama terkumpul):

1. `gray`  : grayscale + autocontrast + upscale (teks KTP kecil).
2. `sharp` : gray + unsharp mask (tepi huruf lebih tegas).
3. `bin`   : ambang adaptif lokal (numpy) — pola guilloche, hologram, dan
   latar KTP biasanya lebih teredam daripada teks yang tajam.
4. `plain` : grayscale + upscale, tanpa autocontrast.

NIK diambil dari area ROI di kanan label "NIK" (kata-kata nilai, whitelist
angka, upscale 3–4x) plus nilai dari baris/ROI, lalu dibagi bobot lintas
varian. Kandidat dibersihkan dari kekeliruan karakter umum dan divalidasi
tanggal lahir sebelum dipilih. Baris halaman penuh dipakai
bila ROI gagal. Nama diambil dari baris "Nama" halaman penuh (ROI hanya
cadangan, karena crop sering memotong huruf).

Bila NIK & nama belum lengkap pada sudut 0°, dicoba rotasi 90/180/270 — foto
HP sering menghasilkan gambar miring atau tegak.
"""
import os
import re
import subprocess
import tempfile
from collections import Counter

import numpy as np
from PIL import Image, ImageFilter, ImageOps

OCR_TIMEOUT = 30
MIN_WIDTH = 1400
MAX_SIDE = 2400

# Bobot varian untuk voting: varian yang paling tajam/bersih lebih dipercaya.
VARIANT_WEIGHT = {'gray': 1.0, 'sharp': 3.0, 'bin': 2.0, 'plain': 1.0}

_NIK_LINE = re.compile(r'(?i)\bnik\b')
_NIK_DIGITS = re.compile(r'\d{16}')
_NAMA_PREFIX = re.compile(r'(?i)^\s*nama\b')
_NAMA_CLEAN = re.compile(r"[^A-Za-z .'\-]")

# Kekeliruan umum Tesseract pada angka; dipakai HANYA untuk kandidat NIK.
_DIGIT_FIX = str.maketrans({
    'O': '0', 'o': '0', 'Q': '0', 'D': '0', 'U': '0',
    'I': '1', 'l': '1', 'i': '1', '|': '1', '!': '1',
    'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2',
    'G': '6', 'g': '6', 'T': '7',
})


def _tesseract_available():
    try:
        subprocess.run(['tesseract', '--version'], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _prepare(src_path):
    """Grayscale + autocontrast + upscale gambar kecil (KTP sering <1400 px)."""
    with Image.open(src_path) as raw:
        img = ImageOps.exif_transpose(raw).convert('L')
        if img.width < MIN_WIDTH:
            factor = min(3.0, MIN_WIDTH / float(max(1, img.width)))
            img = img.resize((max(1, int(img.width * factor)),
                              max(1, int(img.height * factor))), Image.LANCZOS)
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        return ImageOps.autocontrast(img)


def _plain_variant(src_path):
    """Varian tanpa autocontrast — autocontrast kadang menghilangkan kontras
    halus pada foto gelap/berpola."""
    with Image.open(src_path) as raw:
        img = ImageOps.exif_transpose(raw).convert('L')
        if img.width < MIN_WIDTH:
            factor = min(3.0, MIN_WIDTH / float(max(1, img.width)))
            img = img.resize((max(1, int(img.width * factor)),
                              max(1, int(img.height * factor))), Image.LANCZOS)
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        return img


def _variants(base, plain_base):
    """Varian praproses; urutan menentukan prioritas voting."""
    yield 'gray', base
    yield 'sharp', base.filter(ImageFilter.UnsharpMask(
        radius=2, percent=140, threshold=3))
    # Ambang adaptif: teks gelap di atas latar lokal yang terang.
    arr = np.asarray(base, dtype=np.float32)
    local = np.asarray(base.filter(ImageFilter.BoxBlur(radius=25)),
                       dtype=np.float32)
    text_mask = (local - arr) > 10
    yield 'bin', Image.fromarray(np.where(text_mask, 0, 255).astype(np.uint8), 'L')
    yield 'plain', plain_base


def _save_temp(img):
    handle, path = tempfile.mkstemp(suffix='.png', prefix='ktpocr_')
    os.close(handle)
    img.save(path, 'PNG')
    return path


def _ocr_tsv(path, psm='6', whitelist=None, lang='ind'):
    cmd = ['tesseract', path, 'stdout', '-l', lang, '--oem', '1', '--psm', psm]
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
                      'width': int(cols[8] or 0), 'height': int(cols[9] or 0),
                      'line': (cols[2], cols[3], cols[4])})
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


def _digits_only(text):
    return re.sub(r'\D', '', str(text or '').translate(_DIGIT_FIX))


def _nik_candidates(lines, roi=False, variant=''):
    candidates = []
    for line in lines:
        digits = _digits_only(line['text'])
        labelled = bool(_NIK_LINE.search(line['text']))
        for match in _NIK_DIGITS.finditer(digits):
            candidates.append({'nik': match.group(0),
                               'conf': line['conf'],
                               'labelled': labelled,
                               'roi': roi,
                               'variant': variant})
    return candidates


def _clean_name(value):
    text = _NAMA_CLEAN.sub(' ', str(value or ''))
    text = re.sub(r'\s+', ' ', text).strip(" .-'")
    words = [w for w in text.split(' ') if w]
    out = []
    for word in words:
        letters = re.sub(r'[^A-Za-z]', '', word)
        if len(letters) < 2:
            continue
        # KTP umumnya huruf kapital: perbaiki 'BILi' -> 'BILI'.
        if letters.isupper() or any(c.isupper() for c in letters):
            word = word.upper()
        else:
            word = word.capitalize()
        out.append(word)
    # Sisa satu huruf di ujung hampir selalu artefak OCR ('... SUSILO a').
    if len(out) >= 2 and len(re.sub(r"[^A-Za-z]", '', out[-1])) == 1:
        out.pop()
    text = ' '.join(out)
    if len(text) >= 3 and re.search(r'[A-Za-z]{3}', text):
        return text
    return ''


def _nama_candidates(lines, roi=False, variant=''):
    candidates = []
    for line in lines:
        text = line['text'].strip()
        if not _NAMA_PREFIX.search(text):
            continue
        value = _clean_name(_NAMA_PREFIX.sub('', text).lstrip(' :.-'))
        if value:
            candidates.append({'nama': value, 'conf': line['conf'],
                               'roi': roi, 'variant': variant})
    return candidates


def _find_anchor(words, keyword):
    found = None
    for word in words:
        letters = re.sub(r'[^A-Z]', '', word['text'].upper())
        if letters.startswith(keyword):
            if found is None or word['conf'] > found['conf']:
                found = word
    return found


def _right_box(anchor, img, width_frac):
    """Area di kanan label, setinggi baris label itu."""
    x0 = min(img.width - 8, anchor['left'] + anchor['width'] + 2)
    y0 = max(0, anchor['top'] - int(anchor['height'] * 0.7))
    x1 = min(img.width, x0 + int(img.width * width_frac))
    y1 = min(img.height, anchor['top'] + int(anchor['height'] * 1.7))
    if x1 - x0 < 20 or y1 - y0 < 12:
        return None
    return (x0, y0, x1, y1)


def _region_ocr(img, box, whitelist=None, psm='7'):
    """Baca satu area kecil; kembalikan teks + keyakinan."""
    if not box:
        return None
    crop = img.crop(box)
    canvas = Image.new('L', (crop.width + 16, crop.height + 16), 255)
    canvas.paste(crop, (8, 8))
    if canvas.width < 900:
        factor = 2
        canvas = canvas.resize((canvas.width * factor, canvas.height * factor),
                               Image.LANCZOS)
    path = _save_temp(canvas)
    try:
        words = [w for w in _words_from_tsv(_ocr_tsv(path, psm, whitelist))
                 if w['text'].strip()]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not words:
        return None
    confs = [w['conf'] for w in words if w['conf'] > 0]
    # Tesseract sering mengembalikan keyakinan 0 pada crop whitelist;
    # beri nilai netral agar kandidat ROI masih bisa menang voting.
    conf = (sum(confs) / len(confs)) if confs else 70.0
    return {'text': ' '.join(w['text'] for w in words), 'conf': conf}


def _ocr_words(img, psm='7', whitelist=None, lang='ind'):
    """Baca kata dari PIL Image (crop) — TSV untuk tahu keyakinan."""
    path = _save_temp(img)
    try:
        return [w for w in _words_from_tsv(_ocr_tsv(path, psm, whitelist, lang))
                if w['text'].strip()]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _value_box(words):
    """Kotak gabungan kata-kata nilai di kanan label pada baris yang sama."""
    if not words:
        return None
    x0 = max(0, min(w['left'] for w in words) - 4)
    y0 = max(0, min(w['top'] for w in words) - 4)
    x1 = max(w['left'] + w['width'] for w in words) + 4
    y1 = max(w['top'] + w['height'] for w in words) + 4
    if x1 - x0 < 12 or y1 - y0 < 8:
        return None
    return (x0, y0, x1, y1)


def _nik_token_hits(img, words, variant):
    """Baca nilai NIK dari kotak kata-kata di kanan label 'NIK'.

    Angka KTP dicetak rapat dan jelas; dengan crop tepat + whitelist angka +
    upscale 3–4×, Tesseract jauh lebih akurat daripada membaca halaman penuh.
    """
    anchor = _find_anchor(words, 'NIK')
    if not anchor:
        return []
    line_words = [w for w in words
                  if w['line'] == anchor['line']
                  and w['left'] >= anchor['left'] + max(2, anchor['width'] - 2)]
    box = _value_box(line_words)
    if not box:
        return []
    x0, y0, x1, y1 = box
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 12 or y1 - y0 < 8:
        return []
    crop = img.crop((x0, y0, x1, y1))
    hits = {}
    for scale in (3, 4):
        big = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        big = big.filter(ImageFilter.UnsharpMask(2, 120, 3))
        canvas = Image.new('L', (big.width + 16, big.height + 16), 255)
        canvas.paste(big, (8, 8))
        for psm in ('7', '8', '13'):
            read = _ocr_words(canvas, psm, '0123456789')
            digits = _digits_only(' '.join(w['text'] for w in read))
            confs = [w['conf'] for w in read if w['conf'] > 0]
            conf = (sum(confs) / len(confs)) if confs else 70.0
            for match in _NIK_DIGITS.finditer(digits):
                nik = match.group(0)
                hits[nik] = max(hits.get(nik, 0.0), conf)
    return [{'nik': nik, 'conf': conf, 'roi': True, 'token': True,
             'variant': variant} for nik, conf in hits.items()]


_DATE_RE = re.compile(r'(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{2,4})')


def _birth_date_from_lines(lines):
    """Tanggal lahir dari baris 'Tempat/Tgl Lahir' — (dd, mm, yy) atau None."""
    for line in lines:
        text = line['text']
        if 'lahir' not in text.lower():
            continue
        match = _DATE_RE.search(text)
        if not match:
            continue
        day, month, year = (int(match.group(1)), int(match.group(2)),
                            int(match.group(3)))
        if year < 100:
            year += 1900 if year > 30 else 2000
        if 1 <= day <= 31 and 1 <= month <= 12:
            return (day, month, f'{year % 100:02d}')
    return None


def _nik_birth(nik):
    day, month, year = int(nik[6:8]), int(nik[8:10]), int(nik[10:12])
    if day > 40:  # perempuan: tanggal + 40
        day -= 40
    return (day, month, f'{year:02d}')


def _aggregate_nik(candidates, birth=None):
    """Gabung kandidat NIK: bobot varian + ROI + token + cocok tanggal lahir."""
    agg = {}
    for c in candidates:
        nik = c.get('nik') or ''
        if len(nik) != 16 or not _nik_date_valid(nik):
            continue
        weight = VARIANT_WEIGHT.get(c.get('variant') or '', 1.0)
        if c.get('roi'):
            weight *= 3.0
        if c.get('token'):
            weight *= 2.0
        if birth:
            if _nik_birth(nik) == birth:
                weight *= 1.5
            else:
                weight *= 0.5
        item = agg.setdefault(nik, {'nik': nik, 'weight': 0.0, 'conf': 0.0})
        item['weight'] += weight
        item['conf'] = max(item['conf'], float(c.get('conf') or 0))
    return list(agg.values())


def _pick_nik(aggregated):
    if not aggregated:
        return None
    aggregated.sort(key=lambda c: (c['weight'], c['conf']), reverse=True)
    return aggregated[0]


def _aggregate_nama(candidates):
    agg = {}
    for c in candidates:
        nama = c.get('nama') or ''
        weight = VARIANT_WEIGHT.get(c.get('variant') or '', 1.0)
        if c.get('roi'):
            weight *= 0.5  # ROI nama sering terpotong; halaman penuh lebih aman
        item = agg.setdefault(nama, {'nama': nama, 'weight': 0.0, 'conf': 0.0})
        item['weight'] += weight
        item['conf'] = max(item['conf'], float(c.get('conf') or 0))
    return list(agg.values())


def _pick_nama(aggregated):
    if not aggregated:
        return None
    aggregated.sort(key=lambda c: (c['weight'], c['conf']), reverse=True)
    return aggregated[0]


def extract_ktp(src_path):
    """Baca NIK & nama dari foto KTP.

    Return {'nik', 'nama', 'confidence', 'lines'}; nilai kosong bila tidak
    ditemukan. Raise RuntimeError bila mesin OCR tidak tersedia.
    """
    if not src_path or not os.path.isfile(src_path):
        return {'nik': '', 'nama': '', 'confidence': 0, 'lines': 0}
    if not _tesseract_available():
        raise RuntimeError('Mesin OCR belum tersedia di server ini.')

    base = _prepare(src_path)
    plain_base = _plain_variant(src_path)
    lines_count = 0
    nik = None
    nama = None
    try:
        for angle in (0, 90, 180, 270):
            rotated = base.rotate(angle, expand=True, fillcolor=255) if angle else base
            rotated_plain = (plain_base.rotate(angle, expand=True, fillcolor=255)
                             if angle else plain_base)
            nik_candidates = []
            nama_candidates = []
            birth = None
            for variant, img in _variants(rotated, rotated_plain):
                try:
                    path = _save_temp(img)
                    try:
                        tsv = _ocr_tsv(path, '6')
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    words = _words_from_tsv(tsv)
                    lines = _lines_from_tsv(tsv)
                    lines_count = max(lines_count, len(lines))
                    nik_candidates.extend(
                        _nik_candidates(lines, roi=False, variant=variant))
                    nama_candidates.extend(
                        _nama_candidates(lines, roi=False, variant=variant))
                    if birth is None:
                        birth = _birth_date_from_lines(lines)

                    # NIK: crop kata-kata nilai di kanan label + voting
                    # lintas varian. Ini jalur paling akurat.
                    nik_candidates.extend(_nik_token_hits(img, words, variant))

                    nik_anchor = _find_anchor(words, 'NIK')
                    if nik_anchor:
                        roi_hits = {}
                        for psm in ('7', '13'):
                            region = _region_ocr(
                                img, _right_box(nik_anchor, img, 0.7),
                                '0123456789', psm)
                            if region:
                                for match in _NIK_DIGITS.finditer(
                                        _digits_only(region['text'])):
                                    nik = match.group(0)
                                    roi_hits[nik] = max(
                                        roi_hits.get(nik, 0.0),
                                        float(region['conf'] or 0))
                        # Satu varian = satu suara, walau dibaca dua PSM.
                        for nik, conf in roi_hits.items():
                            nik_candidates.append({'nik': nik, 'conf': conf,
                                                   'roi': True,
                                                   'variant': variant})

                    # Nama dari ROI hanya bila baris halaman penuh belum ada.
                    if not _pick_nama(_aggregate_nama(nama_candidates)):
                        nama_anchor = _find_anchor(words, 'NAMA')
                        if nama_anchor:
                            region = _region_ocr(
                                img, _right_box(nama_anchor, img, 0.95))
                            if region:
                                value = _clean_name(region['text'])
                                if value:
                                    nama_candidates.append(
                                        {'nama': value, 'conf': region['conf'],
                                         'roi': True, 'variant': variant})
                except (RuntimeError, OSError, ValueError):
                    continue

                nik = _pick_nik(_aggregate_nik(nik_candidates, birth))
                nama = _pick_nama(_aggregate_nama(nama_candidates))
                # Berhenti cepat hanya bila NIK punya dukungan kuat
                # (satu varian tajam = 6, atau dua varian lemah).
                if nik and nama and nik.get('weight', 0.0) >= 6.0:
                    break

            nik = _pick_nik(_aggregate_nik(nik_candidates, birth))
            nama = _pick_nama(_aggregate_nama(nama_candidates))
            if nik and nama:
                break
            # Fallback halaman penuh (sparse) bila varian normal gagal.
            try:
                sparse_path = _save_temp(rotated)
                try:
                    sparse = _lines_from_tsv(_ocr_tsv(sparse_path, '11'))
                finally:
                    try:
                        os.remove(sparse_path)
                    except OSError:
                        pass
            except (RuntimeError, OSError):
                continue
            nik_candidates.extend(
                _nik_candidates(sparse, roi=False, variant='sparse'))
            nama_candidates.extend(
                _nama_candidates(sparse, roi=False, variant='sparse'))
            nik = _pick_nik(_aggregate_nik(nik_candidates, birth))
            nama = _pick_nama(_aggregate_nama(nama_candidates))
            if nik and nama:
                break
    except (RuntimeError, OSError, ValueError):
        # Mesin OCR rusak total: kembalikan apa pun yang sempat terkumpul.
        nik = nik or None
        nama = nama or None

    nik = nik or {}
    nama = nama or {}
    confidence = max(float(nik.get('conf') or 0), float(nama.get('conf') or 0))
    return {
        'nik': nik.get('nik') or '',
        'nama': nama.get('nama') or '',
        'confidence': int(round(confidence)),
        'lines': lines_count,
    }
