"""Routes rilis APK BPF Agenda (v2.125.0).

Publik, read-only, dipakai aplikasi Android untuk cek & unduh pembaruan:

    GET /api/app/latest
    GET /api/app/download/<nama-file>.apk

Keduanya juga dibuka lewat bridge nginx port 8444. Tanpa login karena aplikasi
belum punya sesi WorkHub; isi yang dilayani hanya APK rilis internal.
"""
from flask import jsonify, send_file

from modules import app_release


def register_app_release_routes(app):

    @app.route('/api/app/latest')
    def api_app_latest():
        try:
            data = app_release.latest_release()
        except app_release.ReleaseError as exc:
            resp = jsonify({'ok': False, 'error': str(exc)})
            resp.status_code = 404
            resp.headers['Cache-Control'] = 'no-store'
            return resp
        resp = jsonify(data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/api/app/download/<path:filename>')
    def api_app_download(filename):
        try:
            path = app_release.resolve_apk(filename)
            meta = app_release.latest_release()
        except app_release.ReleaseError:
            return jsonify({'ok': False, 'error': 'file APK tidak ditemukan'}), 404
        # File yang diminta harus sama dengan rilis aktif (tidak membuka
        # APK lama yang mungkin masih tersimpan di folder).
        if meta['file'] != filename:
            return jsonify({'ok': False, 'error': 'rilis tidak aktif'}), 404
        resp = send_file(
            path,
            mimetype='application/vnd.android.package-archive',
            as_attachment=True,
            download_name=filename,
            conditional=True,
            max_age=0,
        )
        resp.headers['X-Checksum-SHA256'] = meta['sha256']
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
