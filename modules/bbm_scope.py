"""Definisi tunggal metrik BBM, kasbon, dan LPJ (v2.100.1 — Fase 2).

Sebelum modul ini, tiga halaman menjawab pertanyaan yang sama dengan aturan
berbeda:

- Rekap Klaim  : transaksi `archived` saja.
- Realisasi    : LPJ `<> 'rejected'` (termasuk yang belum diverifikasi) dan
                 kasbon hanya `COMPLETED` (dana yang masih di driver hilang).
- Analisis     : klaim `archived` + kasbon `COMPLETED`.

Modul ini menetapkan satu definisi dan satu pembangun query. Semua laporan
WAJIB memakai fungsi di sini agar angkanya tidak menyimpang lagi.

Definisi resmi
--------------
Klaim BBM (transactions.transaction_type='CLAIM'), basis `created_at`:
  masuk      : status pending / modified
  siap_cair  : status verified_ga
  dibayar    : status os_finance / archived
  final      : status archived

LPJ kasbon (transactions.transaction_type='CASH_LPJ'), basis `created_at`:
  diajukan   : status pending
  sah        : status verified_ga / archived
               (dana sudah keluar saat handover, jadi `archived` bukan syarat)

Kasbon BBM (fuel_cash_requests), basis `handover_at`:
  diajukan   : semua status kecuali REJECTED, basis `created_at`
  cair       : handover_at terisi (dana benar-benar diserahkan)
  selesai    : cair + status COMPLETED (LPJ sudah diverifikasi)
  outstanding: cair + status FUNDS_WITH_DRIVER / LPJ_SUBMITTED
               (dana masih di driver — WAJIB tampil di laporan)

Identitas yang diuji di tests/test_bbm_scope.py:
  kasbon.cair = kasbon.selesai + kasbon.outstanding
"""
from datetime import date, timedelta

CLAIM_OPEN_STATUSES = ('pending', 'modified')
CLAIM_READY_STATUSES = ('verified_ga',)
CLAIM_PAID_STATUSES = ('os_finance', 'archived')
CLAIM_FINAL_STATUSES = ('archived',)

LPJ_OPEN_STATUSES = ('pending',)
LPJ_VALID_STATUSES = ('verified_ga', 'archived')

# Voucher rekanan (v2.107.0): pemakaian sah = verified_ga/archived. Pembayaran
# tagihan ke SPBU bukan beban baru, jadi TIDAK dihitung lagi di laporan.
VOUCHER_OPEN_STATUSES = ('pending', 'modified')
VOUCHER_VALID_STATUSES = ('verified_ga', 'archived')

CASH_OPEN_STATUSES = ('FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED')
CASH_DONE_STATUS = 'COMPLETED'
CASH_VOID_STATUS = 'REJECTED'

def rekap_scope_sql(alias=''):
    """Klausa SQL Rekap Klaim BBM — definisi "final", bukan hanya arsip.

    Klaim final = CLAIM yang sudah dibayar (os_finance/archived) + LPJ kasbon
    yang sah (verified_ga/archived). Dengan begitu Rekap menjawab pertanyaan
    yang sama dengan Realisasi: berapa biaya BBM yang sudah final pada periode
    ini — bukan sekadar berapa baris yang sudah diarsipkan.
    """
    p = f'{alias}.' if alias else ''
    return (
        f"((COALESCE({p}transaction_type, 'CLAIM') = 'CLAIM' "
        f"AND {p}status IN ('os_finance', 'archived')) "
        f"OR ({p}transaction_type = 'CASH_LPJ' "
        f"AND {p}status IN ('verified_ga', 'archived')) "
        f"OR ({p}transaction_type = 'CLAIM' "
        f"AND COALESCE({p}voucher_value, 0) > 0 "
        f"AND {p}status IN ('verified_ga', 'archived')))"
    )


REKAP_SCOPE_SQL = rekap_scope_sql()

BASIS = {
    'claim': 'transactions CLAIM; basis created_at; demo dikecualikan',
    'lpj': 'CASH_LPJ berstatus verified_ga/archived; basis created_at',
    'voucher': 'baris CLAIM berlabel SPBU rekanan (voucher_value terisi), status verified_ga/archived; dihitung sekali saat pemakaian',
    'kasbon': 'fuel_cash_requests dengan handover_at terisi (dana diserahkan)',
    'outstanding': 'kasbon FUNDS_WITH_DRIVER/LPJ_SUBMITTED — dana masih di driver',
    'rekap': 'klaim cash CLAIM os_finance/archived + LPJ CASH_LPJ verified_ga/archived + voucher rekanan verified_ga/archived',
}
BASIS_VERSION = 'bbm-scope-2'


def default_period(days=30, today=None):
    """(start, end) ISO untuk `days` hari terakhir, inklusif."""
    end = today or date.today()
    start = end - timedelta(days=max(1, int(days)) - 1)
    return start.isoformat(), end.isoformat()


def _placeholders(values):
    return ', '.join(['%s'] * len(values))


def statuses_in(statuses, alias=''):
    """Fragmen SQL `status IN (...)` dari satu set status.

    Dipakai supaya definisi status TIDAK ditulis ulang di tiap query: cukup
    Costi, statuses, dan parameternya. Memakai helper ini membuat definisi
    tetap satu sumber kebenaran (v2.104.0 — Phase 4, rapikan duplikasi).
    """
    p = f'{alias}.' if alias else ''
    return f"{p}status IN ({_placeholders(statuses)})"


def _date_clause(column, start, end):
    """Klausa rentang tanggal inklusif. Returns (sql, params)."""
    parts, params = [], []
    if start:
        parts.append(f'DATE({column}) >= %s')
        params.append(start)
    if end:
        parts.append(f'DATE({column}) <= %s')
        params.append(end)
    return (' AND ' + ' AND '.join(parts)) if parts else '', params


def _tx_totals(conn, start, end, tx_type, statuses=None, voucher=None):
    """Agregat transaksi satu jenis (opsional status & label voucher).

    `voucher=True` → hanya baris berlabel voucher (SPBU rekanan + kolom voucher
    terisi); `voucher=False` → hanya baris cash; `None` → semua baris jenis itu.
    """
    sql = [
        "SELECT COUNT(*) AS count, COALESCE(SUM(nominal), 0) AS amount, "
        "COALESCE(SUM(liter), 0) AS liter FROM transactions",
        "WHERE COALESCE(transaction_type, 'CLAIM') = %s",
        "AND (is_dummy = 0 OR is_dummy IS NULL)",
    ]
    params = [tx_type]
    if voucher is True:
        sql.append("AND COALESCE(voucher_value, 0) > 0")
    elif voucher is False:
        sql.append("AND COALESCE(voucher_value, 0) = 0")
    if statuses:
        sql.append(f'AND status IN ({_placeholders(statuses)})')
        params.extend(statuses)
    clause, date_params = _date_clause('created_at', start, end)
    query = ' '.join(sql) + clause
    params.extend(date_params)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(query, params)
        row = cur.fetchone() or {}
    finally:
        cur.close()
    return {
        'count': int(row.get('count') or 0),
        'amount': round(float(row.get('amount') or 0), 2),
        'liter': round(float(row.get('liter') or 0), 2),
    }


def claim_metrics(conn, start, end):
    """Ember klaim BBM + LPJ untuk satu periode."""
    return {
        # Ember "klaim" hanya uang tunai ke driver. Baris voucher dipisah ke
        # ember voucher_sah agar tidak dihitung sebagai pencairan klaim.
        'masuk': _tx_totals(conn, start, end, 'CLAIM', CLAIM_OPEN_STATUSES, voucher=False),
        'siap_cair': _tx_totals(conn, start, end, 'CLAIM', CLAIM_READY_STATUSES, voucher=False),
        'dibayar': _tx_totals(conn, start, end, 'CLAIM', CLAIM_PAID_STATUSES, voucher=False),
        'final': _tx_totals(conn, start, end, 'CLAIM', CLAIM_FINAL_STATUSES, voucher=False),
        'lpj_diajukan': _tx_totals(conn, start, end, 'CASH_LPJ', LPJ_OPEN_STATUSES),
        'lpj_sah': _tx_totals(conn, start, end, 'CASH_LPJ', LPJ_VALID_STATUSES),
        'voucher_masuk': _tx_totals(conn, start, end, 'CLAIM', VOUCHER_OPEN_STATUSES, voucher=True),
        'voucher_sah': _tx_totals(conn, start, end, 'CLAIM', VOUCHER_VALID_STATUSES, voucher=True),
    }


def _cash_aggregate(conn, where, params=None):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS amount "
            "FROM fuel_cash_requests WHERE " + where, params or [])
        row = cur.fetchone() or {}
    finally:
        cur.close()
    return {
        'count': int(row.get('count') or 0),
        'amount': round(float(row.get('amount') or 0), 2),
    }


def cash_totals(conn, start=None, end=None):
    """Kasbon: diajukan (periode), cair/selesai (periode), outstanding (kini).

    `cair` memakai handover_at — dana yang sudah keluar — bukan hanya yang
    sudah COMPLETED. `outstanding` selalu dihitung tanpa batas tanggal karena
    uang yang masih di driver harus terlihat kapan pun laporan dibuka.
    """
    date_sql, date_params = _date_clause('handover_at', start, end)
    cair = _cash_aggregate(conn, 'handover_at IS NOT NULL' + date_sql, date_params)
    selesai = _cash_aggregate(
        conn, f"handover_at IS NOT NULL AND status = '{CASH_DONE_STATUS}'" + date_sql,
        date_params)
    outstanding = _cash_aggregate(
        conn,
        "handover_at IS NOT NULL AND status IN ("
        + _placeholders(CASH_OPEN_STATUSES) + ')',
        list(CASH_OPEN_STATUSES))

    diajukan_sql = f"status <> '{CASH_VOID_STATUS}'"
    diajukan_clause, diajukan_params = _date_clause('created_at', start, end)
    diajukan = _cash_aggregate(conn, diajukan_sql + diajukan_clause, diajukan_params)

    return {
        'diajukan': diajukan,
        'cair': cair,
        'selesai': selesai,
        'outstanding': outstanding,
    }


def monthly_cash_rows(conn, year):
    """Vektor 12 bulan kasbon cair (basis handover_at)."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT MONTH(handover_at) AS m, "
            "COALESCE(SUM(total_amount), 0) AS amount "
            "FROM fuel_cash_requests "
            "WHERE handover_at IS NOT NULL AND YEAR(handover_at) = %s "
            "GROUP BY MONTH(handover_at)", (year,))
        return cur.fetchall() or []
    finally:
        cur.close()


def monthly_lpj_rows(conn, year):
    """Vektor 12 bulan LPJ sah (basis created_at)."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT MONTH(created_at) AS m, "
            "COALESCE(SUM(nominal), 0) AS amount "
            "FROM transactions "
            "WHERE transaction_type = 'CASH_LPJ' "
            f"AND status IN ({_placeholders(LPJ_VALID_STATUSES)}) "
            "AND (is_dummy = 0 OR is_dummy IS NULL) "
            "AND YEAR(created_at) = %s "
            "GROUP BY MONTH(created_at)",
            tuple(LPJ_VALID_STATUSES) + (year,))
        return cur.fetchall() or []
    finally:
        cur.close()


def monthly_voucher_rows(conn, year):
    """Vektor 12 bulan voucher rekanan sah (basis created_at, sekali)."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT MONTH(created_at) AS m, "
            "COALESCE(SUM(nominal), 0) AS amount "
            "FROM transactions "
            "WHERE transaction_type = 'CLAIM' "
            "AND COALESCE(voucher_value, 0) > 0 "
            f"AND status IN ({_placeholders(VOUCHER_VALID_STATUSES)}) "
            "AND (is_dummy = 0 OR is_dummy IS NULL) "
            "AND YEAR(created_at) = %s "
            "GROUP BY MONTH(created_at)",
            tuple(VOUCHER_VALID_STATUSES) + (year,))
        return cur.fetchall() or []
    finally:
        cur.close()


def summary(conn, start=None, end=None):
    """Ringkasan lintas kategori untuk satu periode & satu DB cabang.

    Angka di sini adalah sumber yang sama dengan Rekap, Realisasi, dan
    Analisis. Pemanggil bertanggung jawab atas cakupan cabang (lihat
    modules/branch_scope.py).
    """
    start = start or default_period()[0]
    end = end or default_period()[1]
    claims = claim_metrics(conn, start, end)
    cash = cash_totals(conn, start, end)
    return {
        'period': {'start': start, 'end': end},
        'claims': claims,
        'kasbon': cash,
        'realisasi': {
            'lpj_sah': claims['lpj_sah']['amount'],
            'klaim_dibayar': claims['dibayar']['amount'],
            'voucher_sah': claims['voucher_sah']['amount'],
            'total': round(claims['lpj_sah']['amount']
                           + claims['dibayar']['amount']
                           + claims['voucher_sah']['amount'], 2),
        },
        'meta': {
            'basis': BASIS,
            'basis_version': BASIS_VERSION,
            'generated_at': None,
        },
    }
