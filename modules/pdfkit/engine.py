"""modules/pdfkit/engine.py (v2.47.0)

Mesin kompresi PDF untuk halaman IT (role `it_*` + admin).

## Dua mesin, dipilih per mode

- **qpdf** — kompresi **lossless struktural** (`--object-streams=generate`,
  `--recompress-flate --compression-level=9`). Teks, vektor, tautan, dan
  gambar asli tidak diubah sama sekali. Lazimnya 5–30% lebih kecil; PDF yang
  sudah rapat bisa **tidak** menyusut (uji: 1,71 MB → 1,71 MB).
- **Ghostscript** (`-sDEVICE=pdfwrite`) — kompresi **lossy bertingkat**:
  gambar di-downsample (dan di-JPEG-kan di mode `maksimal`), sedangkan teks &
  vektor tetap teks sehingga masih bisa dicari/copy. Hemat besar untuk PDF
  hasil scan/foto (uji: 1,71 MB → 121 KB pada mode `maksimal`).

## Guard sebelum kompresi (daftar lindungi otomatis)

1. **Dokumen terbitan sistem** — bila `sha256` file ada di `document_registry`
   (`modules/doc_integrity.py`), file **dilewati**: mengompresnya mematahkan
   verifikasi keaslian `POST /api/documents/verify` (dokumen air minum,
   laporan overtime, laporan in-out). Inilah "dokumen yang tidak boleh
   dikompres" — diputuskan otomatis, bukan manual.
2. **PDF bertanda tangan digital** (`pdfsig`) — dilewati: kompresi
   membatalkan tanda tangan.
3. **PDF terenkripsi** (`pdfinfo` → `Encrypted: yes`) — dilewati: butuh
   password yang tidak dimiliki aplikasi.
4. **Tanpa perbaikan berarti** — hasil yang lebih besar atau hanya menyusut
   < 2% dibuang; item ditandai `skipped` ("sudah optimal") supaya IT tidak
   mengunduh file yang tak berguna. File **asli tidak pernah ditimpa** —
   hasil selalu file terpisah di folder job.

Desain job mencerminkan `modules/transcoder/engine.py`: registry in-memory
thread-safe, satu worker thread per job, antrean `MAX_CONCURRENT=1` (Ghostscript
haus RAM di server 3,8 GB), hasil di `data/transcoder/pdfkit/<job_id>/out`.
"""

import os
import re
import shutil
import threading
import time

from modules.transcoder import _proc  # reuse anti-deadlock + watchdog subprocess

# ---------------------------------------------------------------------------
# Mode kompresi
# ---------------------------------------------------------------------------

# kind: 'lossless' (qpdf) | 'gs' (Ghostscript bertingkat) | 'auto' (rantai)
MODES = {
    'lossless': {
        'label': 'Lossless (aman)',
        'hint': 'Struktur & stream PDF dirapikan. Teks, tautan, dan gambar asli tidak disentuh.',
        'kind': 'lossless', 'needs_target': False,
    },
    'ringan': {
        'label': 'Ringan — 150 dpi',
        'hint': 'Gambar diturunkan ke 150 dpi. Untuk scan/foto 300 dpi.',
        'kind': 'gs', 'dpi': 150, 'needs_target': False,
    },
    'sedang': {
        'label': 'Sedang — 120 dpi',
        'hint': 'Seimbang: masih enak dibaca di layar & cetak biasa.',
        'kind': 'gs', 'dpi': 120, 'needs_target': False,
    },
    'kuat': {
        'label': 'Kuat — 100 dpi',
        'hint': 'Kecil, teks tetap tajam (teks bukan gambar). Untuk arsip kirim email.',
        'kind': 'gs', 'dpi': 100, 'needs_target': False,
    },
    'maksimal': {
        'label': 'Maksimal — 72 dpi + JPEG',
        'hint': 'Paling kecil. Gambar di-JPEG-kan; cocok untuk lampiran scan.',
        'kind': 'gs', 'dpi': 72, 'jpeg': True, 'needs_target': False,
    },
    'target': {
        'label': 'Target ukuran (otomatis)',
        'hint': 'Coba lossless → ringan → kuat → maksimal sampai ukuran target tercapai.',
        'kind': 'auto', 'needs_target': True,
    },
}

# Rantai mode auto ('target'): dari paling aman ke paling agresif.
AUTO_CHAIN = ('lossless', 'ringan', 'kuat', 'maksimal')

MAX_CONCURRENT = 1          # Ghostscript haus RAM — antrekan
MAX_JOBS = 200              # batas entri registry (paling lama dibuang)
FILE_RETENTION_HOURS = 48   # hasil job selesai dihapus lewat usia ini
MAX_FILES_PER_JOB = 10
MAX_FILE_MB = 100           # batas per berkas
MAX_TOTAL_MB = 250          # batas total sekali submit
PROC_TIMEOUT = 600          # detik per berkas (gs/qpdf PDF besar bisa lama)
MIN_GAIN_PCT = 2.0          # < 2% → dianggap tidak ada perbaikan


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------

def _safe_stem(name: str, maxlen: int = 80) -> str:
    """Nama berkas aman: tanpa path/traversal, karakter aneh dibuang."""
    stem = os.path.basename(str(name or '')).rsplit('.', 1)[0]
    stem = re.sub(r'[^\w\s().\-]', '', stem, flags=re.UNICODE).strip()
    stem = re.sub(r'\s+', ' ', stem).lstrip('.')
    return (stem[:maxlen] or 'dokumen')


def _pct(before: int, after: int) -> float:
    """Persentase penghematan (0–100, selalu ≥ 0)."""
    if not before:
        return 0.0
    return round(max(0.0, (before - after) * 100.0 / before), 1)


def _run(cmd, workdir=None, timeout=None):
    """Jalankan perintah eksternal tanpa deadlock; return (ok, stderr_tail)."""
    try:
        proc = _proc.spawn(cmd, workdir=workdir)
    except FileNotFoundError as e:
        return False, f'perintah tidak ditemukan: {e}'
    except Exception as e:
        return False, str(e)[:300]
    errs = _proc.drain_stderr(proc)
    state = _proc.setup_timeout(proc, timeout or PROC_TIMEOUT)
    try:
        proc.wait()
    finally:
        _proc.cancel_timeout(state)
    if state['timed_out']:
        return False, f'melewati batas waktu {state["timeout"]}s'
    if proc.returncode != 0:
        return False, (errs.tail(300) or f'exit code {proc.returncode}')
    return True, ''


def probe(path):
    """Baca sifat PDF via poppler: halaman, enkripsi, tanda tangan, ada teks?.

    Selalu mengembalikan dict (gagal baca → nilai default konservatif),
    tidak pernah raise.
    """
    info = {'pages': 0, 'encrypted': False, 'signed': False, 'has_text': False,
            'version': '', 'optimized': False}
    try:
        ok, out = _run_capture(['pdfinfo', path])
        if ok:
            for line in out.splitlines():
                low = line.lower()
                if low.startswith('pages:'):
                    info['pages'] = int(re.sub(r'\D', '', line.split(':', 1)[1]) or 0)
                elif low.startswith('encrypted:') and 'no' not in low:
                    info['encrypted'] = True
                elif low.startswith('pdf version:'):
                    info['version'] = line.split(':', 1)[1].strip()
                elif low.startswith('optimized:') and 'yes' in low:
                    info['optimized'] = True
    except Exception:
        pass
    # pdfsig: exit 0 = ada tanda tangan; exit 2 = tidak ada (pesan ke stderr).
    try:
        ok, out = _run_capture(['pdfsig', path])
        info['signed'] = bool(ok and re.search(r'Signature\s*#?\d', out, re.I))
    except Exception:
        pass
    try:
        ok, out = _run_capture(['pdftotext', '-f', '1', '-l', '3', path, '-'])
        info['has_text'] = bool(ok and out and out.strip())
    except Exception:
        pass
    return info


def _run_capture(cmd, timeout=60):
    """Jalankan perintah & tangkap stdout (tanpa deadlock, best-effort)."""
    try:
        proc = _proc.spawn(cmd)
    except FileNotFoundError as e:
        return False, f'perintah tidak ditemukan: {e}'
    errs = _proc.drain_stderr(proc)
    state = _proc.setup_timeout(proc, timeout)
    try:
        out = proc.stdout.read() or ''
        proc.wait()
    finally:
        _proc.cancel_timeout(state)
    if state['timed_out'] or proc.returncode not in (0, 2):
        return False, out
    return True, out


# ---------------------------------------------------------------------------
# Guard integritas / keamanan
# ---------------------------------------------------------------------------

def registry_row(sha256_hex):
    """Baris `document_registry` untuk hash ini, atau None (best-effort).

    Dipakai sebagai daftar lindungi otomatis: PDF yang diterbitkan aplikasi
    (air minum, overtime, laporan in-out) tidak boleh dikompres karena
    hash-nya dipakai memverifikasi keaslian dokumen.
    """
    if not sha256_hex:
        return None
    try:
        from modules.doc_integrity import lookup_sha256
        return lookup_sha256(sha256_hex)
    except Exception as e:
        print(f'[pdfkit] cek registri gagal (lanjut tanpa proteksi): {e}')
        return None


def guard_reason(item, info, row):
    """Alasan item TIDAK boleh/tidak bisa dikompres — '' bila aman diproses."""
    if row:
        doc = row.get('doc_no') or row.get('doc_type') or 'terdaftar'
        return (f'Dokumen terbitan sistem ({doc}) terdaftar di registri '
                f'integritas — dikompres akan mematahkan verifikasi keaslian '
                f'(POST /api/documents/verify). Dilewati.')
    if info.get('signed'):
        return ('PDF bertanda tangan digital — kompresi membatalkan tanda '
                'tangan. Dilewati.')
    if info.get('encrypted'):
        return 'PDF terenkripsi (butuh password) — tidak bisa diproses. Dilewati.'
    return ''


# ---------------------------------------------------------------------------
# Mesin kompresi
# ---------------------------------------------------------------------------

def gs_cmd(src, out, mode):
    """Perintah Ghostscript untuk mode bertingkat (pdfwrite)."""
    cfg = MODES[mode]
    dpi = int(cfg.get('dpi') or 150)
    cmd = [
        'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.5',
        '-dNOPAUSE', '-dBATCH', '-dQUIET', '-dSAFER',
        '-dDetectDuplicateImages=true',
        '-dCompressFonts=true', '-dSubsetFonts=true',
        '-dPreserveAnnots=true', '-dAutoRotatePages=/None',
        '-dDownsampleColorImages=true', '-dDownsampleGrayImages=true',
        '-dColorImageDownsampleType=/Bicubic',
        '-dGrayImageDownsampleType=/Bicubic',
        f'-dColorImageResolution={dpi}',
        f'-dGrayImageResolution={dpi}',
        '-dMonoImageResolution=300',
    ]
    if cfg.get('jpeg'):
        # JPEG pada gambar berwarna & abu-abu; hitam-putih tetap CCITT/Flate.
        cmd += ['-dAutoFilterColorImages=false', '-dColorImageFilter=/DCTEncode',
                '-dAutoFilterGrayImages=false', '-dGrayImageFilter=/DCTEncode']
    cmd += [f'-sOutputFile={out}', src]
    return cmd


def qpdf_cmd(src, out):
    """Perintah qpdf — kompresi lossless struktural (tanpa ubah kualitas)."""
    return ['qpdf', '--object-streams=generate', '--compress-streams=y',
            '--recompress-flate', '--compression-level=9', src, out]


def compress_with(src, out, mode):
    """Jalankan satu mesin untuk satu mode. Return (ok, error, mode_dipakai)."""
    cmd = qpdf_cmd(src, out) if MODES[mode]['kind'] == 'lossless' else gs_cmd(src, out, mode)
    ok, err = _run(cmd, workdir=os.path.dirname(out))
    if not ok or not os.path.exists(out) or os.path.getsize(out) == 0:
        # Buang sisa file gagal supaya tidak terunduh setengah jadi.
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return False, err or 'tidak ada keluaran', mode
    return True, '', mode


def compress_chain(src, out, mode, target_bytes=0, on_step=None):
    """Kompres `src` → `out`.

    mode normal  : satu mesin. Bila hasilnya tidak lebih kecil, mesin
                   berikutnya yang lebih kuat tetap TIDAK dijalankan (pilihan
                   user dihormati) — cukup laporkan apa adanya.
    mode 'target': iterasi AUTO_CHAIN sampai `target_bytes` tercapai /
                   rantai habis; keluaran akhir = yang terkecil.

    Return dict {ok, mode_used, error, tried: [mode…]}.
    """
    if mode == 'target':
        candidates = list(AUTO_CHAIN)
    else:
        candidates = [mode]

    best = None            # (size, mode, path)
    tried = []
    for i, m in enumerate(candidates):
        tmp = f'{out}.{m}.tmp'
        ok, err, used = compress_with(src, tmp, m)
        tried.append(m)
        if on_step:
            on_step(m)
        if not ok:
            if i == 0 and len(candidates) == 1:
                return {'ok': False, 'mode_used': '', 'error': err, 'tried': tried}
            print(f'[pdfkit] mode {m} gagal: {err}')
            continue
        size = os.path.getsize(tmp)
        if best is None or size < best[0]:
            if best is not None:
                try:
                    os.remove(best[2])
                except OSError:
                    pass
            best = (size, m, tmp)
        else:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if target_bytes and size <= target_bytes:
            break                      # target tercapai — berhenti lebih awal

    if best is None:
        return {'ok': False, 'mode_used': '', 'error': 'semua mode gagal', 'tried': tried}
    if os.path.exists(out):
        try:
            os.remove(out)
        except OSError:
            pass
    shutil.move(best[2], out)
    return {'ok': True, 'mode_used': best[1], 'error': '', 'tried': tried}


# ---------------------------------------------------------------------------
# Job registry (in-memory, thread-safe) — pola modules/transcoder/engine.py
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_jobs = {}
_sem = threading.BoundedSemaphore(MAX_CONCURRENT)
_seq = [0]


def _new_job(files, mode, target_mb, user, base, role='', branch_code='',
             display=''):
    _seq[0] += 1
    return {
        'id': f'pk{_seq[0]:06d}',
        'mode': mode,
        'target_mb': target_mb or 0,
        'user': user,
        # Nama tampilan (full_name) dipakai sebagai identitas tunggal di
        # activity_logs: submit & done HARUS memakai nama yang sama, kalau tidak
        # laporan pemakaian memecah satu orang jadi dua baris.
        'display': display or user,
        'role': role,              # v2.47.0: untuk laporan pemakaian
        '_branch': branch_code,    # DB cabang tempat audit ditulis (internal)
        'status': 'queued',        # queued|running|done|error|cancelled
        'stage': 'Menunggu antrean',
        'progress': 0,
        'created_at': time.time(),
        'finished_at': None,
        'error': '',
        'saved_bytes': 0,
        'ratio_pct': 0.0,
        'items': [{
            'name': f['name'],
            'size_before': int(f.get('size') or 0),
            'size_after': 0,
            'ratio_pct': 0.0,
            'pages': 0,
            'mode_used': '',
            'text_kept': None,
            'status': 'pending',   # pending|running|done|skipped|protected|error
            'note': '',
            'error': '',
            'outputs': [],
            '_path': f['path'],            # berkas staging (dipindah saat jalan)
            '_sha256': f.get('sha256') or '',
        } for f in files],
        '_base': base,
    }


def _public(job):
    """Salinan job tanpa kunci internal (diawali '_')."""
    out = {k: v for k, v in job.items() if not k.startswith('_')}
    out['items'] = [{k: v for k, v in it.items() if not k.startswith('_')}
                    for it in job.get('items', [])]
    out['created_at_iso'] = _iso(job.get('created_at'))
    return out


def _iso(ts):
    if not ts:
        return ''
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def create_job(files, mode, target_mb, user, base, role='', branch_code='',
               display=''):
    """Buat + jalankan job. `files` = [{name, path (staging), size, sha256}].

    `base` = folder data/transcoder/pdfkit (dari request context);
    `role`/`branch_code`/`display` dari sesi untuk jejak audit laporan pemakaian.
    """
    job = _new_job(files, mode, target_mb, user, base, role=role,
                   branch_code=branch_code, display=display)
    with _lock:
        _jobs[job['id']] = job
        if len(_jobs) > MAX_JOBS:
            for jid in sorted(_jobs, key=lambda k: _jobs[k]['created_at'])[:-MAX_JOBS]:
                _cleanup_job_files(_jobs.pop(jid))
    cleanup_expired_files()
    threading.Thread(target=_worker, args=(job,), daemon=True,
                     name=f"pdfkit-{job['id']}").start()
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
    """Hapus folder kerja job (staging + hasil). Tidak butuh app context."""
    base = job.get('_base') or ''
    if base:
        workdir = os.path.join(base, job['id'])
        if os.path.isdir(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
    for it in job.get('items', []):
        path = it.get('_path') or ''        # berkas staging yang belum dipindah
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def cleanup_expired_files():
    """Hapus hasil job selesai yang lebih tua dari FILE_RETENTION_HOURS."""
    cutoff = time.time() - FILE_RETENTION_HOURS * 3600
    with _lock:
        jobs = list(_jobs.values())
    for job in jobs:
        if job['status'] in ('done', 'error', 'cancelled') and \
           job.get('finished_at') and job['finished_at'] < cutoff:
            _cleanup_job_files(job)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class _CancelledError(Exception):
    pass


def _update(job, **kw):
    with _lock:
        job.update(kw)


def _update_item(job, idx, **kw):
    with _lock:
        job['items'][idx].update(kw)


def _summary(job):
    """Hitung total sebelum/sesudah + rasio penghematan job."""
    before = sum(it['size_before'] for it in job['items'])
    after = sum(it['size_after'] for it in job['items'] if it['size_after'])
    return {'saved_bytes': max(0, before - after),
            'ratio_pct': _pct(before, after) if after else 0.0}


def _worker(job):
    with _sem:
        if job['status'] == 'cancelled':
            return
        base = job.get('_base') or ''
        if not base:
            _update(job, status='error', error='Folder PDF Kit belum diset',
                    stage='Gagal', finished_at=time.time())
            return
        workdir = os.path.join(base, job['id'])
        os.makedirs(os.path.join(workdir, 'in'), exist_ok=True)
        os.makedirs(os.path.join(workdir, 'out'), exist_ok=True)
        _update(job, status='running', stage='Mengompres…')

        total = max(len(job['items']), 1)
        for idx, item in enumerate(list(job['items'])):
            if job['status'] == 'cancelled':
                return
            _update_item(job, idx, status='running')
            try:
                _process_item(job, idx, workdir)
            except _CancelledError:
                return
            except Exception as e:
                _update_item(job, idx, status='error', error=str(e)[:300],
                             note='Gagal diproses')
            done = sum(1 for it in job['items']
                       if it['status'] in ('done', 'skipped', 'protected', 'error'))
            _update(job, progress=int(done * 100 / total), **_summary(job))

        # v2.47.0: catat hasil ke activity_logs (laporan pemakaian di Audit Log)
        # SEBELUM status final diumumkan — pemanggil yang menunggu status
        # 'done' (polling UI / `_wait` pada tes) dijamin sudah melewati
        # pencatatan, jadi tidak ada tulisan audit yang menyusul setelah job
        # dianggap selesai. Diluar lock; log_activity_async mengantre ke thread
        # lain. Job batal tidak dicatat (bukan pemakaian).
        if job['status'] != 'cancelled':
            _audit_done(job)

        with _lock:
            if job['status'] == 'cancelled':
                return
            items = job['items']
            ok_items = [it for it in items if it['status'] == 'done']
            if ok_items:
                job['status'] = 'done'
                job['stage'] = ('Selesai' if len(ok_items) == len(items)
                                else 'Selesai — sebagian dilewati/gagal')
            elif any(it['status'] in ('skipped', 'protected') for it in items):
                job['status'] = 'done'
                job['stage'] = 'Tidak ada berkas yang dikompres (lihat catatan)'
            else:
                job['status'] = 'error'
                job['stage'] = 'Gagal'
            job['finished_at'] = time.time()
            job.update(_summary(job))


def _audit_done(job):
    """Tulis ringkasan job ke `activity_logs` (action `pdfkit_done`).

    Best-effort dari worker thread: `log_activity_async` membuka koneksi
    sendiri, jadi tidak butuh app context — kegagalan audit tak boleh
    menggagalkan job. Angka inilah sumber laporan pemakaian PDF Kit
    (`/api/pdfkit/report`, halaman Audit Log).
    """
    try:
        from modules.helpers import log_activity_async
        items = job['items']
        counted = lambda st: len([it for it in items if it['status'] == st])
        s = _summary(job)
        log_activity_async(
            None, 'pdfkit_done', job.get('role', ''),
            job.get('display') or job.get('user', '?'),
            new_data={'job': job['id'], 'mode': job['mode'],
                      'files': len(items),
                      'done': counted('done'),
                      'skipped': counted('skipped') + counted('protected'),
                      'failed': counted('error'),
                      'saved_bytes': s['saved_bytes'],
                      'ratio_pct': s['ratio_pct'],
                      'size_before': sum(it['size_before'] for it in items),
                      'size_after': sum(it['size_after'] for it in items)},
            branch_code=job.get('_branch') or None)
    except Exception as e:
        print(f'[pdfkit] audit pemakaian gagal: {e}')


def aggregate_usage(rows):
    """Agregasi baris `activity_logs` (action pdfkit_*) → laporan pemakaian.

    Murni fungsi (tanpa DB) supaya bisa diuji tanpa basis data. `rows` = list
    dict dengan kunci user_name, user_type, action, created_at, new_data
    (dict atau JSON string).

    Return {'per_user': [...], 'totals': {...}, 'recent': [...]}.
    """
    users = {}
    recent = []
    for r in rows or []:
        action = (r.get('action') or '')
        if action not in ('pdfkit_submit', 'pdfkit_done'):
            continue
        data = r.get('new_data')
        if isinstance(data, str):
            try:
                import json as _json
                data = _json.loads(data)
            except Exception:
                data = None
        data = data if isinstance(data, dict) else {}
        name = (r.get('user_name') or '—')
        u = users.setdefault(name, {
            'user': name, 'role': r.get('user_type') or '', 'jobs': 0,
            'files': 0, 'done': 0, 'skipped': 0, 'failed': 0,
            'size_before': 0, 'size_after': 0, 'saved_bytes': 0,
            'last_at': '',
        })
        if r.get('user_type'):
            u['role'] = r['user_type']
        at = str(r.get('created_at') or '')
        if at > str(u['last_at']):
            u['last_at'] = at
        if action == 'pdfkit_submit':
            u['jobs'] += 1
        else:
            u['files'] += int(data.get('files') or 0)
            u['done'] += int(data.get('done') or 0)
            u['skipped'] += int(data.get('skipped') or 0)
            u['failed'] += int(data.get('failed') or 0)
            u['size_before'] += int(data.get('size_before') or 0)
            u['size_after'] += int(data.get('size_after') or 0)
            u['saved_bytes'] += int(data.get('saved_bytes') or 0)
            recent.append({
                'job': data.get('job') or '', 'user': name,
                'mode': data.get('mode') or '',
                'files': int(data.get('files') or 0),
                'done': int(data.get('done') or 0),
                'skipped': int(data.get('skipped') or 0),
                'saved_bytes': int(data.get('saved_bytes') or 0),
                'ratio_pct': float(data.get('ratio_pct') or 0),
                'at': at,
            })
    per_user = sorted(users.values(), key=lambda u: u['saved_bytes'], reverse=True)
    for u in per_user:
        u['ratio_pct'] = _pct(u['size_before'], u['size_after'])
    totals = {
        'users': len([u for u in per_user if u['jobs'] or u['files']]),
        'jobs': sum(u['jobs'] for u in per_user),
        'files': sum(u['files'] for u in per_user),
        'done': sum(u['done'] for u in per_user),
        'skipped': sum(u['skipped'] for u in per_user),
        'failed': sum(u['failed'] for u in per_user),
        'size_before': sum(u['size_before'] for u in per_user),
        'size_after': sum(u['size_after'] for u in per_user),
        'saved_bytes': sum(u['saved_bytes'] for u in per_user),
    }
    totals['ratio_pct'] = _pct(totals['size_before'], totals['size_after'])
    recent.sort(key=lambda j: j['at'], reverse=True)
    return {'per_user': per_user, 'totals': totals, 'recent': recent[:20]}


def _process_item(job, idx, workdir):
    """Proses satu berkas: guard → kompres → catat hasil. Item di-update di place."""
    item = job['items'][idx]
    src = os.path.join(workdir, 'in', item['name'])
    try:
        shutil.move(item['_path'], src)
    except Exception as e:
        raise RuntimeError(f'berkas unggahan tidak ditemukan: {e}')

    info = probe(src)
    _update_item(job, idx, pages=info['pages'])

    row = registry_row(item.get('_sha256'))
    reason = guard_reason(item, info, row)
    if reason:
        # 'protected' = ditolak karena kebijakan integritas/keaslian;
        # 'skipped'   = tidak didukung (enkripsi). Dua-duanya tidak dikompres.
        status = 'protected' if (row or info.get('signed')) else 'skipped'
        _update_item(job, idx, status=status, note=reason)
        return

    _check_cancel(job)
    stem = _safe_stem(item['name'])
    target_bytes = int(job.get('target_mb') or 0) * 1024 * 1024
    out = os.path.join(workdir, 'out', f'{stem}_kompres.pdf')
    n = 2
    while os.path.exists(out):
        out = os.path.join(workdir, 'out', f'{stem}_kompres({n}).pdf')
        n += 1

    res = compress_chain(src, out, job['mode'], target_bytes=target_bytes,
                         on_step=lambda m: _update_item(job, idx, mode_used=m))
    _check_cancel(job)
    if not res['ok']:
        _update_item(job, idx, status='error', error=res.get('error') or 'gagal',
                     note='Kompresi gagal')
        return

    after = os.path.getsize(out)
    gain = _pct(item['size_before'], after)
    if gain < MIN_GAIN_PCT:
        # Hasil tidak berguna → jangan beri file yang sama/malah lebih besar.
        try:
            os.remove(out)
        except OSError:
            pass
        _update_item(job, idx, status='skipped', mode_used=res['mode_used'],
                     size_after=item['size_before'],
                     note=f'Tidak ada perbaikan berarti (selisih {gain}% < '
                          f'{MIN_GAIN_PCT:.0f}%). Berkas asli sudah optimal.')
        return

    text_kept = None
    if info['has_text']:
        _, after_text = _run_capture(['pdftotext', '-f', '1', '-l', '3', out, '-'])
        text_kept = bool(after_text and after_text.strip())

    _update_item(job, idx, status='done', size_after=after, ratio_pct=gain,
                 text_kept=text_kept,
                 outputs=[{'file': os.path.basename(out), 'size': after,
                           'mode': res['mode_used']}],
                 note=f'Hemat {gain}% (mode {res["mode_used"]})')


def _check_cancel(job):
    if job['status'] == 'cancelled':
        raise _CancelledError()


# ---------------------------------------------------------------------------
# Unggahan (dipakai routes.py)
# ---------------------------------------------------------------------------

def valid_pdf_name(name):
    return str(name or '').lower().endswith('.pdf')


def staging_dir(base):
    path = os.path.join(base, '_incoming')
    os.makedirs(path, exist_ok=True)
    return path


def discard_staging(paths):
    """Buang berkas staging (dipakai bila submit ditolak setelah unggah)."""
    for p in paths or []:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
