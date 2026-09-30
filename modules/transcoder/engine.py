"""
modules/transcoder/engine.py (v2.46.0)

Job manager konversi media dari link YouTube ke berbagai format output
audio (mp3/m4a/wav) & video (mp4/webm/mkv).

Desain:
- In-memory job registry (thread-safe via Lock) — pola sama dengan
  progress_tracker news_scraper; job lama dipangkas (MAX_JOBS).
- Tiap job = worker thread (daemon): unduh yt-dlp → transcode ffmpeg.
  Konkurensi dibatasi MAX_CONCURRENT (job lain menunggu antrean).
- Folder kerja job di-capture saat create_job (request context) — worker
  thread TIDAK memakai current_app (tidak punya app context).
- Fase job: queued → downloading → transcoding → done / error / cancelled.
- Progres: yt-dlp --newline + ffmpeg -progress pipe:1.
"""

import os
import re
import json
import shutil
import threading
import subprocess
import time

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

# format: (kind, label, ekstensi, argumen ffmpeg audio)
FORMATS = {
    'mp3':   ('audio', 'MP3 192 kbps',       'mp3',  ['-codec:a', 'libmp3lame', '-b:a', '192k']),
    'm4a':   ('audio', 'M4A (AAC) 128 kbps', 'm4a',  ['-codec:a', 'aac', '-b:a', '128k']),
    'wav':   ('audio', 'WAV (PCM 16-bit)',   'wav',  ['-codec:a', 'pcm_s16le']),
    'mp4':   ('video', 'MP4 720p',           'mp4',  []),
    'mp4hd': ('video', 'MP4 1080p',          'mp4',  []),
    'webm':  ('video', 'WebM (VP9)',         'webm', []),
    'mkv':   ('video', 'MKV (salin ulang)',  'mkv',  []),
}

VIDEO_HEIGHT = {'mp4': 720, 'mp4hd': 1080}   # webm/mkv tanpa skala ulang

MAX_CONCURRENT = 1          # server 3.8GB — transcode berat, antrekan
MAX_JOBS = 200              # batas entri registry (paling lama dibuang)
FILE_RETENTION_HOURS = 48   # hasil job selesai dihapus lewat usia ini
MAX_URLS_PER_REQUEST = 10   # batas multi-link per submit

# Unggah otomatis ke share publik Nextcloud (v2.46.2) — hasil bisa dibagikan
# lewat tautan publik. Boleh dimatikan lewat config share (auto_upload=false).
AUTO_UPLOAD_TO_NC = True

_URL_RE = re.compile(
    r'^(https?://)?(www\.|m\.|music\.)?'
    r'(youtube\.com/[\w\-/?=&.%]+|youtu\.be/[\w\-?=&.%]+)$',
    re.IGNORECASE,
)


def is_youtube_url(url: str) -> bool:
    """Validasi URL YouTube (youtu.be & youtube.com, opsional scheme)."""
    u = (url or '').strip()
    if not u:
        return False
    if not u.lower().startswith(('http://', 'https://')):
        u = 'https://' + u
    return bool(_URL_RE.match(u))


def _sanitize_name(name: str, maxlen: int = 60) -> str:
    """Nama file aman: huruf/angka/spasi/strip/underscore, tanpa traversal.
    Titik di awal dibuang (cegah '..' & dotfile)."""
    name = re.sub(r'[^\w\s.\-()]', '', (name or ''), flags=re.UNICODE).strip()
    name = re.sub(r'\s+', '_', name).lstrip('.')
    return name[:maxlen] or 'media'


# ---------------------------------------------------------------------------
# Job registry (in-memory, thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_jobs = {}          # job_id -> dict
_sem = threading.BoundedSemaphore(MAX_CONCURRENT)
_seq = [0]


def _new_job(urls, formats, user, base):
    _seq[0] += 1
    return {
        'id': f"tc{_seq[0]:06d}",
        'urls': list(urls),
        'formats': list(formats),
        'user': user,
        'status': 'queued',        # queued|downloading|transcoding|done|error|cancelled
        'stage': 'Menunggu antrean',
        'progress': 0,             # 0-100 keseluruhan
        'created_at': time.time(),
        'finished_at': None,
        'error': '',
        'items': [],               # per-link: {url,title,status,progress,stage_note,error,outputs}
        '_base': base,             # folder data/transcoder (internal)
        '_nc': {'auto': AUTO_UPLOAD_TO_NC, 'results': [], 'failed': False},
    }


def _public(job):
    """Salinan job tanpa kunci internal — kecuali status share publik."""
    out = {k: v for k, v in job.items() if not k.startswith('_')}
    nc = job.get('_nc') or {}
    out['nc'] = {'auto': nc.get('auto', False),
                 'urls': nc.get('results', []),
                 'failed': nc.get('failed', False),
                 'purged': nc.get('purged'),
                 'purge_detail': nc.get('purge_detail', '')}
    return out


def create_job(urls, formats, user, base):
    """Buat + jalankan job. `base` = folder data/transcoder (dari request)."""
    job = _new_job(urls, formats, user, base)
    with _lock:
        _jobs[job['id']] = job
        if len(_jobs) > MAX_JOBS:
            for jid in sorted(_jobs, key=lambda k: _jobs[k]['created_at'])[:-MAX_JOBS]:
                _cleanup_job_files(_jobs.pop(jid))
    threading.Thread(target=_worker, args=(job,), daemon=True,
                     name=f"transcode-{job['id']}").start()
    return _public(job)


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        return _public(job) if job else None


def list_jobs(limit=50):
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j['created_at'], reverse=True)
        return [_public(j) for j in jobs[:limit]]


def cancel_job(job_id, user):
    """Tandai cancel — worker berhenti di antara fase (best-effort)."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return False, 'Job tidak ditemukan'
        if job.get('user') != user and user != 'admin':
            return False, 'Bukan job Anda'
        if job['status'] in ('done', 'error', 'cancelled'):
            return False, 'Job sudah selesai'
        job['status'] = 'cancelled'
        job['stage'] = 'Dibatalkan oleh pengguna'
        return True, 'Job dibatalkan'


def delete_job(job_id, user):
    """Hapus job + file hasilnya lokal & salinan share publik (hanya job selesai)."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return False, 'Job tidak ditemukan'
        if job.get('user') != user and user != 'admin':
            return False, 'Bukan job Anda'
        if job['status'] not in ('done', 'error', 'cancelled'):
            return False, 'Job masih berjalan — batalkan dulu'
        _cleanup_job_files(job)
        del _jobs[job_id]
    return True, 'Job dihapus'


def _cleanup_job_files(job):
    """Hapus direktori kerja job (hasil + sementara). Panggil dgn lock pegang
    atau dari request context — tidak butuh app context.

    Retensi cermin (v2.46.3): folder job di share publik Nextcloud ikut
    dihapus bila unggahan pernah dilakukan — tautan publik otomatis mati
    seiring kedaluwarsa hasil lokal. Best-effort: gagal jaringan/izin tidak
    menggagalkan pembersihan lokal; status tercatat di job['_nc']."""
    base = job.get('_base') or ''
    if not base:
        return
    workdir = os.path.join(base, job['id'])
    if os.path.isdir(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
    nc = job.get('_nc') or {}
    if nc.get('results'):
        try:
            from . import ncshare
            ok, detail = ncshare.delete_folder(job['id'])
            nc['purged'] = ok
            nc['purge_detail'] = detail
        except Exception as e:
            nc['purged'] = False
            nc['purge_detail'] = str(e)[:120]
        print(f"[transcoder] purge share {job['id']}: "
              f"{nc.get('purge_detail', '?')}")


def cleanup_expired_files():
    """Hapus hasil job selesai lebih tua dari FILE_RETENTION_HOURS (lokal +
    salinan share publik). Dipanggil periodik dari thread latar."""
    with _lock:
        jobs = list(_jobs.values())
    cutoff = time.time() - FILE_RETENTION_HOURS * 3600
    for job in jobs:
        if job['status'] in ('done', 'error', 'cancelled') and \
           job.get('finished_at') and job['finished_at'] < cutoff:
            _cleanup_job_files(job)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _update(job, **kw):
    with _lock:
        job.update(kw)


def _update_item(job, idx, **kw):
    with _lock:
        if idx < len(job['items']):
            job['items'][idx].update(kw)


def _worker(job):
    with _sem:
        if job['status'] == 'cancelled':
            return
        base = job.get('_base') or ''
        if not base:
            _update(job, status='error', error='Folder transcoder belum diset',
                    stage='Gagal', finished_at=time.time())
            return
        workdir = os.path.join(base, job['id'])
        os.makedirs(workdir, exist_ok=True)

        _update(job, status='downloading', stage='Memproses…')
        total = max(len(job['urls']), 1)
        try:
            for idx, url in enumerate(job['urls']):
                if job['status'] == 'cancelled':
                    return
                with _lock:
                    job['items'].append({'url': url, 'title': '',
                                         'status': 'downloading', 'progress': 0,
                                         'stage_note': '', 'error': '', 'outputs': []})
                try:
                    _process_one(job, idx, url, workdir)
                except _CancelledError:
                    return
                except Exception as e:  # satu link gagal tidak menghentikan yang lain
                    _update_item(job, idx, status='error', error=str(e)[:300],
                                 stage_note='Gagal')
                done = sum(1 for it in job['items'] if it['status'] in ('done', 'error'))
                _update(job, progress=int(done * 100 / total))
        finally:
            with _lock:
                if job['status'] != 'cancelled':
                    items = job['items']
                    if items and all(it['status'] == 'done' for it in items):
                        job['status'] = 'done'
                        job['stage'] = 'Selesai'
                    elif any(it['status'] == 'done' for it in items):
                        job['status'] = 'done'
                        job['stage'] = 'Selesai — sebagian link gagal'
                    else:
                        job['status'] = 'error'
                        job['stage'] = 'Gagal'
                    job['finished_at'] = time.time()


class _CancelledError(Exception):
    pass


def _check_cancel(job):
    if job['status'] == 'cancelled':
        raise _CancelledError()


def _process_one(job, idx, url, workdir):
    from .ytdlp import download_media, probe_title  # import lokal: mudah di-mock di test

    _update_item(job, idx, stage_note='Mengambil info…')
    title = probe_title(url) or 'media'
    _update_item(job, idx, title=title)

    safe = _sanitize_name(title)
    for fmt in job['formats']:
        _check_cancel(job)
        kind, label, ext, aflags = FORMATS[fmt]
        out = os.path.join(workdir, f"{safe}.{ext}")
        n = 2
        while os.path.exists(out):
            out = os.path.join(workdir, f"{safe}({n}).{ext}")
            n += 1

        _update_item(job, idx, status='transcoding',
                     stage_note=f'Membuat {label}…', progress=0)
        src = download_media(url, kind, VIDEO_HEIGHT.get(fmt, 0), workdir,
                             lambda p: _update_item(job, idx, progress=p))
        _check_cancel(job)
        if kind == 'video':
            _transcode_video(src, out, fmt, workdir,
                             lambda p: _update_item(job, idx, progress=p))
        else:
            _transcode_audio(src, out, aflags,
                             lambda p: _update_item(job, idx, progress=p))
        with _lock:
            job['items'][idx]['outputs'].append({
                'format': fmt, 'label': label, 'kind': kind,
                'file': os.path.basename(out),
                'size': os.path.getsize(out),
            })
        if (job.get('_nc') or {}).get('auto'):
            _nc_upload(job, out)
    _update_item(job, idx, status='done', progress=100, stage_note='')


# ---------------------------------------------------------------------------
# Unggah ke share publik Nextcloud (best-effort — gagal tidak menggagalkan job)
# ---------------------------------------------------------------------------

def _nc_upload(job, filepath):
    """Unggah satu hasil ke share publik; catat URL di job['_nc']."""
    try:
        from . import ncshare
        url = ncshare.upload_file(job['id'], os.path.basename(filepath), filepath)
        with _lock:
            job['_nc']['results'].append(url)
    except Exception as e:
        with _lock:
            job['_nc']['failed'] = True
            job['_nc']['error'] = str(e)[:200]
        print(f'[transcoder] unggah Nextcloud gagal: {e}')


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def _run_ffmpeg(input_args, duration, on_progress, workdir):
    """Jalankan ffmpeg dengan -progress pipe:1; on_progress(0-100)."""
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
           '-progress', 'pipe:1'] + input_args
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=workdir)
    for line in proc.stdout:
        if line.startswith('out_time_us=') or line.startswith('out_time_ms='):
            try:
                val = int(line.split('=', 1)[1])
                # ffmpeg: out_time_us=mikrodetik (baru), out_time_ms=µs (legacy)
                if duration > 0:
                    secs = val / 1_000_000
                    on_progress(min(99, int(secs / duration * 100)))
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read()[-400:]
        raise RuntimeError(f'ffmpeg gagal: {err}')


def _probe_duration(path):
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'json', path],
            capture_output=True, text=True, timeout=30)
        return float(json.loads(out.stdout)['format']['duration'])
    except Exception:
        return 0.0


def _transcode_audio(src, out, aflags, on_progress):
    duration = _probe_duration(src)
    args = ['-i', src, '-vn', *aflags, os.path.basename(out)]
    _run_ffmpeg(args, duration, on_progress, os.path.dirname(out))


def _transcode_video(src, out, fmt, workdir, on_progress):
    duration = _probe_duration(src)
    name = os.path.basename(out)
    if fmt == 'mkv':
        # salin ulang stream (cepat, tanpa re-encode)
        args = ['-i', src, '-codec', 'copy', name]
    elif fmt == 'webm':
        # VP9 cpu-used 8: kompromi kecepatan utk CPU lemah
        args = ['-i', src, '-codec:v', 'libvpx-vp9', '-cpu-used', '8',
                '-crf', '34', '-b:v', '0', '-row-mt', '1',
                '-codec:a', 'libopus', '-b:a', '128k', name]
    else:  # mp4 / mp4hd — skala & re-encode x264
        h = VIDEO_HEIGHT[fmt]
        args = ['-i', src, '-vf', f'scale=-2:min({h},ih)',
                '-codec:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-codec:a', 'aac', '-b:a', '160k', name]
    _run_ffmpeg(args, duration, on_progress, workdir)
