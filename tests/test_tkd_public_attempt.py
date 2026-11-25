# tests/test_tkd_public_attempt.py
from datetime import datetime, timedelta
import json
import time
import pytest
from flask import Flask
from modules import routes_tkd as rt
from modules import tkd_service as svc

NIK = '3573010101990001'
ATTEMPT = {'id': 'TKD-1', 'case_id': 'RC-1', 'attempt_no': 1, 'status': 'BERLANGSUNG',
           'expires_at': datetime.now() + timedelta(minutes=20), 'modal_tier': '30k',
           'settings_snapshot': json.dumps({'duration_minutes': 25}),
           'pass_score_snapshot': 70, 'branch_code': 'SBY'}
ITEM = {'position': 1, 'snapshot': json.dumps({'type': 'MCQ', 'category': 'REGULASI',
        'prompt': 'P', 'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
        'answer': {'option': 'a'}, 'points': 1}), 'answer': None}
BASE = '/api/recruitment/tkd/attempts/TKD-1'
ENDPOINTS = [('GET', BASE), ('PUT', BASE + '/answers/1'),
             ('POST', BASE + '/submit'), ('GET', BASE + '/result')]


@pytest.fixture(autouse=True)
def _waktu_import_yang_basi(monkeypatch):
    """Simulasikan suite panjang: expiry tidak boleh berasal dari waktu import.

    Regresi v2.134.0: pytest penuh butuh >20 menit tanpa DB, jadi konstanta
    `ATTEMPT` yang dihitung saat modul diimpor sudah kedaluwarsa saat tes ini
    dijalankan. Fixture `ctx` wajib membuat expires_at yang segar per tes.
    """
    monkeypatch.setitem(ATTEMPT, 'expires_at', datetime.now() - timedelta(minutes=1))


class _Cursor:
    """Cursor tiruan yang mencatat SQL dan commit lewat `cursor.connection`."""

    def __init__(self, conn):
        self.conn = conn
        self.connection = conn

    def execute(self, sql, params=None):
        self.conn.events.append('sql')
        self.conn.statements.append((' '.join(str(sql).split()), params))

    def close(self):
        self.conn.events.append('cursor_close')


class _Conn:
    def __init__(self):
        self.events = []
        self.statements = []

    def cursor(self, dictionary=False):
        return _Cursor(self)

    def commit(self):
        self.events.append('commit')

    def rollback(self):
        self.events.append('rollback')

    def close(self):
        self.events.append('close')


@pytest.fixture
def ctx(monkeypatch):
    a = Flask(__name__); a.secret_key = 'tkd-test'
    rt.register_tkd_routes(a)
    conn = _Conn()
    # Expiry harus dihitung saat tes berjalan, bukan saat modul diimpor:
    # suite penuh bisa berjalan >20 menit tanpa DB (lihat fixture atas).
    attempt = dict(ATTEMPT, expires_at=datetime.now() + timedelta(minutes=20))
    state = {'attempt': attempt, 'items': [dict(ITEM)],
             'finalize_calls': [], 'submit_audits': [], 'rate_calls': [],
             'fetch_for_update': [], 'results': []}

    monkeypatch.setattr(rt, 'get_master_connection', lambda: conn)

    def _rate(*args, **kwargs):
        state['rate_calls'].append((args, kwargs))
        return True
    monkeypatch.setattr(rt, 'redis_rate_hit', _rate)

    def _fetch(cur, aid, for_update=False):
        if aid != 'TKD-1':
            return None
        state['fetch_for_update'].append(for_update)
        return state['attempt']
    monkeypatch.setattr(svc, 'fetch_attempt', _fetch)
    monkeypatch.setattr(svc, 'fetch_attempt_items', lambda cur, aid: state['items'])
    monkeypatch.setattr(svc, 'load_settings', lambda cur: {'pass_score': 70, 'max_attempts': 2, 'question_count': 20, 'duration_minutes': 25, 'active': 1, 'quota': {}})
    monkeypatch.setattr(svc, 'fetch_case_by_nik', lambda cur, nik: {'case_id': 'RC-1', 'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0})
    monkeypatch.setattr(svc, 'fetch_attempts', lambda cur, cid: [state['attempt']])
    monkeypatch.setattr(svc, 'fetch_tkd_steps', lambda cur, cid: [])
    monkeypatch.setattr(svc, 'finalize_expired', lambda cur, cid: [])

    def _finalize(cur, attempt, status='SELESAI'):
        conn.events.append('finalize')
        state['finalize_calls'].append(status)
        # Mutasi objek yang sama: fetch berikutnya harus melihat attempt selesai.
        attempt.update(status=status, score=85.0, passed=1,
                       submitted_at=datetime.now())
        state['attempt'] = attempt
        return attempt
    monkeypatch.setattr(svc, 'finalize_attempt', _finalize)

    def _result(cur, attempt, settings):
        state['results'].append({'attempt_id': attempt.get('id'),
                                 'status': attempt.get('status'),
                                 'score': attempt.get('score')})
        return {'score': 85.0, 'passed': True, 'official_score': 85.0,
                'best_score': 85.0, 'attempts_used': 1, 'max_attempts': 2,
                'state': 'LULUS'}
    monkeypatch.setattr(svc, 'attempt_result', _result)

    def _audit(*args, **kwargs):
        conn.events.append('audit')
        state['submit_audits'].append((args, kwargs))
    monkeypatch.setattr(rt, 'log_activity_async', _audit)

    return {'app': a, 'conn': conn, 'state': state}


@pytest.fixture
def app(ctx):
    return ctx['app']


def _client(app, case_id='RC-1', verified_at=None):
    c = app.test_client()
    with c.session_transaction() as s:
        if case_id is not None:
            s['tkd_case_id'] = case_id
        s['tkd_verified_at'] = int(time.time() if verified_at is None else verified_at)
    return c


def test_attempt_tanpa_sesi_atau_kasus_lain_ditolak(app):
    assert app.test_client().get(BASE).status_code == 403
    assert _client(app, 'RC-lain').get(BASE).status_code == 404


def test_resume_mengembalikan_soal_tanpa_kunci(app):
    r = _client(app).get(BASE)
    assert r.status_code == 200
    body = r.get_json()['data']
    q = body['questions'][0]
    assert 'answer' not in q and 'points' not in q
    assert q['position'] == 1


def test_simpan_jawaban_mcq_valid_dan_opsi_asing_ditolak(app, monkeypatch):
    saved = {}
    monkeypatch.setattr(rt, '_save_answer', lambda cur, item, answer: saved.update(answer=answer))
    c = _client(app)
    ok = c.put(BASE + '/answers/1', json={'answer': {'option': 'b'}})
    assert ok.status_code == 200 and saved['answer'] == {'option': 'b'}
    bad = c.put(BASE + '/answers/1', json={'answer': {'option': 'z'}})
    assert bad.status_code == 400
    missing = c.put(BASE + '/answers/99', json={'answer': {'option': 'a'}})
    assert missing.status_code == 404


def test_submit_idempoten_dan_tanpa_kunci(ctx):
    app, state = ctx['app'], ctx['state']
    c = _client(app)
    first = c.post(BASE + '/submit')
    second = c.post(BASE + '/submit')
    assert first.status_code == 200 and second.status_code == 200
    assert 'answer' not in first.get_data(as_text=True)
    # Attempt yang sudah selesai tidak boleh difinalisasi/diaudit dua kali.
    assert state['finalize_calls'] == ['SELESAI']
    assert len(state['submit_audits']) == 1
    assert state['fetch_for_update'] == [True, True]


def test_hasil_attempt_masih_berjalan_ditolak(app):
    assert _client(app).get(BASE + '/result').status_code == 409


@pytest.mark.parametrize('method,path', ENDPOINTS)
def test_sesi_kosong_basi_dan_kasus_lain_ditolak(ctx, method, path):
    app = ctx['app']
    responses = (
        app.test_client().open(path, method=method, json={}),
        _client(app, verified_at=time.time() - 7201).open(path, method=method, json={}),
        _client(app, 'RC-lain').open(path, method=method, json={}),
    )
    assert [r.status_code for r in responses] == [403, 403, 404]
    assert all(r.headers['Cache-Control'] == 'no-store' for r in responses)


def test_no_store_juga_untuk_sukses_dan_gagal_validasi(ctx):
    c = _client(ctx['app'])
    ok = c.get(BASE)
    bad = c.put(BASE + '/answers/1', json={'answer': {'option': 'z'}})
    conflict = c.get(BASE + '/result')
    assert [ok.status_code, bad.status_code, conflict.status_code] == [200, 400, 409]
    assert all(r.headers['Cache-Control'] == 'no-store'
               for r in (ok, bad, conflict))


def test_rate_limit_jawaban_dan_submit(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(rt, 'redis_rate_hit',
                        lambda *a, **k: calls.append((a, k)) or False)
    c = _client(ctx['app'])
    answer = c.put(BASE + '/answers/1', json={'answer': {'option': 'a'}})
    assert answer.status_code == 429
    assert calls[-1] == (('tkd-answer|TKD-1', 60, 60), {'prefix': 'tkd'})
    submit = c.post(BASE + '/submit')
    assert submit.status_code == 429
    assert calls[-1] == (('tkd-submit|TKD-1', 5, 60), {'prefix': 'tkd'})
    assert answer.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('suffix,method,expected', [
    ('', 'GET', 200), ('/answers/1', 'PUT', 409), ('/result', 'GET', 200),
])
def test_kedaluwarsa_finalisasi_then_commit(ctx, suffix, method, expected):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    state['attempt']['expires_at'] = datetime.now() - timedelta(minutes=1)
    state['items'] = [{'position': 1, 'attempt_id': 'TKD-1',
                       'snapshot': json.dumps({'type': 'MCQ',
                                               'options': [{'id': 'a'}]})}]
    r = _client(app).open(BASE + suffix, method=method,
                          json={'answer': {'option': 'a'}})
    assert r.status_code == expected
    assert state['finalize_calls'] == ['KEDALUWARSA']
    assert conn.events.index('finalize') < conn.events.index('commit')
    data = r.get_json()['data']
    result = data['result'] if suffix == '' else data
    assert result['score'] == 85.0
    assert 'answer' not in r.get_data(as_text=True)


@pytest.mark.parametrize('offset,expected_status', [
    (timedelta(0), 'SELESAI'), (timedelta(seconds=1), 'KEDALUWARSA'),
])
def test_submit_batas_grace_60_detik(ctx, monkeypatch, offset, expected_status):
    expiry = datetime(2026, 11, 25, 10, 0, 0)
    fixed_now = expiry + timedelta(seconds=60) + offset

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(rt, 'datetime', _FrozenDatetime)
    ctx['state']['attempt']['expires_at'] = _FrozenDatetime(2026, 11, 25, 10, 0, 0)
    r = _client(ctx['app']).post(BASE + '/submit')
    assert r.status_code == 200
    assert ctx['state']['finalize_calls'] == [expected_status]
    assert len(ctx['state']['submit_audits']) == 1


def test_audit_submit_hanya_field_diizinkan(ctx):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    _client(app).post(BASE + '/submit')
    args, kwargs = state['submit_audits'][0]
    assert args[1] == 'tkd_attempt_submit'
    assert kwargs['new_data'] == {'attempt_id': 'TKD-1', 'case_id': 'RC-1',
                                  'status': 'SELESAI', 'score': 85.0}
    # `branch_code` adalah kolom activity_logs terpisah (disetujui reviewer).
    assert kwargs['branch_code'] == 'SBY'
    assert NIK not in json.dumps({'args': args, 'kwargs': kwargs})
    assert conn.events.index('commit') < conn.events.index('audit')


def test_save_answer_menjalankan_update_dan_commit(ctx):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    state['items'] = [{'position': 1, 'attempt_id': 'TKD-1',
                       'snapshot': json.dumps({'type': 'MCQ',
                                               'options': [{'id': 'a'}]})}]
    r = _client(app).put(BASE + '/answers/1', json={'answer': {'option': 'a'}})
    assert r.status_code == 200
    assert r.get_json()['data'] == {'position': 1, 'saved': True}
    assert conn.events.count('commit') == 1
    assert conn.events.index('sql') < conn.events.index('commit')
    sql, params = conn.statements[-1]
    assert sql.upper().startswith('UPDATE TKD_ATTEMPT_ITEMS SET ANSWER=%S, ANSWERED_AT=NOW()')
    assert params == (json.dumps({'option': 'a'}, ensure_ascii=False), 'TKD-1', 1)


@pytest.mark.parametrize('qtype,answer,expected', [
    ('NUMERIC', {'value': '1.234,5'}, {'value': 1234.5}),
    ('NUMERIC', '1.234,5', {'value': 1234.5}),
    ('SHORT_TEXT', {'text': 'x' * 600}, {'text': 'x' * 500}),
    ('PROFILE', {'text': 'y' * 1200}, {'text': 'y' * 1000}),
    ('PROFILE_TEXT', {'text': 'z' * 1200}, {'text': 'z' * 1000}),
])
def test_validasi_dan_pemotongan_jawaban(ctx, qtype, answer, expected):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    state['items'][0]['snapshot'] = json.dumps({'type': qtype})
    r = _client(app).put(BASE + '/answers/1', json={'answer': answer})
    assert r.status_code == 200
    assert conn.statements[-1][1][0] == json.dumps(expected, ensure_ascii=False)


@pytest.mark.parametrize('qtype,answer', [
    ('NUMERIC', {'value': 'abc'}),
    ('SHORT_TEXT', {'text': 123}),
    ('PROFILE', {'text': None}),
])
def test_jawaban_tidak_sah_ditolak(ctx, qtype, answer):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    state['items'][0]['snapshot'] = json.dumps({'type': qtype})
    r = _client(app).put(BASE + '/answers/1', json={'answer': answer})
    assert r.status_code == 400
    assert not conn.statements


@pytest.mark.parametrize('snapshot_id,request_id,expected', [
    (1, '1', 1), ('1', 1, '1'),
])
def test_id_opsi_mengikuti_snapshot(ctx, snapshot_id, request_id, expected):
    app, conn, state = ctx['app'], ctx['conn'], ctx['state']
    state['items'][0]['snapshot'] = json.dumps({
        'type': 'MCQ', 'options': [{'id': snapshot_id, 'text': 'A'}]})
    r = _client(app).put(BASE + '/answers/1', json={'answer': {'option': request_id}})
    assert r.status_code == 200
    assert conn.statements[-1][1][0] == json.dumps({'option': expected},
                                                   ensure_ascii=False)
