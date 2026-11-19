"""Tes modul Agenda (v2.123.0).

Fokus:
- logika murni: validasi payload, pengulangan, ICS, media;
- isolasi & cakupan cabang (admin cabang / admin master / content creator);
- fan-out batch hanya Admin Pusat;
- guard route: role, step-up hapus, bridge Cordova.
"""
import os
import sys
from datetime import date, datetime

import pytest
from flask import Flask, session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import modules.agenda as ag  # noqa: E402
import modules.routes_agenda as ra  # noqa: E402
import modules.admin_scope as admin_scope  # noqa: E402
import modules.stepup as stepup  # noqa: E402


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.lastrowid = None
        self.log = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        if sql.strip().upper().startswith('INSERT'):
            self.lastrowid = 101
            self.rowcount = 1
        if sql.strip().upper().startswith('UPDATE'):
            self.rowcount = 1
        return None

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None):
        self.cur = FakeCursor(rows)
        self.commits = 0

    def cursor(self, dictionary=False):
        return self.cur

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _row(**kw):
    base = {
        'id': 1, 'batch_id': None, 'legacy_id': None, 'branch_code': 'SBY',
        'agenda_date': date(2026, 11, 19), 'title': 'Rapat',
        'body': 'Isi', 'category': 'umum', 'audience': 'all',
        'audience_roles': '', 'publish_mode': 'now', 'publish_at': None,
        'end_at': None, 'repeat_rule': 'none', 'repeat_until': None,
        'media_url': None, 'media_type': None, 'attachment_path': None,
        'pinned': 0, 'active': 1, 'created_by': 'admin', 'updated_by': 'admin',
    }
    base.update(kw)
    return base


class _Session:
    """Konteks request Flask dengan sesi tertentu."""

    def __init__(self, role='admin', username='admin', branch='SBY'):
        self.role = role
        self.username = username
        self.branch = branch

    def __enter__(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        session['user_role'] = self.role
        session['user_name'] = self.username
        session['branch_code'] = self.branch
        return self

    def __exit__(self, *exc):
        self.ctx.pop()


# ---------------------------------------------------------------------------
# Validasi payload
# ---------------------------------------------------------------------------
class TestValidate:
    def test_minimal_valid(self):
        item, errors = ag.validate_payload({'date': '2026-11-19', 'title': 'Rapat'})
        assert errors == []
        assert item['category'] == 'umum'
        assert item['repeat_rule'] == 'none'
        # Pengingat hari H opsional — default mati.
        assert item['notify_on_day'] == 0

    def test_notify_on_day_dinormalisasi(self):
        item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'notify_on_day': True})
        assert errors == []
        assert item['notify_on_day'] == 1
        item, _ = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'notify_on_day': 'off'})
        assert item['notify_on_day'] == 0

    def test_scheduled_wajib_publish_at(self):
        _item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'publish_mode': 'scheduled'})
        assert any('publish_at wajib' in e for e in errors)

    def test_end_harus_setelah_publish(self):
        _item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'publish_mode': 'scheduled',
            'publish_at': '2026-11-19T10:00', 'end_at': '2026-11-19T09:00'})
        assert any('end_at harus setelah' in e for e in errors)

    def test_repeat_maks_dua_tahun(self):
        _item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'repeat_rule': 'weekly',
            'repeat_until': '2030-01-01'})
        assert any('maksimal 2 tahun' in e for e in errors)

    def test_repeat_none_menghapus_until(self):
        item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'repeat_rule': 'none',
            'repeat_until': '2027-01-01'})
        assert errors == []
        assert item['repeat_until'] is None

    def test_media_url_divalidasi(self):
        _item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat', 'media_url': 'javascript:alert(1)'})
        assert errors

    def test_media_type_diisi_otomatis(self):
        item, errors = ag.validate_payload({
            'date': '2026-11-19', 'title': 'Rapat',
            'media_url': 'https://youtu.be/abc'})
        assert errors == []
        assert item['media_type'] == 'youtube'
        assert ag.media_kind('https://x.test/a.mp4')['kind'] == 'video'
        assert ag.media_kind('https://x.test/a.png')['kind'] == 'image'
        assert ag.media_kind('https://x.test/a')['kind'] == 'link'


# ---------------------------------------------------------------------------
# Pengulangan
# ---------------------------------------------------------------------------
class TestOccurrences:
    def test_weekly_mulai_dari_tanggal_yang_benar(self):
        r = _row(agenda_date=date(2026, 11, 2), repeat_rule='weekly',
                 repeat_until=date(2026, 12, 31))
        occ = ag.occurrences(r, date(2026, 11, 16), date(2026, 11, 30))
        assert occ == [date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 30)]

    def test_bulanan_31_dijepit_ke_akhir_bulan(self):
        r = _row(agenda_date=date(2026, 1, 31), repeat_rule='monthly',
                 repeat_until=date(2026, 4, 30))
        occ = ag.occurrences(r, date(2026, 2, 1), date(2026, 4, 30))
        assert occ == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]

    def test_non_repeat_di_luar_rentang_kosong(self):
        r = _row(agenda_date=date(2026, 11, 19))
        assert ag.occurrences(r, date(2026, 12, 1), date(2026, 12, 31)) == []
        assert ag.occurrences(r, date(2026, 11, 1), date(2026, 11, 30)) == [date(2026, 11, 19)]

    def test_repeat_until_membatasi(self):
        r = _row(agenda_date=date(2026, 11, 2), repeat_rule='weekly',
                 repeat_until=date(2026, 11, 20))
        occ = ag.occurrences(r, date(2026, 11, 1), date(2026, 12, 31))
        assert occ == [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16)]


# ---------------------------------------------------------------------------
# Visibilitas & cabang
# ---------------------------------------------------------------------------
class TestVisibility:
    def test_scheduled_belum_tayang(self):
        r = _row(publish_mode='scheduled', publish_at=datetime(2026, 11, 19, 10, 0))
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 9, 0)) is False
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 10, 0)) is True

    def test_scheduled_sudah_berakhir(self):
        r = _row(publish_mode='scheduled', publish_at=datetime(2026, 11, 19, 8, 0),
                 end_at=datetime(2026, 11, 19, 9, 0))
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 9, 1)) is False

    def test_audiens_marketing(self):
        r = _row(audience='marketing')
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 8),
                             role='marketing') is True
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 8),
                             role='finance') is False
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 8),
                             audience_filter='marketing') is True

    def test_audiens_roles(self):
        r = _row(audience='roles', audience_roles='finance,ga')
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 8),
                             role='ga') is True
        assert ag.is_visible(r, date(2026, 11, 19), now=datetime(2026, 11, 19, 8),
                             role='driver') is False

    def test_content_creator_cabang_sendiri(self, monkeypatch):
        with _Session('content_creator', 'content_sby', 'SBY'):
            code, errs = ag.branch_for_write('content_creator', 'SBY')
            assert errs == [] and code == 'SBY'
            code, errs = ag.branch_for_write('content_creator', 'BDG')
            assert code is None and errs

    def test_admin_cabang_scope(self, monkeypatch):
        monkeypatch.setattr(admin_scope, 'is_ho_admin', lambda conn=None: False)
        monkeypatch.setattr(admin_scope, 'admin_managed_branches', lambda conn=None: [])
        with _Session('admin', 'admin_bdg', 'BDG'):
            assert ag.branch_for_write('admin', 'BDG')[0] == 'BDG'
            assert ag.branch_for_write('admin', 'SBY')[1]

    def test_role_lain_tidak_boleh_tulis(self):
        with _Session('marketing', 'marketing_sby', 'SBY'):
            code, errs = ag.branch_for_write('marketing', 'SBY')
            assert code is None and errs


# ---------------------------------------------------------------------------
# Fan-out batch
# ---------------------------------------------------------------------------
class TestFanOut:
    def test_content_creator_tidak_boleh_semua_cabang(self):
        with _Session('content_creator', 'content_sby', 'SBY'):
            items, errors = ag.create_items(
                {'date': '2026-11-19', 'title': 'Rapat', 'scope': 'all'},
                'content_sby', 'content_creator')
            assert items == [] and errors

    def test_admin_cabang_tidak_boleh_semua_cabang(self, monkeypatch):
        monkeypatch.setattr(admin_scope, 'is_ho_admin', lambda conn=None: False)
        with _Session('admin', 'admin_sby', 'SBY'):
            items, errors = ag.create_items(
                {'date': '2026-11-19', 'title': 'Rapat', 'scope': 'all'},
                'admin_sby', 'admin')
            assert items == [] and errors

    def test_admin_master_fan_out_semua_cabang(self, monkeypatch):
        conns = []

        def fake_conn(branch_code=None, master=False):
            c = FakeConn()
            conns.append((branch_code, c))
            return c

        monkeypatch.setattr(ag, 'get_db_connection', fake_conn)
        monkeypatch.setattr(ag, 'active_branch_codes', lambda: ['SBY', 'BDG', 'MLG'])
        monkeypatch.setattr(ag, 'log_activity_async', lambda *a, **k: None)
        monkeypatch.setattr(admin_scope, 'is_ho_admin', lambda conn=None: True)

        with _Session('admin', 'admin', 'SBY'):
            items, errors = ag.create_items(
                {'date': '2026-11-19', 'title': 'Rapat Pusat', 'scope': 'all'},
                'admin', 'admin')
        assert errors == []
        assert len(items) == 3
        assert {i['batch_id'] for i in items} and len({i['batch_id'] for i in items}) == 1
        assert [c[0] for c in conns] == ['SBY', 'BDG', 'MLG']

    def test_satu_cabang_tanpa_batch(self, monkeypatch):
        monkeypatch.setattr(ag, 'get_db_connection', lambda branch_code=None, master=False: FakeConn())
        monkeypatch.setattr(ag, 'log_activity_async', lambda *a, **k: None)
        with _Session('content_creator', 'content_sby', 'SBY'):
            items, errors = ag.create_items(
                {'date': '2026-11-19', 'title': 'Rapat Cabang'},
                'content_sby', 'content_creator')
        assert errors == [] and len(items) == 1
        assert items[0]['batch_id'] is None


# ---------------------------------------------------------------------------
# Dedupe & bridge
# ---------------------------------------------------------------------------
class TestBridge:
    def test_visible_items_dedupe_batch_lintas_cabang(self, monkeypatch):
        rows = {
            'SBY': [_row(id=1, batch_id='b1', branch_code='SBY')],
            'BDG': [_row(id=2, batch_id='b1', branch_code='BDG')],
        }
        monkeypatch.setattr(ag, 'get_db_connection',
                            lambda branch_code=None, master=False: FakeConn(rows.get(branch_code, [])))
        out = ag.visible_items(['SBY', 'BDG'], date(2026, 11, 1),
                               date(2026, 11, 30), merge_batches=True,
                               now=datetime(2026, 11, 19, 8))
        assert len(out) == 1
        assert out[0]['branches'] == ['SBY', 'BDG']

    def test_bridge_state_shape(self, monkeypatch):
        rows = [_row(id=1, media_url='https://x.test/foto.jpg')]
        monkeypatch.setattr(ag, 'get_db_connection',
                            lambda branch_code=None, master=False: FakeConn(rows))
        monkeypatch.setattr(ag, 'active_branch_codes', lambda: ['SBY'])
        data = ag.bridge_state(day='2026-11-19', audience='all',
                               now=datetime(2026, 11, 19, 8))
        assert data['date'] == '2026-11-19'
        assert data['items'][0]['media']['kind'] == 'image'
        assert {'date', 'now', 'audience', 'items', 'ok', 'server_time'} <= set(data)

    def test_bridge_month_dates(self, monkeypatch):
        rows = [_row(id=1), _row(id=2, title='Kedua')]
        monkeypatch.setattr(ag, 'get_db_connection',
                            lambda branch_code=None, master=False: FakeConn(rows))
        monkeypatch.setattr(ag, 'active_branch_codes', lambda: ['SBY'])
        data = ag.bridge_month(month='2026-11')
        assert data['ok'] is True
        assert data['dates'] == [{'date': '2026-11-19', 'count': 2}]

    def test_ics(self, monkeypatch):
        monkeypatch.setattr(ag, 'get_db_connection',
                            lambda branch_code=None, master=False: FakeConn([_row()]))
        body = ag.build_ics(['SBY'], '2026-11')
        assert 'BEGIN:VCALENDAR' in body
        assert 'DTSTART;VALUE=DATE:20261119' in body
        assert 'SUMMARY:Rapat' in body
        assert body.endswith('END:VCALENDAR\r\n')


# ---------------------------------------------------------------------------
# Route: akses & step-up
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    ra.register_agenda_routes(app)
    # Default aman: bukan HO, tanpa cabang tambahan; tes menimpanya sendiri.
    monkeypatch.setattr(ra, 'is_ho_admin', lambda conn=None: False)
    monkeypatch.setattr(ra, 'admin_branches', lambda conn=None: (['SBY'], False))
    return app.test_client()


def _login(client, role='admin', username='admin_sby', branch='SBY'):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = branch


class TestRoutes:
    def test_role_lain_tidak_boleh_tulis(self, client):
        _login(client, 'marketing', 'marketing_sby', 'SBY')
        r = client.post('/api/admin/agenda/items',
                        json={'date': '2026-11-19', 'title': 'Rapat'})
        assert r.status_code == 403

    def test_content_creator_cabang_lain_ditolak(self, client):
        _login(client, 'content_creator', 'content_sby', 'SBY')
        r = client.post('/api/admin/agenda/items',
                        json={'date': '2026-11-19', 'title': 'Rapat',
                              'branch_code': 'BDG'})
        assert r.status_code == 400

    def test_content_creator_cabang_sendiri_ok(self, client, monkeypatch):
        seen = {}

        def fake_create(payload, actor, role, requested_branch=None,
                        legacy_id=None):
            seen.update(payload=payload, actor=actor, role=role,
                        requested=requested_branch)
            return [{'id': 1, 'title': payload['title']}], []

        monkeypatch.setattr(ra.ag, 'create_items', fake_create)
        _login(client, 'content_creator', 'content_sby', 'SBY')
        r = client.post('/api/admin/agenda/items',
                        json={'date': '2026-11-19', 'title': 'Rapat',
                              'branch_code': 'SBY'})
        assert r.status_code == 200
        assert r.get_json()['items'][0]['title'] == 'Rapat'
        assert seen['role'] == 'content_creator'

    def test_delete_perlu_stepup(self, client, monkeypatch):
        monkeypatch.setattr(stepup, 'stepup_expiry', lambda: 0)
        _login(client, 'admin', 'admin_sby', 'SBY')
        r = client.delete('/api/admin/agenda/items/1', json={})
        assert r.status_code == 428
        assert r.get_json()['code'] == 'STEPUP_REQUIRED'

    def test_delete_setelah_stepup(self, client, monkeypatch):
        monkeypatch.setattr(stepup, 'stepup_expiry', lambda: 120)
        monkeypatch.setattr(ra.ag, 'delete_items', lambda *a, **k: (1, []))
        _login(client, 'admin', 'admin_sby', 'SBY')
        r = client.delete('/api/admin/agenda/items/1', json={})
        assert r.status_code == 200
        assert r.get_json()['deleted'] == 1

    def test_coverage_hanya_admin_master(self, client):
        _login(client, 'admin', 'admin_sby', 'SBY')
        r = client.get('/api/admin/agenda/coverage?month=2026-11')
        assert r.status_code == 403

    def test_bridge_publik(self, client, monkeypatch):
        monkeypatch.setattr(ra.ag, 'bridge_state',
                            lambda **k: {'date': '2026-11-19', 'now': 'x',
                                         'audience': 'all', 'items': []})
        r = client.get('/api/state?date=2026-11-19')
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-11-19'

    def test_bridge_logo_tersedia(self, client):
        # Aplikasi Cordova lama memuat ${API_BASE}/assets/logo.png.
        r = client.get('/assets/logo.png')
        assert r.status_code == 200
        assert r.mimetype == 'image/png'

    def test_upload_tolak_ekstensi_berbahaya(self, client):
        _login(client, 'content_creator', 'content_sby', 'SBY')
        r = client.post('/api/admin/agenda/upload', data=b'<script>',
                        headers={'X-Filename': 'x.html',
                                 'Content-Type': 'application/octet-stream'})
        assert r.status_code == 400

    def test_upload_media_ok(self, client):
        _login(client, 'content_creator', 'content_sby', 'SBY')
        r = client.post('/api/admin/agenda/upload', data=b'\x89PNG',
                        headers={'X-Filename': 'foto.png',
                                 'Content-Type': 'application/octet-stream'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['url'].startswith('/assets/up/agenda_')
        assert body['media_type'] == 'image'
        name = body['filename']
        try:
            os.remove(os.path.join(ra.MEDIA_DIR, name))
        except OSError:
            pass


def test_bridge_cors_untuk_webview(client):
    """Bridge dipanggil dari https://localhost (WebView) — wajib ada ACAO."""
    pre = client.options('/api/state')
    assert pre.status_code == 204
    assert pre.headers['Access-Control-Allow-Origin'] == '*'

    r = client.get('/api/state')
    assert r.headers['Access-Control-Allow-Origin'] == '*'
    assert 'Range' in r.headers['Access-Control-Allow-Headers']
