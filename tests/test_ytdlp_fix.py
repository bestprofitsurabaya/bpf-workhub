"""Unit test baru — BUG "1 video yang sama beda nama" (12 Okt 2026).

Simulasi persis laporan user: satu job berisi banyak link, semuanya
ditulis ke workdir yang sama. Dulu download_media memilih file mtime
terbaru global → link berikutnya mentranskode file link pertama.
Sekarang path diambil dari output yt-dlp sendiri.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.transcoder.ytdlp import _parse_stdout_path, download_media


class TestParseStdoutPath:
    def test_destination(self):
        assert _parse_stdout_path(
            '[download] Destination: /tmp/w/src_abc.webm'
        ) == '/tmp/w/src_abc.webm'

    def test_destination_quoted(self):
        assert _parse_stdout_path(
            '[Merger] Merging formats into "/tmp/w/src_abc.mp4"'
        ) == '/tmp/w/src_abc.mp4'

    def test_already_downloaded(self):
        assert _parse_stdout_path(
            '[download] /tmp/w/src_abc.webm has already been downloaded'
        ) == '/tmp/w/src_abc.webm'

    def test_part_stripped(self):
        assert _parse_stdout_path(
            '[download] Destination: /tmp/w/src_abc.webm.part'
        ) == '/tmp/w/src_abc.webm'

    def test_progress_line_no_path(self):
        assert _parse_stdout_path(
            '[download]  23.4% of 10.00MiB at 1.00MiB/s ETA 00:08'
        ) is None


class TestDownloadMediaDistinctSources:
    """Workdir dibagi bareng + file lama lebih baru (mtime lama tersisa)
    → tetap harus mengembalikan file milik URL ini, bukan mtime global."""

    def _dl(self, monkeypatch, tmp_path, url, fname):
        workdir = str(tmp_path)
        real_popen = __import__('subprocess').Popen

        class FakeProc:
            def __init__(self):
                self.returncode = 0
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            @property
            def stdout(self):
                lines = [f'[download] Destination: {os.path.join(workdir, fname)}',
                         '[download] 100.0% of 1.00MiB']
                return iter(lines)
            def wait(self):
                return 0

        monkeypatch.setattr('subprocess.Popen', lambda *a, **k: FakeProc())
        got = download_media(url, 'audio', 0, workdir, lambda p: None)
        return got

    def test_each_url_gets_own_file(self, tmp_path, monkeypatch):
        # file "lama" milik link lain sudah ada di workdir (mtime lama)
        other = tmp_path / 'src_OLDEST.webm'
        other.write_bytes(b'x' * 10)
        os.utime(other, (time.time() - 3600, time.time() - 3600))

        got = self._dl(monkeypatch, tmp_path, 'https://youtu.be/new99', 'src_NEW99.webm')
        assert os.path.basename(got) == 'src_NEW99.webm', (
            f'harus file unduhan ini, dapat {got}')

    def test_fallback_newest_non_part(self, tmp_path, monkeypatch):
        # tanpa baris Destination (yt-dlp lawan) → fallback mtime,
        # file .part tidak boleh terpilih
        part = tmp_path / 'src_PART.webm.part'
        part.write_bytes(b'x')
        newest_ok = tmp_path / 'src_OK.webm'
        newest_ok.write_bytes(b'y' * 20)
        os.utime(newest_ok, (time.time() - 10, time.time() - 10))

        class FakeProc:
            returncode = 0
            stdout = iter(['[download] 100.0% of 1.00MiB'])
            def wait(self):
                return 0
        monkeypatch.setattr('subprocess.Popen', lambda *a, **k: FakeProc())
        got = download_media('https://youtu.be/zz', 'audio', 0, str(tmp_path), lambda p: None)
        assert os.path.basename(got) == 'src_OK.webm'
