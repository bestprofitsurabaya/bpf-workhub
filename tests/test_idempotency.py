"""Unit tests — idempotensi submit driver (v2.120.0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import idempotency  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self.rowcount = -1
        self._row = None

    def execute(self, sql, params=None):
        q = ' '.join(str(sql).split())
        params = params or ()
        if q.startswith('INSERT IGNORE INTO submit_idempotency'):
            uuid, scope = params
            if uuid in self.conn.rows:
                self.rowcount = 0
            else:
                self.conn.rows[uuid] = {'client_uuid': uuid, 'scope': scope,
                                        'display_id': '', 'doc_id': 0,
                                        'created_at': 'now'}
                self.rowcount = 1
        elif q.startswith('UPDATE submit_idempotency'):
            display_id, doc_id, uuid = params
            row = self.conn.rows.get(uuid)
            if row:
                row['display_id'] = display_id
                row['doc_id'] = doc_id
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif q.startswith('SELECT client_uuid'):
            self._row = self.conn.rows.get(params[0])
        else:
            raise AssertionError('SQL tak terduga: ' + q)

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, fail=False):
        self.rows = {}
        self.fail = fail

    def cursor(self, dictionary=False):
        if self.fail:
            raise RuntimeError('tabel belum siap')
        return FakeCursor(self, dictionary)

    def commit(self):
        pass


def test_tanpa_uuid_dilewati():
    assert idempotency.begin(FakeConn(), '', 'bbm')[0] == 'skip'
    assert idempotency.begin(FakeConn(), 'bukan uuid!', 'bbm')[0] == 'skip'


def test_alur_baru_lalu_replay_mengembalikan_dokumen_sama():
    conn = FakeConn()
    token = 'abcdef12-3456-7890-abcd-ef1234567890'
    state, row = idempotency.begin(conn, token, 'bbm_claim')
    assert state == 'new' and row is None

    cur = conn.cursor()
    assert idempotency.finish(cur, token, 'BPF-SBY-1', 77)

    state, row = idempotency.begin(conn, token, 'bbm_claim')
    assert state == 'replay'
    body, code = idempotency.replay_payload(row)
    assert code == 200 and body['status'] == 'success'
    assert body['duplicate'] is True
    assert body['transaction_id'] == 'BPF-SBY-1'
    assert body['numeric_id'] == 77


def test_replay_saat_masih_diproses_memberi_409():
    conn = FakeConn()
    token = 'abcdef12-3456-7890-abcd-ef1234567890'
    idempotency.begin(conn, token, 'trip')
    state, row = idempotency.begin(conn, token, 'trip')
    assert state == 'replay'
    body, code = idempotency.replay_payload(row, 'trip')
    assert code == 409
    assert body['status'] == 'error'


def test_tabel_belum_siap_tidak_menggagalkan_submit():
    state, row = idempotency.begin(FakeConn(fail=True), 'abcdef12-3456', 'cash')
    assert state == 'skip' and row is None


def test_bentuk_payload_per_jenis():
    row = {'display_id': 'OT-SBY-1', 'doc_id': 9}
    assert idempotency.replay_payload(row, 'overtime')[0]['display_id'] == 'OT-SBY-1'
    assert idempotency.replay_payload(row, 'cash')[0]['cash_id'] == 9
    assert idempotency.replay_payload(row, 'trip')[0]['trip_id'] == 'OT-SBY-1'
