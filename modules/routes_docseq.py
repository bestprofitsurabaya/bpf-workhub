"""API Admin — Nomor Dokumen (doc_sequences) v2.29.11.

Admin dapat melihat nomor urut dokumen per cabang (tabel doc_sequences di DB
master / DB tiap cabang) dan me-reset penghitung — berguna di awal hari,
setelah uji coba, atau koreksi nomor. Nomor berikutnya setelah reset akan
dialokasikan mulai dari 0001 lagi.

Keamanan: seluruh endpoint admin-only (role_required(['admin'])), menulis
jejak audit (log_activity_async) per aksi reset.
"""
from flask import request, jsonify, session

from modules.config import DB_CONFIG, get_master_connection, _pool_for
from modules.helpers import role_required, log_activity_async
from modules import branch_manager as bm
from modules.admin_scope import is_ho_admin, admin_branches, scope_denied_response

# Label prefix untuk tampilan Admin (mapping kode → dokumen).
PREFIX_LABELS = {
    'WTR': 'Tanda Terima Air Minum',
    'BPF': 'Transaksi BBM',
    'CASH': 'Kasbon / LPJ',
    'TRIP': 'Trip',
    'APP': 'Kunjungan Marketing',
    'PLM': 'Pendaftaran Pelamar',
    'OTL': 'Overtime OB / Security',
    'OTD': 'Overtime Driver',
}


def _branch_conn(branch):
    """Koneksi ke DB cabang (master utk cabang utama, pool utk cabang lain)."""
    db = branch.get('db_name') or ''
    if db == DB_CONFIG['database']:
        return get_master_connection()
    pool = _pool_for(db)
    return pool.get_connection() if pool else None


def parse_seq_key(seq_key):
    """Parse 'SBY|WTR|20260905' -> (branch, prefix, date). Tahan format tak dikenal."""
    parts = str(seq_key or '').split('|')
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ''
    return (parts[0] if parts else ''), '', ''


def read_sequences(branch):
    """Baca semua baris doc_sequences satu cabang (list dict siap JSON)."""
    conn = _branch_conn(branch)
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT seq_key, seq FROM doc_sequences ORDER BY seq_key")
        rows = cur.fetchall()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    out = []
    for r in rows:
        b, p, d = parse_seq_key(r['seq_key'])
        out.append({
            'seq_key': r['seq_key'],
            'branch': b,
            'prefix': p,
            'prefix_label': PREFIX_LABELS.get(p, p or '—'),
            'date': d,
            'seq': int(r.get('seq') or 0),
        })
    return out


def reset_sequences(branch, prefix, date=''):
    """Hapus baris doc_sequences (counter direset → nomor berikutnya 0001).

    - date diisi  → hanya tanggal tsb (seq_key persis).
    - date kosong → semua tanggal utk (cabang, prefix).

    Return jumlah baris terhapus.
    """
    conn = _branch_conn(branch)
    if not conn:
        raise RuntimeError(f'DB cabang {branch.get("code")} tidak tersedia')
    cur = conn.cursor()
    try:
        if date:
            cur.execute("DELETE FROM doc_sequences WHERE seq_key=%s",
                        (f'{branch.get("code")}|{prefix}|{date}',))
        else:
            cur.execute("DELETE FROM doc_sequences WHERE seq_key LIKE %s",
                        (f'{branch.get("code")}|{prefix}|%',))
        n = int(cur.rowcount or 0)
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    return n


def register_docseq_routes(app):

    @app.route('/api/admin/doc-sequences')
    @role_required(['admin'])
    def api_doc_sequences():
        """Daftar nomor urut dokumen per cabang (semua prefix).

        v2.37.0: Admin cabang (`admin_<kode>`) hanya melihat cabangnya;
        Admin Pusat melihat semua cabang.
        """
        try:
            branches = bm.list_branches()
            if not is_ho_admin():
                allowed, _ = admin_branches()
                branches = [b for b in branches if b['code'] in allowed]
            result = []
            for b in branches:
                try:
                    seqs = read_sequences(b) if b.get('is_active') else []
                except Exception as e:
                    print(f'[docseq] baca {b.get("code")} gagal: {e}')
                    seqs = []
                result.append({
                    'code': b['code'],
                    'name': b['name'],
                    'db_name': b.get('db_name') or '',
                    'is_active': bool(b.get('is_active')),
                    'sequences': seqs,
                })
            return jsonify({'branches': result})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/admin/doc-sequences/reset', methods=['POST'])
    @role_required(['admin'])
    def api_doc_sequences_reset():
        """Reset penghitung nomor dokumen utk (cabang, prefix[, tanggal])."""
        try:
            if not is_ho_admin():
                allowed, _ = admin_branches()
                data = request.get_json(silent=True) or {}
                code = str(data.get('branch_code', '') or '').strip().upper()
                if code not in allowed:
                    return scope_denied_response()
            data = request.get_json(silent=True) or {}
            code = str(data.get('branch_code', '') or '').strip().upper()
            prefix = str(data.get('prefix', '') or '').strip().upper()
            date = str(data.get('date', '') or '').strip()
            if not code or not prefix:
                return jsonify({'status': 'error', 'msg': 'branch_code dan prefix wajib diisi'}), 400
            if date and not (len(date) == 8 and date.isdigit()):
                return jsonify({'status': 'error', 'msg': 'format tanggal harus YYYYMMDD'}), 400
            branch = bm.get_branch(code)
            if not branch:
                return jsonify({'status': 'error', 'msg': 'Cabang tidak ditemukan'}), 404
            n = reset_sequences(branch, prefix, date)
            actor = session.get('full_name') or session.get('user_name') or 'Admin'
            log_activity_async(0, 'doc_seq_reset', 'admin', actor,
                               new_data={'branch': code, 'prefix': prefix,
                                         'date': date or 'semua', 'deleted': n},
                               ip=request.remote_addr, branch_code=code)
            scope = f'tanggal {date}' if date else 'semua tanggal'
            return jsonify({'status': 'success',
                            'msg': f'Counter {prefix} cabang {code} ({scope}) direset — '
                                    f'{n} baris dihapus. Nomor berikutnya mulai dari 0001.'})
        except Exception as e:
            print(f'[docseq] reset error: {e}')
            return jsonify({'status': 'error', 'msg': str(e)}), 500