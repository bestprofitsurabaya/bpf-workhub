#!/usr/bin/env python3
"""Smoke test modul Pengadaan v2.70.0 — jalankan di dalam container bpf-workhub-web.

Cara:
  docker cp scripts/smoke_procurement.py bpf-workhub-web:/tmp/
  docker exec -w /app bpf-workhub-web python3 /tmp/smoke_procurement.py

Pakai flask test_client + session palsu (user finance) agar menyentuh DB REAL
cabang aktif (master: bpf_asset_system) tanpa browser. Semua data uji
dihapus kembali di akhir (po receipts cascade), suppliers diberi nama uji
lalu dinonaktifkan; jejak audit tersengaja dibiarkan (jejak uji jelas).
"""
import json
import sys
import time

RUN = str(int(time.time()))[-6:]  # suffix unik per run (supplier unique key)

sys.path.insert(0, '/app')
from app import app  # noqa: E402

RIL = []
FAILS = []


def check(label, cond, extra=''):
    if cond:
        print(f'PASS  {label}')
        RIL.append(label)
    else:
        print(f'FAIL  {label} {extra}')
        FAILS.append(label)


def main():
    client = app.test_client()

    def login(role='finance', name='FINANCE_UJI'):
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = name
            s['full_name'] = name
            s.pop('branch_code', None)
            s['csrf_token'] = 'x'

    login()

    def post(path, **kw):
        kw.setdefault('headers', {})
        kw['headers']['X-CSRF-Token'] = 'x'
        return client.post(path, **kw)

    def put(path, **kw):
        kw.setdefault('headers', {})
        kw['headers']['X-CSRF-Token'] = 'x'
        return client.put(path, **kw)

    def delete(path, **kw):
        kw.setdefault('headers', {})
        kw['headers']['X-CSRF-Token'] = 'x'
        return client.delete(path, **kw)

    # 1) Supplier: create → duplikat → list → update
    s_name = f'UJI-PO-SUPPLIER-{RUN}'
    r = post('/api/procurement/suppliers', json={
        'name': s_name, 'category': 'Uji', 'contact_name': 'Budi', 'phone': '081', 'address': 'Jl. Uji'})
    check('supplier create', r.status_code == 200 and r.get_json().get('status') == 'success',
          r.get_data(as_text=True)[:120])
    sup_id = r.get_json().get('id')

    r = post('/api/procurement/suppliers', json={'name': s_name})
    check('supplier duplikat ditolak', r.status_code == 400)

    r = client.get('/api/procurement/suppliers?all=1')
    rows = r.get_json().get('suppliers', [])
    check('supplier list memuat supplier uji', any(x['name'] == s_name for x in rows))

    r = put(f'/api/procurement/suppliers/{sup_id}', json={'category': 'Uji B'})
    check('supplier update', r.status_code == 200)

    r = put('/api/procurement/suppliers/999999', json={'name': 'X'})
    check('supplier update tak ditemukan → 404', r.status_code == 404)

    # 2) PO: create → duplikat item abnormal → detail
    r = post('/api/procurement/orders', json={
        'supplier_id': sup_id, 'order_date': '2026-10-25',
        'notes': 'pengujian v2.70',
        'items': [{'description': 'Tinta Uji', 'qty': 3, 'satuan': 'pcs', 'price': 50000},
                  {'description': 'Kertas Uji', 'qty': 10, 'satuan': 'dus'}]
    })
    j = r.get_json()
    check('PO create', r.status_code == 200 and j.get('status') == 'success', r.get_data(as_text=True)[:150])
    po_id = j['id']
    disp = j.get('display_id', '')
    check('nomor PO format PO-SBY-', disp.startswith('PO-SBY-'), disp)

    r = post('/api/procurement/orders', json={
        'supplier_id': sup_id, 'order_date': '2026-10-25',
        'items': [{'description': '', 'qty': 1}]})
    check('PO item kosong ditolak', r.status_code == 400)

    r = client.get(f'/api/procurement/orders/{po_id}')
    d = r.get_json()
    check('PO detail: 2 item', r.status_code == 200
          and len(d.get('items', [])) == 2, json.dumps(d.get('items', []))[:150])
    check('detail: outstanding item 1 = 3', d['items'][0]['outstanding'] == 3)
    check('total PO = Rp150.000 (tinta) + 0 (kertas tanpa harga)',
          d['total_amount'] == 150000.0, d['total_amount'])

    # 3) Penerimaan: kelebihan dilarang; parsial; menutup
    items = {it['id']: it for it in d['items']}
    item1 = next(it for it in d['items'] if it['description'] == 'Tinta Uji')
    item2 = next(it for it in d['items'] if it['description'] == 'Kertas Uji')

    r = post(f'/api/procurement/orders/{po_id}/receive', json={
        'receipts': [{'item_id': item1['id'], 'qty': 5}]})
    check('penerimaan kelebihan ditolak', r.status_code == 400, r.get_data(as_text=True)[:120])

    r = post(f'/api/procurement/orders/{po_id}/receive', json={
        'receipts': [{'item_id': item1['id'], 'qty': 2, 'note': 'parsial'}]})
    check('penerimaan parsial → partial', r.status_code == 200
          and r.get_json().get('po_status') == 'partial',
          r.get_data(as_text=True)[:160])

    r = client.get(f'/api/procurement/orders/{po_id}')
    d2 = r.get_json()
    check('detail partial: received 2 sisa 1', d2['items'][0]['received'] == 2
          and d2['items'][0]['outstanding'] == 1, json.dumps(d2['items'][0])[:160])
    check('riwayat penerimaan lengkap', len(d2.get('receipts', [])) == 1,
          f'jumlah={len(d2.get("receipts", []))}')

    r = post(f'/api/procurement/orders/{po_id}/receive', json={
        'receipts': [{'item_id': item1['id'], 'qty': 1},
                     {'item_id': item2['id'], 'qty': 10}]})
    check('penerimaan penuh → closed', r.status_code == 200
          and r.get_json().get('po_status') == 'closed', r.get_data(as_text=True)[:160])

    # 4) Pembatalan PO: TANPA grant step-up → 428; DENGAN grant → guard penerimaan
    r = post(f'/api/procurement/orders/{po_id}/cancel', json={'reason': 'x'})
    check('cancel tanpa grant step-up → 428', r.status_code == 428
          and r.get_json().get('code') == 'STEPUP_REQUIRED', r.get_data(as_text=True)[:120])
    with client.session_transaction() as s:
        s['stepup_until'] = time.time() + 600
    r = post(f'/api/procurement/orders/{po_id}/cancel', json={'reason': 'x'})
    check('PO terima-sudah tidak boleh dibatalkan',
          'penerimaan' in r.get_json().get('error', ''), r.get_data(as_text=True)[:150])

    # 5) PO baru dgn status open → batalkan, wajib alasan
    r = post('/api/procurement/orders', json={
        'supplier_id': sup_id, 'order_date': '2026-10-25',
        'items': [{'description': 'Aksesoris Uji', 'qty': 1, 'price': 12300}]})
    po_id2 = r.get_json()['id']
    r = post(f'/api/procurement/orders/{po_id2}/cancel', json={'reason': ''})
    check('batal tanpa alasan ditolak', r.status_code == 400,
          r.get_data(as_text=True)[:120])
    r = post(f'/api/procurement/orders/{po_id2}/cancel', json={'reason': 'uji selesai'})
    check('PO open dibatalkan', r.status_code == 200, r.get_data(as_text=True)[:160])
    r = post(f'/api/procurement/orders/{po_id2}/receive',
                    json={'receipts': [{'item_id': 999999, 'qty': 1}]})
    check('PO cancelled tak bisa diterima', r.status_code == 400)

    # 6) Role gate
    def login_as(role):
        with client.session_transaction() as s:
            s['user_role'] = role
            s['user_name'] = role.upper()
            s['full_name'] = role.upper()
    login_as('ob')
    r = client.get('/api/procurement/orders')
    check('ob mengetik tak diizinkan', r.status_code == 403)
    login_as('ga')
    r = post('/api/procurement/suppliers', json={'name': 'X99', 'phone': 'x'})
    check('ga tak boleh kelola supplier', r.status_code == 403)

    # 7) Cleanup: PO uji (id diketahui) + supplier uji dinonaktifkan —
    #    po_items & po_receipts ikut cascade; jejak audit dibiarkan (jejak uji jelas).
    import modules.config as cfg
    conn = cfg.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM purchase_orders WHERE id IN (%s,%s)", (po_id, po_id2))
    po_clean = cur.rowcount
    cur.execute("UPDATE suppliers SET is_active=0 WHERE name=%s", (s_name,))
    conn.commit(); cur.close(); conn.close()
    check('cleanup PO uji', po_clean >= 2, f'dihapus {po_clean}')

    print()
    print(f'== {len(RIL)} PASS, {len(FAILS)} FAIL ==')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
