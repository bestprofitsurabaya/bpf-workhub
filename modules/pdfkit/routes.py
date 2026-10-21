"""modules/pdfkit/routes.py (v2.47.0)

Endpoint REST PDF Kit (semua ber-session + CSRF bawaan `before_request`):

- GET  /api/pdfkit/modes                        → daftar mode kompresi
- POST /api/pdfkit/jobs                         → submit 1..10 berkas PDF (multipart)
- GET  /api/pdfkit/jobs                         → daftar job (milik user; admin semua)
- GET  /api/pdfkit/jobs/<id>                    → detail job (polling progres)
- POST /api/pdfkit/jobs/<id>/cancel             → batalkan job
- DELETE /api/pdfkit/jobs/<id>                  → hapus job + berkas hasil
- GET  /api/pdfkit/download/<job_id>/<filename> → unduh hasil (auth, path-guard)

Role: role IT cabang + admin (`PDFKIT_ROLES`).
"""

import hashlib
import os
import secrets

from flask import (current_app, jsonify, request, send_from_directory, session)

from modules.helpers import log_activity_async, role_required

from . import PDFKIT_ROLES, pdfkit_bp
from . import engine
from .engine import MODES


def _user():
    return session.get('user_name') or '?'


def _base():
    return current_app.config.get('PDFKIT_DIR', '')


def _can_view(job):
    return job.get('user') == _user() or session.get('user_role') == 'admin'


def _save_upload(base, f, max_bytes):
    """Simpan unggahan ke folder staging sambil menghitung sha256 (tanpa muat
    seluruh berkas ke memori). Return dict {name, path, size, sha256}."""
    name = os.path.basename(f.filename or '')[:150]
    if not engine.valid_pdf_name(name):
        raise ValueError(f'Bukan berkas PDF: {name[:60]}')
    dest = os.path.join(engine.staging_dir(base),
                        f'{secrets.token_hex(8)}_{engine._safe_stem(name)}.pdf')
    h = hashlib.sha256()
    size = 0
    try:
        with open(dest, 'wb') as out:
            while True:
                chunk = f.stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f'{name[:60]} melebihi batas '
                                     f'{max_bytes // (1024 * 1024)} MB')
                h.update(chunk)
                out.write(chunk)
    except Exception:
        engine.discard_staging([dest])
        raise
    if not size:
        engine.discard_staging([dest])
        raise ValueError(f'{name[:60]} kosong')
    return {'name': name, 'path': dest, 'size': size, 'sha256': h.hexdigest()}


# ---------------------------------------------------------------------------
# Mode & submit
# ---------------------------------------------------------------------------

@pdfkit_bp.route('/api/pdfkit/modes', methods=['GET'])
@role_required(list(PDFKIT_ROLES))
def list_modes():
    modes = [{'key': k, 'label': v['label'], 'hint': v['hint'],
              'needs_target': bool(v.get('needs_target'))}
             for k, v in MODES.items()]
    return jsonify({'status': 'ok', 'modes': modes,
                    'limits': {'max_files': engine.MAX_FILES_PER_JOB,
                               'max_file_mb': engine.MAX_FILE_MB,
                               'max_total_mb': engine.MAX_TOTAL_MB}})


@pdfkit_bp.route('/api/pdfkit/jobs', methods=['POST'])
@role_required(list(PDFKIT_ROLES))
def submit_job():
    files = [f for f in request.files.getlist('files') if f and f.filename]
    mode = str(request.form.get('mode') or 'ringan').strip().lower()
    if mode not in MODES:
        return jsonify({'status': 'error',
                        'msg': f'Mode tidak dikenal: {mode[:20]}'}), 400
    if not files:
        return jsonify({'status': 'error', 'msg': 'Pilih minimal satu berkas PDF'}), 400
    if len(files) > engine.MAX_FILES_PER_JOB:
        return jsonify({'status': 'error',
                        'msg': f'Maksimal {engine.MAX_FILES_PER_JOB} berkas sekali submit'}), 400

    try:
        target_mb = float(request.form.get('target_mb') or 0)
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Target ukuran harus angka (MB)'}), 400
    if MODES[mode].get('needs_target'):
        if not (0.1 <= target_mb <= 50):
            return jsonify({'status': 'error',
                            'msg': 'Isi target ukuran 0,1–50 MB untuk mode ini'}), 400
    else:
        target_mb = 0

    base = _base()
    if not base:
        return jsonify({'status': 'error', 'msg': 'Folder kerja PDF Kit belum siap'}), 500

    saved = []
    try:
        for f in files:
            saved.append(_save_upload(base, f, engine.MAX_FILE_MB * 1024 * 1024))
        total_mb = sum(s['size'] for s in saved) / (1024 * 1024)
        if total_mb > engine.MAX_TOTAL_MB:
            engine.discard_staging([s['path'] for s in saved])
            return jsonify({'status': 'error',
                            'msg': f'Total berkas {total_mb:.0f} MB melebihi batas '
                                   f'{engine.MAX_TOTAL_MB} MB'}), 400
        job = engine.create_job(saved, mode, target_mb, _user(), base,
                                role=session.get('user_role', ''),
                                branch_code=session.get('branch_code', ''),
                                display=session.get('full_name') or '')
    except ValueError as ve:
        engine.discard_staging([s['path'] for s in saved])
        return jsonify({'status': 'error', 'msg': str(ve)}), 400
    except Exception as e:
        engine.discard_staging([s['path'] for s in saved])
        return jsonify({'status': 'error', 'msg': f'Gagal menyimpan berkas: {e}'}), 500

    log_activity_async(None, 'pdfkit_submit', session.get('user_role', ''),
                       session.get('full_name') or _user(),
                       new_data={'job': job['id'], 'mode': mode,
                                 'files': [s['name'] for s in saved],
                                 'total_mb': round(sum(s['size'] for s in saved) / (1024 * 1024), 2)},
                       ip=request.remote_addr)
    return jsonify({'status': 'ok', 'job': job}), 201


@pdfkit_bp.route('/api/pdfkit/report', methods=['GET'])
@role_required(list(PDFKIT_ROLES))
def usage_report():
    """Laporan pemakaian PDF Kit (siapa, berapa berkas, berapa byte dihemat).

    Sumber: `activity_logs` (action `pdfkit_submit` dari routes + `pdfkit_done`
    yang ditulis worker saat job selesai) — sehingga tetap ada setelah hasil job
    (retensi 48 jam) terhapus. Dipakai panel "📄 Pemakaian PDF Kit" di halaman
    Audit Log. Scoping cabang sama dengan `/api/audit-logs`: admin cabang
    terkunci ke cabangnya sendiri.
    """
    try:
        date_from = str(request.args.get('date_from') or '').strip()
        date_to = str(request.args.get('date_to') or '').strip()
        branch = str(request.args.get('branch') or '').strip().upper()
        if session.get('user_role') == 'admin' and branch:
            from modules.admin_scope import is_ho_admin, admin_can_operate_branch
            if not is_ho_admin() and not admin_can_operate_branch(branch):
                return jsonify({'status': 'error',
                                'msg': 'Admin cabang hanya boleh melihat log cabangnya.'}), 403
        from modules.config import get_db_connection
        conn = get_db_connection(branch_code=branch or None)
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        where = ["action IN ('pdfkit_submit', 'pdfkit_done')"]
        params = []
        if date_from:
            where.append('DATE(created_at) >= %s')
            params.append(date_from)
        if date_to:
            where.append('DATE(created_at) <= %s')
            params.append(date_to)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT action, user_type, user_name, created_at, new_data '
            'FROM activity_logs WHERE ' + ' AND '.join(where) +
            ' ORDER BY created_at DESC LIMIT 5000', params)
        rows = cursor.fetchall()
        cursor.close(); conn.close()
        data = engine.aggregate_usage(rows)
        data['meta'] = {'date_from': date_from, 'date_to': date_to,
                        'branch': branch or 'current', 'rows': len(rows)}
        return jsonify({'status': 'ok', 'data': data})
    except Exception as e:
        print(f'[pdfkit] laporan gagal: {e}')
        return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500


@pdfkit_bp.route('/api/pdfkit/jobs', methods=['GET'])
@role_required(list(PDFKIT_ROLES))
def list_jobs():
    jobs = engine.list_jobs(limit=100)
    if session.get('user_role') != 'admin':
        jobs = [j for j in jobs if j.get('user') == _user()]
    return jsonify({'status': 'ok', 'jobs': jobs})


@pdfkit_bp.route('/api/pdfkit/jobs/<job_id>', methods=['GET'])
@role_required(list(PDFKIT_ROLES))
def get_job(job_id):
    job = engine.get_job(job_id)
    if not job:
        return jsonify({'status': 'error', 'msg': 'Job tidak ditemukan'}), 404
    if not _can_view(job):
        return jsonify({'status': 'error', 'msg': 'Bukan job Anda'}), 403
    return jsonify({'status': 'ok', 'job': job})


@pdfkit_bp.route('/api/pdfkit/jobs/<job_id>/cancel', methods=['POST'])
@role_required(list(PDFKIT_ROLES))
def cancel_job(job_id):
    ok, msg = engine.cancel_job(job_id, _user())
    if not ok:
        code = 404 if 'tidak ditemukan' in msg.lower() else 409
        return jsonify({'status': 'error', 'msg': msg}), code
    return jsonify({'status': 'ok', 'msg': msg})


@pdfkit_bp.route('/api/pdfkit/jobs/<job_id>', methods=['DELETE'])
@role_required(list(PDFKIT_ROLES))
def delete_job(job_id):
    ok, msg = engine.delete_job(job_id, _user())
    if not ok:
        code = 404 if 'tidak ditemukan' in msg.lower() else 409
        return jsonify({'status': 'error', 'msg': msg}), code
    log_activity_async(None, 'pdfkit_delete', session.get('user_role', ''),
                       session.get('full_name') or _user(),
                       new_data={'job': job_id}, ip=request.remote_addr)
    return jsonify({'status': 'ok', 'msg': msg})


@pdfkit_bp.route('/api/pdfkit/download/<job_id>/<path:filename>', methods=['GET'])
@role_required(list(PDFKIT_ROLES))
def download(job_id, filename):
    """Unduh hasil — hanya berkas yang tercatat di job, dan hanya job milik user."""
    job = engine.get_job(job_id)
    if not job:
        return jsonify({'status': 'error', 'msg': 'Job tidak ditemukan'}), 404
    if not _can_view(job):
        return jsonify({'status': 'error', 'msg': 'Bukan job Anda'}), 403
    allowed = {o['file'] for it in job['items'] for o in it.get('outputs', [])}
    name = os.path.basename(filename)
    if name not in allowed:
        return jsonify({'status': 'error', 'msg': 'Berkas tidak ada di job ini'}), 404
    folder = os.path.join(_base(), job_id, 'out')
    resp = send_from_directory(folder, name, as_attachment=True,
                               download_name=name)
    resp.headers['Content-Type'] = 'application/pdf'
    return resp
