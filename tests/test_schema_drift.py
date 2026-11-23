def test_parse_create_table_mendapat_kolom():
    from scripts.check_schema_drift import parse_init_sql
    ddl = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(10));"
    assert parse_init_sql(ddl)["t"] == ["id", "name"]


def test_db_tidak_tersedia_tidak_traceback(monkeypatch):
    from scripts import check_schema_drift
    monkeypatch.setattr(check_schema_drift, 'get_db_connection', lambda: None)
    assert check_schema_drift.main() == 0
