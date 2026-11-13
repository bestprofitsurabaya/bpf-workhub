"""Voucher BBM Rekanan — pemakaian, rekonsiliasi, dan pembayaran (v2.107.0).

Tiga hal yang dijaga modul ini:

1. **Pemakaian** dicatat driver dari tab BBM (satu voucher = satu transaksi).
2. **Rekonsiliasi** mengumpulkan voucher terverifikasi GA menjadi satu tagihan
   per periode (mingguan/bulanan) ke SPBU mitra.
3. **Anti tagihan dobel** — begitu masuk tagihan, `settlement_id` mengunci
   transaksi sehingga tidak bisa masuk periode berikutnya.

Transaksi voucher TIDAK memakai `transaction_type` baru: tetap `CLAIM`
seperti laporan BBM lain. Penandanya adalah `spbu_type='rekanan'` + kolom
voucher terisi (`voucher_value > 0`). Dengan begitu laporan BBM tetap satu
alur, sementara pembayaran ke SPBU mitra ditangani tagihan periode.

Voucher dihitung sebagai beban BBM SEKALI saat pemakaian sah
(`verified_ga`/`archived`). Pembayaran tagihan adalah kas keluar, bukan beban
baru — karena itu tidak menambah `nominal` transaksi.
"""
import random
from datetime import datetime

from flask import jsonify, make_response, request, session

from modules.config import get_db_connection
from modules.helpers import generate_display_id, log_activity_async, role_required
from modules.stepup import stepup_required

CONFIG_VALUE_KEY = 'voucher_default_value'
CONFIG_PARTNER_KEY = 'voucher_partner_name'
DEFAULT_VALUE = 130000
DAILY_CODES = [100, 200, 300, 400, 500, 600, 700, 800, 900,
               1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000]

VIEW_ROLES = ['ga', 'finance', 'admin']
EDIT_ROLES = ['finance', 'admin']
USAGE_ROLES = ['driver', 'ga', 'finance', 'admin']


def _actor():
    return (session.get('full_name') or session.get('user_name') or 'Admin').strip()


def get_or_create_daily_code(conn):
    """Kode harian cabang — satu kode per hari, dipakai bersama kasbon/voucher."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT unique_code FROM daily_unique_codes WHERE code_date=CURDATE()")
        row = cur.fetchone()
        if row:
            return int(row['unique_code'])
        code = random.choice(DAILY_CODES)
        cur.execute(
            "INSERT INTO daily_unique_codes (code_date, unique_code) VALUES (CURDATE(), %s) "
            "ON DUPLICATE KEY UPDATE unique_code=unique_code", (code,))
        conn.commit()
        cur.execute(
            "SELECT unique_code FROM daily_unique_codes WHERE code_date=CURDATE()")
        row = cur.fetchone()
        return int(row['unique_code']) if row else code
    finally:
        try:
            cur.close()
        except Exception:
            pass


def read_voucher_config(conn):
    """Nilai voucher + nama mitra default cabang (system_config)."""
    value, partner = DEFAULT_VALUE, ''
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT config_key, config_value FROM system_config "
            "WHERE config_key IN (%s, %s)",
            (CONFIG_VALUE_KEY, CONFIG_PARTNER_KEY))
        for row in cur.fetchall() or []:
            if row['config_key'] == CONFIG_VALUE_KEY:
                try:
                    value = float(row['config_value'] or DEFAULT_VALUE)
                except (TypeError, ValueError):
                    value = DEFAULT_VALUE
            elif row['config_key'] == CONFIG_PARTNER_KEY:
                partner = (row['config_value'] or '').strip()
    except Exception as exc:
        print(f"[voucher] read config: {exc}")
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return {'value': value, 'partner': partner}


def _fmt_date(value):
    if not value:
        return '-'
    if hasattr(value, 'strftime'):
        return value.strftime('%d-%m-%Y')
    return str(value)[:10]


def register_voucher_routes(app):

    @app.route('/api/voucher/config')
    @role_required(USAGE_ROLES)
    def api_voucher_config():
        """Nilai voucher cabang + kode harian untuk pratinjau form driver."""
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cfg = read_voucher_config(conn)
            code = get_or_create_daily_code(conn)
            return jsonify({
                'value': cfg['value'],
                'partner': cfg['partner'],
                'daily_code': code,
                'nominal': cfg['value'] + code,
            })
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/config', methods=['POST'])
    @role_required(EDIT_ROLES)
    def api_voucher_config_save():
        body = request.get_json(silent=True) or request.form or {}
        try:
            value = float(body.get('value', DEFAULT_VALUE))
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'msg': 'Nilai voucher harus angka'}), 400
        if value <= 0:
            return jsonify({'status': 'error', 'msg': 'Nilai voucher harus lebih dari 0'}), 400
        partner = str(body.get('partner') or '').strip()[:120]
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            for key, val in ((CONFIG_VALUE_KEY, str(int(value))),
                             (CONFIG_PARTNER_KEY, partner)):
                cur.execute(
                    "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)", (key, val))
            conn.commit()
            cur.close()
            log_activity_async(0, 'voucher_config', session.get('user_role', ''),
                               _actor(), new_data={'value': value, 'partner': partner},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Pengaturan voucher disimpan',
                            'value': value, 'partner': partner})
        except Exception as exc:
            return jsonify({'status': 'error', 'msg': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/summary')
    @role_required(VIEW_ROLES)
    def api_voucher_summary():
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                  SUM(CASE WHEN status IN ('pending','modified') THEN 1 ELSE 0 END) AS pending_count,
                  SUM(CASE WHEN status IN ('pending','modified') THEN nominal ELSE 0 END) AS pending_amount,
                  SUM(CASE WHEN status='verified_ga' AND settlement_id IS NULL THEN 1 ELSE 0 END) AS open_count,
                  SUM(CASE WHEN status='verified_ga' AND settlement_id IS NULL THEN nominal ELSE 0 END) AS open_amount,
                  SUM(CASE WHEN settlement_id IS NOT NULL OR status='archived' THEN 1 ELSE 0 END) AS settled_count,
                  SUM(CASE WHEN settlement_id IS NOT NULL OR status='archived' THEN nominal ELSE 0 END) AS settled_amount
                FROM transactions
                WHERE transaction_type='CLAIM'
                  AND COALESCE(voucher_value, 0) > 0
                  AND (is_dummy=0 OR is_dummy IS NULL)
            """)
            row = cur.fetchone() or {}
            cur.close()
            cfg = read_voucher_config(conn)
            return jsonify({
                'pending': {'count': int(row.get('pending_count') or 0),
                            'amount': float(row.get('pending_amount') or 0)},
                'open': {'count': int(row.get('open_count') or 0),
                         'amount': float(row.get('open_amount') or 0)},
                'settled': {'count': int(row.get('settled_count') or 0),
                            'amount': float(row.get('settled_amount') or 0)},
                'config': cfg,
            })
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/pending')
    @role_required(VIEW_ROLES)
    def api_voucher_pending():
        """Voucher yang menunggu verifikasi GA (foto & pemakaian)."""
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT id, display_id, driver_name, nopol, bbm_type, nominal, liter,
                       voucher_value, daily_code, voucher_partner, nota_no, odo_km,
                       gps_address, foto_odo_sebelum, foto_nota_odo_sesudah, foto_struk,
                       ml_anomaly_flag, status, created_at
                FROM transactions WHERE transaction_type='CLAIM'
                  AND COALESCE(voucher_value, 0) > 0
                  AND status IN ('pending','modified')
                  AND (is_dummy=0 OR is_dummy IS NULL)
                ORDER BY created_at ASC, id ASC
            """)
            rows = cur.fetchall() or []
            cur.close()
            for row in rows:
                for key in ('nominal', 'liter', 'voucher_value', 'odo_km'):
                    if row.get(key) is not None:
                        row[key] = float(row[key])
                if hasattr(row.get('created_at'), 'isoformat'):
                    row['created_at'] = row['created_at'].isoformat()
            return jsonify({'data': rows, 'count': len(rows),
                            'total': sum(float(r.get('nominal') or 0) for r in rows)})
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/verify/<int:tx_id>', methods=['POST'])
    @role_required(['ga', 'admin'])
    def api_voucher_verify(tx_id):
        """GA memverifikasi pemakaian voucher (foto & ODO) → verified_ga."""
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT status, ml_anomaly_flag FROM transactions "
                "WHERE id=%s AND transaction_type='CLAIM' "
                "AND COALESCE(voucher_value, 0) > 0", (tx_id,))
            row = cur.fetchone()
            if not row:
                cur.close()
                return jsonify({'status': 'error', 'msg': 'Transaksi voucher tidak ditemukan'}), 404
            if row.get('ml_anomaly_flag'):
                # Tetap boleh diverifikasi GA, tetapi harus lewat pemeriksaan
                # penuh (bukan tombol cepat) — samakan dengan klaim BBM.
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Voucher ber-flag anomali — periksa foto bukti terlebih dahulu.'}), 409
            cur.execute(
                "UPDATE transactions SET status='verified_ga', ga_approved_by=%s, "
                "ga_approved_at=NOW(), approved_by_user=%s "
                "WHERE id=%s AND transaction_type='CLAIM' "
                "AND COALESCE(voucher_value, 0) > 0 AND status IN ('pending','modified')",
                (_actor(), _actor(), tx_id))
            affected = cur.rowcount
            conn.commit()
            cur.close()
            if affected == 0:
                return jsonify({'status': 'error',
                                'msg': 'Voucher tidak ditemukan atau sudah diverifikasi.'}), 409
            log_activity_async(tx_id, 'voucher_verify', session.get('user_role', ''),
                               _actor(), ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Voucher diverifikasi GA'})
        except Exception as exc:
            return jsonify({'status': 'error', 'msg': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/unsettled')
    @role_required(VIEW_ROLES)
    def api_voucher_unsettled():
        """Voucher terverifikasi GA yang belum masuk tagihan mana pun."""
        start = (request.args.get('start') or '').strip()
        end = (request.args.get('end') or '').strip()
        partner = (request.args.get('partner') or '').strip()
        sql = [
            "SELECT id, display_id, driver_name, nopol, bbm_type, nominal, liter,",
            "voucher_value, daily_code, voucher_partner, nota_no, odo_km, created_at",
            "FROM transactions WHERE transaction_type='CLAIM'",
            "AND COALESCE(voucher_value, 0) > 0",
            "AND status IN ('verified_ga','archived') AND settlement_id IS NULL",
            "AND (is_dummy=0 OR is_dummy IS NULL)",
        ]
        params = []
        if start:
            sql.append('AND DATE(created_at) >= %s'); params.append(start)
        if end:
            sql.append('AND DATE(created_at) <= %s'); params.append(end)
        if partner:
            sql.append('AND voucher_partner = %s'); params.append(partner)
        sql.append('ORDER BY created_at ASC, id ASC')
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute(' '.join(sql), params)
            rows = cur.fetchall() or []
            cur.close()
            for row in rows:
                for key in ('nominal', 'liter', 'voucher_value', 'odo_km'):
                    if row.get(key) is not None:
                        row[key] = float(row[key])
                row['created_at'] = row.get('created_at').isoformat() if hasattr(
                    row.get('created_at'), 'isoformat') else row.get('created_at')
            total = sum(float(r.get('nominal') or 0) for r in rows)
            return jsonify({'data': rows, 'count': len(rows), 'total': total})
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements')
    @role_required(VIEW_ROLES)
    def api_voucher_settlements():
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT * FROM voucher_settlements
                ORDER BY created_at DESC, id DESC LIMIT 200
            """)
            rows = cur.fetchall() or []
            cur.close()
            for row in rows:
                for key in ('period_start', 'period_end', 'paid_at', 'created_at'):
                    if hasattr(row.get(key), 'isoformat'):
                        row[key] = row[key].isoformat()
                row['total_amount'] = float(row.get('total_amount') or 0)
            return jsonify(rows)
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements/<int:settlement_id>')
    @role_required(VIEW_ROLES)
    def api_voucher_settlement_detail(settlement_id):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM voucher_settlements WHERE id=%s", (settlement_id,))
            head = cur.fetchone()
            if not head:
                cur.close()
                return jsonify({'error': 'Tagihan tidak ditemukan'}), 404
            cur.execute("""
                SELECT id, display_id, driver_name, nopol, bbm_type, nominal, liter,
                       voucher_value, daily_code, voucher_partner, nota_no, created_at
                FROM transactions WHERE settlement_id=%s ORDER BY created_at ASC, id ASC
            """, (settlement_id,))
            rows = cur.fetchall() or []
            cur.close()
            for row in rows:
                for key in ('nominal', 'liter', 'voucher_value'):
                    if row.get(key) is not None:
                        row[key] = float(row[key])
                if hasattr(row.get('created_at'), 'isoformat'):
                    row['created_at'] = row['created_at'].isoformat()
            for key in ('period_start', 'period_end', 'paid_at', 'created_at'):
                if hasattr(head.get(key), 'isoformat'):
                    head[key] = head[key].isoformat()
            head['total_amount'] = float(head.get('total_amount') or 0)
            return jsonify({'settlement': head, 'items': rows})
        except Exception as exc:
            return jsonify({'error': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements', methods=['POST'])
    @role_required(EDIT_ROLES)
    @stepup_required
    def api_voucher_settlement_create():
        body = request.get_json(silent=True) or {}
        period_start = str(body.get('period_start') or '').strip()
        period_end = str(body.get('period_end') or '').strip()
        invoice_no = str(body.get('invoice_no') or '').strip()[:60]
        notes = str(body.get('notes') or '').strip()[:2000]
        partner = str(body.get('partner') or '').strip()[:120]
        raw_ids = body.get('tx_ids') or []
        try:
            tx_ids = sorted({int(x) for x in raw_ids})
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'msg': 'Daftar transaksi tidak valid'}), 400
        if not period_start or not period_end:
            return jsonify({'status': 'error', 'msg': 'Periode tagihan wajib diisi'}), 400
        if not tx_ids:
            return jsonify({'status': 'error', 'msg': 'Pilih minimal satu voucher'}), 400
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            fmt = ','.join(['%s'] * len(tx_ids))
            cur.execute(
                f"SELECT id, display_id, nominal, voucher_value, voucher_partner, "
                f"settlement_id, status, transaction_type "
                f"FROM transactions WHERE id IN ({fmt})", tx_ids)
            rows = cur.fetchall() or []
            found = {int(r['id']): r for r in rows}
            missing = [i for i in tx_ids if i not in found]
            if missing:
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Transaksi tidak ditemukan: ' + ', '.join(map(str, missing))}), 404
            bad_type = [r['display_id'] for r in rows
                        if r.get('transaction_type') != 'CLAIM'
                        or float(r.get('voucher_value') or 0) <= 0]
            if bad_type:
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Bukan transaksi voucher: ' + ', '.join(bad_type)}), 400
            locked = [r['display_id'] for r in rows
                      if r.get('settlement_id') or r.get('status') not in ('verified_ga', 'archived')]
            if locked:
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Sudah masuk tagihan / belum sah: ' + ', '.join(locked)}), 409
            partners = sorted({(r.get('voucher_partner') or '').strip()
                               for r in rows if (r.get('voucher_partner') or '').strip()})
            if not partner:
                partner = partners[0] if len(partners) == 1 else ', '.join(partners)[:120]
            total = round(sum(float(r.get('nominal') or 0) for r in rows), 2)
            display_id = generate_display_id('VST', conn)
            cur.execute("""
                INSERT INTO voucher_settlements
                    (display_id, period_start, period_end, partner, invoice_no,
                     voucher_count, total_amount, status, notes, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)
            """, (display_id, period_start, period_end, partner, invoice_no,
                  len(tx_ids), total, notes, _actor()))
            settlement_id = cur.lastrowid

            # Kunci transaksi: settlement_id + archived. Syarat ulang di WHERE
            # mencegah dua pengguna menyelesaikan tagihan yang sama bersamaan.
            cur.execute(
                f"UPDATE transactions SET settlement_id=%s, settled_at=NOW(), settled_by=%s, "
                f"status='archived' WHERE id IN ({fmt}) AND transaction_type='CLAIM' "
                f"AND COALESCE(voucher_value, 0) > 0 "
                f"AND settlement_id IS NULL AND status IN ('verified_ga','archived')",
                [settlement_id, _actor()] + tx_ids)
            if cur.rowcount != len(tx_ids):
                conn.rollback()
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Sebagian voucher baru saja masuk tagihan lain. Muat ulang daftar.'}), 409
            conn.commit()
            cur.close()
            log_activity_async(0, 'voucher_settlement', session.get('user_role', ''),
                               _actor(), new_data={'settlement': display_id,
                                                   'count': len(tx_ids), 'total': total},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'Tagihan {display_id} dibuat',
                            'settlement_id': settlement_id, 'display_id': display_id,
                            'total': total, 'count': len(tx_ids)})
        except Exception as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return jsonify({'status': 'error', 'msg': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements/<int:settlement_id>/pay', methods=['POST'])
    @role_required(EDIT_ROLES)
    @stepup_required
    def api_voucher_settlement_pay(settlement_id):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute(
                "UPDATE voucher_settlements SET status='paid', paid_at=NOW(), paid_by=%s "
                "WHERE id=%s AND status='draft'", (_actor(), settlement_id))
            affected = cur.rowcount
            conn.commit()
            cur.close()
            if affected == 0:
                return jsonify({'status': 'error',
                                'msg': 'Tagihan tidak ditemukan atau sudah dibayar.'}), 409
            log_activity_async(0, 'voucher_paid', session.get('user_role', ''),
                               _actor(), new_data={'settlement_id': settlement_id},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Tagihan ditandai sudah dibayar'})
        except Exception as exc:
            return jsonify({'status': 'error', 'msg': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements/<int:settlement_id>/cancel', methods=['POST'])
    @role_required(EDIT_ROLES)
    @stepup_required
    def api_voucher_settlement_cancel(settlement_id):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT status FROM voucher_settlements WHERE id=%s", (settlement_id,))
            row = cur.fetchone()
            if not row:
                cur.close()
                return jsonify({'status': 'error', 'msg': 'Tagihan tidak ditemukan'}), 404
            if row['status'] != 'draft':
                cur.close()
                return jsonify({'status': 'error',
                                'msg': 'Hanya tagihan berstatus draft yang bisa dibatalkan'}), 409
            cur.execute(
                "UPDATE transactions SET settlement_id=NULL, settled_at=NULL, settled_by=NULL, "
                "status='verified_ga' WHERE settlement_id=%s AND status='archived'", (settlement_id,))
            cur.execute(
                "UPDATE voucher_settlements SET status='cancelled' WHERE id=%s", (settlement_id,))
            conn.commit()
            cur.close()
            log_activity_async(0, 'voucher_cancel', session.get('user_role', ''),
                               _actor(), new_data={'settlement_id': settlement_id},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Tagihan dibatalkan; voucher kembali terbuka'})
        except Exception as exc:
            return jsonify({'status': 'error', 'msg': str(exc)[:200]}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---- PDF ----
    @app.route('/api/voucher/<int:tx_id>/pdf')
    @role_required(USAGE_ROLES)
    def api_voucher_usage_pdf(tx_id):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return make_response('DB error', 500)
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM transactions WHERE id=%s AND transaction_type='CLAIM' "
                "AND COALESCE(voucher_value, 0) > 0", (tx_id,))
            tx = cur.fetchone()
            if not tx:
                cur.close()
                return make_response('Transaksi voucher tidak ditemukan', 404)
            if session.get('user_role') == 'driver':
                from modules.helpers import session_driver_name
                if (session_driver_name() or '').upper() != (tx.get('driver_name') or '').upper():
                    cur.close()
                    return make_response('Akses ditolak', 403)
            cur.close()

            from modules.pdf_generator import VoucherUsagePDF
            pdf = VoucherUsagePDF()
            try:
                pdf.set_identity(branch_code=session.get('branch_code'))
            except Exception:
                pass
            pdf.add_page()
            pdf.generate(tx, app.config.get('UPLOAD_FOLDER', 'uploads'))
            raw = pdf.output(dest='S')
            data = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
            fname = f"Voucher_{tx.get('display_id', tx_id)}.pdf"
            resp = make_response(data)
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
            log_activity_async(tx_id, 'voucher_pdf', session.get('user_role', ''),
                               _actor(), ip=request.remote_addr)
            try:
                from modules.doc_integrity import register_pdf
                register_pdf('voucher_usage', tx.get('display_id') or f'id-{tx_id}', data,
                             signer_name=tx.get('ga_approved_by') or _actor(),
                             signer_role='ga',
                             branch_code=session.get('branch_code') or '',
                             filename=fname,
                             meta={'tx_id': tx_id, 'status': tx.get('status')})
            except Exception:
                pass
            return resp
        except Exception as exc:
            return make_response(f'Error: {exc}', 500)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @app.route('/api/voucher/settlements/<int:settlement_id>/pdf')
    @role_required(VIEW_ROLES)
    def api_voucher_settlement_pdf(settlement_id):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                return make_response('DB error', 500)
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM voucher_settlements WHERE id=%s", (settlement_id,))
            head = cur.fetchone()
            if not head:
                cur.close()
                return make_response('Tagihan tidak ditemukan', 404)
            cur.execute("""
                SELECT display_id, driver_name, nopol, bbm_type, nominal, liter,
                       voucher_value, daily_code, voucher_partner, nota_no, created_at
                FROM transactions WHERE settlement_id=%s ORDER BY created_at ASC, id ASC
            """, (settlement_id,))
            items = cur.fetchall() or []
            cur.close()

            from modules.pdf_generator import VoucherSettlementPDF
            pdf = VoucherSettlementPDF()
            try:
                pdf.set_identity(branch_code=session.get('branch_code'))
            except Exception:
                pass
            pdf.add_page()
            pdf.generate(head, items)
            raw = pdf.output(dest='S')
            data = raw.encode('latin-1') if isinstance(raw, str) else bytes(raw)
            fname = f"BeritaAcara_Voucher_{head.get('display_id', settlement_id)}.pdf"
            resp = make_response(data)
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
            log_activity_async(0, 'voucher_settlement_pdf', session.get('user_role', ''),
                               _actor(), new_data={'settlement_id': settlement_id},
                               ip=request.remote_addr)
            try:
                from modules.doc_integrity import register_pdf
                register_pdf('voucher_settlement', head.get('display_id') or f'id-{settlement_id}',
                             data, signer_name=head.get('paid_by') or _actor(),
                             signer_role='finance',
                             branch_code=session.get('branch_code') or '',
                             filename=fname,
                             meta={'settlement_id': settlement_id,
                                   'count': head.get('voucher_count'),
                                   'total': float(head.get('total_amount') or 0)})
            except Exception:
                pass
            return resp
        except Exception as exc:
            return make_response(f'Error: {exc}', 500)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # dipakai modul lain bila perlu format tanggal
    app.jinja_env.globals['voucher_fmt_date'] = _fmt_date
