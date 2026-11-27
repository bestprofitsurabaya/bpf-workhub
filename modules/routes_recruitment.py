"""Rekrutmen — lookup publik & exception langkah staff (Rilis A).

`GET /api/recruitment/lookup?nik=<16 digit>` menjawab satu
pertanyaan saja: "NIK ini sudah dikenal sistem rekrutmen atau belum?"
Jawabannya HANYA boolean (`known`, `can_continue`) — tidak ada cabang, tahap,
nama, atau data pribadi lain, dan tidak ada baris yang ditulis.

`POST /api/recruitment/steps/<step_id>/exception` dipakai petugas
(traineer/ga_hr/admin) untuk mengecualikan satu langkah yang masih `BELUM`
atau `PENDING`. Alasan wajib (maks. 500 karakter) dan tercatat di audit.

`GET /api/recruitment/cases` menyuapi dashboard staff (Task 6): daftar kasus
beserta riwayat cabang dan langkahnya. NIK hanya dikirim sebagai empat digit
terakhir (`****0002`), baik di respons maupun di audit. `case_id` sudah opaque
(dibuat service tanpa NIK) sehingga dikembalikan apa adanya.

`POST /api/recruitment/steps/<step_id>/evidence` dipakai staff untuk mencatat
bukti manual TRAINING/TKD (Rilis B Task 6). `step_id=0` berarti langkah belum
ada dan dibuat lebih dulu dari `case_id`/`step_type` di body.

Deteksi bersifat global ke DB master (lintas cabang), memakai tiga sumber:
`recruitment_cases`, `cv_online_submissions.nik`, `first_work_submissions.nik`.
Peserta dengan NIK baru tetap boleh mengisi CV Online; keputusan kartu langkah
ada di portal (Task 7), bukan di endpoint ini.

Pola mengikuti `/api/first-work/check-nik`: rate limit Redis per IP,
normalisasi NIK bersama, dan `Cache-Control: no-store`.
"""
import math
import re
import uuid
from datetime import date, datetime

from flask import jsonify, request, session

from modules.config import get_master_connection
from modules.helpers import (client_ip, log_activity_async, normalize_nik,
                             redis_rate_hit, role_required)
from modules.tkd_service import (load_settings, resolve_branch_token,
                                 set_manual_score)

# 10 pengecekan / menit / IP. Endpoint ini menjawab keberadaan NIK, jadi
# kuota longgar = alat enumerasi data pribadi (lihat check-nik FirstWork).
_LOOKUP_MAX = 10
_LOOKUP_WINDOW = 60
_LOOKUP_PREFIX = 'recruitment'

# Sumber keberadaan NIK — DB master, tanpa filter cabang.
_NIK_TABLES = ('recruitment_cases', 'cv_online_submissions',
               'first_work_submissions')
_STAGE_TYPES = ('CV', 'TRAINING', 'TKD', 'FIRSTWORK')
_STATUS_RANK = {'BELUM': 1, 'PENDING': 2, 'DIKECUALIKAN': 3, 'SELESAI': 4}

# Peran staff rekrutmen (dashboard + exception langkah).
_STAFF_ROLES = ['traineer', 'ga_hr', 'admin']

# Exception langkah: hanya status sebelum selesai yang boleh dikecualikan.
_EXCEPTION_ALLOWED = ('BELUM', 'PENDING')
_REASON_MAX = 500

# Cabang tanpa sesi TIDAK boleh jadi "semua cabang": sentinel ini sengaja
# tidak cocok dengan kode cabang mana pun (sama seperti routes_tkd).
_NO_BRANCH = '__NOBRANCH__'

# Bukti manual: hanya TRAINING/TKD yang datanya tidak berasal dari modul nyata.
# CV/FIRSTWORK diisi oleh submit CV Online/FirstWork, jadi ditolak 409.
_EVIDENCE_STEP_TYPES = ('TRAINING', 'TKD')
_EVIDENCE_TOKEN_PREFIX = 'MEV-'
# step_id=0 dipakai UI bila langkah belum ada (Task 4 hanya membuat CV/FIRSTWORK).
_LAZY_STEP_ID = 0

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


def _latest_branch_code(cursor, case_id, fallback=''):
    """Cabang terakhir yang dipakai kasus; jatuh ke cabang asal bila kosong."""
    cursor.execute(
        'SELECT branch_code FROM case_branch_history WHERE case_id=%s '
        'ORDER BY last_seen_at DESC, first_seen_at DESC LIMIT 1', (case_id,))
    row = cursor.fetchone() or {}
    return str(row.get('branch_code') or fallback or '')[:10]


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


def _as_text(value):
    """Nilai waktu dari DB (datetime/date) -> string; None tetap None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _as_float(value):
    """Skor DB (Decimal/int/str) -> float; None atau sampah -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value):
    """Flag angka dari DB -> int; None tetap None."""
    number = _as_float(value)
    return int(number) if number is not None else None


def _case_scope_ok(cursor, case_id, scope):
    """Aturan scope kasus yang sama dengan endpoint skor TKD.

    Impor lokal menghindari siklus modul: `routes_tkd` mengimpor `_mask_nik`
    dari modul ini.
    """
    from modules.routes_tkd import _case_in_scope
    return _case_in_scope(cursor, case_id, scope)


def _tkd_visible_for(scope, row, branches, steps):
    """True bila skor TKD kasus boleh tampil untuk staff bercabang `scope`.

    Daftar kasus tetap global seperti sebelumnya; hanya field skor TKD yang
    dibatasi ke cabang asal/riwayat/langkah milik staff.
    """
    if scope is None:
        return True
    first = str((row or {}).get('first_branch') or '').strip().upper()[:10]
    if first == scope:
        return True
    for branch in branches or []:
        if str((branch or {}).get('branch_code') or '').strip().upper()[:10] == scope:
            return True
    for step in steps or []:
        if str((step or {}).get('branch_code') or '').strip().upper()[:10] == scope:
            return True
    return False


def _portal_scope_branch(conn):
    """None hanya untuk Admin Pusat; selain itu cabang sesi (fail-closed)."""
    if session.get('user_role') == 'admin':
        try:
            from modules.admin_scope import is_ho_admin
            if is_ho_admin(conn):
                return None
        except Exception:
            pass  # Hak tidak terbaca tidak boleh menaikkan ke lintas cabang.
    return str(session.get('branch_code') or '').strip().upper()[:10] or _NO_BRANCH


def _active_flag(value):
    """Flag aktif DB: hanya 1/True/'1' yang aktif; '0'/0/kosong tidak."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or '').strip().lower() in ('1', 'true')


def _parse_tkd_score(text):
    """Skor TKD manual: (nilai float, valid) dalam rentang 0–100."""
    if not text:
        return None, True
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None, False
    return (value, True) if 0.0 <= value <= 100.0 else (None, False)


def _nik_known(cursor, nik):
    """True bila NIK ada di salah satu sumber (berhenti di temuan pertama)."""
    for table in _NIK_TABLES:
        # Nama tabel konstan, bukan input pengguna — aman dari injeksi.
        cursor.execute(f'SELECT COUNT(*) AS n FROM {table} WHERE nik=%s', (nik,))
        row = cursor.fetchone() or {}
        if int(row.get('n') or 0) > 0:
            return True
    return False


def _masked_name(value):
    """Nama depan + inisial kata kedua; tidak mengandung NIK/DOB/alamat."""
    parts = str(value or '').split()
    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    return f'{parts[0]} {parts[1][0]}.'


def _iso_date(value):
    """Tanggal ISO dari DATETIME/date/teks; '' bila tidak bisa dipakai."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or '').strip()
    return text[:10] if _DATE_RE.match(text[:10]) else ''


def portal_branch_history(cursor, nik, current_branch):
    """Info "pernah tercatat di cabang lain" — tanpa NIK/kode/case_id.

    Hanya dihitung bila cabang portal diketahui dari token aktif. Cabang yang
    sama dengan `current_branch` tidak dihitung. Hasil berisi jumlah cabang
    lain, tanggal pertama (paling awal), dan nama tampilan cabang; kode cabang
    tidak pernah dikirim ke halaman publik.

    Sumber: `case_branch_history` + `recruitment_cases.first_branch`. Untuk
    data lama yang belum punya baris kasus, dipakai `cv_online_submissions`
    dan `first_work_submissions`. Semua operasi baca saja.
    """
    current = str(current_branch or '').strip().upper()
    if not current:
        return None

    cursor.execute(
        'SELECT case_id, first_branch, first_seen_at '
        'FROM recruitment_cases WHERE nik=%s', (nik,))
    case = cursor.fetchone() or {}
    case_id = str(case.get('case_id') or '')
    seen = {}

    def _note(code, when):
        code = str(code or '').strip().upper()
        when = _iso_date(when)
        if not code or not when:
            return
        if code not in seen or when < seen[code]:
            seen[code] = when

    if case_id:
        cursor.execute(
            'SELECT branch_code, first_seen_at FROM case_branch_history '
            'WHERE case_id=%s', (case_id,))
        for row in cursor.fetchall() or []:
            _note(row.get('branch_code'), row.get('first_seen_at'))
        _note(case.get('first_branch'), case.get('first_seen_at'))
    else:
        for table in ('cv_online_submissions', 'first_work_submissions'):
            # Nama tabel konstan, bukan input pengguna — aman dari injeksi.
            cursor.execute(
                f'SELECT branch_code, submitted_at FROM {table} WHERE nik=%s',
                (nik,))
            for row in cursor.fetchall() or []:
                _note(row.get('branch_code'), row.get('submitted_at'))

    others = {code: when for code, when in seen.items() if code != current}
    if not others:
        return None

    codes = sorted(others)
    name_map = {}
    try:
        placeholders = ','.join(['%s'] * len(codes))
        cursor.execute(
            f'SELECT code, name FROM branches WHERE code IN ({placeholders})',
            tuple(codes))
        name_map = {
            str(row.get('code') or '').strip().upper():
            str(row.get('name') or '').strip()
            for row in cursor.fetchall() or []
        }
    except Exception:
        name_map = {}
    names = [name_map.get(code) or 'cabang lain' for code in codes[:5]]
    return {
        'other_branch_count': len(codes),
        'first_seen_at': min(others.values()),
        'branch_names': names,
    }


def portal_summary(cursor, nik, known=False, branch_code=None):
    """Ringkasan empat tahap untuk satu NIK — tanpa data pribadi lengkap.

    `branch_code` opsional membatasi langkah ke satu cabang. Portal publik
    memakai semua langkah (NIK global); dokumen cabang (kartu First Work)
    memakai cabang baris agar capaian cabang lain tidak ikut tampil.
    """
    cursor.execute('SELECT case_id, nama FROM recruitment_cases WHERE nik=%s',
                   (nik,))
    case = cursor.fetchone() or {}
    case_id = case.get('case_id') or ''
    steps = []
    if case_id:
        sql = ('SELECT step_type, status, completed_at, branch_code '
               'FROM recruitment_steps WHERE case_id=%s')
        params = [case_id]
        if branch_code:
            sql += ' AND branch_code=%s'
            params.append(branch_code)
        cursor.execute(sql, tuple(params))
        # WHERE sudah membatasi ke case_id; jangan memfilter ulang di Python
        # karena kolom case_id sengaja tidak ikut di-SELECT.
        steps = cursor.fetchall() or []

    best = {}
    for step in steps:
        kind = str(step.get('step_type') or '')
        if kind not in _STAGE_TYPES:
            continue
        status = str(step.get('status') or 'BELUM')
        previous = best.get(kind)
        if not previous or _STATUS_RANK.get(status, 0) > \
                _STATUS_RANK.get(previous['status'], 0):
            best[kind] = {'status': status,
                          'completed_at': step.get('completed_at')}
        elif (status == 'SELESAI' and step.get('completed_at') and
              not previous.get('completed_at')):
            previous['completed_at'] = step.get('completed_at')

    stages = []
    for kind in _STAGE_TYPES:
        info = best.get(kind, {})
        status = info.get('status', 'BELUM')
        stages.append({
            'type': kind,
            'status': status,
            # Kirim ISO, bukan datetime mentah: Flask akan meng-encode
            # datetime menjadi RFC 822 Inggris ("Wed, 25 Nov ... GMT").
            'completed_at': _as_text(info.get('completed_at')),
            'can_open': (False if status == 'SELESAI' else
                         True if kind == 'CV' else bool(known)),
        })

    next_action = 'DONE'
    for kind in _STAGE_TYPES:
        if best.get(kind, {}).get('status') != 'SELESAI':
            next_action = kind
            break

    return {'nama_masked': _masked_name(case.get('nama')),
            'stages': stages, 'next_action': next_action}


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
        if len(nik) != 16:
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
            payload = None
            history = None
            try:
                known = _nik_known(cursor, nik)
                try:
                    payload = portal_summary(cursor, nik, known)
                except Exception:
                    payload = None  # best-effort: kontrak lama tetap dipakai
                try:
                    token = (request.args.get('token')
                             or request.args.get('t') or '').strip()[:200]
                    branch = resolve_branch_token(cursor, token) if token else ''
                    if branch and known:
                        history = portal_branch_history(cursor, nik, branch)
                except Exception:
                    history = None  # info tambahan tidak boleh menggagalkan lookup
            finally:
                cursor.close()
            result = {'status': 'success', 'known': known,
                      'can_continue': known}
            if payload:
                result.update(payload)
            if history:
                result['branch_history'] = history
            return _response(result)
        except Exception:
            # Jangan kembalikan str(e): detail DB bisa membocorkan skema/PII.
            return _response({'status': 'error', 'msg': 'DB error'}, 500)
        finally:
            if conn:
                conn.close()

    @app.route('/api/recruitment/portal-links', methods=['GET'])
    @role_required(['receptionist', 'traineer', 'ga_hr', 'admin'])
    def api_recruitment_portal_links():
        """Satu tautan portal per cabang; token hanya dikirim di dalam URL."""
        role = session.get('user_role') or ''
        actor = session.get('user_name') or 'system'
        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            scope = _portal_scope_branch(conn)
            cursor = conn.cursor(dictionary=True)
            try:
                if scope is None:  # Admin Pusat: hanya cabang aktif, tanpa filter.
                    cursor.execute(
                        'SELECT code, name FROM branches '
                        'WHERE is_active=1 ORDER BY code')
                else:
                    # Non-HO selalu memakai bind: sentinel tidak cocok apa pun.
                    cursor.execute(
                        'SELECT code, name FROM branches '
                        'WHERE is_active=1 AND code=%s ORDER BY code', (scope,))
                branches = cursor.fetchall() or []
                if scope is None:
                    cursor.execute(
                        'SELECT branch_code, form_token, active '
                        'FROM cv_online_branch_forms')
                else:
                    cursor.execute(
                        'SELECT branch_code, form_token, active '
                        'FROM cv_online_branch_forms WHERE branch_code=%s',
                        (scope,))
                tokens = {}
                for row in cursor.fetchall() or []:
                    code = str(row.get('branch_code') or '').strip().upper()
                    tokens[code] = row
            finally:
                cursor.close()

            data = []
            for info in branches:
                code = str(info.get('code') or '').strip().upper()
                if not code or (scope is not None and code != scope):
                    continue
                token_row = tokens.get(code) or {}
                token = str(token_row.get('form_token') or '').strip()
                active = bool(token) and _active_flag(token_row.get('active', 1))
                data.append({
                    'branch_code': code,
                    'branch_name': str(info.get('name') or code),
                    # Token tidak pernah jadi field terpisah: QR memakai URL ini.
                    'portal_path': (f'/app/recruitment-portal?token={token}'
                                    if active else ''),
                    'active': active,
                })
        except Exception:
            # Jangan kembalikan str(e): detail DB bisa membocorkan skema/PII.
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        finally:
            if conn:
                conn.close()

        try:
            # tx_id None karena ini aksi baca, bukan transaksi. Tanpa NIK.
            log_activity_async(
                None, 'recruitment_portal_links_view', role, actor,
                new_data={'scope_branch': scope, 'count': len(data)})
        except Exception:
            pass  # Audit gagal tidak boleh menggagalkan pembacaan tautan.
        return jsonify({'data': data, 'scope_branch': scope})

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
                scope = _portal_scope_branch(conn)
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
                    # Non-HO hanya melihat kasus yang terikat ke cabangnya
                    # (asal, riwayat, atau langkah). HO admin tetap global.
                    if scope is not None:
                        conditions.append(
                            '(c.first_branch=%s OR EXISTS ('
                            'SELECT 1 FROM case_branch_history h '
                            'WHERE h.case_id=c.case_id AND h.branch_code=%s) '
                            'OR EXISTS ('
                            'SELECT 1 FROM recruitment_steps s '
                            'WHERE s.case_id=c.case_id AND s.branch_code=%s))')
                        params.extend([scope] * 3)

                    sql = ('SELECT c.case_id, c.nik, c.nama, c.first_branch, '
                           'c.status, c.tkd_score, c.tkd_score_source, '
                           'c.tkd_score_note, c.tkd_passed '
                           'FROM recruitment_cases c')
                    if conditions:
                        sql += ' WHERE ' + ' AND '.join(conditions)
                    sql += ' ORDER BY c.first_seen_at DESC LIMIT 100'
                    cursor.execute(sql, tuple(params))
                    rows = cursor.fetchall() or []

                    branches_by_case, steps_by_case = {}, {}
                    training_by_case = {}
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
                        # id langkah ikut dikirim supaya dashboard bisa memanggil
                        # POST /api/recruitment/steps/<id>/exception (Task 6).
                        cursor.execute(
                            'SELECT id, case_id, step_type, status, branch_code, '
                            'exception_reason, completed_at FROM recruitment_steps '
                            f'WHERE case_id IN ({marks}) '
                            'ORDER BY step_type, branch_code', tuple(case_ids))
                        for s in cursor.fetchall() or []:
                            steps_by_case.setdefault(s['case_id'], []).append({
                                'id': s.get('id'),
                                'step_type': str(s.get('step_type') or ''),
                                'status': str(s.get('status') or ''),
                                'branch_code': str(s.get('branch_code') or ''),
                                'exception_reason': _as_text(
                                    s.get('exception_reason')),
                                'completed_at': _as_text(s.get('completed_at')),
                            })
                        # Absensi training portal (2 hari) — bukti per kasus.
                        # Tabel bisa belum ada di DB lama; dashboard tetap jalan.
                        try:
                            cursor.execute(
                                'SELECT case_id, day, attended_at, link_status '
                                'FROM training_attendance '
                                f'WHERE case_id IN ({marks}) ORDER BY day',
                                tuple(case_ids))
                            for t in cursor.fetchall() or []:
                                training_by_case.setdefault(
                                    t['case_id'], []).append({
                                        'day': _as_int(t.get('day')),
                                        'attended_at': _as_text(
                                            t.get('attended_at')),
                                        'link_status': str(
                                            t.get('link_status') or ''),
                                    })
                        except Exception:
                            training_by_case = {}

                    data = []
                    for r in rows:
                        branches = branches_by_case.get(r['case_id'], [])
                        steps = steps_by_case.get(r['case_id'], [])
                        # Skor TKD resmi hanya untuk kasus dalam cakupan staff;
                        # kasus di luar cakupan tetap tampil tanpa skor (field
                        # kontrak dipertahankan bernilai null).
                        show_tkd = _tkd_visible_for(scope, r, branches, steps)
                        data.append({
                            'case_id': str(r.get('case_id') or ''),
                            'nik_masked': _mask_nik(r.get('nik')),
                            'nama': str(r.get('nama') or ''),
                            'first_branch': str(r.get('first_branch') or ''),
                            'status': str(r.get('status') or ''),
                            'branches': branches,
                            'steps': steps,
                            'training': training_by_case.get(
                                r['case_id'], []),
                            'tkd_score': (_as_float(r.get('tkd_score'))
                                          if show_tkd else None),
                            'tkd_score_source': (_as_text(r.get('tkd_score_source'))
                                                 if show_tkd else None),
                            'tkd_score_note': (_as_text(r.get('tkd_score_note'))
                                               if show_tkd else None),
                            'tkd_passed': (_as_int(r.get('tkd_passed'))
                                           if show_tkd else None),
                        })
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
                    'SELECT id, status, case_id FROM recruitment_steps '
                    'WHERE id=%s', (step_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah tidak ditemukan'}), 404
                # Scope cabang diperiksa sebelum status: langkah cabang lain
                # tidak boleh terbaca statusnya lewat kode 409.
                scope = _portal_scope_branch(conn)
                if not _case_scope_ok(cursor, row.get('case_id'), scope):
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah tidak ditemukan'}), 403
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

    @app.route('/api/recruitment/steps/<int:step_id>/evidence', methods=['POST'])
    @role_required(_STAFF_ROLES)
    def api_recruitment_step_evidence(step_id):
        """Simpan bukti manual TRAINING/TKD.

        `step_id=0` berarti langkah belum ada: dibuat lebih dulu dari
        `case_id`/`step_type` di body dengan cabang terakhir si kasus.
        NIK tidak pernah diterima maupun ditulis ke audit di endpoint ini.
        """
        body = request.get_json(silent=True) or {}

        raw_date = body.get('date')
        evidence_date = str(raw_date).strip() if isinstance(raw_date, str) else ''
        if not _valid_dob(evidence_date):
            return jsonify({'status': 'error',
                            'msg': 'Tanggal bukti wajib diisi (YYYY-MM-DD).'}), 400

        raw_note = body.get('note')
        note = str(raw_note).strip() if isinstance(raw_note, str) else ''
        note = note[:_REASON_MAX]  # exception_reason VARCHAR(500)

        def _optional_text(key, limit):
            value = body.get(key)
            return str(value).strip()[:limit] if isinstance(value, str) else ''

        file_url = _optional_text('file_url', 300)
        score = _optional_text('score', 30)

        lazy = step_id == _LAZY_STEP_ID
        case_id = str(body.get('case_id') or '').strip()[:40]
        step_type_body = str(body.get('step_type') or '').strip().upper()
        if lazy and not case_id:
            return jsonify({'status': 'error',
                            'msg': 'case_id wajib untuk langkah baru.'}), 400
        if lazy and step_type_body not in _EVIDENCE_STEP_TYPES:
            return jsonify({'status': 'error',
                            'msg': 'Jenis langkah tidak mendukung bukti manual'}), 409

        score_value, score_ok = _parse_tkd_score(score)
        # Langkah baru: tolak skor buruk sebelum INSERT (tidak ada write).
        if lazy and step_type_body == 'TKD' and not score_ok:
            return jsonify({'status': 'error',
                            'msg': 'Skor TKD harus angka 0–100.'}), 400

        conn = None
        try:
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            try:
                scope = _portal_scope_branch(conn)
                if lazy:
                    cursor.execute(
                        'SELECT case_id, first_branch FROM recruitment_cases '
                        'WHERE case_id=%s', (case_id,))
                    case_row = cursor.fetchone()
                    if not case_row:
                        return jsonify({'status': 'error',
                                        'msg': 'Kasus tidak ditemukan'}), 404
                    if not _case_scope_ok(cursor, case_id, scope):
                        return jsonify({'status': 'error',
                                        'msg': 'Kasus di luar cabang Anda.'}), 403
                    branch = _latest_branch_code(
                        cursor, case_id, case_row.get('first_branch'))
                    cursor.execute("""
                        INSERT IGNORE INTO recruitment_steps
                            (case_id, step_type, status, branch_code)
                        VALUES (%s,%s,'BELUM',%s)
                    """, (case_id, step_type_body, branch))
                    cursor.execute("""
                        SELECT id FROM recruitment_steps
                        WHERE case_id=%s AND step_type=%s AND branch_code=%s
                        ORDER BY id DESC LIMIT 1
                    """, (case_id, step_type_body, branch))
                    created = cursor.fetchone()
                    if not created:
                        return jsonify({'status': 'error', 'msg': 'DB error'}), 500
                    step_id = created['id']

                cursor.execute(
                    'SELECT id, case_id, step_type, status, branch_code '
                    'FROM recruitment_steps WHERE id=%s', (step_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah tidak ditemukan'}), 404
                if not _case_scope_ok(cursor, row.get('case_id'), scope):
                    return jsonify({'status': 'error',
                                    'msg': 'Kasus di luar cabang Anda.'}), 403
                if row.get('step_type') not in _EVIDENCE_STEP_TYPES:
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah ini tidak menerima bukti manual'}), 409
                if row.get('status') == 'DIKECUALIKAN':
                    return jsonify({'status': 'error',
                                    'msg': 'Langkah dikecualikan tidak bisa diisi'}), 409

                actor = session.get('user_name') or 'system'
                role = session.get('user_role') or ''
                tkd_score = row.get('step_type') == 'TKD' and bool(score)
                if tkd_score and not score_ok:
                    return jsonify({'status': 'error',
                                    'msg': 'Skor TKD harus angka 0–100.'}), 400
                if tkd_score:
                    # Skor manual TKD: service yang menulis skor kasus, status,
                    # dan bukti langkah — jangan ditimpa UPDATE manual di bawah.
                    result = set_manual_score(
                        cursor, row.get('case_id'), score_value,
                        note or 'Bukti manual TKD', actor,
                        load_settings(cursor)['pass_score'],
                        row.get('branch_code') or '') or {}
                    conn.commit()
                    evidence_id = ''
                    final_status = ('SELESAI' if result.get('passed')
                                    else 'PENDING')
                    audit_score = score_value
                else:
                    # Tanpa skor (atau TRAINING): perilaku bukti manual lama.
                    evidence_id = (_EVIDENCE_TOKEN_PREFIX
                                   + uuid.uuid4().hex[:16])
                    cursor.execute("""
                        UPDATE recruitment_steps
                        SET status=%s, evidence_type=%s, evidence_id=%s,
                            exception_reason=%s, completed_at=%s, actor=%s
                        WHERE id=%s
                    """, ('SELESAI', 'manual_evidence', evidence_id, note,
                          evidence_date, actor, step_id))
                    conn.commit()
                    final_status = 'SELESAI'
                    audit_score = score
            finally:
                cursor.close()

            try:
                # tx_id None: activity_logs.transaction_id ber-FK ke transactions.
                log_activity_async(
                    None, 'recruitment_step_evidence', role, actor,
                    new_data={'step_id': step_id,
                              'case_id': str(row.get('case_id') or ''),
                              'date': evidence_date, 'note': note,
                              'file_url': file_url, 'score': audit_score,
                              'created': bool(lazy)})
            except Exception:
                pass  # Audit gagal tidak boleh mengembalikan 500 setelah commit.
            return jsonify({
                'status': 'success', 'msg': 'Bukti tersimpan',
                'data': {'id': step_id, 'step_type': row.get('step_type'),
                         'status': final_status, 'date': evidence_date,
                         'evidence_id': evidence_id},
            })
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
