"""Unit tests — Receptionist v2.42.0: In-Out Karyawan full CRUD + registrasi karyawan.

Cakupan:
- _inout_mode: default hybrid, config sheet/hybrid, DB mati → default
- _do_sync_inout: guard sheet rusak, full-replace hanya baris sheet,
  catatan app/registrasi/locked dipertahankan
- POST /api/receptionist/inout: catat keluar (baris baru), masuk menutup
  baris keluar terbuka, duplikat keluar 409, mode sheet 403
- PATCH/DELETE: catatan sheet ditolak 409, step-up 428, sukses + audit
- register-employee: lulus → status lulus + baris in-out terkunci, 409
  pelamar sudah lulus, duplikat baris keluar terbuka dipakai
- inout-mode: admin boleh set, receptionist 403, nilai invalid 400
- Audit trail: setiap peristiwa masuk employee_inout_events
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

import modules.routes_receptionist as rr  # noqa: E402


# ============================================================
# Fake DB
# ============================================================
class FakeCursor:
    """Cursor fake employee_inout + events + system_config."""

    def __init__(self, conn, dictionary=True):
        self.conn = conn
        self.dictionary = dictionary
        self._rows = []
        self.rowcount = 0
        self.lastrowid = 0

    def _as_row(self, r):
        if self.dictionary:
            return dict(r)
        return tuple(r[c] for c in self.conn.cols)

    def execute(self, sql, params=None):
        c = self.conn
        low = ' '.join(sql.split()).lower()
        self._rows = []
        self.rowcount = 0
        p = params or ()

        if low.startswith('select config_value from system_config'):
            row = c.config.get(p[0])
            self._rows = [{'config_value': row}] if row is not None else []
        if low.startswith('select id from employee_inout where nama='):
            nama, day = p[0], p[1]
            for r in c.inout_rows:
                wp = r['waktu_pergi']
                wp_day = (wp.isoformat() if hasattr(wp, 'isoformat') else str(wp or ''))[:10]
                if (r['nama'] == nama and r['pergi'] == 1 and r['datang'] == 0
                        and wp_day == day):
                    self._rows = [{'id': r['id']}]
                    break
        elif low.startswith('select * from employee_inout where id='):
            for r in c.inout_rows:
                if r['id'] == p[0]:
                    self._rows = [dict(r)]
                    break
        elif low.startswith('select nama from employee_inout'):
            self._rows = [{'nama': r['nama']} for r in c.inout_rows
                          if r['pergi'] == 1 and r['datang'] == 0]
        elif low.startswith('select id from employee_inout where source in'):
            # Pencocokan konten utk push webhook (nama+keterangan+waktu).
            nama, ket, wp, wp2, wd, wd2 = p
            for r in c.inout_rows:
                rwp = r['waktu_pergi']
                rwp_s = rwp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(rwp, 'strftime') else rwp
                rwd = r['waktu_datang']
                rwd_s = rwd.strftime('%Y-%m-%d %H:%M:%S') if hasattr(rwd, 'strftime') else rwd
                if (r['nama'] == nama and (r['keterangan'] or '') == ket
                        and (rwp_s or None) == (wp or None)
                        and (rwd_s or None) == (wd or None)):
                    self._rows = [{'id': r['id']}]
                    break
        elif low.startswith('select trim(nama)'):
            seen = {}
            for r in c.inout_rows:
                if r['nama']:
                    seen.setdefault(r['nama'], {'nama': r['nama'], 'jabatan': r['jabatan'],
                                                'terakhir_aktif': None})
            self._rows = list(seen.values())
        elif low.startswith('insert into employee_inout_events'):
            c.events.append(p)
            self.rowcount = 1
        elif low.startswith('insert into employee_inout') and 'select ' in low:
            # INSERT INTO employee_inout ... SELECT ... FROM stage
            self.rowcount = len(c.staged)
        elif low.startswith('insert ignore into employee_inout_stage') or \
                low.startswith('insert into employee_inout_stage'):
            c.staged.append(p)
            self.rowcount = 1
        elif low.startswith('delete from employee_inout_stage'):
            c.staged = []
            self.rowcount = 0
        elif low.startswith('select count(*) from employee_inout'):
            n = sum(1 for r in c.inout_rows if r['source'] != 'sheet' or r['locked'])
            self._rows = [(n,)]
        elif low.startswith('insert into employee_inout'):
            c.insert_counter += 1
            row = {
                'id': c.insert_counter, 'source_uid': p[0], 'nama': p[1],
                'jabatan': p[2], 'pergi': p[3], 'waktu_pergi': p[4] if len(p) > 4 else None,
                'datang': p[5] if len(p) > 5 else 0, 'waktu_datang': None,
                'keterangan': p[6] if len(p) > 6 else '', 'source': 'app',
                'locked': 1, 'created_by': '', 'updated_by': '', 'created_at': None,
                'updated_at': None, 'applicant_id': None,
            }
            # Peta argumen varian INSERT berbeda-beda — isi dari dict pengujian.
            row.update(c.next_insert_fields or {})
            c.inout_rows.append(row)
            c.next_insert_fields = None
            self.rowcount = 1
            self.lastrowid = row['id']
            c.last_insert_id = row['id']
        elif low.startswith('update employee_inout set datang=1'):
            # UPDATE ... SET datang=1, waktu_datang=%s, ... WHERE id=%s
            for r in c.inout_rows:
                if r['id'] == p[-1]:
                    r['datang'] = 1
                    r['waktu_datang'] = p[0]
                    self.rowcount = 1
        elif low.startswith('update employee_inout set nama='):
            # UPDATE hasil push webhook: 7 kolom + id di posisi terakhir.
            if len(p) == 8:
                for r in c.inout_rows:
                    if r['id'] == p[-1]:
                        (r['nama'], r['jabatan'], r['pergi'], r['waktu_pergi'],
                         r['datang'], r['waktu_datang'], r['keterangan']) = p[:7]
                        self.rowcount = 1
        elif low.startswith('update employee_inout'):
            self.rowcount = 1
            c.updated = list(p)
        elif low.startswith('delete from employee_inout where id=') or \
                low.startswith('delete from employee_inout where source='):
            self.rowcount = 1
            c.deleted.append(p)
        elif low.startswith('insert into system_config'):
            c.config[p[0]] = p[1]
            self.rowcount = 1
        elif low.startswith('select * from applicants where id='):
            appt = c.applicants.get(p[0])
            self._rows = [dict(appt)] if appt else []
        elif low.startswith('update applicants set status=' + "'lulus'"):
            c.lulus.append(p[0])
            self.rowcount = 1
        else:
            self.rowcount = 0
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConn:
    cols = ('id',)

    def __init__(self, inout_rows=None, config=None, applicants=None):
        self.inout_rows = inout_rows or []
        self.config = config or {}
        self.applicants = applicants or {}
        self.events = []
        self.staged = []
        self.deleted = []
        self.updated = None
        self.lulus = []
        self.insert_counter = 100
        self.last_insert_id = None
        self.next_insert_fields = None
        self.commits = 0
        self.closed = False

    def cursor(self, dictionary=True):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _mk_app(monkeypatch, conn=None, mode='hybrid', role='receptionist'):
    monkeypatch.setattr(rr, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(rr, '_inout_mode', lambda conn=None: mode)
    if conn is not None:
        monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    rr.register_receptionist_routes(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = 'receptionist_sby'
        s['full_name'] = 'Resepsionis SBY'
        s['stepup_until'] = 9_999_999_999
        s['csrf_token'] = 'x'
    return client


def _with_conn(monkeypatch, conn):
    monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
    return conn


# ============================================================
# _inout_mode
# ============================================================
class TestInOutMode:
    def test_default_hybrid_tanpa_db(self, monkeypatch):
        monkeypatch.setattr(rr, 'get_db_connection', lambda: None)
        assert rr._inout_mode() == 'hybrid'

    def test_mode_dari_config(self):
        assert rr._inout_mode(FakeConn(config={rr.INOUT_MODE_CONFIG_KEY: 'sheet'})) == 'sheet'

    def test_mode_invalid_fallback_hybrid(self):
        conn = FakeConn(config={rr.INOUT_MODE_CONFIG_KEY: 'gaib'})
        assert rr._inout_mode(conn) == 'hybrid'


# ============================================================
# Sync in-out: guard + preservasi data app
# ============================================================
def _sheet_row(nama='BUDI', pergi='TRUE', wp='9/14/2026 6:53:19 AM'):
    return {'Nama Karyawan': nama, 'Jabatan/Posisi': 'OB', 'Pergi': pergi,
            'Waktu Pergi': wp, 'Datang': 'FALSE', 'Waktu Datang': '', 'Keterangan': 'survei'}


class TestSyncInOutGuard:
    def test_sheet_kosong_tidak_menghapus_catatan_app(self, monkeypatch):
        conn = FakeConn(inout_rows=[{
            'id': 1, 'source_uid': 'io-app-x', 'nama': 'SITI', 'jabatan': 'STAFF',
            'pergi': 1, 'waktu_pergi': datetime(2026, 9, 20, 8, 0), 'datang': 0,
            'waktu_datang': None, 'keterangan': '', 'source': 'app', 'locked': 1,
            'created_by': 'r', 'updated_by': '', 'created_at': None, 'updated_at': None,
            'applicant_id': None,
        }])
        monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(rr, '_get_sheet_url', lambda conn, modul='inout': 'http://x')
        monkeypatch.setattr(rr, '_fetch_sheet_rows', lambda url: [])
        # sheet kosong + ada baris → rows=0 → guard tidak aktif → full replace
        result = rr._do_sync_inout()
        assert result['preserved'] == 1
        assert conn.deleted  # hanya DELETE baris sheet

    def test_sheet_rusak_sync_dibatalkan(self, monkeypatch):
        conn = FakeConn()
        monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(rr, '_get_sheet_url', lambda conn, modul='inout': 'http://x')
        # 4 baris, hanya 1 valid → < 50% → ValueError
        bad = [{'Kolom Asing': 'x'}] * 3 + [_sheet_row()]
        monkeypatch.setattr(rr, '_fetch_sheet_rows', lambda url: bad)
        try:
            rr._do_sync_inout()
            assert False, 'harusnya ValueError'
        except ValueError as e:
            assert 'tidak wajar' in str(e)

    def test_valid_sheet_tersinkron(self, monkeypatch):
        conn = FakeConn(inout_rows=[{
            'id': 2, 'source_uid': 'io-app-y', 'nama': 'SITI', 'jabatan': '', 'pergi': 0,
            'waktu_pergi': None, 'datang': 0, 'waktu_datang': None, 'keterangan': '',
            'source': 'registrasi', 'locked': 1, 'created_by': '', 'updated_by': '',
            'created_at': None, 'updated_at': None, 'applicant_id': 7,
        }])
        monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
        monkeypatch.setattr(rr, '_get_sheet_url', lambda conn, modul='inout': 'http://x')
        monkeypatch.setattr(rr, '_fetch_sheet_rows', lambda url: [_sheet_row()])
        result = rr._do_sync_inout()
        assert result['replaced'] >= 0
        assert result['preserved'] == 1


# ============================================================
# Catat keluar / masuk dari aplikasi
# ============================================================
class TestCatatInOut:
    def test_mode_sheet_ditolak_403(self, monkeypatch):
        client = _mk_app(monkeypatch, conn=FakeConn(), mode='sheet')
        r = client.post('/api/receptionist/inout', json={'nama': 'BUDI', 'arah': 'keluar'})
        assert r.status_code == 403

    def test_keluar_baru(self, monkeypatch):
        conn = FakeConn()
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/receptionist/inout',
                        json={'nama': 'BUDI', 'jabatan': 'OB', 'arah': 'keluar',
                              'keterangan': 'survei pasar'})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'
        assert len(conn.inout_rows) == 1
        assert conn.inout_rows[0]['source'] == 'app'
        assert any(ev[1] == 'app_keluar' for ev in conn.events)

    def test_keluar_duplikat_409(self, monkeypatch):
        conn = FakeConn(inout_rows=[{
            'id': 5, 'source_uid': 'io-app-x', 'nama': 'BUDI', 'jabatan': 'OB',
            'pergi': 1, 'waktu_pergi': datetime.now(), 'datang': 0, 'waktu_datang': None,
            'keterangan': '', 'source': 'app', 'locked': 1, 'created_by': '',
            'updated_by': '', 'created_at': None, 'updated_at': None, 'applicant_id': None,
        }])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/receptionist/inout', json={'nama': 'BUDI', 'arah': 'keluar'})
        assert r.status_code == 409

    def test_masuk_menutup_baris_keluar(self, monkeypatch):
        conn = FakeConn(inout_rows=[{
            'id': 5, 'source_uid': 'io-app-x', 'nama': 'BUDI', 'jabatan': 'OB',
            'pergi': 1, 'waktu_pergi': datetime.now(), 'datang': 0, 'waktu_datang': None,
            'keterangan': '', 'source': 'app', 'locked': 1, 'created_by': '',
            'updated_by': '', 'created_at': None, 'updated_at': None, 'applicant_id': None,
        }])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/receptionist/inout', json={'nama': 'BUDI', 'arah': 'masuk'})
        assert r.status_code == 200
        assert conn.inout_rows[0]['datang'] == 1
        assert any(ev[1] == 'app_masuk' for ev in conn.events)

    def test_nama_wajib(self, monkeypatch):
        client = _mk_app(monkeypatch, conn=FakeConn())
        r = client.post('/api/receptionist/inout', json={'nama': '  ', 'arah': 'keluar'})
        assert r.status_code == 400

    def test_arah_invalid(self, monkeypatch):
        client = _mk_app(monkeypatch, conn=FakeConn())
        r = client.post('/api/receptionist/inout', json={'nama': 'BUDI', 'arah': 'melayang'})
        assert r.status_code == 400


# ============================================================
# Edit / hapus
# ============================================================
def _row(nama='BUDI', source='app', locked=1):
    return {'id': 9, 'source_uid': 'io-x', 'nama': nama, 'jabatan': 'OB', 'pergi': 1,
            'waktu_pergi': datetime(2026, 9, 21, 9, 0), 'datang': 0, 'waktu_datang': None,
            'keterangan': 'survei', 'source': source, 'locked': locked,
            'created_by': 'r', 'updated_by': '', 'created_at': None,
            'updated_at': None, 'applicant_id': None}


class TestEditHapus:
    def test_catatan_sheet_tidak_bisa_diedit(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row(source='sheet', locked=0)])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.patch('/api/receptionist/inout/9', json={'keterangan': 'ubah'})
        assert r.status_code == 409

    def test_edit_tanpa_stepup_428(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row()])
        client = _mk_app(monkeypatch, conn=conn)
        with client.session_transaction() as s:
            s.pop('stepup_until', None)
        r = client.patch('/api/receptionist/inout/9', json={'keterangan': 'ubah'})
        assert r.status_code == 428

    def test_edit_sukses(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row()])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.patch('/api/receptionist/inout/9', json={'keterangan': 'antar dokumen'})
        assert r.status_code == 200
        assert any(ev[1] == 'app_edit' for ev in conn.events)

    def test_edit_waktu_invalid_400(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row()])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.patch('/api/receptionist/inout/9', json={'waktu_pergi': 'besok'})
        assert r.status_code == 400

    def test_hapus_catatan_sheet_ditolak(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row(source='sheet', locked=0)])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.delete('/api/receptionist/inout/9')
        assert r.status_code == 409

    def test_hapus_sukses(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row()])
        client = _mk_app(monkeypatch, conn=conn)
        r = client.delete('/api/receptionist/inout/9')
        assert r.status_code == 200
        assert conn.deleted
        assert any(ev[1] == 'app_delete' for ev in conn.events)


# ============================================================
# Registrasi pelamar → karyawan
# ============================================================
class TestRegisterEmployee:
    def _applicants(self, status='training_2'):
        return {3: {'id': 3, 'display_id': 'PLM-0003', 'nama_lengkap': 'YOGA',
                    'status': status, 'posisi': 'STAFF'}}

    def test_sukses_lulus_dan_inout_aktif(self, monkeypatch):
        conn = FakeConn(applicants=self._applicants())
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/applicants/3/register-employee', json={'jabatan': 'STAFF'})
        assert r.status_code == 200
        assert 3 in conn.lulus
        assert any(ev[1] == 'registrasi' for ev in conn.events)
        # baris in-out baru dibuat via INSERT (insert_counter naik)
        assert conn.insert_counter > 100

    def test_sudah_lulus_409(self, monkeypatch):
        conn = FakeConn(applicants=self._applicants('lulus'))
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/applicants/3/register-employee', json={'jabatan': 'STAFF'})
        assert r.status_code == 409

    def test_rejected_ditolak(self, monkeypatch):
        conn = FakeConn(applicants=self._applicants('rejected'))
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/applicants/3/register-employee', json={'jabatan': 'STAFF'})
        assert r.status_code == 409

    def test_pelamar_tidak_ada_404(self, monkeypatch):
        conn = FakeConn(applicants={})
        client = _mk_app(monkeypatch, conn=conn)
        r = client.post('/api/applicants/999/register-employee', json={'jabatan': ''})
        assert r.status_code == 404


# ============================================================
# Mode endpoint (admin-only)
# ============================================================
class TestModeEndpoint:
    def test_get_mode(self, monkeypatch):
        conn = FakeConn(config={rr.INOUT_MODE_CONFIG_KEY: 'hybrid'})
        client = _mk_app(monkeypatch, conn=conn)
        r = client.get('/api/receptionist/inout-mode')
        assert r.status_code == 200
        assert r.get_json()['mode'] == 'hybrid'

    def test_set_mode_admin(self, monkeypatch):
        conn = FakeConn()
        client = _mk_app(monkeypatch, conn=conn, role='admin')
        r = client.post('/api/receptionist/inout-mode', json={'mode': 'sheet'})
        assert r.status_code == 200
        assert conn.config[rr.INOUT_MODE_CONFIG_KEY] == 'sheet'

    def test_set_mode_receptionist_403(self, monkeypatch):
        conn = FakeConn()
        client = _mk_app(monkeypatch, conn=conn, role='receptionist')
        r = client.post('/api/receptionist/inout-mode', json={'mode': 'sheet'})
        assert r.status_code == 403

    def test_set_mode_invalid_400(self, monkeypatch):
        conn = FakeConn()
        client = _mk_app(monkeypatch, conn=conn, role='admin')
        r = client.post('/api/receptionist/inout-mode', json={'mode': 'gaib'})
        assert r.status_code == 400


# ============================================================
# PDF laporan harian in-out
# ============================================================
class TestInOutPDF:
    def test_pdf_kosong_dan_terisi(self):
        from modules.pdf_generator import InOutReportPDF
        rows = [{
            'nama': 'BUDI', 'jabatan': 'OB', 'pergi': 1,
            'waktu_pergi': datetime(2026, 9, 21, 9, 0), 'datang': 0,
            'waktu_datang': None, 'keterangan': 'survei', 'source': 'app',
        }]
        pdf = InOutReportPDF()
        pdf.generate(rows, report_date=datetime(2026, 9, 21).date(), generated_by='Resepsionis')
        import io
        buf = io.BytesIO()
        pdf.output(buf)
        data = buf.getvalue()
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        from tests.pdf_text import _pdf_text
        txt = _pdf_text(data)
        assert 'BUDI' in txt.upper()
        assert 'RECEPTIONIST' in txt.upper()


# ============================================================
# Webhook push realtime (v2.42.0) — Apps Script onEdit → app
# ============================================================
class TestWebhook:
    def _mk(self, monkeypatch, conn, secret='rahasia-webhook'):
        monkeypatch.setattr(rr, 'log_activity_async', lambda *a, **k: None)
        monkeypatch.setattr(rr, '_verify_webhook_secret',
                            lambda tok: tok == secret)
        monkeypatch.setattr(rr, 'get_db_connection', lambda: conn)
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        rr.register_receptionist_routes(app)
        return app.test_client()

    def test_token_salah_401(self, monkeypatch):
        client = self._mk(monkeypatch, FakeConn(), secret='benar')
        r = client.post('/api/receptionist/webhook', json={'modul': 'inout', 'rows': [{}]},
                        headers={'X-BPF-Token': 'salah'})
        assert r.status_code == 401

    def test_rows_kosong_400(self, monkeypatch):
        client = self._mk(monkeypatch, FakeConn())
        r = client.post('/api/receptionist/webhook', json={'modul': 'inout', 'rows': []},
                        headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 400

    def test_push_baris_baru_masuk(self, monkeypatch):
        conn = FakeConn()
        client = self._mk(monkeypatch, conn)
        r = client.post('/api/receptionist/webhook', json={
            'modul': 'inout',
            'rows': [{'Nama': 'BUDI', 'Jabatan/Posisi': 'OB', 'Pergi': 'TRUE',
                      'Waktu Pergi': '9/23/2026 8:15:00 AM', 'Datang': 'FALSE',
                      'Waktu Datang': '', 'Keterangan': 'kirim dokumen'}],
        }, headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['added'] == 1
        assert any(x['source_uid'].startswith('io-push-') for x in conn.inout_rows)

    def test_push_edit_tak_menciptakan_duplikat(self, monkeypatch):
        conn = FakeConn(inout_rows=[_row()])  # BUDI, survei, 09:00
        client = self._mk(monkeypatch, conn)
        r = client.post('/api/receptionist/webhook', json={
            'modul': 'inout',
            'rows': [{'Nama': 'BUDI', 'Jabatan/Posisi': 'SECURITY', 'Pergi': 'TRUE',
                      'Waktu Pergi': '9/21/2026 9:00:00 AM', 'Datang': 'FALSE',
                      'Waktu Datang': '', 'Keterangan': 'survei'}],
        }, headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['updated'] == 1
        assert body['added'] == 0
        assert len(conn.inout_rows) == 1
        assert conn.inout_rows[0]['jabatan'] == 'SECURITY'

    def test_push_pelamar_baru(self, monkeypatch):
        conn = FakeConn()
        client = self._mk(monkeypatch, conn)
        r = client.post('/api/receptionist/webhook', json={
            'modul': 'applicants',
            'rows': [{'Tanggal Interview': '9/23/2026', 'Jam': '9:00:00 AM',
                      'Nama Lengkap': 'ANDI', 'Pendidikan Terakhir': 'SMA',
                      'Nomor Telepon/HP': '0812', 'UPLINE': 'BELA',
                      'User': 'TEAM A', 'Posisi Yang Dilamar': 'STAFF'}],
        }, headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['added'] == 1

    def test_header_changed_200_dan_resync_penuh(self, monkeypatch):
        """v2.42.0: rows kosong + header_changed → 200 (bukan 400) dan
        sinkron penuh kedua modul dijadwalkan di background."""
        calls = []
        monkeypatch.setattr(rr, '_do_sync_both', lambda: (calls.append(1) or
                                                          {'applicants': {'summary': 'ok'},
                                                           'inout': {'summary': 'ok'}}))
        events = []
        monkeypatch.setattr(rr, 'emit_event', lambda *a, **k: events.append(a))
        client = self._mk(monkeypatch, FakeConn())
        r = client.post('/api/receptionist/webhook', json={
            'modul': 'inout', 'rows': [], 'header_changed': True,
        }, headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['status'] == 'success'
        assert body['header_changed'] is True
        assert events and 'Header' in events[0][1]['summary']
        deadline = time.time() + 2
        while not calls and time.time() < deadline:
            time.sleep(0.01)
        assert calls, 'resync penuh tidak dijadwalkan di background'

    def test_rows_kosong_tanpa_header_changed_tetap_400(self, monkeypatch):
        """Guard: rows kosong TANPA tanda header_changed tetap ditolak 400."""
        client = self._mk(monkeypatch, FakeConn())
        r = client.post('/api/receptionist/webhook', json={'modul': 'inout'},
                        headers={'X-BPF-Token': 'rahasia-webhook'})
        assert r.status_code == 400
