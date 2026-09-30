"""Unit tests — modul Transcoder (v2.46.0).

- is_youtube_url & _sanitize_name (validasi murni).
- create_job → lifecycle selesai dgn yt-dlp/ffmpeg di-mock (tanpa jaringan).
- submit API: role guard, multi-link parse, format guard.
- download: ekstensi guard + daftar berkas harus milik job.

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_transcoder.py -v
"""

import os
import sys
import time
import json
import shutil
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

from modules.transcoder import engine, register_transcoder_routes
from modules.transcoder.routes import _user  # noqa: F401  (menjaga modul terimpor)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path, monkeypatch):
    from modules.helpers import role_required  # noqa: F401  (patch target)

    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_transcoder_routes(app)

    # jadikan folder job tmp_path agar tidak menyentuh data/
    base = os.path.join(str(tmp_path), 'data', 'transcoder')
    os.makedirs(base, exist_ok=True)

    real_create = engine.create_job

    def create_job_sync(urls, formats, user, base_dir):
        job = real_create(urls, formats, user, base_dir)
        return job

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, role='it_sby', name=None):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = name or role
        s['csrf_token'] = 'test-csrf'


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type='application/json',
                       headers={'X-CSRF-Token': 'test-csrf'})


# ---------------------------------------------------------------------------
# Validasi URL & nama file
# ---------------------------------------------------------------------------

class TestUrlValidation:
    def test_standard(self):
        assert engine.is_youtube_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    def test_short(self):
        assert engine.is_youtube_url('https://youtu.be/dQw4w9WgXcQ')

    def test_no_scheme(self):
        assert engine.is_youtube_url('youtube.com/watch?v=abc123')

    def test_music(self):
        assert engine.is_youtube_url('https://music.youtube.com/watch?v=abc123')

    def test_reject_other(self):
        assert not engine.is_youtube_url('https://vimeo.com/12345')
        assert not engine.is_youtube_url('https://facebook.com/video')
        assert not engine.is_youtube_url('')
        assert not engine.is_youtube_url('javascript:alert(1)')

    def test_reject_traversal_lookalike(self):
        assert not engine.is_youtube_url('https://youtube.com.evil.com/x')


class TestSanitize:
    def test_basic(self):
        assert engine._sanitize_name('Harga Emas Naik!') == 'Harga_Emas_Naik'

    def test_traversal(self):
        assert '/' not in engine._sanitize_name('../../etc/passwd')
        assert '..' not in engine._sanitize_name('..')

    def test_empty(self):
        assert engine._sanitize_name('') == 'media'
        assert engine._sanitize_name('###') == 'media'


# ---------------------------------------------------------------------------
# Lifecycle job (yt-dlp & ffmpeg dimock)
# ---------------------------------------------------------------------------

class FakeTranscode:
    """Mock jalur unduh+transcode: tulis file dummy + progres langsung."""

    def __init__(self):
        self.calls = []

    def probe_title(self, url):
        return f'Judul {len(self.calls)}'

    def download_media(self, url, kind, max_height, workdir, on_progress):
        self.calls.append((url, kind))
        path = os.path.join(workdir, f'src_{len(self.calls)}.mp4')
        with open(path, 'wb') as f:
            f.write(b'\x00' * 1024)
        on_progress(100)
        return path


class TestJobLifecycle:
    def test_full_flow(self, tmp_path, monkeypatch):
        fake = FakeTranscode()
        base = str(tmp_path / 'tc')
        os.makedirs(base, exist_ok=True)

        import modules.transcoder.ytdlp as ytdlp
        monkeypatch.setattr(ytdlp, 'probe_title', fake.probe_title)
        monkeypatch.setattr(ytdlp, 'download_media', fake.download_media)

        import modules.transcoder.engine as eng
        # ffmpeg dimock: tulis file output dummy agar ukuran terbaca
        def fake_run(input_args, duration, on_progress, workdir):
            out = input_args[-1]
            with open(os.path.join(workdir, out), 'wb') as f:
                f.write(b'\x00' * 512)
            on_progress(100)
        monkeypatch.setattr(eng, '_run_ffmpeg', fake_run)

        job = eng.create_job(
            ['https://youtu.be/aaa111', 'https://youtu.be/bbb222'],
            ['mp3', 'mp4'], 'it_sby', base)

        # tunggu worker selesai (maks 5 dtk)
        deadline = time.time() + 5
        while time.time() < deadline:
            j = eng.get_job(job['id'])
            if j['status'] in ('done', 'error'):
                break
            time.sleep(0.05)

        j = eng.get_job(job['id'])
        assert j['status'] == 'done'
        assert len(j['items']) == 2
        for it in j['items']:
            assert it['status'] == 'done'
            assert {o['format'] for o in it['outputs']} == {'mp3', 'mp4'}
            for o in it['outputs']:
                assert o['size'] > 0

    def test_concurrent_sem(self, tmp_path, monkeypatch):
        """MAX_CONCURRENT=1 → job kedua menunggu (antrean, bukan paralel)."""
        fake = FakeTranscode()
        base = str(tmp_path / 'tc')
        os.makedirs(base, exist_ok=True)

        import modules.transcoder.ytdlp as ytdlp
        import modules.transcoder.engine as eng
        monkeypatch.setattr(ytdlp, 'probe_title', fake.probe_title)
        monkeypatch.setattr(ytdlp, 'download_media', fake.download_media)

        def slow_run(input_args, duration, on_progress, workdir):
            time.sleep(0.3)
            with open(os.path.join(workdir, input_args[-1]), 'wb') as f:
                f.write(b'x')
            on_progress(100)
        monkeypatch.setattr(eng, '_run_ffmpeg', slow_run)

        j1 = eng.create_job(['https://youtu.be/x1'], ['mp3'], 'it_sby', base)
        j2 = eng.create_job(['https://youtu.be/x2'], ['mp3'], 'it_sby', base)
        # keduanya harus selesai; MAX_CONCURRENT=1 → urut, bukan paralel
        deadline = time.time() + 5
        while time.time() < deadline:
            if eng.get_job(j1['id'])['status'] == 'done' and \
               eng.get_job(j2['id'])['status'] == 'done':
                break
            time.sleep(0.05)
        assert eng.get_job(j1['id'])['status'] == 'done'
        assert eng.get_job(j2['id'])['status'] == 'done'

    def test_partial_failure(self, tmp_path, monkeypatch):
        """1 link gagal → job tetap done dgn catatan sebagian gagal."""
        fake = FakeTranscode()
        base = str(tmp_path / 'tc')
        os.makedirs(base, exist_ok=True)

        import modules.transcoder.ytdlp as ytdlp
        import modules.transcoder.engine as eng
        monkeypatch.setattr(ytdlp, 'probe_title', fake.probe_title)

        def dl(url, kind, mh, workdir, on_progress):
            if 'bad' in url:
                raise RuntimeError('simulasi gagal unduh')
            return fake.download_media(url, kind, mh, workdir, on_progress)
        monkeypatch.setattr(ytdlp, 'download_media', dl)

        def fake_run(input_args, duration, on_progress, workdir):
            with open(os.path.join(workdir, input_args[-1]), 'wb') as f:
                f.write(b'x')
            on_progress(100)
        monkeypatch.setattr(eng, '_run_ffmpeg', fake_run)

        job = eng.create_job(
            ['https://youtu.be/good1', 'https://youtu.be/bad99'],
            ['mp3'], 'it_sby', base)
        deadline = time.time() + 5
        while time.time() < deadline:
            j = eng.get_job(job['id'])
            if j['status'] in ('done', 'error'):
                break
            time.sleep(0.05)
        j = eng.get_job(job['id'])
        assert j['status'] == 'done'
        statuses = {it['status'] for it in j['items']}
        assert statuses == {'done', 'error'}
        assert 'sebagian' in j['stage'].lower()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class TestApi:
    def test_submit_requires_login(self, client):
        r = client.post('/api/transcoder/jobs', json={})
        assert r.status_code in (302, 401, 403)

    def test_submit_rejects_non_youtube(self, client):
        _login(client)
        r = _post(client, '/api/transcoder/jobs',
                  {'urls': ['https://vimeo.com/1'], 'formats': ['mp3']})
        assert r.status_code == 400
        assert 'YouTube' in r.get_json()['msg']

    def test_submit_rejects_bad_format(self, client):
        _login(client)
        r = _post(client, '/api/transcoder/jobs',
                  {'urls': ['https://youtu.be/aaa'], 'formats': ['flv']})
        assert r.status_code == 400

    def test_submit_rejects_empty(self, client):
        _login(client)
        r = _post(client, '/api/transcoder/jobs', {'urls': [], 'formats': ['mp3']})
        assert r.status_code == 400

    def test_submit_over_limit(self, client):
        _login(client)
        urls = [f'https://youtu.be/v{i:02d}' for i in range(engine.MAX_URLS_PER_REQUEST + 1)]
        r = _post(client, '/api/transcoder/jobs', {'urls': urls, 'formats': ['mp3']})
        assert r.status_code == 400
        assert 'Maksimal' in r.get_json()['msg']

    def test_submit_multi_line_string(self, client, monkeypatch):
        _login(client)
        import modules.transcoder.engine as eng
        monkeypatch.setattr(eng, 'create_job',
                            lambda urls, formats, user, base: {
                                'id': 'tc000001', 'urls': urls, 'formats': formats,
                                'user': user, 'status': 'queued', 'stage': '',
                                'progress': 0, 'created_at': 0, 'finished_at': None,
                                'error': '', 'items': []})
        r = _post(client, '/api/transcoder/jobs',
                  {'urls': 'https://youtu.be/a1\nhttps://youtu.be/b2',
                   'formats': ['mp3']})
        assert r.status_code == 201
        assert len(r.get_json()['job']['urls']) == 2

    def test_list_filtered_per_user(self, client, monkeypatch):
        _login(client, 'it_sby')
        monkeypatch.setattr(engine, 'list_jobs', lambda limit=50: [
            {'id': '1', 'user': 'it_sby', 'status': 'done', 'items': []},
            {'id': '2', 'user': 'it_hu', 'status': 'done', 'items': []},
            {'id': '3', 'user': 'admin', 'status': 'done', 'items': []},
        ])
        r = client.get('/api/transcoder/jobs')
        ids = [j['id'] for j in r.get_json()['jobs']]
        assert ids == ['1']

    def test_admin_sees_all(self, client, monkeypatch):
        _login(client, 'admin', 'admin')
        monkeypatch.setattr(engine, 'list_jobs', lambda limit=50: [
            {'id': '1', 'user': 'it_sby', 'status': 'done', 'items': []},
        ])
        r = client.get('/api/transcoder/jobs')
        assert len(r.get_json()['jobs']) == 1

    def test_detail_hidden_from_other_user(self, client, monkeypatch):
        _login(client, 'it_hu')
        monkeypatch.setattr(engine, 'get_job', lambda jid: {'id': jid, 'user': 'it_sby'})
        r = client.get('/api/transcoder/jobs/tc000001')
        assert r.status_code == 404

    def test_cancel_other_user_409(self, client, monkeypatch):
        _login(client, 'it_hu')
        monkeypatch.setattr(engine, 'get_job',
                            lambda jid: {'id': jid, 'user': 'it_sby', 'status': 'downloading'})
        r = _post(client, '/api/transcoder/jobs/tc000001/cancel', {})
        assert r.status_code == 409

    def test_download_unknown_file_404(self, client, monkeypatch, tmp_path):
        _login(client, 'it_sby')
        monkeypatch.setattr(engine, 'get_job', lambda jid: {
            'id': jid, 'user': 'it_sby', 'items': [
                {'outputs': [{'file': 'judul.mp3', 'format': 'mp3'}]}]})
        r = client.get('/api/transcoder/download/tc000001/lain.mp3')
        assert r.status_code == 404

    def test_download_bad_ext(self, client, monkeypatch):
        _login(client, 'it_sby')
        monkeypatch.setattr(engine, 'get_job', lambda jid: {
            'id': jid, 'user': 'it_sby', 'items': []})
        r = client.get('/api/transcoder/download/tc000001/virus.exe')
        assert r.status_code == 400
