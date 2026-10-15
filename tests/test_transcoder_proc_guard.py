"""Unit — guard subprocess transcoder (v2.46.7).

Latar (audit 15 Okt 2026): yt-dlp & ffmpeg dulu memakai `stderr=PIPE` yang
HANYA dibaca setelah stdout habis → bila anak menulis > buffer pipe (~64 KB),
terjadi deadlock; dan tanpa batas waktu, job bisa menggantung selamanya —
karena MAX_CONCURRENT=1, satu proses macet membekukan seluruh antrean.

Tes ini mengunci dua perilaku kunci: (1) stderr benar-benar dikuras dan
isinya dipakai untuk pesan error, (2) proses yang menggantung dimatikan oleh
watchdog waktu.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.transcoder import _proc  # noqa: E402
from modules.transcoder.ytdlp import YtDlpError, download_media  # noqa: E402


class FakeProc:
    """Proses palsu: stream stdout/stderr dari list, bisa 'menggantung'."""

    def __init__(self, stdout_lines=(), stderr_lines=(), returncode=0, hang=False):
        self._stdout = iter(list(stdout_lines))
        self._stderr = iter(list(stderr_lines))
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def wait(self, *args, **kwargs):
        # Meniru proses macet: tetap blokir sampai di-'kill' (interruptible).
        while self._hang and not self.killed:
            time.sleep(0.02)
        return self.returncode

    def poll(self):
        return None if self._hang else self.returncode

    def kill(self):
        self.killed = True
        self._hang = False
        self.returncode = -9


# ---------------------------------------------------------------------------
# Kuras stderr (anti-deadlock)
# ---------------------------------------------------------------------------

class TestDrainStderr:
    def test_menguras_seluruh_stream_dan_menyimpan_tail(self):
        """Seluruh 500 baris stderr dikonsumsi; hanya tail terakhir disimpan."""
        proc = FakeProc(stderr_lines=[f'e{i}\n' for i in range(500)])
        drain = _proc.drain_stderr(proc)
        out = drain.tail()
        # deque maxlen=200 → tak menahan semua, tapi elemen terakhir benar
        assert 'e499' in out
        assert out.rstrip().endswith('e499')

    def test_aman_tanpa_atribut_stderr(self):
        class NoErr:
            pass
        drain = _proc.drain_stderr(NoErr())
        assert drain.tail() == ''

    def test_tail_deterministik_setelah_join(self):
        proc = FakeProc(stderr_lines=[f'line{i}\n' for i in range(50)])
        drain = _proc.drain_stderr(proc)
        assert 'line49' in drain.tail()      # join implisit di tail()


# ---------------------------------------------------------------------------
# Watchdog timeout (anti-stall)
# ---------------------------------------------------------------------------

class TestTimeoutWatchdog:
    def test_proses_menggantung_dimatikan(self):
        proc = FakeProc(hang=True)
        state = _proc.setup_timeout(proc, timeout=0.2)
        deadline = time.time() + 3
        while time.time() < deadline and not proc.killed:
            time.sleep(0.02)
        assert state['timed_out'] is True
        assert proc.killed is True

    def test_dibatalkan_tidak_mematikan_proses(self):
        proc = FakeProc(hang=True)
        state = _proc.setup_timeout(proc, timeout=0.3)
        _proc.cancel_timeout(state)
        time.sleep(0.6)
        assert proc.killed is False
        assert state['timed_out'] is False

    def test_tidak_menembak_proses_yang_sudah_selesai(self):
        proc = FakeProc(returncode=0)  # poll() != None → watchdog lewati
        state = _proc.setup_timeout(proc, timeout=0.05)
        time.sleep(0.4)
        assert proc.killed is False
        assert state['timed_out'] is False

    def test_timeout_nonaktif_bila_nol(self):
        assert _proc.setup_timeout(FakeProc(), timeout=0)['timer'] is None


# ---------------------------------------------------------------------------
# Integrasi dengan download_media
# ---------------------------------------------------------------------------

class TestDownloadMediaGuard:
    def test_pesan_error_memuat_isi_stderr(self, monkeypatch, tmp_path):
        """Gagal (returncode!=0) → pesan memuat stderr, bukti stderr dikuras."""
        proc = FakeProc(returncode=1,
                        stderr_lines=['ERROR: Video tidak tersedia\n'])
        monkeypatch.setattr(_proc, 'spawn', lambda cmd, workdir=None: proc)
        with pytest.raises(YtDlpError) as exc:
            download_media('https://youtu.be/x', 'audio', 0, str(tmp_path),
                           lambda p: None)
        assert 'Video tidak tersedia' in str(exc.value)

    def test_proses_menggantung_gagal_karena_timeout(self, monkeypatch, tmp_path):
        """Proses yang menguras stdout habis tapi tidak selesai → timeout."""
        proc = FakeProc(stdout_lines=['[download] Destination: '
                                      + os.path.join(str(tmp_path), 'src_x.webm')],
                        returncode=0, hang=True)
        monkeypatch.setattr(_proc, 'spawn', lambda cmd, workdir=None: proc)
        # batas waktu sangat pendek → watchdog mematikan proses
        monkeypatch.setattr(_proc, 'setup_timeout',
                            lambda p, t=None: _real_setup(p, 0.2))
        with pytest.raises(YtDlpError) as exc:
            download_media('https://youtu.be/x', 'audio', 0, str(tmp_path),
                           lambda p: None)
        assert 'batas waktu' in str(exc.value)
        assert proc.killed is True


_real_setup = _proc.setup_timeout  # simpan sebelum monkeypatch
