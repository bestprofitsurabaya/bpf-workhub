"""Regression v2.109.1 — helper OCR form publik harus bebas CSRF.

Insiden: `/api/first-work/ocr-ktp` tidak terdaftar di `CSRF_EXEMPT_PREFIXES`,
sehingga Traineer/Admin yang membuka form sambil login selalu ditolak
"CSRF token tidak valid" (400 dalam 0 ms) dan OCR tampak tidak berfungsi.

Tes ini membaca `app.py` lewat AST — tanpa meng-import aplikasi penuh yang
butuh SECRET_KEY, koneksi DB, dan worker — lalu memastikan prefix-nya ada.

Jalankan:
    python3 -m pytest tests/test_first_work_ocr_csrf.py -v
"""

import ast
import os

APP_PATH = os.path.join(os.path.dirname(__file__), '..', 'app.py')


def _exempt_prefixes():
    with open(APP_PATH, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'CSRF_EXEMPT_PREFIXES':
                return list(ast.literal_eval(node.value))
    raise AssertionError('CSRF_EXEMPT_PREFIXES tidak ditemukan di app.py')


def test_ocr_first_work_dikecualikan_dari_csrf():
    prefixes = _exempt_prefixes()
    assert '/api/first-work/ocr-ktp' in prefixes, (
        'OCR form publik akan ditolak CSRF untuk sesi login (bug v2.109.1).')
    # Jangan sampai perbaikan ini menghapus pengecualian submit publik.
    assert '/api/first-work/public' in prefixes
