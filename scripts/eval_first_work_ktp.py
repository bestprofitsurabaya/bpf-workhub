"""Evaluasi pipeline scan + OCR KTP FirstWork (v2.90.0).

Dipakai untuk mengukur dampak perubahan sebelum/sesudah — bukan untuk
menyimpan data pribadi. Dua mode:

1. Sintetis (default) — membuat KTP palsu dengan variasi rotasi, blur,
   pencahayaan, dan JPEG; ground truth diketahui pasti.
       python3 scripts/eval_first_work_ktp.py --synthetic 24 --out /tmp/eval.json

2. Korpus nyata ber-consent — folder gambar + truth.json:
       [{"file": "ktp01.jpg", "nik": "3171...", "nama": "BUDI SANTOSO"}, ...]
       python3 scripts/eval_first_work_ktp.py --corpus /data/ktp --truth /data/truth.json

Catatan: akurasi sintetis BUKAN proksi akurasi lapangan. Ia hanya baseline
yang konsisten untuk membandingkan perubahan pipeline.
"""
import argparse
import difflib
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ktp_ocr import extract_ktp  # noqa: E402
from modules.ktp_scan import normalize_ktp  # noqa: E402

FONT = '/app/fonts/DejaVuSans.ttf'
PROVINCES = ('DKI JAKARTA', 'JAWA BARAT', 'JAWA TIMUR', 'JAWA TENGAH')
NAMES = (
    'BUDI SANTOSO', 'SITI AMINAH', 'AGUS PRAYITNO', 'DEWI LESTARI',
    'RIZKY PRATAMA', 'NUR HIDAYAH', 'ANDI WIBAWA', 'PUTRI ANGGRAINI',
    'HENDRA GUNAWAN', 'MAYA SARI', 'FAJAR NUGROHO', 'INDRA KUSUMA',
)


def _digits(nik):
    return ' '.join(nik[i:i + 4] for i in range(0, 16, 4))


def _pick_nik(rng):
    province = rng.choice(('31', '32', '33', '35'))
    district = rng.randint(10, 99)  # 2 digit kabupaten/kota
    village = rng.randint(10, 99)   # 2 digit kecamatan
    day = rng.randint(1, 28)
    month = rng.randint(1, 12)
    if rng.random() < 0.5:
        month += 40  # perempuan
    year = rng.randint(70, 99)
    serial = rng.randint(1, 9999)
    # 16 digit: provinsi(2) kab(2) kec(2) dd(2) mm(2) yy(2) serial(4)
    nik = (f'{province}{district:02d}{village:02d}{day:02d}{month:02d}'
           f'{year:02d}{serial:04d}')
    assert len(nik) == 16, nik
    return nik


def _make_card(truth, path, rng):
    img = Image.new('RGB', (1000, 630), (248, 246, 238))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 28)
    bold = ImageFont.truetype(FONT, 34)
    draw.rectangle([0, 0, 1000, 70], fill=(214, 222, 236))
    draw.text((28, 18), 'PROVINSI ' + rng.choice(PROVINCES), font=bold, fill=(20, 24, 34))
    draw.text((28, 100), 'NIK', font=font, fill=(20, 20, 20))
    draw.text((110, 100), ': ' + _digits(truth['nik']), font=font, fill=(20, 20, 20))
    draw.text((28, 170), 'Nama', font=font, fill=(20, 20, 20))
    draw.text((110, 170), ': ' + truth['nama'], font=font, fill=(20, 20, 20))
    draw.text((28, 240), 'Tempat/Tgl Lahir', font=font, fill=(20, 20, 20))
    draw.text((330, 240), ': JAKARTA, 01-01-1990', font=font, fill=(20, 20, 20))
    draw.text((28, 310), 'Alamat', font=font, fill=(20, 20, 20))
    draw.text((110, 310), ': JL MERDEKA NO 1', font=font, fill=(20, 20, 20))
    draw.rectangle([760, 190, 960, 400], fill=(232, 228, 218))  # area foto
    img.save(path, 'JPEG', quality=rng.randint(82, 95))


def _degrade(path, out_path, rng):
    img = Image.open(path).convert('RGB')
    angle = rng.uniform(-9, 9)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(248, 246, 238))
    if rng.random() < 0.6:
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.4, 1.6)))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.72, 1.18))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.8, 1.25))
    if rng.random() < 0.35:
        draw = ImageDraw.Draw(img, 'RGBA')
        x = rng.randint(80, max(120, img.width - 200))
        y = rng.randint(60, max(120, img.height - 160))
        draw.ellipse([x, y, x + 220, y + 120], fill=(255, 255, 255, 110))
    img.save(out_path, 'JPEG', quality=rng.randint(55, 88))


def _norm_text(value):
    return re.sub(r'[^A-Z ]', '', str(value or '').upper()).strip()


def _score(truth, result):
    nik_ok = bool(result.get('nik')) and result.get('nik') == truth['nik']
    name_got = _norm_text(result.get('nama'))
    name_want = _norm_text(truth['nama'])
    return {
        'nik_ok': nik_ok,
        'nik_found': bool(result.get('nik')),
        'name_ok': bool(name_got) and name_got == name_want,
        'name_sim': round(difflib.SequenceMatcher(None, name_got, name_want).ratio(), 3),
    }


def _build_synthetic(count, workdir, seed=7):
    rng = random.Random(seed)
    truth = []
    for index in range(count):
        sample = {'nik': _pick_nik(rng), 'nama': rng.choice(NAMES)}
        base = os.path.join(workdir, f'base_{index:03d}.jpg')
        shot = os.path.join(workdir, f'ktp_{index:03d}.jpg')
        _make_card(sample, base, rng)
        _degrade(base, shot, rng)
        truth.append({'file': shot, 'nik': sample['nik'], 'nama': sample['nama']})
    return truth


def _evaluate(samples, workdir):
    rows = []
    for sample in samples:
        src = sample['file']
        started = time.time()
        scan = normalize_ktp(src, workdir, 'EVAL')
        scan_ms = round((time.time() - started) * 1000)
        scan_path = os.path.join(workdir, scan['file']) if scan else src
        started = time.time()
        raw = extract_ktp(src)
        raw_ms = round((time.time() - started) * 1000)
        started = time.time()
        scanned = extract_ktp(scan_path)
        ocr_ms = round((time.time() - started) * 1000)
        rows.append({
            'file': os.path.basename(src),
            'scan_ok': bool(scan),
            'raw': {**_score(sample, raw), 'ms': raw_ms},
            'scan': {**_score(sample, scanned), 'ms': ocr_ms},
            'normalize_ms': scan_ms,
        })
    total = max(1, len(rows))
    summary = {
        'count': len(rows),
        'scan_ok_rate': round(sum(r['scan_ok'] for r in rows) / total, 3),
        'raw_nik_acc': round(sum(r['raw']['nik_ok'] for r in rows) / total, 3),
        'raw_name_acc': round(sum(r['raw']['name_ok'] for r in rows) / total, 3),
        'scan_nik_acc': round(sum(r['scan']['nik_ok'] for r in rows) / total, 3),
        'scan_name_acc': round(sum(r['scan']['name_ok'] for r in rows) / total, 3),
        'scan_name_sim': round(sum(r['scan']['name_sim'] for r in rows) / total, 3),
        'nik_missing': sum(1 for r in rows if not r['scan']['nik_found']),
        'avg_normalize_ms': round(sum(r['normalize_ms'] for r in rows) / total),
        'avg_scan_ocr_ms': round(sum(r['scan']['ms'] for r in rows) / total),
    }
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description='Evaluasi scan + OCR KTP FirstWork')
    parser.add_argument('--synthetic', type=int, default=24,
                        help='jumlah KTP sintetis (default 24)')
    parser.add_argument('--corpus', help='folder gambar KTP nyata (ber-consent)')
    parser.add_argument('--truth', help='JSON ground truth untuk --corpus')
    parser.add_argument('--out', default='/tmp/fw_ktp_eval.json')
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()

    workdir = tempfile.mkdtemp(prefix='fw_eval_')
    try:
        if args.corpus:
            if not args.truth:
                print('--truth wajib untuk --corpus')
                return 2
            with open(args.truth, encoding='utf-8') as handle:
                raw = json.load(handle)
            samples = [{'file': os.path.join(args.corpus, item['file']),
                        'nik': str(item['nik']), 'nama': item['nama']}
                       for item in raw]
        else:
            samples = _build_synthetic(args.synthetic, workdir, args.seed)

        summary, rows = _evaluate(samples, workdir)
        report = {'mode': 'corpus' if args.corpus else 'synthetic',
                  'summary': summary, 'rows': rows}
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

        print(f"mode={report['mode']} n={summary['count']}")
        print(f"scan sukses      : {summary['scan_ok_rate'] * 100:.1f}%")
        print(f"NIK  mentah/scan : {summary['raw_nik_acc'] * 100:.1f}% / "
              f"{summary['scan_nik_acc'] * 100:.1f}%")
        print(f"Nama mentah/scan : {summary['raw_name_acc'] * 100:.1f}% / "
              f"{summary['scan_name_acc'] * 100:.1f}% "
              f"(sim {summary['scan_name_sim'] * 100:.1f}%)")
        print(f"rata-rata        : normalize {summary['avg_normalize_ms']} ms, "
              f"OCR scan {summary['avg_scan_ocr_ms']} ms")
        print(f"laporan          : {args.out}")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
