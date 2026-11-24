"""Rekrutmen — lookup publik & exception langkah staff (Rilis A).

`GET /api/recruitment/lookup?nik=<16 digit>&dob=YYYY-MM-DD` menjawab satu
pertanyaan saja: "NIK ini sudah dikenal sistem rekrutmen atau belum?"
Jawabannya HANYA boolean (`known`, `can_continue`) — tidak ada cabang, tahap,
nama, atau data pribadi lain, dan tidak ada baris yang ditulis.

`POST /api/recruitment/steps/<step_id>/exception` dipakai petugas
(traineer/ga_hr/admin) untuk mengecualikan satu langkah yang masih `BELUM`
atau `PENDING`. Alasan wajib (maks. 500 karakter) dan tercatat di audit.

`GET /api/recruitment/cases` menyuapi dashboard staff (Task 6): daftar kasus
beserta riwayat cabang dan langkahnya. NIK hanya dikirim sebagai empat digit
terakhir (`****0002`), baik di respons maupun di audit.

Deteksi bersifat global ke DB master (lintas cabang), memakai tiga sumber:
`recruitment_cases`, `cv_online_submissions.nik`, `first_work_submissions.nik`.
Peserta dengan NIK baru tetap boleh mengisi CV Online; keputusan kartu langkah
ada di portal (Task 7), bukan di endpoint ini.

Pola mengikuti `/api/first-work/check-nik`: rate limit Redis per IP,
normalisasi NIK bersama, dan `Cache-Control: no-store`.
"""
import re
from datetime import date, datetime

from flask import jsonify, request, session

from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, normalize_nik,
                             redis_rate_hit, role_required)

# 10 pengecekan / menit / IP. Endpoint ini menjawab keberadaan NIK, jadi
# kuota longgar = alat enumerasi data pribadi (lihat check-nik FirstWork).
_LOOKUP_MAX = 10
_LOOKUP_WINDOW = 60
_LOOKUP_PREFIX = 'recruitment'

# Sumber keberadaan NIK — DB master, tanpa filter cabang.
_NIK_TABLES = ('recruitment_cases', 'cv_online_submissions',
               'first_work_submissions')

# Peran staff rekrutmen (dashboard + exception langkah).
_STAFF_ROLES = ['traineer', 'ga_hr', 'admin']

# Exception langkah: hanya status sebelum selesai yang boleh dikecualikan.
_EXCEPTION_ALLOWED = ('BELUM', 'PENDING')
_REASON_MAX = 500

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


def _mask_nik(value):
    """Tampilkan maksimal empat digit terakhir; NIK penuh tidak pernah keluar."""
    text = str(value or '').strip()
    return ('****' + text[-4:]) if text else '****'


def _mask_case_id(value):
    """ID kasus bawaan Task 4 berbentuk `RC-<16 digit>` — NIK-nya ikut ditutup."""
    text = str(value or '')
    if text.startswith('RC-'):
        suffix = text[3:]
        if len(suffix) == 16 and suffix.isdigit():
            return 'RC-' + _mask_nik(suffix)
    return text


def _as_text(value):
    """Nilai waktu dari DB (datetime/date) -> string; None tetap None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


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
            # Kontrak 3 kunci dipertahankan juga untuk input invalid: tidak
            # ada field `valid` atau petunjuk lain. TIDAK membuka koneksi DB
            # sama sekali pada jalur ini.
            return _response({'status': 'success', 'known': False,
                              'can_continue': False})

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

    @app.route('/api/recruitment/cases', methods=['GET'])
    @role_required(_STAFF_ROLES)
    def api_recruitment_cases():
        """Daftar kasus staff: riwayat cabang + langkah, NIK selalu termasker."""
        role = session.get('user_role') or ''
        actor = session.get('user_name') or 'system'
        raw_nik = request.args.get('nik') or ''
        nik, _raw = normalize_nik(raw_nik)
        branch_code = (request.args.get('branch_code') or '').strip().upper()[:10]
        status = (request.args.get('status') or '').strip()[:30]

        if raw_nik.strip() and len(nik) != 16:
            # Filter NIK tidak valid = tidak ada baris; tidak buka DB sama sekali.
            data = []
        else:
            conn = None
            try:
                conn = get_master_connection()
                if not conn:
                    return jsonify({'status': 'error', 'msg': 'DB error'}), 500
                cursor = conn.cursor(dictionary=True)
                try:
                    conditions, params = [], []
                    if nik:
                        conditions.append('c.nik=%s')
                        params.append(nik)
                    if branch_code:
                        conditions.append(
                            '(c.first_branch=%s OR EXISTS ('
                            'SELECT 1 FROM case_branch_history h '
                            'WHERE h.case_id=c.case_id AND h.branch_code=%s) '
                            'OR EXISTS ('
                            'SELECT 1 FROM recruitment_steps s '
                            'WHERE s.case_id=c.case_id AND s.branch_code=%s))')
                        params.extend([branch_code] * 3)
                    if status:
                        conditions.append('c.status=%s')
                        params.append(status)

                    sql = ('SELECT c.case_id, c.nik, c.nama, c.first_branch, '
                           'c.status FROM recruitment_cases c')
                    if conditions:
                        sql += ' WHERE ' + ' AND '.join(conditions)
                    sql += ' ORDER BY c.first_seen_at DESC LIMIT 100'
                    cursor.execute(sql, tuple(params))
                    rows = cursor.fetchall() or []

                    branches_by_case, steps_by_case = {}, {}
                    case_ids = [row['case_id'] for row in rows]
                    if case_ids:
                        # Dua query massal, bukan N+1; placeholder dibangun dari
                        # jumlah ID, bukan dari input pengguna.
                        marks = ','.join(['%s'] * len(case_ids))
                        cursor.execute(
                            'SELECT case_id, branch_code, first_seen_at, '
                            'last_seen_at FROM case_branch_history '
                            f'WHERE case_id IN ({marks}) '
                            'ORDER BY first_seen_at DESC', tuple(case_ids))
                        for b in cursor.fetchall() or []:
                            branches_by_case.setdefault(b['case_id'], []).append({
                                'branch_code': str(b.get('branch_code') or ''),
                                'first_seen_at': _as_text(b.get('first_seen_at')),
                                'last_seen_at': _as_text(b.get('last_seen_at')),
                            })
                        cursor.execute(
                            'SELECT case_id, step_type, status, branch_code, '
                            'exception_reason, completed_at FROM recruitment_steps '
                            f'WHERE case_id IN ({marks}) '
                            'ORDER BY step_type, branch_code', tuple(case_ids))
                        for s in cursor.fetchall() or []:
                            steps_by_case.setdefault(s['case_id'], []).append({
                                'step_type': str(s.get('step_type') or ''),
                                'status': str(s.get('status') or ''),
                                'branch_code': str(s.get('branch_code') or ''),
                                'exception_reason': _as_text(
                                    s.get('exception_reason')),
                                'completed_at': _as_text(s.get('completed_at')),
                            })

                    data = [{
                        'case_id': _mask_case_id(r.get('case_id')),
                        'nik_masked': _mask_nik(r.get('nik')),
                        'nama': str(r.get('nama') or ''),
                        'first_branch': str(r.get('first_branch') or ''),
                        'status': str(r.get('status') or ''),
                        'branches': branches_by_case.get(r['case_id'], []),
                        'steps': steps_by_case.get(r['case_id'], []),
                    } for r in rows]
                finally:
                    cursor.close()
            except Exception:
                # Jangan kembalikan str(e): detail DB bisa membocorkan skema/PII.
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            finally:
                if conn:
                    conn.close()

        try:
            # tx_id None karena ini aksi baca, bukan transaksi (v2.131.3).
            log_activity_async(
                None, 'recruitment_cases_view', role, actor,
                new_data={'nik_masked': _mask_nik(nik) if nik else '****',
                          'count': len(data)})
        except Exception:
            pass  # Audit gagal tidak boleh menggagalkan pembacaan dashboard.
        return jsonify({'data': data})

    @app.route('/api/recruitment/steps/<int:step_id>/exception', methods=['POST'])
    @role_required(_STAFF_ROLES)
    def api_recruitment_step_exception(step_id):
        """Kecualikan satu langkah; hanya BELUM/PENDING yang boleh diubah."""
        body = request.get_json(silent=True) or {}
        raw_reason = body.get('reason')
        reason = raw_reason.strip() if isinstance(raw_reason, str) else ''
        if not reason or len(reason) > _REASON_MAX:
            return jsonify({'status': 'error',
                            'msg': f'Alasan wajib diisi (maks. '
                                   f'{_REASON_MAX} karakter).'}), 400

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    'SELECT id, status FROM recruitment_steps WHERE id=%s',
                    (step_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah tidak ditemukan'}), 404
                if row.get('status') not in _EXCEPTION_ALLOWED:
                    return jsonify({'status': 'error',
                                    'msg': 'Status langkah tidak mendukung '
                                           'pengecualian'}), 409

                actor = session.get('user_name') or 'system'
                role = session.get('user_role') or ''
                cursor.execute("""
                    UPDATE recruitment_steps
                    SET status='DIKECUALIKAN', exception_reason=%s,
                        actor=%s, completed_at=NOW()
                    WHERE id=%s
                """, (reason, actor, step_id))
                conn.commit()
            finally:
                cursor.close()

            try:
                # tx_id None: activity_logs.transaction_id ber-FK ke transactions;
                # ID langkah cukup dibawa di new_data (v2.131.3 audit fix).
                log_activity_async(None, 'recruitment_step_exception', role, actor,
                                   new_data={'step_id': step_id, 'reason': reason})
            except Exception:
                # Audit gagal tidak boleh mengembalikan 500 setelah commit.
                pass
            return jsonify({'status': 'success', 'msg': 'Langkah dikecualikan',
                            'data': {'id': step_id, 'status': 'DIKECUALIKAN'}})
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        finally:
            if conn:
                conn.close()
