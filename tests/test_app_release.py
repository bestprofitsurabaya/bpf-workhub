"""Tes rilis APK Agenda (v2.125.0)."""
import hashlib
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import app_release  # noqa: E402
from modules.routes_app_release import register_app_release_routes  # noqa: E402


APK_BYTES = b'PK\x03\x04fake-apk-bytes' * 10
APK_NAME = 'bpf-agenda-1.8.0-release.apk'


@pytest.fixture
def release_dir(tmp_path, monkeypatch):
    folder = tmp_path / 'apk'
    folder.mkdir()
    (folder / APK_NAME).write_bytes(APK_BYTES)
    manifest = {
        'version_name': '1.8.0',
        'version_code': 10800,
        'file': APK_NAME,
        'notes': 'Updater otomatis',
        'mandatory': False,
        'released_at': '2026-11-19T15:00:00+07:00',
    }
    (folder / 'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setenv('BPF_APK_DIR', str(folder))
    app_release.clear_cache()
    return folder


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_app_release_routes(app)
    return app.test_client()


def test_latest_manifest(client, release_dir):
    r = client.get('/api/app/latest')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['version_name'] == '1.8.0'
    assert data['version_code'] == 10800
    assert data['file'] == APK_NAME
    assert data['size'] == len(APK_BYTES)
    assert data['sha256'] == hashlib.sha256(APK_BYTES).hexdigest()
    assert data['apk_url'] == f'/api/app/download/{APK_NAME}'
    assert data['mandatory'] is False
    assert r.headers['Cache-Control'] == 'no-store'


def test_download_apk(client, release_dir):
    r = client.get(f'/api/app/download/{APK_NAME}')
    assert r.status_code == 200
    assert r.mimetype == 'application/vnd.android.package-archive'
    assert r.data == APK_BYTES
    assert r.headers['X-Checksum-SHA256'] == hashlib.sha256(APK_BYTES).hexdigest()
    assert APK_NAME in r.headers['Content-Disposition']


def test_filename_traversal_ditolak(client, release_dir):
    for bad in ('../latest.json', '..%2Flatest.json', 'catatan.txt',
                'bpf-agenda-1.8.0-release.apk.bak', ''):
        r = client.get(f'/api/app/download/{bad}')
        assert r.status_code == 404, bad


def test_rilis_lama_tidak_bisa_diunduh(client, release_dir):
    (release_dir / 'bpf-agenda-1.7.1-release.apk').write_bytes(b'old')
    r = client.get('/api/app/download/bpf-agenda-1.7.1-release.apk')
    assert r.status_code == 404


def test_tanpa_manifest(client, tmp_path, monkeypatch):
    monkeypatch.setenv('BPF_APK_DIR', str(tmp_path))
    app_release.clear_cache()
    r = client.get('/api/app/latest')
    assert r.status_code == 404
    assert r.get_json()['ok'] is False


def test_manifest_menunjuk_file_hilang(client, release_dir):
    manifest = json.loads((release_dir / 'latest.json').read_text(encoding='utf-8'))
    manifest['file'] = 'bpf-agenda-9.9.9-release.apk'
    (release_dir / 'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
    r = client.get('/api/app/latest')
    assert r.status_code == 404


def test_manifest_version_code_tidak_valid(client, release_dir):
    manifest = json.loads((release_dir / 'latest.json').read_text(encoding='utf-8'))
    manifest['version_code'] = 'abc'
    (release_dir / 'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
    r = client.get('/api/app/latest')
    assert r.status_code == 404
