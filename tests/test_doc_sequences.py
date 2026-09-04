"""
Unit Tests — Standar Penomoran Dokumen (v2.29.10): PREFIX-BRANCH-YYYYMMDD-SEQ.

Menjalankan mengetes generate_display_id() tanpa MariaDB: jalur in-memory
(deterministik) + jalur DB (doc_sequences atomik via fake conn) + cabang dari
sesi.

Jalankan:
    python3 -m pytest tests/test_doc_sequences.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask
from modules.helpers import generate_display_id, ensure_doc_sequences


# ================================================================
# Fake conn — mensimulasikan doc_sequences (counter per seq_key)
# ================================================================
class FakeSeqCursor:
    def __init__(self, store):
        self.store = store
        self.lastrowid = 0
        self._seq = 0

    def execute(self, sql, params=None):
        up = sql.upper()
        if 'CREATE TABLE' in up:
            return None
        if 'SELECT LAST_INSERT_ID' in up:
            # SELECT LAST_INSERT_ID() — tanpa params; kembalikan nilai terakhir.
            return None
        # INSERT ... VALUES (k, LAST_INSERT_ID(1)) / ODKU ... LAST_INSERT_ID(seq+1)
        params = params or ()
        key = params[0]
        self.store[key] = self.store.get(key, 0) + 1
        self._seq = self.store[key]
        self.lastrowid = self._seq
        return None

    def fetchone(self):
        return (self._seq,)

    def close(self):
        pass


class FakeSeqConn:
    def __init__(self, store):
        self.store = store
        self.commits = 0

    def cursor(self):
        return FakeSeqCursor(self.store)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


class ExplodingConn:
    def cursor(self):
        raise RuntimeError('db down')

    def close(self):
        pass


# ================================================================
# TEST 1: Format standar (jalur in-memory)
# ================================================================
class TestFormat:
    def test_format_standar(self):
        did = generate_display_id('WTR')
        parts = did.split('-')
        assert len(parts) == 4, f"Harus 4 bagian: {did}"
        assert parts[0] == 'WTR'
        assert parts[1] and parts[1].isupper(), f"Cabang uppercase: {did}"
        assert len(parts[2]) == 8 and parts[2].isdigit()
        assert len(parts[3]) == 4 and parts[3].isdigit()

    def test_format_per_prefix(self):
        assert generate_display_id('CASH').startswith('CASH-')
        assert generate_display_id('BPF').startswith('BPF-')
        assert generate_display_id('TRIP').startswith('TRIP-')
        assert generate_display_id('PLM').startswith('PLM-')

    def test_unique_50(self):
        ids = {generate_display_id('WTR') for _ in range(50)}
        assert len(ids) == 50, "ID harus unik"

    def test_seq_naik(self):
        a = generate_display_id('APP')
        b = generate_display_id('APP')
        assert a != b, "Dua id harus berbeda (seq naik)"
        # hanya bagian terakhir yang berbeda
        assert a.rsplit('-', 1)[0] == b.rsplit('-', 1)[0]


# ================================================================
# TEST 2: Jalur DB (doc_sequences atomik)
# ================================================================
class TestDbPath:
    def test_seq_atomic_naik(self):
        store = {}
        conn = FakeSeqConn(store)
        ids = [generate_display_id('WTR', conn) for _ in range(3)]
        seqs = [int(i.split('-')[-1]) for i in ids]
        assert seqs == [1, 2, 3], f"Seq harus berurutan: {seqs}"
        assert len(ids[0].split('-')) == 4

    def test_db_down_fallback_memory(self):
        did = generate_display_id('WTR', ExplodingConn())
        assert len(did.split('-')) == 4, "Fallback in-memory tetap format standar"


# ================================================================
# TEST 3: ensure_doc_sequences idempoten
# ================================================================
class TestEnsure:
    def test_idempotent(self):
        conn = FakeSeqConn({})
        assert ensure_doc_sequences(conn) is True
        assert ensure_doc_sequences(conn) is True


# ================================================================
# TEST 4: Cabang dari sesi
# ================================================================
class TestBranchFromSession:
    def test_branch_dari_sesi(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        with app.test_request_context('/x'):
            from flask import session
            session['branch_code'] = 'BDG'
            did = generate_display_id('WTR')
        assert '-BDG-' in did, f"Harus memuat cabang BDG: {did}"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])