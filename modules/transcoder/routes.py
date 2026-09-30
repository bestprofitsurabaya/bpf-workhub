"""
modules/transcoder/routes.py (v2.46.0)

Endpoint REST transcoder (semua ber-session + CSRF bawaan before_request):
- POST /api/transcoder/jobs        → submit 1..10 link + format (role IT/admin)
- GET  /api/transcoder/jobs        → daftar job (milik user; admin semua)
- GET  /api/transcoder/jobs/<id>   → detail job (polling progres)
- POST /api/transcoder/jobs/<id>/cancel → batalkan job
- DELETE /api/transcoder/jobs/<id> → hapus job + file hasil
- GET  /api/transcoder/download/<job_id>/<file> → unduh hasil (auth, path-guard)
"""
import os

from flask import (request, jsonify, session, send_from_directory,
                   current_app)

from modules.helpers import role_required

from . import transcoder_bp, TRANSCODER_ROLES
from . import engine
from .engine import FORMATS  # noqa: F401


def _user():
    return session.get('user_name') or '?'


def _can_view(job):
    return job.get('user') == _user() or session.get('user_role') == 'admin'


# ---------------------------------------------------------------------------
# Submit & list
# ---------------------------------------------------------------------------

@transcoder_bp.route('/api/transcoder/jobs', methods=['POST'])
@role_required(list(TRANSCODER_ROLES))
def submit_jobs():
    data = request.get_json(silent=True) or {}
    raw_urls = data.get('urls') or []
    formats = data.get('formats') or []

    # multi-link: string (1 link), list, atau teks multi-baris dipisah baris/koma
    if isinstance(raw_urls, str):
        raw_urls = raw_urls.replace(',', '\n').split()
    urls, seen = [], set()
    for u in raw_urls:
        u = (u or '').strip()
        if not u:
            continue
        if not engine.is_youtube_url(u):
            return jsonify({'status': 'error',
                            'msg': f'URL bukan YouTube: {u[:80]}'}), 400
        if u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        return jsonify({'status': 'error', 'msg': 'Minimal satu link YouTube'}), 400
    if len(urls) > engine.MAX_URLS_PER_REQUEST:
        return jsonify({'status': 'error',
                        'msg': f'Maksimal {engine.MAX_URLS_PER_REQUEST} link sekali submit'}), 400

    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        return jsonify({'status': 'error',
                        'msg': f'Format tidak dikenal: {", ".join(unknown)}'}), 400
    if not formats:
        return jsonify({'status': 'error', 'msg': 'Pilih minimal satu format output'}), 400

    job = engine.create_job(urls, formats, _user(),
                            current_app.config.get('TRANSCODE_DIR', ''))
    return jsonify({'status': 'ok', 'job': job}), 201


@transcoder_bp.route('/api/transcoder/jobs', methods=['GET'])
@role_required(list(TRANSCODER_ROLES))
def list_jobs():
    jobs = engine.list_jobs(limit=100)
    if session.get('user_role') != 'admin':
        jobs = [j for j in jobs if j.get('user') == _user()]
    return jsonify({'status': 'ok', 'jobs': jobs})


@transcoder_bp.route('/api/transcoder/jobs/<job_id>', methods=['GET'])
@role_required(list(TRANSCODER_ROLES))
def job_detail(job_id):
    job = engine.get_job(job_id)
    if not job or not _can_view(job):
        return jsonify({'status': 'error', 'msg': 'Job tidak ditemukan'}), 404
    return jsonify({'status': 'ok', 'job': job})


# ---------------------------------------------------------------------------
# Cancel / delete
# ---------------------------------------------------------------------------

@transcoder_bp.route('/api/transcoder/jobs/<job_id>/cancel', methods=['POST'])
@role_required(list(TRANSCODER_ROLES))
def cancel(job_id):
    ok, msg = engine.cancel_job(job_id, _user())
    return (jsonify({'status': 'ok', 'msg': msg}) if ok
            else jsonify({'status': 'error', 'msg': msg}), 409)


@transcoder_bp.route('/api/transcoder/jobs/<job_id>', methods=['DELETE'])
@role_required(list(TRANSCODER_ROLES))
def delete(job_id):
    ok, msg = engine.delete_job(job_id, _user())
    return (jsonify({'status': 'ok', 'msg': msg}) if ok
            else jsonify({'status': 'error', 'msg': msg}), 409)


# ---------------------------------------------------------------------------
# Download hasil
# ---------------------------------------------------------------------------

@transcoder_bp.route('/api/transcoder/download/<job_id>/<path:filename>',
                     methods=['GET'])
@role_required(list(TRANSCODER_ROLES))
def download(job_id, filename):
    job = engine.get_job(job_id)
    if not job or not _can_view(job):
        return jsonify({'status': 'error', 'msg': 'Job tidak ditemukan'}), 404
    base = current_app.config.get('TRANSCODE_DIR', '')
    workdir = os.path.join(base, job_id)
    ext = os.path.splitext(filename)[1].lstrip('.').lower()
    if ext not in FORMATS:
        return jsonify({'status': 'error', 'msg': 'Ekstensi tidak diizinkan'}), 400
    allowed = {o['file'] for it in job.get('items', []) for o in it.get('outputs', [])}
    if filename not in allowed:
        return jsonify({'status': 'error', 'msg': 'Berkas bukan hasil job ini'}), 404
    resp = send_from_directory(workdir, filename, as_attachment=True)
    return resp
