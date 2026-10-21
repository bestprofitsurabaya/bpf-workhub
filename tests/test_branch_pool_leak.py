"""Regresi v2.47.1 — ensure_branch_database() tidak boleh membocorkan koneksi.

Dulu koneksi master yang dibuka sendiri (bukan `conn` dari pemanggil) tidak
pernah di-close: satu koneksi pool master hilang per cabang pada SETIAP
startup (8 cabang → 8 dari 25 koneksi). Efeknya "⚠ Pool exhausted" lalu
fallback membuka koneksi non-pool tanpa batas.
"""
import modules.branch_manager as bm


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeMaster:
    def __init__(self):
        self.closes = 0
        self.dictionary = False

    def cursor(self, dictionary=False):
        return FakeCursor([{'Tables_in_bpf_asset_system': 'users'}])

    def close(self):
        self.closes += 1


class FakeBranchConn:
    def __init__(self):
        self.closes = 0

    def cursor(self, dictionary=False):
        return FakeCursor([])

    def commit(self):
        pass

    def close(self):
        self.closes += 1


class FakePool:
    def __init__(self):
        self.conns = []

    def get_connection(self):
        c = FakeBranchConn()
        self.conns.append(c)
        return c


def _patch_helpers(monkeypatch):
    import modules.notifications as notif
    import modules.appointments_schema as appt
    import modules.helpers as helpers
    import modules.approvals as approvals
    import modules.overtime_schema as ot
    import modules.routes_water as water
    import modules.admin_scope as scope

    for mod, name in (
        (notif, 'ensure_notifications_table'),
        (appt, 'ensure_appointments_schema'),
        (helpers, 'ensure_doc_sequences'),
        (approvals, 'ensure_manager_column'),
        (approvals, 'ensure_approval_tables'),
        (ot, 'ensure_overtime_schema'),
        (water, 'ensure_water_edit_columns'),
        (scope, 'ensure_branch_admin_columns'),
    ):
        monkeypatch.setattr(mod, name, lambda *a, **k: True)
    monkeypatch.setattr(bm, 'write_branch_identity', lambda *a, **k: True)


def test_master_connection_closed_after_schema_sync(monkeypatch):
    master = FakeMaster()
    pool = FakePool()
    monkeypatch.setattr(bm, 'get_branch',
                        lambda code, conn=None: {'code': code,
                                                 'db_name': 'bpf_branch_uji'})
    monkeypatch.setattr(bm, 'get_master_connection', lambda: master)
    monkeypatch.setattr('modules.config._pool_for', lambda db: pool)
    _patch_helpers(monkeypatch)

    ok, msg = bm.ensure_branch_database('UJI')

    assert ok, msg
    assert master.closes == 1, 'koneksi master bocor (tidak di-close)'
    assert pool.conns and all(c.closes == 1 for c in pool.conns), \
        'koneksi DB cabang bocor'


def test_caller_owned_connection_not_closed(monkeypatch):
    """Bila pemanggil menyerahkan `conn`, fungsi TIDAK boleh menutupnya."""
    master = FakeMaster()
    pool = FakePool()
    monkeypatch.setattr(bm, 'get_branch',
                        lambda code, conn=None: {'code': code,
                                                 'db_name': 'bpf_branch_uji2'})
    monkeypatch.setattr('modules.config._pool_for', lambda db: pool)
    _patch_helpers(monkeypatch)

    ok, msg = bm.ensure_branch_database('UJI2', conn=master)

    assert ok, msg
    assert master.closes == 0, 'koneksi milik pemanggil tidak boleh ditutup'
