"""
modules/transcoder/ncshare.py (v2.46.2)

Distribusi hasil transcoder via **Nextcloud public share**.

Latar: tautan unduhan lokal (`/api/transcoder/download/...`) terikat sesi
login WorkHub — tidak bisa dibuka pihak lain. Dengan share publik Nextcloud
(mis. `https://nasbpfsby.duckdns.org/index.php/s/H6ja3kDFts3aCke`), hasil
konversi diunggah via **WebDAV publik** (`/public.php/webdav/<job>/<file>`,
Basic Auth user=<token> share) sehingga tiap berkas mendapat tautan unduh
publik: `/index.php/s/<token>/download?path=<job>/<file>`.

Konfigurasi disimpan di `data/transcoder/nc_share.json` (volume persisten)
— bisa diset lewat API/UI tanpa rebuild. Password share opsional.
"""

import os
import re
import json
from urllib.parse import quote

import requests

# data/transcoder — pola sama dengan modules/transcoder/__init__.py
_NC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                       'data', 'transcoder')
CONFIG_FILE = os.path.join(_NC_DIR, 'nc_share.json')

_TOKEN_RE = re.compile(r'/index\.php/s/([A-Za-z0-9_-]{6,64})')
_UPLOAD_TIMEOUT = (10, 600)      # connect, read — berkas video bisa ratusan MB


def load_config():
    """Baca & parse config share. Return dict {origin, token, password}
    atau None bila tidak/belum valid."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        parsed = parse_share_url(raw.get('url', ''))
        if not parsed:
            return None
        return {'origin': parsed[0], 'token': parsed[1],
                'password': str(raw.get('password') or '')}
    except (OSError, ValueError, AttributeError):
        return None


def save_config(url, password=''):
    """Simpan config; raise ValueError bila URL bukan share Nextcloud valid."""
    parsed = parse_share_url(url or '')
    if not parsed:
        raise ValueError('URL bukan tautan share Nextcloud yang valid '
                         '(format: https://host/index.php/s/<token>)')
    os.makedirs(_NC_DIR, exist_ok=True)
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'url': parsed[0] + '/index.php/s/' + parsed[1],
                   'password': password or ''}, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
    return {'origin': parsed[0], 'token': parsed[1]}


def parse_share_url(url):
    """URL share → (origin, token) atau None."""
    m = _TOKEN_RE.search(url or '')
    if not m:
        return None
    origin = (url or '').split('/index.php/s/')[0].rstrip('/')
    if not origin.startswith(('http://', 'https://')):
        return None
    return origin, m.group(1)


def is_configured():
    return load_config() is not None


def public_url(origin, token, job_id, filename):
    """Tautan unduh publik untuk satu berkas di dalam share folder."""
    path = quote(f"{job_id}/{filename}")
    return f"{origin}/index.php/s/{token}/download?path={path}"


def upload_file(job_id, filename, filepath):
    """Unggah satu berkas ke share publik (folder per job). Return URL publik.

    - MKCOL folder job dulu (abaikan error bila sudah ada / tak diizinkan).
    - PUT isi berkas via stream (tanpa memuat penuh ke memori).
    - HTTP selain 2xx → RuntimeError (pemanggil memutuskan fallback).
    """
    cfg = load_config()
    if not cfg:
        raise RuntimeError('Share Nextcloud belum dikonfigurasi')
    auth = (cfg['token'], cfg['password'])
    dav_dir = f"{cfg['origin']}/public.php/webdav/{quote(job_id)}"
    try:
        requests.request('MKCOL', dav_dir, auth=auth, timeout=(10, 30))
    except requests.RequestException:
        pass  # 405 = folder sudah ada; gagal jaringan dicoba lagi saat PUT

    with open(filepath, 'rb') as fh:
        r = requests.put(f"{dav_dir}/{quote(filename)}", data=fh,
                         auth=auth, timeout=_UPLOAD_TIMEOUT)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f'Unggah Nextcloud gagal: HTTP {r.status_code}')
    return public_url(cfg['origin'], cfg['token'], job_id, filename)
