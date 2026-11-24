"""Rilis B Task 1 — kode cabang pada ID FP & ID BPF FirstWork.

Regresi yang dijaga:
1. Pemetaan 12 cabang -> prefix dua huruf sesuai desain (SBY -> EF, dll).
2. Pengisian baru memakai `<prefix>_<nomor>` dan nomor berasal dari counter
   `(branch_code, series)` — bukan counter global bersama.
3. Counter cabang disemai dari counter global saat pertama dipakai, sehingga
   nomor lanjut dari posisi lama (tidak mulai dari 1) dan counter global
   tidak berubah saat cabang memakai counter sendiri.
4. Baris historis tidak dinomori ulang; ID lama tetap apa adanya.
5. Jalur tanpa cabang (legacy) masih menghasilkan angka polos B/C.
6. DDLkolom & init.sql mengizinkan format baru.
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

PREFIXES = {
    'JKT': 'EI', 'JKT2': 'EA', 'JMB': 'EB', 'MLG': 'EC', 'PTK': 'ED',
    'SBY': 'EF', 'BDG': 'EG', 'MDN': 'EH', 'BJM': 'EJ', 'PKU': 'EK',
    'LPG': 'EL', 'SMG': 'EM',
}
BRANCHES = list(PREFIXES)


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
    """DB master tiruan: counter + baris submit, cukup untuk submit publik."""

    def __init__(self, branches=None, tokens=None):
        self.branches = list(branches or BRANCHES)
        self.tokens = dict(tokens or {c: f'tok-{c}' for c in self.branches})
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
            return [{'code': c, 'name': c, 'city': c} for c in self.branches]
        if 'FROM first_work_branch_forms' in q:
            return [{'branch_code': c, 'form_token': t, 'active': 1}
                    for c, t in self.tokens.items()]
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
            row = dict(zip(
                ('registration_no', 'source_uid', 'submitted_at', 'nik',
                 'nik_raw', 'nama', 'pendidikan', 'pendidikan_norm',
                 'referensi_raw', 'referensi_norm', 'referrer_id',
                 'referrer_needs_review', 'no_hp_raw', 'no_hp',
                 'branch_code', 'ktp_file', 'fingerprint_no', 'bpf_no'),
                params))
            row['id'] = self.lastrowid
            self.lastrowid += 1
            self.submissions.append(row)
            return []
        return []


def _assign(conn, branch):
    return fw._assign_id_numbers(conn, branch_code=branch)


# ================================================================
# Pemetaan prefix
# ================================================================
class TestBranchPrefixMapping:
    def test_seluruh_12_cabang_punya_prefix(self):
        assert len(PREFIXES) == 12
        for code, prefix in PREFIXES.items():
            assert fw.branch_id_prefix(code) == prefix, code

    def test_kode_kecil_dinormalisasi(self):
        assert fw.branch_id_prefix(' sby ') == 'EF'

    def test_cabang_tak_dikenal_tanpa_prefix(self):
        assert fw.branch_id_prefix('XXXX') == ''
        assert fw.branch_id_prefix(None) == ''


# ================================================================
# Generator ID
# ================================================================
class TestBranchIdGeneration:
    def test_sby_memakai_counter_cabang_dan_prefix_ef(self):
        conn = FakeConn()
        assert _assign(conn, 'SBY') == ('EF_25001', 'EF_8001')
        assert conn.branch_counters[('SBY', 'B')] == 25001
        assert conn.branch_counters[('SBY', 'C')] == 8001
        # Counter global tidak ikut bergeser saat cabang punya counter sendiri.
        assert conn.counters == {'B': 25000, 'C': 8000}

    def test_bdg_mendapat_prefix_eg_dan_counter_sendiri(self):
        conn = FakeConn()
        assert _assign(conn, 'BDG') == ('EG_25001', 'EG_8001')
        assert conn.branch_counters[('BDG', 'B')] == 25001

    def test_pengisian_kedua_tidak_mulai_dari_1(self):
        conn = FakeConn()
        assert _assign(conn, 'SBY') == ('EF_25001', 'EF_8001')
        assert _assign(conn, 'SBY') == ('EF_25002', 'EF_8002')

    def test_nomor_yang_sudah_dipakai_dilewati(self):
        conn = FakeConn()
        conn.used_ids['fingerprint_no'].add('EF_25001')
        assert _assign(conn, 'SBY')[0] == 'EF_25002'

    def test_jalur_legacy_tanpa_cabang_tetap_angka_polos(self):
        conn = FakeConn()
        assert _assign(conn, None) == (25001, 8001)
        assert conn.counters == {'B': 25001, 'C': 8001}
        assert conn.branch_counters == {}

    def test_baris_historis_tidak_diubah(self):
        conn = FakeConn()
        conn.submissions.append({'id': 1, 'branch_code': 'SBY',
                                 'fingerprint_no': 25000, 'bpf_no': 8000})
        before = dict(conn.submissions[0])
        _assign(conn, 'SBY')
        assert conn.submissions[0] == before


# ================================================================
# Submit publik (ujung ke ujung)
# ================================================================
APP = Flask(__name__)
APP.secret_key = 'uji'
fw.register_first_work_routes(APP)

_VALID = {
    'nik': '3578010101900001',
    'nama': 'Contoh Pendaftar',
    'pendidikan': 'SMA',
    'no_hp': '081234567890',
    'referensi_text': 'Uji',
    'consent': '1',
}


def _submit(monkeypatch, conn, branch):
    monkeypatch.setattr(fw, 'get_master_connection', lambda: conn)
    monkeypatch.setattr(fw, 'log_activity_async', lambda *a, **k: None)
    monkeypatch.setattr(fw, 'upsert_case_step', lambda *a, **k: None)
    monkeypatch.setattr(fw, 'save_file', lambda *a, **k: 'ktp-uji.jpg')
    monkeypatch.setattr(fw, '_ensure_ktp_scan', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_flag_reuse_signals', lambda *a, **k: None)
    monkeypatch.setattr(fw, '_rate_ok', lambda ip: True)
    client = APP.test_client()
    data = dict(_VALID)
    data['branch'] = branch
    data['ktp'] = (io.BytesIO(b'\xff\xd8\xff\xe0' + b'x' * 16), 'ktp.jpg')
    return client.post(f'/api/first-work/public?cabang={branch}&t=tok-{branch}',
                       data=data, content_type='multipart/form-data')


class TestPublicSubmit:
    def test_submit_sby_menghasilkan_ef(self, monkeypatch):
        conn = FakeConn()
        response = _submit(monkeypatch, conn, 'SBY')
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['fingerprint_no'] == 'EF_25001'
        assert data['bpf_no'] == 'EF_8001'
        row = conn.submissions[-1]
        assert (row['fingerprint_no'], row['bpf_no']) == ('EF_25001', 'EF_8001')

    def test_submit_bdg_menghasilkan_eg(self, monkeypatch):
        conn = FakeConn()
        response = _submit(monkeypatch, conn, 'BDG')
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['fingerprint_no'] == 'EG_25001'
        assert conn.submissions[-1]['fingerprint_no'] == 'EG_25001'


# ================================================================
# ID lama & baru tetap bisa dibaca/koreksi
# ================================================================
class TestLegacyAndPrefixedValues:
    def test_number_part_membaca_dua_format(self):
        assert fw._number_part(25000) == 25000
        assert fw._number_part('25000') == 25000
        assert fw._number_part('EF_30031') == 30031

    def test_valid_id_value_menerima_format_baru(self):
        assert fw._valid_id_value('EF_30031') == 'EF_30031'
        assert fw._valid_id_value(30031) == 30031
        assert fw._valid_id_value('ZZ_30031') is None
        assert fw._valid_id_value('EF_0') is None


# ================================================================
# Skema & init.sql
# ================================================================
class TestSchema:
    def test_kolom_id_di_helper_menampung_prefix(self):
        source = open(os.path.join(ROOT, 'modules', 'first_work_schema.py'),
                      encoding='utf-8').read()
        assert re.search(r'fingerprint_no\s+VARCHAR\(30\)', source)
        assert re.search(r'bpf_no\s+VARCHAR\(30\)', source)

    def test_init_sql_memiliki_kolom_dan_counter(self):
        sql = open(os.path.join(ROOT, 'init.sql'), encoding='utf-8').read()
        assert re.search(r'fingerprint_no\s+VARCHAR\(30\)', sql)
        assert re.search(r'bpf_no\s+VARCHAR\(30\)', sql)
        assert 'CREATE TABLE IF NOT EXISTS first_work_branch_counters' in sql
        assert 'CREATE TABLE IF NOT EXISTS first_work_id_counters' in sql
