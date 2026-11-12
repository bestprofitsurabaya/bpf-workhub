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

from modules.config import _pool_for, get_master_connection
from modules.helpers import role_required

EXPENSE_ROLES = ['finance', 'admin']

CATEGORIES = ('po', 'kasbon', 'lpj')
MONTHS = 12
MASTER_DB = 'bpf_asset_system'
MASTER_CODE = 'SBY'
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
    cur.execute("""
        SELECT MONTH(handover_at) AS m, COALESCE(SUM(total_amount), 0) AS amount
        FROM fuel_cash_requests
        WHERE status = 'COMPLETED' AND handover_at IS NOT NULL
          AND YEAR(handover_at) = %s
        GROUP BY MONTH(handover_at)
    """, (year,))
    out['kasbon'] = _fill_vector(cur.fetchall())
    cur.execute("""
        SELECT MONTH(created_at) AS m, COALESCE(SUM(nominal), 0) AS amount
        FROM transactions
        WHERE transaction_type = 'CASH_LPJ' AND status <> 'rejected'
          AND (is_dummy = 0 OR is_dummy IS NULL)
          AND YEAR(created_at) = %s
        GROUP BY MONTH(created_at)
    """, (year,))
    out['lpj'] = _fill_vector(cur.fetchall())
    cur.close()
    return out


def _db_name_for(code, branches):
    for b in branches:
        if b['code'] == code:
            return b.get('db_name') or MASTER_DB
    return None


DETAIL_CATEGORIES = ('po', 'kasbon', 'lpj')


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
            WHERE status = 'COMPLETED' AND handover_at IS NOT NULL
              AND YEAR(handover_at) = %s AND MONTH(handover_at) = %s
            ORDER BY handover_at
        """, (year, month))
    else:
        cur.execute("""
            SELECT display_id AS ref, created_at AS date, driver_name AS party,
                   CONCAT('LPJ BBM', IF(COALESCE(nopol, '') = '', '', CONCAT(' · ', nopol)),
                          ' · ', status) AS description,
                   nominal AS amount
            FROM transactions
            WHERE transaction_type = 'CASH_LPJ' AND status <> 'rejected'
              AND (is_dummy = 0 OR is_dummy IS NULL)
              AND YEAR(created_at) = %s AND MONTH(created_at) = %s
            ORDER BY created_at
        """, (year, month))
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
            branch = (request.args.get('branch') or MASTER_CODE).strip().upper()

            mconn = get_master_connection()
            if not mconn:
                return jsonify({'error': 'DB error'}), 500
            try:
                cur = mconn.cursor(dictionary=True)
                cur.execute("""SELECT code, name, db_name FROM branches
                               WHERE is_active=1 ORDER BY id""")
                branches = cur.fetchall()
                cur.close()
            finally:
                try:
                    mconn.close()
                except Exception:
                    pass

            if branch != 'ALL' and branch not in {b['code'] for b in branches}:
                return jsonify({'error': f'Cabang {branch} tidak dikenal'}), 400
            targets = branches if branch == 'ALL' else [b for b in branches if b['code'] == branch]

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
                'selected': branch, 'rows': rows,
                'total': round(sum(float(r.get('amount') or 0) for r in rows), 2),
                'errors': errors,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

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

            branch = (request.args.get('branch') or MASTER_CODE).strip().upper()

            # Daftar cabang aktif dari DB master (branches).
            branches = []
            mconn = get_master_connection()
            if not mconn:
                return jsonify({'error': 'DB error'}), 500
            try:
                cur = mconn.cursor(dictionary=True)
                cur.execute("""SELECT code, name, db_name FROM branches
                               WHERE is_active=1 ORDER BY id""")
                branches = cur.fetchall()
                cur.close()
            finally:
                try:
                    mconn.close()
                except Exception:
                    pass

            if branch != 'ALL' and branch not in {b['code'] for b in branches}:
                return jsonify({'error': f'Cabang {branch} tidak dikenal'}), 400

            targets = branches if branch == 'ALL' else [
                b for b in branches if b['code'] == branch]

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
                            # Total realisasi = barang diterima + LPJ terpakai.
                            'total': [round(agg['po'][i] + agg['lpj'][i], 2)
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
                }
                for d in data.values():
                    for i in range(MONTHS):
                        combined['po'][i] += d['po'][i]
                        combined['kasbon'][i] += d['kasbon'][i]
                        combined['lpj'][i] += d['lpj'][i]
                for k in ('po', 'kasbon', 'lpj'):
                    combined[k] = [round(x, 2) for x in combined[k]]
                combined['total'] = [round(combined['po'][i] + combined['lpj'][i], 2)
                                     for i in range(MONTHS)]

            totals = {}
            for d in data.values():
                for cat in CATEGORIES:
                    totals[cat] = round(totals.get(cat, 0.0) + sum(d[cat]), 2)
            # Total realisasi = PO diterima + LPJ; kasbon dipakai untuk jembatan.
            grand = round(sum(sum(d['total']) for d in data.values()), 2)
            sisa_total = round(totals.get('kasbon', 0.0) - totals.get('lpj', 0.0), 2)
            display = combined or (data.get(branch) if branch in data
                                   else {'name': '—', 'po': _months_vector(),
                                         'kasbon': _months_vector(), 'lpj': _months_vector(),
                                         'total': _months_vector()})
            return jsonify({
                'year': year,
                'selected': branch,
                'categories': list(CATEGORIES),
                'branches': [{'code': b['code'], 'name': b['name']} for b in branches],
                'display': display,
                'per_branch': data,
                'totals': totals,
                'grand_total': grand,
                'sisa_total': sisa_total,
                'basis': {
                    'po': 'qty diterima × harga item, bulan mengikuti tanggal order',
                    'kasbon': 'kasbon COMPLETED, bulan mengikuti tanggal serah dana (handover_at)',
                    'lpj': 'transaksi CASH_LPJ non-rejected, bulan mengikuti tanggal LPJ',
                    'total': 'PO diterima + realisasi LPJ (kasbon bukan pengeluaran final)',
                    'excluded': 'Air minum & overtime belum menyimpan nominal di sistem',
                },
                'errors': errors,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
