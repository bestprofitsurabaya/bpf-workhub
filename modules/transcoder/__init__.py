"""
modules/transcoder/__init__.py (v2.46.0)

Blueprint Transcoder — konversi link YouTube ke berbagai format audio/video.

- Role pengguna: role IT cabang (it_sby … it_lpg) + admin — pola SCRAPER_ROLES.
- Penyimpanan hasil: data/transcoder/ (volume ./data di docker-compose —
  persisten & tidak ikut image).
- Registrasi: register_transcoder_routes(app) dipanggil di app.py.
"""

import os

from flask import Blueprint

transcoder_bp = Blueprint('transcoder', __name__)

TRANSCODER_ROLES = (
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin',
)


def register_transcoder_routes(app) -> None:
    """Pasang blueprint + konfigurasi folder kerja transcoder."""
    base = os.path.join(app.root_path, 'data', 'transcoder')
    os.makedirs(base, exist_ok=True)
    app.config['TRANSCODE_DIR'] = base

    from . import routes  # noqa: F401 (daftarkan view ke blueprint)
    app.register_blueprint(transcoder_bp)
    print('[transcoder] blueprint terpasang — dir:', base)
