#!/usr/bin/env python3
"""Smoke test PDF Generator v2.72.0 — jalankan di container bpf-workhub-web.

Cakupan: kedua PDF yang menyentuh transaksi BBM —
  1) PDF per-transaksi (/admin/report/<id>, tx is_reported=TRUE agar tidak
     menandai data produksi baru) — mark is_reported hanya setelah render.
  2) Rekap dana BBM (/admin/rekap/pdf) + filter type (CLAIM vs CASH_LPJ)
     yang di v2.71.0-lama adalah dead parameter.
  3) Hasil engine get_rekap_data (multifill) kembali dimanfaatkan renderer.
"""
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
        # v2.104.0: sesi WAJIB punya branch_code (isolasi cabang v2.99.1).
        if branch:
            s['branch_code'] = branch
        else:
            s.pop('branch_code', None)
        s['csrf_token'] = 'x'


def main():
    import datetime as dt
    from modules.engine import get_rekap_data
    import modules.config as cfg

    c = app.test_client()

    # --- role gate ---
    rv = c.get('/admin/rekap/pdf')
    check('rekap tanpa login ditolak', rv.status_code in (401, 403, 302), str(rv.status_code))
    rv = c.get('/admin/report/1')
    check('report tanpa login ditolak', rv.status_code in (401, 403, 302), str(rv.status_code))

    # --- finance login ---
    login(c, 'finance')

    # 1) PDF per-transaksi: pakai tx yang SUDAH is_reported=TRUE
    conn = cfg.get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, display_id, nopol FROM transactions WHERE is_reported=TRUE ORDER BY id DESC LIMIT 1")
    tx = cur.fetchone()
    check('ada tx is_reported=TRUE untuk smoke', bool(tx))
    if tx:
        rv = c.get(f"/admin/report/{tx['id']}")
        check('PDF per-tx → 200', rv.status_code == 200, str(rv.status_code))
        check('content-type application/pdf', 'application/pdf' in rv.headers.get('Content-Type', ''),
              rv.headers.get('Content-Type', ''))
        data = rv.get_data()
        check('magic %PDF', data[:5] == b'%PDF-', repr(data[:8]))
        check('ukuran layak (>2KB)', len(data) > 2000, f'{len(data)}B')
        filename = rv.headers.get('Content-Disposition', '')
        check('nama file BPF_Report_', filename.startswith('attachment; filename=BPF_Report_'), filename[:60])
        cur.execute("SELECT is_reported FROM transactions WHERE id=%s", (tx['id'],))
        check('is_reported tetap TRUE setelah download', bool(cur.fetchone()['is_reported']))

    # 2) Rekap PDF — periode diambil dari DATA, bukan dari asumsi "bulan
    #    berjalan". Klaim final (dibayar/arsip) & LPJ sah tidak selalu ada di
    #    bulan ini; asumsi bulan berjalan bikin smoke merah tanpa ada bug.
    today = dt.date.today()
    from modules import bbm_scope
    probe = get_rekap_data(start_date='2000-01-01', end_date=today.isoformat())
    if probe:
        dates = sorted(str(r.get('created_at') or '')[:10] for r in probe)
        dates = [d for d in dates if d]
        start, end = (dates[0], dates[-1]) if dates else (
            today.replace(day=1).isoformat(), today.isoformat())
    else:
        start, end = today.replace(day=1).isoformat(), today.isoformat()
    print(f"	info: periode rekap dari data = {start} s/d {end} ({len(probe)} baris)")
    rv = c.get(f'/admin/rekap/pdf?start_date={start}&end_date={end}')
    check('rekap PDF → 200', rv.status_code == 200, str(rv.status_code))
    check('rekap content-type application/pdf', 'application/pdf' in rv.headers.get('Content-Type', ''))
    check('rekap magic %PDF', rv.get_data()[:5] == b'%PDF-')
    # v2.104.0: rekap kosong kini menjawab 404 + pesan jelas (bukan redirect
    # diam-diam yang membuat pengguna mengira PDF rusak) — expectation lama
    # masih menyebut 302.
    rv = c.get('/admin/rekap/pdf?start_date=1999-01-01&end_date=1999-01-02')
    check('rekap periode kosong → 404 + pesan', rv.status_code == 404
          and 'Tidak ada data' in rv.get_data(as_text=True), str(rv.status_code))

    # 3) filter tx_type (restorasi) — verifikasi kontra SQL manual
    rows_all = get_rekap_data(start_date=start, end_date=end)
    rows_kas = get_rekap_data(start_date=start, end_date=end, tx_type='CASH_LPJ')
    rows_claim = get_rekap_data(start_date=start, end_date=end, tx_type='CLAIM')
    check('engine tx_type=CASH_LPJ murni kasbon',
          all(r.get('transaction_type') == 'CASH_LPJ' for r in rows_kas), f'{len(rows_kas)} baris')
    check('engine tx_type=CLAIM murni klaim',
          all(r.get('transaction_type') == 'CLAIM' for r in rows_claim), f'{len(rows_claim)} baris')
    # v2.104.0: bandingkan dengan definisi RESMI (modules/bbm_scope.py) —
    # daftar status manual lama (v2.71) sudah tidak sama dengan engine
    # sejak definisi tunggal v2.101.0, jadi perbandingan ini perlu ikut
    # sumber kebenaran agar tidak menyimpang diam-diam.
    cur.execute(f"""SELECT COUNT(*) n FROM transactions
                    WHERE {bbm_scope.REKAP_SCOPE_SQL}
                      AND transaction_type='CASH_LPJ'
                      AND (is_dummy=0 OR is_dummy IS NULL)
                      AND DATE(created_at)>=%s AND DATE(created_at)<=%s""", (start, end))
    n_sql = int(cur.fetchone()['n'])
    check('jumlah kasbon engine = SQL manual', len(rows_kas) == n_sql, f'engine={len(rows_kas)} sql={n_sql}')

    # 4) hasil engine multifill tampil di baris (fitur restorasi)
    if rows_all:
        smp = rows_all[0]
        check('engine mengeluarkan keys multifill',
              all(k in smp for k in ('km_awal', 'km_akhir', 'total_km', 'rata_rata', 'is_multifill')))
    n_rej = sum(1 for r in rows_all if r.get('status') == 'rejected')
    print(f"	info: rows_all={len(rows_all)} kasbon={len(rows_kas)} klaim={len(rows_claim)} rejected={n_rej}")

    # 5) PDF rekap dengan filter type: 200+PDF bila ada baris,
    #    404 + "Tidak ada data" bila kosong — bukan error, bukan redirect.
    rv = c.get(f'/admin/rekap/pdf?start_date={start}&end_date={end}&type=CASH_LPJ')
    if len(rows_kas) > 0:
        check('rekap ?type=CASH_LPJ → 200 pdf',
              rv.status_code == 200 and rv.get_data()[:5] == b'%PDF-', str(rv.status_code))
    else:
        check('rekap ?type=CASH_LPJ kosong → 404 "Tidak ada data"',
              rv.status_code == 404 and 'Tidak ada data' in rv.get_data(as_text=True),
              str(rv.status_code))
    rv = c.get(f'/admin/rekap/pdf?start_date={start}&end_date={end}&type=CLAIM')
    if len(rows_claim) > 0:
        check('rekap ?type=CLAIM → 200 pdf',
              rv.status_code == 200 and rv.get_data()[:5] == b'%PDF-', str(rv.status_code))
    else:
        check('rekap ?type=CLAIM kosong → 404 "Tidak ada data"',
              rv.status_code == 404 and 'Tidak ada data' in rv.get_data(as_text=True),
              str(rv.status_code))

    print()
    print(f'RESULT  PASS={len(PASS)}  FAIL={len(FAIL)}')
    if FAIL:
        print('PERLU TINDAKAN: ' + '; '.join(FAIL))
        sys.exit(1)


if __name__ == '__main__':
    main()
