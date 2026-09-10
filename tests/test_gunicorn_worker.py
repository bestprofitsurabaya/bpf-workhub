"""Smoke test worker gunicorn — cegah regresi seperti gunicorn 26 (8 Sep 2026).

gunicorn 26.x menghapus worker BAWAAN eventlet/gevent (menjadi extra
terpisah: `gunicorn[gevent]` TERSEDIA, `gunicorn[eventlet]` TIDAK ADA).
CI lulus karena pytest tidak pernah memulai worker, tapi produksi crash-loop:
`gunicorn --worker-class eventlet` → ImportError entry point tidak ditemukan.

Sejak v2.38.0 worker produksi = gevent (eventlet deprecated). Test ini
mem-parse CMD Dockerfile dan memastikan worker-class tersebut terdaftar di
gunicorn versi yang ter-install — mencegah naik ke versi/konfigurasi yang
worker-nya tidak tersedia (eventlet di 26.x, atau gevent tanpa extra).

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
    """Ambil nilai --worker-class dari CMD Dockerfile (default gevent)."""
    try:
        text = open(DOCKERFILE, encoding='utf-8').read()
    except OSError:
        return 'gevent'
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
        f"dihapus, jadi extra terpisah). Tambahkan extra gunicorn[{worker}] "
        f"di requirements.txt (khusus gevent — eventlet TIDAK punya extra di "
        f"26.x) — lihat insiden 8 Sep 2026 & WORKER_MIGRATION_PLAN.md."
    )


def test_gunicorn_26_dengan_eventlet_ditolak():
    """Guard eksplisit: gunicorn >= 26 + eventlet = kombinasi produksi mati.

    eventlet TIDAK punya extra di gunicorn 26 (tidak seperti gevent), jadi
    kombinasi ini tidak pernah valid pada versi >= 26.
    """
    worker = _worker_class_from_dockerfile()
    version = _gunicorn_version()
    major = int(version.split('.')[0])
    if major >= 26 and worker == 'eventlet':
        pytest.fail(
            f"gunicorn {version} + --worker-class eventlet akan gagal start "
            f"(worker bawaan dihapus di 26.x & tidak ada extra `gunicorn["
            f"eventlet]`). Migrasi ke gevent (v2.38.0) — lihat "
            f"WORKER_MIGRATION_PLAN.md."
        )
