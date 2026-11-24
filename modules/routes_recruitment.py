"""Rekrutmen — endpoint lookup publik (Rilis A).

`GET /api/recruitment/lookup?nik=<16 digit>&dob=YYYY-MM-DD` menjawab satu
pertanyaan saja: "NIK ini sudah dikenal sistem rekrutmen atau belum?"
Jawabannya HANYA boolean (`known`, `can_continue`) — tidak ada cabang, tahap,
nama, atau data pribadi lain, dan tidak ada baris yang ditulis.

Deteksi bersifat global ke DB master (lintas cabang), memakai tiga sumber:
`recruitment_cases`, `cv_online_submissions.nik`, `first_work_submissions.nik`.
Peserta dengan NIK baru tetap boleh mengisi CV Online; keputusan kartu langkah
ada di portal (Task 7), bukan di endpoint ini.

Pola mengikuti `/api/first-work/check-nik`: rate limit Redis per IP,
normalisasi NIK bersama, dan `Cache-Control: no-store`.
"""
import re
from datetime import datetime

from flask import jsonify, request

from modules.config import get_master_connection
from modules.helpers import client_ip, normalize_nik, redis_rate_hit

# 10 pengecekan / menit / IP. Endpoint ini menjawab keberadaan NIK, jadi
# kuota longgar = alat enumerasi data pribadi (lihat check-nik FirstWork).
_LOOKUP_MAX = 10
_LOOKUP_WINDOW = 60
_LOOKUP_PREFIX = 'recruitment'

# Sumber keberadaan NIK — DB master, tanpa filter cabang.
_NIK_TABLES = ('recruitment_cases', 'cv_online_submissions',
               'first_work_submissions')

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _valid_dob(value):
    """Terima hanya tanggal ISO YYYY-MM-DD yang benar-benar ada."""
    text = str(value or '').strip()
    if not _DATE_RE.match(text):
        return False
    try:
        datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        return False
    return True


def _lookup_ok(ip):
    """Satu hit kuota lookup (Redis atomik + fallback memori)."""
    return redis_rate_hit(f'lookup|{ip}', _LOOKUP_MAX, _LOOKUP_WINDOW,
                          prefix=_LOOKUP_PREFIX)


def _response(payload, status=200):
    """Semua jawaban lookup — termasuk 429/500 — tidak boleh di-cache."""
    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'no-store'
    return resp, status


def _nik_known(cursor, nik):
    """True bila NIK ada di salah satu sumber (berhenti di temuan pertama)."""
    for table in _NIK_TABLES:
        # Nama tabel konstan, bukan input pengguna — aman dari injeksi.
        cursor.execute(f'SELECT COUNT(*) AS n FROM {table} WHERE nik=%s', (nik,))
        row = cursor.fetchone() or {}
        if int(row.get('n') or 0) > 0:
            return True
    return False


def register_recruitment_routes(app):
    @app.route('/api/recruitment/lookup', methods=['GET'])
    def api_recruitment_lookup():
        """Cek keberadaan NIK tanpa membocorkan cabang/langkah/data pribadi."""
        ip = client_ip() or '?'
        if not _lookup_ok(ip):
            return _response({'status': 'error',
                              'msg': 'Terlalu banyak pengecekan. Coba lagi sebentar.'},
                             429)

        nik, _raw = normalize_nik(request.args.get('nik'))
        if len(nik) != 16 or not _valid_dob(request.args.get('dob')):
            # Sengaja sukses dengan valid:false (pola check-nik) agar tidak
            # memberi petunjuk lebih banyak dari sekadar "input tidak valid".
            # TIDAK membuka koneksi DB sama sekali pada jalur ini.
            return _response({'status': 'success', 'valid': False,
                              'known': False, 'can_continue': False})

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return _response({'status': 'error', 'msg': 'DB error'}, 500)
            cursor = conn.cursor(dictionary=True)
            try:
                known = _nik_known(cursor, nik)
            finally:
                cursor.close()
            return _response({'status': 'success',
                              'known': known, 'can_continue': known})
        except Exception:
            # Jangan kembalikan str(e): detail DB bisa membocorkan skema/PII.
            return _response({'status': 'error', 'msg': 'DB error'}, 500)
        finally:
            if conn:
                conn.close()
