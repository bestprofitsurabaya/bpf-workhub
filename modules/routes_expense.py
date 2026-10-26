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

CATEGORIES = ('po', 'kasbon')
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
    cur.close()
    return out


def _db_name_for(code, branches):
    for b in branches:
        if b['code'] == code:
            return b.get('db_name') or MASTER_DB
    return None


def register_expense_routes(app):
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
                            'total': [round(agg['po'][i] + agg['kasbon'][i], 2)
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
                }
                for d in data.values():
                    for i in range(MONTHS):
                        combined['po'][i] += d['po'][i]
                        combined['kasbon'][i] += d['kasbon'][i]
                for k in ('po', 'kasbon'):
                    combined[k] = [round(x, 2) for x in combined[k]]
                combined['total'] = [round(combined['po'][i] + combined['kasbon'][i], 2)
                                     for i in range(MONTHS)]

            totals = {}
            for d in data.values():
                for cat in CATEGORIES:
                    totals[cat] = round(totals.get(cat, 0.0) + sum(d[cat]), 2)
            grand = round(sum(totals.values()), 2)
            display = combined or (data.get(branch) if branch in data
                                   else {'name': '—', 'po': _months_vector(),
                                         'kasbon': _months_vector(), 'total': _months_vector()})
            return jsonify({
                'year': year,
                'selected': branch,
                'categories': list(CATEGORIES),
                'branches': [{'code': b['code'], 'name': b['name']} for b in branches],
                'display': display,
                'per_branch': data,
                'totals': totals,
                'grand_total': grand,
                'errors': errors,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
