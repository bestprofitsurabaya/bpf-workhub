"""Integritas & siklus hidup dokumen (v2.35.0 — Tahap 6/6 ISO/IEC 27001).

Kontrol ISO/IEC 27001:2022 / ISO 15489:
- A.8.2 / A.8.9  — memastikan dokumen tidak berubah tanpa terdeteksi.
- A.8.24 / ISO 15489 — keaslian (authenticity) dokumen: siapa membuat,
  kapan, dan isi tidak diubah sejak diterbitkan.

Cara kerja:
1. Saat PDF resmi dibuat (mis. Tanda Terima Air Minum, Form Permohonan
   Overtime, laporan detail), aplikasi memanggil `register_pdf(...)`:
   hash SHA-256 dari byte PDF + penandatangan (nama & role) + timestamp +
   nomor dokumen disimpan di tabel `document_registry` (DB master).
2. `POST /api/documents/verify` menghitung ulang hash dari file yang
   di-upload lalu mencocokkan dengan registri — membuktikan dokumen itu
   asli & utuh (tidak diubah sejak diterbitkan), siapa menerbitkannya,
   dan kapan.

Pencatatan bersifat best-effort: bila DB sedang bermasalah, PDF tetap
dihasilkan — integritas hanya tercatat bila registri bisa ditulis.
"""

import hashlib
import os
from datetime import datetime

# Tabel registri dibuat di DB master (dokumen lintas cabang dicatat dengan
# kolom branch_code). DDL idempoten — aman dijalankan berulang.
_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS document_registry (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doc_type VARCHAR(40) NOT NULL,
    doc_no VARCHAR(80) NOT NULL,
    branch_code VARCHAR(10) DEFAULT '',
    sha256 CHAR(64) NOT NULL,
    bytes_size INT UNSIGNED NOT NULL DEFAULT 0,
    filename VARCHAR(255) DEFAULT '',
    signer_name VARCHAR(150) DEFAULT '',
    signer_role VARCHAR(40) DEFAULT '',
    meta JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_sha256 (sha256),
    KEY idx_doc_no (doc_no),
    KEY idx_doc_type (doc_type),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_document_registry(conn=None):
    """CREATE TABLE IF NOT EXISTS document_registry (master) — idempoten."""
    own = conn is None
    if conn is None:
        from modules.config import get_master_connection
        conn = get_master_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(_REGISTRY_DDL)
        conn.commit()
        return True
    except Exception as e:
        print(f'⚠ document_registry ensure error: {e}')
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def register_pdf(doc_type, doc_no, pdf_bytes, signer_name='', signer_role='',
                 branch_code='', filename='', meta=None):
    """Catat PDF yang baru dibuat ke registri integritas (best-effort).

    Return dict registri bila tersimpan, None bila gagal (tidak fatal).
    """
    if not pdf_bytes:
        return None
    try:
        from modules.config import get_master_connection
        import json as _json
        conn = get_master_connection()
        if not conn:
            return None
        sha = _sha256(pdf_bytes)
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO document_registry "
                "(doc_type, doc_no, branch_code, sha256, bytes_size, filename, "
                " signer_name, signer_role, meta, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE doc_no=VALUES(doc_no)",
                (doc_type[:40], str(doc_no)[:80], (branch_code or '')[:10],
                 sha, len(pdf_bytes), str(filename or '')[:255],
                 str(signer_name or '')[:150], str(signer_role or '')[:40],
                 _json.dumps(meta) if meta else None,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            return {'sha256': sha, 'doc_type': doc_type, 'doc_no': doc_no}
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[doc-integrity] register error ({doc_type} {doc_no}): {e}')
        return None


def lookup_pdf(pdf_bytes):
    """Cari dokumen di registri berdasarkan hash byte PDF.

    Return dict (row registri) atau None bila tidak terdaftar.
    """
    if not pdf_bytes:
        return None
    try:
        from modules.config import get_master_connection
        conn = get_master_connection()
        if not conn:
            return None
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT id, doc_type, doc_no, branch_code, sha256, bytes_size, "
                "filename, signer_name, signer_role, meta, created_at "
                "FROM document_registry WHERE sha256=%s",
                (_sha256(pdf_bytes),))
            row = cur.fetchone()
            return row
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[doc-integrity] lookup error: {e}')
        return None


def _row_to_dict(r):
    import json as _json
    meta = r.get('meta')
    if isinstance(meta, str):
        try:
            meta = _json.loads(meta)
        except Exception:
            meta = None
    return {
        'id': r['id'],
        'doc_type': r['doc_type'],
        'doc_no': r['doc_no'],
        'branch_code': r.get('branch_code') or '',
        'sha256': r['sha256'],
        'bytes_size': int(r.get('bytes_size') or 0),
        'filename': r.get('filename') or '',
        'signer_name': r.get('signer_name') or '',
        'signer_role': r.get('signer_role') or '',
        'meta': meta,
        'created_at': str(r['created_at']) if r.get('created_at') else '',
    }
