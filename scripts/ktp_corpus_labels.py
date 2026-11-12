"""Siapkan truth.json untuk mengukur OCR pada KTP nyata ber-consent.

Harness pengukuran sudah ada: scripts/eval_first_work_ktp.py --corpus ...
--truth ...  Skrip ini hanya menyiapkan berkas labelnya, dengan pengaman agar
data pribadi tidak gampang ikut ter-commit.

Format labels.csv (baris pertama header):
    file,nik,nama
    ktp_001.jpg,3171010101900001,BUDI SANTOSO

Aturan:
- `file` relatif terhadap folder --corpus dan harus ada.
- `nik` tepat 16 digit; `nama` minimal 3 karakter.
- Output default ditolak bila berada di dalam repo (kecuali --allow-repo),
  dan selalu ditulis dengan izin 600.
- Skrip ini TIDAK mengunggah apa pun dan tidak menyimpan salinan gambar.

Contoh:
    python3 scripts/ktp_corpus_labels.py \
        --corpus /data/ktp --labels /data/labels.csv --out /data/truth.json
"""
import argparse
import csv
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIK_RE = re.compile(r'^\d{16}$')


def _inside_repo(path):
    try:
        return os.path.commonpath([os.path.abspath(path), REPO_ROOT]) == REPO_ROOT
    except ValueError:
        return False


def build_truth(corpus, labels_path):
    truth, errors, seen = [], [], set()
    with open(labels_path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        required = {'file', 'nik', 'nama'}
        if not required.issubset({(field or '').strip().lower()
                                  for field in (reader.fieldnames or [])}):
            raise SystemExit('labels.csv wajib punya kolom: file,nik,nama')
        for line_no, row in enumerate(reader, start=2):
            row = {(key or '').strip().lower(): (value or '').strip()
                   for key, value in row.items()}
            name = row.get('file') or ''
            nik = row.get('nik') or ''
            nama = row.get('nama') or ''
            if not name and not nik and not nama:
                continue
            if name in seen:
                errors.append(f'baris {line_no}: file duplikat {name}')
                continue
            if not os.path.isfile(os.path.join(corpus, name)):
                errors.append(f'baris {line_no}: file tidak ada: {name}')
                continue
            if not NIK_RE.match(nik):
                errors.append(f'baris {line_no}: NIK harus 16 digit ({name})')
                continue
            if len(nama) < 3:
                errors.append(f'baris {line_no}: nama terlalu pendek ({name})')
                continue
            seen.add(name)
            truth.append({'file': name, 'nik': nik, 'nama': nama})
    return truth, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', required=True, help='folder gambar KTP')
    parser.add_argument('--labels', required=True, help='CSV label manual')
    parser.add_argument('--out', required=True, help='path truth.json')
    parser.add_argument('--allow-repo', action='store_true',
                        help='izinkan output di dalam repo (tidak disarankan)')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()

    corpus = os.path.abspath(args.corpus)
    if not os.path.isdir(corpus):
        raise SystemExit(f'Folder korpus tidak ditemukan: {corpus}')
    if _inside_repo(args.out) and not args.allow_repo:
        raise SystemExit('Output di dalam repo ditolak: data pribadi bisa '
                         'ter-commit. Pakai folder di luar repo atau --allow-repo.')

    truth, errors = build_truth(corpus, args.labels)
    for message in errors:
        print(f'[tolak] {message}')
    if errors:
        raise SystemExit(f'{len(errors)} baris bermasalah; perbaiki dulu.')
    if not truth:
        raise SystemExit('Tidak ada label valid.')
    if args.check_only:
        print(f'OK: {len(truth)} label valid (tidak menulis apa pun).')
        return

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(truth, handle, ensure_ascii=False, indent=2)
    os.chmod(args.out, 0o600)
    print(f'OK: {len(truth)} label ditulis ke {args.out} (izin 600).')
    print('Jalankan: python3 scripts/eval_first_work_ktp.py '
          f'--corpus {corpus} --truth {args.out} --out /tmp/fw_ktp_eval.json')
    print('Setelah selesai: hapus gambar + truth.json; jangan commit ke repo.')


if __name__ == '__main__':
    sys.exit(main())
