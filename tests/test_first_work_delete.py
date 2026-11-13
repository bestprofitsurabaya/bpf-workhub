"""Hapus data uji FirstWork (v2.108.2).

Regresi yang dijaga:

1. Sebelum v2.108.2 **tidak ada jalur hapus sama sekali** — satu kiriman uji
   ("UJI COBA") menetap selamanya dan hanya bisa dibuang lewat SQL manual,
   padahal traineer yang menjalankan gladi resik justru yang membuatnya.
2. Hapus wajib konfirmasi eksplisit `{"confirm": "HAPUS"}` -> 400 tanpa itu.
3. Traineer hanya boleh menghapus data cabangnya yang **belum final**
   (`submitted`/`rejected`). Data `verified` adalah arsip resmi -> 403.
4. Admin cabang tidak bisa menghapus data cabang lain; Admin Pusat (HO, baik
   lewat nama `admin_master` maupun flag `admin_all_branches=1`) bisa.
5. File KTP ikut dihapus dari disk, tetapi hanya di dalam `UPLOAD_DIR`.
6. Jejak audit ditulis dengan PII tersamarkan (NIK/HP bukan nilai mentah).
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, session  # noqa: E402

from modules import routes_first_work as fw  # noqa: E402


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        q = re.sub(r'\s+', ' ', sql).strip().upper()
        params = tuple(params or ())
        self._rows = []
        self.rowcount = 0
        if q.startswith('SELECT * FROM FIRST_WORK_SUBMISSIONS WHERE ID='):
            row = self.conn.rows.get(params[0])
            self._rows = [dict(row)] if row else []
        elif q.startswith('DELETE FROM FIRST_WORK_SUBMISSIONS WHERE ID='):
            row = self.conn.rows.pop(params[0], None)
            self.rowcount = 1 if row else 0
        elif 'FROM USERS' in q:
            self._rows = [{'admin_all_branches': self.conn.ho_flag,
                           'managed_branches': ''}]
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows=None, ho_flag=0):
        self.rows = {int(r['id']): dict(r) for r in (rows or [])}
        self.ho_flag = ho_flag
        self.commits = 0
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


APP = Flask(__name__)
APP.secret_key = 'uji-hapus'
fw.register_first_work_routes(APP)


def _row(**over):
    base = {
        'id': 1849,
        'registration_no': 'FW-20261113-0001',
        'nama': 'UJI COBA',
        'nik': '3578010101010001',
        'no_hp': '081234567890',
        'branch_code': 'SBY',
        'status': 'submitted',
        'source': 'form',
        'ktp_file': 'ktp_uji.jpg',
        'ktp_scan_file': 'ktp_uji_scan.jpg',
    }
    base.update(over)
    return base


def _client(monkeypatch, conn, role='traineer', username='traineer_sby',
            branch='SBY'):
    logs = []

    def fake_log(*args, **kwargs):
        logs.append({'args': args, 'kwargs': kwargs})
        return None

    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', fake_log)
    client = APP.test_client()
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = username
        s['branch_code'] = branch
        s['full_name'] = 'Uji Hapus'
    return client, logs


def _delete(client, sub_id=1849, body=None):
    return client.delete(f'/api/first-work/{sub_id}',
                         json=body if body is not None else {'confirm': 'HAPUS'})


# ================================================================
# Konfirmasi & keberadaan data
# ================================================================
class TestConfirmation:
    def test_tanpa_konfirmasi_ditolak_400(self, monkeypatch):
        conn = FakeConn([_row()])
        client, _ = _client(monkeypatch, conn)
        rv = client.delete('/api/first-work/1849', json={})
        assert rv.status_code == 400
        assert 1849 in conn.rows, 'data tidak boleh terhapus tanpa konfirmasi'

    def test_konfirmasi_salah_ditolak_400(self, monkeypatch):
        conn = FakeConn([_row()])
        client, _ = _client(monkeypatch, conn)
        rv = _delete(client, body={'confirm': 'hapus semua'})
        assert rv.status_code == 400
        assert 1849 in conn.rows

    def test_data_tidak_ada_404(self, monkeypatch):
        client, _ = _client(monkeypatch, FakeConn([]))
        rv = _delete(client, sub_id=999)
        assert rv.status_code == 404


# ================================================================
# Traineer
# ================================================================
class TestTraineer:
    def test_traineer_hapus_data_uji_cabangnya(self, monkeypatch):
        """Kasus nyata: "UJI COBA" status submitted di SBY."""
        conn = FakeConn([_row()])
        client, logs = _client(monkeypatch, conn)
        rv = _delete(client)
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'success'
        assert 1849 not in conn.rows
        assert conn.commits == 1
        assert logs and logs[0]['args'][1] == 'first_work_delete'

    def test_traineer_hapus_rejected_boleh(self, monkeypatch):
        conn = FakeConn([_row(status='rejected')])
        client, _ = _client(monkeypatch, conn)
        assert _delete(client).status_code == 200

    def test_traineer_tidak_bisa_hapus_verified(self, monkeypatch):
        """Data terverifikasi = arsip resmi; traineer tidak boleh menghapus."""
        conn = FakeConn([_row(status='verified')])
        client, _ = _client(monkeypatch, conn)
        rv = _delete(client)
        assert rv.status_code == 403
        assert 1849 in conn.rows

    def test_traineer_tidak_bisa_hapus_cabang_lain(self, monkeypatch):
        conn = FakeConn([_row(branch_code='MLG')])
        client, _ = _client(monkeypatch, conn, branch='SBY')
        rv = _delete(client)
        assert rv.status_code == 403
        assert 1849 in conn.rows

    def test_sesi_tanpa_cabang_fail_closed(self, monkeypatch):
        conn = FakeConn([_row()])
        client, _ = _client(monkeypatch, conn, branch='')
        rv = _delete(client)
        assert rv.status_code == 403


# ================================================================
# Admin
# ================================================================
class TestAdmin:
    def test_admin_cabang_hapus_verified_boleh(self, monkeypatch):
        conn = FakeConn([_row(status='verified')])
        client, _ = _client(monkeypatch, conn, role='admin',
                            username='admin_sby', branch='SBY')
        assert _delete(client).status_code == 200
        assert 1849 not in conn.rows

    def test_admin_cabang_tidak_bisa_hapus_cabang_lain(self, monkeypatch):
        conn = FakeConn([_row(branch_code='MLG')])
        client, _ = _client(monkeypatch, conn, role='admin',
                            username='admin_sby', branch='SBY')
        rv = _delete(client)
        assert rv.status_code == 403

    def test_admin_master_bisa_semua_cabang(self, monkeypatch):
        """admin_master = Admin Pusat (nama legacy)."""
        conn = FakeConn([_row(branch_code='MLG')])
        client, _ = _client(monkeypatch, conn, role='admin',
                            username='admin_master', branch='SBY')
        assert _delete(client).status_code == 200
        assert 1849 not in conn.rows

    def test_admin_ho_lewat_flag_bisa_semua_cabang(self, monkeypatch):
        """Admin Pusat yang dipromosikan lewat flag admin_all_branches=1."""
        conn = FakeConn([_row(branch_code='BJM')], ho_flag=1)
        client, _ = _client(monkeypatch, conn, role='admin',
                            username='admin_bjm', branch='BJM')
        assert _delete(client).status_code == 200


# ================================================================
# File KTP & jejak audit
# ================================================================
class TestFilesAndAudit:
    def test_file_ktp_ikut_dihapus(self, monkeypatch, tmp_path):
        upload = tmp_path / 'first_work'
        upload.mkdir()
        (upload / 'ktp_uji.jpg').write_bytes(b'x')
        (upload / 'ktp_uji_scan.jpg').write_bytes(b'x')
        monkeypatch.setattr(fw, 'UPLOAD_DIR', str(upload))

        conn = FakeConn([_row()])
        client, _ = _client(monkeypatch, conn)
        rv = _delete(client)
        assert rv.status_code == 200
        assert rv.get_json()['files_removed'] == 2
        assert not (upload / 'ktp_uji.jpg').exists()
        assert not (upload / 'ktp_uji_scan.jpg').exists()

    def test_tidak_menghapus_file_di_luar_upload_dir(self, monkeypatch, tmp_path):
        upload = tmp_path / 'first_work'
        upload.mkdir()
        outside = tmp_path / 'penting.txt'
        outside.write_text('jangan dihapus')

        monkeypatch.setattr(fw, 'UPLOAD_DIR', str(upload))
        conn = FakeConn([_row(ktp_file='../../penting.txt', ktp_scan_file='')])
        client, _ = _client(monkeypatch, conn)
        rv = _delete(client)
        assert rv.status_code == 200
        assert outside.exists(), 'path traversal tidak boleh keluar UPLOAD_DIR'

    def test_audit_pii_tersamar(self, monkeypatch):
        conn = FakeConn([_row()])
        client, logs = _client(monkeypatch, conn)
        _delete(client)
        snapshot = logs[0]['kwargs']['old_data']
        assert snapshot['id'] == 1849
        assert snapshot['nama'] == 'UJI COBA'
        assert snapshot['nik'].endswith('0001')
        assert snapshot['nik'] != '3578010101010001'
        assert set(snapshot['nik']) <= set('•0123456789')
        assert snapshot['no_hp'].endswith('7890')
        assert snapshot['no_hp'] != '081234567890'
