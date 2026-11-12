"""Normalisasi foto KTP FirstWork (v2.88.0 — P3/P4).

Tujuan: file KTP yang diunggah tetap terbaca rapi walau sumbernya kurang
rapi (foto miring sudah diluruskan di perangkat; PDF/legacy dirapikan di
sini). Proses berjalan lokal di server BPF — tidak ada layanan pihak ketiga.

- PDF: halaman pertama di-render via poppler (pdftoppm), lalu diperlakukan
  sebagai gambar.
- Gambar: orientasi EXIF diterapkan, margin latar seragam dipotong,
  kontras dinaikkan, diberi watermark internal, disimpan sebagai JPEG.
- Setiap hasil menghasilkan SHA-256 untuk jejak integritas (dipakai di
  kolom `ktp_sha256`).

Modul ini sengaja tidak memakai OpenCV: Pillow + numpy sudah tersedia dan
cukup untuk auto-orient, trim, enhance, serta watermark.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

# Batas aman agar file publik tidak menghabiskan memori (decompression bomb).
MAX_PIXELS = 24_000_000
MAX_SIDE = 1600
JPEG_QUALITY = 88
WATERMARK_TEXT = 'INTERNAL · REKRUTMEN BPF'
Image.MAX_IMAGE_PIXELS = 50_000_000

_FONT_CANDIDATES = (
    '/app/fonts/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)


def _render_pdf_first_page(path, workdir):
    """Render halaman 1 PDF ke JPEG 200 dpi. None bila gagal/timeout."""
    out = os.path.join(workdir, 'page')
    try:
        subprocess.run(
            ['pdftoppm', '-jpeg', '-f', '1', '-l', '1', '-r', '200',
             '-singlefile', path, out],
            check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return None
    candidate = out + '.jpg'
    return candidate if os.path.isfile(candidate) else None


def _trim_uniform_border(img):
    """Potong margin latar yang seragam (foto KTP di atas meja / scan bertepi).

    Hanya dilakukan bila tepi gambar memang hampir satu warna, dan hasil
    potongan masih mencakup sebagian besar gambar — supaya KTP yang penuh
    frame tidak ikut terpotong.
    """
    probe = img.copy()
    probe.thumbnail((600, 600))
    arr = np.asarray(probe.convert('RGB')).astype(np.int16)
    height, width, _ = arr.shape
    if height < 40 or width < 40:
        return img
    border = np.concatenate([arr[0, :, :], arr[-1, :, :],
                             arr[:, 0, :], arr[:, -1, :]])
    background = np.median(border, axis=0)
    if float(border.std()) > 14:
        return img  # latar tidak seragam — jangan menebak
    distance = np.abs(arr - background).sum(axis=2)
    mask = distance > 45
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return img
    x0, x1 = int(cols[0]), int(cols[-1])
    y0, y1 = int(rows[0]), int(rows[-1])
    area_ratio = ((x1 - x0 + 1) * (y1 - y0 + 1)) / float(width * height)
    if area_ratio < 0.35 or area_ratio > 0.985:
        return img
    scale_x = img.width / float(width)
    scale_y = img.height / float(height)
    pad_x = max(2, int(width * 0.01))
    pad_y = max(2, int(height * 0.01))
    box = (
        max(0, int((x0 - pad_x) * scale_x)),
        max(0, int((y0 - pad_y) * scale_y)),
        min(img.width, int((x1 + pad_x) * scale_x)),
        min(img.height, int((y1 + pad_y) * scale_y)),
    )
    if box[2] - box[0] < 100 or box[3] - box[1] < 60:
        return img
    return img.crop(box)


def _load_font(size):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _watermark(img, label=''):
    """Watermark tipis di pojok bawah — tidak menutupi NIK/foto."""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    size = max(11, img.width // 55)
    font = _load_font(size)
    text = WATERMARK_TEXT + (f' · {label}' if label else '')
    draw.text((8, max(0, img.height - size - 10)), text, font=font,
              fill=(40, 40, 40, 90))
    return Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')


def normalize_ktp(src_path, out_dir, label=''):
    """Hasilkan scan KTP ternormalisasi.

    Return dict: {'file', 'sha256', 'width', 'height'} atau None bila gagal.
    File asli TIDAK diubah — pemanggil tetap menyimpannya sebagai bukti.
    """
    if not src_path or not os.path.isfile(src_path):
        return None
    os.makedirs(out_dir, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix='ktpscan_')
    try:
        source = src_path
        if src_path.lower().endswith('.pdf'):
            source = _render_pdf_first_page(src_path, workdir)
            if not source:
                return None

        with Image.open(source) as raw:
            img = ImageOps.exif_transpose(raw)
            img = img.convert('RGB')
            pixels = img.width * img.height
            if pixels > MAX_PIXELS:
                ratio = (MAX_PIXELS / float(pixels)) ** 0.5
                img = img.resize((max(1, int(img.width * ratio)),
                                  max(1, int(img.height * ratio))))
            img = _trim_uniform_border(img)
            img = ImageOps.autocontrast(img, cutoff=1)
            img = ImageEnhance.Sharpness(img).enhance(1.12)
            if max(img.size) > MAX_SIDE:
                img.thumbnail((MAX_SIDE, MAX_SIDE))

        label_clean = ''.join(ch for ch in str(label or '')
                              if ch.isalnum() or ch in '-_')[:40] or 'FWKTP'
        img = _watermark(img, label_clean)
        filename = f'FWKTPSCAN_{label_clean}_{uuid.uuid4().hex[:8]}.jpg'
        out_path = os.path.join(out_dir, filename)
        img.save(out_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)

        with open(out_path, 'rb') as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        return {
            'file': filename,
            'sha256': digest,
            'width': img.width,
            'height': img.height,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
