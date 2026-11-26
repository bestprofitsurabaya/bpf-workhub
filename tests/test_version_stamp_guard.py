"""Guard 7 titik stamp versi (v2.40.3) — bump versi tidak boleh ada titik yang tertinggal.

Insiden v2.40.2 (14 Sep 2026): setelah rebuild produksi, stamp `system_config`
cabang revert ke v2.40.0 — startup app menanam ulang identitas cabang dari
tabel `branches.system_version` yang masih versi lama. Fix struktural:
`write_branch_identity()` kini menulis system_version dari versi kode, dan
checker ini menjaga konsistensi semua titik stamp FILE di repo (titik DB
adalah langkah deploy, diprobe via scripts/check_version_stamps.py --with-db).

Jalankan: python3 -m pytest tests/test_version_stamp_guard.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.version_stamp import check_all  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


def test_semua_titik_stamp_konsisten_dengan_kode_backend():
    """Bump versi harus menyentuh SEMUA 7 titik — satu lupa = test merah."""
    report = check_all(ROOT)
    assert report['version'], "Titik referensi (company_identity.py) tidak memuat versi valid"
    beda = [p for p in report['points'] if not p['ok']]
    assert not beda, "Titik stamp tidak konsisten dgn {}: {}".format(
        report['version'],
        '; '.join("{} = {} (harus {})".format(p['file'], p['value'], report['version']) for p in beda))


def test_checker_mendeteksi_titik_yang_tertinggal(tmp_path):
    """Skenario insiden: satu file masih versi lama → checker HARUS gagal."""
    import shutil
    # Salin repo minimal: semua titik stamp dgn isi asli
    for _, relpath, _ in _stamp_points():
        src = os.path.join(ROOT, relpath)
        dst = tmp_path / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    # Turunkan satu titik ke versi lama (simulasi lupa bump). Versi diambil
    # dinamis dari repo asli agar test tetap valid setiap kali bump versi
    # (sebelumnya hardcode v2.40.3 — rusak tiap bump).
    cur = check_all()['version']
    sw = tmp_path / 'frontend' / 'public' / 'sw.js'
    sw.write_text(sw.read_text(encoding='utf-8').replace(cur, 'v0.0.1'), encoding='utf-8')

    report = check_all(str(tmp_path))
    assert not report['all_ok'], "Checker harus gagal saat ada titik versi lama"
    salah = [p for p in report['points'] if p['file'].endswith('sw.js')]
    assert salah and not salah[0]['ok']


def test_checker_mendeteksi_file_stamp_hilang(tmp_path):
    """File stamp terhapus/format rusak → checker gagal-tertutup (bukan lolos)."""
    import shutil
    for _, relpath, _ in _stamp_points():
        src = os.path.join(ROOT, relpath)
        dst = tmp_path / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    (tmp_path / 'modules' / 'pdf_generator.py').unlink()

    report = check_all(str(tmp_path))
    assert not report['all_ok']
    pdf = [p for p in report['points'] if p['file'].endswith('pdf_generator.py')]
    assert pdf and pdf[0]['value'] is None and not pdf[0]['ok']


def test_write_branch_identity_tak_bisa_menahan_versi_lama():
    """Fix struktural anti-revert: mapping system_version WAJIB dari versi kode.

    Regresi insiden v2.40.2 = write_branch_identity menimpa stamp cabang dari
    tabel branches. Sekarang sumbernya IDENTITY_DEFAULTS (versi kode) — guard
    sumber, bukan perilaku-DB, supaya test ini jalan tanpa MariaDB.
    """
    import inspect
    from modules import branch_manager
    src = inspect.getsource(branch_manager.write_branch_identity)
    assert "IDENTITY_DEFAULTS['system_version']" in src, \
        "write_branch_identity harus menulis system_version dari versi kode (IDENTITY_DEFAULTS)"


def _stamp_points():
    from modules.version_stamp import STAMP_POINTS
    return STAMP_POINTS

class _DbCursor:
    def __init__(self, master, branches):
        self.master = master
        self.branches = branches

    def execute(self, sql):
        self._branches_query = 'branches' in sql

    def fetchone(self):
        return {'config_value': self.master}

    def fetchall(self):
        return [{'system_version': v} for v in self.branches]

    def close(self):
        pass


class _DbConn:
    def __init__(self, master, branches):
        self.master = master
        self.branches = branches

    def cursor(self, dictionary=False):
        return _DbCursor(self.master, self.branches)

    def close(self):
        pass


def _patch_db(monkeypatch, master, branches):
    import modules.config as config
    monkeypatch.setattr(
        config, 'get_master_connection',
        lambda: _DbConn(master, branches))


def test_check_db_stamps_lolos_saat_sama_dengan_versi_kode(monkeypatch):
    from modules.company_identity import IDENTITY_DEFAULTS
    from modules.version_stamp import check_db_stamps
    ver = IDENTITY_DEFAULTS['system_version']
    _patch_db(monkeypatch, ver, [ver])
    db = check_db_stamps()
    assert all(d['ok'] for d in db), db


def test_check_db_stamps_menolak_db_tertinggal(monkeypatch):
    """Regresi v2.131.4: DB v2.131.3 vs kode v2.131.4 harus GAGAL."""
    from modules.version_stamp import check_db_stamps
    _patch_db(monkeypatch, 'v0.0.1', ['v0.0.1'])
    db = check_db_stamps()
    assert not all(d['ok'] for d in db), db
    assert any(d.get('error') for d in db)


def test_check_db_stamps_menolak_cabang_tidak_seragam(monkeypatch):
    from modules.company_identity import IDENTITY_DEFAULTS
    from modules.version_stamp import check_db_stamps
    ver = IDENTITY_DEFAULTS['system_version']
    _patch_db(monkeypatch, ver, [ver, 'v0.0.1'])
    db = check_db_stamps()
    assert not all(d['ok'] for d in db), db



def test_sync_version_stamps_menulis_master_dan_cabang(monkeypatch):
    """Titik DB master & branches ikut diperbarui saat startup (v2.135.11)."""
    from modules import branch_manager as bm
    from modules.company_identity import IDENTITY_DEFAULTS
    ver = IDENTITY_DEFAULTS['system_version']
    calls = []

    class _Conn:
        committed = False

        def cursor(self):
            return self

        def execute(self, sql, params=None):
            calls.append((sql, params))

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            pass

    conn = _Conn()
    assert bm.sync_version_stamps(conn=conn) is True
    assert conn.committed is True
    assert any('INSERT INTO system_config' in sql and params == (ver,)
               for sql, params in calls)
    assert any('UPDATE branches' in sql and params == (ver,)
               for sql, params in calls)


def test_sync_version_stamps_aman_tanpa_koneksi(monkeypatch):
    from modules import branch_manager as bm
    monkeypatch.setattr(bm, 'get_master_connection', lambda: None)
    assert bm.sync_version_stamps() is False
