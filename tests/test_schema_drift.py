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
