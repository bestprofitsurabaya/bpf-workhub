"""modules/pdfkit/__init__.py (v2.47.0)

Blueprint PDF Kit — **kompresi PDF** untuk role IT cabang (it_sby … it_lpg) +
admin — pola sama dengan modul Transcoder (v2.46.0).

- Mesin: **qpdf** (lossless struktural) & **Ghostscript** (lossy bertingkat) —
  keduanya dipasang via apt di Dockerfile; ruang lingkup dibatasi role IT.
- Penyimpanan hasil: `data/transcoder/pdfkit/` — subfolder dari volume
  persisten `./data/transcoder` (docker-compose) sehingga hasil tidak ikut
  image & tidak perlu menambah mount baru.
- Registrasi: `register_pdfkit_routes(app)` dipanggil di app.py.
"""

import os

from flask import Blueprint

pdfkit_bp = Blueprint('pdfkit', __name__)

# Role IT cabang + admin (paritas TRANSCODER_ROLES / SCRAPER_ROLES).
PDFKIT_ROLES = (
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin',
)


def register_pdfkit_routes(app) -> None:
    """Pasang blueprint + konfigurasi folder kerja PDF Kit."""
    base = os.path.join(app.root_path, 'data', 'transcoder', 'pdfkit')
    os.makedirs(base, exist_ok=True)
    app.config['PDFKIT_DIR'] = base

    from . import routes  # noqa: F401 (daftarkan view ke blueprint)
    app.register_blueprint(pdfkit_bp)
    print('[pdfkit] blueprint terpasang — dir:', base)
