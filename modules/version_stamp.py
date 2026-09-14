"""Checker 7 titik stamp versi (v2.40.3).

Insiden v2.40.2 (14 Sep 2026): setelah rebuild, stamp `system_config`
cabang revert ke v2.40.0 — startup app (`app.py` → `ensure_branch_database()`
→ `write_branch_identity()`) menanam ulang identitas cabang dari tabel
`branches.system_version`, dan bump versi lupa meng-update kolom itu.

Dua lapis perbaikan:
1. Struktural: `write_branch_identity()` kini SELALU menulis system_version
   dari versi kode (IDENTITY_DEFAULTS) — tabel branches tak bisa lagi
   "menahan" versi lama.
2. Guard ini: 7 titik stamp di file WAJIB konsisten, diperiksa oleh pytest
   dan step CI. Titik ke-8 (DB: master + branches.system_version) bisa
   diprobe opsional via CLI `--with-db` (server/container dengan DB).

Titik stamp:
  1. modules/company_identity.py        → IDENTITY_DEFAULTS['system_version']  (REFERENSI)
  2. modules/pdf_generator.py           → SYSTEM_VERSION = 'BPF WorkHub v…'
  3. frontend/src/stores/identity.js    → system_version: 'v…'
  4. frontend/public/sw.js              → CACHE = 'bpf-spa-YYYYMMDD-vX.Y.Z'
  5. CHANGELOG.md                       → heading ## vX.Y.Z teratas
  6. docs/internal/USER_LIST.md         → vX.Y.Z di header
  7. guides/USER_GUIDE.md               → vX.Y.Z di header

Sengaja murni parsing file (tanpa import modul aplikasi) supaya bisa jalan
di CI, di host tanpa dependensi, dan diuji dengan file palsu (tmp_path).
"""
import os
import re

VERSION_RE = re.compile(r'^v\d+\.\d+\.\d+$')


def _regex_first(pattern, text):
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _parse_sw_cache_version(text):
    """'bpf-spa-20260914-v2.40.3' → 'v2.40.3'; None bila format salah/hilang."""
    m = re.search(r"const CACHE\s*=\s*'bpf-spa-(\d{8})-(v[\d.]+)'", text)
    if not m:
        return None
    ver = m.group(2)
    return ver if VERSION_RE.match(ver) else None


def _parse_changelog_latest(text):
    m = re.search(r'^##\s+(v\d+\.\d+\.\d+)', text, re.MULTILINE)
    return m.group(1) if m else None


def _parse_doc_version(text):
    return _regex_first(r'(v\d+\.\d+\.\d+)', text)


# (nama, path relatif ke root repo, parser)
STAMP_POINTS = (
    ('kode backend (company_identity)', os.path.join('modules', 'company_identity.py'),
     lambda t: _regex_first(r"'system_version':\s*'([^']+)'", t)),
    ('PDF generator (kop & footer)', os.path.join('modules', 'pdf_generator.py'),
     lambda t: _regex_first(r"SYSTEM_VERSION\s*=\s*'BPF WorkHub (v[\d.]+)'", t)),
    ('SPA store (identity.js)', os.path.join('frontend', 'src', 'stores', 'identity.js'),
     lambda t: _regex_first(r"system_version:\s*'([^']+)'", t)),
    ('Service Worker (sw.js CACHE)', os.path.join('frontend', 'public', 'sw.js'),
     _parse_sw_cache_version),
    ('CHANGELOG.md (entri teratas)', 'CHANGELOG.md',
     _parse_changelog_latest),
    ('USER_LIST.md (header)', os.path.join('docs', 'internal', 'USER_LIST.md'),
     _parse_doc_version),
    ('USER_GUIDE.md (header)', os.path.join('guides', 'USER_GUIDE.md'),
     _parse_doc_version),
)


def check_all(root=None):
    """Bandingkan ke-7 titik dengan versi referensi (kode backend).

    Returns dict: {'version': referensi, 'points': [{name,file,value,ok}], 'all_ok': bool}
    File hilang / format rusak → value=None, ok=False (checker gagal-tertutup).
    """
    root = root or os.path.join(os.path.dirname(__file__), '..')
    points = []
    expected = None
    for name, relpath, parser in STAMP_POINTS:
        path = os.path.join(root, relpath)
        try:
            with open(path, encoding='utf-8') as f:
                value = parser(f.read())
        except OSError:
            value = None
        if expected is None:
            # Titik pertama = referensi; tetap wajib format valid.
            expected = value if (value and VERSION_RE.match(value)) else None
        points.append({
            'name': name,
            'file': relpath,
            'value': value,
            'ok': bool(value and expected and value == expected),
        })
    return {'version': expected, 'points': points, 'all_ok': expected is not None and all(p['ok'] for p in points)}


def check_db_stamps():
    """Probe stamp DB (titik opsional ke-8): master + branches.system_version.

    Hanya jalan di tempat dengan DB (container/server). Tidak pernah raise —
    error jadi titik ok=False dengan pesan error.
    """
    result = []
    try:
        from modules.config import get_master_connection
        conn = get_master_connection()
        if not conn:
            return [{'name': 'DB master (system_config)', 'value': None, 'ok': False, 'error': 'koneksi DB gagal'}]
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT config_value FROM system_config WHERE config_key='system_version'")
            row = cur.fetchone()
            result.append({'name': 'DB master (system_config)', 'value': row and row['config_value'], 'ok': bool(row)})
            cur.execute("SELECT DISTINCT system_version FROM branches")
            vals = sorted({r['system_version'] for r in cur.fetchall() if r['system_version']})
            result.append({
                'name': 'DB branches.system_version',
                'value': vals[0] if len(vals) == 1 else (vals or None),
                'ok': len(vals) == 1,
                'error': None if len(vals) <= 1 else 'tidak seragam: ' + ', '.join(vals),
            })
        finally:
            cur.close()
            conn.close()
    except Exception as e:  # pragma: no cover — jalur probe DB di server
        result.append({'name': 'DB stamp probe', 'value': None, 'ok': False, 'error': str(e)})
    return result
