#!/usr/bin/env python3
"""Smoke test UI role FINANCE (audit keselarasan FE↔BE, 2026-10-28) — di container.

Cara:
  docker cp scripts/smoke_finance_ui.py bpf-workhub-web:/tmp/
  docker exec -w /app bpf-workhub-web python3 /tmp/smoke_finance_ui.py

Membedah seluruh endpoint yang dipanggil halaman-halaman finance
(dashboard AdminDashboard/FinanceDashboard, Trips, Rekap, Cash, Analytics,
Approvals, Water, Procurement, Expenses) langsung ke DB REAL cabang aktif:

  1. READ-WALK: setiap GET yang dipanggil UI finance → wajib 200 (404
     hanya untuk id uji yang memang tidak ada).
  2. WRITE-GUARD NEGATIF (TANPA mutasi data uang nyata):
     - endpoint finance wajib step-up → 428 STEPUP_REQUIRED sebelum body
       jalan (payout, cash approve-finance, water verify);
     - endpoint yang TIDAK untuk finance → 403 (queue reject/modify = GA);
     - endpoint finance yang tidak ber-step-up (archive, brand CRUD) → sehat
       via id 999999 (409/404) + 1 siklus create→delete merk uji (cleanup).
Semua pengujian read-only terhadap data uang nyata; jejak audit uji
(jika ada) hanya pada merk air minum bernama UJIFIN-* yang langsung
dinonaktifkan kembali.
"""
import sys
import time

sys.path.insert(0, '/app')
from app import app  # noqa: E402

RUN = str(int(time.time()))[-6:]
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
            s['branch_code'] = 'SBY'
            s['csrf_token'] = 'x'

    def post(path, **kw):
        kw.setdefault('headers', {})
        kw['headers']['X-CSRF-Token'] = 'x'
        return client.post(path, **kw)

    def delete(path, **kw):
        kw.setdefault('headers', {})
        kw['headers']['X-CSRF-Token'] = 'x'
        return client.delete(path, **kw)

    login()

    print('== 1. READ-WALK halaman finance ==')
    # GET yang wajib 200 (data bisa kosong, tapi jangan 401/403/500)
    must200 = [
        '/api/stats',                       # AdminDashboard (antarrekap)
        '/api/nav/badges',                  # badge sidebar
        '/api/queue',                       # Antrean Verifikasi / FinanceDashboard
        '/api/transaction-flags',           # filter anomali
        '/api/subsidy/status',              # kartu Subsidi Tepat
        '/api/subsidy/otp/status',          # sesi OTP agen
        '/api/subsidy/attest',              # dokumen berita acara
        '/api/transactions/archive',        # RekapView
        '/api/trips',                       # TripsView
        '/api/cash/history',                # CashView (finance = semua driver)
        '/api/cash/pending-lpj',            # CashView
        '/api/cash/daily-code',             # CashView kode harian
        '/api/water/brands',                # WaterView master merk
        '/api/water/edit-enabled',          # status edit/hapus (v2.37)
        '/api/water/purchases',             # WaterView pengajuan
        '/api/water/recap',                 # kartu rekap air minum
        '/api/procurement/orders',          # ProcurementView
        '/api/procurement/suppliers',       # ProcurementView master supplier
        '/api/vehicle-health',              # AnalyticsView
        '/api/analytics/data',              # AnalyticsView
        '/api/approvals',                   # ApprovalsView (finance diizinkan BE)
    ]
    for p in must200:
        r = client.get(p)
        ok = r.status_code == 200
        extra = '' if ok else f'→ HTTP {r.status_code} {r.get_data(as_text=True)[:90]}'
        check(f'GET {p}', ok, extra)

    # GET dengan id uji: 200 ATAU 404 sah (tergantung isi DB), JANGAN 401/403/500
    for p in ['/api/trip-detail/1', '/api/cash/detail/1', '/api/subsidy/match/1']:
        r = client.get(p)
        ok = r.status_code in (200, 404)
        check(f'GET {p} (200/404)', ok, f'→ HTTP {r.status_code}')

    # Rekap pengeluaran (ExpensesView) — pakai tahun aktif & cabang SBY
    r = client.get('/api/expenses/recap?year=2026&branch=SBY')
    check('GET /api/expenses/recap?2026', r.status_code == 200,
          f'→ HTTP {r.status_code} {r.get_data(as_text=True)[:90]}')

    print('== 2. WRITE-GUARD NEGATIF (tanpa mutasi data uang) ==')
    # 2a. Wajib step-up → 428 SEBELUM body jalan: id uji 999999 tak tersentuh
    r = post('/api/queue/payout/999999')
    check('payout tanpa step-up → 428', r.status_code == 428
          and str(r.get_json().get('code')) == 'STEPUP_REQUIRED',
          r.get_data(as_text=True)[:120])
    r = post('/api/cash/approve-finance/999999', json={})
    check('cash approve-finance tanpa step-up → 428', r.status_code == 428,
          r.get_data(as_text=True)[:120])
    r = post('/api/water/purchases/999999/verify', json={'remark': 'uji'})
    check('water verify tanpa step-up → 428', r.status_code == 428,
          r.get_data(as_text=True)[:120])

    # 2b. Endpoint yang bukan untuk finance → 403 (guard GA)
    r = post('/api/queue/reject/999999', json={'reason': 'uji'})
    check('queue/reject oleh finance → 403', r.status_code == 403,
          r.get_data(as_text=True)[:120])
    r = post('/api/queue/modify/999999', json={})
    check('queue/modify oleh finance → 403', r.status_code == 403,
          r.get_data(as_text=True)[:120])
    r = client.get('/api/procurement/orders')
    # kontrol positif: ob dilarang kelola supplier (peran jelas)
    with client.session_transaction() as s2:
        s2['user_role'] = 'ob'
        s2['csrf_token'] = 'x'
    r = delete('/api/water/brands/999999')
    check('water brand delete oleh OB → 403', r.status_code == 403,
          r.get_data(as_text=True)[:120])
    r = post('/api/queue/payout/999999')
    check('payout oleh OB → 403', r.status_code == 403,
          r.get_data(as_text=True)[:120])
    login()  # kembali jadi finance

    # 2c. Endpoint finance tanpa step-up (arsip) — id uji 999999 → 409, tanpa efek
    r = post('/api/queue/archive/999999')
    check('queue/archive finance (id uji) → 409', r.status_code == 409,
          r.get_data(as_text=True)[:120])

    print('== 3. Siklus tulis finance yang bisa dibersihkan (merk air minum) ==')
    data = client.get('/api/water/brands').get_json()
    types = (data or {}).get('types') or []
    brands = (data or {}).get('brands') or []
    check('water/brands shape {types, brands}', isinstance(data, dict)
          and 'types' in data and 'brands' in data)
    type_id = types[0]['id'] if types else None
    if type_id:
        bn = f'UJIFIN-{RUN}'
        r = post('/api/water/brands', json={'type_id': type_id, 'brand': bn})
        bid = (r.get_json() or {}).get('id')
        check('brand uji dibuat finance', r.status_code == 200 and bid,
              r.get_data(as_text=True)[:120])
        r2 = delete(f'/api/water/brands/{bid}')
        check('brand uji dinonaktifkan (cleanup)', r2.status_code == 200,
              r2.get_data(as_text=True)[:120])
    else:
        check('brand uji dibuat finance', False,
              'tipe merk kosong — tidak bisa uji siklus tulis aman')

    # FE memakai shape ini untuk dropdown & daftar merk — wajib konsisten
    data2 = client.get('/api/water/brands').get_json()
    b_after = (data2 or {}).get('brands') or []
    sisa_uji = [b for b in b_after if str(b.get('brand', '')).startswith('UJIFIN-')]
    check('tidak ada merk uji tersisa (bersih)', not sisa_uji, str(sisa_uji[:2]))

    print()
    print(f'HASIL: {len(RIL)} lulus, {len(FAILS)} gagal')
    if FAILS:
        print('GAGAL:')
        for f in FAILS:
            print(f'  - {f}')
        sys.exit(1)
    print('SMOKE FINANCE UI SEHAT')


if __name__ == '__main__':
    main()
