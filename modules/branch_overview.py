"""Ringkasan lintas cabang untuk Admin Pusat (v2.114.0 — Fase 1 "Pusat").

Pusat tidak perlu membuka 12 dashboard satu per satu untuk tahu cabang mana
yang perlu ditindak. Satu endpoint membaca **antrean kerja** (bukan angka
laporan periode) dari DB tiap cabang, lalu menambahkan antrean yang sumbernya
DB master (`branch_code`).

Prinsip:
- **Baca saja.** Modul ini tidak pernah menulis, tidak mengubah status, dan
  tidak menjalankan aksi atas nama cabang.
- **Satu definisi.** Status yang dihitung sama dengan badge sidebar &
  `bbm_action_queue` (klaim `pending/modified`, kasbon `FUNDS_WITH_DRIVER`,
  LPJ `LPJ_SUBMITTED` > 7 hari) — tidak ada aturan baru.
- **Gagal sebagian boleh.** DB satu cabang mati / kolom lama belum ada →
  sinyal itu `None` + dicatat di `errors`; cabang lain tetap tampil.
- **Cache 60 detik.** 12 DB × 8 query tiap muat dashboard terlalu mahal;
  `?refresh=1` melewati cache untuk pemeriksaan langsung.

Sinyal per DB cabang (`transactions`, `fuel_cash_requests`, `water_purchases`)
dan per DB master (`cv_online_submissions`, `first_work_submissions`).
Overtime tidak dihitung: tabelnya menyimpan catatan kehadiran, bukan antrean
persetujuan, jadi tidak ada status "menunggu" yang jujur untuk dilaporkan.
"""
from datetime import datetime
import threading

from modules import branch_manager as bm

CACHE_TTL_SECONDS = 60

# (key, label, SQL). SQL mengembalikan kolom `n` dan opsional `amount`.
BRANCH_SIGNALS = (
    ('bbm_pending', 'Klaim BBM menunggu GA',
     "SELECT COUNT(*) AS n FROM transactions "
     "WHERE status IN ('pending', 'modified') "
     "AND COALESCE(voucher_value, 0) = 0 "
     "AND (is_dummy = 0 OR is_dummy IS NULL)"),
    ('bbm_ready', 'Klaim siap dicairkan Finance',
     "SELECT COUNT(*) AS n FROM transactions "
     "WHERE status = 'verified_ga' "
     "AND COALESCE(transaction_type, 'CLAIM') = 'CLAIM' "
     "AND COALESCE(voucher_value, 0) = 0 "
     "AND (is_dummy = 0 OR is_dummy IS NULL)"),
    ('kasbon_driver', 'Kasbon masih di driver',
     "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount "
     "FROM fuel_cash_requests WHERE status = 'FUNDS_WITH_DRIVER'"),
    ('lpj_late', 'LPJ > 7 hari belum diverifikasi',
     "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount "
     "FROM fuel_cash_requests WHERE status = 'LPJ_SUBMITTED' "
     "AND lpj_submitted_at IS NOT NULL "
     "AND lpj_submitted_at < (NOW() - INTERVAL 7 DAY)"),
    ('spbu_mismatch', 'Nilai BBM tidak cocok SPBU',
     "SELECT COUNT(*) AS n FROM transactions "
     "WHERE subsidy_match = 'mismatch' "
     "AND status NOT IN ('archived', 'rejected') "
     "AND (is_dummy = 0 OR is_dummy IS NULL)"),
    ('water_pending', 'Air minum menunggu verifikasi',
     "SELECT COUNT(*) AS n FROM water_purchases WHERE status = 'pending'"),
    # Sinyal pendukung badge sidebar untuk Admin Pusat. Tidak ditampilkan di
    # tabel Pusat (kolomnya sudah cukup), tetapi ikut dihitung di `totals`
    # supaya badge menu menunjukkan beban kerja seluruh cabang.
    ('cash_ga', 'Kasbon menunggu verifikasi GA',
     "SELECT COUNT(*) AS n FROM fuel_cash_requests WHERE status = 'LPJ_SUBMITTED'"),
    ('cash_finance', 'Kasbon menunggu pencairan Finance',
     "SELECT COUNT(*) AS n FROM fuel_cash_requests WHERE status = 'GA_APPROVED'"),
    ('assignments_pending', 'Penugasan belum dikonfirmasi driver',
     "SELECT COUNT(*) AS n FROM vehicle_assignments "
     "WHERE is_current = 1 AND confirmed_by_driver = 0"),
)

# (key, label, tabel master). Semua memakai kolom `branch_code` + status.
MASTER_SIGNALS = (
    ('cv_new', 'Registrasi CV baru', 'cv_online_submissions'),
    ('first_work_new', 'Absensi FirstWork baru', 'first_work_submissions'),
)

SIGNAL_LABELS = {k: label for k, label, _ in BRANCH_SIGNALS}
SIGNAL_LABELS.update({k: label for k, label, _ in MASTER_SIGNALS})

# Sinyal yang nominalnya bermakna (kolom `amount`).
SIGNAL_AMOUNTS = {'kasbon_driver', 'lpj_late'}

# Hanya sinyal ini yang dihitung sebagai "perlu perhatian" di urutan tabel.
# Sinyal pendukung badge (`cash_*`, `assignments_pending`) tidak menambah
# skor perhatian — angka badge memang gabungan beberapa antrean.
ATTENTION_KEYS = {
    'bbm_pending', 'bbm_ready', 'kasbon_driver', 'lpj_late',
    'spbu_mismatch', 'water_pending', 'cv_new', 'first_work_new',
}

_cache = {}
_lock = threading.Lock()


def _cache_key(codes):
    """Kunci cache: `*` untuk semua cabang, selain itu daftar kode terurut."""
    if codes is None:
        return '*'
    return '|'.join(sorted(str(c).strip().upper() for c in codes if str(c).strip()))


def _connect_db(db_name):
    """Koneksi ke satu DB cabang (master DB memakai pool master)."""
    from modules.config import DB_CONFIG, _pool_for, get_master_connection
    if not db_name:
        return None
    if db_name == DB_CONFIG['database']:
        return get_master_connection()
    pool = _pool_for(db_name)
    return pool.get_connection() if pool else None


def _read_signals(conn):
    """Jalankan semua sinyal pada satu koneksi; kegagalan per sinyal diisolasi."""
    counts = {}
    amounts = {}
    errors = []
    cur = conn.cursor(dictionary=True)
    try:
        for key, _label, sql in BRANCH_SIGNALS:
            try:
                cur.execute(sql)
                row = cur.fetchone() or {}
                counts[key] = int(row.get('n') or 0)
                if key in SIGNAL_AMOUNTS:
                    amounts[key] = float(row.get('amount') or 0)
            except Exception as exc:
                # DB cabang lama bisa belum punya tabel/kolom ini. Itu bukan
                # alasan mematikan seluruh panel — tandai "tidak tersedia".
                counts[key] = None
                errors.append({'signal': key, 'error': str(exc)[:160]})
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return counts, amounts, errors


def _master_counts(conn):
    """Hitung sinyal DB master per `branch_code` (satu query per tabel)."""
    per_branch = {key: {} for key, _l, _t in MASTER_SIGNALS}
    errors = []
    cur = conn.cursor(dictionary=True)
    try:
        for key, _label, table in MASTER_SIGNALS:
            try:
                cur.execute(
                    f"SELECT branch_code, COUNT(*) AS n FROM {table} "
                    "WHERE status = 'submitted' GROUP BY branch_code")
                for row in cur.fetchall() or []:
                    code = str(row.get('branch_code') or '').strip().upper()
                    per_branch[key][code] = int(row.get('n') or 0)
            except Exception as exc:
                errors.append({'signal': key, 'error': str(exc)[:160]})
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return per_branch, errors


def _build(codes=None, now=None):
    """Susun payload overview. `codes` membatasi cabang (Admin cabang)."""
    now = now or datetime.now()
    from modules.config import get_master_connection

    mc = get_master_connection()
    if not mc:
        return {
            'branches': [], 'totals': {}, 'amounts': {},
            'summary': {'branches_total': 0, 'branches_attention': 0,
                        'signals_total': 0},
            'errors': [{'signal': 'master', 'error': 'DB master tidak tersedia'}],
            'cache_ttl': CACHE_TTL_SECONDS,
            'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

    try:
        branches = bm.list_branches(conn=mc)
        master_counts, master_errors = _master_counts(mc)
    finally:
        try:
            mc.close()
        except Exception:
            pass

    allowed = None
    if codes is not None:
        allowed = {str(c).strip().upper() for c in codes}

    rows = []
    totals = {key: 0 for key, _l, _s in BRANCH_SIGNALS}
    amounts = {key: 0.0 for key in SIGNAL_AMOUNTS}
    for key in master_counts:
        totals[key] = 0

    for b in branches:
        code = str(b.get('code') or '').strip().upper()
        if allowed is not None and code not in allowed:
            continue
        row = {
            'code': code,
            'name': b.get('name') or code,
            'db_name': b.get('db_name') or '',
            'is_active': bool(b.get('is_active')),
            'status': 'inactive' if not b.get('is_active') else 'ok',
            'signals': {key: None for key, _l, _s in BRANCH_SIGNALS},
            'amounts': {},
            'errors': [],
        }
        for key, _label, _table in MASTER_SIGNALS:
            row['signals'][key] = int(master_counts.get(key, {}).get(code, 0))

        if row['is_active'] and row['db_name']:
            conn = None
            try:
                conn = _connect_db(row['db_name'])
                if not conn:
                    row['status'] = 'error'
                    row['errors'].append({'signal': 'db', 'error': 'DB tidak tersedia'})
                else:
                    signals, signal_amounts, errors = _read_signals(conn)
                    row['signals'].update(signals)
                    row['amounts'] = signal_amounts
                    row['errors'].extend(errors)
                    if errors:
                        row['status'] = 'partial'
            except Exception as exc:
                row['status'] = 'error'
                row['errors'].append({'signal': 'db', 'error': str(exc)[:160]})
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        attention = sum(int(v) for k, v in row['signals'].items()
                        if v and k in ATTENTION_KEYS)
        row['attention'] = attention
        rows.append(row)

        for key, value in row['signals'].items():
            if value is not None:
                totals[key] = int(totals.get(key, 0)) + int(value)
        for key, value in row['amounts'].items():
            amounts[key] = round(amounts.get(key, 0.0) + float(value or 0), 2)

    rows.sort(key=lambda r: (-r['attention'], r['code']))
    return {
        'branches': rows,
        'totals': totals,
        'amounts': amounts,
        'summary': {
            'branches_total': len(rows),
            'branches_attention': sum(1 for r in rows if r['attention'] > 0),
            'signals_total': sum(int(v or 0) for v in totals.values()),
        },
        'errors': master_errors,
        'cache_ttl': CACHE_TTL_SECONDS,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
    }


def overview(codes=None, force=False, now=None):
    """Payload ringkasan lintas cabang (cache 60 detik).

    `codes=None` = semua cabang (Admin Pusat). Admin cabang mengirim daftar
    kode miliknya sehingga tidak pernah membaca DB cabang lain.
    """
    key = _cache_key(codes)
    now = now or datetime.now()
    if not force:
        hit = _cache.get(key)
        if hit and (now - hit[0]).total_seconds() < CACHE_TTL_SECONDS:
            payload = dict(hit[1])
            payload['cached'] = True
            return payload
    with _lock:
        payload = _build(codes, now)
        _cache[key] = (now, payload)
    out = dict(payload)
    out['cached'] = False
    return out


def invalidate_cache():
    """Kosongkan cache (dipakai saat cabang disimpan/diaktifkan)."""
    with _lock:
        _cache.clear()
