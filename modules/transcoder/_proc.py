"""Helper subprocess aman untuk transcoder (v2.46.7).

Masalah yang diperbaiki (audit 15 Okt 2026):
yt-dlp & ffmpeg dipanggil dengan `stderr=subprocess.PIPE`, tetapi stderr hanya
dibaca SETELAH stdout habis (`proc.stderr.read()`). Bila proses anak menulis
lebih dari kapasitas buffer pipe (~64 KB) ke stderr, anak memblokir saat
menulis sementara induk memblokir saat membaca stdout → **deadlock**. Karena
antrean transcoder memakai MAX_CONCURRENT=1, satu proses macet membuat seluruh
antrean macet permanen sampai container di-restart.

Helper ini menutup dua celah:
1. `drain_stderr()` menguras stderr di thread daemon (buffer terbatas) → pipe
   tak pernah penuh, tidak ada deadlock. `StderrDrain.tail()` menunggu thread
   selesai dulu sehingga pesan error deterministik (tidak race).
2. `setup_timeout()` memasang watchdog yang mematikan proses bila melewati
   batas waktu → job gagal dengan pesan jelas, bukan menggantung selamanya.

Modul ini murni stdlib dan tidak bergantung Flask, agar mudah diuji.
"""
import os
import subprocess
import threading
from collections import deque

# Batas waktu proses (detik). Longgar untuk unduhan/kodek panjang, tapi tidak
# selamanya. Dapat diubah lewat env tanpa mengubah kode. 0 / negatif = tanpa
# batas (dipakai hanya bila operator benar-benar menginginkannya).
DEFAULT_PROC_TIMEOUT = int(os.environ.get('TRANSCODER_PROC_TIMEOUT', '3600'))

# Simpan hanya N baris terakhir stderr — cukup untuk pesan error, tanpa
# menahan memori bila proses sangat cerewet.
_STDERR_TAIL_LINES = 200


class ProcessTimeout(RuntimeError):
    """Proses anak melewati batas waktu dan dihentikan paksa."""


class StderrDrain:
    """Penguras stderr di thread daemon (anti-deadlock).

    `tail()` MENUNGGU thread selesai dulu (dengan batas) supaya isi buffer
    tidak terbaca setengah jalan.
    """

    def __init__(self, stream=None):
        self._lines = deque(maxlen=_STDERR_TAIL_LINES)
        self._thread = None
        if stream is not None:
            self._thread = threading.Thread(
                target=self._run, args=(stream,), daemon=True)
            self._thread.start()

    def _run(self, stream):
        try:
            for line in stream:
                self._lines.append(line)
        except Exception:
            pass  # pipe ditutup / proses mati — tidak fatal

    def join(self, timeout=5):
        if self._thread is not None:
            self._thread.join(timeout)

    def tail(self, limit=300, wait=True):
        """N karakter terakhir stderr; tunggu penguras selesai (default)."""
        if wait:
            self.join()
        return ''.join(self._lines)[-limit:]


def spawn(cmd, workdir=None):
    """Popen teks dengan stdout+stderr PIPE (sumber tunggal bagi transcoder)."""
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=workdir)


def drain_stderr(proc):
    """Mulai menguras stderr `proc`; kembalikan StderrDrain.

    Aman untuk objek proses palsu pada tes yang tidak punya atribut stderr.
    """
    return StderrDrain(getattr(proc, 'stderr', None))


def setup_timeout(proc, timeout=None):
    """Pasang watchdog `kill` bila proses melewati `timeout` detik.

    Mengembalikan state dict; `state['timed_out']` menjadi True hanya bila
    watchdog benar-benar menembak (proses belum selesai saat itu).
    """
    timeout = DEFAULT_PROC_TIMEOUT if timeout is None else timeout
    state = {'timed_out': False, 'timer': None, 'timeout': timeout}
    if not timeout or timeout <= 0:
        return state

    def _kill():
        # Lewati bila proses ternyata sudah selesai (hindari false positive).
        poll = getattr(proc, 'poll', None)
        if callable(poll):
            try:
                if poll() is not None:
                    return
            except Exception:
                pass
        state['timed_out'] = True
        try:
            proc.kill()
        except Exception:
            pass

    timer = threading.Timer(timeout, _kill)
    timer.daemon = True
    timer.start()
    state['timer'] = timer
    return state


def cancel_timeout(state):
    """Batalkan watchdog (dipanggil setelah proses selesai normal)."""
    timer = state.get('timer') if state else None
    if timer is not None:
        try:
            timer.cancel()
        except Exception:
            pass
