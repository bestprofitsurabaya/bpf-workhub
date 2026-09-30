"""
modules/transcoder/ytdlp.py (v2.46.0)

Pembungkus yt-dlp: ambil judul, unduh audio/video terbaik sesuai kebutuhan
transcode. Semua unduhan dikarantina di workdir job — path keluaran selalu
di bawah workdir (dipastikan via os.path.realpath).

yt-dlp & ffmpeg dipanggil sebagai subprocess agar versi mudah dinaikkan
tanpa menyentuh API Python.
"""

import os
import subprocess

from flask import current_app


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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    for line in proc.stdout:
        line = line.strip()
        # --newline: baris [download]  23.4% of ...
        if line.startswith('[download]') and '%' in line:
            try:
                pct = float(line.split('%')[0].split()[-1])
                on_progress(int(pct))
            except (ValueError, IndexError):
                pass
    proc.wait()
    if proc.returncode != 0:
        raise YtDlpError(f'yt-dlp gagal: {proc.stderr.read()[-300:]}')

    # cari file src_* terbaru di workdir
    cands = [os.path.join(workdir, f) for f in os.listdir(workdir)
             if f.startswith('src_')]
    if not cands:
        raise YtDlpError('yt-dlp tidak menghasilkan berkas')
    newest = max(cands, key=os.path.getmtime)
    if not _inside(workdir, newest):
        raise YtDlpError('path keluaran di luar workdir')
    return newest
