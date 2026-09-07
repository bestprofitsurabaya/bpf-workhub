"""Retensi & Arsip Dokumen (v2.34.0 — Tahap 5/6 ISO/IEC 27001).

Kontrol ISO/IEC 27001:2022, ISO 15489-1, dan UU PDP:
- A.8.2 / A.8.10 — data pribadi (mis. pelamar) tidak disimpan lebih lama
  dari yang dibutuhkan (data minimization).
- ISO 15489-1 — dokumen direkam, dipelihara, lalu dimusnahkan/diserahkan
  sesuai jadwal retensi; jejak disposisi tercatat.
- A.5.28 — arsip audit trail: jejak audit dipindah ke tabel arsip
  (`activity_logs_archive`) setelah lewat masa aktif, bukan dihapus.

Fitur (admin-only):
1. `GET  /api/admin/retention/overview` — kebijakan retensi per kelas
   dokumen + inventaris live lintas DB (master + tiap cabang): jumlah
   baris, tanggal tertua/terbaru, dan estimasi baris yang sudah lewat
   masa retensi.
2. `POST /api/admin/retention/archive-audit` — ARSIPKAN audit trail lebih
   tua dari N hari (default 5 tahun): dipindah ke `activity_logs_archive`
   di DB yang sama (utuh & awet), lalu dihapus dari tabel aktif. Semua
   tindakan dicatat di `retention_actions` + audit `retention_audit_archive`.

Penghancuran data bisnis (transaksi/OT/air/pelamar) TIDAK diotomatisasi di
kode — sesuai RETENTION_POLICY.md, pemusnahan harus lewat persetujuan
manajemen dan dieksekusi manual setelah arsip diverifikasi.
"""

import os
from datetime import datetime, timedelta

from flask import jsonify, request, session

from modules.config import DB_CONFIG, get_master_connection, _pool_for
from modules.helpers import role_required, log_activity_async, client_ip
from modules import branch_manager as bm
from modules.admin_scope import is_ho_admin, scope_denied_response

# ================================================================
# Kebijakan retensi per kelas dokumen
# ================================================================
# scope 'all' = tabel ada di master + tiap DB cabang (skema disinkron).
# action 'archive' = kelas yang punya mekanisme arsip otomatis (di kode).
# retention_days None = permanen (mis. dokumen keuangan — keputusan manajemen).
RETENTION_CLASSES = [
    {'key': 'audit_logs', 'label': 'Audit trail (activity_logs)',
     'table': 'activity_logs', 'date_col': 'created_at', 'scope': 'all',
     'action': 'archive', 'default_days': 1825,
     'note': 'Jejak audit dipindah ke tabel arsip setelah masa aktif (A.5.28).'},
    {'key': 'overtime_driver', 'label': 'Overtime Driver (sesi)',
     'table': 'overtime_driver', 'date_col': 'tanggal', 'scope': 'all',
     'action': 'none', 'default_days': 1825,
     'note': 'Rekap kehadiran/klaim — data kepegawaian.'},
    {'key': 'overtime_ob', 'label': 'Overtime OB/Security (sesi)',
     'table': 'overtime_ob_security', 'date_col': 'tanggal', 'scope': 'all',
     'action': 'none', 'default_days': 1825,
     'note': 'Rekap kehadiran/klaim — data kepegawaian.'},
    {'key': 'water', 'label': 'Air minum (pengajuan + foto)',
     'table': 'water_purchases', 'date_col': 'purchase_date', 'scope': 'all',
     'action': 'none', 'default_days': 1825,
     'note': 'Bukti pengeluaran operasional.'},
    {'key': 'transactions', 'label': 'Transaksi BBM',
     'table': 'transactions', 'date_col': 'created_at', 'scope': 'all',
     'action': 'none', 'default_days': None,
     'note': 'Dokumen keuangan — retensi permanen sesuai kebijakan manajemen.'},
    {'key': 'applicants', 'label': 'Pelamar kerja (data pribadi)',
     'table': 'applicants', 'date_col': 'created_at', 'scope': 'all',
     'action': 'none', 'default_days': 730,
     'note': 'Data pribadi — tidak disimpan lebih lama dari kebutuhan (UU PDP).'},
]

_ARCHIVE_DDL = """
CREATE TABLE IF NOT EXISTS activity_logs_archive (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NULL,
    action VARCHAR(50) NOT NULL,
    user_type VARCHAR(20) NOT NULL,
    user_name VARCHAR(100),
    old_data JSON,
    new_data JSON,
    ip_address VARCHAR(45),
    user_agent TEXT,
    branch_code VARCHAR(10) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_created (created_at),
    KEY idx_action (action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_REGISTER_DDL = """
CREATE TABLE IF NOT EXISTS retention_actions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_key VARCHAR(40) NOT NULL,
    action VARCHAR(20) NOT NULL,
    db_name VARCHAR(80) NOT NULL,
    cutoff_date VARCHAR(30) DEFAULT '',
    rows_affected INT UNSIGNED NOT NULL DEFAULT 0,
    actor VARCHAR(150) DEFAULT '',
    note VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_class (class_key),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _env_days(cls):
    """Hari retensi efektif kelas: env `RETENTION_DAYS_<KEY>` > default."""
    val = os.environ.get(f"RETENTION_DAYS_{cls['key'].upper()}")
    if val:
        try:
            return max(0, int(val))
        except ValueError:
            pass
    return cls['default_days']


def _cutoff_datetime(days):
    """Batas waktu 'lebih tua dari N hari' (datetime, tanpa timezone)."""
    return datetime.now() - timedelta(days=max(0, int(days)))


def ensure_retention_tables(conn):
    """CREATE TABLE IF NOT EXISTS activity_logs_archive + retention_actions."""
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(_ARCHIVE_DDL)
        cur.execute(_REGISTER_DDL)
        conn.commit()
        return True
    except Exception as e:
        print(f'⚠ retention tables ensure error: {e}')
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _all_dbs():
    """Daftar (db_name, is_master) — master + cabang aktif yang punya DB."""
    dbs = [(DB_CONFIG['database'], True)]
    try:
        for b in bm.list_branches():
            if b.get('is_active') and b.get('db_name') and b['db_name'] != DB_CONFIG['database']:
                dbs.append((b['db_name'], False))
    except Exception as e:
        print(f'[retention] list branches error: {e}')
    return dbs


def _open_db(db_name, is_master):
    """Koneksi ke DB (master via get_master_connection, cabang via pool)."""
    if is_master:
        return get_master_connection()
    pool = _pool_for(db_name)
    return pool.get_connection() if pool else None


def _class_meta(cls, rows_meta=None):
    """Metadata kelas utk JSON: kebijakan + (opsional) agregat inventaris."""
    days = _env_days(cls)
    meta = {
        'key': cls['key'],
        'label': cls['label'],
        'table': cls['table'],
        'date_col': cls['date_col'],
        'action': cls['action'],
        'retention_days': days if cls['default_days'] is not None else None,
        'permanent': cls['default_days'] is None,
        'note': cls['note'],
    }
    if rows_meta is not None:
        meta.update(rows_meta)
    return meta


def _db_inventory(conn, cls):
    """Inventaris satu (DB, kelas): count, oldest, newest, expired estimate.

    Return dict {db, count, oldest, newest, expired} — None bila tabel/DB
    bermasalah (tidak menggagalkan overview).
    """
    try:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(f"SELECT COUNT(*) AS c, MIN({cls['date_col']}) AS mn, "
                        f"MAX({cls['date_col']}) AS mx FROM {cls['table']}")
            r = cur.fetchone() or {}
            count = int(r.get('c') or 0)
            expired = None
            days = _env_days(cls)
            if count and cls['default_days'] is not None:
                cur.execute(f"SELECT COUNT(*) AS c FROM {cls['table']} "
                            f"WHERE {cls['date_col']} < %s",
                            (_cutoff_datetime(days).strftime('%Y-%m-%d %H:%M:%S'),))
                expired = int((cur.fetchone() or {}).get('c') or 0)
            return {'count': count,
                    'oldest': str(r['mn']) if r.get('mn') else '',
                    'newest': str(r['mx']) if r.get('mx') else '',
                    'expired': expired}
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as e:
        print(f"[retention] inventory {cls['key']} error: {e}")
        return None


def archive_audit_db(conn, cutoff):
    """Arsipkan activity_logs < cutoff di satu DB → activity_logs_archive.

    Return (rows_archived, cutoff_str) atau (0, cutoff_str) bila tidak ada /
    error tabel. Memakai transaksi: INSERT...SELECT lalu DELETE.
    """
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO activity_logs_archive "
                    "(transaction_id, action, user_type, user_name, old_data, "
                    " new_data, ip_address, user_agent, branch_code, created_at) "
                    "SELECT transaction_id, action, user_type, user_name, old_data, "
                    " new_data, ip_address, user_agent, branch_code, created_at "
                    "FROM activity_logs WHERE created_at < %s", (cutoff_str,))
        inserted = int(cur.rowcount or 0)
        if inserted:
            cur.execute("DELETE FROM activity_logs WHERE created_at < %s", (cutoff_str,))
            conn.commit()
        return inserted, cutoff_str
    except Exception as e:
        print(f'[retention] archive audit error: {e}')
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _record_action(conn, class_key, action, db_name, cutoff, rows, actor, note=''):
    """Catat tindakan retensi di register `retention_actions` (master)."""
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO retention_actions (class_key, action, db_name, "
                "cutoff_date, rows_affected, actor, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (class_key, action, db_name, cutoff, rows, actor, note))
            conn.commit()
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[retention] register action error: {e}')


def _session_name():
    return (session.get('full_name') or session.get('user_name') or 'Admin').strip()


def register_retention_routes(app):

    @app.route('/api/admin/retention/overview')
    @role_required(['admin'])
    def api_retention_overview():
        """Kebijakan retensi + inventaris live per kelas (master + cabang).

        v2.37.0: endpoint ini menyentuh DB semua cabang — khusus Admin Pusat.
        """
        if not is_ho_admin():
            return scope_denied_response()
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
        try:
            ensure_retention_tables(conn)
            classes = []
            for cls in RETENTION_CLASSES:
                dbs = []
                total = 0
                for db_name, is_master in _all_dbs():
                    try:
                        c = _open_db(db_name, is_master)
                        if not c:
                            continue
                        try:
                            inv = _db_inventory(c, cls)
                            if inv:
                                inv['db'] = db_name
                                dbs.append(inv)
                                total += int(inv['count'] or 0)
                        finally:
                            try:
                                c.close()
                            except Exception:
                                pass
                    except Exception as e:
                        print(f'[retention] {cls["key"]} {db_name}: {e}')
                classes.append(_class_meta(cls, {
                    'total': total,
                    'per_db': dbs,
                }))
            # Tindakan arsip terakhir (register) utk ringkasan.
            cur = conn.cursor(dictionary=True)
            try:
                cur.execute("SELECT id, class_key, action, db_name, cutoff_date, "
                            "rows_affected, actor, created_at, note "
                            "FROM retention_actions ORDER BY id DESC LIMIT 20")
                actions = cur.fetchall()
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
            return jsonify({'status': 'success', 'classes': classes,
                            'actions': actions,
                            'policy_doc': 'RETENTION_POLICY.md'})
        except Exception as e:
            print(f'[retention] overview error: {e}')
            return jsonify({'status': 'error', 'msg': 'Terjadi kesalahan server'}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/admin/retention/archive-audit', methods=['POST'])
    @role_required(['admin'])
    def api_retention_archive_audit():
        """Arsipkan audit trail lebih tua dari N hari di semua DB (master+cabang).

        v2.37.0: aksi lintas cabang — khusus Admin Pusat.
        """
        if not is_ho_admin():
            return scope_denied_response()
        data = request.get_json(silent=True) or {}
        data = request.get_json(silent=True) or {}
        cls = next((c for c in RETENTION_CLASSES if c['key'] == 'audit_logs'), None)
        if not cls:
            return jsonify({'status': 'error', 'msg': 'Kelas audit_logs tidak terdefinisi'}), 500
        days = cls['default_days']
        if 'days' in data:
            try:
                days = max(30, int(data['days']))  # minimal 30 hari — anti salah-klik
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'msg': 'days harus angka (hari)'}), 400
        cutoff = _cutoff_datetime(days)
        actor = _session_name()

        master = get_master_connection()
        if not master:
            return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
        results, total = [], 0
        for db_name, is_master in _all_dbs():
            try:
                c = _open_db(db_name, is_master)
                if not c:
                    results.append({'db': db_name, 'status': 'skip', 'rows': 0,
                                    'msg': 'koneksi tidak tersedia'})
                    continue
                try:
                    ensure_retention_tables(c)
                    rows, cutoff_str = archive_audit_db(c, cutoff)
                    total += rows
                    # Register tindakan (master) — sekali per DB yang diarsip.
                    _record_action(master, 'audit_logs', 'archive', db_name,
                                   cutoff_str, rows, actor,
                                   note=f'arsip > {days} hari')
                    results.append({'db': db_name, 'status': 'ok', 'rows': rows})
                finally:
                    try:
                        c.close()
                    except Exception:
                        pass
            except Exception as e:
                print(f'[retention] archive {db_name} error: {e}')
                results.append({'db': db_name, 'status': 'error', 'rows': 0, 'msg': str(e)})

        log_activity_async(0, 'retention_audit_archive', 'admin', actor,
                           new_data={'days': days, 'rows': total,
                                     'cutoff': cutoff.strftime('%Y-%m-%d %H:%M:%S')},
                           ip=client_ip())
        return jsonify({'status': 'success',
                        'msg': f'{total} baris audit trail (> {days} hari) dipindah '
                                f'ke arsip di seluruh DB.',
                        'cutoff': cutoff.strftime('%Y-%m-%d %H:%M:%S'),
                        'days': days, 'total_rows': total, 'results': results})
