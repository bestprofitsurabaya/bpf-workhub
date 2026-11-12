"""Cakupan cabang untuk laporan & operasional finance (v2.99.1).

Aturan keras — data antar cabang tidak boleh tercampur:

- **Admin Pusat** (`admin` / flag `admin_all_branches`) → semua cabang.
- **Finance HO** (`finance_hu`, bisa ditambah lewat env `FINANCE_HO_USERNAMES`)
  → semua cabang, karena tugasnya mengonsolidasi laporan.
- **Finance cabang lain** → HANYA cabang pada sesinya. `?branch=ALL` maupun
  kode cabang lain ditolak 403; tanpa parameter pun tetap cabang sendiri,
  bukan default SBY.
- **Admin cabang** → kode dari `users.managed_branches` + suffix username;
  `ALL` hanya bila Admin Pusat.
- Sesi tanpa cabang dan bukan HO → fail-closed (403).

Dipakai endpoint laporan yang membaca lebih dari satu DB cabang
(`/api/expenses/recap`, `/api/expenses/detail`, dan endpoint workspace BBM
berikutnya). Endpoint yang memakai `get_db_connection()` sudah ter-scope oleh
DB sesi dan tidak perlu aturan ini.
"""
import os

from flask import session

from modules.admin_scope import admin_branches, is_ho_admin

# Finance HO: username (bukan role) yang boleh melihat semua cabang.
HO_FINANCE_USERNAMES = {'finance_hu'} | {
    u.strip().lower() for u in os.environ.get('FINANCE_HO_USERNAMES', '').split(',')
    if u.strip()
}


def _norm(code):
    return str(code or '').strip().upper()


def _username():
    return str(session.get('user_name') or '').strip().lower()


def is_ho_finance():
    """True bila sesi finance ini adalah Finance HO (boleh semua cabang)."""
    if (session.get('user_role') or '').strip().lower() != 'finance':
        return False
    return _username() in HO_FINANCE_USERNAMES


def session_branch_code():
    """Kode cabang sesi ('' bila tidak ada)."""
    return _norm(session.get('branch_code'))


def sees_all_branches():
    """True bila sesi boleh melihat seluruh cabang (Admin Pusat / Finance HO).

    Dipakai endpoint yang datanya tersimpan di DB master (mis. registry
    Berita Acara SPBU) sehingga tidak bisa mengandalkan routing DB sesi.
    """
    role = (session.get('user_role') or '').strip().lower()
    if role == 'admin':
        return is_ho_admin()
    if role == 'finance':
        return is_ho_finance()
    return False


def visible_branch_codes(branches):
    """Kode cabang yang boleh dilihat sesi ini, dari daftar cabang aktif.

    Returns (kode_set, boleh_semua). Fail-closed: sesi tak dikenal → set kosong.
    """
    role = (session.get('user_role') or '').strip().lower()
    codes = {b['code'] for b in branches}
    if role == 'admin':
        admin_codes, all_branches = admin_branches()
        if all_branches:
            return set(codes), True
        return {c for c in _norm_list(admin_codes) if c in codes}, False
    if role == 'finance':
        if is_ho_finance():
            return set(codes), True
        own = _norm(session.get('branch_code'))
        return ({own} & codes) if own else set(), False
    return set(), False


def _norm_list(values):
    return [_norm(v) for v in values or [] if _norm(v)]


def resolve_report_scope(branches, requested):
    """Tentukan cabang yang boleh dibaca sebuah laporan.

    Args:
        branches: baris aktif dari tabel `branches` (master).
        requested: nilai `?branch=` mentah (kode atau 'ALL', boleh kosong).

    Returns:
        (targets, selected, visible, error)
        - targets : baris cabang yang akan dihitung
        - selected: 'ALL' atau kode cabang
        - visible : baris cabang yang boleh muncul di pemilih
        - error   : None | 'unknown' | 'forbidden'
    """
    by_code = {b['code']: b for b in branches}
    req = _norm(requested)

    # Kode yang tidak ada tetap 400 (pesan "tidak dikenal"), bukan 403 —
    # agar salah ketik tidak disamarkan sebagai masalah izin.
    if req and req != 'ALL' and req not in by_code:
        return [], None, [], 'unknown'

    allowed, all_branches = visible_branch_codes(branches)
    visible = [b for b in branches if b['code'] in allowed]
    if not visible:
        return [], None, [], 'forbidden'

    if req == 'ALL':
        if not all_branches:
            return [], None, [], 'forbidden'
        return list(visible), 'ALL', visible, None

    if req:
        if req not in allowed:
            return [], None, [], 'forbidden'
        return [by_code[req]], req, visible, None

    # Tanpa parameter: HO (Admin Pusat / Finance HO) memakai SELURUH cakupan
    # yang boleh ia lihat — sesuai desain (desain §5.1a: "Tanpa parameter =
    # ALL"). Finance/admin cabang tetap terkunci ke cabangnya.
    if all_branches:
        return list(visible), 'ALL', visible, None

    own = _norm(session.get('branch_code'))
    if own in allowed:
        selected = own
    elif len(visible) == 1:
        selected = visible[0]['code']
    else:
        return [], None, [], 'forbidden'

    targets = visible if selected == 'ALL' else [by_code[selected]]
    return targets, selected, visible, None
