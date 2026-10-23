"""v2.50.0 — Integrasi Subsidi Tepat (MyPertamina).

Riwayat transaksi BBM resmi dari akun Subsidi Tepat perseroan (diambil agen
`subsiditepat` di host dari portal subsiditepat.mypertamina.id) di-impor ke
tabel `subsidy_transactions` (MASTER DB — otoritatif, lintas cabang). Finance
lalu saat verifikasi klaim membandingkan klaim driver ↔ riwayat SPBU:

  - GET  /api/subsidy/match/<tx_id>   kandidat kecocokan (nopol+tanggal+liter)
  - POST /api/subsidy/link/<tx_id>    tautkan klaim ke transaksi SPBU (finance)
  - POST /api/subsidy/unlink/<tx_id>  lepas tautan (finance)
  - GET  /api/subsidy/status          ringkasan data terimpor
  - POST /api/subsidy/import          upsert data dari agen (token) / admin

Impor memakai header X-SUBSIDY-TOKEN == env SUBSIDY_IMPORT_TOKEN (automation)
atau sesi admin untuk uji manual. Sifat integrasi ADVISORY, bukan blokir:
alat kepastian data yang diputuskan Finance saat verifikasi — rating match
hanya membantu, payout tetap kebijakan Finance.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta

from flask import jsonify, request, session, make_response, send_from_directory

from modules.config import get_db_connection, get_master_connection
from modules.helpers import role_required, log_activity_async
from modules.subsidy_attest import (build_attestation, ensure_attestation_schema,
                                    mark_pdf_path, persist_attestation)

# ============================================================
# Schema — idempoten (pola ensure_anti_fraud_schema)
# ============================================================

_SUBSIDY_DDL = """
CREATE TABLE IF NOT EXISTS subsidy_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_id VARCHAR(60) NOT NULL,
    validation_id VARCHAR(80) DEFAULT '',
    transaction_date DATETIME NOT NULL,
    nopol_norm VARCHAR(20) NOT NULL,
    nopol_raw VARCHAR(30) DEFAULT '',
    product VARCHAR(20) DEFAULT '',
    volume DOUBLE DEFAULT 0,
    amount DOUBLE DEFAULT 0,
    spbu_id VARCHAR(20) DEFAULT '',
    city VARCHAR(80) DEFAULT '',
    witel VARCHAR(80) DEFAULT '',
    verification VARCHAR(10) DEFAULT '',
    business_type VARCHAR(20) DEFAULT '',
    customer_type VARCHAR(20) DEFAULT '',
    raw_json JSON,
    pulled_at DATETIME NULL,
    imported_by VARCHAR(80) DEFAULT 'agent',
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_txid (transaction_id),
    KEY idx_nopol (nopol_norm),
    KEY idx_date (transaction_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# Kolom transactions di DB cabang — tautan hasil verifikasi Finance.
_TX_COLUMNS = (
    ("subsidy_tx_id", "BIGINT NULL"),
    ("subsidy_match", "VARCHAR(20) NULL"),
    ("subsidy_linked_by", "VARCHAR(150) NULL"),
    ("subsidy_linked_at", "DATETIME NULL"),
)

_MAX_RAW = 20000  # batas panjang raw_json (payload besar diceguk)

# Toleransi kecocokan klaim ↔ SPBU:
_MATCH_LITER = 0.05   # deskripsi volume 2 desimal → ≤0.05 berarti identik
_MATCH_RUP = 2000     # propagasi harga/liter antar-deskripsi hari itu
_CLOSE_LITER = 2.0    # 'close' = kemungkinan sama pos (ruang baca meter)


def _norm_nopol(s):
    """'B 2731 SRQ' == 'B2731SRQ' — normalisasi tanpa spasi/tanda, uppercase."""
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())[:20]


def _parse_date(v):
    """ISO ('2026-10-22T03:03:38Z'/'2026-10-22 10:03') → datetime naive."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    s = str(v).replace('T', ' ')[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def ensure_subsidy_schema(conn=None):
    """Idempoten SATU DB: tabel subsidy_transactions + kolom subsidy_* di
    transactions. Master dipanggil bebas (conn=None); tiap DB cabang dipanggil
    eksplisit dengan conn masing-masing."""
    own = conn is None
    if conn is None:
        conn = get_master_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(_SUBSIDY_DDL)
        for col, definition in _TX_COLUMNS:
            try:
                cur.execute(f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col} {definition}")
            except Exception as col_err:
                print(f"[subsidy] kolom {col}: {col_err}")
        conn.commit()
        return True
    finally:
        cur.close()
        if own:
            try:
                conn.close()
            except Exception:
                pass


def _import_actor():
    if session.get('user_role'):
        return (session.get('full_name') or session.get('user_name') or 'admin').strip()[:80]
    return 'agent'


def _row_tuple(r):
    """Row mentah pull.mjs → tuple kolom import. None bila tak valid."""
    txid = str((r or {}).get('transactionId') or '').strip()[:60]
    if not txid:
        return None
    d = _parse_date(r.get('transactionDate'))
    if not d:
        return None
    try:
        raw_json = json.dumps(r, ensure_ascii=False, default=str)[:_MAX_RAW]
    except Exception:
        raw_json = None
    return (
        txid,
        str(r.get('validationId') or '')[:80],
        d,
        _norm_nopol(r.get('vehicleLicenseNumber')),
        str(r.get('vehicleLicenseNumber') or '')[:30],
        str(r.get('product') or '')[:20].lower(),
        float(r.get('volumeTransaction') or 0),
        float(r.get('totalAmount') or 0),
        str(r.get('spbuId') or '')[:20],
        str(r.get('city') or '')[:80],
        str(r.get('witel') or '')[:80],
        str(r.get('verificationType') or '')[:10],
        str(r.get('businessType') or '')[:20],
        str(r.get('customerType') or '')[:20],
        raw_json,
        _parse_date(r.get('pulledAt')),
    )


def _judge(liter, nominal, volume, amount):
    """Verdict per pasangan: 'match' | 'close' | 'mismatch'."""
    dv = abs(float(liter or 0) - float(volume or 0))
    dn = abs(float(nominal or 0) - float(amount or 0))
    if dv <= _MATCH_LITER and dn <= _MATCH_RUP:
        return 'match'
    if dv <= _CLOSE_LITER:
        return 'close'
    return 'mismatch'


# ============================================================
# Routes
# ============================================================

def register_subsidy_routes(app):

    # v2.50.0: pastikan schema (master + semua cabang) tiap startup — idempoten.
    # v2.51.0: + registry subsidy_attestations (master) untuk Berita Acara.
    def _ensure_all_dbs():
        try:
            if not ensure_subsidy_schema():
                return
            ensure_attestation_schema()
            from modules.branch_manager import list_branches
            for b in (list_branches() or []):
                if not (b.get('is_active') and b.get('db_name')):
                    continue
                c = get_db_connection(branch_code=b.get('code'))
                if c:
                    ensure_subsidy_schema(c)
                    try:
                        c.close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[subsidy] ensure schema startup: {e}")

    try:
        threading.Thread(target=_ensure_all_dbs, daemon=True).start()
    except Exception:
        pass

    @app.route('/api/subsidy/import', methods=['POST'])
    def api_subsidy_import():
        """Automation (token) atau admin (sesi). Body: {rows: [...]}."""
        expected = os.environ.get('SUBSIDY_IMPORT_TOKEN', '').strip()
        header = (request.headers.get('X-SUBSIDY-TOKEN') or '').strip()
        has_session = bool(session.get('user_role'))
        if has_session and str(session.get('user_role')).lower() != 'admin':
            return jsonify({'status': 'error', 'msg': 'Hanya admin'}), 403
        if not has_session:
            if not expected or not header or header != expected:
                return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        data = request.get_json(silent=True) or {}
        rows = data.get('rows') or []
        if not isinstance(rows, list) or not rows:
            return jsonify({'status': 'error', 'msg': 'rows kosong'}), 400
        rows = rows[:2000]
        # pulled_at tingkat payload (agent pull.mjs mengirim {pulledAt}) —
        # dipakai untuk baris tanpa timestamp pulanya sendiri, supaya
        # /api/subsidy/status (MAX(pulled_at)) tidak pernah NULL.
        payload_pulled = _parse_date(data.get('pulled_at') or data.get('pulledAt'))
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor()
        try:
            ok = dup = invalid = 0
            for r in rows:
                if isinstance(r, dict) and not r.get('pulledAt'):
                    r = {**r, 'pulledAt': payload_pulled}
                tup = _row_tuple(r)
                if not tup:
                    invalid += 1
                    continue
                cur.execute(
                    "INSERT INTO subsidy_transactions "
                    "(transaction_id, validation_id, transaction_date, nopol_norm, nopol_raw, "
                    " product, volume, amount, spbu_id, city, witel, verification, "
                    " business_type, customer_type, raw_json, pulled_at, imported_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE "
                    " validation_id=VALUES(validation_id), amount=VALUES(amount), "
                    " volume=VALUES(volume), raw_json=VALUES(raw_json), pulled_at=VALUES(pulled_at)",
                    tup + (_import_actor(),))
                if cur.rowcount > 0:
                    ok += 1
                else:
                    dup += 1
            conn.commit()
            log_activity_async(0, 'subsidy_import', 'system', _import_actor(),
                               ip=request.remote_addr,
                               new_data={'jumlah': len(rows), 'baru': ok, 'duplikat': dup, 'invalid': invalid})
            return jsonify({'status': 'success',
                            'msg': f'Impor Subsidi Tepat: {ok} baru, {dup} duplikat, {invalid} invalid'})
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/subsidy/match/<int:tx_id>')
    @role_required(['ga', 'finance', 'admin'])
    def api_subsidy_match(tx_id):
        """Kandidat kecocokan transaksi klaim ↔ data SPBU Subsidi Tepat."""
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT id, display_id, nopol, liter, nominal, bbm_type, created_at, "
                "subsidy_tx_id, subsidy_match, subsidy_linked_by, subsidy_linked_at "
                "FROM transactions WHERE id=%s", (tx_id,))
            tx = cur.fetchone()
            if not tx:
                return jsonify({'error': 'Not found'}), 404

            linked = None
            linked_by = tx.get('subsidy_linked_by')
            linked_at = str(tx.get('subsidy_linked_at') or '')
            created = tx.get('created_at')
            liter = float(tx.get('liter') or 0)
            nominal = float(tx.get('nominal') or 0)
            tx_bbm = str(tx.get('bbm_type') or '').lower()

            m = get_master_connection()
            mcur = None
            if m:
                try:
                    mcur = m.cursor(dictionary=True)
                    if tx.get('subsidy_tx_id'):
                        mcur.execute("SELECT * FROM subsidy_transactions WHERE id=%s",
                                     (tx['subsidy_tx_id'],))
                        linked = mcur.fetchone()
                    cands = []
                    if created:
                        start = created.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                        end = created + timedelta(days=2, hours=6)
                        mcur.execute(
                            "SELECT * FROM subsidy_transactions "
                            "WHERE nopol_norm=%s AND transaction_date BETWEEN %s AND %s "
                            "ORDER BY ABS(volume-%s) ASC, transaction_date ASC LIMIT 10",
                            (_norm_nopol(tx['nopol']), start, end, liter))
                        for st in mcur.fetchall():
                            verdict = 'match' if linked and linked['id'] == st['id'] else (
                                _judge(liter, nominal, st['volume'], st['amount']))
                            cands.append({
                                'id': st['id'],
                                'transaction_id': st['transaction_id'],
                                'transaction_date': str(st['transaction_date']),
                                'nopol_raw': st.get('nopol_raw') or st['nopol_norm'],
                                'volume': float(st['volume'] or 0),
                                'amount': float(st['amount'] or 0),
                                'product': st['product'],
                                'spbu_id': st['spbu_id'],
                                'city': st['city'], 'witel': st['witel'],
                                'verification': st['verification'],
                                'verdict': verdict,
                                'dvol': round(liter - float(st['volume'] or 0), 2),
                                'dnom': round(nominal - float(st['amount'] or 0), 2),
                                'tipe_ok': (st['product'] == tx_bbm) if tx_bbm else False,
                            })
                finally:
                    if mcur:
                        mcur.close()
                    try:
                        m.close()
                    except Exception:
                        pass

            if linked:
                verdict = 'linked'
            elif not cands:
                verdict = 'no_record'
            elif any(c['verdict'] == 'match' for c in cands):
                verdict = 'match'
            elif any(c['verdict'] == 'close' for c in cands):
                verdict = 'close'
            else:
                verdict = 'no_match'

            return jsonify({
                'verdict': verdict, 'nopol_norm': _norm_nopol(tx['nopol']),
                'liter': liter, 'nominal': nominal, 'candidates': cands,
                'linked': {
                    'id': linked['id'], 'transaction_id': linked['transaction_id'],
                    'transaction_date': str(linked['transaction_date']),
                    'volume': linked['volume'], 'amount': linked['amount'],
                    'spbu_id': linked['spbu_id'], 'city': linked['city'],
                } if linked else None,
                'linked_by': linked_by, 'linked_at': linked_at,
            })
        except Exception as e:
            return jsonify({'error': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/subsidy/link/<int:tx_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_subsidy_link(tx_id):
        actor = (session.get('full_name') or session.get('user_name') or 'Finance').strip()
        data = request.get_json(silent=True) or {}
        st_id = int(data.get('subsidy_transaction_id') or 0)
        if not st_id:
            return jsonify({'status': 'error', 'msg': 'subsidy_transaction_id wajib'}), 400
        m = get_master_connection()
        if not m:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        mcur = m.cursor(dictionary=True)
        try:
            mcur.execute("SELECT id, transaction_id, volume FROM subsidy_transactions WHERE id=%s", (st_id,))
            st = mcur.fetchone()
        finally:
            mcur.close()
            try:
                m.close()
            except Exception:
                pass
        if not st:
            return jsonify({'status': 'error', 'msg': 'Transaksi Subsidi Tepat tidak ditemukan'}), 404
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE transactions SET subsidy_tx_id=%s, subsidy_match='linked', "
                "subsidy_linked_by=%s, subsidy_linked_at=NOW() WHERE id=%s",
                (st_id, actor, tx_id))
            conn.commit()
            log_activity_async(tx_id, 'subsidy_link', 'finance', actor, ip=request.remote_addr,
                               new_data={'subsidy_tx_id': st_id, 'subsidy_transaction_id': st['transaction_id']})
            return jsonify({'status': 'success',
                            'msg': f"Klaim tertaut ke SPBU {st['transaction_id']} ({st['volume']} L)"})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/subsidy/unlink/<int:tx_id>', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_subsidy_unlink(tx_id):
        actor = (session.get('full_name') or session.get('user_name') or 'Finance').strip()
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE transactions SET subsidy_tx_id=NULL, subsidy_match='unlinked', "
                "subsidy_linked_by=%s, subsidy_linked_at=NOW() WHERE id=%s", (actor, tx_id))
            conn.commit()
            log_activity_async(tx_id, 'subsidy_unlink', 'finance', actor, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Tautan dilepas'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                conn.close()
            except Exception:
                pass

    @app.route('/api/subsidy/attest', methods=['POST'])
    @role_required(['finance', 'admin'])
    def api_subsidy_attest_create():
        """Buat Berita Acara Rekonsiliasi untuk satu periode (v2.51.0).

        Body: {period: 'YYYY-MM'} atau {start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'}.
        Klaim yang disertakan = yang DITAUT finance (subsidy_linked_at) di
        periode itu. Menghasilkan PDF + snapshot arsip JSON + registry master.
        """
        actor = (session.get('full_name') or session.get('user_name') or 'Finance').strip()
        data = request.get_json(silent=True) or {}
        try:
            period = str(data.get('period') or '').strip()
            if re.fullmatch(r'\d{4}-\d{2}', period):
                y, mo = int(period[:4]), int(period[5:7])
                start = datetime(y, mo, 1).date()
                nxt = datetime(y + 1, 1, 1) if mo == 12 else datetime(y, mo + 1, 1)
                end = nxt.date() - timedelta(days=1)
            else:
                start = _parse_date(data.get('start')).date() if _parse_date(data.get('start')) else None
                end = _parse_date(data.get('end')).date() if _parse_date(data.get('end')) else None
                if not start or not end or end < start:
                    return jsonify({'status': 'error',
                                    'msg': "Isi period 'YYYY-MM' atau start/end 'YYYY-MM-DD'"}), 400
            attest = build_attestation(start, end, actor)
        except ValueError as ve:
            return jsonify({'status': 'error', 'msg': str(ve)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500

        try:
            attest_id = persist_attestation(attest, actor)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': f"Registry: {str(e)[:180]}"}), 500

        # PDF + arsip salinan
        from modules.pdf_generator import AttestReportPDF
        try:
            attest['meta'] = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            pdf = AttestReportPDF()
            pdf.generate(attest, generated_by=actor)
            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            pdf_rel = os.path.join('data', 'subsidy_attest',
                                   f'berita_acara_{start}_{end}_{attest_id}.pdf')
            os.makedirs(os.path.dirname(pdf_rel), exist_ok=True)
            with open(pdf_rel, 'wb') as f:
                f.write(pdf_bytes)
            mark_pdf_path(attest_id, pdf_rel)
        except Exception as e:
            return jsonify({'status': 'error', 'msg': f'PDF: {str(e)[:180]}'}), 500

        log_activity_async(0, 'subsidy_attest', 'finance', actor, ip=request.remote_addr,
                           new_data={'attest_id': attest_id, 'periode': f'{start} s/d {end}',
                                     'records': attest['record_count'], 'root_hash': attest['root_hash']})
        return jsonify({
            'status': 'success',
            'msg': f"Berita Acara #{attest_id}: {attest['record_count']} klaim, periode {start} s/d {end}",
            'id': attest_id, 'root_hash': attest['root_hash'],
            'record_count': attest['record_count'],
            'snapshot_sha256': attest['snapshot_sha256'],
        })

    @app.route('/api/subsidy/attest')
    @role_required(['finance', 'admin'])
    def api_subsidy_attest_list():
        """Daftar Berita Acara terakhir (registry master)."""
        m = get_master_connection()
        if not m:
            return jsonify({'error': 'DB error'}), 500
        cur = m.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT id, period_start, period_end, record_count, root_hash, "
                "snapshot_sha256, pdf_path, generated_by, generated_at "
                "FROM subsidy_attestations ORDER BY id DESC LIMIT 25")
            rows = cur.fetchall() or []
            return jsonify({'attestations': [
                {**r, 'period_start': str(r['period_start']),
                 'period_end': str(r['period_end']),
                 'generated_at': str(r['generated_at'])} for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                m.close()
            except Exception:
                pass

    @app.route('/api/subsidy/attest/<int:att_id>/pdf')
    @role_required(['finance', 'admin'])
    def api_subsidy_attest_pdf(att_id):
        """Unduh PDF Berita Acara (dari arsip; regenerate bila hilang)."""
        m = get_master_connection()
        if not m:
            return jsonify({'error': 'DB error'}), 500
        cur = m.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM subsidy_attestations WHERE id=%s", (att_id,))
            row = cur.fetchone()
        finally:
            cur.close()
            try:
                m.close()
            except Exception:
                pass
        if not row:
            return jsonify({'error': 'Not found'}), 404

        pdf_rel = row.get('pdf_path')
        if pdf_rel and os.path.isfile(pdf_rel):
            directory = os.path.dirname(pdf_rel)
            filename = os.path.basename(pdf_rel)
        else:
            # Arsip PDF hilang → bangun ulang dari data tervalidasi + hash lama.
            try:
                attest = build_attestation(row['period_start'], row['period_end'],
                                           row.get('generated_by') or 'Finance')
            except Exception as e:
                return jsonify({'error': f'Arsip PDF hilang & data periode berubah: {str(e)[:150]}'}), 409
            if attest['root_hash'] != row['root_hash']:
                return jsonify({'error': 'Data periode berubah sejak BA diterbitkan '
                                         '(root hash tidak cocok) — BA pakai lama tidak sah'}), 409
            attest['meta'] = {'generated_at': str(row['generated_at'])}
            from modules.pdf_generator import AttestReportPDF
            pdf = AttestReportPDF()
            pdf.generate(attest, generated_by=row.get('generated_by') or 'Finance')
            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            pdf_rel = os.path.join('data', 'subsidy_attest',
                                   f"berita_acara_{row['period_start']}_{row['period_end']}_{att_id}.pdf")
            os.makedirs(os.path.dirname(pdf_rel), exist_ok=True)
            with open(pdf_rel, 'wb') as f:
                f.write(pdf_bytes)
            mark_pdf_path(att_id, pdf_rel)
            directory, filename = os.path.dirname(pdf_rel), os.path.basename(pdf_rel)
        resp = make_response(send_from_directory(directory, filename))
        resp.headers['Content-Type'] = 'application/pdf'
        fname = f"BPF_Berita_Acara_SubsidiTepat_{row['period_start']}_{row['period_end']}_BA{att_id}.pdf"
        resp.headers['Content-Disposition'] = f'inline; filename="{fname}"'
        return resp

    @app.route('/api/subsidy/auto-match', methods=['POST'])
    def api_subsidy_auto_match():
        """Advisory bulk-match — satu klik Finance setelah agen menarik data.

        Semua klaim BBM yang masih terbuka (belum arsip/ditolak) di DB cabang
        ini diadu ke master `subsidy_transactions` (nopol + rentang tanggal).
        Hasil ditulis ke `subsidy_match` (match/close/mismatch/no_record),
        TIDAK mengubah tautan (subsidy_tx_id) yang sudah dijodohkan Finance —
        kepastian verifikasi tetap putusan manusia (prinsip ADVISORY).

        Auth: sesi finance/admin ATAU agen host dengan header X-SUBSIDY-TOKEN
        (paritas /api/subsidy/import) — supaya cron harian bisa mengeksekusi
        import + auto-match tanpa sesi browser.
        """
        expected = os.environ.get('SUBSIDY_IMPORT_TOKEN', '').strip()
        header = (request.headers.get('X-SUBSIDY-TOKEN') or '').strip()
        has_session = bool(session.get('user_role'))
        role = str(session.get('user_role') or '').lower()
        if has_session and role not in ('finance', 'admin'):
            return jsonify({'status': 'error', 'msg': 'Hanya finance/admin'}), 403
        if not has_session:
            if not expected or not header or header != expected:
                return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        actor = (session.get('full_name') or session.get('user_name') or 'agen').strip()
        conn = get_db_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        m = get_master_connection()
        mcur = None
        result = {'checked': 0, 'skipped_linked': 0, 'match': 0, 'close': 0,
                  'mismatch': 0, 'no_record': 0}
        try:
            if m:
                mcur = m.cursor(dictionary=True)
            cur.execute(
                "SELECT id, display_id, nopol, liter, nominal, created_at, subsidy_tx_id "
                "FROM transactions WHERE status NOT IN ('archived', 'rejected')")
            claims = cur.fetchall() or []
            for tx in claims:
                result['checked'] += 1
                if tx.get('subsidy_tx_id'):
                    result['skipped_linked'] += 1
                    continue
                liter = float(tx.get('liter') or 0)
                nominal = float(tx.get('nominal') or 0)
                created = tx.get('created_at')
                verdict = 'no_record'
                if mcur and created:
                    start = created.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                    end = created + timedelta(days=2, hours=6)
                    mcur.execute(
                        "SELECT volume, amount FROM subsidy_transactions "
                        "WHERE nopol_norm=%s AND transaction_date BETWEEN %s AND %s",
                        (_norm_nopol(tx['nopol']), start, end))
                    cands = mcur.fetchall() or []
                    best = 'mismatch' if cands else 'no_record'
                    for st in cands:
                        j = _judge(liter, nominal, st.get('volume'), st.get('amount'))
                        if j == 'match':
                            best = 'match'
                            break
                        if j == 'close':
                            best = 'close'
                    verdict = best
                result.setdefault(verdict, 0)
                result[verdict] += 1
                if verdict in ('match', 'close'):
                    cur.execute("UPDATE transactions SET subsidy_match=%s WHERE id=%s",
                                (verdict, tx['id']))
                elif verdict in ('mismatch', 'no_record'):
                    cur.execute(
                        "UPDATE transactions SET subsidy_match=%s "
                        "WHERE id=%s AND subsidy_match IN ('', 'mismatch', 'no_record', NULL)",
                        (verdict, tx['id']))
            conn.commit()
            log_activity_async(0, 'subsidy_auto_match', 'finance', actor,
                               ip=request.remote_addr, new_data=result)
            return jsonify({'status': 'success', **result,
                            'msg': (f"Pencocokan otomatis: {result['match']} match, "
                                    f"{result['close']} close, {result['no_record']} tanpa catatan, "
                                    f"{result['skipped_linked']} sudah dijodohkan")})
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return jsonify({'status': 'error', 'msg': str(e)[:200]}), 500
        finally:
            cur.close()
            if mcur:
                mcur.close()
            try:
                conn.close()
            except Exception:
                pass
            try:
                m.close()
            except Exception:
                pass

    @app.route('/api/subsidy/status')
    @role_required(['finance', 'admin'])
    def api_subsidy_status():
        """Ringkasan kesiapan data: jumlah row, tanggal tarikan terakhir."""
        m = get_master_connection()
        if not m:
            return jsonify({'error': 'DB error'}), 500
        cur = m.cursor(dictionary=True)
        try:
            cur.execute("SELECT COUNT(*) AS c, MAX(pulled_at) AS last_pull, "
                        "MIN(transaction_date) AS oldest, MAX(transaction_date) AS newest "
                        "FROM subsidy_transactions")
            row = cur.fetchone()
            # Cakupan klaim BBM cabang ini (v2.68.0): berapa klaim terbuka sudah
            # tervalidasi data SPBU (link/jodoh + sinyal advisory match/close).
            coverage = {}
            b = get_db_connection()
            bcur = None
            try:
                if b:
                    bcur = b.cursor()
                    bcur.execute(
                        "SELECT COALESCE(subsidy_match, 'belum') AS ket, COUNT(*) AS n "
                        "FROM transactions WHERE status NOT IN ('archived', 'rejected') "
                        "GROUP BY COALESCE(subsidy_match, 'belum')")
                    coverage = {r[0]: int(r[1]) for r in (bcur.fetchall() or [])}
                    bcur.execute("SELECT COUNT(*) FROM transactions "
                                 "WHERE status NOT IN ('archived', 'rejected')")
                    coverage['terbuka'] = int(bcur.fetchone()[0])
            except Exception as ce:
                print(f"[subsidy] status coverage: {ce}")
            finally:
                if bcur:
                    bcur.close()
                try:
                    b.close()
                except Exception:
                    pass
            return jsonify({
                'count': int(row.get('c') or 0),
                'last_pull': str(row.get('last_pull') or ''),
                'oldest': str(row.get('oldest') or ''),
                'newest': str(row.get('newest') or ''),
                'coverage': coverage,
            })
        except Exception as e:
            return jsonify({'error': str(e)[:200]}), 500
        finally:
            cur.close()
            try:
                m.close()
            except Exception:
                pass
