"""Guard regresi v2.39.2 — monkey-patching gevent hanya boleh dari worker.

Insiden (CI run 34425989650, 10 Sep 2026): v2.38.0 menambah
`from gevent import monkey; monkey.patch_all()` di app.py. Patching di
dalam modul aplikasi jalan saat `import app` — termasuk saat pytest
meng-import app di tengah sesi test — dan merusak lock importlib yang
sudah di-acquire interpreter:
    ERROR at setup of test_security_headers_present
    RuntimeError: cannot release un-acquired lock  (_ModuleLock 'app')
CI jadi merah walau 587 test lulus; host lokal hijau hanya karena gevent
tidak ter-install di sana (fallback threading menyembunyikan bug).

Aturan arsitektur yang di-guard test ini:
1. app.py TIDAK boleh memanggil monkey_patch()/patch_all() — pemetaan
   patch ditentukan worker gunicorn via --worker-class (Dockerfile);
   gunicorn melakukan patch SEBELUM app di-load.
2. Worker produksi tetap gevent (v2.38.0) — CMD Dockerfile + gevent di
   requirements.txt tidak boleh hilang saat merapikan app.py.

Jalankan: python3 -m pytest tests/test_worker_patch_guard.py -v
"""
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')
APP_PY = os.path.join(ROOT, 'app.py')
DOCKERFILE = os.path.join(ROOT, 'Dockerfile')
REQUIREMENTS = os.path.join(ROOT, 'requirements.txt')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _code_lines(text):
    """Baris efektif (strip komentar & kosong) supaya komentar tidak ikut match."""
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if line:
            yield line


def test_app_module_tidak_memanggil_monkeypatch():
    """app.py tidak boleh patch gevent/eventlet saat di-import.

    import app oleh pytest terjadi SETELAH puluhan modul & fixture lain
    ter-load — patch di tengah jalan merusak lock importlib
    ("cannot release un-acquired lock"). Patch hanya boleh dilakukan
    pihak yang meng-import app PERTAMA kali sebelum apa pun: worker
    gunicorn (via --worker-class).
    """
    source = _read(APP_PY)
    banned = re.compile(
        r'monkey_patch\s*\(|monkey\.patch_all\s*\(|patch_all\s*\(|'
        r'eventlet\.monkey_patch|gevent\.monkey',
    )
    offenders = [line for line in _code_lines(source) if banned.search(line)]
    assert not offenders, (
        'app.py memanggil monkey-patching — pindahkan ke worker gunicorn '
        '(--worker-class gevent) atau tooling entry-point. Baris: '
        + '; '.join(offenders)
    )


def test_async_mode_tetap_terdefinisi():
    """socketio_async_mode harus tetap ada — dipakai SocketIO(app, async_mode=…).

    Setelah patching dibuang dari app.py, mode mengikuti environment:
    'gevent' saat di-load oleh gunicorn, 'threading' selain itu
    (pytest / python app.py).
    """
    source = _read(APP_PY)
    assert re.search(
        r"^socketio_async_mode\s*=", source, re.M
    ), "socketio_async_mode hilang dari app.py"
    assert "async_mode=socketio_async_mode" in source


def test_worker_gevent_tidak_ikut_dibuang():
    """Rapikan app.py tidak boleh menghapus worker gevent (v2.38.0).

    - CMD Dockerfile tetap `--worker-class gevent` (satu-satunya titik
      pemanggilan patch yang benar).
    - requirements.txt tetap menyediakan gevent (extra gunicorn[gevent]
      + paket gevent) — tanpa ini worker gunicorn gagal boot (insiden
      gunicorn 26, 8 Sep 2026).
    """
    dockerfile = _read(DOCKERFILE)
    assert re.search(
        r'--worker-class[=\s]+gevent\b', dockerfile
    ), "Dockerfile tidak lagi menjalankan worker gevent"

    requirements = _read(REQUIREMENTS)
    assert re.search(r'^gunicorn\[gevent\]', requirements, re.M), \
        "extra gunicorn[gevent] hilang dari requirements.txt"
    assert re.search(r'^gevent[>=~<!=\s]', requirements, re.M), \
        "paket gevent hilang dari requirements.txt"


def test_import_app_dengan_gevent_tanpa_merusak_importlib():
    """Smoke asli (v2.39.2): import app dgn gevent ter-install HARUS bersih.

    Statik (test atas) bisa basi; smoke ini mengulang PERSIS kondisi CI
    yang merah: gevent ter-install + `import app` di proses yang sudah
    me-load modul lain (subprocess dgn -X importtime memaksa import
    intern loader dulu). Gagal bila:
    - import app error apa pun (mis. RuntimeError lock importlib), atau
    - app.py kembali mem-patch (async_mode jadi 'gevent' di luar gunicorn).

    Skip di host tanpa gevent (persepsi sama dgn CIBackend job — di sana
    gevent ter-install dari requirements.txt, jadi test ini JALAN).
    """
    pytest.importorskip('gevent')
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
    proc = subprocess.run(
        [sys.executable, '-X', 'importtime', '-c',
         'import app; print("ASYNC_MODE=" + app.socketio_async_mode)'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    combined = (proc.stdout or '') + '\n' + (proc.stderr or '')
    assert proc.returncode == 0, (
        'import app gagal dgn gevent ter-install — inilah mode kegagalan '
        'insiden CI 34425989650. Stderr terakhir:\n' + combined[-2000:])
    assert 'cannot release un-acquired lock' not in combined, \
        'lock importlib rusak saat import app (regresi monkey-patch)'
    assert 'ASYNC_MODE=threading' in combined, (
        'di luar gunicorn async_mode harus threading — app.py kemungkinan '
        'kembali mem-patch sendiri. Output:\n' + combined[-1500:])
