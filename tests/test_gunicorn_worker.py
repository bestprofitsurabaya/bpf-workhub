"""Smoke test worker gunicorn — cegah regresi seperti gunicorn 26 (8 Sep 2026).

gunicorn 26.x menghapus worker bawaan eventlet/gevent (jadi extra terpisah).
CI lulus karena pytest tidak pernah memulai worker, tapi produksi crash-loop:
`gunicorn --worker-class eventlet` → ImportError entry point tidak ditemukan.

Test ini mem-parse CMD Dockerfile dan memastikan worker-class tersebut
terdaftar di entry point `gunicorn.workers` versi yang ter-install.

Jalankan: python3 -m pytest tests/test_gunicorn_worker.py -v
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

try:
    import importlib.metadata as _md
except ImportError:  # Python < 3.8 tidak didukung project ini
    _md = None

DOCKERFILE = os.path.join(os.path.dirname(__file__), '..', 'Dockerfile')


def _worker_class_from_dockerfile():
    """Ambil nilai --worker-class dari CMD Dockerfile (default eventlet)."""
    try:
        text = open(DOCKERFILE, encoding='utf-8').read()
    except OSError:
        return 'eventlet'
    m = re.search(r'--worker-class[=\s]+([A-Za-z_][\w.]*)', text)
    return m.group(1) if m else 'eventlet'


def _gunicorn_version():
    if _md is None:
        pytest.skip('importlib.metadata tidak tersedia')
    try:
        return _md.version('gunicorn')
    except _md.PackageNotFoundError:
        pytest.skip('gunicorn tidak ter-install di environment ini')


def test_worker_class_tersedia_di_gunicorn():
    """Worker yang diminta CMD Dockerfile harus bisa di-resolve gunicorn.

    gunicorn 23 memakai dict SUPPORTED_WORKERS (gunicorn.workers);
    gunicorn >= 26 pindah ke entry point 'gunicorn.workers' (worker
    bawaan eventlet/gevent dihapus — jadi extra terpisah).
    """
    worker = _worker_class_from_dockerfile()
    version = _gunicorn_version()
    available = set()
    try:
        from gunicorn.workers import SUPPORTED_WORKERS
        available |= set(SUPPORTED_WORKERS)
    except Exception:
        pass
    try:
        available |= {ep.name for ep in _md.entry_points(group='gunicorn.workers')}
    except Exception:
        pass
    # Dukungan nama bertitik (mis. 'eventlet' atau path penuh class)
    short = worker.split('.')[-1].lower()
    assert worker in available or short in available, (
        f"gunicorn {version} tidak menyediakan worker '{worker}' — tersedia: "
        f"{sorted(available)}. Kemungkinan gunicorn >= 26 (worker bawaan "
        f"dihapus, jadi extra terpisah). Kembali ke gunicorn 23.x ATAU "
        f"tambahkan extra gunicorn[{worker}] di requirements.txt — lihat "
        f"insiden 8 Sep 2026."
    )


def test_gunicorn_bukan_versi_26_dengan_worker_eventlet():
    """Guard eksplisit: gunicorn >= 26 + eventlet = kombinasi produksi mati."""
    worker = _worker_class_from_dockerfile()
    version = _gunicorn_version()
    major = int(version.split('.')[0])
    if major >= 26 and worker in ('eventlet', 'gevent', 'gthread'):
        pytest.fail(
            f"gunicorn {version} + --worker-class {worker} akan gagal start "
            f"(worker bawaan dihapus di 26.x). Turunkan ke 23.x atau migrasi "
            f"worker — lihat CHANGELOG 8 Sep 2026."
        )
