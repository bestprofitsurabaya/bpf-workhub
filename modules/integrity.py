"""Penghitung kegagalan yang sengaja ditelan (v2.119.0).

Sebagian kegagalan memang boleh ditelan: koneksi gagal ditutup, Redis mati
lalu jatuh ke memori, metadata opsional tidak ada. Masalahnya, kegagalan yang
**berdampak pada data atau hak akses** juga ikut hilang tanpa jejak — laporan
tampak "ok", penomoran jatuh ke cadangan, rantai ACC memakai default.

Modul ini mencatatnya di memori proses (tanpa DB, tanpa I/O wajib) supaya
`/api/health` bisa menunjukkannya:

    from modules.integrity import note
    try:
        ...
    except Exception as exc:
        note('laporan.bbm', exc, critical=True)   # angka bisa salah

`critical=True` berarti hasil yang dilihat pengguna mungkin tidak lengkap
atau salah. Kegagalan non-kritis (mis. Redis mati lalu memakai memori) tetap
dicatat, tetapi tidak menurunkan status health.

Aturan: `note()` tidak boleh melempar exception apa pun. Health tidak boleh
ikut mati hanya karena pencatat error bermasalah.
"""
import logging
import threading
import time

_LOG = logging.getLogger('bpf.integrity')
_LOCK = threading.Lock()
_MAX_RECENT = 50
_MAX_TEXT = 200
_DEFAULT_WINDOW = 30 * 60

_recent = []
_total = 0
_critical_total = 0
_by_context = {}


def note(context, exc=None, critical=False):
    """Catat satu kegagalan yang ditelan. Tidak pernah melempar."""
    try:
        ctx = str(context or 'unknown')[:80]
        try:
            text = '' if exc is None else str(exc)
        except Exception:
            text = f'<{type(exc).__name__}>'
        text = ' '.join(text.split())[:_MAX_TEXT]
        global _total, _critical_total
        with _LOCK:
            _total += 1
            if critical:
                _critical_total += 1
            _by_context[ctx] = _by_context.get(ctx, 0) + 1
            _recent.append({
                'at': time.time(), 'context': ctx,
                'error': text, 'critical': bool(critical),
            })
            if len(_recent) > _MAX_RECENT:
                del _recent[:-_MAX_RECENT]
        if critical:
            _LOG.warning('[integrity] %s: %s', ctx, text or '(tanpa pesan)')
        else:
            _LOG.debug('[integrity] %s: %s', ctx, text or '(tanpa pesan)')
    except Exception:  # pragma: no cover - penjaga terakhir
        pass


def snapshot(limit=10, window_seconds=_DEFAULT_WINDOW):
    """Ringkasan aman-JSON untuk `/api/health`."""
    try:
        now = time.time()
        with _LOCK:
            total = _total
            critical_total = _critical_total
            recent = list(_recent)
            top = sorted(_by_context.items(), key=lambda kv: kv[1], reverse=True)[:5]
        recent_critical = sum(
            1 for e in recent
            if e['critical'] and now - e['at'] <= window_seconds)
        return {
            'total': total,
            'critical_total': critical_total,
            'recent_critical': recent_critical,
            'window_seconds': int(window_seconds),
            'by_context': [{'context': c, 'count': n} for c, n in top],
            'recent': [
                {
                    'at': time.strftime('%Y-%m-%d %H:%M:%S',
                                        time.localtime(e['at'])),
                    'context': e['context'],
                    'error': e['error'],
                    'critical': e['critical'],
                }
                for e in recent[-int(limit or 10):]
            ],
        }
    except Exception:  # pragma: no cover - snapshot tidak boleh gagal
        return {
            'total': 0, 'critical_total': 0, 'recent_critical': 0,
            'window_seconds': int(window_seconds or 0),
            'by_context': [], 'recent': [],
        }


def reset():
    """Kosongkan penghitung (dipakai tes)."""
    global _total, _critical_total
    with _LOCK:
        _recent.clear()
        _by_context.clear()
        _total = 0
        _critical_total = 0
