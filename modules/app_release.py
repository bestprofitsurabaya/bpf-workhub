"""Rilis APK BPF Agenda (v2.125.0).

Sumber tunggal pembaruan aplikasi Android: manifest `latest.json` + file APK
di folder yang di-mount dari host (`/srv/bpf-workhub/apk` → `/app/data/apk`).

Manifest sengaja sederhana supaya bisa ditulis skrip rilis:

    {
      "version_name": "1.8.0",
      "version_code": 10800,
      "file": "bpf-agenda-1.8.0-release.apk",
      "notes": "…",
      "mandatory": false,
      "released_at": "2026-11-19T15:00:00+07:00"
    }

Tidak ada autentikasi: APK memang dibagikan ke perangkat internal dan bridge
8444 sudah publik. Yang dijaga: nama file (anti path traversal), ukuran, dan
SHA-256 agar aplikasi bisa memverifikasi unduhan sebelum memasang.
"""
import hashlib
import json
import os
import re
import threading

FILENAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*\.apk$')
DEFAULT_HOST_DIR = '/app/data/apk'

_sha_cache = {}
_sha_lock = threading.Lock()


class ReleaseError(Exception):
    """Manifest/folder rilis tidak valid atau belum tersedia."""


def apk_dir():
    """Folder rilis: env `BPF_APK_DIR`, container, atau `apk/dist` repo."""
    env = (os.environ.get('BPF_APK_DIR') or '').strip()
    if env:
        return env
    if os.path.isdir(DEFAULT_HOST_DIR):
        return DEFAULT_HOST_DIR
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'apk', 'dist')


def _safe_filename(name):
    name = str(name or '').strip()
    if not FILENAME_RE.match(name):
        raise ReleaseError('nama file APK tidak valid')
    return name


def _sha256(path):
    """SHA-256 dengan cache (path, mtime, size) — file 3 MB, aman dihitung ulang."""
    st = os.stat(path)
    key = (os.path.realpath(path), int(st.st_mtime), st.st_size)
    with _sha_lock:
        hit = _sha_cache.get(key)
    if hit:
        return hit
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    value = digest.hexdigest()
    with _sha_lock:
        _sha_cache[key] = value
    return value


def latest_release():
    """Baca `latest.json` dan validasi APK-nya. Raise ReleaseError bila gagal."""
    folder = apk_dir()
    manifest_path = os.path.join(folder, 'latest.json')
    if not os.path.isfile(manifest_path):
        raise ReleaseError('belum ada rilis APK')
    try:
        with open(manifest_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ReleaseError(f'manifest tidak terbaca: {exc}')

    if not isinstance(data, dict):
        raise ReleaseError('manifest bukan objek JSON')

    filename = _safe_filename(data.get('file'))
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        raise ReleaseError('file APK tidak ditemukan')

    try:
        version_code = int(data.get('version_code'))
    except (TypeError, ValueError):
        raise ReleaseError('version_code tidak valid')
    if version_code <= 0:
        raise ReleaseError('version_code tidak valid')

    version_name = str(data.get('version_name') or '').strip()
    if not version_name:
        raise ReleaseError('version_name kosong')

    notes = str(data.get('notes') or '').strip()
    released_at = str(data.get('released_at') or '').strip() or None
    mandatory = bool(data.get('mandatory'))

    size = os.path.getsize(path)
    return {
        'ok': True,
        'version_name': version_name,
        'version_code': version_code,
        'file': filename,
        'size': size,
        'sha256': _sha256(path),
        'notes': notes,
        'mandatory': mandatory,
        'released_at': released_at,
        'apk_url': f'/api/app/download/{filename}',
    }


def resolve_apk(filename):
    """Path APK yang aman untuk diunduh. Raise ReleaseError bila tidak valid."""
    folder = os.path.realpath(apk_dir())
    name = _safe_filename(filename)
    path = os.path.realpath(os.path.join(folder, name))
    if os.path.dirname(path) != folder or not os.path.isfile(path):
        raise ReleaseError('file APK tidak ditemukan')
    return path


def clear_cache():
    """Dipakai tes/ops setelah file rilis diganti."""
    with _sha_lock:
        _sha_cache.clear()
