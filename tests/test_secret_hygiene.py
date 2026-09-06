"""
Tests v2.30 — Secret hygiene (ISO/IEC 27001 A.8.2/A.8.13, A.8.23).

1. Tidak ada kredensial DB produksi yang di-hardcode di file yang di-commit
   (docker-compose.yml, kode, scripts, dokumentasi). Kredensial HANYA dari .env
   (gitignored) — pola password lama (bpf_pass / password_db) dilarang muncul.

2. modules/config.py fail-fast: di FLASK_ENV=production tanpa DB_PASSWORD →
   RuntimeError (tidak diam-diam memakai kredensial default yang dikenal
   publik). Di luar production (dev/test) → nilai dev-only yang jelas gagal
   connect (bukan password produksi).

Tidak butuh MariaDB — murni statis (scan file) + unit config.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

REPO_ROOT = Path(__file__).resolve().parent.parent

# File yang WAJIB bebas dari password produksi hardcoded. .env & .env.* sengaja
# TIDAK diskimming untuk memastikan tidak menormalisasi pola lama di template.
SCAN_FILES = [
    'docker-compose.yml',
    'app.py',
    '.env.example',
    '.github/workflows/ci.yml',
]
SCAN_DIRS = ['modules', 'scripts']
# Dokumentasi yang memuat contoh perintah DB
SCAN_DOCS = ['docs/internal/DEPLOYMENT.md', 'docs/internal/DEPLOY_FRESH.md',
             'docs/public/PELATIHAN.md', 'README.md',
             'guides/USER_GUIDE.md']

# Password produksi lama (sudah dipindah ke .env & akan dirotasi) — dilarang
# muncul di repo. Dipecah agar pola ini sendiri tidak terdeteksi oleh pencari.
_OLD_PASSWORDS = ['password' + '_db', 'bpf_' + 'pass', 'bpf_root' + '_pass']


def _iter_scan_files():
    for f in SCAN_FILES:
        p = REPO_ROOT / f
        if p.exists():
            yield p
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if base.exists():
            for p in sorted(base.rglob('*')):
                # Lewati bytecode/sampah build (bukan source, isi bisa stale)
                if (p.is_file() and not p.name.startswith('.')
                        and '__pycache__' not in p.parts
                        and p.suffix != '.pyc'):
                    yield p
    for f in SCAN_DOCS:
        p = REPO_ROOT / f
        if p.exists():
            yield p


class TestNoHardcodedDBCredentials:
    def test_password_produksi_tidak_ada_di_repo(self):
        """Pola password lama tidak boleh muncul di file yang di-commit."""
        offenders = []
        for p in _iter_scan_files():
            try:
                text = p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for pw in _OLD_PASSWORDS:
                    if pw in line:
                        offenders.append(f'{p}:{i}: {line.strip()[:120]}')
        assert not offenders, (
            'Kredensial DB masih di-hardcode — pindahkan ke .env:\n' +
            '\n'.join(offenders))

    def test_compose_membaca_kredensial_dari_env(self):
        """docker-compose.yml wajib memakai ${VAR:?...} untuk password."""
        compose = (REPO_ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        for var in ('MYSQL_ROOT_PASSWORD', 'MYSQL_PASSWORD'):
            expected = '${' + var + ':?'
            assert expected in compose, \
                (var + ' harus dibaca dari .env dengan fail-fast ' +
                 '(${' + var + ':?...})')

    def test_env_example_tanpa_nilai_nyata(self):
        """.env.example hanya berisi placeholder kosong — bukan kredensial."""
        example = (REPO_ROOT / '.env.example').read_text(encoding='utf-8')
        for var in ('MYSQL_ROOT_PASSWORD=', 'MYSQL_PASSWORD=', 'SECRET_KEY='):
            # Pastikan ada baris `VAR=` kosong (nilai diisi user saat deploy)
            assert re.search(rf'^{re.escape(var)}\s*(#.*)?$', example, re.M), \
                f'.env.example harus punya baris kosong {var} untuk diisi user'


class TestConfigFailFast:
    def _clear_db_password(self, monkeypatch):
        monkeypatch.delenv('DB_PASSWORD', raising=False)
        monkeypatch.delenv('FLASK_ENV', raising=False)

    def test_production_tanpa_db_password_raise(self, monkeypatch):
        """FLASK_ENV=production & DB_PASSWORD kosong → RuntimeError (fail-fast)."""
        import modules.config as mc
        self._clear_db_password(monkeypatch)
        monkeypatch.setenv('FLASK_ENV', 'production')
        try:
            mc._resolve_db_password()
            assert False, 'harus RuntimeError'
        except RuntimeError as e:
            assert 'DB_PASSWORD' in str(e)

    def test_default_environment_tanpa_password_dev_fallback(self, monkeypatch):
        """FLASK_ENV kosong (dev/test) → fallback dev-only, bukan password lama."""
        import modules.config as mc
        self._clear_db_password(monkeypatch)
        val = mc._resolve_db_password()
        assert 'dev-only' in val
        # Fallback dev TIDAK boleh sama dengan password produksi lama
        for pw in _OLD_PASSWORDS:
            assert pw not in val

    def test_password_dari_env_dipakai(self, monkeypatch):
        import modules.config as mc
        self._clear_db_password(monkeypatch)
        monkeypatch.setenv('DB_PASSWORD', 'rahasia-kuat-123')
        assert mc._resolve_db_password() == 'rahasia-kuat-123'

    def test_db_config_memakai_env_atau_dev_fallback(self, monkeypatch):
        """DB_CONFIG['password'] tidak pernah memuat password produksi lama."""
        import modules.config as mc
        self._clear_db_password(monkeypatch)
        cfg = dict(mc.DB_CONFIG)
        for pw in _OLD_PASSWORDS:
            assert cfg['password'] != pw


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])
