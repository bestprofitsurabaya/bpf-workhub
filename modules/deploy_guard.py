"""Guard deploy (v2.98.0) — tolak request bila image lebih lama dari repo.

Insiden 12 Nov 2026: container masih menjalankan v2.97.0 (image dibangun 12:06)
ketika repo sudah naik ke v2.97.1 (12:49). Selama ~1 jam traineer cabang tetap
menerima counter ID semua cabang karena kode lama masih melayani request, tanpa
sinyal apa pun bahwa deploy tertinggal.

Guard ini membandingkan versi kode yang BERJALAN (`IDENTITY_DEFAULTS`) dengan
entri teratas `CHANGELOG.md` milik repo host yang di-mount read-only ke
`/app/deploy/CHANGELOG.md` (lihat docker-compose.yml). Bila versi repo lebih
baru, request non-health ditolak 503 sampai image di-rebuild.

Konfigurasi:
  DEPLOY_GUARD=block|warn|off     (default block)
  DEPLOY_GUARD_FILE=<path>        (default /app/deploy/CHANGELOG.md)
  DEPLOY_GUARD_TTL=<detik>        (default 15; cache pembacaan file)

Catatan: bila file pembanding tidak ada (mis. image dijalankan tanpa mount),
guard tidak aktif — tidak ada sumber kebenaran untuk dibandingkan. Pemeriksaan
dilakukan per request (dengan cache TTL) supaya commit yang masuk SETELAH
container start tetap terdeteksi, bukan hanya saat startup.
"""
import logging
import os
import re
import time

from flask import jsonify, request

logger = logging.getLogger(__name__)

DEFAULT_CHANGELOG = '/app/deploy/CHANGELOG.md'
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_CHANGELOG = os.path.join(_REPO_ROOT, 'CHANGELOG.md')

# Endpoint yang harus tetap hidup saat deploy tertinggal: monitoring + aset
# statis supaya halaman error/UI bisa dimuat.
ALLOW_PREFIXES = (
    '/api/health',
    '/static/',
    '/app/assets/',
    '/favicon.ico',
    '/manifest.webmanifest',
)

_VERSION_RE = re.compile(r'v?(\d+)\.(\d+)\.(\d+)')

_CACHE = {'path': None, 'mtime': None, 'repo': None, 'checked': 0.0}
_LAST_LOG = {'key': None, 'at': 0.0}


def parse_version(text):
    """'v2.98.0' / 'BPF WorkHub v2.98.0' -> (2, 98, 0); None bila tak ada."""
    m = _VERSION_RE.search(str(text or ''))
    if not m:
        return None
    return tuple(int(part) for part in m.groups())


def changelog_path():
    """Path pembanding: env > mount produksi > CHANGELOG repo (dev/test)."""
    path = os.environ.get('DEPLOY_GUARD_FILE') or DEFAULT_CHANGELOG
    if os.path.isfile(path):
        return path
    return LOCAL_CHANGELOG if os.path.isfile(LOCAL_CHANGELOG) else path


def running_version():
    """Versi kode yang sedang dieksekusi (bukan versi di DB)."""
    try:
        from modules.company_identity import IDENTITY_DEFAULTS
        return parse_version(IDENTITY_DEFAULTS.get('system_version'))
    except Exception:  # pragma: no cover - import rusak tidak boleh melumpuhkan app
        return None


def repo_version(path=None):
    """Versi entri teratas CHANGELOG (heading '## vX.Y.Z')."""
    path = path or changelog_path()
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('## '):
                    return parse_version(line)
    except OSError:
        return None
    return None


def status(now=None, path=None):
    """Ringkasan guard: {'stale', 'running', 'repo', 'path'}.

    `stale` True hanya bila kedua versi terbaca dan versi repo lebih baru.
    """
    now = time.time() if now is None else now
    path = path or changelog_path()
    running = running_version()
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return {'stale': False, 'running': running, 'repo': None, 'path': path}

    try:
        ttl = float(os.environ.get('DEPLOY_GUARD_TTL') or 15)
    except (TypeError, ValueError):
        ttl = 15.0
    if (_CACHE['path'] == path and _CACHE['mtime'] == mtime
            and (now - _CACHE['checked']) < ttl):
        repo = _CACHE['repo']
    else:
        repo = repo_version(path)
        _CACHE.update(path=path, mtime=mtime, repo=repo, checked=now)
    stale = bool(running and repo and repo > running)
    return {'stale': stale, 'running': running, 'repo': repo, 'path': path}


def reset_cache():
    """Kosongkan cache (dipakai test)."""
    _CACHE.update({'path': None, 'mtime': None, 'repo': None, 'checked': 0.0})
    _LAST_LOG.update({'key': None, 'at': 0.0})


def install_deploy_guard(app):
    """Daftarkan before_request guard pada Flask app."""

    @app.before_request
    def _deploy_guard():
        mode = (os.environ.get('DEPLOY_GUARD') or 'block').strip().lower()
        if mode == 'off':
            return None

        state = status()
        if not state['stale']:
            _LAST_LOG['key'] = None
            return None

        running = state['running']
        repo = state['repo']
        msg = (f'Deploy belum sinkron: kode berjalan v{running[0]}.{running[1]}.{running[2]} '
               f'lebih lama dari repo v{repo[0]}.{repo[1]}.{repo[2]}. '
               "Jalankan 'docker compose up -d --build web'.")
        _log_once(msg, mode)

        if mode == 'warn':
            return None
        if request.path.startswith(ALLOW_PREFIXES):
            return None

        if request.path.startswith('/api/'):
            response = jsonify({
                'status': 'error',
                'msg': msg,
                'running_version': f'v{running[0]}.{running[1]}.{running[2]}',
                'repo_version': f'v{repo[0]}.{repo[1]}.{repo[2]}',
            })
            response.status_code = 503
        else:
            response = app.response_class(msg, status=503, mimetype='text/plain')
        response.headers['Retry-After'] = '30'
        response.headers['X-Deploy-Guard'] = 'stale'
        return response


def _log_once(msg, mode):
    """Satu baris log per kombinasi versi per 5 menit — hindari banjir log."""
    key = (mode, msg)
    now = time.time()
    if _LAST_LOG['key'] == key and (now - _LAST_LOG['at']) < 300:
        return
    _LAST_LOG.update({'key': key, 'at': now})
    if mode == 'warn':
        logger.warning('[deploy-guard] %s', msg)
    else:
        logger.error('[deploy-guard] %s', msg)
