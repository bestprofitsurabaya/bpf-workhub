"""Finance BBM workspace routes: persistent claim/cash-LPJ list and evidence upload."""
from flask import Flask

import modules.routes_api_transactions as rat


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.conn.queries.append((sql, params))

    def fetchone(self):
        sql = self.conn.queries[-1][0]
        if 'COUNT(*)' in sql:
            return {'total': 1}
        return self.conn.transaction

    def fetchall(self):
        return [self.conn.list_row]

    def close(self):
        pass


class Connection:
    def __init__(self, transaction=None, list_row=None):
        self.transaction = transaction or {'transaction_type': 'CASH_LPJ', 'nopol': 'L 1 A'}
        self.list_row = list_row or {
            'id': 4, 'display_id': 'BPF-SBY-20261028-0001',
            'transaction_type': 'CASH_LPJ', 'cash_request_id': 9,
            'driver_name': 'BUDI', 'nopol': 'L 1 A', 'vehicle_type': 'AVANZA',
            'bbm_type': 'PERTALITE', 'nominal': 100000, 'liter': 10,
            'odo_km': 1000, 'ml_anomaly_flag': 0, 'status': 'verified_ga',
            'created_at': '2026-10-28 10:00:00', 'foto_mypertamina_admin': None,
            'subsidy_tx_id': None,
        }
        self.queries = []
        self.commits = 0

    def cursor(self, dictionary=False):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def make_client(monkeypatch, conn=None, tmp_path=None):
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['UPLOAD_FOLDER'] = str(tmp_path or '.')
    conn = conn or Connection()
    monkeypatch.setattr(rat, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(rat, 'log_activity_async', lambda *a, **k: None)
    rat.register_transaction_api(app)
    return app.test_client(), conn


def login(client, role='finance'):
    with client.session_transaction() as session:
        session['user_name'] = 'finance_sby'
        session['user_role'] = role
        session['csrf_token'] = 'csrf'


def test_finance_workspace_list_requires_finance_role(monkeypatch, tmp_path):
    client, _ = make_client(monkeypatch, tmp_path=tmp_path)
    assert client.get('/api/finance/bbm').status_code == 401
    login(client, 'driver')
    assert client.get('/api/finance/bbm').status_code == 403


def test_history_includes_completed_cash_lpj_and_excludes_dummy(monkeypatch, tmp_path):
    client, conn = make_client(monkeypatch, tmp_path=tmp_path)
    login(client)
    response = client.get('/api/finance/bbm?tab=history')
    assert response.status_code == 200
    assert response.get_json()['data'][0]['transaction_type'] == 'CASH_LPJ'
    sql = conn.queries[-1][0]
    assert "transaction_type='CASH_LPJ'" in sql
    assert "status IN ('verified_ga','archived')" in sql
    assert '(is_dummy=0 OR is_dummy IS NULL)' in sql


def test_incoming_and_ready_list_only_claim_not_cash_lpj(monkeypatch, tmp_path):
    client, conn = make_client(monkeypatch, tmp_path=tmp_path)
    login(client)
    for tab in ('incoming', 'ready'):
        conn.queries.clear()
        response = client.get(f'/api/finance/bbm?tab={tab}')
        assert response.status_code == 200
        sql = conn.queries[-1][0]
        assert "COALESCE(transaction_type,'CLAIM') = 'CLAIM'" in sql
        assert "'CASH_LPJ'" not in sql


def test_finance_evidence_upload_updates_transaction_without_changing_status(monkeypatch, tmp_path):
    conn = Connection()
    client, conn = make_client(monkeypatch, conn=conn, tmp_path=tmp_path)
    login(client)
    monkeypatch.setattr(rat, 'save_file', lambda upload, prefix, nopol, folder: 'evidence.png')
    response = client.post('/api/finance/bbm/4/subsidy-evidence', data={
        'file': ( __import__('io').BytesIO(b'image'), 'evidence.png', 'image/png'),
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    assert response.get_json()['photo']['url'] == '/uploads/evidence.png'
    update = [q for q in conn.queries if q[0].startswith('UPDATE transactions SET foto_mypertamina_admin')]
    assert update and update[0][1] == ('evidence.png', 4)
    assert conn.commits == 1
