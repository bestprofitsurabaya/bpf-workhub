"""Approval Berjenjang (v2.36.0) — ACC atasan sebelum diproses back-office.

Keputusan produk (6 Sep 2026):
- Cakupan  : overtime (driver + OB/Security), klaim BBM (transactions), kasbon.
- Rantai   : BBM & kasbon = Chief Driver (ACC-1) → GA (ACC-2, titik proses
             approve-ga yang sudah ada); overtime = GA HR (ACC-1) → Admin (ACC-2).
- Atasan   : default dari role pengaju (driver→chief_driver, ob→ga_hr),
             override per user via kolom `users.manager_username` (Admin).
- Pengecualian: tidak ada (semua pengajuan lewat atasan).

Desain:
- Tabel `approval_requests` (per DB) sebagai jurnal ACC: subjek
  (doc_type + doc_ref + display_id), pengaju, rantai approver berurutan,
  langkah aktif, status.
- Pengajuan baru → baris approval `pending` di langkah 1.
- decide() mencatat ACC/tolak per langkah; ACC langkah terakhir membuat
  status final `approved`; tolak → `rejected` (alasan wajib, tercatat).
- Gate endpoint back-office: pending → 409 `SUPERVISOR_APPROVAL_REQUIRED`
  (berisi posisi ACC saat ini); rejected → 409 juga.
- Pengaju tidak boleh memutus pengajuannya sendiri.
- Tanpa DB (tes/offline) semua fungsi aman — pola doc_sequences/retention.

Chain step: {'approver': <username | nama>, 'role': <role | None>}.
Langkah ber-role cocok untuk siapa pun memegang role itu (divalidasi
actor_role); langkah ber-nama hanya untuk user tersebut.
"""
import json

from flask import jsonify, request, session

from modules.helpers import client_ip, log_activity_async, role_required
from modules.config import get_master_connection

APPROVAL_CODE = 'SUPERVISOR_APPROVAL_REQUIRED'
APPROVAL_MSG = 'Menunggu persetujuan atasan (approval berjenjang).'

# Rantai default per jenis dokumen (langkah ber-role).
CHAIN_CASH_BBM = ('chief_driver', 'ga')     # ACC-1 Chief Driver, ACC-2 GA (approve-ga)
CHAIN_OVERTIME = ('ga_hr', 'admin')         # ACC-1 GA HR, ACC-2 Admin

# Role pengaju → role atasan default (langkah 1) — override via manager_username.
_ROLE_SUPERVISOR_DEFAULT = {
    'driver': 'chief_driver',
    'ob': 'ga_hr',
    'security': 'ga_hr',  # v2.39: pengaju overtime Security — rantai sama dgn OB
}

DOC_TYPES = ('cash', 'bbm', 'overtime_driver', 'overtime_ob')


def _doc_chain(doc_type):
    return CHAIN_OVERTIME if str(doc_type).startswith('overtime') else CHAIN_CASH_BBM


# ============================================================
# Schema
# ============================================================

def _run(cursor, sql, label):
    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        print(f"[approvals] {label}: {e}")
        return False


def ensure_approval_tables(conn):
    """Buat tabel approval_requests (idempoten). True bila siap."""
    if conn is None:
        return False
    cur = conn.cursor()
    try:
        _run(cur, """
            CREATE TABLE IF NOT EXISTS approval_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                doc_type VARCHAR(20) NOT NULL,
                doc_ref INT NOT NULL,
                display_id VARCHAR(40) DEFAULT '',
                requested_by VARCHAR(100) DEFAULT '',
                requester_role VARCHAR(30) DEFAULT '',
                branch_code VARCHAR(20) DEFAULT '',
                chain JSON NULL,
                step INT NOT NULL DEFAULT 1,
                status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
                decided_by VARCHAR(100) DEFAULT '',
                decided_at DATETIME NULL,
                note VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_appr_doc (doc_type, doc_ref),
                INDEX idx_appr_status (status),
                INDEX idx_appr_doc (doc_type, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """, "approval_requests")
        conn.commit()
        return True
    except Exception as e:
        print(f"[approvals] ensure tables: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _ensure_manager_column(conn):
    """Kolom users.manager_username (override atasan per user) — idempoten."""
    if conn is None:
        return False
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN manager_username VARCHAR(50) DEFAULT NULL")
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass


def ensure_manager_column(conn=None):
    """Dipanggil startup (DB master). True bila kolom siap / sudah ada."""
    return _ensure_manager_column(conn if conn is not None else get_master_connection())


# ============================================================
# Resolusi rantai approver
# ============================================================

def _lookup_supervisor(conn, requester_name):
    """Override atasan: users.manager_username milik pengaju (bila ada).

    JOIN memastikan atasan benar-benar ada & aktif — salah ketik pada kolom
    manager_username tidak boleh menghasilkan langkah yang tak bisa diputus.
    """
    if conn is None or not requester_name:
        return None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT u2.username AS manager FROM users u1 "
            "JOIN users u2 ON u2.username = u1.manager_username AND u2.is_active = TRUE "
            "WHERE (u1.username=%s OR u1.full_name=%s) AND u1.is_active = TRUE LIMIT 1",
            (requester_name, requester_name))
        row = cur.fetchone()
        cur.close()
        if row and row.get('manager'):
            return str(row['manager']).strip() or None
    except Exception:
        pass
    return None


def build_chain(conn, doc_type, requester_name, requester_role):
    """Susun rantai langkah utk pengajuan baru.

    Overtime (driver & OB)  : GA HR → Admin (selalu — tanpa override).
    Kasbon / Klaim BBM      : atasan override (users.manager_username) bila
                              ada, else role atasan default per role pengaju
                              (driver→chief_driver, ob→ga_hr); langkah kedua GA.
    Hasil ≥ 1 langkah.
    """
    default = _doc_chain(doc_type)
    if str(doc_type).startswith('overtime'):
        first = {'approver': default[0], 'role': default[0]}
    else:
        supervisor = _lookup_supervisor(conn, requester_name)
        if supervisor:
            # Override per user: langkah hanya utk orang tsb (tanpa fallback role).
            first = {'approver': supervisor, 'role': None}
        else:
            # Default per role: role diikutkan agar cadangan dgn role sama
            # (mis. chief_driver kedua) juga bisa memutus langkah ini.
            sup_role = _ROLE_SUPERVISOR_DEFAULT.get(requester_role, default[0])
            first = {'approver': sup_role, 'role': sup_role}
    second = {'approver': default[1], 'role': default[1]}
    # Hindari langkah duplikat (mis. override = user ber-role chief_driver).
    if first['role'] == second['role'] or (not first['role'] and first['approver'] == second['role']):
        return [first]
    return [first, second]


def _normalize_chain(raw_chain, doc_type, requester_name, requester_role):
    """Terima chain bentuk apa pun (JSON string / list nama / list dict).

    None / tak terbaca → None (create_approval membangun chain dari DB —
    dgn koneksi asli agar override manager_username tetap berlaku).
    """
    if raw_chain is None:
        return None
    steps = []
    if isinstance(raw_chain, str):
        try:
            raw_chain = json.loads(raw_chain)
        except Exception:
            return None
    if isinstance(raw_chain, list):
        for item in raw_chain:
            if isinstance(item, dict):
                ap = str(item.get('approver', '') or '').strip()
                if ap:
                    steps.append({'approver': ap, 'role': item.get('role') or None})
            else:
                ap = str(item or '').strip()
                if ap:
                    steps.append({'approver': ap, 'role': None})
    return steps or None


# ============================================================
# Penulisan jurnal ACC
# ============================================================

def create_approval(conn, doc_type, doc_ref, display_id='', requested_by='',
                    requester_role='', branch_code='', chain=None):
    """Catat kebutuhan ACC utk dokumen baru (langkah 1, pending).

    Upsert: satu dokumen = satu baris jurnal (uq_appr_doc). Re-submit dokumen
    yang sama (draft diedit & dikirim ulang) me-reset jurnal ke langkah 1
    pending — bukan error duplicate.
    """
    if conn is None or doc_type not in DOC_TYPES or not doc_ref:
        return False
    steps = _normalize_chain(chain, doc_type, requested_by, requester_role)
    if steps is None:
        steps = build_chain(conn, doc_type, requested_by, requester_role)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO approval_requests (doc_type, doc_ref, display_id, requested_by, "
            "requester_role, branch_code, chain, step, status) VALUES (%s,%s,%s,%s,%s,%s,%s,1,'pending') "
            "ON DUPLICATE KEY UPDATE display_id=VALUES(display_id), requested_by=VALUES(requested_by), "
            "requester_role=VALUES(requester_role), branch_code=VALUES(branch_code), "
            "chain=VALUES(chain), step=1, status='pending', decided_by='', decided_at=NULL, note=''",
            (doc_type, doc_ref, display_id or '', requested_by or '', requester_role or '',
             branch_code or '', json.dumps(steps)))
        conn.commit()
        return True
    except Exception as e:
        print(f"[approvals] create: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _load(conn, doc_type, doc_ref):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM approval_requests WHERE doc_type=%s AND doc_ref=%s",
                    (doc_type, doc_ref))
        return cur.fetchone()
    finally:
        try:
            cur.close()
        except Exception:
            pass


def approval_status(conn, doc_type, doc_ref):
    """(status, row): 'pending'/'approved'/'rejected'/None bila tak teregistrasi."""
    row = _load(conn, doc_type, doc_ref)
    if not row:
        return None, None
    return row.get('status'), row


def _row_steps(row):
    """Chain baris jurnal sbg list of dict (JSON string / list / None aman)."""
    try:
        steps = row['chain'] if isinstance(row['chain'], list) else json.loads(row['chain'] or '[]')
    except Exception:
        return []
    return steps if isinstance(steps, list) else []


def current_step(row):
    """Langkah aktif (dict) bila pending — selain itu None.

    Indeks langkah dihitung dari field status/step (bukan cuma `step`) agar
    baris lama / reset tetap konsisten: approved/rejected → tidak ada langkah
    aktif; pending step=1 → langkah pertama; step melebihi panjang chain
    (mis. chain lama lebih pendek) → langkah terakhir.
    """
    if not row or row.get('status') != 'pending':
        return None
    steps = _row_steps(row)
    if not steps:
        return None
    idx = (row.get('step') or 1) - 1
    if idx < 0:
        idx = 0
    elif idx >= len(steps):
        idx = len(steps) - 1
    return steps[idx]


def step_label(step):
    if not step:
        return '?'
    return step.get('approver') or step.get('role') or '?'


def decision_allowed(row, actor, actor_role):
    """True bila actor (username, role sesi) berhak memutus langkah aktif.

    Langkah ber-nama cocok utk user tersebut ATAU siapa pun memegang role
    yang sama dgn user itu — jika tidak, ACC macet saat atasan login pakai
    akun lain dgn role sama (mis. chief_driver cadangan).
    """
    step = current_step(row)
    if not step or not actor:
        return False
    approver = str(step.get('approver', '') or '')
    if approver:
        if approver.lower() == str(actor).lower():
            return True
        if step.get('role'):
            return str(actor_role or '').lower() == str(step['role']).lower()
        # Langkah ber-nama tanpa info role: cocokkan role hanya bila langkah
        # lain di chain memegang role itu (build_chain selamenya mengisi role).
        return False
    if step.get('role'):
        return str(actor_role or '').lower() == str(step['role']).lower()
    return False


def decide(conn, doc_type, doc_ref, decision, actor, actor_role='', note=''):
    """Catat keputusan atasan pada langkah aktif. Return (ok, msg).

    approve  → maju ke langkah berikutnya, atau final 'approved' bila terakhir.
    rejected → status final 'rejected' (pengajuan mati).
    """
    if decision not in ('approved', 'rejected'):
        return False, 'Keputusan tidak valid'
    row = _load(conn, doc_type, doc_ref)
    if not row:
        return False, 'Pengajuan tidak ditemukan'
    if row.get('status') != 'pending':
        return False, 'Pengajuan sudah diproses'
    # Pengecualian: Admin memproses lewat akun yang sama dgn pengaju (nama &
    # role identik) tetapi dgn role sesi berbeda — contoh: Chief Driver
    # mengajukan klaim lalu admin menyetujui dari akun admin-nya. Yang
    # diblokir hanyalah memutus dgn identitas & role yang persis sama.
    if (str(actor or '').lower() == str(row.get('requested_by', '')).lower()
            and str(actor_role or '').lower() == str(row.get('requester_role', '')).lower()):
        return False, 'Pengaju tidak boleh memutus pengajuannya sendiri'
    if not decision_allowed(row, actor, actor_role):
        return False, f'Menunggu persetujuan: {step_label(current_step(row))}'
    steps = _row_steps(row)
    nxt = (row.get('step') or 1) + 1
    cur = conn.cursor()
    try:
        if decision == 'rejected':
            cur.execute("UPDATE approval_requests SET status='rejected', decided_by=%s, "
                        "decided_at=NOW(), note=%s WHERE id=%s",
                        (actor, (note or '')[:500], row['id']))
            conn.commit()
            return True, 'Pengajuan ditolak atasan'
        if nxt <= len(steps):
            cur.execute("UPDATE approval_requests SET step=%s, decided_by=%s, decided_at=NOW(), "
                        "note=%s WHERE id=%s", (nxt, actor, (note or '')[:500], row['id']))
            conn.commit()
            return True, f'ACC langkah {row["step"]} — lanjut ke {step_label(steps[nxt - 1])}'
        cur.execute("UPDATE approval_requests SET status='approved', decided_by=%s, "
                    "decided_at=NOW(), note=%s WHERE id=%s",
                    (actor, (note or '')[:500], row['id']))
        conn.commit()
        return True, 'Semua ACC terpenuhi'
    finally:
        try:
            cur.close()
        except Exception:
            pass


def is_fully_approved(conn, doc_type, doc_ref):
    """True bila sudah lewat seluruh ACC (atau tidak teregistrasi — dokumen lama)."""
    status, _row = approval_status(conn, doc_type, doc_ref)
    return status in (None, 'approved')


def gate_allows(conn, doc_type, doc_ref):
    """Gate endpoint proses back-office.

    Return (True, None) bila boleh diproses; (False, (resp, 409)) bila
    masih pending ACC / telah ditolak atasan.
    """
    row = _load(conn, doc_type, doc_ref) if conn else None
    if row and row.get('status') == 'pending':
        return False, (jsonify({'status': 'error', 'code': APPROVAL_CODE, 'msg': APPROVAL_MSG,
                                'pending_at': step_label(current_step(row))}), 409)
    if row and row.get('status') == 'rejected':
        return False, (jsonify({'status': 'error', 'code': APPROVAL_CODE,
                                'msg': 'Pengajuan ini telah ditolak atasan.'}), 409)
    return True, None


# ============================================================
# Endpoint API (dipasang via register_approval_routes(app))
# ============================================================

def _actor():
    return (session.get('user_name') or session.get('full_name') or ''), (session.get('user_role') or '')


def _requester():
    return (session.get('full_name') or session.get('user_name') or ''), (session.get('user_role') or '')


def register_approval_routes_full(app, role_required):
    """Endpoint jurnal ACC: daftar utk atasan, keputusan, status per dokumen."""

    @app.route('/api/approvals')
    @role_required(['admin', 'ga', 'finance', 'chief_driver', 'ga_hr'])
    def api_approvals_list():
        """Daftar pengajuan menunggu keputusan atasan yang relevan utk sesi."""
        actor, actor_role = _actor()
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            from modules.config import get_db_connection
            bconn = get_db_connection()
            cur = bconn.cursor(dictionary=True)
            cur.execute("SELECT * FROM approval_requests WHERE status='pending' ORDER BY created_at ASC LIMIT 200")
            rows = cur.fetchall()
            cur.close()
            bconn.close()
        except Exception as e:
            try:
                bconn.close()
            except Exception:
                pass
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass
        visible = []
        for r in rows:
            step = current_step(r)
            if step is None:
                continue
            if decision_allowed(r, actor, actor_role) or actor_role == 'admin':
                vis = dict(r)
                vis['chain'] = json.loads(r['chain']) if isinstance(r['chain'], str) else (r['chain'] or [])
                vis['pending_at'] = step_label(step)
                visible.append(vis)
        return jsonify({'status': 'success', 'data': visible})

    @app.route('/api/approvals/<doc_type>/<int:doc_ref>/decision', methods=['POST'])
    @role_required(['admin', 'ga', 'finance', 'chief_driver', 'ga_hr'])
    def api_approvals_decision(doc_type, doc_ref):
        """Catat ACC/tolak atasan pada langkah aktif."""
        if doc_type not in DOC_TYPES:
            return jsonify({'status': 'error', 'msg': 'Jenis dokumen tidak dikenal'}), 404
        data = request.get_json(silent=True) or {}
        decision = 'approved' if str(data.get('decision', '')).lower() in ('approved', 'approve', 'acc') else 'rejected'
        if decision == 'rejected' and not str(data.get('note', '') or '').strip():
            return jsonify({'status': 'error', 'msg': 'Alasan penolakan wajib diisi'}), 400
        actor, actor_role = _actor()
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            from modules.config import get_db_connection
            bconn = get_db_connection()
            try:
                ok, msg = decide(bconn, doc_type, doc_ref, decision, actor, actor_role,
                                 note=str(data.get('note', '') or ''))
                if ok:
                    log_activity_async(0, f'approval_{decision}', actor_role, actor,
                                       new_data={'doc_type': doc_type, 'doc_ref': doc_ref,
                                                 'note': data.get('note', '')},
                                       ip=client_ip())
            finally:
                try:
                    bconn.close()
                except Exception:
                    pass
            return jsonify({'status': 'success' if ok else 'error', 'msg': msg}), (200 if ok else 409)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/approvals/<doc_type>/<int:doc_ref>')
    @role_required(['admin', 'ga', 'finance', 'chief_driver', 'ga_hr'])
    def api_approvals_status(doc_type, doc_ref):
        """Status ACC satu dokumen (untuk badge SPA)."""
        if doc_type not in DOC_TYPES:
            return jsonify({'status': 'error', 'msg': 'Jenis dokumen tidak dikenal'}), 404
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        try:
            from modules.config import get_db_connection
            bconn = get_db_connection()
            try:
                status, row = approval_status(bconn, doc_type, doc_ref)
            finally:
                try:
                    bconn.close()
                except Exception:
                    pass
            if not row:
                return jsonify({'status': 'success', 'approval': None})
            row = dict(row)
            row['chain'] = json.loads(row['chain']) if isinstance(row['chain'], str) else (row['chain'] or [])
            step = current_step(row)
            row['pending_at'] = step_label(step) if step else None
            return jsonify({'status': 'success', 'approval': row})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# Hook integrasi (dipanggil dari endpoint pengajuan & proses)
# ============================================================

def register_approval_routes(app):
    """Pasang endpoint jurnal ACC ke Flask app (tanpa argumen role)."""
    register_approval_routes_full(app, role_required)


def hook_create_approval(conn, doc_type, doc_ref, display_id='', role='', best_effort=True):
    """Catat ACC utk pengajuan baru dari endpoint submit (best-effort).

    Identitas pengaju & cabang dari sesi login.    Kegagalan (DB down, tabel
    belum siap) TIDAK boleh menggagalkan pengajuan bisnis itu — gate
    fail-open akan mengizinkan proses bila jurnal tidak tercatat.
    """
    try:
        if not conn:
            return False
        requester = (session.get('full_name') or session.get('user_name') or '')
        role = (role or session.get('user_role') or '')
        branch = (session.get('branch_code') or '')
        chain = build_chain(conn, doc_type, requester, role)
        return create_approval(conn, doc_type, doc_ref, display_id=display_id,
                               requested_by=requester, requester_role=role,
                               branch_code=branch, chain=chain)
    except Exception as e:
        if not best_effort:
            raise
        print(f"[approvals] hook create {doc_type}#{doc_ref}: {e}")
        return False


def gate_approval(conn, doc_type, doc_ref):
    """Guard endpoint proses back-office (approve/pay/edit-final).

    Pending/tolak ACC → 409 JSON (response Flask siap-return); lolos/tidak
    teregistrasi/DB down → (True, None). Pola fail-open seperti step-up.
    """
    try:
        return gate_allows(conn, doc_type, doc_ref)
    except Exception as e:
        print(f"[approvals] gate {doc_type}#{doc_ref}: {e}")
        return True, None
