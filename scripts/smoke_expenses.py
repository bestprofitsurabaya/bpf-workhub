#!/usr/bin/env python3
"""Smoke test Rekap Pengeluaran v2.71.0 — jalankan di container bpf-workhub-web."""
import os
import sys

sys.path.insert(0, '/app')
from app import app  # noqa: E402

PASS, FAIL = [], []


def check(label, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + label + (f'  {extra}' if extra and not cond else ''))
    (PASS if cond else FAIL).append(label)


def login(client, role='finance', branch='SBY'):
    with client.session_transaction() as s:
        s['user_role'] = role
        s['user_name'] = role.upper()
        s['full_name'] = role.upper()
        # v2.104.0: sesi WAJIB punya branch_code. Sejak isolasi cabang
        # (v2.99.1) sesi tanpa cabang ditolak 403 — script lama justru
        # MENGHAPUS branch_code sehingga semua pemeriksaan gagal 403.
        if branch:
            s['branch_code'] = branch
        else:
            s.pop('branch_code', None)
        s['csrf_token'] = 'x'


def main():
    import datetime as dt
    import json

    c = app.test_client()

    # --- role gate ---
    rv = c.get('/api/expenses/recap')
    check('tanpa login → 401/403', rv.status_code in (401, 403))
    login(c, 'ga')
    rv = c.get('/api/expenses/recap')
    check('ga ditolak (finance-only)', rv.status_code == 403)

    # --- finance SBY ---
    login(c, 'finance')
    rv = c.get('/api/expenses/recap?year=2026&branch=SBY')
    d = rv.get_json()
    check('finance SBY → 200', rv.status_code == 200, str(d)[:150])
    check('bentuk: 12 bulan', rv.status_code == 200
          and len(d.get('display', {}).get('po', [])) == 12
          and len(d.get('display', {}).get('kasbon', [])) == 12)
    check('totals & grand ada', 'totals' in d and 'grand_total' in d)

    # --- bandingkan angka vs SQL manual (SBY = master) ---
    import modules.config as cfg
    conn = cfg.get_db_connection()
    cur = conn.cursor(dictionary=True)
    year = d.get('year', 2026)
    cur.execute("""SELECT COALESCE(SUM(COALESCE(ri.qty,0)*i.price),0) AS a
                   FROM purchase_orders po JOIN po_items i ON i.po_id=po.id
                   LEFT JOIN (SELECT item_id, SUM(qty) qty FROM po_receipts GROUP BY item_id) ri
                     ON ri.item_id=i.id
                   WHERE po.status IN ('open','partial','closed') AND YEAR(po.order_date)=%s""", (year,))
    po_manual = float(cur.fetchone()['a'])
    cur.execute("""SELECT COALESCE(SUM(total_amount),0) AS a FROM fuel_cash_requests
                   WHERE handover_at IS NOT NULL AND YEAR(handover_at)=%s""", (year,))
    kas_manual = float(cur.fetchone()['a'])
    cur.close(); conn.close()
    po_api = sum(d['display']['po'])
    kas_api = sum(d['display']['kasbon'])
    check('angka PO cocok SQL manual', abs(po_api - po_manual) < 1.0,
          f'api={po_api} sql={po_manual}')
    check('angka kasbon cocok SQL manual', abs(kas_api - kas_manual) < 1.0,
          f'api={kas_api} sql={kas_manual}')
    # v2.108.2: total realisasi = PO diterima + LPJ sah + voucher rekanan.
    # Voucher masuk `total` sejak v2.107.0; assertion lama hanya PO + LPJ
    # sehingga selalu merah di cabang yang punya baris SPBU rekanan.
    check('grand_total = PO + LPJ + voucher',
          abs((d['totals']['po'] + d['totals']['lpj']
               + d['totals'].get('voucher', 0.0)) - d['grand_total']) < 1.0,
          f"po={d['totals']['po']} lpj={d['totals']['lpj']} "
          f"voucher={d['totals'].get('voucher', 0.0)} grand={d['grand_total']}")
    check('sisa kasbon = kasbon cair - LPJ sah',
          abs((d['totals']['kasbon'] - d['totals']['lpj']) - d['sisa_total']) < 1.0,
          f"kasbon={d['totals']['kasbon']} lpj={d['totals']['lpj']} sisa={d['sisa_total']}")

    # --- admin ALL ---
    login(c, 'admin')
    rv = c.get(f'/api/expenses/recap?year={year}&branch=ALL')
    d2 = rv.get_json()
    check('admin ALL → per_branch >= 11 cabang', rv.status_code == 200
          and len(d2.get('per_branch', {})) >= 11, f'n={len(d2.get("per_branch", {}))}')
    check('ALL: total po = jumlah per cabang',
          abs(sum(sum(v['po']) for v in d2['per_branch'].values())
              - sum(d2['display']['po'])) < 1.0)
    check('errors kosong', d2.get('errors') == {}, json.dumps(d2.get('errors', {}))[:100])

    # --- validasi ---
    rv = c.get('/api/expenses/recap?branch=XXX')
    check('cabang tidak dikenal → 400', rv.status_code == 400)
    rv = c.get('/api/expenses/recap?year=bukan-tahun')
    check('tahun invalid → fallback tahun berjalan', rv.status_code == 200
          and rv.get_json().get('year') == dt.date.today().year)

    print()
    print(f'== {len(PASS)} PASS, {len(FAIL)} FAIL ==')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
