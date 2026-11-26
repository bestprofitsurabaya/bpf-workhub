"""Regresi penulis event kasus rekrutmen (Rilis C — Task C2).

Event ditulis best-effort: aksi sumber tetap sukses walaupun master gagal. Kunci
idempoten `(source_module, branch_code, source_id, event_type)` dan NIK tidak
pernah masuk ke stdout. Rebuild dari tabel sumber harus bisa diulang dengan
0 insert pada putaran kedua.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NIK = '3573010101900001'


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        text = ' '.join(sql.split()).upper()
        if text.startswith('INSERT IGNORE INTO RECRUITMENT_EVENTS'):
            self.rowcount = self.conn._insert(dict(params or {}))
            return
        if text.startswith('SELECT'):
            match = re.search(r'\bFROM\s+([A-Z_]+)', text)
            table = match.group(1).lower() if match else ''
            rows = self.conn.rows.get(table, [])
            limit = None
            m = re.search(r'\bLIMIT\s+(\d+)', text)
            if m:
                limit = int(m.group(1))
            self._rows = [dict(row) for row in rows]
            if limit is not None:
                self._rows = self._rows[:limit]
        elif text.startswith('UPDATE'):
            self.rowcount = 1

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.events = []
        self.keys = set()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, dictionary=False):
        return _FakeCursor(self)

    def _insert(self, row):
        key = (row.get('source_module'), row.get('branch_code'),
               row.get('source_id'), row.get('event_type'))
        if key in self.keys:
            return 0
        self.keys.add(key)
        self.events.append(row)
        return 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _BrokenConn:
    def cursor(self, dictionary=False):
        raise RuntimeError('master down')

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def conn():
    return _FakeConn()


def test_event_idempoten_dan_nik_tidak_masuk_log(conn, capsys):
    from modules.recruitment_events import record_event
    kwargs = dict(case_id='RC-1', nik=NIK, event_type='VERIFIED',
                  branch_code='SBY', source_module='applicants',
                  source_id='PLM-SBY-1', conn=conn)
    assert record_event(**kwargs) is True
    assert record_event(**kwargs) is True
    assert len(conn.events) == 1
    assert NIK not in capsys.readouterr().out


def test_event_gagal_tidak_melempar(capsys):
    from modules.recruitment_events import record_event
    assert record_event('RC-1', NIK, 'VERIFIED', conn=_BrokenConn()) is False
    assert NIK not in capsys.readouterr().out


def test_metadata_json_dan_pemotongan_panjang(conn):
    from modules.recruitment_events import record_event
    assert record_event('RC-1', NIK, 'CARD_ISSUED', conn=conn,
                        source_module='first_work', source_id='FW' * 64,
                        note='x' * 700,
                        metadata={'branch_code': 'SBY', 'score': 90}) is True
    row = conn.events[0]
    assert len(row['source_id']) == 64
    assert len(row['note']) == 500
    assert '"score": 90' in row['metadata_json']


def test_event_type_tidak_dikenal_ditolak(conn):
    from modules.recruitment_events import record_event
    assert record_event('RC-1', NIK, 'ASAL', conn=conn) is False
    assert conn.events == []


def test_fetch_timeline_mengurai_metadata_rusak(conn):
    from modules.recruitment_events import fetch_timeline
    conn.rows['recruitment_events'] = [
        {'id': 1, 'event_type': 'VERIFIED', 'event_at': '2026-11-26 10:00:00',
         'branch_code': 'SBY', 'actor_role': 'receptionist',
         'actor_name': 'Rina', 'source_module': 'applicants',
         'note': '', 'metadata_json': '{"a": 1}'},
        {'id': 2, 'event_type': 'PASSED', 'event_at': '2026-11-26 11:00:00',
         'branch_code': 'SBY', 'actor_role': '', 'actor_name': '',
         'source_module': 'applicants', 'note': '', 'metadata_json': 'rust'},
    ]
    cur = conn.cursor(dictionary=True)
    rows = fetch_timeline(cur, 'RC-1', limit=5)
    assert [r['event_type'] for r in rows] == ['VERIFIED', 'PASSED']
    assert rows[0]['metadata'] == {'a': 1}
    assert rows[1]['metadata'] == {}
    assert 'nik' not in rows[0]


def test_rebuild_membangun_event_dari_sumber():
    from modules.recruitment_events import rebuild_events
    rows = {
        'recruitment_cases': [
            {'case_id': 'RC-1', 'nik': NIK, 'first_seen_at': '2026-11-01 09:00:00'},
        ],
        'recruitment_steps': [
            {'id': 11, 'case_id': 'RC-1', 'step_type': 'CV',
             'status': 'SELESAI', 'completed_at': '2026-11-02 09:00:00',
             'branch_code': 'SBY'},
            {'id': 12, 'case_id': 'RC-1', 'step_type': 'FIRSTWORK',
             'status': 'SELESAI', 'completed_at': '2026-11-03 09:00:00',
             'branch_code': 'SBY'},
        ],
        'cv_online_submissions': [
            {'id': 21, 'nik': NIK, 'submitted_at': '2026-11-02 09:00:00'},
        ],
        'first_work_submissions': [
            {'id': 31, 'nik': NIK, 'registration_no': 'FW-SBY-1',
             'submitted_at': '2026-11-03 09:00:00'},
        ],
    }
    applicants = [{'display_id': 'PLM-SBY-1', 'nik': NIK, 'nama_lengkap': 'Budi',
                   'status': 'lulus', 'verified_at': '2026-11-01 10:00:00',
                   'interview_at': '2026-11-01 11:00:00',
                   'created_at': '2026-11-01 08:00:00'}]
    db = _FakeConn(rows)
    first = rebuild_events(conn=db, branch_rows=applicants)
    assert first['inserted'] >= 3
    again = rebuild_events(conn=db, branch_rows=applicants)
    assert again['inserted'] == 0


def test_rebuild_dry_run_tidak_commit():
    from modules.recruitment_events import rebuild_events
    conn = _FakeConn({'recruitment_cases': [], 'recruitment_steps': []})
    result = rebuild_events(conn=conn, branch_rows=[], commit=False)
    assert result['inserted'] == 0
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_skrip_rebuild_default_dry_run(monkeypatch, capsys):
    path = ROOT / 'scripts' / 'rebuild_recruitment_events.py'
    spec = importlib.util.spec_from_file_location('rebuild_events_script', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = {}
    fake = _FakeConn()

    def fake_rebuild(conn=None, branch_rows=None, commit=True):
        seen['commit'] = commit
        return {'inserted': 2, 'skipped': 1}

    monkeypatch.setattr(module, 'get_master_connection', lambda: fake)
    monkeypatch.setattr(module, 'get_db_connection', lambda **kw: fake)
    monkeypatch.setattr(module, 'rebuild_events', fake_rebuild)
    assert module.main([]) == 0
    assert seen['commit'] is False
    out = capsys.readouterr().out
    assert 'inserted=2' in out
    assert NIK not in out
