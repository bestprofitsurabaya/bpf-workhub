"""Antrean "Perlu Tindakan" untuk meja kerja BBM (v2.103.0 — Fase 3).

Antrean ini menjawab "apa yang menunggu saya sekarang", bukan "berapa biaya
periode ini". Karena itu umurnya dihitung dari waktu sekarang, bukan dari
periode laporan yang dipilih di context bar.

Ambang (SOP, satu tempat — ubah di sini bila SOP berubah):
  klaim   > 2 hari   menunggu verifikasi GA
  driver  > 14 hari  dana sudah diserahkan, LPJ belum masuk
  lpj     > 7 hari   LPJ masuk, menunggu verifikasi GA

v2.104.0 — dua penambahan:

1. **Baris nyata, bukan hanya jumlah.** Setiap item antrean membawa baris
   yang menunggu (dibatasi `MAX_ROWS`), sehingga aksi — verifikasi GA,
   approve/tolak LPJ — bisa diambil langsung dari antrean. Aksinya TIDAK
   dibuat baru: endpoint dan step-up PIN yang sudah ada tetap dipakai.

2. **Antrean keempat: SPBU mismatch.** Aturannya **bukan aturan baru** —
   ini verdict yang sudah ditulis mesin auto-match
   (`transactions.subsidy_match = 'mismatch'`, lihat
   `modules/routes_subsidy.py::_judge`: volume/nominal di luar toleransi).
   Antrean ini hanya MEMBACA nilai itu, tidak menilai ulang. Ambang umurnya
   sama dengan ambang klaim (2 hari) supaya antrean tetap berisi pekerjaan
   yang benar-benar sudah menunggu. Status `no_record` sengaja TIDAK
   masuk: itu berarti tidak ada kandidat SPBU sama sekali (bisa karena data
   belum ditarik), bukan selisih angka.

Hanya status yang benar-benar menunggu aksi yang dihitung; `archived`,
`COMPLETED`, dan `REJECTED` tidak pernah masuk antrean. Tidak ada data yang
diubah modul ini — murni baca.
"""
from datetime import datetime, timedelta

ACTION_THRESHOLDS = {
    'claim_days': 2,
    'driver_days': 14,
    'lpj_days': 7,
}

# Batas baris per item supaya payload antrean tetap kecil. Jumlah total dan
# nominal tetap akurat karena dihitung dengan query agregat terpisah.
MAX_ROWS = 20

# Status kasbon yang berarti "dana masih di driver" (belum ada LPJ sah).
CASH_OUTSTANDING_STATUSES = ('FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED')


def _claim_where(extra=''):
    return (
        "COALESCE(transaction_type, 'CLAIM') = 'CLAIM' "
        "AND status IN ('pending', 'modified') "
        "AND (is_dummy = 0 OR is_dummy IS NULL)"
        + extra
    )


# (key, label, kind, threshold, target, query agregat, query baris)
_QUEUE_SPECS = (
    {
        'key': 'claim_pending',
        'label': 'Klaim menunggu verifikasi GA',
        'kind': 'claim',
        'threshold': 'claim_days',
        'target': 'bbm',
        'count_sql': (
            "SELECT COUNT(*) AS n, COALESCE(SUM(nominal), 0) AS amount, "
            "MIN(created_at) AS oldest FROM transactions WHERE "
            + _claim_where(" AND created_at < %s")
        ),
        'rows_sql': (
            "SELECT id, COALESCE(display_id, '') AS ref, COALESCE(driver_name, '') AS driver_name, "
            "COALESCE(nopol, '') AS nopol, COALESCE(nominal, 0) AS amount, created_at AS since "
            "FROM transactions WHERE " + _claim_where(" AND created_at < %s") +
            " ORDER BY created_at ASC LIMIT %s"
        ),
    },
    {
        'key': 'driver_due_lpj',
        'label': 'Dana di driver, LPJ belum masuk',
        'kind': 'cash',
        'threshold': 'driver_days',
        'target': 'kasbon',
        'count_sql': (
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount, "
            "MIN(handover_at) AS oldest FROM fuel_cash_requests "
            "WHERE status = 'FUNDS_WITH_DRIVER' AND handover_at IS NOT NULL "
            "AND handover_at < %s"
        ),
        'rows_sql': (
            "SELECT id, COALESCE(display_id, '') AS ref, COALESCE(driver_name, '') AS driver_name, "
            "COALESCE(nopol, '') AS nopol, COALESCE(total_amount, 0) AS amount, handover_at AS since "
            "FROM fuel_cash_requests "
            "WHERE status = 'FUNDS_WITH_DRIVER' AND handover_at IS NOT NULL "
            "AND handover_at < %s ORDER BY handover_at ASC LIMIT %s"
        ),
    },
    {
        'key': 'lpj_pending',
        'label': 'LPJ menunggu verifikasi GA',
        'kind': 'cash',
        'threshold': 'lpj_days',
        'target': 'kasbon',
        'count_sql': (
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount, "
            "MIN(lpj_submitted_at) AS oldest FROM fuel_cash_requests "
            "WHERE status = 'LPJ_SUBMITTED' AND lpj_submitted_at IS NOT NULL "
            "AND lpj_submitted_at < %s"
        ),
        'rows_sql': (
            "SELECT id, COALESCE(display_id, '') AS ref, COALESCE(driver_name, '') AS driver_name, "
            "COALESCE(nopol, '') AS nopol, COALESCE(total_amount, 0) AS amount, "
            "lpj_submitted_at AS since FROM fuel_cash_requests "
            "WHERE status = 'LPJ_SUBMITTED' AND lpj_submitted_at IS NOT NULL "
            "AND lpj_submitted_at < %s ORDER BY lpj_submitted_at ASC LIMIT %s"
        ),
    },
    {
        # v2.104.0 — verdict yang SUDAH ditulis mesin auto-match; modul ini
        # hanya membacanya. Klaim yang sudah ditutup (arsip/ditolak) tidak
        # masuk antrean:-matched atau tidak, tidak ada yang menunggu.
        'key': 'spbu_mismatch',
        'label': 'Nilai BBM tidak cocok dengan data SPBU',
        'kind': 'claim',
        'threshold': 'claim_days',
        'target': 'subsidy',
        'count_sql': (
            "SELECT COUNT(*) AS n, COALESCE(SUM(nominal), 0) AS amount, "
            "MIN(created_at) AS oldest FROM transactions "
            "WHERE subsidy_match = 'mismatch' "
            "AND status NOT IN ('archived', 'rejected') "
            "AND (is_dummy = 0 OR is_dummy IS NULL) "
            "AND created_at < %s"
        ),
        'rows_sql': (
            "SELECT id, COALESCE(display_id, '') AS ref, COALESCE(driver_name, '') AS driver_name, "
            "COALESCE(nopol, '') AS nopol, COALESCE(nominal, 0) AS amount, created_at AS since "
            "FROM transactions WHERE subsidy_match = 'mismatch' "
            "AND status NOT IN ('archived', 'rejected') "
            "AND (is_dummy = 0 OR is_dummy IS NULL) "
            "AND created_at < %s ORDER BY created_at ASC LIMIT %s"
        ),
    },
)


def _age_days(oldest, now):
    if not oldest:
        return None
    try:
        return max(0, (now - oldest).days)
    except TypeError:
        return None


def _row_age(row, now):
    """Umur baris dalam hari (basis `since`)."""
    return _age_days(row.get('since'), now)


def _rows(cur, sql, cutoff, now):
    """Ambil baris antrean (dibatasi MAX_ROWS) + umur per baris."""
    cur.execute(sql, (cutoff, MAX_ROWS))
    fetched = cur.fetchall() or []
    out = []
    for row in fetched:
        amount = float(row.get('amount') or 0)
        out.append({
            'id': row.get('id'),
            'ref': row.get('ref') or '',
            'driver_name': row.get('driver_name') or '',
            'nopol': row.get('nopol') or '',
            'amount': amount,
            'age_days': _row_age(row, now),
        })
    return out


def action_queue(conn, now=None):
    """Bangun antrean tindakan dari koneksi cabang sesi.

    Mengembalikan:
      {items: [{key, label, kind, count, amount, oldest_days, threshold_days,
                target, rows: [{id, ref, driver_name, nopol, amount, age_days}]}],
       thresholds: {...}, errors: [{key, error}], generated_at: 'YYYY-MM-DD HH:MM:SS'}

    Satu jenis antrean yang gagal (mis. kolom `subsidy_match` belum ada di
    DB cabang lama) TIDAK boleh mematikan seluruh panel — jenis itu dilewati
    dan errornya dilaporkan terpisah.
    """
    now = now or datetime.now()
    cur = conn.cursor(dictionary=True)
    items = []
    errors = []
    try:
        for spec in _QUEUE_SPECS:
            cutoff = now - timedelta(days=ACTION_THRESHOLDS[spec['threshold']])
            try:
                cur.execute(spec['count_sql'], (cutoff,))
                row = cur.fetchone() or {}
                count = int(row.get('n') or 0)
                rows = _rows(cur, spec['rows_sql'], cutoff, now) if count else []
            except Exception as e:  # noqa: BLE001 — satu jenis gagal ≠ panel gagal
                errors.append({'key': spec['key'], 'error': str(e)[:200]})
                continue
            if count <= 0:
                continue
            items.append({
                'key': spec['key'],
                'label': spec['label'],
                'kind': spec['kind'],
                'count': count,
                'amount': float(row.get('amount') or 0),
                'oldest_days': _age_days(row.get('oldest'), now),
                'threshold_days': ACTION_THRESHOLDS[spec['threshold']],
                'target': spec['target'],
                'rows': rows,
            })
    finally:
        cur.close()
    return {
        'items': items,
        'thresholds': dict(ACTION_THRESHOLDS),
        'errors': errors,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
    }
