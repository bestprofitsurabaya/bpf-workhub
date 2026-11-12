"""Kontrak antrean 'Perlu Tindakan' (v2.103.0 — Fase 3; v2.104.0 — baris & aksi)."""
from datetime import datetime

from modules import bbm_action_queue as aq


class FakeCursor:
    """Cursor palsu: menjawab dari dict per jenis antrean."""

    def __init__(self, data):
        self.data = data
        self.executed = []
        self._key = None
        self._kind = None

    @staticmethod
    def _key_of(sql):
        if "status IN ('pending', 'modified')" in sql:
            return 'claim_pending'
        if "status = 'FUNDS_WITH_DRIVER'" in sql:
            return 'driver_due_lpj'
        if "status = 'LPJ_SUBMITTED'" in sql:
            return 'lpj_pending'
        if "subsidy_match = 'mismatch'" in sql:
            return 'spbu_mismatch'
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._key = self._key_of(sql)
        self._kind = 'rows' if 'LIMIT %s' in sql else 'count'

    def fetchone(self):
        return (self.data.get(self._key) or {}).get('count') or {}

    def fetchall(self):
        return (self.data.get(self._key) or {}).get('rows') or []

    def close(self):
        pass


class FakeConn:
    def __init__(self, data):
        self.cur = FakeCursor(data)

    def cursor(self, dictionary=False):
        return self.cur


NOW = datetime(2026, 11, 12, 10, 0, 0)


def _empty():
    return {
        'claim_pending': {'count': {'n': 0, 'amount': 0, 'oldest': None}, 'rows': []},
        'driver_due_lpj': {'count': {'n': 0, 'amount': 0, 'oldest': None}, 'rows': []},
        'lpj_pending': {'count': {'n': 0, 'amount': 0, 'oldest': None}, 'rows': []},
        'spbu_mismatch': {'count': {'n': 0, 'amount': 0, 'oldest': None}, 'rows': []},
    }


def test_ambang_sop_tertulis_di_satu_tempat():
    assert aq.ACTION_THRESHOLDS == {'claim_days': 2, 'driver_days': 14, 'lpj_days': 7}


def test_tidak_ada_antrean_tidak_menghasilkan_item():
    conn = FakeConn(_empty())
    out = aq.action_queue(conn, now=NOW)
    assert out['items'] == []
    assert out['thresholds']['driver_days'] == 14
    assert out['generated_at'].startswith('2026-11-12')


def test_item_memuat_umur_nominal_dan_tab_tujuan():
    data = _empty()
    data['claim_pending']['count'] = {
        'n': 3, 'amount': 150000, 'oldest': datetime(2026, 11, 7, 9, 0, 0)}   # 5 hari
    data['driver_due_lpj']['count'] = {
        'n': 1, 'amount': 500000, 'oldest': datetime(2026, 10, 20, 9, 0, 0)}  # 23 hari
    data['lpj_pending']['count'] = {
        'n': 2, 'amount': 200000, 'oldest': datetime(2026, 11, 1, 9, 0, 0)}    # 11 hari
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    by_key = {i['key']: i for i in out['items']}

    assert by_key['claim_pending']['count'] == 3
    assert by_key['claim_pending']['oldest_days'] == 5
    assert by_key['claim_pending']['target'] == 'bbm'
    assert by_key['driver_due_lpj']['oldest_days'] == 23
    assert by_key['driver_due_lpj']['amount'] == 500000.0
    assert by_key['driver_due_lpj']['target'] == 'kasbon'
    assert by_key['lpj_pending']['oldest_days'] == 11
    assert by_key['lpj_pending']['threshold_days'] == 7
    # Tiap item tahu jenis barisnya (claim / kasbon) — frontend memakai ini
    # untuk menentukan tombol aksi yang boleh tampil per peran.
    assert by_key['claim_pending']['kind'] == 'claim'
    assert by_key['lpj_pending']['kind'] == 'cash'


def test_cutoff_memakai_ambang_dan_status_yang_menunggu_aksi():
    data = _empty()
    conn = FakeConn(data)
    aq.action_queue(conn, now=NOW)
    sqls = [sql for sql, _ in conn.cur.executed]
    params = [p[0] for _, p in conn.cur.executed]

    assert params[0] == NOW.replace(day=10)          # klaim > 2 hari
    assert params[2] == NOW.replace(day=5)           # LPJ > 7 hari
    assert "status IN ('pending', 'modified')" in sqls[0]
    assert "status = 'FUNDS_WITH_DRIVER'" in sqls[1]
    assert "status = 'LPJ_SUBMITTED'" in sqls[2]
    # Tidak ada status final yang/antre yang menunggu aksi.
    for sql in sqls:
        assert "'COMPLETED'" not in sql


def test_antrean_kosong_untuk_satu_jenis_tidak_menggeser_lainnya():
    data = _empty()
    data['driver_due_lpj']['count'] = {
        'n': 2, 'amount': 700000, 'oldest': datetime(2026, 10, 1)}
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    assert [i['key'] for i in out['items']] == ['driver_due_lpj']


# --- v2.104.0: baris nyata + antrean keempat SPBU mismatch ---

def test_item_membawa_baris_nyata_bukan_jumlah_saja():
    data = _empty()
    data['lpj_pending']['count'] = {'n': 2, 'amount': 700000, 'oldest': datetime(2026, 11, 1)}
    data['lpj_pending']['rows'] = [
        {'id': 11, 'ref': 'KSB-001', 'driver_name': 'Budi', 'nopol': 'N 1',
         'amount': 300000, 'since': datetime(2026, 11, 1, 8, 0, 0)},
        {'id': 12, 'ref': 'KSB-002', 'driver_name': 'Sari', 'nopol': '',
         'amount': 400000, 'since': datetime(2026, 11, 3, 8, 0, 0)},
    ]
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    item = out['items'][0]
    assert item['count'] == 2
    assert len(item['rows']) == 2
    assert item['rows'][0]['id'] == 11
    assert item['rows'][0]['ref'] == 'KSB-001'
    assert item['rows'][0]['amount'] == 300000.0
    # Umur per baris dihitung dari `since`, bukan dari agregat.
    assert item['rows'][0]['age_days'] == 11
    assert item['rows'][1]['age_days'] == 9


def test_baris_dibatasi_supaya_payload_antrean_tetap_kecil():
    data = _empty()
    data['claim_pending']['count'] = {'n': 57, 'amount': 100, 'oldest': datetime(2026, 1, 1)}
    data['claim_pending']['rows'] = [
        {'id': i, 'ref': f'C-{i}', 'driver_name': '', 'nopol': '',
         'amount': 0, 'since': datetime(2026, 1, 1)} for i in range(aq.MAX_ROWS)
    ]
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    item = out['items'][0]
    assert item['count'] == 57               # total tetap akurat
    assert len(item['rows']) == aq.MAX_ROWS   # baris dibatasi
    # Parameter LIMIT ikut dikirim ke query baris.
    rows_sql = [sql for sql, _ in conn.cur.executed if 'LIMIT %s' in sql][0]
    assert rows_sql.rstrip().endswith('LIMIT %s')


def test_antrean_spbu_mismatch_membaca_verdict_auto_match_yang_sudah_ada():
    """Mismatch bukan aturan baru — ini verdict yang sudah ditulis mesin
    auto-match (subsidy_match='mismatch'). Antrean hanya membacanya."""
    data = _empty()
    data['spbu_mismatch']['count'] = {'n': 4, 'amount': 1800000, 'oldest': datetime(2026, 11, 3)}
    data['spbu_mismatch']['rows'] = [
        {'id': 91, 'ref': 'TX-91', 'driver_name': 'Dedi', 'nopol': 'N 9',
         'amount': 450000, 'since': datetime(2026, 11, 3, 9, 0, 0)},
    ]
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    item = {i['key']: i for i in out['items']}['spbu_mismatch']
    assert item['count'] == 4
    assert item['target'] == 'subsidy'
    assert item['rows'][0]['id'] == 91

    sqls = [sql for sql, _ in conn.cur.executed]
    mismatch_sql = [s for s in sqls if "subsidy_match = 'mismatch'" in s]
    assert mismatch_sql, 'antrean mismatch harus membaca kolom subsidy_match'
    # Klaim yang sudah ditutup tidak masuk antrean.
    assert "status NOT IN ('archived', 'rejected')" in mismatch_sql[0]
    # Tidak ada penilaian ulang di SQL — tidak ada aturan angka baru di sini.
    assert 'ABS(' not in mismatch_sql[0].upper()
    assert 'liter' not in mismatch_sql[0]


def test_mismatch_memakai_ambang_klaim_supaya_antrean_konsisten():
    data = _empty()
    conn = FakeConn(data)
    aq.action_queue(conn, now=NOW)
    params = [p[0] for _, p in conn.cur.executed]
    # Urutan: claim, driver, lpj, mismatch (mismatch pakai ambang klaim 2 hari).
    assert params[3] == NOW.replace(day=10)


def test_semua_item_membawa_baris_dan_batas_nilai_konsisten():
    """Nilai non-numerik tidak boleh membuat antrean error (payload JSON-safe)."""
    data = _empty()
    data['claim_pending']['count'] = {'n': 1, 'amount': None, 'oldest': None}
    data['claim_pending']['rows'] = [
        {'id': 5, 'ref': None, 'driver_name': None, 'nopol': None,
         'amount': None, 'since': None},
    ]
    conn = FakeConn(data)
    out = aq.action_queue(conn, now=NOW)
    row = out['items'][0]['rows'][0]
    assert row['ref'] == ''
    assert row['driver_name'] == ''
    assert row['amount'] == 0.0
    assert row['age_days'] is None


def test_satu_jenis_gagal_tidak_mematikan_panel_seluruhnya():
    """Mis. kolom `subsidy_match` belum ada di DB cabang lama → antrean
    mismatch dilewati, jenis lain tetap tampil dan errornya dilaporkan."""
    class BrokenCursor(FakeCursor):
        def execute(self, sql, params=None):
            if "subsidy_match = 'mismatch'" in sql:
                raise Exception("Unknown column 'subsidy_match'")
            return super().execute(sql, params)

    data = _empty()
    data['claim_pending']['count'] = {'n': 2, 'amount': 100, 'oldest': datetime(2026, 11, 1)}
    data['claim_pending']['rows'] = [
        {'id': 1, 'ref': 'C-1', 'driver_name': '', 'nopol': '', 'amount': 100,
         'since': datetime(2026, 11, 1)},
    ]
    conn = FakeConn(data)
    conn.cur = BrokenCursor(data)
    out = aq.action_queue(conn, now=NOW)

    assert [i['key'] for i in out['items']] == ['claim_pending']
    assert out['errors'] and out['errors'][0]['key'] == 'spbu_mismatch'
    assert 'subsidy_match' in out['errors'][0]['error']
