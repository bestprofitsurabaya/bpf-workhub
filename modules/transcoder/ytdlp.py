"""
modules/transcoder/ytdlp.py (v2.46.0)

Pembungkus yt-dlp: ambil judul, unduh audio/video terbaik sesuai kebutuhan
transcode. Semua unduhan dikarantina di workdir job — path keluaran selalu
di bawah workdir (dipastikan via os.path.realpath).

yt-dlp & ffmpeg dipanggil sebagai subprocess agar versi mudah dinaikkan
tanpa menyentuh API Python.
"""

import os
import re
import subprocess

from . import _proc


class YtDlpError(RuntimeError):
    pass


def _base_cmd():
    return ['yt-dlp', '--no-playlist', '--no-warnings', '--no-progress']


def probe_title(url: str) -> str:
    """Judul video utk penamaan file; gagal → string kosong."""
    try:
        out = subprocess.run(
            _base_cmd() + ['--get-title', url],
            capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0][:200]
    except Exception:
        pass
    return ''


def _inside(workdir, path):
    return os.path.realpath(path).startswith(os.path.realpath(workdir) + os.sep)


def _parse_stdout_path(line: str):
    """Ambil path berkas dari baris progres yt-dlp, bila ada."""
    m = re.match(r'^.*\[(?:download|Merger)\]\s*(?:Destination|Merger|Merging formats into)\s*:?"?(.+?)"?\s*$', line)
    if m:
        path = m.group(1).strip()
        path = re.sub(r'\s+has already been downloaded$', '', path)
        if path.endswith(".part"):
            path = path[:-len(".part")]
        return path
    m = re.match(r'^.*\[download\]\s*(.+?)\s+has already been downloaded', line)
    if m:
        return m.group(1).strip()
    return None


def download_media(url, kind, max_height, workdir, on_progress) -> str:
    """Unduh sumber ke workdir; return path file hasil.

    kind 'audio' → bestaudio; 'video' → bestvideo+batasto tinggi
    (disingkat bila > max_height). on_progress(pct 0-100) dipanggil reguler.
    """
    outtmpl = os.path.join(workdir, 'src_%(id)s.%(ext)s')
    cmd = _base_cmd() + ['-o', outtmpl, '--newline', url]
    if kind == 'audio':
        cmd += ['-f', 'bestaudio/best']
    else:
        h = int(max_height or 0)
        if h:
            cmd += ['-f', f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best']
        else:
            cmd += ['-f', 'bestvideo+bestaudio/best']
        cmd += ['--merge-output-format', 'mp4']

    # v2.46.7: spawn + kuras stderr paralel + watchdog timeout (lihat _proc.py).
    # Dulu stderr hanya dibaca setelah stdout habis → berisiko deadlock pipe
    # dan tanpa batas waktu → job bisa menggantung selamanya.
    proc = _proc.spawn(cmd)
    errs = _proc.drain_stderr(proc)
    tstate = _proc.setup_timeout(proc)
    reported = None
    try:
        for line in proc.stdout:
            line = line.rstrip()
            # --newline: baris [download]  23.4% of ...
            if line.startswith('[download]') and '%' in line and reported is None:
                try:
                    pct = float(line.split('%')[0].split()[-1])
                    on_progress(int(pct))
                except (ValueError, IndexError):
                    pass
            # Ambil path persis dari yt-dlp — jangan menebak dari mtime.
            p = _parse_stdout_path(line)
            if p and _inside(workdir, p) and not p.endswith(('.part', '.ytdl')):
                reported = p  # unduhan ini yang paling akhir melapor
        proc.wait()
    finally:
        _proc.cancel_timeout(tstate)
    if tstate['timed_out']:
        raise YtDlpError(f'yt-dlp melewati batas waktu {tstate["timeout"]}s')
    if proc.returncode != 0:
        raise YtDlpError(f'yt-dlp gagal: {errs.tail()}')

    if reported:
        return reported

    # Fallback (mis. baris path tidak tersedia): file src_* terbaru yang
    # BUKAN part/merge sementara — tetap bisa salah bila workdir dipakai
    # bareng, tapi jauh lebih aman daripada dulu.
    cands = [os.path.join(workdir, f) for f in os.listdir(workdir)
             if f.startswith('src_') and not f.endswith(('.part', '.ytdl', '.tmp'))]
    if not cands:
        raise YtDlpError('yt-dlp tidak menghasilkan berkas')
    newest = max(cands, key=os.path.getmtime)
    if not _inside(workdir, newest):
        raise YtDlpError('path keluaran di luar workdir')
    return newest
