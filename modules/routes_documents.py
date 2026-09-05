"""API Dokumen — verifikasi integritas & registri (v2.35.0 — Tahap 6/6 ISO).

- `POST /api/documents/verify`  — upload PDF (multipart 'file'); hash SHA-256
  dihitung ulang lalu dicocokkan dengan `document_registry`. Diketik
  (semua role login) karena verifikasi dipakai user yang menerima dokumen.
- `GET /api/admin/documents`     — daftar registri dokumen (admin only).

Verifikasi membuktikan: dokumen utuh (tidak diubah sejak diterbitkan),
kapan diterbitkan, dan siapa penandatangannya (A.8.2 / ISO 15489 keaslian).
"""

import io

from flask import jsonify, request, session

from modules import doc_integrity as di
from modules.helpers import role_required, log_activity_async, client_ip

# Batas unggahan verifikasi: 20 MB (PDF foto tinggi bisa beberapa MB).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def register_document_routes(app):

    @app.route('/api/documents/verify', methods=['POST'])
    @role_required(['admin', 'ga', 'finance', 'ga_hr', 'chief_driver',
                    'marketing', 'receptionist', 'ob', 'traineer'])
    def api_document_verify():
        """Verifikasi PDF terhadap registri integritas dokumen."""
        f = request.files.get('file')
        if f is None or not f.filename:
            return jsonify({'status': 'error', 'msg': 'Lampirkan file PDF untuk diverifikasi'}), 400
        name = (f.filename or '').strip()
        if not name.lower().endswith('.pdf'):
            return jsonify({'status': 'error', 'msg': 'Hanya file PDF yang didukung'}), 400
        data = f.read()
        if not data:
            return jsonify({'status': 'error', 'msg': 'File kosong'}), 400
        if len(data) > MAX_UPLOAD_BYTES:
            return jsonify({'status': 'error', 'msg': 'File terlalu besar (maks 20 MB)'}), 400

        row = di.lookup_pdf(data)
        role = session.get('user_role', '')
        log_activity_async(0, 'document_verify', role,
                           session.get('full_name') or session.get('user_name') or '',
                           new_data={'filename': name, 'found': bool(row)},
                           ip=client_ip())
        if not row:
            return jsonify({'status': 'success', 'found': False,
                            'msg': 'Dokumen TIDAK terdaftar di registri integritas. '
                                   'Tidak bisa dipastikan keasliannya (mungkin bukan dokumen resmi '
                                   'yang diterbitkan sistem, atau sudah diubah).'})
        return jsonify({'status': 'success', 'found': True,
                        'document': di._row_to_dict(row),
                        'msg': 'Dokumen VALID — utuh sejak diterbitkan dan cocok dengan registri.'})

    @app.route('/api/admin/documents')
    @role_required(['admin'])
    def api_admin_documents():
        """Daftar registri dokumen (terbaru dulu), filter doc_type/q."""
        q = str(request.args.get('q', '') or '').strip()
        limit = min(int(request.args.get('limit', 50) or 50), 200)
        conn = None
        try:
            from modules.config import get_master_connection
            conn = get_master_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
            cur = conn.cursor(dictionary=True)
            try:
                where, params = [], []
                if q:
                    like = f'%{q}%'
                    where.append('(doc_no LIKE %s OR doc_type LIKE %s OR signer_name LIKE %s OR filename LIKE %s)')
                    params += [like, like, like, like]
                sql = ("SELECT id, doc_type, doc_no, branch_code, sha256, bytes_size, "
                       "filename, signer_name, signer_role, meta, created_at "
                       "FROM document_registry")
                if where:
                    sql += ' WHERE ' + ' AND '.join(where)
                sql += ' ORDER BY id DESC LIMIT %s'
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()
                return jsonify({'status': 'success', 'documents': [di._row_to_dict(r) for r in rows],
                                'count': len(rows)})
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
        except Exception as e:
            print(f'[documents] list error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
