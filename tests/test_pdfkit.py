"""Unit + integrasi — modul PDF Kit (v2.47.0).

Cakupan:
- helper murni: nama berkas aman, hitungan persen, perintah gs/qpdf.
- guard integritas: dokumen terdaftar di `document_registry`, bertanda tangan,
  terenkripsi, dan kondisi "tidak ada perbaikan berarti".
- API: mode, submit multipart, guard role, unduhan ter-path-guard, cancel/delete.
- integrasi nyata dengan ghostscript & qpdf (dilewati bila biner tidak ada).

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_pdfkit.py -v
"""

import io
import os
import shutil
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask

from modules.pdfkit import engine, register_pdfkit_routes

HAVE_TOOLS = bool(shutil.which('gs') and shutil.which('qpdf'))
needs_tools = pytest.mark.skipif(
    not HAVE_TOOLS, reason='ghostscript/qpdf tidak terpasang di lingkungan ini')


# ---------------------------------------------------------------------------
# Fixtures & bantu
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    register_pdfkit_routes(app)
    app.config['PDFKIT_DIR'] = str(tmp_path / 'pdfkit')   # jangan sentuh data/
    os.makedirs(app.config['PDFKIT_DIR'], exist_ok=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# Jejak audit selama sesi tes (diisi fixture autouse di bawah).
AUDIT_CALLS = []


@pytest.fixture(autouse=True)
def no_prod_audit(monkeypatch):
    """Tes tidak boleh menulis jejak audit ke `activity_logs` produksi.

    Job nyata memanggil `log_activity_async()` (sumber laporan pemakaian), dan
    saat suite dijalankan di dalam container DB-nya adalah DB produksi — tanpa
    tambalan ini jejak uji ikut terhitung di laporan IT.
    `engine` meng-import fungsi itu di dalam fungsi (via `modules.helpers`),
    sementara `routes` menahannya di level modul → keduanya ditambal.
    """
    import modules.helpers as helpers
    import modules.pdfkit.routes as pk_routes

    def fake(*a, **kw):
        AUDIT_CALLS.append((a, kw))

    monkeypatch.setattr(helpers, 'log_activity_async', fake)
    monkeypatch.setattr(pk_routes, 'log_activity_async', fake)
    yield AUDIT_CALLS


def _login(client, role='it_sby', name=None, full_name=None):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = name or role
        if full_name:
            s['full_name'] = full_name
        s['csrf_token'] = 'test-csrf'


def _upload(client, paths, mode='ringan', target_mb=None):
    data = {'mode': mode}
    if target_mb is not None:
        data['target_mb'] = str(target_mb)
    data['files'] = [(io.BytesIO(open(p, 'rb').read()), os.path.basename(p))
                     for p in paths]
    return client.post('/api/pdfkit/jobs', data=data,
                       content_type='multipart/form-data',
                       headers={'X-CSRF-Token': 'test-csrf'})


def _wait(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f'/api/pdfkit/jobs/{job_id}').get_json()['job']
        if job['status'] in ('done', 'error', 'cancelled'):
            return job
        time.sleep(0.2)
    raise AssertionError('job tidak selesai dalam batas waktu')


def _make_text_pdf(path, lines=60):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    for i in range(lines):
        pdf.cell(0, 6, f'Baris teks uji nomor {i} untuk pengujian kompresi')
        pdf.ln()
    pdf.output(path)
    return path


def _make_heavy_pdf(path, pages=1):
    """PDF berisi gambar ber-noise besar — tiruan hasil scan/foto (±240 dpi).

    Satu halaman saja: cukup untuk menguji penghematan, sekaligus menjaga beban
    CPU suite (ghostscript dipanggil beberapa kali di mode `target`) tetap kecil
    agar tes lain yang sensitif waktu (mis. antrean Transcoder) tidak terganggu.
    """
    import numpy as np
    from PIL import Image
    from fpdf import FPDF
    arr = np.random.default_rng(7).integers(0, 256, (1800, 1800, 3), dtype=np.uint8)
    jpg = path + '.jpg'
    Image.fromarray(arr).save(jpg, quality=95)
    pdf = FPDF()
    for _ in range(pages):
        pdf.add_page()
        pdf.image(jpg, x=10, y=10, w=190)
    pdf.output(path)
    return path


@pytest.fixture(scope='module')
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp('pdfs')
    return {
        'heavy': _make_heavy_pdf(str(d / 'scan_berat.pdf')),
        'text': _make_text_pdf(str(d / 'teks.pdf')),
    }


# ---------------------------------------------------------------------------
# Helper murni
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_safe_stem_buang_traversal(self):
        assert '/' not in engine._safe_stem('../../etc/passwd.pdf')
        assert not engine._safe_stem('../../etc/passwd.pdf').startswith('.')
        assert engine._safe_stem('') == 'dokumen'
        assert engine._safe_stem('###') == 'dokumen'

    def test_safe_stem_pertahankan_spasi(self):
        assert engine._safe_stem('Laporan In-Out Karyawan.pdf') == 'Laporan In-Out Karyawan'

    def test_pct(self):
        assert engine._pct(1000, 250) == 75.0
        assert engine._pct(1000, 1000) == 0.0
        assert engine._pct(1000, 1200) == 0.0     # membesar → 0, bukan negatif
        assert engine._pct(0, 10) == 0.0

    def test_valid_pdf_name(self):
        assert engine.valid_pdf_name('a.PDF')
        assert not engine.valid_pdf_name('a.docx')
        assert not engine.valid_pdf_name('')

    def test_gs_cmd_per_mode(self):
        ringan = engine.gs_cmd('/in.pdf', '/out.pdf', 'ringan')
        assert '-dColorImageResolution=150' in ringan
        assert '-dColorImageFilter=/DCTEncode' not in ringan
        assert ringan[-1] == '/in.pdf'
        maks = engine.gs_cmd('/in.pdf', '/out.pdf', 'maksimal')
        assert '-dColorImageResolution=72' in maks
        assert '-dColorImageFilter=/DCTEncode' in maks
        assert '-dAutoFilterColorImages=false' in maks
        # Teks & vektor tetap teks → font tetap disematkan.
        assert '-dCompressFonts=true' in maks

    def test_qpdf_cmd_lossless(self):
        cmd = engine.qpdf_cmd('/in.pdf', '/out.pdf')
        assert cmd[0] == 'qpdf'
        assert '--object-streams=generate' in cmd
        assert '--recompress-flate' in cmd
        assert cmd[-2:] == ['/in.pdf', '/out.pdf']

    def test_mode_target_pakai_rantai_aman(self):
        assert engine.MODES['target']['kind'] == 'auto'
        assert engine.AUTO_CHAIN[0] == 'lossless'      # mulai dari yang aman
        assert engine.AUTO_CHAIN[-1] == 'maksimal'


# ---------------------------------------------------------------------------
# Guard integritas / keaslian
# ---------------------------------------------------------------------------

class TestGuard:
    def test_dokumen_registri_dilindungi(self):
        reason = engine.guard_reason({}, {}, {'doc_no': 'WTR-20260904-1', 'doc_type': 'water'})
        assert 'registri' in reason.lower()
        assert 'WTR-20260904-1' in reason

    def test_bertanda_tangan_dilindungi(self):
        assert 'tanda tangan' in engine.guard_reason({}, {'signed': True}, None).lower()

    def test_terenkripsi_dilewati(self):
        r = engine.guard_reason({}, {'encrypted': True}, None)
        assert 'password' in r.lower() or 'enkripsi' in r.lower()

    def test_pdf_biasa_tanpa_alasan(self):
        assert engine.guard_reason({}, {'signed': False, 'encrypted': False}, None) == ''

    def test_registry_row_memakai_lookup_hash(self, monkeypatch):
        import modules.doc_integrity as di
        called = {}

        def fake_lookup(sha):
            called['sha'] = sha
            return {'doc_no': 'OT-1'}

        monkeypatch.setattr(di, 'lookup_sha256', fake_lookup)
        assert engine.registry_row('abc123') == {'doc_no': 'OT-1'}
        assert called['sha'] == 'abc123'

    def test_registry_row_hash_kosong(self):
        assert engine.registry_row('') is None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class TestApi:
    def test_modes(self, client):
        _login(client)
        d = client.get('/api/pdfkit/modes').get_json()
        assert d['status'] == 'ok'
        keys = {m['key'] for m in d['modes']}
        assert {'lossless', 'ringan', 'sedang', 'kuat', 'maksimal', 'target'} <= keys
        assert d['limits']['max_files'] == engine.MAX_FILES_PER_JOB
        tgt = [m for m in d['modes'] if m['key'] == 'target'][0]
        assert tgt['needs_target'] is True

    def test_role_bukan_it_ditolak(self, client):
        _login(client, role='ga')
        assert client.get('/api/pdfkit/modes').status_code == 403

    def test_tanpa_berkas(self, client):
        _login(client)
        r = client.post('/api/pdfkit/jobs', data={'mode': 'ringan'},
                        content_type='multipart/form-data',
                        headers={'X-CSRF-Token': 'test-csrf'})
        assert r.status_code == 400
        assert 'PDF' in r.get_json()['msg']

    def test_bukan_pdf_ditolak(self, client):
        _login(client)
        r = client.post('/api/pdfkit/jobs',
                        data={'mode': 'ringan',
                              'files': [(io.BytesIO(b'halo'), 'catatan.txt')]},
                        content_type='multipart/form-data',
                        headers={'X-CSRF-Token': 'test-csrf'})
        assert r.status_code == 400
        assert 'Bukan berkas PDF' in r.get_json()['msg']

    def test_mode_tidak_dikenal(self, client, samples):
        _login(client)
        r = _upload(client, [samples['text']], mode='super')
        assert r.status_code == 400

    def test_mode_target_wajib_isi_ukuran(self, client, samples):
        _login(client)
        r = _upload(client, [samples['text']], mode='target')
        assert r.status_code == 400
        assert 'target ukuran' in r.get_json()['msg'].lower()

    def test_job_tidak_ada(self, client):
        _login(client)
        assert client.get('/api/pdfkit/jobs/pk999999').status_code == 404
        assert client.delete('/api/pdfkit/jobs/pk999999').status_code == 404

    def test_bukan_pemilik_tidak_bisa_lihat(self, client, samples, monkeypatch):
        monkeypatch.setattr(engine, 'probe',
                            lambda p: {'pages': 1, 'encrypted': False,
                                       'signed': False, 'has_text': False})
        _login(client, name='it_sby')
        job = _upload(client, [samples['text']], mode='lossless').get_json()['job']
        with client.session_transaction() as s:
            s['user_name'] = 'it_bdg'
        assert client.get(f"/api/pdfkit/jobs/{job['id']}").status_code == 403
        _login(client, name='it_sby')   # pulihkan pemilik sebelum menunggu
        _wait(client, job['id'])       # tunggu worker selesai (audit tak bocor ke tes lain)


# ---------------------------------------------------------------------------
# Laporan pemakaian (Audit Log)
# ---------------------------------------------------------------------------

USAGE_ROWS = [
    {'action': 'pdfkit_submit', 'user_type': 'it_sby', 'user_name': 'it_sby',
     'created_at': '2026-10-16 09:00:00',
     'new_data': {'job': 'pk000001', 'mode': 'sedang', 'files': ['a.pdf'], 'total_mb': 2.0}},
    {'action': 'pdfkit_done', 'user_type': 'it_sby', 'user_name': 'it_sby',
     'created_at': '2026-10-16 09:01:00',
     'new_data': {'job': 'pk000001', 'mode': 'sedang', 'files': 2, 'done': 1,
                  'skipped': 1, 'failed': 0, 'size_before': 2_000_000,
                  'size_after': 500_000, 'saved_bytes': 1_500_000, 'ratio_pct': 75.0}},
    {'action': 'pdfkit_submit', 'user_type': 'it_bdg', 'user_name': 'it_bdg',
     'created_at': '2026-10-16 10:00:00', 'new_data': {'job': 'pk000002'}},
    {'action': 'pdfkit_done', 'user_type': 'it_bdg', 'user_name': 'it_bdg',
     'created_at': '2026-10-16 10:02:00',
     'new_data': {'job': 'pk000002', 'mode': 'lossless', 'files': 1, 'done': 1,
                  'skipped': 0, 'failed': 0, 'size_before': 1_000_000,
                  'size_after': 900_000, 'saved_bytes': 100_000, 'ratio_pct': 10.0}},
    {'action': 'login', 'user_type': 'ga', 'user_name': 'ga_sby', 'created_at': '',
     'new_data': None},            # aksi lain harus diabaikan
]


class TestUsageReport:
    def test_agregasi_per_user_dan_total(self):
        rep = engine.aggregate_usage(USAGE_ROWS)
        t = rep['totals']
        assert t['jobs'] == 2 and t['files'] == 3 and t['done'] == 2 and t['skipped'] == 1
        assert t['saved_bytes'] == 1_600_000
        assert t['size_before'] == 3_000_000 and t['size_after'] == 1_400_000
        assert t['ratio_pct'] == 53.3              # 1 - 1,4/3,0
        assert [u['user'] for u in rep['per_user']] == ['it_sby', 'it_bdg']   # hemat terbesar dulu
        sby = rep['per_user'][0]
        assert (sby['jobs'], sby['files'], sby['saved_bytes']) == (1, 2, 1_500_000)
        assert sby['role'] == 'it_sby' and sby['last_at'] == '2026-10-16 09:01:00'
        assert rep['recent'][0]['job'] == 'pk000002'    # terbaru dulu
        assert len(rep['recent']) == 2

    def test_agregasi_toleran_new_data_string_dan_kosong(self):
        rep = engine.aggregate_usage([
            {'action': 'pdfkit_done', 'user_name': 'it_sby', 'user_type': 'it_sby',
             'created_at': '2026-10-16 09:00:00',
             'new_data': '{"files": 1, "saved_bytes": 10, "size_before": 100, "size_after": 90}'},
        ])
        assert rep['totals']['saved_bytes'] == 10
        assert engine.aggregate_usage([])['totals']['jobs'] == 0
        assert engine.aggregate_usage(None)['per_user'] == []

    def test_api_laporan_mengembalikan_agregat(self, client, monkeypatch):
        class FakeCursor:
            def execute(self, *a, **k):
                pass

            def fetchall(self):
                return USAGE_ROWS

            def close(self):
                pass

        class FakeConn:
            def cursor(self, dictionary=False):
                return FakeCursor()

            def close(self):
                pass

        import modules.config as cfg
        monkeypatch.setattr(cfg, 'get_db_connection', lambda *a, **k: FakeConn())
        _login(client, role='admin')
        d = client.get('/api/pdfkit/report').get_json()
        assert d['status'] == 'ok'
        assert d['data']['totals']['saved_bytes'] == 1_600_000
        assert d['data']['per_user'][0]['user'] == 'it_sby'
        assert d['data']['meta']['branch'] == 'current'

    def test_api_laporan_ditolak_untuk_role_lain(self, client):
        _login(client, role='ga')
        assert client.get('/api/pdfkit/report').status_code == 403

    def test_tambalan_audit_aktif(self, client):
        """Guard fixture `no_prod_audit`: import di kedua modul harus tetap
        tertambal. Kalau ini gagal, tes lain sedang menulis ke DB produksi."""
        import modules.helpers as helpers
        import modules.pdfkit.routes as pk_routes
        assert helpers.log_activity_async.__name__ == 'fake'
        assert pk_routes.log_activity_async.__name__ == 'fake'

    def test_job_selesai_menulis_jejak_pemakaian(self, client, samples,
                                                 monkeypatch, no_prod_audit):
        """Job selesai → worker menulis activity_logs action 'pdfkit_done'."""
        calls = no_prod_audit
        monkeypatch.setattr(engine, 'registry_row', lambda sha: None)
        monkeypatch.setattr(engine, 'probe',
                            lambda p: {'pages': 1, 'encrypted': False,
                                       'signed': False, 'has_text': False})

        def fake_chain(src, out, mode, target_bytes=0, on_step=None):
            with open(src, 'rb') as f:
                data = f.read()
            with open(out, 'wb') as f:
                f.write(data[:len(data) // 2])
            return {'ok': True, 'mode_used': mode, 'error': '', 'tried': [mode]}

        monkeypatch.setattr(engine, 'compress_chain', fake_chain)
        _login(client, full_name='Budi Santoso')
        job = _upload(client, [samples['text']], mode='ringan').get_json()['job']
        job = _wait(client, job['id'])
        assert job['status'] == 'done'
        # filter per job: worker job uji lain bisa selesai bersamaan
        audit = [c for c in calls if c[0][1] == 'pdfkit_done'
                 and c[1]['new_data']['job'] == job['id']]
        assert len(audit) == 1
        (args, kw) = audit[0]
        # role + identitas: submit dan done WAJIB memakai nama tampilan yang
        # sama, kalau tidak laporan pemakaian memecah satu orang jadi 2 baris.
        assert args[2] == 'it_sby' and args[3] == 'Budi Santoso'
        submit = [c for c in calls if c[0][1] == 'pdfkit_submit'
                  and c[1]['new_data']['job'] == job['id']]
        assert len(submit) == 1 and submit[0][0][3] == 'Budi Santoso'
        assert kw['new_data']['job'] == job['id']
        assert kw['new_data']['files'] == 1 and kw['new_data']['done'] == 1
        assert kw['new_data']['saved_bytes'] > 0


# ---------------------------------------------------------------------------
# Siklus hidup job
# ---------------------------------------------------------------------------

class TestLifecycle:
    @needs_tools
    def test_kompres_pdf_hasil_scan(self, client, samples):
        """PDF gambar besar → menyusut nyata, hasil bisa diunduh."""
        _login(client)
        before = os.path.getsize(samples['heavy'])
        job = _upload(client, [samples['heavy']], mode='sedang').get_json()['job']
        job = _wait(client, job['id'])
        assert job['status'] == 'done'
        item = job['items'][0]
        assert item['status'] == 'done'
        assert item['size_before'] == before
        assert item['size_after'] < before
        assert item['ratio_pct'] >= 50          # scan 240 dpi → 120 dpi
        assert item['mode_used'] in ('sedang', 'lossless')
        out = item['outputs'][0]
        assert out['file'].endswith('.pdf')

        d = client.get(f"/api/pdfkit/download/{job['id']}/{out['file']}")
        assert d.status_code == 200
        assert d.headers['Content-Type'] == 'application/pdf'
        assert len(d.data) == item['size_after']
        # berkas yang tidak tercatat di job tidak boleh diunduh
        assert client.get(f"/api/pdfkit/download/{job['id']}/lain.pdf").status_code == 404

    @needs_tools
    def test_lossless_mempertahankan_teks(self, client, samples):
        _login(client)
        job = _upload(client, [samples['text']], mode='lossless').get_json()['job']
        job = _wait(client, job['id'])
        item = job['items'][0]
        assert item['status'] in ('done', 'skipped')
        if item['status'] == 'done':
            assert item['text_kept'] is True
            assert item['size_after'] < item['size_before']

    @needs_tools
    def test_mode_target_tercapai_dan_berhenti_di_rantai(self, client, samples):
        _login(client)
        before = os.path.getsize(samples['heavy'])
        target = max(0.2, before / (1024 * 1024) / 4)   # minta ~1/4 ukuran asli
        job = _upload(client, [samples['heavy']], mode='target',
                      target_mb=round(target, 2)).get_json()['job']
        job = _wait(client, job['id'])
        item = job['items'][0]
        assert item['status'] == 'done'
        assert item['size_after'] <= int(target * 1024 * 1024)
        assert item['mode_used'] in engine.AUTO_CHAIN

    def test_compress_chain_berhenti_saat_target_tercapai(self, tmp_path, monkeypatch):
        """Logika rantai diuji deterministik: berhenti di mode pertama yang
        mencapai target, dan memakai yang TERKECIL bila target tak tercapai."""
        sizes = {'lossless': 10_000_000, 'ringan': 3_000_000,
                 'kuat': 1_000_000, 'maksimal': 500_000}
        calls = []

        def fake_compress(src, out, mode):
            calls.append(mode)
            with open(out, 'wb') as f:
                f.write(b'x' * sizes[mode])
            return True, '', mode

        monkeypatch.setattr(engine, 'compress_with', fake_compress)
        src = tmp_path / 'in.pdf'
        src.write_bytes(b'y' * 20_000_000)
        out = str(tmp_path / 'out.pdf')

        res = engine.compress_chain(str(src), out, 'target', target_bytes=2_000_000)
        assert res['ok'] is True
        assert calls == ['lossless', 'ringan', 'kuat']    # berhenti begitu tercapai
        assert res['mode_used'] == 'kuat'
        assert os.path.getsize(out) == 1_000_000
        assert not os.path.exists(f'{out}.ringan.tmp')     # kandidat kalah dibuang
        assert not os.path.exists(f'{out}.lossless.tmp')

        calls.clear()
        res = engine.compress_chain(str(src), out, 'target', target_bytes=1)
        assert res['mode_used'] == 'maksimal'              # target mustahil → terkecil
        assert calls == list(engine.AUTO_CHAIN)
        assert os.path.getsize(out) == 500_000

    def test_dokumen_terdaftar_dilewati(self, client, samples, monkeypatch):
        """Dokumen terbitan sistem (ada di document_registry) TIDAK dikompres."""
        monkeypatch.setattr(engine, 'registry_row',
                            lambda sha: {'doc_no': 'WTR-20260904-10300556',
                                         'doc_type': 'water'})
        monkeypatch.setattr(engine, 'probe',
                            lambda p: {'pages': 1, 'encrypted': False,
                                       'signed': False, 'has_text': False})
        _login(client)
        job = _upload(client, [samples['heavy']], mode='maksimal').get_json()['job']
        job = _wait(client, job['id'])
        item = job['items'][0]
        assert item['status'] == 'protected'
        assert item['outputs'] == []
        assert 'WTR-20260904-10300556' in item['note']
        assert job['status'] == 'done'           # job tetap "selesai", bukan error

    def test_bertanda_tangan_dan_terenkripsi_tidak_diproses(self, client, samples, monkeypatch):
        monkeypatch.setattr(engine, 'registry_row', lambda sha: None)
        _login(client)
        for info, expected in (({'signed': True, 'encrypted': False}, 'protected'),
                               ({'signed': False, 'encrypted': True}, 'skipped')):
            monkeypatch.setattr(engine, 'probe',
                                lambda p, i=info: {'pages': 1, 'has_text': False, **i})
            job = _upload(client, [samples['text']], mode='ringan').get_json()['job']
            job = _wait(client, job['id'])
            assert job['items'][0]['status'] == expected

    def test_tanpa_perbaikan_berarti_dilewati(self, client, samples, monkeypatch):
        """Hasil yang tidak menyusut ≥2% dibuang — IT tidak dikirimi file sia-sia."""
        monkeypatch.setattr(engine, 'registry_row', lambda sha: None)
        monkeypatch.setattr(engine, 'probe',
                            lambda p: {'pages': 1, 'encrypted': False,
                                       'signed': False, 'has_text': True})

        def fake_chain(src, out, mode, target_bytes=0, on_step=None):
            with open(src, 'rb') as f:
                data = f.read()
            with open(out, 'wb') as f:
                f.write(data)                     # ukuran identik → gain 0%
            return {'ok': True, 'mode_used': mode, 'error': '', 'tried': [mode]}

        monkeypatch.setattr(engine, 'compress_chain', fake_chain)
        _login(client)
        job = _upload(client, [samples['text']], mode='ringan').get_json()['job']
        job = _wait(client, job['id'])
        item = job['items'][0]
        assert item['status'] == 'skipped'
        assert item['outputs'] == []
        assert 'optimal' in item['note'].lower()

    def test_cancel_dan_delete(self, client, samples, monkeypatch):
        monkeypatch.setattr(engine, 'registry_row', lambda sha: None)
        monkeypatch.setattr(engine, 'probe',
                            lambda p: {'pages': 1, 'encrypted': False,
                                       'signed': False, 'has_text': False})

        def fake_chain(src, out, mode, target_bytes=0, on_step=None):
            time.sleep(0.4)
            with open(src, 'rb') as f:
                data = f.read()
            with open(out, 'wb') as f:
                f.write(data[:-1])
            return {'ok': True, 'mode_used': mode, 'error': '', 'tried': [mode]}

        monkeypatch.setattr(engine, 'compress_chain', fake_chain)
        _login(client)
        job = _upload(client, [samples['text']], mode='ringan').get_json()['job']
        assert client.post(f"/api/pdfkit/jobs/{job['id']}/cancel",
                           headers={'X-CSRF-Token': 'test-csrf'}).status_code == 200
        job = _wait(client, job['id'])
        assert job['status'] == 'cancelled'
        assert client.delete(f"/api/pdfkit/jobs/{job['id']}",
                             headers={'X-CSRF-Token': 'test-csrf'}).status_code == 200
        assert client.get(f"/api/pdfkit/jobs/{job['id']}").status_code == 404

    @needs_tools
    def test_banyak_berkas_sekali_submit(self, client, samples):
        _login(client)
        job = _upload(client, [samples['text'], samples['heavy']],
                      mode='lossless').get_json()['job']
        job = _wait(client, job['id'])
        assert len(job['items']) == 2
        assert job['progress'] == 100
        assert job['saved_bytes'] >= 0
        assert job['ratio_pct'] >= 0
