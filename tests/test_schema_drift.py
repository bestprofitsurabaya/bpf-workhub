def test_parse_create_table_mendapat_kolom():
    from scripts.check_schema_drift import parse_init_sql
    ddl = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(10));"
    assert parse_init_sql(ddl)["t"] == ["id", "name"]


def test_db_tidak_tersedia_tidak_traceback(monkeypatch):
    from scripts import check_schema_drift
    monkeypatch.setattr(check_schema_drift, 'get_db_connection', lambda: None)
    assert check_schema_drift.main() == 0

def test_parse_unique_named_inline_dan_primary():
    from scripts.check_schema_drift import parse_init_unique
    ddl = """
    CREATE TABLE t (
      id INT PRIMARY KEY,
      code VARCHAR(10) UNIQUE,
      a INT,
      b INT,
      UNIQUE KEY uq_a_b (a, b)
    );
    """
    uq = parse_init_unique(ddl)
    assert ('id',) in uq['t']
    assert ('code',) in uq['t']
    assert ('a', 'b') in uq['t']

    # Prefix index (geocode_cache) dibandingkan sebagai nama kolom saja.
    ddl_prefix = "CREATE TABLE g (address VARCHAR(500), PRIMARY KEY (address(255)));"
    assert parse_init_unique(ddl_prefix)['g'] == {('address',)}


def test_compare_unique_deteksi_hilang_tanpa_bandingkan_nama_index():
    from scripts.check_schema_drift import compare_unique_with_db
    expected = {'t': {('code',), ('a', 'b')}}
    assert compare_unique_with_db(expected, {'t': {('code',)}}) == [
        'unique t (a, b) hilang dari DB']
    # Nama index boleh berbeda asal kolomnya sama (mis. idx_trip_display_id).
    assert compare_unique_with_db(
        expected, {'t': {('code',), ('a', 'b')}}) == []


class _BranchCursor:
    """Cursor palsu: information_schema per nama schema."""

    def __init__(self, columns, uniques):
        self.columns = columns
        self.uniques = uniques
        self._sql = ''
        self._params = None

    def execute(self, sql, params=None):
        self._sql = sql
        self._params = params

    def fetchall(self):
        schema = self._params[0]
        if 'information_schema.COLUMNS' in self._sql:
            return [(t, c) for t, cols in self.columns.get(schema, {}).items()
                    for c in sorted(cols)]
        rows = []
        for table, sets in self.uniques.get(schema, {}).items():
            for idx, cols in enumerate(sorted(sets)):
                for seq, col in enumerate(cols, start=1):
                    rows.append((table, 'idx{}'.format(idx), col, seq))
        return rows


def test_compare_schema_cabang_mendeteksi_kolom_hilang():
    from scripts.check_schema_drift import compare_schema
    expected = {'transactions': ['id', 'gps_kota']}
    expected_unique = {'transactions': {('id',)}}
    cursor = _BranchCursor(
        columns={'bpf_branch_x': {'transactions': {'id'}}},
        uniques={'bpf_branch_x': {'transactions': {('id',)}}})
    assert compare_schema(
        expected, expected_unique, cursor, 'bpf_branch_x') == [
        'kolom transactions.gps_kota hilang dari DB']


def test_branch_schemas_tanpa_tabel_branches_tidak_error():
    from scripts.check_schema_drift import branch_schemas

    class _NoBranches:
        def execute(self, sql, params=None):
            raise RuntimeError('tabel branches tidak ada')

        def fetchall(self):
            return []

    assert branch_schemas(_NoBranches()) == []


def test_branch_schemas_mengembalikan_kode_dan_db():
    from scripts.check_schema_drift import branch_schemas

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return [('SBY', 'bpf_asset_system'), ('MLG', 'bpf_branch_malang')]

    assert branch_schemas(_Cursor()) == [
        ('SBY', 'bpf_asset_system'), ('MLG', 'bpf_branch_malang')]
