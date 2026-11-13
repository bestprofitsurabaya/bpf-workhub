"""Expense Recap Routes (v2.71.0) — Rekap Pengeluaran lintas modul.

Laporan pengeluaran bulanan yang menggabungkan dua sumber biaya yang
ANGKA-NYA TERUKUR di sistem (per DB cabang):

1. Pembelian Barang (PO)  — nilai barang yang benar-benar diterima:
   SUM(qty_terima × harga_item) atas PO status open/partial/closed,
   bulan mengikuti order_date. (Barang belum terima = belum jadi biaya
   realisasi; PO cancelled tak pernah punya penerimaan.)
2. Kasbon BBM (fuel_cash_requests) — uang yang benar-benar keluar:
   SUM(total_amount) status COMPLETED, bulan mengikuti handover_at
   (penyerahan dana ke driver/OB).
3. Realisasi LPJ BBM (transactions.transaction_type='CASH_LPJ') — nilai
   yang benar-benar dipertanggungjawabkan driver. Status rejected tidak
   dihitung. Bulan mengikuti created_at transaksi LPJ.

Total realisasi = Pembelian diterima + Realisasi LPJ. Kasbon cair BUKAN
pengeluaran final: ia dana muka. Sisa = Kasbon cair - Realisasi LPJ.

Sumber yang SENGAJA TIDAK dimasukkan (angkanya tak terukur di sistem):
- Air minum (water_purchases tidak menyimpan harga pembelian).
- Overtime (overtime_driver tidak menyimpan nominal bayaran).
Keduanya akan diikuti saat kolom nominal tersedia — jangan mengarang angka.

Scope: permintaan selalu menjawab SELURUH kategori per cabang yang dipilih
(atau gabungan semua cabang aktif) untuk satu tahun, sehingga kartu total &
tabel bulanan konsisten antar-cabang.

Tidak ada DDL — modul ini murni agregasi atas tabel yang dijamin oleh
schema ensure modul lain; koneksi gagal/tabel belum siap per cabang dilaporkan
di kolom `errors` tanpa merusak cabang lain.
"""
from flask import request, jsonify, session

from modules import bbm_action_queue, bbm_scope
from modules.branch_scope import resolve_report_scope
from modules.config import _pool_for, get_db_connection, get_master_connection
from modules.helpers import role_required

EXPENSE_ROLES = ['finance', 'admin']

CATEGORIES = ('po', 'kasbon', 'lpj', 'voucher')
MONTHS = 12
MASTER_DB = 'bpf_asset_system'
MIN_YEAR, MAX_YEAR = 2020, 2035


def _months_vector():
    return [0.0] * MONTHS


def _fill_vector(rows, key_month='m', key_amount='amount'):
    """Ubah baris GROUP BY bulan → vektor 12 bulan (index 0 = Januari)."""
    vec = _months_vector()
    for r in rows or []:
        m = int(r[key_month] or 0)
        if 1 <= m <= MONTHS:
            vec[m - 1] += round(float(r[key_amount] or 0), 2)
    return [round(x, 2) for x in vec]


def _query_db(conn, year):
    """Agregasi dua kategori dari satu DB. Return {'po': vec, 'kasbon': vec}."""
    cur = conn.cursor(dictionary=True)
    out = {}
    cur.execute("""
        SELECT MONTH(po.order_date) AS m,
               COALESCE(SUM(COALESCE(ri.qty, 0) * i.price), 0) AS amount
        FROM purchase_orders po
        JOIN po_items i ON i.po_id = po.id
        LEFT JOIN (SELECT item_id, SUM(qty) AS qty FROM po_receipts
                   GROUP BY item_id) ri ON ri.item_id = i.id
        WHERE po.status IN ('open','partial','closed')
          AND YEAR(po.order_date) = %s
        GROUP BY MONTH(po.order_date)
    """, (year,))
    out['po'] = _fill_vector(cur.fetchall())
    # v2.100.1: definisi tunggal (modules/bbm_scope.py).
    # Kasbon cair = handover_at terisi (termasuk dana yang masih di driver),
    # LPJ = hanya yang sah (verified_ga/archived), bukan semua non-rejected.
    out['kasbon'] = _fill_vector(bbm_scope.monthly_cash_rows(conn, year))
    out['lpj'] = _fill_vector(bbm_scope.monthly_lpj_rows(conn, year))
    out['voucher'] = _fill_vector(bbm_scope.monthly_voucher_rows(conn, year))
    out['outstanding'] = bbm_scope.cash_totals(conn)['outstanding']
    cur.close()
    return out


def _load_branches():
    """Daftar cabang aktif dari DB master. Returns (branches, error_response)."""
    mconn = get_master_connection()
    if not mconn:
        return None, (jsonify({'error': 'DB error'}), 500)
    cur = None
    try:
        cur = mconn.cursor(dictionary=True)
        cur.execute("""SELECT code, name, db_name FROM branches
                       WHERE is_active=1 ORDER BY id""")
        return cur.fetchall(), None
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        try:
            mconn.close()
        except Exception:
            pass


def _scope_error_response(error):
    """400 untuk cabang tak dikenal, 403 untuk akses lintas cabang."""
    if error == 'unknown':
        return jsonify({'error': 'Cabang tidak dikenal'}), 400
    return jsonify({
        'error': 'Akses lintas cabang ditolak — laporan ini hanya untuk cabang Anda.',
    }), 403


def _db_name_for(code, branches):
    for b in branches:
        if b['code'] == code:
            return b.get('db_name') or MASTER_DB
    return None


DETAIL_CATEGORIES = ('po', 'kasbon', 'lpj', 'voucher')


def _detail_rows(conn, year, month, category):
    """Rincian baris untuk drill-down satu bulan & satu kategori."""
    cur = conn.cursor(dictionary=True)
    if category == 'po':
        cur.execute("""
            SELECT po.display_id AS ref, po.order_date AS date,
                   po.supplier_name AS party,
                   CONCAT(i.description, ' (', COALESCE(ri.qty, 0), ' ', COALESCE(i.satuan, ''), ')') AS description,
                   i.price AS unit_price, COALESCE(ri.qty, 0) AS qty,
                   ROUND(COALESCE(ri.qty, 0) * i.price, 2) AS amount
            FROM purchase_orders po
            JOIN po_items i ON i.po_id = po.id
            LEFT JOIN (SELECT item_id, SUM(qty) AS qty FROM po_receipts
                       GROUP BY item_id) ri ON ri.item_id = i.id
            WHERE po.status IN ('open','partial','closed')
              AND YEAR(po.order_date) = %s AND MONTH(po.order_date) = %s
              AND COALESCE(ri.qty, 0) > 0
            ORDER BY po.order_date, po.id
        """, (year, month))
    elif category == 'kasbon':
        cur.execute("""
            SELECT display_id AS ref, handover_at AS date, driver_name AS party,
                   CONCAT('Kasbon BBM', IF(COALESCE(nopol, '') = '', '', CONCAT(' · ', nopol))) AS description,
                   total_amount AS amount
            FROM fuel_cash_requests
            WHERE handover_at IS NOT NULL
              AND YEAR(handover_at) = %s AND MONTH(handover_at) = %s
            ORDER BY handover_at
        """, (year, month))
    elif category == 'lpj':
        # v2.104.0: definisi "LPJ sah" diambil dari sumber tunggal
        # (modules/bbm_scope.py) — drill-down harus sama dengan kartu & PDF.
        cur.execute("""
            SELECT display_id AS ref, created_at AS date, driver_name AS party,
                   CONCAT('LPJ BBM', IF(COALESCE(nopol, '') = '', '', CONCAT(' · ', nopol)),
                          ' · ', status) AS description,
                   nominal AS amount
            FROM transactions
            WHERE transaction_type = 'CASH_LPJ'
              AND """ + bbm_scope.statuses_in(bbm_scope.LPJ_VALID_STATUSES) + """
              AND (is_dummy = 0 OR is_dummy IS NULL)
              AND YEAR(created_at) = %s AND MONTH(created_at) = %s
            ORDER BY created_at
        """, tuple(bbm_scope.LPJ_VALID_STATUSES) + (year, month))
    else:
        # v2.107.0: voucher rekanan — beban BBM sekali saat pemakaian sah.
        cur.execute("""
            SELECT display_id AS ref, created_at AS date,
                   COALESCE(NULLIF(voucher_partner, ''), 'SPBU Rekanan') AS party,
                   CONCAT('Voucher BBM', IF(COALESCE(nopol, '') = '', '', CONCAT(' · ', nopol)),
                          IF(COALESCE(nota_no, '') = '', '', CONCAT(' · nota ', nota_no))) AS description,
                   nominal AS amount
            FROM transactions
            WHERE transaction_type = 'CLAIM'
              AND COALESCE(voucher_value, 0) > 0
              AND """ + bbm_scope.statuses_in(bbm_scope.VOUCHER_VALID_STATUSES) + """
              AND (is_dummy = 0 OR is_dummy IS NULL)
              AND YEAR(created_at) = %s AND MONTH(created_at) = %s
            ORDER BY created_at
        """, tuple(bbm_scope.VOUCHER_VALID_STATUSES) + (year, month))
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        if r.get('date') is not None and hasattr(r['date'], 'isoformat'):
            r['date'] = r['date'].isoformat()
        for key in ('amount', 'qty', 'unit_price'):
            if r.get(key) is not None:
                r[key] = float(r[key])
    return rows


def register_expense_routes(app):
    @app.route('/api/expenses/detail')
    @role_required(EXPENSE_ROLES)
    def api_expense_detail():
        """Drill-down satu bulan: ?year=&month=&branch=CODE|ALL&category=po|kasbon|lpj."""
        try:
            import datetime as _dt
            year = request.args.get('year', type=int) or _dt.date.today().year
            year = max(MIN_YEAR, min(MAX_YEAR, year))
            month = request.args.get('month', type=int) or 1
            if not 1 <= month <= MONTHS:
                return jsonify({'error': 'Bulan harus 1-12'}), 400
            category = (request.args.get('category') or '').strip().lower()
            if category not in DETAIL_CATEGORIES:
                return jsonify({'error': 'Kategori tidak dikenal'}), 400
            branches, err_resp = _load_branches()
            if err_resp:
                return err_resp
            # v2.99.1: cakupan cabang — Finance cabang terkunci ke cabangnya.
            targets, branch, _visible, scope_err = resolve_report_scope(
                branches, request.args.get('branch'))
            if scope_err:
                return _scope_error_response(scope_err)

            rows, errors = [], {}
            for b in targets:
                db_name = b.get('db_name') or MASTER_DB
                conn = None
                try:
                    if db_name == MASTER_DB:
                        conn = get_master_connection()
                    else:
                        pool = _pool_for(db_name)
                        conn = pool.get_connection() if pool else None
                    if not conn:
                        errors[b['code']] = 'DB tidak tersedia'
                        continue
                    for row in _detail_rows(conn, year, month, category):
                        row['branch_code'] = b['code']
                        row['branch_name'] = b['name']
                        rows.append(row)
                except Exception as e:
                    errors[b['code']] = str(e)[:200]
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

            rows.sort(key=lambda r: (r.get('date') or '', r.get('ref') or ''))
            return jsonify({
                'year': year, 'month': month, 'category': category,
                'selected': branch,
                'scope': {'all_branches': len(_visible) == len(branches)},
                'rows': rows,
                'total': round(sum(float(r.get('amount') or 0) for r in rows), 2),
                'errors': errors,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/bbm/workspace/summary')
    @role_required(['ga', 'finance', 'admin'])
    def api_bbm_workspace_summary():
        """Ringkasan satu periode dengan definisi tunggal (modules/bbm_scope.py).

        Angka di sini = angka Rekap/Realisasi/Analisis pada periode yang sama:
        klaim per ember status, LPJ diajukan vs sah, kasbon cair/selesai, dan
        dana yang masih di driver. Cakupan cabang mengikuti DB sesi.
        """
        try:
            import datetime as _dt
            start = (request.args.get('start_date') or '').strip()
            end = (request.args.get('end_date') or '').strip()
            if not (start and end):
                d_start, d_end = bbm_scope.default_period(30)
                start, end = start or d_start, end or d_end
            for value in (start, end):
                try:
                    _dt.date.fromisoformat(value)
                except ValueError:
                    return jsonify({'error': 'Tanggal harus YYYY-MM-DD'}), 400
            if start > end:
                return jsonify({'error': 'Tanggal awal melebihi tanggal akhir'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            try:
                data = bbm_scope.summary(conn, start, end)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            data['meta']['generated_at'] = _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data['meta']['branch'] = (session.get('branch_code') or '').upper() or None
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)[:200]}), 500

    @app.route('/api/bbm/workspace/actions')
    @role_required(['ga', 'finance', 'admin'])
    def api_bbm_workspace_actions():
        """Antrean 'Perlu Tindakan' — umur antrean, bukan angka periode.

        Cakupan cabang mengikuti DB sesi (get_db_connection). Aksi uang tidak
        dilakukan di sini: endpoint ini hanya membaca dan menunjuk tab tujuan.
        """
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            try:
                data = bbm_action_queue.action_queue(conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            data['meta'] = {
                'branch': (session.get('branch_code') or '').upper() or None,
                'generated_at': data.get('generated_at'),
                # Jenis antrean yang gagal (mis. kolom belum ada di DB cabang
                # lama) dilaporkan, bukan disembunyikan.
                'errors': data.get('errors') or [],
            }
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)[:200]}), 500

    @app.route('/api/expenses/recap')
    @role_required(EXPENSE_ROLES)
    def api_expense_recap():
        """Rekap pengeluaran bulanan: ?year=YYYY&branch=CODE|all (default tahun berjalan)."""
        try:
            year = request.args.get('year') or ''
            try:
                year = int(year)
            except (TypeError, ValueError):
                import datetime as _dt
                year = _dt.date.today().year
            year = max(MIN_YEAR, min(MAX_YEAR, year))

            # Daftar cabang aktif dari DB master (branches), lalu dipersempit
            # ke cakupan sesi. Finance cabang tidak menerima daftar/pool
            # cabang lain — bukan hanya angkanya yang disembunyikan.
            branches, err_resp = _load_branches()
            if err_resp:
                return err_resp
            targets, branch, _visible, scope_err = resolve_report_scope(
                branches, request.args.get('branch'))
            if scope_err:
                return _scope_error_response(scope_err)

            data = {}
            errors = {}
            for b in targets:
                db_name = b.get('db_name') or MASTER_DB
                try:
                    if db_name == MASTER_DB:
                        conn = get_master_connection()
                    else:
                        pool = _pool_for(db_name)
                        conn = pool.get_connection() if pool else None
                    if not conn:
                        errors[b['code']] = 'DB tidak tersedia'
                        continue
                    try:
                        agg = _query_db(conn, year)
                        data[b['code']] = {
                            'name': b['name'],
                            'po': agg['po'],
                            'kasbon': agg['kasbon'],
                            'lpj': agg['lpj'],
                            'voucher': agg.get('voucher') or _months_vector(),
                            'outstanding': agg.get('outstanding') or {'count': 0, 'amount': 0},
                            # Total realisasi = barang diterima + LPJ terpakai
                            # + voucher rekanan terpakai (sekali).
                            'total': [round(agg['po'][i] + agg['lpj'][i]
                                            + (agg.get('voucher') or _months_vector())[i], 2)
                                      for i in range(MONTHS)],
                        }
                    finally:
                        try:
                            conn.close()
                        except Exception:
                            pass
                except Exception as e:
                    errors[b['code']] = str(e)[:200]

            # Gabungan lintas cabang bila scope ALL
            combined = None
            if branch == 'ALL' and data:
                combined = {
                    'name': 'Semua Cabang',
                    'po': _months_vector(),
                    'kasbon': _months_vector(),
                    'lpj': _months_vector(),
                    'voucher': _months_vector(),
                }
                for d in data.values():
                    for i in range(MONTHS):
                        combined['po'][i] += d['po'][i]
                        combined['kasbon'][i] += d['kasbon'][i]
                        combined['lpj'][i] += d['lpj'][i]
                        combined['voucher'][i] += d['voucher'][i]
                for k in ('po', 'kasbon', 'lpj', 'voucher'):
                    combined[k] = [round(x, 2) for x in combined[k]]
                combined['total'] = [round(combined['po'][i] + combined['lpj'][i]
                                           + combined['voucher'][i], 2)
                                     for i in range(MONTHS)]

            totals = {}
            for d in data.values():
                for cat in CATEGORIES:
                    totals[cat] = round(totals.get(cat, 0.0) + sum(d[cat]), 2)
            # Total realisasi = PO diterima + LPJ; kasbon dipakai untuk jembatan.
            grand = round(sum(sum(d['total']) for d in data.values()), 2)
            sisa_total = round(totals.get('kasbon', 0.0) - totals.get('lpj', 0.0), 2)
            outstanding_total = round(sum(
                float((d.get('outstanding') or {}).get('amount') or 0)
                for d in data.values()), 2)
            outstanding_count = sum(
                int((d.get('outstanding') or {}).get('count') or 0)
                for d in data.values())
            display = combined or (data.get(branch) if branch in data
                                   else {'name': '—', 'po': _months_vector(),
                                         'kasbon': _months_vector(), 'lpj': _months_vector(),
                                         'voucher': _months_vector(),
                                         'total': _months_vector()})
            return jsonify({
                'year': year,
                'selected': branch,
                'scope': {'all_branches': len(_visible) == len(branches)},
                'categories': list(CATEGORIES),
                'branches': [{'code': b['code'], 'name': b['name']} for b in _visible],
                'display': display,
                'per_branch': data,
                'totals': totals,
                'grand_total': grand,
                'sisa_total': sisa_total,
                'outstanding': {'total': outstanding_total, 'count': outstanding_count},
                'basis': {
                    'po': 'qty diterima × harga item, bulan mengikuti tanggal order',
                    'kasbon': 'kasbon yang dananya sudah diserahkan (handover_at), termasuk yang masih di driver',
                    'lpj': 'transaksi CASH_LPJ berstatus verified_ga/archived (LPJ sah), bukan yang masih pending',
                    'voucher': 'baris BBM berlabel SPBU rekanan (voucher) berstatus verified_ga/archived; dihitung sekali saat pemakaian, pembayaran tagihan SPBU bukan beban baru',
                    'total': 'PO diterima + realisasi LPJ + voucher rekanan (kasbon bukan pengeluaran final)',
                    'excluded': 'Air minum & overtime belum menyimpan nominal di sistem',
                },
                'errors': errors,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
