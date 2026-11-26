"""Penautan NIK pelamar lama (Rilis C — C12)."""
import pytest

from modules import recruitment_service as rs
from scripts.link_applicants_nik import link_applicants_nik

NIK = '3573010101900001'


class _MasterCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def execute(self, sql, params=None):
        upper = ' '.join(str(sql).upper().split())
        if 'FROM CV_ONLINE_SUBMISSIONS' in upper:
            nama, hp = (params or ('', ''))[:2]
            self.rows = [r for r in self.conn.cv_rows
                         if r.get('nama') == nama and r.get('no_hp') == hp]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Master:
    def __init__(self, cv_rows=None):
        self.cv_rows = cv_rows or []
        self.cases = []
        self.events = []
        self.commits = 0

    def cursor(self, dictionary=False):
        return _MasterCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def master(monkeypatch):
    conn = _Master([
        {'id': 1, 'nama': 'Budi', 'no_hp': '0812', 'nik': NIK},
        {'id': 2, 'nama': 'Rina', 'no_hp': '0813', 'nik': '3573010101900002'},
        {'id': 3, 'nama': 'Rina', 'no_hp': '0813', 'nik': '3573010101900002'},
    ])
    monkeypatch.setattr(rs, 'ensure_case',
                        lambda nik, *a, **k: 'RC-1')
    monkeypatch.setattr('scripts.link_applicants_nik.ensure_case',
                        lambda nik, *a, **k: 'RC-1')
    monkeypatch.setattr('scripts.link_applicants_nik.record_event',
                        lambda *a, **k: (conn.events.append(a), True)[1])
    return conn


def _rows():
    return [
        {'display_id': 'PLM-1', 'nama_lengkap': 'Budi', 'no_hp': '0812',
         'nik': None, 'link_status': 'unlinked'},
        {'display_id': 'PLM-2', 'nama_lengkap': 'Rina', 'no_hp': '0813',
         'nik': None, 'link_status': 'unlinked'},
        {'display_id': 'PLM-3', 'nama_lengkap': 'Asing', 'no_hp': '0814',
         'nik': None, 'link_status': 'unlinked'},
    ]


def test_menautkan_hanya_bila_nama_dan_hp_cocok_tunggal(master):
    rows = _rows()
    result = link_applicants_nik(master, rows, commit=False)
    assert result == {'linked': 1, 'ambiguous': 1, 'unlinked': 1}
    assert rows[0]['nik'] == NIK
    assert rows[1]['link_status'] == 'ambiguous'
    assert master.events == []  # dry-run tidak menulis event


def test_putaran_kedua_tidak_menulis_ulang(master):
    rows = _rows()
    first = link_applicants_nik(master, rows, commit=True)
    assert first['linked'] == 1
    second = link_applicants_nik(master, rows, commit=True)
    assert second['linked'] == 0
