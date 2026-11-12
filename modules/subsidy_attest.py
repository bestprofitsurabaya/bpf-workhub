"""v2.51.0 — Berita Acara Rekonsiliasi Klaim BBM ↔ Riwayat SPBU Subsidi Tepat.

Dokumen resmi untuk kantor pusat. Kekuatan bukti bertingkat:
  1. Setiap baris membawa nomor resmi sistem Pertamina (transactionId,
     timestamp server SPBU, verifikasi QR) — dapat dicerminkan HQ langsung
     di portal subsiditepat.mypertamina.id → Riwayat Transaksi.
  2. Rantai hash SHA-256 berantai (hash_n = sha256(hash_n-1 + record_n));
     ROOT ditulis di PDF — mengubah satu angka di DB → root tidak cocok.
  3. Snapshot mentah JSON tarikan portal diarsip read-only + hash; klik dua
     salinan (DB vs arsip) yang beda = fraud ketahuan.
  4. TTD bertingkat: nama GA (verifikasi masuk) + Finance (verifikator final,
     step-up PIN tercatat) dari audit trail, bukan diketik manual.

Output: PDF landscape + file snapshot JSON + baris registry
`subsidy_attestations` (MASTER DB). Endpoint (routes_subsidy.py):
  - POST /api/subsidy/attest          (finance/admin) buat BA untuk periode
  - GET  /api/subsidy/attest          daftar BA terakhir
  - GET  /api/subsidy/attest/<id>/pdf unduh PDF
"""
import hashlib
import json
import os
from datetime import datetime

from modules.config import get_db_connection, get_master_connection

# ============================================================
# Schema — registry di MASTER (BA bersifat lintas cabang)
# ============================================================

_ATTEST_DDL = """
CREATE TABLE IF NOT EXISTS subsidy_attestations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    record_count INT NOT NULL,
    root_hash CHAR(64) NOT NULL,
    manifest_json LONGTEXT,
    snapshot_sha256 CHAR(64) NULL,
    snapshot_path VARCHAR(255) NULL,
    pdf_path VARCHAR(255) NULL,
    generated_by VARCHAR(80) NOT NULL,
    -- v2.99.1: BA adalah milik satu cabang; registry di master tapi daftar &
    -- unduhannya tidak boleh lintas cabang (kecuali Admin Pusat/Finance HO).
    branch_code VARCHAR(20) DEFAULT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_period (period_start, period_end),
    KEY idx_generated (generated_at),
    KEY idx_branch (branch_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_attestation_schema(conn=None):
    """Idempoten SATU DB (master)."""
    own = conn is None
    if conn is None:
        from modules.config import get_master_connection as gm
        conn = gm()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(_ATTEST_DDL)
        # Kolom baru untuk DB yang tabelnya sudah ada (idempoten).
        try:
            cur.execute(
                "ALTER TABLE subsidy_attestations "
                "ADD COLUMN IF NOT EXISTS branch_code VARCHAR(20) DEFAULT NULL")
        except Exception:
            pass
        conn.commit()
        return True
    finally:
        cur.close()
        if own:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# Inti: data builder + rantai hash
# ============================================================

def _canonical(obj):
    """JSON kanonik deterministik — wajib untuk hash yang stabil."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def _sha256_hex(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def build_attestation(period_start, period_end, actor):
    """Bangun data BA untuk periode [start, end] (tanggal taut finance).

    Klaim yang disertakan: transactions.subsidy_tx_id NOT NULL dan
    subsidy_linked_at di dalam periode (keputusan verifikasi Finance).
    Return dict data BA atau raise ValueError.
    """
    conn = get_db_connection()
    if not conn:
        raise ValueError('DB cabang tidak tersedia')
    rows = []
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT t.id, t.display_id, t.driver_name, t.nopol, t.vehicle_type, "
            "       t.bbm_type, t.liter, t.nominal, t.odo_km, t.ga_approved_by, "
            "       t.finance_payout_by, t.status, "
            "       t.subsidy_tx_id, t.subsidy_linked_by, t.subsidy_linked_at, "
            "       t.created_at AS claim_created "
            "FROM transactions t "
            "WHERE t.subsidy_tx_id IS NOT NULL AND t.subsidy_linked_by IS NOT NULL "
            "  AND t.subsidy_linked_at >= %s AND t.subsidy_linked_at < %s + INTERVAL 1 DAY "
            "ORDER BY t.subsidy_linked_at ASC, t.id ASC",
            (period_start, period_end))
        rows = cur.fetchall()
    finally:
        cur.close()
        try:
            conn.close()
        except Exception:
            pass
    if not rows:
        raise ValueError('Tidak ada klaim tertaut Subsidi Tepat di periode ini')

    # Join raw SPBU dari master
    m = get_master_connection()
    if not m:
        raise ValueError('DB master tidak tersedia')
    spbu_ids = tuple(r['subsidy_tx_id'] for r in rows)
    cur = m.cursor(dictionary=True)
    try:
        ph = ', '.join(['%s'] * len(spbu_ids))
        cur.execute(f"SELECT * FROM subsidy_transactions WHERE id IN ({ph})", spbu_ids)
        spbu = {r['id']: r for r in cur.fetchall()}
    finally:
        cur.close()
        try:
            m.close()
        except Exception:
            pass

    # --- rantai hash -------------------------------------------------
    prev = '0' * 64
    chain = []
    for r in rows:
        st = spbu.get(r['subsidy_tx_id']) or {}
        rec = {
            'claim_id': r['id'],
            'display_id': r['display_id'],
            'driver': r['driver_name'],
            'nopol_norm': ''.join(ch for ch in str(r['nopol']).upper() if ch.isalnum()),
            'vehicle_type': r['vehicle_type'],
            'bbm_type': r['bbm_type'],
            'claim_liter': float(r['liter'] or 0),
            'claim_nominal': float(r['nominal'] or 0),
            'claim_odo_km': int(r['odo_km'] or 0),
            'claim_created': str(r['claim_created']),
            'ga_approved_by': r['ga_approved_by'],
            'subsidy_linked_by': r['subsidy_linked_by'],
            'subsidy_linked_at': str(r['subsidy_linked_at']),
            'spbu_transaction_id': st.get('transaction_id'),
            'spbu_transaction_date': str(st.get('transaction_date')),
            'spbu_volume': float(st.get('volume') or 0),
            'spbu_amount': float(st.get('amount') or 0),
            'spbu_id': st.get('spbu_id'),
            'spbu_witel': st.get('witel'),
            'spbu_verification': st.get('verification'),
            'spbu_validation_id': st.get('validation_id'),
        }
        data = _canonical(rec)
        h = _sha256_hex(prev + data)
        prev = h
        chain.append({
            'claim_id': r['id'], 'display_id': r['display_id'],
            'subsidy_transaction_id': st.get('transaction_id'),
            'record_hash': h,
            '_rec': rec,
        })
    root = _sha256_hex(prev + f'records={len(chain)}')  # commit jumlah juga

    # --- snapshot arsip (bukti yang tak dapat diubah dari app) --------
    attest_dir = os.path.join('data', 'subsidy_attest')
    os.makedirs(attest_dir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    snap_path = os.path.join(attest_dir, f'snapshot_{period_start}_{period_end}_{stamp}.json')
    snapshot = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'period': [str(period_start), str(period_end)],
        'generated_by': actor,
        'root_hash': root,
        'source': 'subsiditepat.my-pertamina.id (akun Subsidi Tepat perseroan)',
        'records': [c['_rec'] for c in chain],
        'spbu_raw': [
            {k: (str(v) if not isinstance(v, (int, float, bool, type(None))) else v)
             for k, v in st.items() if k not in ('raw_json',)}
            for st in (spbu.get(r['subsidy_tx_id']) for r in rows)
        ],
    }
    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, separators=(',', ':'))
    snap_hash = None
    with open(snap_path, 'rb') as f:
        hashlib_obj = hashlib.sha256()
        for chunk in iter(lambda: f.read(65536), b''):
            hashlib_obj.update(chunk)
        snap_hash = hashlib_obj.hexdigest()

    manifest = {
        'root_hash': root,
        'record_count': len(chain),
        'snapshot_sha256': snap_hash,
        'records': [{'claim_id': c['claim_id'], 'display_id': c['display_id'],
                     'subsidy_transaction_id': c['subsidy_transaction_id'],
                     'record_hash': c['record_hash']} for c in chain],
    }
    return {
        'records': chain, 'root_hash': root, 'record_count': len(chain),
        'snapshot_path': snap_path, 'snapshot_sha256': snap_hash,
        'manifest': manifest, 'period_start': str(period_start), 'period_end': str(period_end),
    }


def persist_attestation(data, actor, branch_code=None):
    """Simpan registry BA di master — return id.

    `branch_code` = cabang pemilik BA; dipakai untuk memisahkan daftar/unduhan
    antar cabang. NULL hanya untuk baris lama (sebelum v2.99.1).
    """
    m = get_master_connection()
    if not m:
        raise ValueError('DB master tidak tersedia')
    cur = m.cursor()
    try:
        cur.execute(
            "INSERT INTO subsidy_attestations "
            "(period_start, period_end, record_count, root_hash, manifest_json, "
            " snapshot_sha256, snapshot_path, generated_by, branch_code) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (data['period_start'], data['period_end'], data['record_count'],
             data['root_hash'], json.dumps(data['manifest'], ensure_ascii=False),
             data['snapshot_sha256'], data['snapshot_path'], actor,
             (branch_code or None)))
        m.commit()
        return cur.lastrowid
    finally:
        cur.close()
        try:
            m.close()
        except Exception:
            pass


def mark_pdf_path(att_id, pdf_path):
    """Setelah PDF dibangun, simpan path-nya ke registry (unduhan berikutnya)."""
    m = get_master_connection()
    if not m:
        return False
    cur = m.cursor()
    try:
        cur.execute("UPDATE subsidy_attestations SET pdf_path=%s WHERE id=%s",
                    (pdf_path, att_id))
        m.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        try:
            m.close()
        except Exception:
            pass
