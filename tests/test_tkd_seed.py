from pathlib import Path
from scripts.seed_tkd_bank import seed_bank

ROOT = Path(__file__).resolve().parents[1]
CSV = (ROOT / 'docs' / 'seed' / 'tkd_bank_v1.csv').read_text(encoding='utf-8')

class _Cursor:
    def __init__(self, existing): self.existing = existing; self.inserted = []
    def execute(self, sql, params=None):
        if 'FROM TKD_QUESTIONS' in ' '.join(str(sql).upper().split()):
            self._rows = [{'code': c} for c in self.existing]
        elif 'INSERT INTO TKD_QUESTIONS' in ' '.join(str(sql).upper().split()):
            self.inserted.append(params)
        else:
            self._rows = []
    def fetchall(self): return getattr(self, '_rows', [])
    def fetchone(self): return None
    def close(self): pass

class _Conn:
    def __init__(self, existing): self.c = _Cursor(existing)
    def cursor(self, dictionary=False): return self.c
    def commit(self): pass

def test_seed_insert_if_absent_tidak_menyentuh_kode_yang_ada():
    conn = _Conn(existing={'REG-01'})
    out = seed_bank(conn.c, CSV)
    assert out['inserted'] == 30 and out['skipped'] == 1
    assert all(p[-1] == 0 for p in conn.c.inserted)  # active=0

def test_seed_idempoten_saat_semua_kode_sudah_ada():
    codes = {line.split(',')[0] for line in CSV.splitlines()[1:] if line.strip()}
    conn = _Conn(existing=codes)
    out = seed_bank(conn.c, CSV)
    assert out['inserted'] == 0 and out['skipped'] == 31
