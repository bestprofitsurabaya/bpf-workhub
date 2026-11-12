"""Guard deploy (v2.98.0) — image lebih lama dari repo harus menolak request."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from modules import deploy_guard as dg  # noqa: E402


def _changelog(tmp_path, version):
    path = tmp_path / 'CHANGELOG.md'
    path.write_text(f'# Changelog\n\n## {version} — 12 November 2026 (uji)\n\n- x\n',
                    encoding='utf-8')
    return path


def _client(tmp_path, monkeypatch, running='v2.97.1', repo='v2.98.0',
            mode='block'):
    path = _changelog(tmp_path, repo)
    monkeypatch.setenv('DEPLOY_GUARD_FILE', str(path))
    monkeypatch.setenv('DEPLOY_GUARD', mode)
    monkeypatch.setattr(dg, 'running_version', lambda: dg.parse_version(running))
    dg.reset_cache()

    app = Flask(__name__)

    @app.route('/api/health')
    def health():
        return {'status': 'ok'}

    @app.route('/api/first-work/id-config')
    def first_work():
        return {'status': 'success'}

    @app.route('/app/first-work')
    def spa():
        return 'spa'

    dg.install_deploy_guard(app)
    return app.test_client()


def test_parse_version():
    assert dg.parse_version('v2.98.0') == (2, 98, 0)
    assert dg.parse_version('BPF WorkHub v2.9.10') == (2, 9, 10)
    assert dg.parse_version('tanpa versi') is None


def test_repo_version_reads_latest_heading(tmp_path):
    path = _changelog(tmp_path, 'v2.98.0')
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write('\n## v2.97.1 — lama\n')
    assert dg.repo_version(str(path)) == (2, 98, 0)


def test_stale_when_repo_newer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get('/api/first-work/id-config').status_code == 503
    assert client.get('/app/first-work').status_code == 503


def test_health_stays_up_when_stale(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json() == {'status': 'ok'}


def test_same_version_is_allowed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, running='v2.98.0', repo='v2.98.0')
    assert client.get('/api/first-work/id-config').status_code == 200


def test_rolled_back_image_is_not_blocked(tmp_path, monkeypatch):
    # Image lebih baru dari repo (rollback) bukan kondisi "tertinggal".
    client = _client(tmp_path, monkeypatch, running='v2.99.0', repo='v2.98.0')
    assert client.get('/api/first-work/id-config').status_code == 200


def test_warn_mode_logs_but_serves(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, mode='warn')
    assert client.get('/api/first-work/id-config').status_code == 200


def test_off_mode_disables_guard(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, mode='off')
    assert client.get('/api/first-work/id-config').status_code == 200


def test_missing_reference_file_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv('DEPLOY_GUARD_FILE', str(tmp_path / 'tidak-ada.md'))
    monkeypatch.setenv('DEPLOY_GUARD', 'block')
    # Fallback dev juga harus tidak ada, supaya benar-benar menguji "tanpa referensi".
    monkeypatch.setattr(dg, 'LOCAL_CHANGELOG', str(tmp_path / 'lokal-tidak-ada.md'))
    monkeypatch.setattr(dg, 'running_version', lambda: (2, 97, 1))
    dg.reset_cache()
    app = Flask(__name__)

    @app.route('/api/x')
    def x():
        return {'ok': True}

    dg.install_deploy_guard(app)
    assert app.test_client().get('/api/x').status_code == 200


if __name__ == '__main__':  # pragma: no cover
    pytest.main([__file__, '-q'])
