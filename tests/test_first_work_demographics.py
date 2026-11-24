"""Rilis B Task 2 — 13 field demografi FirstWork.

Yang diuji:
1. Submit publik tanpa field baru tetap diterima (kolom nullable, kompatibel
   dengan form/baris lama).
2. Submit dengan 13 field demografi tersimpan; nilai di-sanitasi dan tanggal
   dibakukan `YYYY-MM-DD`.
3. Field demografi TIDAK pernah menimpa NIK/nama hasil OCR (sumber NIK/nama
   tetap field `nik`/`nama`, bukan field demografi yang kebetulan berisi angka).
4. Detail/list & ekspor CSV menyertakan 13 field; kebijakan masking NIK
   (traineer penuh, finance tersamar) tidak berubah.
5. Helper skema idempoten menambahkan kolom, dan init.sql memuatnya untuk
   schema drift check CI.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask  # noqa: E402

from modules import routes_first_work as fw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEMOGRAPHICS = (
    'tempat_lahir', 'tanggal_lahir', 'jenis_kelamin', 'golongan_darah',
    'alamat', 'rt_rw', 'kel_desa', 'kecamatan', 'agama',
    'status_perkawinan', 'pekerjaan', 'kewarganegaraan', 'berlaku_hingga',
)

DEMO_VALUES = {
    'tempat_lahir': 'Surabaya',
    'tanggal_lahir': '1995-01-19',
    'jenis_kelamin': 'Laki-laki',
    'golongan_darah': 'O',
    'alamat': 'Jl. Contoh No. 12',
    'rt_rw': '03/04',
    'kel_desa': 'Keputih',
    'kecamatan': 'Sukolilo',
    'agama': 'Islam',
    'status_perkawinan': 'Belum Menikah',
    'pekerjaan': 'Karyawan Swasta',
    'kewarganegaraan': 'WNI',
    'berlaku_hingga': '2030-01-19',
}

_VALID = {
    'nik': '3578010101900001',
    'nama': 'Contoh Pendaftar',
    'pendidikan': 'SMA',
    'no_hp': '081234567890',
    'referensi_text': 'Uji',
    'consent': '1',
}


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self.rows = []
        self.lastrowid = None

    def execute(self, sql, params=None):
        q = re.sub(r'\s+', ' ', sql).strip()
        self.rows = self.conn.answer(q, tuple(params or ()))
        return None

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


class FakeConn:
    """DB master tiruan: cukup untuk submit publik + ekspor CSV."""

    def __init__(self, export_rows=None):
        self.export_rows = list(export_rows or [])
        self.config = json.dumps({'fingerprint_series': 'B', 'bpf_series': 'C'})
        self.counters = {'B': 25000, 'C': 8000}
        self.branch_counters = {}
        self.used_ids = {'fingerprint_no': set(), 'bpf_no': set()}
        self.submissions = []
        self.last_insert_id = 0
        self.lastrowid = 100
        self.commits = 0

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.commits += 1

    def close(self):
        pass

    def answer(self, q, params):
        if 'FROM branches' in q:
            return [{'code': 'SBY', 'name': 'Surabaya', 'city': 'Surabaya'}]
        if 'FROM first_work_branch_forms' in q:
            return [{'branch_code': 'SBY', 'form_token': 'tok-SBY', 'active': 1}]
        if 'FROM system_config' in q:
            return [{'config_value': self.config}]
        if 'FROM first_work_submissions WHERE nik=%s' in q:
            return []
        if 'INSERT INTO doc_sequences' in q:
            self.last_insert_id = 1
            return []
        if 'SELECT LAST_INSERT_ID()' in q:
            return [(self.last_insert_id,)]
        if 'WHERE branch_code=%s AND series=%s' in q:
            branch, series = params
            value = self.branch_counters.get((branch, series))
            return [(value,)] if value is not None else []
        if 'INSERT INTO first_work_branch_counters' in q:
            branch, series = params[:2]
            key = (branch, series)
            if 'LAST_INSERT_ID' in q:
                value = self.branch_counters.get(key, 0) + 1
                self.branch_counters[key] = value
                self.last_insert_id = value
            else:
                self.branch_counters[key] = max(
                    self.branch_counters.get(key, 0), int(params[2]))
            return []
        if 'FROM first_work_id_counters' in q:
            return [(self.counters.get(params[0], 0),)]
        if 'INSERT INTO first_work_id_counters' in q:
            if 'LAST_INSERT_ID' in q:
                value = self.counters.get(params[0], 0) + 1
            else:
                value = int(params[1])
            self.counters[params[0]] = value
            self.last_insert_id = value
            return []
        if 'FROM first_work_submissions WHERE fingerprint_no=%s' in q or \
                'FROM first_work_submissions WHERE bpf_no=%s' in q:
            column = 'fingerprint_no' if 'fingerprint_no' in q else 'bpf_no'
            return [(1,)] if str(params[0]) in self.used_ids[column] else []
        if 'INSERT INTO first_work_submissions' in q:
            head, tail = q.split('VALUES', 1)
            columns = [c.strip() for c in re.search(r'\(([^)]*)\)', head).group(1).split(',')]
            # `VALUES` memuat literal ('form', 1, 'submitted') yang bukan
            # parameter — petakan hanya token %s ke params berurutan.
            marks = [m.strip() for m in tail.strip().lstrip('(').rstrip(')').split(',')]
            row, index = {}, 0
            for col, mark in zip(columns, marks):
                if mark == '%s':
                    row[col] = params[index]
                    index += 1
            row['id'] = self.lastrowid
            self.lastrowid += 1
            self.submissions.append(row)
            return []
        if 'FROM first_work_submissions s' in q:
            return list(self.export_rows)
        return []


APP = Flask(__name__)
APP.secret_key = 'uji'
fw.register_first_work_routes(APP)


def _submit(monkeypatch, conn, extra=None):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(fw, 'upsert_case_step', lambda *a, **k: None)
    monkeypatch.setattr(fw, 'save_file', lambda *a, **k: 'ktp-uji.jpg')
    monkeypatch.setattr(fw, '_ensure_ktp_scan', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_flag_reuse_signals', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_rate_ok', lambda ip: True)
    data = dict(_VALID)
    data.update(extra or {})
    data['ktp'] = (io.BytesIO(b'\xff\xd8\xff\xe0' + b'x' * 16), 'ktp.jpg')
    with APP.test_client() as client:
        return client.post('/api/first-work/public?cabang=SBY&t=tok-SBY',
                           data=data, content_type='multipart/form-data')


def _export(monkeypatch, conn, role):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    with APP.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_role'] = role
            sess['user_name'] = 'Uji'
            sess['branch_code'] = 'SBY'
        return client.get('/api/first-work/export')


# ================================================================
# Submit publik
# ================================================================
class TestPublicSubmitDemographics:
    def test_submit_tanpa_field_baru_tetap_diterima(self, monkeypatch):
        conn = FakeConn()
        response = _submit(monkeypatch, conn)
        assert response.status_code == 200, response.get_json()
        row = conn.submissions[-1]
        for field in DEMOGRAPHICS:
            assert field in row, field
            assert row[field] is None, field

    def test_submit_dengan_13_field_tersimpan(self, monkeypatch):
        conn = FakeConn()
        response = _submit(monkeypatch, conn, DEMO_VALUES)
        assert response.status_code == 200, response.get_json()
        row = conn.submissions[-1]
        for field in DEMOGRAPHICS:
            assert row[field] == DEMO_VALUES[field], field

    def test_field_demografi_tidak_menimpa_nik_dan_nama_dari_ocr(self, monkeypatch):
        """OCR mengisi `nik`/`nama`; field baru tidak boleh menimpanya.

        Field demografi yang kebetulan berisi 16 digit atau nama orang lain
        tetap disimpan di kolomnya sendiri, bukan di nik/nama pendaftar.
        """
        conn = FakeConn()
        ocr = {'nik': '3578010101900001', 'nama': 'Hasil OCR KTP'}
        evil = dict(DEMO_VALUES)
        evil.update({
            'nik': '3578010101900001',  # sumber utama, hasil OCR
            'nama': 'Hasil OCR KTP',
            'tempat_lahir': '3578999999999999',
            'pekerjaan': 'Nama Orang Lain',
        })
        response = _submit(monkeypatch, conn, evil)
        assert response.status_code == 200, response.get_json()
        row = conn.submissions[-1]
        assert row['nik'] == ocr['nik']
        assert row['nama'] == ocr['nama']
        assert row['tempat_lahir'] == '3578999999999999'
        assert row['pekerjaan'] == 'Nama Orang Lain'

    def test_tanggal_invalid_tidak_menggagalkan_submit(self, monkeypatch):
        conn = FakeConn()
        bad = dict(DEMO_VALUES)
        bad['tanggal_lahir'] = 'bukan-tanggal'
        response = _submit(monkeypatch, conn, bad)
        assert response.status_code == 200, response.get_json()
        assert conn.submissions[-1]['tanggal_lahir'] is None

    def test_nilai_berlebih_dipangkas_aman(self, monkeypatch):
        conn = FakeConn()
        long = dict(DEMO_VALUES)
        long['alamat'] = 'A' * 5000
        response = _submit(monkeypatch, conn, long)
        assert response.status_code == 200, response.get_json()
        assert len(conn.submissions[-1]['alamat']) <= 255


# ================================================================
# Ekspor CSV
# ================================================================
class TestExportDemographics:
    def _rows(self):
        row = {
            'registration_no': 'FW-SBY-20261124-0001', 'branch_code': 'SBY',
            'fingerprint_no': 'EF_25001', 'bpf_no': 'EF_8001',
            'submitted_at': '2026-11-24 09:00:00', 'nama': 'Contoh Pendaftar',
            'nik': '3578010101900001', 'nik_raw': '3578010101900001',
            'nik_valid': 1, 'pendidikan_raw': 'SMA', 'referensi_raw': 'Uji',
            'referrer_name': None, 'no_hp': '081234567890',
            'status': 'submitted', 'verification_note': '', 'verified_by': '',
            'verified_at': None,
        }
        row.update(DEMO_VALUES)
        return [row]

    def test_export_traineer_memuat_ke_13_field(self, monkeypatch):
        response = _export(monkeypatch, FakeConn(self._rows()), 'traineer')
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert set(DEMOGRAPHICS) <= set(fw.DEMOGRAPHIC_FIELDS)
        header = next(line for line in text.splitlines() if line.startswith('\ufeff'))
        for label in ('Tempat Lahir', 'Tanggal Lahir', 'Jenis Kelamin',
                      'Golongan Darah', 'Alamat', 'RT/RW', 'Kel/Desa',
                      'Kecamatan', 'Agama', 'Status Perkawinan', 'Pekerjaan',
                      'Kewarganegaraan', 'Berlaku Hingga'):
            assert label in header, label
        row = text.splitlines()[1]
        for value in DEMO_VALUES.values():
            assert value in row, value

    def test_masking_nik_tidak_berubah_untuk_finance(self, monkeypatch):
        response = _export(monkeypatch, FakeConn(self._rows()), 'finance')
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert '3578010101900001' not in text
        assert '357801\u2022\u2022\u2022\u20220001' in text


# ================================================================
# Skema & init.sql
# ================================================================
class _SchemaCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        if 'ALTER TABLE' in sql.upper():
            self.conn.alters.append(re.sub(r'\s+', ' ', sql).strip())
        elif 'information_schema.COLUMNS' in sql:
            self.conn.column_checks += 1

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self):
        pass


class _SchemaConn:
    def __init__(self):
        self.alters = []
        self.column_checks = 0
        self.commits = 0

    def cursor(self, dictionary=False):
        return _SchemaCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


class TestSchema:
    def test_helper_menambahkan_13_kolom_nullable(self):
        from modules.first_work_schema import ensure_first_work_schema
        conn = _SchemaConn()
        assert ensure_first_work_schema(conn) is True
        alter = ' '.join(conn.alters)
        for field in DEMOGRAPHICS:
            assert re.search(r'\b' + field + r'\b', alter), field
        assert 'ADD COLUMN IF NOT EXISTS' in alter
        assert 'NULL' in alter

    def test_init_sql_memiliki_kolom_untuk_drift_check(self):
        from scripts.check_schema_drift import parse_init_sql
        sql = (open(os.path.join(ROOT, 'init.sql'), encoding='utf-8').read())
        columns = parse_init_sql(sql).get('first_work_submissions', [])
        missing = [field for field in DEMOGRAPHICS if field not in columns]
        assert not missing, 'init.sql kehilangan kolom: ' + ', '.join(missing)
